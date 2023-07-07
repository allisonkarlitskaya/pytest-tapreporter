import os
import re
import subprocess
import sys
import textwrap
from typing import Hashable, List

import pytest
import tap.directive  # type: ignore[import]
import tap.line  # type: ignore[import]
import tap.parser  # type: ignore[import]
from syrupy.assertion import SnapshotAssertion
from syrupy.types import PropertyPath, SerializableData


def filter_pointers(text: str) -> str:
    return re.sub(r" object at 0x[0-9a-f]+", " object at ***", text)


def pointers_matcher(data: SerializableData, path: PropertyPath) -> SerializableData:
    del path
    if isinstance(data, str):
        return filter_pointers(data)
    return data


def filter_tap_results(prop: Hashable, path: PropertyPath) -> bool:
    if path:
        cls = path[-1][1]

        if issubclass(cls, tap.line.Result):
            return prop not in {"ok", "description", "directive", "yaml_block"}

        if issubclass(cls, tap.directive.Directive):
            return prop not in {"skip", "todo", "reason"}

    return False


def run_cases(config: pytest.Config, *args: str, plugins: str = "") -> str:
    env = dict(
        os.environ,
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_PLUGINS=",".join(["pytest_tapreporter.plugin", *plugins.split()]),
        PYTHONPATH=str(config.rootpath / "src"),
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tap", *args, "test/cases.py"],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    assert result.returncode == 1
    return result.stdout


def test_text(pytestconfig: pytest.Config, snapshot: SnapshotAssertion) -> None:
    assert run_cases(pytestconfig) == snapshot(matcher=pointers_matcher)


def need_workaround_for_tappy_132() -> bool:
    # https://github.com/python-tap/tappy/pull/132
    test_document = textwrap.dedent(
        """
        TAP version 14
        ok 1 - testcase
           ---
           x: |
             there's a newline here ->
           ...
    """
    ).lstrip()
    lines = list(tap.parser.Parser().parse_text(test_document))
    return "\n" not in lines[1].yaml_block["x"]


def parse_tap(text: str) -> List[tap.line.Result]:
    if need_workaround_for_tappy_132():
        # Add an extra newline to the end of every YAML block
        text = re.sub(r"^  \.\.\.$", r"  \n\g<0>", text, flags=re.M)

    text = filter_pointers(text)

    lines = list(tap.parser.Parser().parse_text(text))

    version = lines.pop(0)
    assert isinstance(version, tap.line.Version)
    assert version.version == 14

    plan = lines.pop(0)
    assert not plan.skip
    assert isinstance(plan, tap.line.Plan)
    assert all(isinstance(line, tap.line.Result) for line in lines)
    assert len(lines) == plan.expected_tests

    return lines


def test_parsed(pytestconfig: pytest.Config, snapshot: SnapshotAssertion) -> None:
    lines = parse_tap(run_cases(pytestconfig))

    for line in lines:
        name = line.description

        class_ran = "Skip" not in name  # class-level skip
        block_attrs = set(line.yaml_block or {})

        # Check status
        if "Strict::test_pass" in name:
            assert not line.ok
        elif "test_skip" in name or "Skip" in name:  # (or both)
            assert line.ok
        elif "test_pass" in name:
            assert line.ok
        else:
            assert not line.ok

        # (only) "output" tests write a message
        if class_ran and name.endswith("_output"):
            assert line.yaml_block["Captured stdout call"] == "Hello world\n"
        else:
            assert "Captured stdout call" not in block_attrs

        # Check error messages
        if class_ran and "test_raises" in name:
            assert line.yaml_block["message"] == "assert False"
        elif class_ran and "test_fail_reason" in name:
            assert line.yaml_block["message"] == "Failed: broken"
        elif class_ran and "test_fail" in name:
            assert line.yaml_block["message"] == "Failed"
        elif class_ran and "Strict::test_pass" in name:
            assert line.yaml_block["message"] == "unexpected pass"
        else:
            assert "message" not in block_attrs

        # Check skip/xfail
        if not class_ran:  # class skip
            assert line.skip
            if "Reason" in name or "Conditional" in name:
                assert line.directive.reason == "not supported"
            else:
                assert line.directive.reason == "unconditional skip"
        elif "test_skip" in name:
            assert line.skip
            if "_reason" in name:
                assert line.directive.reason == "not supported"
            else:
                assert not line.directive.reason
        else:
            assert not line.skip

            if "Xfail" in name:
                if "Strict::test_pass" in name:
                    assert not line.todo
                    assert not line.ok
                else:
                    assert line.todo

                if "Strict::test_pass" in name:
                    # We can't put the reason in the directive but we can add it in yaml
                    assert line.directive.reason is None

                    if "Reason" in name:
                        assert line.yaml_block["reason"] == "needs work"
                    else:
                        assert "reason" not in block_attrs
                else:
                    # It goes in the directive in this case, not the yaml
                    assert "reason" not in block_attrs

                    if "Reason" in name:
                        assert line.directive.reason == "needs work"
                    else:
                        assert line.directive.reason == ""

            else:
                assert not line.todo

        # Check traceback output
        if not line.ok and "Strict::test_pass" not in name:
            # We should have a traceback in this case
            assert "traceback" in block_attrs
        else:
            assert "traceback" not in block_attrs

    assert lines == snapshot(matcher=pointers_matcher, exclude=filter_tap_results)


def test_xdist(pytestconfig: pytest.Config) -> None:
    serial_lines = {line.description: line for line in parse_tap(run_cases(pytestconfig))}

    for line in parse_tap(run_cases(pytestconfig, "-n2", plugins="xdist.plugin")):
        assert line.description in serial_lines
        equiv = serial_lines[line.description]

        # There's no `Result.__eq__`, so we do it ourselves, excluding the
        # number (which is subject to reodering depending on xdist scheduling).
        for attr in ["ok", "description", "diagnostics", "skip", "todo"]:
            assert getattr(line, attr) == getattr(equiv, attr)

        # Also no `Directive.__eq__`
        if line.directive:
            for attr in ["skip", "todo", "text", "reason"]:
                assert getattr(line.directive, attr) == getattr(equiv.directive, attr)
        else:
            assert equiv.directive is None

        # Processing the YAML block needs some tweaks: we need to verify that
        # the [gw0] line is present, and remove it.
        if line.yaml_block:
            our_block = dict(line.yaml_block)
            if "traceback" in our_block:
                first_line, _, rest = our_block["traceback"].partition("\n\n")
                assert first_line.startswith("[gw")
                our_block["traceback"] = rest
            assert our_block == equiv.yaml_block
        else:
            assert equiv.yaml_block is None
