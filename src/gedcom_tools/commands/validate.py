"""Validate command for GEDCOM files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "validate",
        help="Validate a GEDCOM file for errors and issues",
        description="Check a GEDCOM file for structural errors and data issues.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the GEDCOM file to validate",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick", action="store_true", help="Fail fast on first error (default)"
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="Collect all errors with IDs and line numbers",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return EXIT_ERROR

    if not file_path.is_file():
        print(f"Error: Not a file: {file_path}", file=sys.stderr)
        return EXIT_ERROR

    # TODO: actual validation
    mode = "full" if args.full else "quick"
    print(f"Validation not yet implemented (mode: {mode})")
    print(f"File: {file_path}")

    return EXIT_SUCCESS
