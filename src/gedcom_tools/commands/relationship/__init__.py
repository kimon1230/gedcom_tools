"""Relationship command — find genealogical relationships between individuals."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.relationship.algorithm import (
    find_relationship,
    load_individuals,
)
from gedcom_tools.commands.relationship.formatter import format_json, format_text
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.graph import build_parent_child_graph
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction

_XREF_PATTERN = re.compile(r"^@[A-Za-z0-9_.:\-]+@$")


def _validate_xref(value: str) -> str:
    """Validate xref format for argparse type= usage."""
    if not _XREF_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            f"Invalid xref format: {value!r}. "
            "Expected format like @I1@, @I123@, @I1-1@. "
            "Must start and end with @, containing only letters, digits, "
            "periods, hyphens, underscores, or colons."
        )
    return value


def register_subcommand(
    subparsers: _SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "relationship",
        help="Determine the relationship between two individuals",
        description=(
            "Find the genealogical relationship between two individuals "
            "in a GEDCOM file using Lowest Common Ancestor analysis."
        ),
    )
    parser.add_argument(
        "file",
        type=Path,
        help="GEDCOM file to analyze",
    )
    parser.add_argument(
        "primary",
        type=_validate_xref,
        help="Primary individual xref (e.g., @I1@)",
    )
    parser.add_argument(
        "target",
        type=_validate_xref,
        help="Target individual xref (e.g., @I2@)",
    )
    parser.add_argument(
        "--type",
        choices=["blood", "all"],
        default="blood",
        dest="rel_type",
        help="Relationship display: blood (default) or all (show half-prefix)",
    )
    parser.add_argument(
        "--paths",
        type=int,
        default=1,
        help="Number of relationship paths to show (default: 1)",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=30,
        help="Maximum ancestor search depth (default: 30)",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file
    primary: str = args.primary
    target: str = args.target
    output_format: str = getattr(args, "format", "text")
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)
    rel_type: str = args.rel_type
    paths: int = args.paths
    generations: int = args.generations

    if err := validate_input_file(file_path):
        return err

    show_half = rel_type == "all"

    try:
        tracker = PhaseTracker(
            4, stream=sys.stderr, no_color=no_color, quiet=quiet, verbose=verbose
        )

        with tracker.phase("Loading individuals"):
            individuals = load_individuals(file_path)

        for xref, label in [(primary, "Primary"), (target, "Target")]:
            if xref not in individuals:
                print(
                    f"Error: {label} individual {xref} not found in file. "
                    f"Use 'gedcom-tools search' to find individuals first.",
                    file=sys.stderr,
                )
                return EXIT_USAGE_ERROR

        with tracker.phase("Building relationship graph"):
            graph = build_parent_child_graph(file_path)

        with tracker.phase("Finding relationship"):
            result, truncated = find_relationship(
                graph,
                individuals,
                primary,
                target,
                paths=paths,
                max_generations=generations,
                show_half=show_half,
            )
            result.file = str(file_path)

        with tracker.phase("Formatting results"):
            if output_format == "json":
                output = format_json(result)
            else:
                colors = Colors(sys.stdout, force_disable=no_color)
                output = format_text(
                    result,
                    colors,
                    quiet=quiet,
                    verbose=verbose,
                    truncated=truncated,
                )

        if output:
            print(output)

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
