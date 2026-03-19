from __future__ import annotations

from enum import IntEnum


class Verbosity(IntEnum):
    """Output verbosity levels for reporters.

    Quiet:    summary only (-q)
    Normal:   suites + per-test results (default)
    Lifecycle: + setup/teardown events (-v)
    Fixtures:  + fixture lifecycle details (-vv)
    """

    QUIET = -1
    NORMAL = 0
    LIFECYCLE = 1
    FIXTURES = 2
