from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import TracebackType

    from protest.compat import Self
    from protest.core.suite import ProTestSuite
    from protest.entities import FixtureCallable
    from protest.evals.types import JudgeInfo, ModelInfo
    from protest.plugin import PluginBase, PluginContext

from protest.cache.plugin import CachePlugin
from protest.cache.storage import CacheStorage
from protest.di.container import FixtureContainer
from protest.di.decorators import get_fixture_marker, unwrap_fixture
from protest.entities import (
    FixtureRegistration,
    FixtureScope,
    Retry,
    Skip,
    TestRegistration,
    Xfail,
    normalize_retry,
    normalize_skip,
    normalize_xfail,
)
from protest.events.bus import EventBus
from protest.events.types import Event
from protest.exceptions import InvalidMaxConcurrencyError
from protest.execution.capture import set_session_teardown_capture
from protest.filters.keyword import KeywordFilterPlugin
from protest.filters.kind import KindFilterPlugin
from protest.filters.suite import SuiteFilterPlugin
from protest.reporting.ascii import AsciiReporter
from protest.reporting.ctrf import CTRFReporter
from protest.reporting.log_file import LogFilePlugin
from protest.reporting.rich_reporter import RichReporter
from protest.tags.plugin import TagFilterPlugin

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


class ProTestSession:
    """Main test session orchestrator.

    Manages test collection, fixture resolution, and plugin coordination.
    Use as async context manager to ensure proper fixture teardown.

    Fixtures registered with @session.bind() live for the entire session.
    Use @session.autouse() for fixtures that should be resolved at session start.

    Args:
        concurrency: Number of parallel test workers (default: 1).
    """

    def __init__(
        self,
        concurrency: int = 1,
        history: bool = False,
        history_dir: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if concurrency < 1:
            raise InvalidMaxConcurrencyError(concurrency)

        self._events = EventBus()
        self._resolver = FixtureContainer(event_bus=self._events)
        self._suites: list[ProTestSuite] = []
        self._tests: list[TestRegistration] = []
        self._fixtures: list[FixtureRegistration] = []
        self._concurrency = concurrency
        self._autouse_fixtures: list[FixtureCallable] = []
        self._cache_storage = CacheStorage()
        self._plugin_classes: list[type[PluginBase]] = []
        self._plugins_activated: bool = False
        self._exitfirst: bool = False
        self._capture: bool = True
        self._setup_duration: float = 0
        self._teardown_duration: float = 0
        self._history = history
        self._history_dir = history_dir
        self._metadata: dict[str, Any] = dict(metadata) if metadata else {}
        self._eval_model: ModelInfo | None = None  # set by EvalSession
        self._eval_judge: JudgeInfo | None = None  # set by EvalSession

    async def resolve_autouse(self) -> None:
        """Resolve all session autouse fixtures at session start."""
        for fixture_func in self._autouse_fixtures:
            await self._resolver.resolve(fixture_func)

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @concurrency.setter
    def concurrency(self, value: int) -> None:
        if value < 1:
            raise InvalidMaxConcurrencyError(value)
        self._concurrency = value

    @property
    def exitfirst(self) -> bool:
        return self._exitfirst

    @exitfirst.setter
    def exitfirst(self, value: bool) -> None:
        self._exitfirst = value

    @property
    def capture(self) -> bool:
        return self._capture

    @capture.setter
    def capture(self, value: bool) -> None:
        self._capture = value

    @property
    def history(self) -> bool:
        return self._history

    @property
    def history_dir(self) -> Path | None:
        return self._history_dir

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata

    @property
    def setup_duration(self) -> float:
        """Duration of session setup (available after resolve_autouse)."""
        return self._setup_duration

    def set_setup_duration(self, duration: float) -> None:
        """Set the setup duration. Called by runner after autouse resolution."""
        self._setup_duration = duration

    @property
    def teardown_duration(self) -> float:
        """Duration of session teardown (available after __aexit__)."""
        return self._teardown_duration

    @property
    def resolver(self) -> FixtureContainer:
        return self._resolver

    @property
    def events(self) -> EventBus:
        return self._events

    @property
    def suites(self) -> list[ProTestSuite]:
        return self._suites

    @property
    def tests(self) -> list[TestRegistration]:
        return self._tests

    @property
    def fixtures(self) -> list[FixtureRegistration]:
        return self._fixtures

    @property
    def cache(self) -> CacheStorage:
        """Shared cache storage for inter-plugin data sharing."""
        return self._cache_storage

    def test(
        self,
        tags: list[str] | None = None,
        timeout: float | None = None,
        skip: bool | str | Callable[..., bool] | Skip | None = None,
        skip_reason: str = "Skipped",
        xfail: bool | str | Xfail | None = None,
        retry: int | Retry | None = None,
        is_eval: bool = False,
    ) -> Callable[[FuncT], FuncT]:
        def decorator(func: FuncT) -> FuncT:
            if timeout is not None and timeout < 0:
                raise ValueError(f"timeout must be non-negative, got {timeout}")

            norm_skip = normalize_skip(skip, reason=skip_reason)
            norm_xfail = normalize_xfail(xfail)
            norm_retry = normalize_retry(retry)

            self._tests.append(
                TestRegistration(
                    func=func,
                    tags=set(tags) if tags else set(),
                    skip=norm_skip,
                    xfail=norm_xfail,
                    timeout=timeout,
                    retry=norm_retry,
                    is_eval=is_eval,
                )
            )
            return func

        return decorator

    def eval(
        self,
        evaluators: list[Any] | None = None,
        expected_key: str = "expected",
        tags: list[str] | None = None,
        timeout: float | None = None,
        name: str | None = None,
        model: Any = None,
    ) -> Callable[[FuncT], FuncT]:
        """Register a scored eval test.

        Creates an implicit eval suite named after the function.
        The decorated function's return value is passed to evaluators.
        Use with ForEach/From for parametrization::

            @session.eval(evaluators=[my_scorer], model=ModelInfo(name="qwen"))
            async def my_eval(case: Annotated[dict, From(cases)]) -> str:
                return await run(case["q"])
        """
        from protest.core.suite import ProTestSuite
        from protest.evals.wrapper import make_eval_wrapper

        def decorator(func: FuncT) -> FuncT:
            suite_name = name or func.__name__
            suite_meta: dict[str, Any] = {}
            resolved_model = model or getattr(self, "_eval_model", None)
            if resolved_model:
                suite_meta["model"] = resolved_model.name
                suite_meta["provider"] = getattr(resolved_model, "provider", None)
            suite = ProTestSuite(
                name=suite_name,
                tags=list(tags or []),
                kind="eval",
                metadata=suite_meta,
            )
            wrapper = make_eval_wrapper(
                func,
                evaluators or [],
                expected_key,
            )
            suite.test(tags=tags, timeout=timeout, is_eval=True)(wrapper)
            self.add_suite(suite)
            return func

        return decorator

    def add_suite(self, suite: ProTestSuite) -> None:
        """Add a suite to this session."""
        suite._attach_to_session(self)
        self._suites.append(suite)

    def bind(
        self,
        fn: FixtureCallable,
        autouse: bool = False,
    ) -> None:
        """Bind a fixture to this session (SESSION scope).

        The fixture must be decorated with @fixture() or @factory().
        Scope is determined by this binding - no scope declaration needed
        on the decorator.

        Args:
            fn: Function decorated with @fixture() or @factory().
            autouse: If True, resolve automatically at session start.

        Raises:
            ValueError: If the function is not decorated with @fixture/@factory.

        Example:
            @fixture()
            def database():
                yield connect()

            session = ProTestSession()
            session.bind(database)  # SESSION scope
            session.bind(config, autouse=True)  # SESSION + auto-resolve
        """
        actual_func = unwrap_fixture(fn)
        marker = get_fixture_marker(fn)
        if marker is None:
            raise ValueError(
                f"Function '{actual_func.__name__}' is not decorated with "
                "@fixture() or @factory(). Use the decorator first."
            )

        registration = FixtureRegistration(
            func=actual_func,
            is_factory=marker.is_factory,
            cache=marker.cache,
            managed=marker.managed,
            tags=set(marker.tags),
            autouse=autouse,
            max_concurrency=marker.max_concurrency,
        )
        self._fixtures.append(registration)

    def use(self, plugin_class: type[PluginBase]) -> None:
        """Register a plugin class for CLI discovery.

        The plugin will be instantiated via from_cli() after CLI parsing.
        Ignores duplicates.
        """
        if plugin_class not in self._plugin_classes:
            self._plugin_classes.append(plugin_class)

    @staticmethod
    def default_plugin_classes() -> list[type[PluginBase]]:
        """Return the list of standard plugin classes."""
        return [
            CachePlugin,
            TagFilterPlugin,
            SuiteFilterPlugin,
            KeywordFilterPlugin,
            KindFilterPlugin,
            RichReporter,
            AsciiReporter,
            CTRFReporter,
            LogFilePlugin,
        ]

    def register_default_plugins(self) -> None:
        """Register all standard ProTest plugins for CLI discovery."""
        for plugin_class in self.default_plugin_classes():
            self.use(plugin_class)
        if self._history:
            from protest.history.plugin import HistoryPlugin

            self.register_plugin(HistoryPlugin(history_dir=self._history_dir))

    @property
    def plugin_classes(self) -> list[type[PluginBase]]:
        """Get registered plugin classes."""
        return self._plugin_classes.copy()

    def register_plugin(self, plugin: PluginBase) -> None:
        """Register a plugin instance and wire it to the event bus.

        Use this to register a pre-configured plugin instance. For CLI usage,
        prefer `use(PluginClass)` which enables CLI option discovery.
        """
        plugin.setup(self)

        for event in Event:
            method_name = f"on_{event.value}"
            handler = getattr(plugin, method_name, None)
            if handler and callable(handler):
                self._events.on(event, handler)

    def activate_plugins(self, ctx: PluginContext) -> None:
        """Activate all registered plugin classes with the given context.

        Each plugin's activate() method is called with the context.
        If it returns an instance, that instance is registered.
        If it returns None, the plugin is skipped.

        This method is idempotent: calling it multiple times has no effect.
        """
        if self._plugins_activated:
            return
        self._plugins_activated = True

        for plugin_class in self._plugin_classes:
            instance = plugin_class.activate(ctx)
            if instance is not None:
                self.register_plugin(instance)

        # Auto-wire eval support if any suite has kind="eval"
        if any(s.kind == "eval" for s in self._suites):
            self._wire_eval_support()

    def _wire_eval_support(self) -> None:
        """Wire eval history + results writer plugins (no EvalPlugin)."""
        from protest.evals.history import EvalHistoryPlugin
        from protest.evals.results_writer import EvalResultsWriter

        judge_dict = None
        if self._eval_judge:
            judge_dict = {
                "name": self._eval_judge.name,
                "provider": getattr(self._eval_judge, "provider", None),
                "evaluators": list(getattr(self._eval_judge, "evaluators", ())),
            }

        history = EvalHistoryPlugin(
            history_dir=self._history_dir,
            model=self._eval_model,
            judge=judge_dict,
            metadata=self._metadata,
        )
        self.register_plugin(history)

        writer = EvalResultsWriter(history_dir=self._history_dir)
        self.register_plugin(writer)

    async def __aenter__(self) -> Self:
        self._register_fixtures()
        await self._resolver.__aenter__()
        return self

    def _register_fixtures(self) -> None:
        """Register all fixtures from session and suites into resolver."""
        self._autouse_fixtures.clear()
        for fixture_reg in self._fixtures:
            self._resolver.register(
                fixture_reg.func,
                scope=FixtureScope.SESSION,
                is_factory=fixture_reg.is_factory,
                cache=fixture_reg.cache,
                managed=fixture_reg.managed,
                tags=fixture_reg.tags,
                autouse=fixture_reg.autouse,
                max_concurrency=fixture_reg.max_concurrency,
            )
            if fixture_reg.autouse:
                self._autouse_fixtures.append(fixture_reg.func)
        self._register_suite_fixtures(self._suites)

    def _register_suite_fixtures(self, suites: list[ProTestSuite]) -> None:
        """Recursively register fixtures from suites.

        Each fixture is registered with its owner suite's full_path. This determines:
        - The cache key (fixtures cached per owner suite, not per test suite)
        - Access control (only tests in this suite or child suites can access)
        """
        for suite in suites:
            for fixture_reg in suite.fixtures:
                self._resolver.register(
                    fixture_reg.func,
                    scope=FixtureScope.SUITE,
                    is_factory=fixture_reg.is_factory,
                    cache=fixture_reg.cache,
                    managed=fixture_reg.managed,
                    tags=fixture_reg.tags,
                    autouse=fixture_reg.autouse,
                    suite_path=suite.full_path,
                    max_concurrency=fixture_reg.max_concurrency,
                )
            self._register_suite_fixtures(suite.suites)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        import time

        teardown_start = time.perf_counter()
        set_session_teardown_capture(True)
        try:
            return await self._resolver.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            set_session_teardown_capture(False)
            self._teardown_duration = time.perf_counter() - teardown_start
