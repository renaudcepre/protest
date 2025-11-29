from enum import Enum


class Scope(Enum):
    """Defines the lifecycle scope for fixtures and tests.

    Values are ordered: SESSION (1) < SUITE (2) < FUNCTION (3).
    Lower values indicate wider scopes.
    """

    SESSION = 1
    SUITE = 2
    FUNCTION = 3
