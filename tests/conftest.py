"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the async backend."""
    return "asyncio"


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run live integration tests that use real CLI tools (requires API credits)",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "live: mark test as requiring live CLI tools (deselect with '-m \"not live\"')",
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --run-live is specified."""
    if config.getoption("--run-live"):
        return

    skip_live = pytest.mark.skip(reason="need --run-live option to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
