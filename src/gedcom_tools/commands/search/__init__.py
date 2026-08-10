from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.search.collector import collect_individuals
from gedcom_tools.commands.search.formatter import (
    format_count,
    format_json,
    format_text,
)
from gedcom_tools.commands.search.matcher import match_individual
from gedcom_tools.commands.search.models import SearchResult
from gedcom_tools.commands.search.query import XREF_FIELDS, parse_query
from gedcom_tools.commands.search.relationships import (
    build_parent_child_graph,
    find_ancestors,
    find_descendants,
)
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "search",
        help="Search for individuals matching criteria",
        description="Search individuals in a GEDCOM file using flexible query syntax.",
        epilog=textwrap.dedent("""\
            query syntax:
              Terms are space-separated (AND logic). Quote the query to prevent
              shell expansion of ~ and *.

              field:value     substring match (default)
              field=value     exact match
              field~value     phonetic match (Soundex or Metaphone, see --phonetic)

              A bare term (no field prefix) searches all name fields.

            fields:
              name, given, surname, born, died, place, sex, ancestor, descendant

            examples:
              gedcom-tools search tree.ged 'Smith'
              gedcom-tools search tree.ged 'surname~Schmidt born:1800-1850'
              gedcom-tools search tree.ged 'place:"New York" sex:F'
              gedcom-tools search tree.ged 'ancestor:@I1@ born:1800-1900'
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file",
        type=Path,
        help="GEDCOM file to search",
    )
    parser.add_argument(
        "query",
        help="Search query (e.g. 'surname~Schmidt born:1800-1850')",
    )
    parser.add_argument(
        "--regex",
        action="store_true",
        default=False,
        help="Treat : operator values as regex patterns",
    )
    parser.add_argument(
        "--fuzzy-dates",
        type=int,
        default=None,
        metavar="N",
        help="Expand approximate dates +/-N years",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of results to display",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        default=False,
        help="Show match count only",
    )
    parser.add_argument(
        "--phonetic",
        choices=["soundex", "metaphone"],
        default="soundex",
        help="Phonetic algorithm for ~ operator (default: soundex)",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file
    query_string: str = args.query
    output_format: str = getattr(args, "format", "text")
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)
    regex_mode: bool = args.regex
    fuzzy_dates: int | None = args.fuzzy_dates
    limit: int | None = args.limit
    count_only: bool = args.count
    phonetic: str = getattr(args, "phonetic", "soundex")

    if err := validate_input_file(file_path):
        return err

    try:
        query = parse_query(
            query_string,
            regex_mode=regex_mode,
            fuzzy_dates=fuzzy_dates,
            limit=limit,
            count_only=count_only,
            phonetic_algo=phonetic,
        )
    except ValueError as exc:
        from gedcom_tools.utils import sanitize_error

        print(f"Error: {sanitize_error(str(exc))}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Determine phase count for progress tracking
    relationship_terms = [t for t in query.terms if t.field in XREF_FIELDS]
    phase_count = 2  # collect + match
    if relationship_terms:
        phase_count += 1  # relationship graph building
    phase_count += 1  # formatting

    try:
        tracker = PhaseTracker(
            phase_count,
            stream=sys.stderr,
            no_color=no_color,
            quiet=quiet,
            verbose=verbose,
        )

        with tracker.phase("Collecting individuals"):
            individuals, encoding_info = collect_individuals(
                file_path, algorithm=phonetic
            )

        # Build relationship pre-filter if needed
        relationship_xrefs: set[str] | None = None
        if relationship_terms:
            with tracker.phase("Building relationship graph"):
                graph = build_parent_child_graph(file_path)
                known_xrefs = {ind.xref for ind in individuals}

                sets: list[set[str]] = []
                for term in relationship_terms:
                    xref = term.value
                    if xref not in known_xrefs:
                        print(
                            f"Error: Individual {xref} not found in file. "
                            f"Use search to find individuals first, then use "
                            f"their @Ixxx@ identifier with ancestor: or descendant:",
                            file=sys.stderr,
                        )
                        return EXIT_USAGE_ERROR

                    if term.field == "ancestor":
                        # ancestor:@I1@ → find descendants of I1
                        sets.append(find_descendants(graph, xref))
                    else:
                        # descendant:@I5@ → find ancestors of I5
                        sets.append(find_ancestors(graph, xref))

                # Intersect all relationship sets
                relationship_xrefs = sets[0]
                for s in sets[1:]:
                    relationship_xrefs = relationship_xrefs & s

        with tracker.phase("Matching individuals"):
            matches = []
            for ind in individuals:
                match = match_individual(ind, query, relationship_xrefs)
                if match is not None:
                    matches.append(match)

        # Apply --limit truncation (but not when --count, which reports total)
        truncated = False
        if not count_only and query.limit is not None and query.limit > 0:
            if len(matches) > query.limit:
                matches = matches[: query.limit]
                truncated = True

        with tracker.phase("Formatting results"):
            result = SearchResult(
                file_path=str(file_path),
                query_string=query_string,
                encoding=encoding_info,
                total_individuals=len(individuals),
                matches=matches,
                truncated=truncated,
            )

            if count_only:
                output = format_count(result, json_mode=(output_format == "json"))
            elif output_format == "json":
                output = format_json(result)
            else:
                colors = Colors(sys.stdout, force_disable=no_color)
                output = format_text(
                    result,
                    colors,
                    quiet=quiet,
                    verbose=verbose,
                    phonetic_algo=query.phonetic_algo,
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
