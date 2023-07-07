"""An extremely small plugin to add TAP reporting to pytest"""

import json
import re
import sys
from typing import Any, List, Set, TextIO

import pytest


class TapReporter:
    """The main plugin class"""

    config: pytest.Config
    output: TextIO
    plan_printed: bool
    reported: Set[str]

    def __init__(self, config: pytest.Config, output: TextIO):
        self.config = config
        self.output = output
        self.plan_printed = False
        self.reported = set()

    def print_plan(self, n_tests: int) -> None:
        """Print the test plan if it's not already written"""
        if not self.plan_printed:
            print("TAP version 14", file=self.output)
            print(f"1..{n_tests}", file=self.output)
            self.output.flush()
            self.plan_printed = True

    def report(
        self, report: pytest.TestReport, status: str, directive: str = "", directive_reason: str = "", **kwargs: str
    ) -> None:
        """Print a report line"""
        line = f"{status} {len(self.reported)} - {report.nodeid}"
        if directive:
            line += f" # {directive}"
            if directive_reason:
                line += f" {directive_reason}"
        lines = [line]

        try:
            # If we can read reprcrash.message then this was a crash
            kwargs["message"] = report.longrepr.reprcrash.message  # type: ignore[union-attr]
            kwargs["traceback"] = report.longreprtext
        except AttributeError:
            pass

        kwargs.update(report.sections)

        if kwargs:
            # something like yaml...
            lines.append("  ---")
            for key, value in kwargs.items():
                if "\n" in value:
                    lines.append(f"  {key}: |+")
                    lines.extend(f"    {line}" for line in value.splitlines())
                elif value:
                    lines.append(f"  {key}: {json.dumps(value)}")
            lines.append("  ...")
        print(*lines, sep="\n", file=self.output, flush=True)

    @pytest.hookimpl()
    def pytest_runtestloop(self, session: pytest.Session) -> None:
        """Print the test plan (non-xdist case)"""
        self.print_plan(session.testscollected)

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node: Any, ids: List[str]) -> None:
        """Print the test plan (xdist case)"""
        del node
        self.print_plan(len(ids))

    @pytest.hookimpl()
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Process a log report (when is 'setup', 'call', or 'teardown')"""
        category, _letter, _verbose = self.config.hook.pytest_report_teststatus(report=report, config=self.config)

        if category and report.nodeid not in self.reported:
            self.reported.add(report.nodeid)
        else:
            return

        if category == "passed":
            self.report(report, "ok")

        elif category == "skipped":
            assert isinstance(report.longrepr, tuple)
            reason = re.sub(r"^Skipped:? ?", "", report.longrepr[2])
            self.report(report, "ok", "SKIP", reason)

        elif category == "xfailed":
            assert isinstance(report.wasxfail, str)
            reason = re.sub(r"^reason:? ?", "", report.wasxfail)
            self.report(report, "not ok", "TODO", reason)

        elif category == "xpassed":
            assert isinstance(report.wasxfail, str)
            reason = re.sub(r"^reason:? ?", "", report.wasxfail)
            self.report(report, "ok", "TODO", reason)

        elif isinstance(report.longrepr, str) and report.longrepr.startswith("[XPASS(strict)]"):
            reason = re.sub("^[^ ]+ ", "", report.longrepr)
            self.report(report, "not ok", reason=reason, message="unexpected pass")

        else:
            self.report(report, "not ok")


@pytest.hookimpl
def pytest_addoption(parser: pytest.Parser) -> None:
    """Patch pytest's argumentparser"""
    parser.addoption("--tap", action="store_true", help="Enable TAP output")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """If --tap (and not --help), then enable TAP and disable normal output"""
    if config.option.tap and not config.option.help:
        config.pluginmanager.register(TapReporter(config, sys.stdout), "tapreporter")
        sys.stdout = open("/dev/null", "w")  # pylint: disable=consider-using-with,unspecified-encoding
