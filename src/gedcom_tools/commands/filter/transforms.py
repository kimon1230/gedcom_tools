"""Transform operations for the filter command.

Applies strip operations to GEDCOM records: removing top-level records
by tag, removing sub-lines by tag (with skip-depth for children),
stripping custom (underscore-prefixed) tags at any level, and
extracting subtrees rooted at a specific individual.
"""

from __future__ import annotations

import sys
from pathlib import Path

from gedcom_tools.commands.filter.models import (
    UNLIMITED_DEPTH,
    FilterSpec,
    GedcomLine,
    GedcomRecord,
)
from gedcom_tools.commands.filter.parser import (
    build_xref_tag_map,
    collect_xrefs,
    is_pointer_value,
)
from gedcom_tools.graph import (
    build_parent_child_graph,
    find_ancestors,
    find_descendants,
)

# Tags whose removal would leave the output structurally invalid. These are
# silently dropped from user-supplied --strip-tag values. Note that SUBM is
# deliberately absent: stripping the submitter record is a legitimate privacy
# operation and must keep working.
_UNSTRIPPABLE_TAGS = frozenset({"HEAD", "TRLR"})


def apply_strip_transforms(
    records: list[GedcomRecord], spec: FilterSpec
) -> tuple[list[GedcomRecord], set[str]]:
    """Apply all strip operations defined in the filter spec.

    Returns filtered records and the set of xrefs removed at the
    record level (needed for downstream dangling-pointer cleanup).
    """
    all_removed_xrefs: set[str] = set()

    # Collect tags for record-level and line-level stripping
    record_tags: set[str] = set()
    line_tags: set[str] = set()

    if spec.strip_notes:
        record_tags.add("NOTE")
        line_tags.add("NOTE")
    if spec.strip_sources:
        record_tags.add("SOUR")
        line_tags.add("SOUR")
    if spec.strip_multimedia:
        record_tags.add("OBJE")
        line_tags.add("OBJE")

    # 1. Record-level strips (remove entire NOTE/SOUR/OBJE records)
    if record_tags:
        records, removed = _strip_records_by_tag(records, record_tags)
        all_removed_xrefs.update(removed)

    # 2. Custom line strips
    if spec.strip_custom_tags:
        records = _strip_custom_lines(records)

    # 3. Line-level strips (remove inline NOTE/SOUR/OBJE sub-tags)
    if line_tags:
        records = _strip_lines_by_tag(records, line_tags)

    # 4. Strip-tag (user-specified tags, both record and line level)
    if spec.strip_tags:
        user_tags = {t.upper() for t in spec.strip_tags}
        ignored = user_tags & _UNSTRIPPABLE_TAGS
        if ignored:
            names = ", ".join(sorted(ignored))
            print(
                f"Warning: Ignoring --strip-tag {names}: removing "
                "these tags would produce an invalid GEDCOM file.",
                file=sys.stderr,
            )
            user_tags -= ignored
        if user_tags:
            records, removed = _strip_records_by_tag(records, user_tags)
            all_removed_xrefs.update(removed)
            records = _strip_lines_by_tag(records, user_tags)

    return records, all_removed_xrefs


def _strip_records_by_tag(
    records: list[GedcomRecord], tags: set[str]
) -> tuple[list[GedcomRecord], set[str]]:
    """Remove level-0 records whose tag is in the given set.

    Returns the filtered record list and the set of xrefs that were
    removed (for dangling-pointer cleanup downstream).
    """
    kept: list[GedcomRecord] = []
    removed_xrefs: set[str] = set()

    for rec in records:
        if rec.tag in tags:
            if rec.xref is not None:
                removed_xrefs.add(rec.xref)
            continue
        kept.append(rec)

    return kept, removed_xrefs


def _strip_lines_by_tag(
    records: list[GedcomRecord], tags: set[str]
) -> list[GedcomRecord]:
    """Remove sub-lines (level 1+) whose tag matches, including children.

    Uses skip-depth logic: when a line at level N is removed, all
    subsequent lines at level > N are also skipped until reaching a
    line at level <= N. Does not mutate the original records.
    """
    result: list[GedcomRecord] = []

    for rec in records:
        filtered_children: list[GedcomLine] = []
        skip_below: int | None = None

        for child in rec.children:
            if skip_below is not None:
                if child.level > skip_below:
                    continue
                skip_below = None

            if child.tag in tags:
                skip_below = child.level
                continue

            filtered_children.append(child)

        result.append(GedcomRecord(header=rec.header, children=filtered_children))

    return result


def _strip_custom_lines(records: list[GedcomRecord]) -> list[GedcomRecord]:
    """Remove lines whose tag starts with ``_`` at any level, including children.

    Uses the same skip-depth logic as ``_strip_lines_by_tag``: when a
    custom tag at level N is removed, all subsequent lines at level > N
    are also skipped. Does not mutate the original records.
    """
    result: list[GedcomRecord] = []

    for rec in records:
        filtered_children: list[GedcomLine] = []
        skip_below: int | None = None

        for child in rec.children:
            if skip_below is not None:
                if child.level > skip_below:
                    continue
                skip_below = None

            if child.tag.startswith("_"):
                skip_below = child.level
                continue

            filtered_children.append(child)

        result.append(GedcomRecord(header=rec.header, children=filtered_children))

    return result


# ---------------------------------------------------------------------------
# Subtree extraction
# ---------------------------------------------------------------------------


# Tags that are always preserved regardless of keep set
_STRUCTURAL_TAGS = frozenset({"HEAD", "TRLR", "SUBM"})

# Record types eligible for transitive dependency collection
_DEPENDENT_TAGS = frozenset({"SOUR", "NOTE", "OBJE", "REPO"})


def _family_has_kept_member(record: GedcomRecord, kept_xrefs: set[str]) -> bool:
    """Check if a FAM record has any HUSB, WIFE, or CHIL in the keep set."""
    for child in record.children:
        if child.tag in ("HUSB", "WIFE", "CHIL"):
            if is_pointer_value(child.value) and child.value is not None:
                stripped = child.value.strip()
                if stripped in kept_xrefs:
                    return True
    return False


def _collect_dependent_xrefs(
    records: list[GedcomRecord],
    kept_xrefs: set[str],
    xref_to_tag: dict[str, str],
) -> set[str]:
    """Transitively collect SOUR/NOTE/OBJE/REPO xrefs referenced by kept records.

    Scans children of records whose xref is in kept_xrefs. For each
    pointer value pointing to a SOUR/NOTE/OBJE/REPO record (checked via
    xref_to_tag), adds it to the result set. Repeats until no new xrefs
    are discovered, ensuring chains like SOUR -> REPO are preserved.
    """
    # Build lookup for fast record access by xref
    rec_by_xref: dict[str, GedcomRecord] = {}
    for rec in records:
        if rec.xref is not None:
            rec_by_xref[rec.xref] = rec

    collected: set[str] = set()
    # Seed: scan all currently-kept records
    to_scan: set[str] = set(kept_xrefs)
    scanned: set[str] = set()

    while to_scan:
        current_xref = to_scan.pop()
        scanned.add(current_xref)

        current_rec = rec_by_xref.get(current_xref)
        if current_rec is None:
            continue

        for child in current_rec.children:
            if not is_pointer_value(child.value) or child.value is None:
                continue
            target = child.value.strip()
            target_tag = xref_to_tag.get(target)
            if target_tag not in _DEPENDENT_TAGS:
                continue
            if target in collected:
                continue
            collected.add(target)
            if target not in scanned:
                to_scan.add(target)

    return collected


def extract_subtree(
    records: list[GedcomRecord],
    file_path: Path,
    root_xref: str,
    ancestor_depth: int | None,
    descendant_depth: int,
    include_spouses: bool,
) -> tuple[list[GedcomRecord], set[str]]:
    """Extract a subtree centered on an individual.

    Keeps the root individual plus ancestors (up to ancestor_depth),
    descendants (up to descendant_depth), optionally their spouses,
    related FAM records, and transitively referenced SOUR/NOTE/OBJE/REPO
    records. HEAD, TRLR, and SUBM records are always preserved.

    Returns the filtered record list and the set of removed xrefs.
    """
    graph = build_parent_child_graph(file_path)

    all_xrefs = collect_xrefs(records)
    if root_xref not in all_xrefs:
        raise ValueError(f"Individual {root_xref} not found in file")

    # Build the individual keep set
    keep: set[str] = {root_xref}

    # Ancestors
    resolved_ancestor_depth = (
        UNLIMITED_DEPTH if ancestor_depth is None else ancestor_depth
    )
    if resolved_ancestor_depth > 0:
        keep |= find_ancestors(graph, root_xref, resolved_ancestor_depth)

    # Descendants
    if descendant_depth > 0:
        keep |= find_descendants(graph, root_xref, descendant_depth)

    # Spouses of all kept individuals
    if include_spouses:
        spouse_xrefs: set[str] = set()
        for xref in keep:
            spouse_xrefs |= graph.couples.get(xref, set())
        keep |= spouse_xrefs

    # FAM records: keep any where HUSB, WIFE, or CHIL is in the keep set
    xref_to_tag = build_xref_tag_map(records)
    fam_keep: set[str] = set()
    for rec in records:
        if rec.tag == "FAM" and rec.xref is not None:
            if _family_has_kept_member(rec, keep):
                fam_keep.add(rec.xref)

    full_keep = keep | fam_keep

    # Transitive dependent records (SOUR/NOTE/OBJE/REPO chains)
    dependents = _collect_dependent_xrefs(records, full_keep, xref_to_tag)
    full_keep |= dependents

    # Filter records
    kept_records: list[GedcomRecord] = []
    removed_xrefs: set[str] = set()

    for rec in records:
        if rec.tag in _STRUCTURAL_TAGS:
            kept_records.append(rec)
        elif rec.xref is None:
            # Non-xref structural records (rare, but preserve them)
            kept_records.append(rec)
        elif rec.xref in full_keep:
            kept_records.append(rec)
        else:
            removed_xrefs.add(rec.xref)

    return kept_records, removed_xrefs
