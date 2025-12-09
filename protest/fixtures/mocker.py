"""Mocker fixture for patching and mocking during tests."""

from __future__ import annotations

import builtins
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

DictType = builtins.dict[Any, Any]

MockType = MagicMock | AsyncMock
AsyncMockType = AsyncMock


class _PatchHelper:
    """Helper class enabling mocker.patch(), mocker.patch.object(), mocker.patch.dict()."""

    def __init__(self, mocker: Mocker) -> None:
        self._mocker = mocker

    def __call__(self, target: str, **kwargs: Any) -> MagicMock:
        """Patch a target specified by a string path (e.g., 'module.function')."""
        patcher = patch(target, **kwargs)
        mock: MagicMock = patcher.start()
        self._mocker._patchers.append(patcher)
        self._mocker._mocks.append(mock)
        self._mocker._mock_to_patcher[id(mock)] = patcher
        return mock

    def object(self, target: Any, attribute: str, **kwargs: Any) -> MagicMock:
        """Patch an attribute on an object instance."""
        patcher = patch.object(target, attribute, **kwargs)
        mock: MagicMock = patcher.start()
        self._mocker._patchers.append(patcher)
        self._mocker._mocks.append(mock)
        self._mocker._mock_to_patcher[id(mock)] = patcher
        return mock

    def dict(
        self,
        in_dict: DictType,
        values: DictType | None = None,
        clear: bool = False,
        **kwargs: Any,
    ) -> DictType:
        """Patch a dictionary (e.g., os.environ). Use clear=True to replace entirely."""
        patcher = patch.dict(in_dict, values or {}, clear=clear, **kwargs)
        patcher.start()
        self._mocker._patchers.append(patcher)
        return in_dict


class Mocker:
    """Mocking helper with automatic cleanup. Injected via the `mocker` fixture."""

    def __init__(self) -> None:
        self._patchers: list[Any] = []
        self._mocks: list[MagicMock | AsyncMock] = []
        self._mock_to_patcher: dict[int, Any] = {}
        self.patch = _PatchHelper(self)

    def spy(self, obj: object, method: str | None = None) -> MagicMock:
        """Spy on a method: calls the real implementation but tracks invocations.

        Usage:
            spy(obj, "method_name")  # Classic style
            spy(obj.method_name)     # Modern style (bound method)
        """
        if method is None:
            if inspect.ismethod(obj):
                bound_method = obj
                obj = bound_method.__self__
                method = bound_method.__name__
            else:
                raise TypeError(
                    "spy() requires either (obj, 'method_name') or a bound method. "
                    "For module functions, use: patch(func, wraps=func)"
                )

        original = getattr(obj, method)
        spy_mock = MagicMock(wraps=original)
        spy_mock.spy_return = None

        def tracking_side_effect(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            spy_mock.spy_return = result
            return result

        spy_mock.side_effect = tracking_side_effect

        patcher = patch.object(obj, method, spy_mock)
        patcher.start()
        self._patchers.append(patcher)
        self._mocks.append(spy_mock)
        self._mock_to_patcher[id(spy_mock)] = patcher
        return spy_mock

    def stub(self, name: str | None = None) -> MagicMock:
        """Create a stub callable, useful for testing callbacks."""
        mock = MagicMock(name=name)
        self._mocks.append(mock)
        return mock

    def async_stub(self, name: str | None = None) -> AsyncMock:
        """Create an async stub callable, useful for testing async callbacks."""
        mock = AsyncMock(name=name)
        self._mocks.append(mock)
        return mock

    def create_autospec(
        self, spec: Any, spec_set: bool = False, instance: bool = False, **kwargs: Any
    ) -> MagicMock:
        """Create a mock that respects the signature of the spec class/function."""
        mock: MagicMock = create_autospec(
            spec, spec_set=spec_set, instance=instance, **kwargs
        )
        self._mocks.append(mock)
        return mock

    def stop(self, mock: MagicMock | AsyncMock) -> None:
        """Stop a specific patch by passing the mock it returned."""
        mock_id = id(mock)
        patcher = self._mock_to_patcher.get(mock_id)
        if patcher is not None:
            patcher.stop()
            self._patchers.remove(patcher)
            if mock in self._mocks:
                self._mocks.remove(mock)
            del self._mock_to_patcher[mock_id]

    def stopall(self) -> None:
        """Stop all patches (called automatically at test teardown)."""
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._patchers.clear()
        self._mocks.clear()
        self._mock_to_patcher.clear()

    def resetall(
        self, *, return_value: bool = False, side_effect: bool = False
    ) -> None:
        """Reset all mocks (clear call_count, call_args, etc.)."""
        for mock in self._mocks:
            mock.reset_mock(return_value=return_value, side_effect=side_effect)
