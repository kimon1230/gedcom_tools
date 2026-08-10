"""Filter and transform GEDCOM files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gedcom_tools.commands.filter.models import FilterResult, FilterSpec, RecordCounts
from gedcom_tools.commands.filter.parser import (
    count_records,
    detect_line_ending,
    group_records,
    has_head_and_trlr,
    parse_lines,
)
from gedcom_tools.commands.filter.transforms import (
    apply_strip_transforms,
    extract_subtree,
)
from gedcom_tools.commands.filter.writer import (
    clean_dangling_pointers,
    remove_empty_families,
    serialize_records,
)
from gedcom_tools.constants import (
    EXIT_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    MAX_FILE_SIZE_BYTES,
)
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import (
    BOMS,
    EncodingInfo,
    check_output_safety,
    detect_encoding,
    resolve_source_codec,
    sanitize_error,
    strip_bom,
    validate_input_file,
    write_output_securely,
)

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("filter", help="Filter and transform GEDCOM files")
    parser.add_argument("file", type=Path, help="Input GEDCOM file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output file path (always a new file)",
    )
    parser.add_argument(
        "--from",
        type=str,
        default=None,
        dest="from_encoding",
        help="Override source encoding detection (any Python codec name)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing output file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )

    strip = parser.add_argument_group("strip options")
    strip.add_argument(
        "--strip-custom-tags",
        action="store_true",
        help="Remove all custom (_-prefixed) tags",
    )
    strip.add_argument(
        "--strip-notes", action="store_true", help="Remove NOTE records and references"
    )
    strip.add_argument(
        "--strip-sources",
        action="store_true",
        help="Remove SOUR records and citations",
    )
    strip.add_argument(
        "--strip-multimedia",
        action="store_true",
        help="Remove OBJE records and references",
    )
    strip.add_argument(
        "--strip-tag",
        action="append",
        default=[],
        metavar="TAG",
        help="Remove specific tag (repeatable)",
    )

    subtree = parser.add_argument_group("subtree options")
    subtree.add_argument(
        "--subtree",
        metavar="XREF",
        help="Extract subtree rooted at individual (e.g., @I1@)",
    )
    subtree.add_argument(
        "--ancestors",
        type=int,
        metavar="N",
        help="Max ancestor generations (default: unlimited)",
    )
    subtree.add_argument(
        "--descendants",
        type=int,
        default=0,
        metavar="N",
        help="Max descendant generations (default: 0)",
    )
    subtree.add_argument(
        "--include-spouses",
        action="store_true",
        help="Include spouses of extracted individuals",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file
    output: Path = args.output
    force: bool = args.force
    dry_run: bool = args.dry_run
    from_encoding: str | None = getattr(args, "from_encoding", None)
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)

    if err := validate_input_file(file_path):
        return err

    # Validate subtree-related args
    if args.subtree is not None:
        if not re.match(r"^@[^@]+@$", args.subtree):
            print(
                f"Error: Invalid xref format: {args.subtree}. " "Expected format: @I1@",
                file=sys.stderr,
            )
            return EXIT_USAGE_ERROR
    if args.ancestors is not None and args.subtree is None:
        print("Error: --ancestors requires --subtree", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if args.descendants != 0 and args.subtree is None:
        print("Error: --descendants requires --subtree", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if args.include_spouses and args.subtree is None:
        print("Error: --include-spouses requires --subtree", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if args.ancestors is not None and args.ancestors < 0:
        print("Error: --ancestors must be non-negative", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if args.descendants < 0:
        print("Error: --descendants must be non-negative", file=sys.stderr)
        return EXIT_USAGE_ERROR

    spec = _build_filter_spec(args)
    if not _has_any_filter(spec):
        print("Error: At least one filter option is required.", file=sys.stderr)
        return EXIT_USAGE_ERROR

    safety_err = check_output_safety(
        file_path, output, force=force, dry_run=dry_run, command="Filter"
    )
    if safety_err is not None:
        print(safety_err, file=sys.stderr)
        return EXIT_ERROR

    colors = Colors(sys.stdout, force_disable=no_color)
    tracker = PhaseTracker(
        4, stream=sys.stderr, no_color=no_color, quiet=quiet, verbose=verbose
    )

    file_size = file_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        print(
            f"Error: File is too large ({actual_mb:.1f} MB). "
            f"Maximum supported size is {limit_mb} MB.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    # Resolved outside the phase on purpose: Spinner.__exit__ reports success
    # whenever no exception escaped, so returning an exit code from inside a
    # phase paints a green tick immediately above the error text.
    #
    # Detection parses the header, which throws on a broken CHAR value. --from
    # exists to rescue exactly those files, so skip it when the user has
    # already said what the encoding is.
    if from_encoding is not None:
        encoding_info = EncodingInfo(encoding=from_encoding)
    else:
        encoding_info = detect_encoding(file_path)
    try:
        source_codec = resolve_source_codec(encoding_info, from_encoding)
    except ValueError as e:
        print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    with tracker.phase("Reading input"):
        raw_bytes = file_path.read_bytes()
        stripped_bytes, bom_type = strip_bom(raw_bytes)
        try:
            text = stripped_bytes.decode(source_codec)
        except (UnicodeDecodeError, LookupError, ValueError) as e:
            # A --from the bytes will not survive is a usage error, not a crash:
            # unguarded this surfaces as "Error: UnicodeDecodeError: ..." from
            # the generic handler in cli.py.
            print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
            return EXIT_USAGE_ERROR

    with tracker.phase("Parsing GEDCOM"):
        line_ending = detect_line_ending(text)
        lines = parse_lines(text)
        records = group_records(lines)

        if not has_head_and_trlr(records):
            print(
                "Error: Input file has no valid GEDCOM structure "
                "(missing HEAD or TRLR)",
                file=sys.stderr,
            )
            return EXIT_ERROR

        source_counts = count_records(records)

    with tracker.phase("Filtering"):
        removed_xrefs: set[str] = set()
        if spec.subtree_root is not None:
            records, subtree_removed = extract_subtree(
                records,
                spec.subtree_root,
                spec.ancestor_depth,
                spec.descendant_depth,
                spec.include_spouses,
            )
            removed_xrefs = subtree_removed

        strip_records, strip_removed = apply_strip_transforms(records, spec)
        records = strip_records
        removed_xrefs.update(strip_removed)

        records, dangling_removed = clean_dangling_pointers(records, removed_xrefs)
        records, cascade_xrefs, empty_fam_count = remove_empty_families(records)
        if cascade_xrefs:
            records, cascade_dangling = clean_dangling_pointers(records, cascade_xrefs)
            dangling_removed += cascade_dangling

        output_counts = count_records(records)

    # Backstop: no transform may drop the structural records, whatever route
    # it takes. Bail out before writing rather than emit a broken file.
    if not has_head_and_trlr(records):
        print(
            "Error: Filtering removed HEAD or TRLR; "
            "output would not be a valid GEDCOM.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    removed_counts = RecordCounts(
        indi=source_counts.indi - output_counts.indi,
        fam=source_counts.fam - output_counts.fam,
        note=source_counts.note - output_counts.note,
        sour=source_counts.sour - output_counts.sour,
        obje=source_counts.obje - output_counts.obje,
        repo=source_counts.repo - output_counts.repo,
        subm=source_counts.subm - output_counts.subm,
        other=source_counts.other - output_counts.other,
    )

    write_err: str | None = None
    with tracker.phase("Writing output"):
        if not dry_run:
            out_text = serialize_records(records, line_ending)
            out_bytes = out_text.encode(source_codec)
            if bom_type is not None:
                out_bytes = BOMS[bom_type] + out_bytes
            write_err = write_output_securely(output, out_bytes, force=force)

    if write_err is not None:
        print(write_err, file=sys.stderr)
        return EXIT_ERROR

    result = FilterResult(
        source_path=str(file_path),
        output_path=str(output),
        source_counts=source_counts,
        output_counts=output_counts,
        removed_counts=removed_counts,
        dangling_lines_removed=dangling_removed,
        empty_families_removed=empty_fam_count,
        dry_run=dry_run,
    )

    fmt = getattr(args, "format", "text")
    if fmt == "json":
        sys.stdout.write(result.format_json() + "\n")
    else:
        print(result.format_text(colors, quiet))

    return EXIT_SUCCESS


def _build_filter_spec(args: Namespace) -> FilterSpec:
    return FilterSpec(
        strip_custom_tags=args.strip_custom_tags,
        strip_notes=args.strip_notes,
        strip_sources=args.strip_sources,
        strip_multimedia=args.strip_multimedia,
        strip_tags=[t.upper() for t in args.strip_tag],
        subtree_root=args.subtree,
        ancestor_depth=args.ancestors,
        descendant_depth=args.descendants,
        include_spouses=args.include_spouses,
    )


def _has_any_filter(spec: FilterSpec) -> bool:
    return (
        spec.strip_custom_tags
        or spec.strip_notes
        or spec.strip_sources
        or spec.strip_multimedia
        or len(spec.strip_tags) > 0
        or spec.subtree_root is not None
    )
