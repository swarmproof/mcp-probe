"""Process exit codes — the CI contract (ARCHITECTURE §7).

CI systems key off these, so they are a stable interface:

* ``0`` — pass (or a run that produced a report without tripping a gate).
* ``1`` — gate failure: ``--fail-under`` not met, or ``--no-regressions`` tripped.
  The run itself succeeded; the *quality bar* was not met.
* ``2`` — probe error: the target was unreachable, non-conformant, or the tool
  could not produce a report at all. Distinct from ``1`` so CI can tell "your
  server is bad" from "the probe broke."
"""

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    GATE_FAILURE = 1
    PROBE_ERROR = 2
