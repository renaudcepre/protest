from collections.abc import Generator

from protest.di.decorators import fixture
from protest.entities import LogCapture
from protest.execution.capture import get_current_log_records
from protest.fixtures.mocker import Mocker


@fixture()
def caplog() -> LogCapture:
    """Capture log records during a test."""
    records = get_current_log_records()
    return LogCapture(records)


@fixture()
def mocker() -> Generator[Mocker, None, None]:
    """Provide a mocker for patching and mocking during tests."""
    mock_manager = Mocker()
    yield mock_manager
    mock_manager.stopall()
