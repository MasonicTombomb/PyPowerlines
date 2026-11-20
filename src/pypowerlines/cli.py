"""Command-line interface for pypowerlines."""

import argparse
from collections.abc import Sequence

from pypowerlines import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Parser for the ``pypowerlines`` command.
    """
    parser = argparse.ArgumentParser(
        prog="pypowerlines",
        description="Steady-state transmission network simulator with weather-dependent losses.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``pypowerlines`` command.

    Parameters
    ----------
    argv : Sequence[str] or None
        Arguments to parse; ``None`` reads them from ``sys.argv``.

    Returns
    -------
    int
        Process exit code.
    """
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
