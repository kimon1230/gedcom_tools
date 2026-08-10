"""Line-level GEDCOM parser for the filter command.

Parses GEDCOM text into structured lines and records without going through
ged4py's reader, preserving raw content for lossless round-trip output. The
line grammar itself is borrowed from ged4py so that the two agree on what a
record is; what is not borrowed is the reader's refusal to continue past a
malformed line, since `filter` is the tool you reach for on a messy file.
"""

from __future__ import annotations

import re

# _RE_GEDCOM_LINE is absent from ged4py.parser.__all__ but is the grammar
# GedcomReader lexes every line with -- deriving from it is the only way `filter`
# can be sure it sees exactly the records `validate` sees. A parallel hand-written
# pattern is what let crafted lines through in the first place. ged4py is pinned
# >=0.5.2,<0.6; a rename fails loudly here at import time.
from ged4py.parser import _RE_GEDCOM_LINE

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

# One grammar, not two. ged4py matches bytes; re.A restores that semantics for the
# decoded copy, without which \d would accept Unicode digits here and nowhere else.
# Flags are inherited rather than restated so an upstream flag change cannot drift.
_LINE_RE: re.Pattern[str] = re.compile(
    _RE_GEDCOM_LINE.pattern.decode("ascii"), _RE_GEDCOM_LINE.flags | re.A
)

# Exactly the characters bytes.lstrip() removes. str.lstrip() with no argument is a
# different operation -- it also eats NBSP, U+2000 and the C1 controls, none of which
# ged4py strips, so a line starting with one would parse here and not there.
_GED_LSTRIP = " \t\n\r\v\f"

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

    The match runs against ged4py's preprocessed form of the line, not the raw
    text: GedcomReader strips leading whitespace and trailing CR/LF before it
    lexes. ``raw`` itself stays untouched -- it is what gets written back out.
    """
    m = _LINE_RE.match(raw.lstrip(_GED_LSTRIP).rstrip("\r\n"))
    if not m:
        return GedcomLine(
            level=0, xref=None, tag="", value=None, raw=raw, line_number=line_number
        )
    try:
        level = int(m["level"])
    except ValueError:
        # The level group is unbounded \d+; CPython refuses int() past 4300 digits.
        return GedcomLine(
            level=0, xref=None, tag="", value=None, raw=raw, line_number=line_number
        )
    xref = m["xref"]
    tag = m["tag"]
    value = m["value"]
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
