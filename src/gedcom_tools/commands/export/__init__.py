"""Export GEDCOM data to CSV or JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.export.collector import collect_export_data
from gedcom_tools.commands.export.formatters import format_csv, format_json
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS
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
        "--to",
        choices=["csv", "json"],
        default=argparse.SUPPRESS,
        help="Export format (default: csv)",
    )
    # Deprecated alias for --to. Kept working so existing scripts do not break,
    # but hidden because it collides with the global --format.
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
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

    # Resolve export format: --to wins, then --format (subparser alias or the
    # global flag, which share one Namespace slot), then csv. A global
    # "--format text" means "unspecified" here — export has no text output.
    requested = getattr(args, "to", None) or getattr(args, "format", None)
    fmt: str = requested if requested in ("csv", "json") else "csv"

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
            if sys.platform != "win32":
                try:
                    import os

                    os.chmod(output_path, 0o600)
                except OSError:
                    pass
            if not quiet:
                print(f"Exported to {output_path}", file=sys.stderr)
        else:
            sys.stdout.write(output)

        return EXIT_SUCCESS

    except BrokenPipeError:
        # cli._run_command turns this into a clean exit; catching it in the
        # generic handler below would report a closed pipe as a failure.
        raise
    except Exception as e:
        if verbose:
            raise
        from gedcom_tools.utils import sanitize_error

        print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
        return EXIT_ERROR
