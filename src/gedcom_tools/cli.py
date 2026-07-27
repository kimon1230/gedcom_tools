"""Command-line interface for gedcom-tools."""

from __future__ import annotations

import argparse
import os
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
from gedcom_tools.progress import set_ascii_mode

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
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="Use ASCII-only decorations (for consoles lacking the glyph fonts)",
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


_streams_hardened = False


def _harden_streams() -> None:
    """Make stdout/stderr survive non-ASCII output on legacy codepages.

    Windows picks the ANSI codepage (cp1252 and friends) for a redirected
    stream, so writing a name like Muller with an umlaut - or the report's own
    check marks - raises UnicodeEncodeError. The tool works interactively and
    dies under `> out.txt`, which is the worst way for it to fail.

    Redirected streams get UTF-8: there is no terminal on the other end whose
    codepage we owe anything to. A real terminal keeps its encoding, because
    forcing UTF-8 onto a cp1252 console produces mojibake; it only gets the
    error handler, which changes nothing except for characters that would
    otherwise raise.
    """
    global _streams_hardened
    if _streams_hardened:
        return
    _streams_hardened = True

    io_encoding = os.environ.get("PYTHONIOENCODING", "")
    if ":" in io_encoding:
        # User specified their own error handler; leave both settings alone.
        return

    for stream, original in (
        (sys.stdout, sys.__stdout__),
        (sys.stderr, sys.__stderr__),
    ):
        # Only touch the real interpreter streams. pytest's CaptureIO is a
        # TextIOWrapper subclass and would otherwise be mutated session-wide.
        if stream is None or stream is not original:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if stream.isatty() or io_encoding:
                reconfigure(errors="backslashreplace")
            else:
                # reconfigure() resets errors to strict unless told otherwise.
                reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def main(argv: list[str] | None = None) -> int:
    # Before create_parser(): argparse writes --help and usage errors from
    # inside parse_args() and then exits.
    _harden_streams()

    parser = create_parser()
    args = parser.parse_args(argv)

    if args.ascii:
        set_ascii_mode(True)

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
