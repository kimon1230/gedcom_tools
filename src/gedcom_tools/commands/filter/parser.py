"""Line-level GEDCOM parser for the filter command.

Parses GEDCOM text into structured lines and records without ged4py,
preserving raw content for lossless round-trip output.
"""

from __future__ import annotations

import re

from gedcom_tools.commands.filter.models import GedcomLine, GedcomRecord, RecordCounts

__all__ = [
    "parse_line",
    "parse_lines",
    "group_records",
    "count_records",
    "collect_xrefs",
    "detect_line_ending",
    "build_xref_tag_map",
    "has_head_and_trlr",
    "is_pointer_value",
]

_LINE_RE = re.compile(
    r"^(\d{1,2})"  # level (1-2 digits, 0-99)
    r"\s+"  # delimiter
    r"(?:(@[^@]+@)"  # optional xref (any non-@ content between @s)
    r"\s+)?"  # delimiter after xref
    r"([A-Za-z0-9_]+)"  # tag
    r"(?:\s(.*))?$"  # optional value (rest of line)
)

_POINTER_RE = re.compile(r"^@[^@]+@$")

# Tags that map to named RecordCounts fields
_TAG_TO_FIELD = {
    "INDI": "indi",
    "FAM": "fam",
    "NOTE": "note",
    "SOUR": "sour",
    "OBJE": "obje",
    "REPO": "repo",
    "SUBM": "subm",
}


def parse_line(raw: str, line_number: int) -> GedcomLine:
    """Parse a single GEDCOM line into its components.

    Lines that don't match the expected format are preserved as-is with
    tag="" to avoid data loss during round-trip processing.
    """
    m = _LINE_RE.match(raw)
    if not m:
        return GedcomLine(
            level=0, xref=None, tag="", value=None, raw=raw, line_number=line_number
        )
    level = int(m.group(1))
    xref = m.group(2)
    tag = m.group(3)
    value = m.group(4)
    return GedcomLine(
        level=level, xref=xref, tag=tag, value=value, raw=raw, line_number=line_number
    )


def parse_lines(text: str) -> list[GedcomLine]:
    """Parse GEDCOM text into a list of GedcomLine objects.

    Splits on exactly the three GEDCOM line terminators: \\r\\n, \\r and \\n.
    str.splitlines() is deliberately NOT used -- it also breaks on VT, FF, FS,
    GS, RS, NEL, LS and PS, none of which terminate a line in GEDCOM. Treating
    those as terminators lets a value containing one be promoted to a top-level
    record on output, so a NOTE payload could smuggle in a forged INDI.
    Each GedcomLine.raw stores the content without trailing line endings.
    """
    pieces = re.split(r"\r\n|\r|\n", text)
    # re.split yields a trailing "" when text ends with a terminator (splitlines
    # does not). Left in, it serializes back out as a spurious blank line.
    if pieces and pieces[-1] == "":
        pieces.pop()
    return [parse_line(raw, i) for i, raw in enumerate(pieces, start=1)]


def group_records(lines: list[GedcomLine]) -> list[GedcomRecord]:
    """Group parsed lines into records by level-0 boundaries.

    Each level-0 line starts a new record. All subsequent lines with
    level > 0 become children of that record.
    """
    records: list[GedcomRecord] = []
    current: GedcomRecord | None = None

    for line in lines:
        if line.level == 0 and line.tag != "":
            if current is not None:
                records.append(current)
            current = GedcomRecord(header=line, children=[])
        elif current is not None:
            current.children.append(line)
        else:
            # Lines before the first level-0 record (orphaned); wrap individually
            records.append(GedcomRecord(header=line, children=[]))

    if current is not None:
        records.append(current)

    return records


def count_records(records: list[GedcomRecord]) -> RecordCounts:
    """Tally records by their level-0 tag."""
    counts = RecordCounts()
    for rec in records:
        field_name = _TAG_TO_FIELD.get(rec.tag)
        if field_name is not None:
            setattr(counts, field_name, getattr(counts, field_name) + 1)
        else:
            counts.other += 1
    return counts


def collect_xrefs(records: list[GedcomRecord]) -> set[str]:
    """Collect all defined xrefs from level-0 records."""
    return {rec.xref for rec in records if rec.xref is not None}


def detect_line_ending(text: str) -> str:
    r"""Detect whether text uses CRLF or LF line endings.

    Returns "\\r\\n" if CRLF is found anywhere in the text, else "\\n".
    """
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def build_xref_tag_map(records: list[GedcomRecord]) -> dict[str, str]:
    """Map each defined xref to its record's tag.

    Skips records without xrefs (HEAD, TRLR, etc.).
    """
    return {rec.xref: rec.tag for rec in records if rec.xref is not None}


def has_head_and_trlr(records: list[GedcomRecord]) -> bool:
    """Check that both HEAD and TRLR records exist."""
    tags = {rec.tag for rec in records}
    return "HEAD" in tags and "TRLR" in tags


def is_pointer_value(value: str | None) -> bool:
    """Check if a value is a GEDCOM pointer reference like @I1@.

    Returns True only when the entire stripped value matches the pointer
    pattern. None, empty strings, and values with extra text return False.
    """
    if value is None:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return _POINTER_RE.match(stripped) is not None
