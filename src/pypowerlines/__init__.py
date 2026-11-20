"""Steady-state transmission network simulator with weather-dependent losses."""

from ._version import __version__

__all__ = ["__version__", "main"]


def main() -> None:
    """Run the command-line entry point."""
    print("Hello from pypowerlines!")
