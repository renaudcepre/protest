import re

import pytest

from protest.assertions import ExceptionInfo, RaisesContext, raises


class TestRaisesBasic:
    def test_captures_expected_exception(self) -> None:
        with raises(ValueError):
            raise ValueError("test error")

    def test_raises_assertion_error_when_no_exception(self) -> None:
        with pytest.raises(AssertionError, match="DID NOT RAISE ValueError"):  # noqa: SIM117
            with raises(ValueError):
                pass

    def test_propagates_unexpected_exception_type(self) -> None:
        with pytest.raises(TypeError, match="wrong type"), raises(ValueError):
            raise TypeError("wrong type")

    def test_captures_subclass_exception(self) -> None:
        class CustomValueError(ValueError):
            pass

        with raises(ValueError) as exc_info:
            raise CustomValueError("subclass error")

        assert exc_info.type is CustomValueError


class TestRaisesWithMatch:
    def test_match_succeeds_with_matching_pattern(self) -> None:
        with raises(ValueError, match=r"invalid.*format"):
            raise ValueError("invalid input format")

    def test_match_fails_with_non_matching_pattern(self) -> None:
        with pytest.raises(AssertionError, match=r"Pattern.+not found") as outer:  # noqa: SIM117
            with raises(ValueError, match=r"expected pattern"):
                raise ValueError("actual message")

        assert outer.value.__cause__ is not None
        assert isinstance(outer.value.__cause__, ValueError)

    def test_match_with_compiled_pattern(self) -> None:
        pattern = re.compile(r"code: \d+")
        with raises(RuntimeError, match=pattern):
            raise RuntimeError("error code: 42")


class TestExceptionInfo:
    def test_value_returns_captured_exception(self) -> None:
        with raises(ValueError) as exc_info:
            raise ValueError("captured")

        assert str(exc_info.value) == "captured"

    def test_type_returns_exception_class(self) -> None:
        with raises(KeyError) as exc_info:
            raise KeyError("missing")

        assert exc_info.type is KeyError

    def test_traceback_is_available(self) -> None:
        with raises(ValueError) as exc_info:
            raise ValueError("with traceback")

        assert exc_info.traceback is not None

    def test_value_raises_before_exception_captured(self) -> None:
        exc_info: ExceptionInfo[ValueError] = ExceptionInfo()
        with pytest.raises(AssertionError, match="No exception captured yet"):
            _ = exc_info.value

    def test_type_raises_before_exception_captured(self) -> None:
        exc_info: ExceptionInfo[ValueError] = ExceptionInfo()
        with pytest.raises(AssertionError, match="No exception captured yet"):
            _ = exc_info.type

    def test_match_method_returns_match_object(self) -> None:
        with raises(TypeError) as exc_info:
            raise TypeError("expected str, got int")

        match_result = exc_info.match(r"expected (\w+), got (\w+)")
        assert match_result.group(1) == "str"
        assert match_result.group(2) == "int"

    def test_match_method_raises_on_no_match(self) -> None:
        with raises(ValueError) as exc_info:
            raise ValueError("actual message")

        with pytest.raises(AssertionError, match=r"Pattern.+not found") as outer:
            exc_info.match(r"nonexistent")

        assert outer.value.__cause__ is not None

    def test_match_method_with_compiled_pattern(self) -> None:
        with raises(RuntimeError) as exc_info:
            raise RuntimeError("status: OK")

        pattern = re.compile(r"status: (\w+)")
        match_result = exc_info.match(pattern)
        assert match_result.group(1) == "OK"


class TestRaisesContextDirectUsage:
    def test_context_manager_direct_instantiation(self) -> None:
        context = RaisesContext(ValueError, match=None)
        with context as exc_info:
            raise ValueError("direct usage")

        assert str(exc_info.value) == "direct usage"

    def test_context_manager_with_match_pattern(self) -> None:
        context = RaisesContext(KeyError, match=r"key")
        with context:
            raise KeyError("missing key")


class TestRaisesAsync:
    @pytest.mark.asyncio
    async def test_works_with_async_code(self) -> None:
        async def async_fail() -> None:
            raise RuntimeError("async error")

        with raises(RuntimeError, match="async"):
            await async_fail()

    @pytest.mark.asyncio
    async def test_captures_exception_from_await(self) -> None:
        async def async_value_error() -> None:
            raise ValueError("awaited error")

        with raises(ValueError) as exc_info:
            await async_value_error()

        assert "awaited" in str(exc_info.value)
