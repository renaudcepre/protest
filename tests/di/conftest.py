"""Pytest fixtures for DI tests."""

import pytest

from tests.di.utils import FixtureCounters


@pytest.fixture
def counters() -> FixtureCounters:
    """Fixture providing isolated counters for tracking fixture calls."""
    return FixtureCounters()
