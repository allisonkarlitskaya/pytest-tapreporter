# `pytest-tapreporter`

An extremely small plugin to add TAP reporting to pytest.

`pytest-tapreporter` is a single file (100ish lines) which you can copy into
your project.  It has no dependencies beyond pytest.

`pytest-tapreporter` is continuously tested against Python 3.6 through 3.11.

## Usage

Just copy the `src/pytest_tapreporter/plugin.py` file into `conftest.py` in the
directory where your tests are.

Use with `pytest --tap`.

## Tests

Tests can be run with `tox`.

The default configuration won't download anything and requires the dependency
packages to be present locally.

`tox -m venv` will run linters and tests in virtual environments, on a variety
of Python versions (3.6 through 3.11).

## Mapping of test results to TAP

The output is TAP 14 with YAML blocks.

The following mappings are performed:

 - successes (`OK`) map to `ok` results, with no directive
 - failures and errors (`FAILED`, `ERROR`) map to `not ok` results, with no
   directive
 - skips (`SKIP`) map to `ok` with a `# SKIP` directive, appending a reason, if
   it was given
 - expected failures (`XFAIL`) map to `not ok` with `# TODO` directive,
   appending a reason, if it was given.  This is the expected behaviour
   according to the TAP specification.
 - unexpected successes (`XPASS`) in non-strict mode map to `ok` with a `#
   TODO` directive, appending a reason, if it was given.  This is what the TAP
   specification seems to specify in this case.
 - expected successes in strict mode aren't considered by the TAP
   specification and there is no way to map them to a result line directive.
   They are reported as `not ok`, without a directive, but the YAML block will
   then contain `message`: `unexpected success` and the reason, if applicable.

In case extra information is present, the YAML block will be written.  It can contain:

 - `reason`: the xfail reason in case of a pass on a strict xfail test
 - `message`: the main message for the failure (like `assert False` or `Failed`)
 - `traceback`: in case of crashes, the traceback usually shown by pytest
 - other "section" data from pytest such as `Captured stdout call`, etc.
