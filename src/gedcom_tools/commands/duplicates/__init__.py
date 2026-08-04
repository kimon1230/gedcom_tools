from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.compare.blocker import (
    DEFAULT_MAX_BLOCK_SIZE,
    describe_oversized_blocks,
    generate_candidates,
)
from gedcom_tools.commands.compare.collector import collect_individuals
from gedcom_tools.commands.compare.dedup import compute_field_diffs
from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    MatchPair,
    MatchScore,
)
from gedcom_tools.commands.compare.scorer import score_pair
from gedcom_tools.commands.duplicates.formatters import format_json, format_text
from gedcom_tools.commands.duplicates.models import DuplicatesResult
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import detect_encoding, validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "duplicates",
        help="Find duplicate individuals within a GEDCOM file",
        description="Scan a single GEDCOM file for potential duplicate individuals.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="GEDCOM file to scan for duplicates",
    )
    parser.add_argument(
        "--certain-threshold",
        type=float,
        default=0.85,
        help="Minimum score for certain duplicate (default: 0.85)",
    )
    parser.add_argument(
        "--probable-threshold",
        type=float,
        default=0.65,
        help="Minimum score for probable duplicate (default: 0.65)",
    )
    parser.add_argument(
        "--show-matches",
        choices=["all", "certain", "probable"],
        default="all",
        help="Which matches to show (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max items per output section (text default: 50, json default: unlimited)",
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
    parser.add_argument(
        "--max-block-size",
        type=int,
        default=DEFAULT_MAX_BLOCK_SIZE,
        help=(
            "Max individuals sharing a blocking key before the group is "
            f"skipped (default: {DEFAULT_MAX_BLOCK_SIZE})"
        ),
    )


def _normalize_candidates(
    raw: set[tuple[str, str]],
) -> set[tuple[str, str]]:
    normalized: set[tuple[str, str]] = set()
    for a, b in raw:
        if a == b:
            continue
        key = (min(a, b), max(a, b))
        normalized.add(key)
    return normalized


def _deduplicate_single_file(
    scored_pairs: list[tuple[CompareIndividual, CompareIndividual, MatchScore]],
) -> tuple[list[MatchPair], list[MatchPair]]:
    used: set[str] = set()
    certain: list[MatchPair] = []
    probable: list[MatchPair] = []

    for a, b, score in sorted(scored_pairs, key=lambda t: t[2].total, reverse=True):
        if score.classification == "non_match":
            continue
        if a.xref in used or b.xref in used:
            continue
        used.add(a.xref)
        used.add(b.xref)
        diffs = compute_field_diffs(a, b)
        pair = MatchPair(individual_a=a, individual_b=b, score=score, field_diffs=diffs)
        if score.classification == "certain":
            certain.append(pair)
        else:
            probable.append(pair)

    return certain, probable


def run(args: Namespace) -> int:
    file_path: Path = args.file
    output_format: str = getattr(args, "format", "text")
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)
    certain_threshold: float = args.certain_threshold
    probable_threshold: float = args.probable_threshold
    reject_sex_mismatch: bool = args.reject_sex_mismatch
    phonetic: str = getattr(args, "phonetic", "soundex")
    max_block_size: int = getattr(args, "max_block_size", DEFAULT_MAX_BLOCK_SIZE)
    show_matches: str = args.show_matches
    limit: int | None = args.limit

    if limit is None:
        limit = 0 if output_format == "json" else 50

    if not (0.0 <= probable_threshold <= 1.0) or not (0.0 <= certain_threshold <= 1.0):
        print("Error: Thresholds must be between 0.0 and 1.0.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if certain_threshold <= probable_threshold:
        print(
            "Error: --certain-threshold must be greater than --probable-threshold.",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    if max_block_size < 1:
        print(
            "Error: --max-block-size must be at least 1. "
            f"The default is {DEFAULT_MAX_BLOCK_SIZE}.",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    if err := validate_input_file(file_path):
        return err

    try:
        tracker = PhaseTracker(
            3, stream=sys.stderr, no_color=no_color, quiet=quiet, verbose=verbose
        )

        with tracker.phase("Reading file"):
            encoding = detect_encoding(file_path)
            individuals = collect_individuals(
                file_path, file_path.name, algorithm=phonetic
            )

        oversized_keys: set[str] = set()

        with tracker.phase("Finding duplicates"):
            by_xref: dict[str, CompareIndividual] = {
                ind.xref: ind for ind in individuals
            }

            raw_candidates = generate_candidates(
                individuals,
                individuals,
                max_block_size=max_block_size,
                algorithm=phonetic,
                oversized_keys=oversized_keys,
            )
            candidates = _normalize_candidates(raw_candidates)

            scored: list[tuple[CompareIndividual, CompareIndividual, MatchScore]] = []
            for xref_a, xref_b in candidates:
                ind_a = by_xref.get(xref_a)
                ind_b = by_xref.get(xref_b)
                if ind_a is None or ind_b is None:
                    continue
                score = score_pair(
                    ind_a,
                    ind_b,
                    certain_threshold=certain_threshold,
                    probable_threshold=probable_threshold,
                    reject_sex_mismatch=reject_sex_mismatch,
                )
                scored.append((ind_a, ind_b, score))

            certain_matches, probable_matches = _deduplicate_single_file(scored)

        with tracker.phase("Formatting results"):
            result = DuplicatesResult(
                file=str(file_path),
                encoding=encoding,
                total_individuals=len(individuals),
                certain_matches=certain_matches,
                probable_matches=probable_matches,
                oversized_blocks_skipped=len(oversized_keys),
            )

            if output_format == "json":
                output = format_json(result, show_matches=show_matches, limit=limit)
            else:
                colors = Colors(sys.stdout, force_disable=no_color)
                output = format_text(
                    result,
                    colors,
                    quiet=quiet,
                    verbose=verbose,
                    show_matches=show_matches,
                    limit=limit,
                )

        if oversized_keys:
            # Printed even under --quiet: this says the answer is incomplete,
            # which is exactly what a user skimming a one-line summary needs.
            print(
                describe_oversized_blocks(len(oversized_keys), max_block_size),
                file=sys.stderr,
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
