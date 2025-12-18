import pytest

from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite
from protest.entities import SessionResult, TestResult
from protest.events.types import Event
from protest.plugin import PluginBase


class TestPluginWiring:
    """session.register_plugin() should auto-wire handlers based on method names."""

    @pytest.mark.asyncio
    async def test_use_wires_on_test_pass_handler(self) -> None:
        """on_test_pass method is wired to TEST_PASS event."""
        session = ProTestSession()
        received: list[TestResult] = []

        class TestPlugin(PluginBase):
            def on_test_pass(self, result: TestResult) -> None:
                received.append(result)

        session.register_plugin(TestPlugin())

        test_result = TestResult(name="my_test", duration=0.1)
        await session.events.emit(Event.TEST_PASS, test_result)

        assert len(received) == 1
        assert received[0].name == "my_test"

    @pytest.mark.asyncio
    async def test_use_wires_multiple_handlers(self) -> None:
        """Multiple on_* methods are all wired."""
        session = ProTestSession()
        events_received: list[str] = []

        class MultiPlugin(PluginBase):
            def on_session_start(self) -> None:
                events_received.append("session_start")

            def on_test_pass(self, result: TestResult) -> None:
                events_received.append("test_pass")

            def on_session_complete(self, result: SessionResult) -> None:
                events_received.append("session_complete")

        session.register_plugin(MultiPlugin())

        await session.events.emit(Event.SESSION_START)
        await session.events.emit(Event.TEST_PASS, TestResult(name="t"))
        await session.events.emit(
            Event.SESSION_COMPLETE, SessionResult(passed=1, failed=0)
        )

        assert events_received == ["session_start", "test_pass", "session_complete"]

    @pytest.mark.asyncio
    async def test_use_ignores_non_matching_methods(self) -> None:
        """Methods not matching on_* pattern are ignored."""
        session = ProTestSession()

        class PluginWithOtherMethods(PluginBase):
            def __init__(self) -> None:
                self.helper_called = False

            def helper_method(self) -> None:
                self.helper_called = True

            def on_test_pass(self, result: TestResult) -> None:
                pass

        plugin = PluginWithOtherMethods()
        session.register_plugin(plugin)

        assert not plugin.helper_called

    @pytest.mark.asyncio
    async def test_use_calls_setup_if_present(self) -> None:
        """setup(session) is called if the plugin has it."""
        session = ProTestSession()

        class PluginWithSetup(PluginBase):
            def __init__(self) -> None:
                self.setup_called = False
                self.received_session: ProTestSession | None = None

            def setup(self, session: ProTestSession) -> None:
                self.setup_called = True
                self.received_session = session

        plugin = PluginWithSetup()
        session.register_plugin(plugin)

        assert plugin.setup_called
        assert plugin.received_session is session

    @pytest.mark.asyncio
    async def test_use_works_without_setup(self) -> None:
        """Plugins without setup() still work."""
        session = ProTestSession()
        received: list[str] = []

        class PluginWithoutSetup(PluginBase):
            def on_session_start(self) -> None:
                received.append("started")

        session.register_plugin(PluginWithoutSetup())
        await session.events.emit(Event.SESSION_START)

        assert received == ["started"]

    @pytest.mark.asyncio
    async def test_use_with_async_handler(self) -> None:
        """Async handlers are wired correctly."""
        session = ProTestSession()
        received: list[str] = []

        class AsyncPlugin:
            async def on_test_pass(self, result: TestResult) -> None:
                received.append(result.name)

        session.register_plugin(AsyncPlugin())  # type: ignore[arg-type]
        await session.events.emit(Event.TEST_PASS, TestResult(name="async_test"))
        await session.events.wait_pending()

        assert received == ["async_test"]


class TestSessionConcurrency:
    """ProTestSession concurrency configuration."""

    def test_default_concurrency_is_one(self) -> None:
        """Default concurrency is 1 (sequential)."""
        session = ProTestSession()
        assert session.concurrency == 1

    def test_concurrency_can_be_set_in_constructor(self) -> None:
        """Concurrency can be set via constructor."""
        session = ProTestSession(concurrency=4)
        assert session.concurrency == 4

    def test_concurrency_setter_enforces_minimum(self) -> None:
        """Concurrency setter enforces minimum of 1."""
        session = ProTestSession()
        session.concurrency = 0
        assert session.concurrency == 1

        session.concurrency = -5
        assert session.concurrency == 1


class TestSuiteMaxConcurrency:
    """ProTestSuite max_concurrency configuration."""

    def test_default_suite_max_concurrency_is_none(self) -> None:
        """Default suite max_concurrency is None (no cap)."""

        suite = ProTestSuite("test_suite")
        assert suite.max_concurrency is None

    def test_suite_max_concurrency_can_be_set_in_constructor(self) -> None:
        """Suite max_concurrency can be set via constructor."""

        suite = ProTestSuite("test_suite", max_concurrency=2)
        assert suite.max_concurrency == 2

    def test_suite_max_concurrency_one_means_sequential(self) -> None:
        """Suite with max_concurrency=1 forces sequential execution."""

        suite = ProTestSuite("sequential_suite", max_concurrency=1)
        assert suite.max_concurrency == 1

    def test_multiple_suites_different_max_concurrency(self) -> None:
        """Different suites can have different max_concurrency settings."""

        fast_suite = ProTestSuite("fast_tests", max_concurrency=10)
        slow_suite = ProTestSuite("db_tests", max_concurrency=1)
        default_suite = ProTestSuite("normal_tests")

        assert fast_suite.max_concurrency == 10
        assert slow_suite.max_concurrency == 1
        assert default_suite.max_concurrency is None
