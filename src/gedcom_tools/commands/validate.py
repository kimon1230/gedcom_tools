"""Validate command for GEDCOM files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS
from gedcom_tools.progress import Colors
from gedcom_tools.utils import validate_input_file
from gedcom_tools.validation import validate_file

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

    parser.add_argument(
        "--strict",
        choices=["5.5.1", "5.5.5"],
        help="Validate against a specific GEDCOM version",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file

    if err := validate_input_file(file_path):
        return err

    mode: Literal["quick", "full"] = "full" if args.full else "quick"

    # Get global options from parent parser
    output_format = getattr(args, "format", "text")
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    no_color = getattr(args, "no_color", False)
    strict = getattr(args, "strict", None)

    try:
        result = validate_file(
            file_path=file_path,
            mode=mode,
            strict=strict,
            quiet=quiet,
            verbose=verbose,
            no_color=no_color,
            stream=sys.stderr,
        )

        if output_format == "json":
            print(result.format_json())
        else:
            colors = Colors(sys.stdout, force_disable=no_color)
            output = result.format_text(colors, quiet=quiet)
            if output:  # Don't print empty string in quiet mode for valid files
                print(output)

        return EXIT_SUCCESS if result.success else EXIT_ERROR

    except BrokenPipeError:
        # cli._run_command turns this into a clean exit; catching it in the
        # generic handler below would report a closed pipe as a failure.
        raise
    except Exception as e:
        if verbose:
            raise
        from gedcom_tools.utils import report_error

        report_error(e)
        return EXIT_ERROR
