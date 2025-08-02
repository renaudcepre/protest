from enum import Enum, auto


class Scope(Enum):
    """Defines the lifecycle scope for fixtures and tests."""

    SESSION = auto()
    SUITE = auto()
    FUNCTION = auto()
