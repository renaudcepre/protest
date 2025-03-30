import asyncio
import contextlib
import inspect
import logging
from collections.abc import AsyncGenerator, Callable, Generator, Sequence
from typing import Any, TypeVar, cast

from src.entities import CachedFixture, FixtureInfo, Scope
from src.use import Use

logger = logging.getLogger(__name__)


T = TypeVar("T")


def _extract_dependencies(func: Callable[..., Any]) -> dict[str, Use]:
    """Extract dependencies declared via Use() in parameters."""
    logger.info(f"Extracting dependencies for function: {func.__name__}")
    sig = inspect.signature(func)
    deps: dict[str, Use] = {}

    for param_name, param in sig.parameters.items():
        logger.debug(f"Checking parameter: {param_name} with annotation {param.annotation}")

        # Check for default values
        if param.default != inspect.Parameter.empty and isinstance(param.default, Use):
            deps[param_name] = param.default
            logger.debug(f"  Found default Use dependency: {param.default}")

        # Check for Annotated type hints
        if hasattr(param.annotation, "__metadata__"):
            logger.debug(f"  Parameter has metadata: {param.annotation.__metadata__}")
            for metadata in param.annotation.__metadata__:
                if isinstance(metadata, Use):
                    deps[param_name] = metadata
                    logger.debug(f"  Found Annotated Use dependency: {metadata}")
                    break

    if not deps:
        logger.warning("No dependencies found")
    else:
        logger.info(f"Extracted dependencies: {deps}")
    return deps


class ProTestSession:
    """Main container for fixtures orchestration."""

    def __init__(self) -> None:
        logger.info("Initializing test session")
        self.fixtures: dict[str, FixtureInfo] = {}
        self._fixture_cache: dict[str, CachedFixture] = {}
        logger.debug(f"Session initialized: fixtures={self.fixtures}, cache={self._fixture_cache}")

    def fixture(self, scope: Scope = Scope.FUNCTION) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator to register a fixture."""
        logger.info(f"Registering fixture with scope: {scope}")

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            logger.debug(f"Decorating function: {func.__name__}")
            dependencies = _extract_dependencies(func)
            self.fixtures[func.__name__] = FixtureInfo(func=func, scope=scope, dependencies=dependencies)
            logger.info(f"Registered fixture: {func.__name__} with scope {scope} and {len(dependencies)} dependencies")
            return func

        return decorator

    async def _resolve_fixture(self, use_dep: Use) -> Any:
        """Resolves a fixture from a Use dependency."""
        fixture_name = use_dep.name
        logger.debug(f"Resolving fixture: {fixture_name}")

        if not fixture_name:
            logger.error(f"Invalid fixture provided to Use(): {use_dep.dependency}")
            raise ValueError(f"Invalid fixture provided to Use(): {use_dep.dependency}")

        # Check if fixture exists
        if fixture_name not in self.fixtures:
            logger.error(f"Fixture '{fixture_name}' not found")
            raise ValueError(f"Fixture '{fixture_name}' not found")

        fixture_info = self.fixtures[fixture_name]
        logger.debug(f"Found fixture info: {fixture_info}")

        # Check if fixture is already in cache
        if fixture_name in self._fixture_cache:
            logger.debug(f"Using cached fixture: {fixture_name}")
            return self._fixture_cache[fixture_name].value

        # Resolve dependencies of this fixture
        logger.debug(f"Resolving dependencies for fixture: {fixture_name}")
        kwargs: dict[str, Any] = {}
        for param_name, dep in fixture_info.dependencies.items():
            logger.debug(f"Resolving dependency {param_name} for fixture {fixture_name}")
            kwargs[param_name] = await self._resolve_fixture(dep)
            logger.debug(f"Resolved dependency {param_name} = {kwargs[param_name]}")

        # Initialize the fixture
        func = fixture_info.func
        is_async = asyncio.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)
        is_generator = inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)
        logger.debug(f"Initializing fixture {fixture_name}: is_async={is_async}, is_generator={is_generator}")

        # Execution adapted to fixture type
        cleanup: Generator[Any, None] | AsyncGenerator[Any, None] | None = None

        if is_async:
            if is_generator:
                # Async fixture with yield (setup/teardown)
                logger.debug(f"Executing async generator fixture: {fixture_name}")
                async_gen = cast(AsyncGenerator[Any, None], func(**kwargs).__aiter__())
                value = await async_gen.__anext__()
                cleanup = async_gen
                logger.debug(f"Async generator fixture {fixture_name} yielded: {value}")
            else:
                # Simple async fixture
                logger.debug(f"Executing async fixture: {fixture_name}")
                value = await func(**kwargs)
                logger.debug(f"Async fixture {fixture_name} returned: {value}")
        elif is_generator:
            # Sync fixture with yield (setup/teardown)
            logger.debug(f"Executing sync generator fixture: {fixture_name}")
            sync_gen = cast(Generator[Any, None, None], func(**kwargs))
            value = next(sync_gen)
            # Cast to fix type error
            cleanup = sync_gen
            logger.debug(f"Sync generator fixture {fixture_name} yielded: {value}")
        else:
            # Simple sync fixture
            logger.debug(f"Executing sync fixture: {fixture_name}")
            value = func(**kwargs)
            logger.debug(f"Sync fixture {fixture_name} returned: {value}")

        # Cache the fixture
        logger.debug(f"Caching fixture {fixture_name}")
        self._fixture_cache[fixture_name] = CachedFixture(
            value=value, cleanup=cleanup, is_async=is_async, is_generator=is_generator, scope=fixture_info.scope
        )

        return value

    async def _cleanup_fixture(self, fixture_name: str) -> None:
        """Cleans up a fixture at the end of its lifecycle."""
        logger.debug(f"Cleaning up fixture: {fixture_name}")
        if fixture_name not in self._fixture_cache:
            logger.debug(f"Fixture {fixture_name} not in cache, nothing to clean up")
            return

        cached_fixture = self._fixture_cache[fixture_name]
        cleanup = cached_fixture.cleanup
        logger.debug(f"Fixture info for cleanup: {cached_fixture}")

        if cleanup is not None:
            logger.debug(f"Running cleanup for fixture: {fixture_name}")
            try:
                if cached_fixture.is_async:
                    logger.debug(f"Running async cleanup for fixture: {fixture_name}")
                    async_cleanup = cast(AsyncGenerator[Any, None], cleanup)
                    with contextlib.suppress(StopAsyncIteration):
                        await async_cleanup.__anext__()
                else:
                    logger.debug(f"Running sync cleanup for fixture: {fixture_name}")
                    sync_cleanup = cast(Generator[Any, None, None], cleanup)
                    with contextlib.suppress(StopIteration):
                        next(sync_cleanup)
                logger.debug(f"Cleanup completed for fixture: {fixture_name}")
            except Exception as e:
                logger.error(f"Error during cleanup of fixture {fixture_name}: {e}")
                raise
            finally:
                logger.debug(f"Removing fixture {fixture_name} from cache")
                del self._fixture_cache[fixture_name]
        else:
            logger.debug(f"No cleanup needed for fixture: {fixture_name}")

    async def cleanup_scope(self, scope: Scope) -> None:
        """Cleans up all fixtures of a specific scope.

        This method is automatically called at the end of
        a test, suite, or session execution.
        """
        logger.debug(f"Cleaning up all fixtures with scope {scope}")
        # Get all fixtures of the specified scope
        fixtures_to_clean = [name for name, fixture in self._fixture_cache.items() if fixture.scope == scope]

        # Clean up each fixture
        for fixture_name in fixtures_to_clean:
            await self._cleanup_fixture(fixture_name)

        logger.debug(f"Completed cleanup of {len(fixtures_to_clean)} fixtures with scope {scope}")

    async def run_test(self, test_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Executes a test with automatic fixture lifecycle management."""
        try:
            # Execute the test
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func(*args, **kwargs)
            else:
                result = test_func(*args, **kwargs)
            return result
        finally:
            # Clean up fixtures with FUNCTION scope
            await self.cleanup_scope(Scope.FUNCTION)

    async def run_suite(self, suite_tests: Sequence[Callable[..., Any]]) -> list[Any]:
        """Executes a test suite with automatic fixture lifecycle management."""
        results: list[Any] = []
        try:
            # Execute all tests
            for test_func in suite_tests:
                result = await self.run_test(test_func)
                results.append(result)
            return results
        finally:
            # Clean up fixtures with SUITE scope
            await self.cleanup_scope(Scope.SUITE)

    async def run_session(
        self, suites_or_tests: Sequence[Sequence[Callable[..., Any]] | Callable[..., Any]]
    ) -> list[Any]:
        """Executes a complete test session with automatic lifecycle management."""
        results: list[Any] = []
        try:
            for item in suites_or_tests:
                if isinstance(item, list):  # It's a suite
                    result = await self.run_suite(cast(Sequence[Callable[..., Any]], item))
                else:  # It's an individual test
                    result = await self.run_test(cast(Callable[..., Any], item))
                results.append(result)
            return results
        finally:
            # Clean up fixtures with SESSION scope
            await self.cleanup_scope(Scope.SESSION)
