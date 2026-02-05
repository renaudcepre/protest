"""Tests for warns() context manager."""

import re
import warnings

import pytest

from protest import ProTestSession, warns
from protest.core.runner import TestRunner


class TestWarnsContextManager:
    """Tests for warns() context manager."""

    def test_warns_single_warning(self) -> None:
        """Single expected warning is captured."""
        with warns(UserWarning) as record:
            warnings.warn("test message", UserWarning, stacklevel=1)

        assert len(record) == 1
        assert record[0].category is UserWarning
        assert str(record[0].message) == "test message"

    def test_warns_fails_if_not_raised(self) -> None:
        """AssertionError raised if expected warning not raised."""
        with (
            pytest.raises(AssertionError, match="DID NOT WARN with UserWarning"),
            warns(UserWarning),
        ):
            pass

    def test_warns_match_pattern_string(self) -> None:
        """Pattern matching works with string."""
        with warns(UserWarning, match=r"must be \d+"):
            warnings.warn("value must be 42", UserWarning, stacklevel=1)

    def test_warns_match_pattern_compiled(self) -> None:
        """Pattern matching works with compiled regex."""
        pattern = re.compile(r"value: \w+")
        with warns(UserWarning, match=pattern):
            warnings.warn("value: test", UserWarning, stacklevel=1)

    def test_warns_match_fails_if_not_matched(self) -> None:
        """AssertionError if pattern doesn't match warning message."""
        with (
            pytest.raises(AssertionError, match=r"Pattern.*not found"),
            warns(UserWarning, match=r"\d{3}"),
        ):
            warnings.warn("no numbers here", UserWarning, stacklevel=1)

    def test_warns_multiple_types_tuple(self) -> None:
        """Tuple of warning types works."""
        with warns((DeprecationWarning, UserWarning)) as record:
            warnings.warn("deprecated", DeprecationWarning, stacklevel=1)

        assert len(record) == 1
        assert record[0].category is DeprecationWarning

    def test_warns_multiple_types_either_matches(self) -> None:
        """Either type in tuple can match."""
        with warns((DeprecationWarning, UserWarning)):
            warnings.warn("user warning", UserWarning, stacklevel=1)

    def test_warns_records_multiple_warnings(self) -> None:
        """Multiple warnings captured in record."""
        with warns(UserWarning) as record:
            warnings.warn("first", UserWarning, stacklevel=1)
            warnings.warn("second", UserWarning, stacklevel=1)

        assert len(record) == 2
        assert str(record[0].message) == "first"
        assert str(record[1].message) == "second"

    def test_warns_capture_only(self) -> None:
        """No argument captures any warning type without validation."""
        with warns() as record:
            warnings.warn("user", UserWarning, stacklevel=1)
            warnings.warn("runtime", RuntimeWarning, stacklevel=1)

        assert len(record) == 2
        assert record[0].category is UserWarning
        assert record[1].category is RuntimeWarning

    def test_warns_capture_only_empty_ok(self) -> None:
        """When expected_warning is None, no AssertionError if no warnings."""
        with warns() as record:
            pass

        assert len(record) == 0

    def test_warns_subclass_matching(self) -> None:
        """Warning subclasses match parent types."""

        class CustomWarning(UserWarning):
            pass

        with warns(UserWarning) as record:
            warnings.warn("custom", CustomWarning, stacklevel=1)

        assert len(record) == 1
        assert issubclass(record[0].category, UserWarning)

    def test_warns_deprecation_warning(self) -> None:
        """Common use case: catching DeprecationWarning."""
        with warns(DeprecationWarning, match="old_function"):
            warnings.warn(
                "old_function is deprecated", DeprecationWarning, stacklevel=1
            )

    def test_record_attributes(self) -> None:
        """Captured warnings have expected attributes."""
        with warns() as record:
            warnings.warn("test message", UserWarning, stacklevel=1)

        w = record[0]
        assert w.category is UserWarning
        assert str(w.message) == "test message"
        assert isinstance(w.filename, str)
        assert isinstance(w.lineno, int)


class TestWarnsWithProTestSession:
    """Tests for warns() integration with ProTest runner."""

    def test_warns_in_test_function(self) -> None:
        """warns() works inside a ProTest test function."""
        session = ProTestSession()

        @session.test()
        def test_with_warns() -> None:
            with warns(DeprecationWarning):
                warnings.warn("deprecated", DeprecationWarning, stacklevel=1)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_warns_failure_reported(self) -> None:
        """warns() failures are reported as test failures."""
        session = ProTestSession()

        @session.test()
        def test_warns_fails() -> None:
            with warns(UserWarning):
                pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False

    def test_warns_with_match_in_test(self) -> None:
        """warns() with match pattern works in tests."""
        session = ProTestSession()

        @session.test()
        def test_warns_match() -> None:
            with warns(UserWarning, match="important"):
                warnings.warn("This is important", UserWarning, stacklevel=1)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_warns_record_inspection_in_test(self) -> None:
        """warns() record can be inspected in tests."""
        session = ProTestSession()

        @session.test()
        def test_inspect_warnings() -> None:
            with warns() as record:
                warnings.warn("first", UserWarning, stacklevel=1)
                warnings.warn("second", RuntimeWarning, stacklevel=1)

            assert len(record) == 2
            assert record[0].category is UserWarning
            assert record[1].category is RuntimeWarning

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
