import logging

import pytest

from src.session import ProTestSession

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG, format="[%(levelname)7s] %(name)20s - %(message)s")


# Setup pytest-asyncio
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def session():
    return ProTestSession()
