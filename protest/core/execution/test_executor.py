"""Single test execution logic."""

from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import AsyncExitStack, asynccontextmanager
from inspect import signature
from typing import TYPE_CHECKING, Any, get_type_hints

from protest.core.collector import get_transitive_fixtures
from protest.core.outcome import OutcomeBuilder, TestExecutionResult
from protest.di.container import FixtureContainer
from protest.entities import (
    FixtureCallable,
    TestItem,
    TestOutcome,
    TestRetryInfo,
    TestStartInfo,
    TestTeardownInfo,
)
from protest.events.types import Event
from protest.exceptions import FixtureError
from protest.execution.async_bridge import ensure_async
from protest.execution.capture import (
    CaptureCurrentTest,
    reset_current_node_id,
    set_current_node_id,
)
from protest.execution.context import TestExecutionContext

if TYPE_CHECKING:
    import io
    from collections.abc import AsyncIterator

    from protest.core.session import ProTestSession
    from protest.entities.skip import Skip
    from protest.events.bus import EventBus


@asynccontextmanager
async def _semaphore_context(sem: asyncio.Semaphore) -> AsyncIterator[None]:
    """Wrap a semaphore for use with AsyncExitStack.enter_async_context()."""
    async with sem:
        yield


class TestExecutor:
    """Executes a single test with capture and context."""

    def __init__(
        self, session: ProTestSession, outcome_builder: OutcomeBuilder
    ) -> None:
        self._session = session
        self._outcome_builder = outcome_builder

    @property
    def _events(self) -> EventBus:
        return self._session.events

    async def execute(
        self,
        item: TestItem,
        start_info: TestStartInfo,
        fixture_semaphores: dict[FixtureCallable, asyncio.Semaphore] | None = None,
    ) -> TestOutcome:
        """Execute a single test with capture and context."""
        await self._events.emit(Event.TEST_ACQUIRED, start_info)
        node_id_token = set_current_node_id(start_info.node_id)
        try:
            async with (
                self._acquire_fixture_semaphores(item, fixture_semaphores),
                TestExecutionContext(self._session.resolver, item.suite_path) as ctx,
            ):
                with CaptureCurrentTest() as buffer:
                    outcome = await self._run_test(item, ctx, buffer, start_info)
                # Emit result AFTER capture (so reporter output goes to stdout)
                await self._events.emit(outcome.event, outcome.result)
                # Then teardown fixtures (back inside capture for fixture prints)
                with CaptureCurrentTest():
                    teardown_info = TestTeardownInfo(
                        name=start_info.name,
                        node_id=start_info.node_id,
                        outcome=outcome.event,
                    )
                    await self._events.emit(Event.TEST_TEARDOWN_START, teardown_info)
                    await ctx.close()
            return outcome  # pyright: ignore[reportPossiblyUnboundVariable]
        finally:
            reset_current_node_id(node_id_token)

    async def _run_test(  # noqa: PLR0912 - complex test execution flow, refactoring would reduce readability
        self,
        item: TestItem,
        ctx: TestExecutionContext,
        buffer: io.StringIO,
        start_info: TestStartInfo,
    ) -> TestOutcome:
        """Run a single test and return outcome (event emitted by caller)."""
        test_name = start_info.name
        node_id = start_info.node_id

        # Static skip - check before fixture resolution
        if item.skip and item.skip.is_static:
            return self._outcome_builder.build(
                TestExecutionResult(
                    test_name=test_name,
                    node_id=node_id,
                    suite_path=item.suite_path,
                    skip_reason=item.skip.reason,
                )
            )

        start = time.perf_counter()

        try:
            kwargs = await self._resolve_test_kwargs(item, ctx)
        except Exception as exc:
            return self._outcome_builder.build(
                TestExecutionResult(
                    test_name=test_name,
                    node_id=node_id,
                    suite_path=item.suite_path,
                    duration=time.perf_counter() - start,
                    output=buffer.getvalue(),
                    error=exc,
                    is_fixture_error=True,
                )
            )

        # Conditional skip (callable) - evaluated AFTER fixture resolution
        if item.skip and item.skip.is_conditional:
            try:
                should_skip = await self._evaluate_skip_condition(item.skip, kwargs)
            except Exception as exc:
                return self._outcome_builder.build(
                    TestExecutionResult(
                        test_name=test_name,
                        node_id=node_id,
                        suite_path=item.suite_path,
                        duration=time.perf_counter() - start,
                        output=buffer.getvalue(),
                        error=exc,
                        is_fixture_error=True,
                    )
                )
            if should_skip:
                return self._outcome_builder.build(
                    TestExecutionResult(
                        test_name=test_name,
                        node_id=node_id,
                        suite_path=item.suite_path,
                        duration=time.perf_counter() - start,
                        skip_reason=item.skip.reason,
                    )
                )

        await self._events.emit(Event.TEST_SETUP_DONE, start_info)

        max_attempts = 1 + (item.retry.times if item.retry else 0)
        previous_errors: list[Exception] = []
        error: Exception | None = None
        is_fixture_error = False
        attempt = 1  # Initialized here; always overwritten by loop

        for attempt in range(1, max_attempts + 1):
            error = None
            is_fixture_error = False

            try:
                if item.timeout is not None:
                    try:
                        await asyncio.wait_for(
                            ensure_async(item.func, **kwargs),
                            timeout=item.timeout,
                        )
                    except asyncio.TimeoutError:
                        # Only wrap timeout from wait_for, not from test code
                        raise asyncio.TimeoutError(
                            f"Test exceeded timeout of {item.timeout}s"
                        ) from None
                else:
                    await ensure_async(item.func, **kwargs)
            except FixtureError as exc:
                error = exc.original
                is_fixture_error = True
            except Exception as exc:
                error = exc

            retry_on = item.retry.on if item.retry else None
            retry_delay = item.retry.delay if item.retry else 0
            should_retry = (
                error is not None
                and not is_fixture_error
                and attempt < max_attempts
                and self._should_retry(error, retry_on)
            )
            if should_retry and error is not None:
                # Clear traceback to save memory - type and message are preserved
                error.__traceback__ = None
                previous_errors.append(error)
                retry_info = TestRetryInfo(
                    name=test_name,
                    node_id=node_id,
                    suite_path=item.suite_path,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=error,
                    delay=retry_delay,
                )
                await self._events.emit(Event.TEST_RETRY, retry_info)
                if retry_delay > 0:
                    await asyncio.sleep(retry_delay)
                continue
            break

        return self._outcome_builder.build(
            TestExecutionResult(
                test_name=test_name,
                node_id=node_id,
                suite_path=item.suite_path,
                duration=time.perf_counter() - start,
                output=buffer.getvalue(),
                error=error,
                is_fixture_error=is_fixture_error,
                xfail_reason=item.xfail.reason
                if item.xfail and not is_fixture_error
                else None,
                timeout=item.timeout,
                attempt=attempt,
                max_attempts=max_attempts,
                previous_errors=tuple(previous_errors),
            )
        )

    async def _resolve_test_kwargs(
        self,
        item: TestItem,
        ctx: TestExecutionContext,
    ) -> dict[str, Any]:
        """Resolve fixture dependencies for a test."""
        func_signature = signature(item.func)
        kwargs: dict[str, Any] = dict(item.case_kwargs)

        try:
            type_hints = get_type_hints(item.func, include_extras=True)
        except Exception:
            type_hints = {}

        for param_name, param in func_signature.parameters.items():
            if param_name in kwargs:
                continue
            resolved_annotation = type_hints.get(param_name, param.annotation)
            if dependency := FixtureContainer._extract_dependency_from_annotation(
                resolved_annotation
            ):
                kwargs[param_name] = await ctx.resolve(dependency)

        return kwargs

    def _should_retry(
        self,
        error: Exception,
        retry_on: type[Exception] | tuple[type[Exception], ...] | None,
    ) -> bool:
        return retry_on is None or isinstance(error, retry_on)

    async def _evaluate_skip_condition(
        self,
        skip: Skip,
        resolved_kwargs: dict[str, Any],
    ) -> bool:
        """Evaluate a conditional skip with resolved fixture values.

        Args:
            skip: The Skip configuration with callable condition
            resolved_kwargs: Resolved fixture values for the test

        Returns:
            True if test should be skipped, False otherwise

        Raises:
            FixtureError: If the callable raises an exception
        """
        condition = skip.condition
        assert callable(condition), "Expected callable for conditional skip"

        # Introspect callable to pass only required kwargs
        try:
            cond_sig = signature(condition)
            cond_params = set(cond_sig.parameters.keys())
        except (ValueError, TypeError):
            # Fallback: callable with no introspectable signature
            cond_params = set()

        # Filter kwargs to only those the condition accepts
        filtered_kwargs = {
            k: v for k, v in resolved_kwargs.items() if k in cond_params
        }

        try:
            result = condition(**filtered_kwargs)
            # Support async skip conditions
            if inspect.isawaitable(result):
                result = await result  # pyright: ignore[reportGeneralTypeIssues] - runtime type guard
            return bool(result)
        except Exception as exc:
            # Wrap exception for consistent error message
            raise FixtureError(
                fixture_name="skip",
                original=exc,
            ) from exc

    @asynccontextmanager
    async def _acquire_fixture_semaphores(
        self,
        item: TestItem,
        fixture_semaphores: dict[FixtureCallable, asyncio.Semaphore] | None,
    ) -> AsyncIterator[None]:
        """Acquire fixture semaphores for rate-limited fixtures.

        Semaphores are acquired in a deterministic order (sorted by id)
        to prevent deadlocks when multiple tests compete for the same fixtures.
        """
        if not fixture_semaphores:
            yield
            return

        # Get fixtures used by this test (including transitive dependencies)
        test_fixtures = get_transitive_fixtures(item.func)

        # Find which fixtures have semaphores (max_concurrency)
        sems_to_acquire = [
            (func, fixture_semaphores[func])
            for func in test_fixtures
            if func in fixture_semaphores
        ]

        if not sems_to_acquire:
            yield
            return

        # Sort by id(func) to prevent deadlocks
        sems_sorted = sorted(sems_to_acquire, key=lambda x: id(x[0]))

        async with AsyncExitStack() as stack:
            for _, sem in sems_sorted:
                await stack.enter_async_context(_semaphore_context(sem))
            yield
