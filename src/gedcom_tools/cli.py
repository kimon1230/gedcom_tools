"""Command-line interface for gedcom-tools."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from gedcom_tools import __version__
from gedcom_tools.commands import validate
from gedcom_tools.constants import EXIT_ERROR, EXIT_USAGE_ERROR

if TYPE_CHECKING:
    from argparse import Namespace


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gedcom-tools",
        description="CLI utility for GEDCOM file validation, analysis, and search.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed progress with timing",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-essential output (errors only)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        metavar="<command>",
    )
    validate.register_subcommand(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.verbose and args.quiet:
        parser.error("--verbose and --quiet are mutually exclusive")

    if args.command is None:
        parser.print_help()
        return EXIT_USAGE_ERROR

    return _run_command(args)


def _run_command(args: Namespace) -> int:
    handlers = {
        "validate": validate.run,
    }

    try:
        return handlers[args.command](args)
    except Exception as e:
        if args.verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
