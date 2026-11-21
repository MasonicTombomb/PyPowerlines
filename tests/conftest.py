"""Shared pytest fixtures for the PyPowerlines test suite."""

from collections.abc import Iterator

import pytest

from pypowerlines._log import shutdown_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    """Make sure no test leaks an annunciator configuration into the next.

    annunciator keeps its configuration (handlers, hooks, log files) in
    module-level state. A test that configures logging and then fails
    before cleaning up would otherwise change the behaviour of every test
    after it. ``shutdown_logging`` is safe to call when nothing is
    configured.
    """
    yield
    shutdown_logging()
