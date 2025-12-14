"""Programmatic BDD steps for ProTest.

Provides a lightweight, code-first approach to BDD without Gherkin files.
Steps emit events via callbacks that reporters can listen to.

Example:
    @session.test()
    async def test_checkout(page: Annotated[Page, Use(page)]):
        async with step("Given un panier rempli"):
            await page.click(".add-to-cart")

        async with step("When je valide la commande"):
            await page.click("#checkout")

        async with step("Then je reçois la confirmation"):
            await expect(page.locator(".success")).to_be_visible()
"""

from __future__ import annotations

import contextlib
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from protest.execution.capture import _current_node_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator


@dataclass(frozen=True, slots=True)
class StepInfo:
    """Information about a step event."""

    node_id: str
    name: str
    status: Literal["start", "success", "failure"]
    duration: float | None = None
    error: BaseException | None = None


# Global callback registry for step events
_step_callbacks: list[Callable[[StepInfo], None]] = []


def add_step_callback(callback: Callable[[StepInfo], None]) -> None:
    """Register a callback to be notified when steps start/end."""
    _step_callbacks.append(callback)


def remove_step_callback(callback: Callable[[StepInfo], None]) -> None:
    """Remove a step callback."""
    if callback in _step_callbacks:
        _step_callbacks.remove(callback)


def _emit_step(info: StepInfo) -> None:
    """Emit step event to all registered callbacks."""
    for callback in _step_callbacks:
        with contextlib.suppress(Exception):
            callback(info)


@asynccontextmanager
async def step(name: str) -> AsyncIterator[None]:
    """Async context manager for BDD-style steps.

    Emits step events that reporters can listen to for live display.
    On failure, step info is included in test output for debugging.

    Args:
        name: Step description (e.g., "Given a filled cart")

    Example:
        async with step("Given a user is logged in"):
            await login(user)

        async with step("When they click logout"):
            await page.click("#logout")

        async with step("Then they see the login page"):
            await expect(page).to_have_url("/login")
    """
    node_id = _current_node_id.get() or ""
    start = time.perf_counter()

    _emit_step(StepInfo(node_id=node_id, name=name, status="start"))

    try:
        yield
        duration = time.perf_counter() - start
        _emit_step(
            StepInfo(node_id=node_id, name=name, status="success", duration=duration)
        )
    except BaseException as e:
        duration = time.perf_counter() - start
        _emit_step(
            StepInfo(
                node_id=node_id, name=name, status="failure", duration=duration, error=e
            )
        )
        raise


@contextmanager
def step_sync(name: str) -> Iterator[None]:
    """Sync context manager for BDD-style steps.

    Same as `step()` but for synchronous test functions.

    Args:
        name: Step description (e.g., "Given a filled cart")

    Example:
        with step_sync("Given a database connection"):
            db = connect()

        with step_sync("When I insert a record"):
            db.insert(record)

        with step_sync("Then the record exists"):
            assert db.get(record.id) is not None
    """
    node_id = _current_node_id.get() or ""
    start = time.perf_counter()

    _emit_step(StepInfo(node_id=node_id, name=name, status="start"))

    try:
        yield
        duration = time.perf_counter() - start
        _emit_step(
            StepInfo(node_id=node_id, name=name, status="success", duration=duration)
        )
    except BaseException as e:
        duration = time.perf_counter() - start
        _emit_step(
            StepInfo(
                node_id=node_id, name=name, status="failure", duration=duration, error=e
            )
        )
        raise
