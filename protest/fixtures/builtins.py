import tempfile
from collections.abc import Generator
from pathlib import Path

from protest.di.decorators import fixture
from protest.entities import LogCapture
from protest.execution.capture import get_current_log_records
from protest.fixtures.mocker import Mocker


@fixture()
def tmp_path() -> Generator[Path, None, None]:
    """Provide a temporary directory that is cleaned up after the test.

    Example:
        @suite.test()
        def test_file_ops(tmp: Annotated[Path, Use(tmp_path)]):
            file = tmp / "test.txt"
            file.write_text("hello")
            assert file.read_text() == "hello"
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


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
