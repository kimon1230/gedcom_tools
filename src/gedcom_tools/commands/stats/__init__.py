"""Stats command for GEDCOM files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Re-export public API
from gedcom_tools.commands.stats.collector import StatsCollector
from gedcom_tools.commands.stats.formatters import StatsResult
from gedcom_tools.commands.stats.models import (
    AggregateStats,
    CoverageStats,
    DatePrecisionStats,
    FamilyData,
    FamilyEntry,
    GenderedAggregateStats,
    GenerationEntry,
    IndividualData,
    LifespanStats,
    MarriageStats,
    RankedItem,
    TimelineEntry,
)
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS
from gedcom_tools.progress import Colors
from gedcom_tools.utils import validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction

__all__ = [
    # Main API
    "register_subcommand",
    "run",
    "StatsCollector",
    "StatsResult",
    # Models
    "AggregateStats",
    "CoverageStats",
    "DatePrecisionStats",
    "FamilyData",
    "FamilyEntry",
    "GenderedAggregateStats",
    "GenerationEntry",
    "IndividualData",
    "LifespanStats",
    "MarriageStats",
    "RankedItem",
    "TimelineEntry",
]


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the stats subcommand."""
    parser = subparsers.add_parser(
        "stats",
        help="Display statistics about a GEDCOM file",
        description="Analyze a GEDCOM file and display genealogical statistics.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the GEDCOM file to analyze",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of items in top-N lists (default: 10)",
    )


def run(args: Namespace) -> int:
    """Execute the stats command."""
    file_path: Path = args.file

    if err := validate_input_file(file_path):
        return err

    output_format = getattr(args, "format", "text")
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    no_color = getattr(args, "no_color", False)
    top_n = getattr(args, "top", 10)

    try:
        collector = StatsCollector(
            file_path=file_path,
            quiet=quiet,
            verbose=verbose,
            no_color=no_color,
            top_n=top_n,
        )
        result = collector.collect()

        if output_format == "json":
            print(result.format_json())
        else:
            colors = Colors(sys.stdout, force_disable=no_color)
            output = result.format_text(colors, quiet=quiet)
            if output:
                print(output)

        return EXIT_SUCCESS

    except Exception as e:
        if verbose:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR
