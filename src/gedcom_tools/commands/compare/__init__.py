from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.compare.blocker import generate_candidates
from gedcom_tools.commands.compare.collector import collect_individuals
from gedcom_tools.commands.compare.dedup import deduplicate_matches
from gedcom_tools.commands.compare.formatters import format_json, format_text
from gedcom_tools.commands.compare.models import CompareResult
from gedcom_tools.commands.compare.scorer import score_pair
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import detect_encoding, validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the compare subcommand."""
    parser = subparsers.add_parser(
        "compare",
        help="Compare two GEDCOM files to find matching individuals",
        description="Compare individuals across two GEDCOM files.",
    )
    parser.add_argument(
        "file_a",
        type=Path,
        help="First GEDCOM file (base)",
    )
    parser.add_argument(
        "file_b",
        type=Path,
        help="Second GEDCOM file (to compare against)",
    )
    parser.add_argument(
        "--certain-threshold",
        type=float,
        default=0.85,
        help="Minimum score for certain match (default: 0.85)",
    )
    parser.add_argument(
        "--probable-threshold",
        type=float,
        default=0.65,
        help="Minimum score for probable match (default: 0.65)",
    )
    parser.add_argument(
        "--show-matches",
        choices=["all", "certain", "probable"],
        default="all",
        help="Which matches to show (default: all)",
    )
    parser.add_argument(
        "--list-unique",
        action="store_true",
        help="List individuals unique to each file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max items per output section",
    )
    parser.add_argument(
        "--reject-sex-mismatch",
        action="store_true",
        help="Treat sex mismatches as hard reject",
    )
    parser.add_argument(
        "--phonetic",
        choices=["soundex", "metaphone"],
        default="soundex",
        help="Phonetic algorithm for blocking/scoring (default: soundex)",
    )


def run(args: Namespace) -> int:
    """Execute the compare command."""
    file_a: Path = args.file_a
    file_b: Path = args.file_b
    output_format: str = getattr(args, "format", "text")
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)
    certain_threshold: float = args.certain_threshold
    probable_threshold: float = args.probable_threshold
    show_matches: str = args.show_matches
    list_unique: bool = args.list_unique
    reject_sex_mismatch: bool = args.reject_sex_mismatch
    phonetic: str = getattr(args, "phonetic", "soundex")
    limit: int | None = args.limit

    # Default limit: unlimited for JSON, 50 for text
    if limit is None:
        limit = 0 if output_format == "json" else 50

    # Validate thresholds
    if not (0.0 <= probable_threshold <= 1.0) or not (0.0 <= certain_threshold <= 1.0):
        print("Error: Thresholds must be between 0.0 and 1.0.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if certain_threshold <= probable_threshold:
        print(
            "Error: --certain-threshold must be greater than --probable-threshold.",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    # Validate input files
    if err := validate_input_file(file_a):
        return err
    if err := validate_input_file(file_b):
        return err

    # Same-file detection
    try:
        same = os.path.samefile(file_a, file_b)
    except OSError:
        same = False  # Files may not exist yet (handled by validate above)
    if same:
        # Only samefile() belongs in a try here. BrokenPipeError is an OSError,
        # so widening it to cover the print would drop the return with it and
        # compare a file against itself.
        try:
            print(
                "Error: Both arguments point to the same file. "
                "Did you mean to compare two different files?",
                file=sys.stderr,
            )
        except OSError:
            pass  # Dead stderr does not change the verdict.
        return EXIT_USAGE_ERROR

    try:
        tracker = PhaseTracker(
            5, stream=sys.stderr, no_color=no_color, quiet=quiet, verbose=verbose
        )

        with tracker.phase("Detecting encodings"):
            encoding_a = detect_encoding(file_a)
            encoding_b = detect_encoding(file_b)

        with tracker.phase(f"Reading {file_a.name}"):
            individuals_a = collect_individuals(file_a, "A", algorithm=phonetic)

        with tracker.phase(f"Reading {file_b.name}"):
            individuals_b = collect_individuals(file_b, "B", algorithm=phonetic)

        with tracker.phase("Finding matches"):
            candidates = generate_candidates(
                individuals_a, individuals_b, algorithm=phonetic
            )

            map_a = {ind.xref: ind for ind in individuals_a}
            map_b = {ind.xref: ind for ind in individuals_b}

            scored = [
                (
                    map_a[xref_a],
                    map_b[xref_b],
                    score_pair(
                        map_a[xref_a],
                        map_b[xref_b],
                        certain_threshold=certain_threshold,
                        probable_threshold=probable_threshold,
                        reject_sex_mismatch=reject_sex_mismatch,
                    ),
                )
                for xref_a, xref_b in candidates
            ]

            certain_matches, probable_matches = deduplicate_matches(scored)

            matched_a = {p.individual_a.xref for p in certain_matches} | {
                p.individual_a.xref for p in probable_matches
            }
            matched_b = {p.individual_b.xref for p in certain_matches} | {
                p.individual_b.xref for p in probable_matches
            }
            unique_a = [ind for ind in individuals_a if ind.xref not in matched_a]
            unique_b = [ind for ind in individuals_b if ind.xref not in matched_b]

        with tracker.phase("Formatting results"):
            result = CompareResult(
                file_a=str(file_a),
                file_b=str(file_b),
                encoding_a=encoding_a,
                encoding_b=encoding_b,
                total_a=len(individuals_a),
                total_b=len(individuals_b),
                certain_matches=certain_matches,
                probable_matches=probable_matches,
                unique_to_a=unique_a,
                unique_to_b=unique_b,
            )

            if output_format == "json":
                output = format_json(
                    result,
                    show_matches=show_matches,
                    list_unique=list_unique,
                    limit=limit,
                )
            else:
                colors = Colors(sys.stdout, force_disable=no_color)
                output = format_text(
                    result,
                    colors,
                    quiet=quiet,
                    verbose=verbose,
                    show_matches=show_matches,
                    list_unique=list_unique,
                    limit=limit,
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
        from gedcom_tools.utils import report_error

        report_error(e)
        return EXIT_ERROR
