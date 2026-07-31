"""Convert GEDCOM files between character encodings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ged4py.parser import CodecError, ParserError

from gedcom_tools.commands.convert.transcoder import (
    CODEC_TO_CHAR,
    ConvertResult,
    resolve_target_codec,
    transcode,
)
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import (
    BOM_ENCODINGS,
    EncodingInfo,
    check_output_safety,
    detect_encoding,
    resolve_source_codec,
    validate_input_file,
)

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


def register_subcommand(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "convert",
        help="Convert GEDCOM file to a different character encoding",
        description=(
            "Transcode a GEDCOM file between character encodings "
            "(e.g., ANSEL to UTF-8) with automatic CHAR header update, "
            "BOM handling, and NFC normalization."
        ),
    )
    parser.add_argument(
        "file",
        type=Path,
        help="GEDCOM file to convert",
    )
    parser.add_argument(
        "--to",
        choices=["utf-8", "ansel", "ascii", "unicode"],
        required=True,
        dest="to_encoding",
        help="Target encoding",
    )
    parser.add_argument(
        "--from",
        type=str,
        default=None,
        dest="from_encoding",
        help="Override source encoding detection (any Python codec name)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output file path",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file",
    )
    parser.add_argument(
        "--bom",
        action="store_true",
        help="Add byte order mark to output",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Skip NFC Unicode normalization",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview conversion without writing output",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file
    to_encoding: str = args.to_encoding
    from_encoding: str | None = args.from_encoding
    output: Path = args.output
    force: bool = args.force
    bom: bool = args.bom
    no_normalize: bool = args.no_normalize
    dry_run: bool = args.dry_run
    quiet: bool = getattr(args, "quiet", False)
    verbose: bool = getattr(args, "verbose", False)
    no_color: bool = getattr(args, "no_color", False)

    if err := validate_input_file(file_path):
        return err

    safety_err = check_output_safety(
        file_path, output, force=force, dry_run=dry_run, command="Convert"
    )
    if safety_err is not None:
        print(safety_err, file=sys.stderr)
        return EXIT_ERROR

    colors = Colors(sys.stdout, force_disable=no_color)
    tracker = PhaseTracker(
        2, stream=sys.stderr, no_color=no_color, quiet=quiet, verbose=verbose
    )

    try:
        with tracker.phase("Detecting encoding"):
            # Detection parses the header, which throws on a broken CHAR value.
            # --from exists to rescue exactly those files, so skip it entirely
            # when the user has already told us the encoding.
            if from_encoding is not None:
                encoding_info = EncodingInfo(encoding=from_encoding)
            else:
                encoding_info = detect_encoding(file_path)

            try:
                source_codec = resolve_source_codec(encoding_info, from_encoding)
                target_codec = resolve_target_codec(to_encoding)
            except ValueError as e:
                from gedcom_tools.utils import sanitize_error

                print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
                return EXIT_USAGE_ERROR

            normalize = (source_codec == "gedcom") and not no_normalize
            target_char = CODEC_TO_CHAR[target_codec]
            add_bom = bom and target_codec in BOM_ENCODINGS

        with tracker.phase("Transcoding"):
            result: ConvertResult = transcode(
                file_path,
                output,
                source_codec=source_codec,
                target_codec=target_codec,
                target_char=target_char,
                normalize=normalize,
                add_bom=add_bom,
                dry_run=dry_run,
            )

    except (CodecError, ParserError) as e:
        # CodecError currently subclasses ParserError; both are listed so a
        # future ged4py reshuffle cannot let one of them escape as a traceback.
        from gedcom_tools.utils import sanitize_error

        print(
            f"Error: {sanitize_error(str(e))}\n"
            "  Use --from to state the source encoding and skip header "
            "detection (e.g. --from ansel).",
            file=sys.stderr,
        )
        return EXIT_ERROR
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError) as e:
        from gedcom_tools.utils import sanitize_error

        print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
        return EXIT_ERROR

    fmt = getattr(args, "format", "text")
    if fmt == "json":
        sys.stdout.write(result.format_json() + "\n")
    else:
        print(result.format_text(colors, quiet))

    if result.lines_over_limit > 0 and not quiet:
        print(
            f"Warning: {result.lines_over_limit:,} lines exceed the "
            f"GEDCOM 255-byte limit in {to_encoding}",
            file=sys.stderr,
        )

    return EXIT_SUCCESS
