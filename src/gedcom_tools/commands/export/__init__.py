"""Export GEDCOM data to CSV or JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.export.collector import collect_export_data
from gedcom_tools.commands.export.formatters import format_csv, format_json
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.progress import PhaseTracker
from gedcom_tools.utils import validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "export",
        help="Export individuals and families to CSV or JSON",
        description=(
            "Extract all individuals and families from a GEDCOM file "
            "into CSV or JSON format for use in spreadsheets, databases, "
            "and downstream tools."
        ),
    )
    parser.add_argument(
        "file",
        type=Path,
        help="GEDCOM file to export",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default=argparse.SUPPRESS,
        help="Export format (default: csv)",
    )
    parser.add_argument(
        "--table",
        choices=["individuals", "families"],
        default="individuals",
        help="Table to export in CSV mode (default: individuals; ignored for JSON)",
    )
    parser.add_argument(
        "--no-bom",
        action="store_true",
        help="Omit UTF-8 BOM when writing CSV to a file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists",
    )
    parser.add_argument(
        "--redact-living",
        action="store_true",
        help="Replace names and dates of estimated-living individuals",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=110,
        help="Maximum age for living estimation (default: 110)",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)
    table: str = args.table
    redact_living: bool = args.redact_living
    max_age: int = args.max_age
    no_bom: bool = args.no_bom
    output_path: Path | None = getattr(args, "output", None)
    force: bool = getattr(args, "force", False)

    # Resolve export format
    fmt = getattr(args, "format", "text")
    if fmt == "text":
        fmt = "csv"
    elif fmt not in ("csv", "json"):
        print(
            f"Error: --format {fmt} is not valid for the export command. "
            "Use --format csv or --format json.",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    if err := validate_input_file(file_path):
        return err

    # Overwrite protection
    if output_path and output_path.exists() and not force:
        print(
            f"Error: {output_path} already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        tracker = PhaseTracker(
            2, stream=sys.stderr, no_color=no_color, quiet=quiet, verbose=verbose
        )

        with tracker.phase("Reading file"):
            result = collect_export_data(file_path)

        with tracker.phase("Formatting output"):
            include_bom = fmt == "csv" and output_path is not None and not no_bom

            if fmt == "json":
                output = format_json(
                    result, redact_living=redact_living, max_age=max_age
                )
            else:
                output = format_csv(
                    result,
                    table=table,
                    include_bom=include_bom,
                    redact_living=redact_living,
                    max_age=max_age,
                )

        if output_path:
            output_path.write_text(output, encoding="utf-8")
            if not quiet:
                print(f"Exported to {output_path}", file=sys.stderr)
        else:
            sys.stdout.write(output)

        return EXIT_SUCCESS

    except Exception as e:
        if verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR
