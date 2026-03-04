"""Command-line interface for gedcom-tools."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from gedcom_tools import __version__
from gedcom_tools.commands import (
    compare,
    convert,
    duplicates,
    export,
    filter,
    isolated,
    languages,
    relationship,
    search,
    stats,
    validate,
)
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
    stats.register_subcommand(subparsers)
    isolated.register_subcommand(subparsers)
    languages.register_subcommand(subparsers)
    compare.register_subcommand(subparsers)
    search.register_subcommand(subparsers)
    relationship.register_subcommand(subparsers)
    duplicates.register_subcommand(subparsers)
    export.register_subcommand(subparsers)
    convert.register_subcommand(subparsers)
    filter.register_subcommand(subparsers)

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
        "stats": stats.run,
        "isolated": isolated.run,
        "languages": languages.run,
        "compare": compare.run,
        "search": search.run,
        "relationship": relationship.run,
        "duplicates": duplicates.run,
        "export": export.run,
        "convert": convert.run,
        "filter": filter.run,
    }

    try:
        return handlers[args.command](args)
    except Exception as e:
        if args.verbose:
            # Note: --verbose shows file paths in traceback, acceptable for local CLI
            raise
        from gedcom_tools.utils import sanitize_error

        print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
