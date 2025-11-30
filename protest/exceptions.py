class ProTestError(Exception):
    """Base exception for all errors raised by the ProTest framework."""


class FixtureError(ProTestError):
    """Raised when a factory fixture fails during test execution."""

    def __init__(self, fixture_name: str, original: Exception):
        self.fixture_name = fixture_name
        self.original = original
        super().__init__(f"Factory '{fixture_name}' failed: {original}")
