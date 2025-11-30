import logging
from typing import Annotated

from protest import ProTestSession, Use, caplog
from protest.core.runner import TestRunner
from protest.events.data import SessionResult, TestResult
from protest.execution.log_capture import LogCapture
from protest.plugin import PluginBase


class TestCaplogFixture:
    def test_caplog_captures_test_logs(self) -> None:
        session = ProTestSession()
        results: list[TestResult] = []

        class Collector(PluginBase):
            def on_test_pass(self, result: TestResult) -> None:
                results.append(result)

        session.use(Collector())

        @session.test()
        def test_with_logs(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("test message")
            assert len(logs.records) == 1
            assert logs.records[0].getMessage() == "test message"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        assert len(results) == 1

    def test_caplog_captures_different_levels(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_levels(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.debug("debug")
            logging.info("info")
            logging.warning("warning")
            logging.error("error")

            assert len(logs.records) == 4
            assert logs.records[0].levelname == "DEBUG"
            assert logs.records[1].levelname == "INFO"
            assert logs.records[2].levelname == "WARNING"
            assert logs.records[3].levelname == "ERROR"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_caplog_at_level_filtering(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_filter(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.debug("debug")
            logging.info("info")
            logging.warning("warning")

            warnings = logs.at_level("WARNING")
            assert len(warnings) == 1
            assert warnings[0].getMessage() == "warning"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_caplog_text_property(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_text(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.warning("hello world")

            assert "WARNING" in logs.text
            assert "hello world" in logs.text

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_caplog_clear(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_clear(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("first")
            assert len(logs.records) == 1

            logs.clear()
            assert len(logs.records) == 0

            logging.info("second")
            assert len(logs.records) == 1
            assert logs.records[0].getMessage() == "second"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_caplog_isolation_between_tests(self) -> None:
        session = ProTestSession()
        captured_counts: list[int] = []

        @session.test()
        def test_first(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("from first test")
            captured_counts.append(len(logs.records))

        @session.test()
        def test_second(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("from second test")
            captured_counts.append(len(logs.records))

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        assert captured_counts == [1, 1]

    def test_caplog_with_named_logger(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_named_logger(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logger = logging.getLogger("my.custom.logger")
            logger.warning("custom logger message")

            assert len(logs.records) == 1
            assert logs.records[0].name == "my.custom.logger"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_caplog_parallel_isolation(self) -> None:
        session = ProTestSession(concurrency=3)
        session_results: list[SessionResult] = []

        class Collector(PluginBase):
            def on_session_end(self, result: SessionResult) -> None:
                session_results.append(result)

        session.use(Collector())

        @session.test()
        def test_a(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("test_a message")
            assert len(logs.records) == 1
            assert "test_a" in logs.records[0].getMessage()

        @session.test()
        def test_b(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("test_b message")
            assert len(logs.records) == 1
            assert "test_b" in logs.records[0].getMessage()

        @session.test()
        def test_c(logs: Annotated[LogCapture, Use(caplog)]) -> None:
            logging.info("test_c message")
            assert len(logs.records) == 1
            assert "test_c" in logs.records[0].getMessage()

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        assert len(session_results) == 1
        assert session_results[0].passed == 3
