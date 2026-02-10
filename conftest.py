"""Pytest configuration for the test suite."""
import pytest

# Configure pytest-asyncio to use auto mode
pytest_plugins = ['pytest_asyncio']


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test."
    )
