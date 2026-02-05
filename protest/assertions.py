import re
import warnings
from contextlib import contextmanager
from re import Pattern
from types import TracebackType
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Generator

E = TypeVar("E", bound=BaseException)


class ExceptionInfo(Generic[E]):
    def __init__(self) -> None:
        self._value: E | None = None
        self._type: type[E] | None = None
        self._traceback: TracebackType | None = None

    def _populate(
        self,
        exc_type: type[E],
        exc_value: E,
        exc_tb: TracebackType | None,
    ) -> None:
        self._type = exc_type
        self._value = exc_value
        self._traceback = exc_tb

    @property
    def value(self) -> E:
        if self._value is None:
            raise AssertionError("No exception captured yet")
        return self._value

    @property
    def type(self) -> type[E]:
        if self._type is None:
            raise AssertionError("No exception captured yet")
        return self._type

    @property
    def traceback(self) -> TracebackType | None:
        return self._traceback

    def match(self, pattern: str | Pattern[str]) -> re.Match[str]:
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        result = compiled.search(str(self.value))
        if result is None:
            raise AssertionError(
                f"Pattern '{pattern}' not found in '{self.value}'"
            ) from self._value
        return result


class RaisesContext(Generic[E]):
    def __init__(
        self,
        expected_exception: type[E],
        match: str | Pattern[str] | None,
    ) -> None:
        self._expected = expected_exception
        self._match_pattern: Pattern[str] | None = None
        if match is not None:
            self._match_pattern = re.compile(match) if isinstance(match, str) else match
        self._exc_info: ExceptionInfo[E] = ExceptionInfo()

    def __enter__(self) -> ExceptionInfo[E]:
        return self._exc_info

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self._expected.__name__}")

        if not issubclass(exc_type, self._expected):
            return False

        self._exc_info._populate(exc_type, exc_val, exc_tb)  # type: ignore[arg-type]

        if self._match_pattern is not None:
            result = self._match_pattern.search(str(exc_val))
            if result is None:
                raise AssertionError(
                    f"Pattern '{self._match_pattern.pattern}' not found in '{exc_val}'"
                ) from exc_val

        return True


def raises(
    expected_exception: type[E],
    match: str | Pattern[str] | None = None,
) -> RaisesContext[E]:
    return RaisesContext(expected_exception, match=match)


@contextmanager
def warns(
    expected_warning: type[Warning] | tuple[type[Warning], ...] | None = None,
    match: str | Pattern[str] | None = None,
) -> "Generator[list[warnings.WarningMessage], None, None]":
    """Context manager for capturing and validating warnings.

    Args:
        expected_warning: Warning type(s) expected. If None, captures all warnings.
        match: Optional regex pattern to match against warning messages.

    Yields:
        List of captured warnings (stdlib warnings.WarningMessage objects).

    Raises:
        AssertionError: If expected warning not raised or pattern not matched.

    Examples:
        with warns(DeprecationWarning):
            warnings.warn("deprecated", DeprecationWarning)

        with warns(UserWarning, match=r"value.*\\d+"):
            warnings.warn("value is 42", UserWarning)

        with warns() as record:
            warnings.warn("hello", UserWarning)
        assert record[0].category is UserWarning
    """
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        yield record

        if expected_warning is None:
            return

        matching = [w for w in record if issubclass(w.category, expected_warning)]

        if not matching:
            if isinstance(expected_warning, tuple):
                names = ", ".join(e.__name__ for e in expected_warning)
            else:
                names = expected_warning.__name__
            raise AssertionError(f"DID NOT WARN with {names}")

        if match is not None:
            pattern = re.compile(match) if isinstance(match, str) else match
            if not any(pattern.search(str(w.message)) for w in matching):
                messages = [str(w.message) for w in matching]
                raise AssertionError(
                    f"Pattern '{pattern.pattern}' not found in: {messages}"
                )
