"""GEDCOM encoding transcoder — byte-level conversion with CHAR header fixup."""

from __future__ import annotations

import codecs
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import ansel  # type: ignore[import-untyped]

from gedcom_tools import __version__
from gedcom_tools.progress import Colors, glyphs
from gedcom_tools.utils import (
    BOMS,
    GEDCOM_CHARSETS,
    strip_bom,
)

ansel.register()
codecs.lookup("gedcom")

CODEC_TO_CHAR: dict[str, str] = {
    "utf-8": "UTF-8",
    "ascii": "ASCII",
    "utf-16-le": "UNICODE",
    "utf-16-be": "UNICODE",
    "gedcom": "ANSEL",
}


@dataclass
class ConvertResult:
    source_file: Path
    output_file: Path
    source_encoding: str  # human label
    target_encoding: str  # human label
    source_codec: str
    target_codec: str
    lines_total: int
    lines_over_limit: int
    normalized: bool
    bom_added: bool
    bom_stripped: str | None  # BOM encoding label like "utf-8", or None
    dry_run: bool

    def format_text(self, colors: Colors, quiet: bool) -> str:
        g = glyphs()
        if quiet:
            line = (
                f"Converted {self.source_file.name} "
                f"({self.source_encoding} {g.arrow} {self.target_encoding}) "
                f"{g.arrow} {self.output_file}"
            )
            if self.dry_run:
                line += " (dry run)"
            return line

        bom_label = "none"
        if self.bom_added:
            bom_label = "added"
        elif self.bom_stripped:
            bom_label = "stripped"

        lines: list[str] = [
            f"File: {self.source_file.name}",
            "",
            f"{colors.cyan}=== Conversion ==={colors.reset}",
            f"  Source encoding: {self.source_encoding}",
            f"  Target encoding: {self.target_encoding}",
            f"  Lines:           {self.lines_total:,}",
            f"  NFC normalized:  {'yes' if self.normalized else 'no'}",
            f"  BOM:             {bom_label}",
            f"  Output:          {self.output_file}",
        ]

        if self.lines_over_limit > 0:
            lines.append(
                f"\n  {colors.yellow}Warning: {self.lines_over_limit:,} lines "
                f"exceed 255-byte GEDCOM limit{colors.reset}"
            )

        if self.dry_run:
            lines.append("\n  (dry run -- no file written)")

        return "\n".join(lines)

    def format_json(self) -> str:
        data = {
            "source_file": str(self.source_file),
            "source_filename": self.source_file.name,
            "output_file": str(self.output_file),
            "output_filename": self.output_file.name,
            "source_encoding": self.source_encoding,
            "target_encoding": self.target_encoding,
            "lines_total": self.lines_total,
            "lines_over_limit": self.lines_over_limit,
            "normalized": self.normalized,
            "bom_added": self.bom_added,
            "bom_stripped": self.bom_stripped,
            "dry_run": self.dry_run,
            "gedcom_tools_version": __version__,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)


def resolve_target_codec(target: str) -> str:
    return GEDCOM_CHARSETS[target]


# Line anchors are EOL-agnostic: MULTILINE ^ handles LF and CRLF, the lookbehind
# handles classic Mac CR-only files. Terminators are matched the same way so a
# valueless "1 CHAR" is recognised regardless of the line ending that follows it.
_LINE_START = r"(?:^|(?<=\r))"
_CHAR_RE = re.compile(
    _LINE_START + r"1 CHAR(?:(?=[\r\n])|$| [^\r\n]*)",
    re.MULTILINE,
)
# Group 1 captures HEAD's own terminator (absent when HEAD is the final line).
# The CRLF alternative must come first, otherwise a bare \r splits the pair.
_HEAD_RE = re.compile(
    _LINE_START + r"0 HEAD[^\r\n]*(\r\n|\r|\n)?",
    re.MULTILINE,
)


def _dominant_eol(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def update_char_header(text: str, new_char: str) -> str:
    replacement = f"1 CHAR {new_char}"

    updated, count = _CHAR_RE.subn(replacement, text, count=1)
    if count > 0:
        return updated

    head_match = _HEAD_RE.search(text)
    if head_match is None:
        msg = "No HEAD record found -- not a valid GEDCOM file"
        raise ValueError(msg)

    insert_pos = head_match.end()
    eol = head_match.group(1)
    if eol is None:
        # HEAD is the last line and carries no terminator; supply one.
        eol = _dominant_eol(text)
        return text[:insert_pos] + eol + replacement + eol + text[insert_pos:]

    return text[:insert_pos] + replacement + eol + text[insert_pos:]


def count_long_lines(text: str, codec_name: str) -> tuple[int, int]:
    raw_lines = text.split("\n")
    # Filter trailing empty string from final newline
    if raw_lines and raw_lines[-1] == "":
        raw_lines = raw_lines[:-1]

    over = 0
    for line in raw_lines:
        stripped = line.rstrip("\r")
        if len(stripped.encode(codec_name, errors="replace")) > 255:
            over += 1

    return len(raw_lines), over


def transcode(
    source_path: Path,
    output_path: Path,
    *,
    source_codec: str,
    target_codec: str,
    target_char: str,
    normalize: bool,
    add_bom: bool,
    dry_run: bool,
) -> ConvertResult:
    from gedcom_tools.constants import MAX_FILE_SIZE_BYTES

    file_size = source_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        msg = (
            f"File is too large ({actual_mb:.1f} MB). "
            f"Maximum supported size is {limit_mb} MB."
        )
        raise ValueError(msg)

    raw = source_path.read_bytes()
    if len(raw) == 0:
        msg = f"File is empty: {source_path}"
        raise ValueError(msg)

    data, bom_encoding = strip_bom(raw)

    try:
        text = data.decode(source_codec)
    except UnicodeDecodeError as exc:
        msg = (
            f"Failed to decode {source_path} as {source_codec}. "
            "Try --from to specify the correct encoding."
        )
        raise ValueError(msg) from exc

    if normalize:
        text = unicodedata.normalize("NFC", text)

    text = update_char_header(text, target_char)

    lines_total, lines_over = count_long_lines(text, target_codec)

    try:
        encoded = text.encode(target_codec)
    except UnicodeEncodeError as exc:
        line_num = text[: exc.start].count("\n") + 1
        char = exc.object[exc.start]
        msg = (
            f"Cannot encode to {target_codec}: character '{char}' "
            f"(U+{ord(char):04X}) at line {line_num}. "
            "Consider UTF-8 as target."
        )
        raise ValueError(msg) from exc

    bom_added = add_bom
    if add_bom:
        encoded = BOMS[target_codec] + encoded

    if not dry_run:
        output_path.write_bytes(encoded)
        if sys.platform != "win32":
            try:
                os.chmod(output_path, 0o600)
            except OSError:
                pass

    return ConvertResult(
        source_file=source_path,
        output_file=output_path,
        source_encoding=CODEC_TO_CHAR.get(source_codec, source_codec),
        target_encoding=CODEC_TO_CHAR.get(target_codec, target_codec),
        source_codec=source_codec,
        target_codec=target_codec,
        lines_total=lines_total,
        lines_over_limit=lines_over,
        normalized=normalize,
        bom_added=bom_added,
        bom_stripped=bom_encoding,
        dry_run=dry_run,
    )
