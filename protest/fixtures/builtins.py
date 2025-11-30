from collections.abc import Generator

from protest.core.scope import Scope
from protest.di.decorators import fixture
from protest.execution.capture import LogCaptureContext
from protest.execution.log_capture import LogCapture


@fixture(scope=Scope.FUNCTION)
def caplog() -> Generator[LogCapture, None, None]:
    with LogCaptureContext() as records:
        yield LogCapture(records)
