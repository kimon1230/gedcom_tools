"""Tests for the filter command transforms module."""

from __future__ import annotations

import pytest

from gedcom_tools.commands.filter.models import (
    FilterSpec,
    GedcomLine,
    GedcomRecord,
)
from gedcom_tools.commands.filter.transforms import (
    _strip_custom_lines,
    _strip_lines_by_tag,
    _strip_records_by_tag,
    apply_strip_transforms,
)


def _line(
    level: int, tag: str, value: str | None = None, xref: str | None = None
) -> GedcomLine:
    """Build a GedcomLine with a synthetic raw string."""
    parts = [str(level)]
    if xref is not None:
        parts.append(xref)
    parts.append(tag)
    if value is not None:
        parts.append(value)
    raw = " ".join(parts)
    return GedcomLine(
        level=level, xref=xref, tag=tag, value=value, raw=raw, line_number=0
    )


def _record(
    tag: str,
    xref: str | None = None,
    children: list[GedcomLine] | None = None,
) -> GedcomRecord:
    """Build a GedcomRecord with a synthetic header."""
    header = _line(0, tag, xref=xref)
    return GedcomRecord(header=header, children=children or [])


# ---------------------------------------------------------------------------
# TestStripCustomLines
# ---------------------------------------------------------------------------


class TestStripCustomLines:
    def test_removes_custom_tag_at_level_1(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "John /Doe/"),
                _line(1, "_CUSTOM", "some value"),
                _line(1, "SEX", "M"),
            ],
        )
        result = _strip_custom_lines([rec])
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME", "SEX"]

    def test_removes_custom_tag_at_level_2(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "BIRT"),
                _line(2, "_MYFACT", "custom data"),
                _line(2, "DATE", "1 JAN 1900"),
                _line(1, "NAME", "Alice"),
            ],
        )
        result = _strip_custom_lines([rec])
        tags = [c.tag for c in result[0].children]
        assert tags == ["BIRT", "DATE", "NAME"]

    def test_removes_children_of_custom_tag(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "_APID"),
                _line(2, "DATA", "ancestry data"),
                _line(3, "TEXT", "details"),
                _line(1, "NAME", "Bob"),
            ],
        )
        result = _strip_custom_lines([rec])
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]

    def test_preserves_standard_tags(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "Jane /Smith/"),
                _line(2, "GIVN", "Jane"),
                _line(2, "SURN", "Smith"),
                _line(1, "BIRT"),
                _line(2, "DATE", "15 MAR 1985"),
            ],
        )
        result = _strip_custom_lines([rec])
        assert len(result[0].children) == 5

    def test_noop_on_clean_file(self) -> None:
        rec = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
                _line(1, "WIFE", "@I2@"),
                _line(1, "CHIL", "@I3@"),
            ],
        )
        result = _strip_custom_lines([rec])
        assert len(result[0].children) == 3

    def test_multiple_custom_tags_in_one_record(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "_UID", "abc123"),
                _line(1, "NAME", "Eve"),
                _line(1, "_FREL", "Natural"),
                _line(1, "SEX", "F"),
                _line(1, "_MREL", "Natural"),
            ],
        )
        result = _strip_custom_lines([rec])
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME", "SEX"]

    def test_does_not_mutate_original(self) -> None:
        original_children = [
            _line(1, "_CUSTOM", "value"),
            _line(1, "NAME", "Test"),
        ]
        rec = _record("INDI", xref="@I1@", children=original_children)
        result = _strip_custom_lines([rec])
        assert result[0] is not rec
        assert len(rec.children) == 2
        assert len(result[0].children) == 1

    def test_nested_custom_tag_under_standard_tag(self) -> None:
        """Custom tag nested under a standard event should be removed."""
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "BIRT"),
                _line(2, "DATE", "1 JAN 1900"),
                _line(2, "_PRIM", "Y"),
                _line(3, "_DETAIL", "extra"),
                _line(2, "PLAC", "London"),
            ],
        )
        result = _strip_custom_lines([rec])
        tags = [c.tag for c in result[0].children]
        assert tags == ["BIRT", "DATE", "PLAC"]

    def test_custom_tag_at_end_of_children(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "Last"),
                _line(1, "_TAIL"),
            ],
        )
        result = _strip_custom_lines([rec])
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]

    def test_empty_children_list(self) -> None:
        rec = _record("INDI", xref="@I1@")
        result = _strip_custom_lines([rec])
        assert result[0].children == []

    def test_multiple_records_processed(self) -> None:
        rec1 = _record(
            "INDI",
            xref="@I1@",
            children=[_line(1, "_UID", "abc"), _line(1, "NAME", "A")],
        )
        rec2 = _record(
            "INDI",
            xref="@I2@",
            children=[_line(1, "NAME", "B"), _line(1, "_FACT", "x")],
        )
        result = _strip_custom_lines([rec1, rec2])
        assert [c.tag for c in result[0].children] == ["NAME"]
        assert [c.tag for c in result[1].children] == ["NAME"]


# ---------------------------------------------------------------------------
# TestStripRecordsByTag
# ---------------------------------------------------------------------------


class TestStripRecordsByTag:
    def test_removes_note_records(self) -> None:
        records = [
            _record("INDI", xref="@I1@"),
            _record("NOTE", xref="@N1@"),
            _record("NOTE", xref="@N2@"),
            _record("TRLR"),
        ]
        result, removed = _strip_records_by_tag(records, {"NOTE"})
        tags = [r.tag for r in result]
        assert tags == ["INDI", "TRLR"]
        assert removed == {"@N1@", "@N2@"}

    def test_removes_sour_records(self) -> None:
        records = [
            _record("HEAD"),
            _record("SOUR", xref="@S1@"),
            _record("INDI", xref="@I1@"),
        ]
        result, removed = _strip_records_by_tag(records, {"SOUR"})
        tags = [r.tag for r in result]
        assert tags == ["HEAD", "INDI"]
        assert removed == {"@S1@"}

    def test_removes_obje_records(self) -> None:
        records = [
            _record("OBJE", xref="@O1@"),
            _record("INDI", xref="@I1@"),
        ]
        result, removed = _strip_records_by_tag(records, {"OBJE"})
        assert len(result) == 1
        assert result[0].tag == "INDI"
        assert removed == {"@O1@"}

    def test_preserves_other_records(self) -> None:
        records = [
            _record("HEAD"),
            _record("INDI", xref="@I1@"),
            _record("FAM", xref="@F1@"),
            _record("TRLR"),
        ]
        result, removed = _strip_records_by_tag(records, {"NOTE", "SOUR"})
        assert len(result) == 4
        assert removed == set()

    def test_returns_correct_removed_xrefs(self) -> None:
        records = [
            _record("SOUR", xref="@S1@"),
            _record("SOUR", xref="@S2@"),
            _record("NOTE", xref="@N1@"),
        ]
        _, removed = _strip_records_by_tag(records, {"SOUR", "NOTE"})
        assert removed == {"@S1@", "@S2@", "@N1@"}

    def test_handles_records_without_xrefs(self) -> None:
        """A NOTE without an xref is still removed but doesn't add to xrefs."""
        records = [
            _record("HEAD"),
            _record("NOTE"),  # inline note, no xref
            _record("TRLR"),
        ]
        result, removed = _strip_records_by_tag(records, {"NOTE"})
        tags = [r.tag for r in result]
        assert tags == ["HEAD", "TRLR"]
        assert removed == set()

    def test_empty_tags_set_is_noop(self) -> None:
        records = [_record("INDI", xref="@I1@"), _record("NOTE", xref="@N1@")]
        result, removed = _strip_records_by_tag(records, set())
        assert len(result) == 2
        assert removed == set()

    def test_empty_records_list(self) -> None:
        result, removed = _strip_records_by_tag([], {"NOTE"})
        assert result == []
        assert removed == set()

    def test_multiple_tags_stripped(self) -> None:
        records = [
            _record("HEAD"),
            _record("NOTE", xref="@N1@"),
            _record("SOUR", xref="@S1@"),
            _record("OBJE", xref="@O1@"),
            _record("INDI", xref="@I1@"),
            _record("TRLR"),
        ]
        result, removed = _strip_records_by_tag(records, {"NOTE", "SOUR", "OBJE"})
        tags = [r.tag for r in result]
        assert tags == ["HEAD", "INDI", "TRLR"]
        assert removed == {"@N1@", "@S1@", "@O1@"}


# ---------------------------------------------------------------------------
# TestStripLinesByTag
# ---------------------------------------------------------------------------


class TestStripLinesByTag:
    def test_removes_note_sub_tags_in_indi(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "John /Doe/"),
                _line(1, "NOTE", "@N1@"),
                _line(1, "SEX", "M"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"NOTE"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME", "SEX"]

    def test_removes_sour_sub_tags_in_events(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "BIRT"),
                _line(2, "DATE", "1 JAN 1900"),
                _line(2, "SOUR", "@S1@"),
                _line(1, "NAME", "Alice"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"SOUR"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["BIRT", "DATE", "NAME"]

    def test_removes_children_of_stripped_sub_tag(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(2, "PAGE", "42"),
                _line(2, "DATA"),
                _line(3, "TEXT", "Citation text"),
                _line(1, "NAME", "Bob"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"SOUR"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]

    def test_noop_when_tag_not_present(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "Jane"),
                _line(1, "SEX", "F"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"SOUR"})
        assert len(result[0].children) == 2

    def test_removes_obje_sub_tags(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "Eve"),
                _line(1, "OBJE", "@O1@"),
                _line(2, "FILE", "photo.jpg"),
                _line(1, "BIRT"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"OBJE"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME", "BIRT"]

    def test_multiple_tags_stripped(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NOTE", "@N1@"),
                _line(1, "SOUR", "@S1@"),
                _line(1, "NAME", "Test"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"NOTE", "SOUR"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]

    def test_skip_depth_stops_at_equal_level(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NOTE", "inline note"),
                _line(2, "CONT", "continuation"),
                _line(1, "NAME", "After"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"NOTE"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]

    def test_does_not_mutate_original(self) -> None:
        original_children = [
            _line(1, "NOTE", "@N1@"),
            _line(1, "NAME", "Test"),
        ]
        rec = _record("INDI", xref="@I1@", children=original_children)
        result = _strip_lines_by_tag([rec], {"NOTE"})
        assert result[0] is not rec
        assert len(rec.children) == 2
        assert len(result[0].children) == 1

    def test_multiple_records_processed(self) -> None:
        rec1 = _record(
            "INDI",
            xref="@I1@",
            children=[_line(1, "NOTE", "@N1@"), _line(1, "NAME", "A")],
        )
        rec2 = _record(
            "FAM",
            xref="@F1@",
            children=[_line(1, "NOTE", "@N2@"), _line(1, "HUSB", "@I1@")],
        )
        result = _strip_lines_by_tag([rec1, rec2], {"NOTE"})
        assert [c.tag for c in result[0].children] == ["NAME"]
        assert [c.tag for c in result[1].children] == ["HUSB"]

    def test_empty_children(self) -> None:
        rec = _record("INDI", xref="@I1@")
        result = _strip_lines_by_tag([rec], {"NOTE"})
        assert result[0].children == []

    def test_deeply_nested_removal(self) -> None:
        """Tag match at level 2 removes level 3 and 4 children."""
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "BIRT"),
                _line(2, "SOUR", "@S1@"),
                _line(3, "PAGE", "10"),
                _line(4, "QUAY", "3"),
                _line(2, "DATE", "1900"),
                _line(1, "NAME", "Deep"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"SOUR"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["BIRT", "DATE", "NAME"]

    def test_consecutive_matching_tags(self) -> None:
        """Multiple adjacent lines with the target tag are all removed."""
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "SOUR", "@S2@"),
                _line(1, "NAME", "End"),
            ],
        )
        result = _strip_lines_by_tag([rec], {"SOUR"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]


# ---------------------------------------------------------------------------
# TestApplyStripTransforms
# ---------------------------------------------------------------------------


class TestApplyStripTransforms:
    def test_empty_spec_is_noop(self) -> None:
        records = [
            _record("HEAD"),
            _record("NOTE", xref="@N1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[_line(1, "_CUSTOM"), _line(1, "SOUR", "@S1@")],
            ),
            _record("TRLR"),
        ]
        spec = FilterSpec()
        result, removed = apply_strip_transforms(records, spec)
        assert len(result) == 4
        assert removed == set()
        # Children untouched
        assert len(result[2].children) == 2

    def test_strip_notes_removes_records_and_lines(self) -> None:
        records = [
            _record("HEAD"),
            _record("NOTE", xref="@N1@", children=[_line(1, "CONT", "text")]),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "NAME", "John"),
                    _line(1, "NOTE", "@N1@"),
                    _line(1, "SEX", "M"),
                ],
            ),
            _record("TRLR"),
        ]
        spec = FilterSpec(strip_notes=True)
        result, removed = apply_strip_transforms(records, spec)
        # NOTE record removed
        tags = [r.tag for r in result]
        assert "NOTE" not in tags
        assert removed == {"@N1@"}
        # Inline NOTE line removed from INDI
        indi = next(r for r in result if r.tag == "INDI")
        child_tags = [c.tag for c in indi.children]
        assert "NOTE" not in child_tags
        assert child_tags == ["NAME", "SEX"]

    def test_strip_sources_removes_records_and_lines(self) -> None:
        records = [
            _record("SOUR", xref="@S1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "SOUR", "@S1@"),
                    _line(2, "PAGE", "5"),
                    _line(1, "NAME", "Alice"),
                ],
            ),
        ]
        spec = FilterSpec(strip_sources=True)
        result, removed = apply_strip_transforms(records, spec)
        assert removed == {"@S1@"}
        indi = result[0]
        assert [c.tag for c in indi.children] == ["NAME"]

    def test_strip_multimedia_removes_records_and_lines(self) -> None:
        records = [
            _record("OBJE", xref="@O1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "OBJE", "@O1@"),
                    _line(2, "FILE", "photo.jpg"),
                    _line(1, "NAME", "Bob"),
                ],
            ),
        ]
        spec = FilterSpec(strip_multimedia=True)
        result, removed = apply_strip_transforms(records, spec)
        assert removed == {"@O1@"}
        indi = result[0]
        assert [c.tag for c in indi.children] == ["NAME"]

    def test_multiple_flags_combined(self) -> None:
        records = [
            _record("HEAD"),
            _record("NOTE", xref="@N1@"),
            _record("SOUR", xref="@S1@"),
            _record("OBJE", xref="@O1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "_CUSTOM", "data"),
                    _line(1, "NOTE", "@N1@"),
                    _line(1, "SOUR", "@S1@"),
                    _line(1, "OBJE", "@O1@"),
                    _line(1, "NAME", "All Stripped"),
                ],
            ),
            _record("TRLR"),
        ]
        spec = FilterSpec(
            strip_custom_tags=True,
            strip_notes=True,
            strip_sources=True,
            strip_multimedia=True,
        )
        result, removed = apply_strip_transforms(records, spec)
        # NOTE, SOUR, OBJE records removed
        result_tags = [r.tag for r in result]
        assert result_tags == ["HEAD", "INDI", "TRLR"]
        assert removed == {"@N1@", "@S1@", "@O1@"}
        # INDI has only NAME left
        indi = next(r for r in result if r.tag == "INDI")
        assert [c.tag for c in indi.children] == ["NAME"]

    def test_strip_tag_with_custom_tag_name(self) -> None:
        records = [
            _record("HEAD"),
            _record("REPO", xref="@R1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "NAME", "Jane"),
                    _line(1, "REPO", "@R1@"),
                ],
            ),
            _record("TRLR"),
        ]
        spec = FilterSpec(strip_tags=["REPO"])
        result, removed = apply_strip_transforms(records, spec)
        result_tags = [r.tag for r in result]
        assert "REPO" not in result_tags
        assert removed == {"@R1@"}
        indi = next(r for r in result if r.tag == "INDI")
        assert [c.tag for c in indi.children] == ["NAME"]

    def test_strip_tag_case_insensitive(self) -> None:
        """User-provided tag names should be uppercased."""
        records = [
            _record("NOTE", xref="@N1@"),
            _record("INDI", xref="@I1@"),
        ]
        spec = FilterSpec(strip_tags=["note"])
        result, removed = apply_strip_transforms(records, spec)
        assert removed == {"@N1@"}
        assert len(result) == 1

    def test_strip_custom_tags_only(self) -> None:
        records = [
            _record("NOTE", xref="@N1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "_UID", "12345"),
                    _line(1, "NAME", "Test"),
                    _line(1, "NOTE", "@N1@"),
                ],
            ),
        ]
        spec = FilterSpec(strip_custom_tags=True)
        result, removed = apply_strip_transforms(records, spec)
        # NOTE record still present (only custom tags stripped)
        assert len(result) == 2
        assert removed == set()
        indi = next(r for r in result if r.tag == "INDI")
        child_tags = [c.tag for c in indi.children]
        assert "_UID" not in child_tags
        # NOTE inline tag preserved (strip_notes is False)
        assert "NOTE" in child_tags

    def test_strip_tags_multiple(self) -> None:
        """Multiple --strip-tag values should all be processed."""
        records = [
            _record("REPO", xref="@R1@"),
            _record("SUBM", xref="@U1@"),
            _record("INDI", xref="@I1@"),
        ]
        spec = FilterSpec(strip_tags=["REPO", "SUBM"])
        result, removed = apply_strip_transforms(records, spec)
        assert len(result) == 1
        assert removed == {"@R1@", "@U1@"}


# ---------------------------------------------------------------------------
# TestStripTagStructural
# ---------------------------------------------------------------------------


class TestStripTagStructural:
    def test_strip_chil_leaves_husb_wife(self) -> None:
        """--strip-tag CHIL removes children but keeps spouses."""
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
                _line(1, "WIFE", "@I2@"),
                _line(1, "CHIL", "@I3@"),
                _line(1, "CHIL", "@I4@"),
                _line(1, "MARR"),
                _line(2, "DATE", "1 JUN 1990"),
            ],
        )
        spec = FilterSpec(strip_tags=["CHIL"])
        result, _ = apply_strip_transforms([fam], spec)
        child_tags = [c.tag for c in result[0].children]
        assert "CHIL" not in child_tags
        assert "HUSB" in child_tags
        assert "WIFE" in child_tags
        assert "MARR" in child_tags

    def test_strip_all_member_tags_empties_fam(self) -> None:
        """Stripping HUSB, WIFE, CHIL empties FAMs (but doesn't remove them)."""
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
                _line(1, "WIFE", "@I2@"),
                _line(1, "CHIL", "@I3@"),
                _line(1, "MARR"),
                _line(2, "DATE", "1 JAN 2000"),
            ],
        )
        spec = FilterSpec(strip_tags=["HUSB", "WIFE", "CHIL"])
        result, _ = apply_strip_transforms([fam], spec)
        # FAM record itself is NOT removed by transforms
        assert len(result) == 1
        assert result[0].tag == "FAM"
        child_tags = [c.tag for c in result[0].children]
        assert "HUSB" not in child_tags
        assert "WIFE" not in child_tags
        assert "CHIL" not in child_tags
        # Non-member tags remain
        assert "MARR" in child_tags

    def test_strip_tag_removes_top_level_records_too(self) -> None:
        """--strip-tag should remove matching top-level records as well."""
        records = [
            _record("HEAD"),
            _record("FAM", xref="@F1@", children=[_line(1, "HUSB", "@I1@")]),
            _record("FAM", xref="@F2@", children=[_line(1, "WIFE", "@I2@")]),
            _record("TRLR"),
        ]
        spec = FilterSpec(strip_tags=["FAM"])
        result, removed = apply_strip_transforms(records, spec)
        result_tags = [r.tag for r in result]
        assert "FAM" not in result_tags
        assert removed == {"@F1@", "@F2@"}

    def test_strip_tag_with_children_of_stripped_line(self) -> None:
        """Children under a stripped inline tag should also be removed."""
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "BIRT"),
                _line(2, "DATE", "1 JAN 1900"),
                _line(2, "PLAC", "London"),
                _line(3, "MAP"),
                _line(4, "LATI", "N51.5"),
                _line(4, "LONG", "W0.1"),
                _line(1, "NAME", "Test"),
            ],
        )
        spec = FilterSpec(strip_tags=["PLAC"])
        result, _ = apply_strip_transforms([rec], spec)
        child_tags = [c.tag for c in result[0].children]
        assert child_tags == ["BIRT", "DATE", "NAME"]

    def test_emptied_fam_not_removed_by_transforms(self) -> None:
        """Transforms should NOT call remove_empty_families -- that's writer's job."""
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
            ],
        )
        spec = FilterSpec(strip_tags=["HUSB"])
        result, _ = apply_strip_transforms([fam], spec)
        # FAM still present with no members
        assert len(result) == 1
        assert result[0].tag == "FAM"
        assert result[0].children == []

    def test_strip_tag_combined_with_strip_notes(self) -> None:
        """--strip-notes and --strip-tag can coexist."""
        records = [
            _record("NOTE", xref="@N1@"),
            _record("REPO", xref="@R1@"),
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "NOTE", "inline note"),
                    _line(1, "NAME", "Test"),
                ],
            ),
        ]
        spec = FilterSpec(strip_notes=True, strip_tags=["REPO"])
        result, removed = apply_strip_transforms(records, spec)
        assert removed == {"@N1@", "@R1@"}
        indi = next(r for r in result if r.tag == "INDI")
        assert [c.tag for c in indi.children] == ["NAME"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestTransformsEdgeCases:
    def test_strip_lines_preserves_header(self) -> None:
        """_strip_lines_by_tag should never remove the record header."""
        rec = _record(
            "NOTE",
            xref="@N1@",
            children=[_line(1, "CONT", "text")],
        )
        result = _strip_lines_by_tag([rec], {"NOTE"})
        # Header is NOTE but it's a level-0 record header, not a sub-line
        assert result[0].tag == "NOTE"
        assert result[0].xref == "@N1@"
        # But CONT is not NOTE, so it stays
        assert len(result[0].children) == 1

    def test_empty_records_list(self) -> None:
        spec = FilterSpec(
            strip_custom_tags=True,
            strip_notes=True,
            strip_sources=True,
            strip_multimedia=True,
        )
        result, removed = apply_strip_transforms([], spec)
        assert result == []
        assert removed == set()

    def test_strip_custom_lines_preserves_record_header_with_underscore(self) -> None:
        """A record-level tag starting with _ is kept by _strip_custom_lines
        since it only processes children, not headers."""
        rec = _record(
            "_CUSTOM_REC",
            xref="@X1@",
            children=[_line(1, "DATA", "value")],
        )
        result = _strip_custom_lines([rec])
        assert result[0].tag == "_CUSTOM_REC"
        assert len(result[0].children) == 1

    def test_ordering_custom_before_line_strip(self) -> None:
        """Custom tag stripping happens before line-level stripping.
        Verify that a custom tag inside a NOTE subtree is handled correctly:
        if strip_notes is on, the NOTE line is removed along with its children
        (including any custom tags underneath).
        """
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NOTE", "A note"),
                _line(2, "_CUSTOM", "inside note"),
                _line(1, "NAME", "Test"),
            ],
        )
        spec = FilterSpec(strip_custom_tags=True, strip_notes=True)
        result, _ = apply_strip_transforms([rec], spec)
        indi = result[0]
        assert [c.tag for c in indi.children] == ["NAME"]

    def test_strip_tag_does_not_affect_head_trlr(self) -> None:
        """HEAD and TRLR survive strip_tags, even when named explicitly.

        Stripping an unrelated tag must leave them alone, and asking for
        them by name is refused rather than honoured.
        """
        records = [
            _record("HEAD"),
            _record("INDI", xref="@I1@"),
            _record("TRLR"),
        ]
        spec = FilterSpec(strip_tags=["INDI"])
        result, removed = apply_strip_transforms(records, spec)
        result_tags = [r.tag for r in result]
        assert "HEAD" in result_tags
        assert "TRLR" in result_tags
        assert "INDI" not in result_tags
        assert removed == {"@I1@"}

        explicit = FilterSpec(strip_tags=["HEAD", "TRLR"])
        result, removed = apply_strip_transforms(records, explicit)
        assert [r.tag for r in result] == ["HEAD", "INDI", "TRLR"]
        assert removed == set()


# ---------------------------------------------------------------------------
# TestStripTagStructuralGuard
# ---------------------------------------------------------------------------


class TestStripTagStructuralGuard:
    def test_trlr_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        records = [_record("HEAD"), _record("INDI", xref="@I1@"), _record("TRLR")]
        result, removed = apply_strip_transforms(
            records, FilterSpec(strip_tags=["TRLR"])
        )
        assert [r.tag for r in result] == ["HEAD", "INDI", "TRLR"]
        assert removed == set()
        assert "TRLR" in capsys.readouterr().err

    def test_head_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        records = [_record("HEAD"), _record("INDI", xref="@I1@"), _record("TRLR")]
        result, removed = apply_strip_transforms(
            records, FilterSpec(strip_tags=["HEAD"])
        )
        assert [r.tag for r in result] == ["HEAD", "INDI", "TRLR"]
        assert removed == set()
        assert "HEAD" in capsys.readouterr().err

    def test_lowercase_trlr_is_refused(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The guard runs after case normalization, so --strip-tag trlr is caught."""
        records = [_record("HEAD"), _record("TRLR")]
        result, _ = apply_strip_transforms(records, FilterSpec(strip_tags=["trlr"]))
        assert [r.tag for r in result] == ["HEAD", "TRLR"]
        assert "TRLR" in capsys.readouterr().err

    def test_subm_is_still_strippable(self, capsys: pytest.CaptureFixture[str]) -> None:
        """SUBM is data, not structure. Stripping it is a supported privacy step."""
        records = [
            _record("HEAD"),
            _record("SUBM", xref="@SUBM1@", children=[_line(1, "NAME", "Me")]),
            _record("INDI", xref="@I1@"),
            _record("TRLR"),
        ]
        result, removed = apply_strip_transforms(
            records, FilterSpec(strip_tags=["SUBM"])
        )
        assert [r.tag for r in result] == ["HEAD", "INDI", "TRLR"]
        assert removed == {"@SUBM1@"}
        assert capsys.readouterr().err == ""

    def test_mixed_tags_strips_the_safe_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = [
            _record("HEAD"),
            _record("INDI", xref="@I1@", children=[_line(1, "NOTE", "inline")]),
            _record("NOTE", xref="@N1@"),
            _record("TRLR"),
        ]
        result, removed = apply_strip_transforms(
            records, FilterSpec(strip_tags=["TRLR", "NOTE"])
        )
        assert [r.tag for r in result] == ["HEAD", "INDI", "TRLR"]
        assert removed == {"@N1@"}
        indi = next(r for r in result if r.tag == "INDI")
        assert indi.children == []
        err = capsys.readouterr().err
        assert "TRLR" in err
        assert "NOTE" not in err

    def test_warning_names_both_ignored_tags(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = [_record("HEAD"), _record("TRLR")]
        apply_strip_transforms(records, FilterSpec(strip_tags=["TRLR", "HEAD"]))
        err = capsys.readouterr().err
        assert "HEAD, TRLR" in err

    def test_no_warning_when_nothing_ignored(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = [_record("HEAD"), _record("INDI", xref="@I1@"), _record("TRLR")]
        apply_strip_transforms(records, FilterSpec(strip_tags=["INDI"]))
        assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Subtree extraction tests
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from gedcom_tools.commands.filter.transforms import (  # noqa: E402
    _collect_dependent_xrefs,
    _family_has_kept_member,
    extract_subtree,
)
from gedcom_tools.graph import ParentChildGraph  # noqa: E402


def _make_graph(
    parents_of: dict[str, list[str]] | None = None,
    children_of: dict[str, list[str]] | None = None,
    couples: dict[str, set[str]] | None = None,
) -> ParentChildGraph:
    return ParentChildGraph(
        parents_of=parents_of or {},
        children_of=children_of or {},
        couples=couples or {},
    )


def _indi(xref: str, children: list[GedcomLine] | None = None) -> GedcomRecord:
    """Shortcut for building an INDI record."""
    return _record("INDI", xref=xref, children=children)


def _fam(xref: str, children: list[GedcomLine] | None = None) -> GedcomRecord:
    """Shortcut for building a FAM record."""
    return _record("FAM", xref=xref, children=children)


# ---------------------------------------------------------------------------
# TestFamilyHasKeptMember
# ---------------------------------------------------------------------------


class TestFamilyHasKeptMember:
    def test_true_when_husb_is_kept(self) -> None:
        fam = _fam(
            "@F1@", children=[_line(1, "HUSB", "@I1@"), _line(1, "WIFE", "@I2@")]
        )
        assert _family_has_kept_member(fam, {"@I1@"}) is True

    def test_true_when_wife_is_kept(self) -> None:
        fam = _fam(
            "@F1@", children=[_line(1, "HUSB", "@I1@"), _line(1, "WIFE", "@I2@")]
        )
        assert _family_has_kept_member(fam, {"@I2@"}) is True

    def test_true_when_chil_is_kept(self) -> None:
        fam = _fam(
            "@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
                _line(1, "WIFE", "@I2@"),
                _line(1, "CHIL", "@I3@"),
            ],
        )
        assert _family_has_kept_member(fam, {"@I3@"}) is True

    def test_false_when_no_members_kept(self) -> None:
        fam = _fam(
            "@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
                _line(1, "WIFE", "@I2@"),
                _line(1, "CHIL", "@I3@"),
            ],
        )
        assert _family_has_kept_member(fam, {"@I99@"}) is False

    def test_false_when_no_husb_wife_chil(self) -> None:
        fam = _fam(
            "@F1@",
            children=[
                _line(1, "MARR"),
                _line(2, "DATE", "1 JAN 2000"),
            ],
        )
        assert _family_has_kept_member(fam, {"@I1@"}) is False


# ---------------------------------------------------------------------------
# TestCollectDependentXrefs
# ---------------------------------------------------------------------------


class TestCollectDependentXrefs:
    def test_collects_sour_referenced_by_indi(self) -> None:
        indi = _indi("@I1@", children=[_line(1, "SOUR", "@S1@")])
        sour = _record("SOUR", xref="@S1@")
        xref_to_tag = {"@I1@": "INDI", "@S1@": "SOUR"}
        result = _collect_dependent_xrefs([indi, sour], {"@I1@"}, xref_to_tag)
        assert "@S1@" in result

    def test_collects_note_referenced_by_indi(self) -> None:
        indi = _indi("@I1@", children=[_line(1, "NOTE", "@N1@")])
        note = _record("NOTE", xref="@N1@")
        xref_to_tag = {"@I1@": "INDI", "@N1@": "NOTE"}
        result = _collect_dependent_xrefs([indi, note], {"@I1@"}, xref_to_tag)
        assert "@N1@" in result

    def test_collects_obje_referenced_by_indi(self) -> None:
        indi = _indi("@I1@", children=[_line(1, "OBJE", "@O1@")])
        obje = _record("OBJE", xref="@O1@")
        xref_to_tag = {"@I1@": "INDI", "@O1@": "OBJE"}
        result = _collect_dependent_xrefs([indi, obje], {"@I1@"}, xref_to_tag)
        assert "@O1@" in result

    def test_collects_repo_via_sour_transitively(self) -> None:
        """SOUR references REPO; both should be collected."""
        indi = _indi("@I1@", children=[_line(1, "SOUR", "@S1@")])
        sour = _record("SOUR", xref="@S1@", children=[_line(1, "REPO", "@R1@")])
        repo = _record("REPO", xref="@R1@")
        xref_to_tag = {"@I1@": "INDI", "@S1@": "SOUR", "@R1@": "REPO"}
        result = _collect_dependent_xrefs([indi, sour, repo], {"@I1@"}, xref_to_tag)
        assert "@S1@" in result
        assert "@R1@" in result

    def test_does_not_collect_indi_references(self) -> None:
        """Pointers to INDI records should not be collected as dependents."""
        fam = _fam("@F1@", children=[_line(1, "HUSB", "@I2@")])
        indi2 = _indi("@I2@")
        xref_to_tag = {"@F1@": "FAM", "@I2@": "INDI"}
        result = _collect_dependent_xrefs([fam, indi2], {"@F1@"}, xref_to_tag)
        assert "@I2@" not in result

    def test_returns_empty_when_no_dependents(self) -> None:
        indi = _indi("@I1@", children=[_line(1, "NAME", "John /Doe/")])
        xref_to_tag = {"@I1@": "INDI"}
        result = _collect_dependent_xrefs([indi], {"@I1@"}, xref_to_tag)
        assert result == set()

    def test_non_pointer_values_are_skipped(self) -> None:
        """Values that aren't pointer patterns should be ignored."""
        indi = _indi(
            "@I1@",
            children=[
                _line(1, "NAME", "John /Doe/"),
                _line(1, "NOTE", "This is an inline note"),
            ],
        )
        xref_to_tag = {"@I1@": "INDI"}
        result = _collect_dependent_xrefs([indi], {"@I1@"}, xref_to_tag)
        assert result == set()

    def test_kept_xref_not_in_records_is_skipped(self) -> None:
        """If kept_xrefs contains an xref with no matching record, skip it."""
        indi = _indi("@I1@", children=[_line(1, "SOUR", "@S1@")])
        sour = _record("SOUR", xref="@S1@")
        xref_to_tag = {"@I1@": "INDI", "@S1@": "SOUR"}
        # "@I_GHOST@" is in kept_xrefs but not in records
        result = _collect_dependent_xrefs(
            [indi, sour], {"@I1@", "@I_GHOST@"}, xref_to_tag
        )
        assert "@S1@" in result

    def test_duplicate_pointer_references_deduplicated(self) -> None:
        """Multiple records pointing to the same SOUR only collect it once."""
        indi1 = _indi("@I1@", children=[_line(1, "SOUR", "@S1@")])
        indi2 = _indi("@I2@", children=[_line(1, "SOUR", "@S1@")])
        sour = _record("SOUR", xref="@S1@")
        xref_to_tag = {"@I1@": "INDI", "@I2@": "INDI", "@S1@": "SOUR"}
        result = _collect_dependent_xrefs(
            [indi1, indi2, sour], {"@I1@", "@I2@"}, xref_to_tag
        )
        assert result == {"@S1@"}


# ---------------------------------------------------------------------------
# TestExtractSubtree
# ---------------------------------------------------------------------------


class TestExtractSubtree:
    """Tests for extract_subtree. Uses mocked build_parent_child_graph."""

    _PATCH_TARGET = "gedcom_tools.commands.filter.transforms.build_parent_child_graph"

    def _base_records(self) -> list[GedcomRecord]:
        """HEAD + TRLR wrapper records for all tests."""
        return [_record("HEAD"), _record("TRLR")]

    def test_single_individual_root_only(self) -> None:
        """Extracting just the root with depth 0 keeps only root + structural."""
        head, trlr = _record("HEAD"), _record("TRLR")
        indi1 = _indi("@I1@")
        indi2 = _indi("@I2@")
        records = [head, indi1, indi2, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, False
            )

        kept_tags_xrefs = [(r.tag, r.xref) for r in kept]
        assert ("HEAD", None) in kept_tags_xrefs
        assert ("TRLR", None) in kept_tags_xrefs
        assert ("INDI", "@I1@") in kept_tags_xrefs
        assert ("INDI", "@I2@") not in kept_tags_xrefs
        assert removed == {"@I2@"}

    def test_ancestors_depth_1_gets_parents(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        child = _indi("@I1@")
        parent1 = _indi("@I2@")
        parent2 = _indi("@I3@")
        grandparent = _indi("@I4@")
        records = [head, child, parent1, parent2, grandparent, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                parents_of={
                    "@I1@": ["@I2@", "@I3@"],
                    "@I2@": ["@I4@"],
                },
                children_of={
                    "@I2@": ["@I1@"],
                    "@I3@": ["@I1@"],
                    "@I4@": ["@I2@"],
                },
            )
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 1, 0, False
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@I1@" in kept_xrefs
        assert "@I2@" in kept_xrefs
        assert "@I3@" in kept_xrefs
        # Grandparent is depth 2, should NOT be included
        assert "@I4@" not in kept_xrefs
        assert "@I4@" in removed

    def test_ancestors_depth_2_gets_grandparents(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        child = _indi("@I1@")
        parent = _indi("@I2@")
        grandparent = _indi("@I3@")
        records = [head, child, parent, grandparent, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                parents_of={"@I1@": ["@I2@"], "@I2@": ["@I3@"]},
                children_of={"@I2@": ["@I1@"], "@I3@": ["@I2@"]},
            )
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I1@", 2, 0, False)

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert {"@I1@", "@I2@", "@I3@"} == kept_xrefs

    def test_ancestors_unlimited_gets_all(self) -> None:
        """ancestor_depth=None means unlimited."""
        head, trlr = _record("HEAD"), _record("TRLR")
        i1, i2, i3, i4 = _indi("@I1@"), _indi("@I2@"), _indi("@I3@"), _indi("@I4@")
        records = [head, i1, i2, i3, i4, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                parents_of={
                    "@I1@": ["@I2@"],
                    "@I2@": ["@I3@"],
                    "@I3@": ["@I4@"],
                },
                children_of={
                    "@I2@": ["@I1@"],
                    "@I3@": ["@I2@"],
                    "@I4@": ["@I3@"],
                },
            )
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", None, 0, False
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert kept_xrefs == {"@I1@", "@I2@", "@I3@", "@I4@"}
        assert removed == set()

    def test_ancestors_zero_skips_ancestors(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        child = _indi("@I1@")
        parent = _indi("@I2@")
        records = [head, child, parent, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                parents_of={"@I1@": ["@I2@"]},
                children_of={"@I2@": ["@I1@"]},
            )
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, False
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@I1@" in kept_xrefs
        assert "@I2@" not in kept_xrefs
        assert "@I2@" in removed

    def test_descendants_depth_1_gets_children(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        parent = _indi("@I1@")
        child = _indi("@I2@")
        grandchild = _indi("@I3@")
        records = [head, parent, child, grandchild, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                children_of={"@I1@": ["@I2@"], "@I2@": ["@I3@"]},
                parents_of={"@I2@": ["@I1@"], "@I3@": ["@I2@"]},
            )
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 1, False
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@I1@" in kept_xrefs
        assert "@I2@" in kept_xrefs
        assert "@I3@" not in kept_xrefs
        assert "@I3@" in removed

    def test_descendants_depth_2_gets_grandchildren(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        i1, i2, i3 = _indi("@I1@"), _indi("@I2@"), _indi("@I3@")
        records = [head, i1, i2, i3, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                children_of={"@I1@": ["@I2@"], "@I2@": ["@I3@"]},
                parents_of={"@I2@": ["@I1@"], "@I3@": ["@I2@"]},
            )
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I1@", 0, 2, False)

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert kept_xrefs == {"@I1@", "@I2@", "@I3@"}

    def test_both_ancestors_and_descendants(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        grandparent = _indi("@I1@")
        parent = _indi("@I2@")
        root = _indi("@I3@")
        child = _indi("@I4@")
        records = [head, grandparent, parent, root, child, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                parents_of={"@I3@": ["@I2@"], "@I2@": ["@I1@"]},
                children_of={"@I1@": ["@I2@"], "@I2@": ["@I3@"], "@I3@": ["@I4@"]},
            )
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I3@", 2, 1, False)

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert kept_xrefs == {"@I1@", "@I2@", "@I3@", "@I4@"}

    def test_include_spouses(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        root = _indi("@I1@")
        spouse = _indi("@I2@")
        unrelated = _indi("@I3@")
        records = [head, root, spouse, unrelated, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                couples={"@I1@": {"@I2@"}, "@I2@": {"@I1@"}},
            )
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, True
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@I1@" in kept_xrefs
        assert "@I2@" in kept_xrefs
        assert "@I3@" not in kept_xrefs
        assert "@I3@" in removed

    def test_fam_records_for_kept_individuals_included(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi("@I1@")
        i2 = _indi("@I2@")
        fam = _fam(
            "@F1@",
            children=[_line(1, "HUSB", "@I1@"), _line(1, "WIFE", "@I2@")],
        )
        records = [head, i1, i2, fam, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                couples={"@I1@": {"@I2@"}, "@I2@": {"@I1@"}},
            )
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I1@", 0, 0, True)

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@F1@" in kept_xrefs

    def test_fam_records_for_removed_individuals_excluded(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi("@I1@")
        i2 = _indi("@I2@")
        i3 = _indi("@I3@")
        fam_kept = _fam("@F1@", children=[_line(1, "HUSB", "@I1@")])
        fam_removed = _fam(
            "@F2@",
            children=[_line(1, "HUSB", "@I2@"), _line(1, "WIFE", "@I3@")],
        )
        records = [head, i1, i2, i3, fam_kept, fam_removed, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, False
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@F1@" in kept_xrefs
        assert "@F2@" not in kept_xrefs
        assert "@F2@" in removed

    def test_head_and_trlr_always_kept(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi("@I1@")
        records = [head, i1, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I1@", 0, 0, False)

        kept_tags = [r.tag for r in kept]
        assert "HEAD" in kept_tags
        assert "TRLR" in kept_tags

    def test_subm_always_kept(self) -> None:
        head = _record("HEAD")
        subm = _record("SUBM", xref="@U1@")
        i1 = _indi("@I1@")
        trlr = _record("TRLR")
        records = [head, subm, i1, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, False
            )

        kept_tags = [r.tag for r in kept]
        assert "SUBM" in kept_tags
        # SUBM should NOT appear in removed even though it's not in the keep set
        assert "@U1@" not in removed

    def test_non_xref_records_preserved(self) -> None:
        """Records with no xref (rare structural records) should be kept."""
        head = _record("HEAD")
        mystery = _record("_WEIRD")  # no xref
        i1 = _indi("@I1@")
        trlr = _record("TRLR")
        records = [head, mystery, i1, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I1@", 0, 0, False)

        # mystery has no xref, so it should be preserved
        assert any(r.tag == "_WEIRD" for r in kept)

    def test_invalid_root_raises_valueerror(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi("@I1@")
        records = [head, i1, trlr]

        import pytest

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            with pytest.raises(ValueError, match="Individual @I99@ not found"):
                extract_subtree(records, Path("fake.ged"), "@I99@", 0, 0, False)

    def test_root_with_no_relatives_in_graph(self) -> None:
        """Individual exists but has no family connections."""
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi("@I1@")
        i2 = _indi("@I2@")
        records = [head, i1, i2, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", None, 5, True
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert kept_xrefs == {"@I1@"}
        assert removed == {"@I2@"}

    def test_dependent_sour_note_obje_included(self) -> None:
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi(
            "@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "NOTE", "@N1@"),
                _line(1, "OBJE", "@O1@"),
            ],
        )
        sour = _record("SOUR", xref="@S1@")
        note = _record("NOTE", xref="@N1@")
        obje = _record("OBJE", xref="@O1@")
        records = [head, i1, sour, note, obje, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, _ = extract_subtree(records, Path("fake.ged"), "@I1@", 0, 0, False)

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@S1@" in kept_xrefs
        assert "@N1@" in kept_xrefs
        assert "@O1@" in kept_xrefs

    def test_transitive_sour_to_repo_chain(self) -> None:
        """SOUR referencing REPO: both should be kept."""
        head, trlr = _record("HEAD"), _record("TRLR")
        i1 = _indi("@I1@", children=[_line(1, "SOUR", "@S1@")])
        sour = _record("SOUR", xref="@S1@", children=[_line(1, "REPO", "@R1@")])
        repo = _record("REPO", xref="@R1@")
        unrelated_sour = _record("SOUR", xref="@S99@")
        records = [head, i1, sour, repo, unrelated_sour, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph()
            kept, removed = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, False
            )

        kept_xrefs = {r.xref for r in kept if r.xref}
        assert "@S1@" in kept_xrefs
        assert "@R1@" in kept_xrefs
        assert "@S99@" not in kept_xrefs
        assert "@S99@" in removed

    def test_fam_kept_after_spouse_addition(self) -> None:
        """A FAM that connects a kept individual's spouse should be included.

        Without include_spouses, the FAM would be excluded because the spouse
        is not in the keep set. With include_spouses, the spouse is added first,
        then FAM membership is checked, so the FAM should be included.
        """
        head, trlr = _record("HEAD"), _record("TRLR")
        root = _indi("@I1@")
        spouse = _indi("@I2@")
        # FAM has HUSB=root, WIFE=spouse, and a child @I3@ who is NOT in the tree
        child_of_couple = _indi("@I3@")
        fam = _fam(
            "@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
                _line(1, "WIFE", "@I2@"),
                _line(1, "CHIL", "@I3@"),
            ],
        )
        # Separate FAM with only the spouse — missed without spouse addition
        fam_spouse_only = _fam(
            "@F2@",
            children=[_line(1, "WIFE", "@I2@")],
        )
        records = [head, root, spouse, child_of_couple, fam, fam_spouse_only, trlr]

        with patch(self._PATCH_TARGET) as mock_graph:
            mock_graph.return_value = _make_graph(
                couples={"@I1@": {"@I2@"}, "@I2@": {"@I1@"}},
            )
            # Without spouses: @F2@ should NOT be kept
            kept_no_spouse, _ = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, False
            )
            no_spouse_xrefs = {r.xref for r in kept_no_spouse if r.xref}
            assert "@F2@" not in no_spouse_xrefs

            # With spouses: @F2@ SHOULD be kept (spouse is now in keep set)
            kept_with_spouse, _ = extract_subtree(
                records, Path("fake.ged"), "@I1@", 0, 0, True
            )
            with_spouse_xrefs = {r.xref for r in kept_with_spouse if r.xref}
            assert "@F2@" in with_spouse_xrefs
