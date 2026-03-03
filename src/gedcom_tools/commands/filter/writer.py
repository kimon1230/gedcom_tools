"""GEDCOM record writer and cleanup for the filter command.

Provides post-filter cleanup (dangling pointer removal, empty family
pruning) and serialization back to GEDCOM text.
"""

from __future__ import annotations

from gedcom_tools.commands.filter.models import GedcomLine, GedcomRecord
from gedcom_tools.commands.filter.parser import is_pointer_value


def clean_dangling_pointers(
    records: list[GedcomRecord], removed_xrefs: set[str]
) -> tuple[list[GedcomRecord], int]:
    """Remove lines whose pointer values reference removed xrefs.

    When a child line is removed, all subsequent children at a deeper level
    are also removed (skip-depth logic). The record header line is never
    checked -- level-0 headers are record definitions, not references.

    Returns a new list of records (originals are not mutated) and the total
    count of lines removed across all records.
    """
    if not removed_xrefs:
        return records, 0

    total_removed = 0
    cleaned: list[GedcomRecord] = []

    for rec in records:
        filtered_children: list[GedcomLine] = []
        skip_below: int | None = None
        removed_in_record = 0

        for child in rec.children:
            # If we're skipping children of a removed line, check depth
            if skip_below is not None:
                if child.level > skip_below:
                    removed_in_record += 1
                    continue
                # Reached same or lesser level -- stop skipping
                skip_below = None

            # Check if this line's value is a pointer to a removed xref
            if is_pointer_value(child.value) and child.value is not None:
                target = child.value.strip()
                if target in removed_xrefs:
                    skip_below = child.level
                    removed_in_record += 1
                    continue

            filtered_children.append(child)

        total_removed += removed_in_record
        cleaned.append(GedcomRecord(header=rec.header, children=filtered_children))

    return cleaned, total_removed


def remove_empty_families(
    records: list[GedcomRecord],
) -> tuple[list[GedcomRecord], set[str], int]:
    """Remove FAM records that have no HUSB, WIFE, or CHIL child lines.

    A family is considered empty when none of its children have a tag of
    HUSB, WIFE, or CHIL. Families with only event or note lines (MARR,
    NOTE, etc.) are still considered empty.

    Returns the filtered record list, set of removed FAM xrefs, and count
    of families removed.
    """
    _MEMBER_TAGS = {"HUSB", "WIFE", "CHIL"}

    kept: list[GedcomRecord] = []
    removed_xrefs: set[str] = set()
    removed_count = 0

    for rec in records:
        if rec.tag == "FAM":
            has_member = any(child.tag in _MEMBER_TAGS for child in rec.children)
            if not has_member:
                if rec.xref is not None:
                    removed_xrefs.add(rec.xref)
                removed_count += 1
                continue

        kept.append(rec)

    return kept, removed_xrefs, removed_count


def serialize_records(records: list[GedcomRecord], line_ending: str) -> str:
    """Serialize records back to GEDCOM text.

    Joins each record's header and child raw lines with the given line
    ending. The output ends with a trailing line ending for a faithful
    round-trip when no transforms were applied.
    """
    if not records:
        return ""

    all_lines: list[str] = []
    for rec in records:
        all_lines.append(rec.header.raw)
        for child in rec.children:
            all_lines.append(child.raw)

    return line_ending.join(all_lines) + line_ending
