from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession


class ProTestSuite:
    """Groups related tests with optional concurrency override.

    Suites provide SUITE-scoped fixture context. Fixtures with Scope.SUITE
    are created once per suite and torn down when the suite completes.

    Args:
        name: Unique identifier for this suite.
        concurrency: Override session's default concurrency for this suite's tests.
    """

    def __init__(self, name: str, concurrency: int | None = None) -> None:
        self._name = name
        self._session: ProTestSession | None = None
        self._tests: list[Callable[..., Any]] = []
        self._concurrency = concurrency

    @property
    def name(self) -> str:
        return self._name

    @property
    def concurrency(self) -> int | None:
        return self._concurrency

    @property
    def tests(self) -> list[Callable[..., Any]]:
        return self._tests

    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def _attach_to_session(self, session: ProTestSession) -> None:
        self._session = session
