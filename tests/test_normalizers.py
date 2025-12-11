"""Tests for normalization functions."""

from protest.entities import (
    Retry,
    Skip,
    Xfail,
    normalize_retry,
    normalize_skip,
    normalize_xfail,
)


class TestNormalizeSkip:
    def test_none_returns_none(self) -> None:
        assert normalize_skip(None) is None

    def test_false_returns_none(self) -> None:
        assert normalize_skip(False) is None

    def test_true_returns_skip_with_default_reason(self) -> None:
        result = normalize_skip(True)
        assert result is not None
        assert result.reason == "Skipped"

    def test_string_returns_skip_with_reason(self) -> None:
        result = normalize_skip("WIP")
        assert result is not None
        assert result.reason == "WIP"

    def test_skip_object_returned_as_is(self) -> None:
        skip = Skip(reason="Custom")
        result = normalize_skip(skip)
        assert result is skip


class TestNormalizeXfail:
    def test_none_returns_none(self) -> None:
        assert normalize_xfail(None) is None

    def test_false_returns_none(self) -> None:
        assert normalize_xfail(False) is None

    def test_true_returns_xfail_with_default_reason(self) -> None:
        result = normalize_xfail(True)
        assert result is not None
        assert result.reason == "Expected failure"

    def test_string_returns_xfail_with_reason(self) -> None:
        result = normalize_xfail("Bug #123")
        assert result is not None
        assert result.reason == "Bug #123"

    def test_xfail_object_returned_as_is(self) -> None:
        xfail = Xfail(reason="Custom")
        result = normalize_xfail(xfail)
        assert result is xfail


class TestNormalizeRetry:
    def test_none_returns_none(self) -> None:
        assert normalize_retry(None) is None

    def test_int_returns_retry_with_times(self) -> None:
        result = normalize_retry(3)
        assert result is not None
        assert result.times == 3
        assert result.delay == 0.0
        assert result.on == (Exception,)

    def test_retry_object_returned_as_is(self) -> None:
        retry = Retry(times=2, delay=1.0)
        result = normalize_retry(retry)
        assert result is retry
