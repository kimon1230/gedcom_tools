"""Tests for the filter command writer module."""

from __future__ import annotations

from gedcom_tools.commands.filter.models import GedcomLine, GedcomRecord
from gedcom_tools.commands.filter.parser import group_records, parse_lines
from gedcom_tools.commands.filter.writer import (
    clean_dangling_pointers,
    remove_empty_families,
    serialize_records,
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
# TestCleanDanglingPointers
# ---------------------------------------------------------------------------


class TestCleanDanglingPointers:
    def test_removes_pointer_to_removed_xref(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "NAME", "John /Doe/"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]
        assert count == 1

    def test_preserves_pointer_to_non_removed_xref(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S5@"),
                _line(1, "NOTE", "@N1@"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        assert len(result[0].children) == 2
        assert count == 0

    def test_preserves_non_pointer_lines(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "Jane /Doe/"),
                _line(1, "SEX", "F"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        assert len(result[0].children) == 2
        assert count == 0

    def test_skip_depth_removes_children_of_removed_line(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(2, "PAGE", "42"),
                _line(1, "NAME", "John /Doe/"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]
        assert count == 2

    def test_skip_depth_nested_children(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(2, "PAGE", "42"),
                _line(2, "DATA"),
                _line(3, "TEXT", "Citation text"),
                _line(1, "NAME", "John /Doe/"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]
        assert count == 4

    def test_noop_when_removed_xrefs_empty(self) -> None:
        recs = [
            _record(
                "INDI",
                xref="@I1@",
                children=[
                    _line(1, "SOUR", "@S1@"),
                ],
            ),
        ]
        result, count = clean_dangling_pointers(recs, set())
        assert result is recs
        assert count == 0

    def test_noop_when_no_pointers_match(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NOTE", "@N1@"),
                _line(1, "NAME", "Alice"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S99@"})
        assert len(result[0].children) == 2
        assert count == 0

    def test_record_with_no_children(self) -> None:
        rec = _record("HEAD")
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        assert len(result) == 1
        assert result[0].children == []
        assert count == 0

    def test_multiple_pointers_removed_in_same_record(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "NOTE", "@N1@"),
                _line(1, "NAME", "Bob"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@", "@N1@"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["NAME"]
        assert count == 2

    def test_pointer_at_level_2(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "BIRT"),
                _line(2, "SOUR", "@S1@"),
                _line(3, "PAGE", "10"),
                _line(2, "DATE", "1 JAN 1900"),
                _line(1, "NAME", "Eve"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["BIRT", "DATE", "NAME"]
        assert count == 2

    def test_xref_with_dot(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@I1.2@"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@I1.2@"})
        assert result[0].children == []
        assert count == 1

    def test_xref_with_hyphen(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NOTE", "@NOTE-42@"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@NOTE-42@"})
        assert result[0].children == []
        assert count == 1

    def test_count_matches_lines_removed(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(2, "PAGE", "42"),
                _line(2, "DATA"),
                _line(1, "SOUR", "@S2@"),
            ],
        )
        _, count = clean_dangling_pointers([rec], {"@S1@", "@S2@"})
        assert count == 4

    def test_returns_new_record_instances(self) -> None:
        original_children = [_line(1, "NAME", "John")]
        rec = _record("INDI", xref="@I1@", children=original_children)
        result, _ = clean_dangling_pointers([rec], {"@S1@"})
        # Result should be a new GedcomRecord, not the same object
        assert result[0] is not rec
        # Original children list unchanged
        assert len(rec.children) == 1

    def test_multiple_records_cleaned(self) -> None:
        rec1 = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "NAME", "Alice"),
            ],
        )
        rec2 = _record(
            "INDI",
            xref="@I2@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "NAME", "Bob"),
            ],
        )
        result, count = clean_dangling_pointers([rec1, rec2], {"@S1@"})
        assert [c.tag for c in result[0].children] == ["NAME"]
        assert [c.tag for c in result[1].children] == ["NAME"]
        assert count == 2

    def test_head_record_children_processed(self) -> None:
        """HEAD records should still have their children checked."""
        rec = _record(
            "HEAD",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(1, "GEDC"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        assert [c.tag for c in result[0].children] == ["GEDC"]
        assert count == 1

    def test_value_with_extra_text_not_treated_as_pointer(self) -> None:
        """Values like '@I1@ some text' are not standalone pointers."""
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NOTE", "@S1@ some text"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        assert len(result[0].children) == 1
        assert count == 0

    def test_skip_depth_stops_at_equal_level(self) -> None:
        """Lines at the same level as the removed line are NOT skipped."""
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "SOUR", "@S1@"),
                _line(2, "PAGE", "5"),
                _line(1, "SOUR", "@S2@"),  # same level, different pointer -- kept
                _line(2, "PAGE", "10"),
            ],
        )
        result, count = clean_dangling_pointers([rec], {"@S1@"})
        tags = [c.tag for c in result[0].children]
        assert tags == ["SOUR", "PAGE"]
        assert result[0].children[0].value == "@S2@"
        assert count == 2


# ---------------------------------------------------------------------------
# TestRemoveEmptyFamilies
# ---------------------------------------------------------------------------


class TestRemoveEmptyFamilies:
    def test_removes_fam_with_no_member_lines(self) -> None:
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "MARR"),
                _line(2, "DATE", "1 JAN 1900"),
            ],
        )
        result, removed, count = remove_empty_families([fam])
        assert len(result) == 0
        assert removed == {"@F1@"}
        assert count == 1

    def test_keeps_fam_with_husb(self) -> None:
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "HUSB", "@I1@"),
            ],
        )
        result, removed, count = remove_empty_families([fam])
        assert len(result) == 1
        assert removed == set()
        assert count == 0

    def test_keeps_fam_with_wife(self) -> None:
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "WIFE", "@I2@"),
            ],
        )
        result, removed, count = remove_empty_families([fam])
        assert len(result) == 1
        assert removed == set()
        assert count == 0

    def test_keeps_fam_with_chil(self) -> None:
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "CHIL", "@I3@"),
            ],
        )
        result, removed, count = remove_empty_families([fam])
        assert len(result) == 1
        assert removed == set()
        assert count == 0

    def test_returns_removed_xrefs(self) -> None:
        fam = _record("FAM", xref="@F5@")
        _, removed, _ = remove_empty_families([fam])
        assert "@F5@" in removed

    def test_count_matches_removed_families(self) -> None:
        fams = [
            _record("FAM", xref="@F1@"),
            _record("FAM", xref="@F2@"),
        ]
        _, _, count = remove_empty_families(fams)
        assert count == 2

    def test_non_fam_records_unaffected(self) -> None:
        indi = _record("INDI", xref="@I1@")
        head = _record("HEAD")
        result, _, count = remove_empty_families([indi, head])
        assert len(result) == 2
        assert count == 0

    def test_fam_with_only_event_lines_is_empty(self) -> None:
        fam = _record(
            "FAM",
            xref="@F1@",
            children=[
                _line(1, "MARR"),
                _line(1, "DIV"),
                _line(1, "NOTE", "@N1@"),
            ],
        )
        result, _, count = remove_empty_families([fam])
        assert len(result) == 0
        assert count == 1

    def test_multiple_empty_fams_removed(self) -> None:
        fams = [
            _record("FAM", xref="@F1@"),
            _record("INDI", xref="@I1@"),
            _record("FAM", xref="@F2@"),
            _record("FAM", xref="@F3@", children=[_line(1, "HUSB", "@I1@")]),
        ]
        result, removed, count = remove_empty_families(fams)
        assert len(result) == 2  # INDI + non-empty FAM
        assert removed == {"@F1@", "@F2@"}
        assert count == 2

    def test_fam_without_xref_still_removed(self) -> None:
        """FAM without xref is unusual but still removed if empty."""
        fam = _record("FAM")
        result, removed, count = remove_empty_families([fam])
        assert len(result) == 0
        assert removed == set()  # no xref to add
        assert count == 1


# ---------------------------------------------------------------------------
# TestSerializeRecords
# ---------------------------------------------------------------------------


class TestSerializeRecords:
    def test_roundtrip_lf(self) -> None:
        text = "0 HEAD\n1 SOUR Test\n0 @I1@ INDI\n1 NAME John /Doe/\n0 TRLR\n"
        lines = parse_lines(text)
        records = group_records(lines)
        output = serialize_records(records, "\n")
        assert output == text

    def test_roundtrip_crlf(self) -> None:
        text = "0 HEAD\r\n1 SOUR Test\r\n0 @I1@ INDI\r\n1 NAME John /Doe/\r\n0 TRLR\r\n"
        lines = parse_lines(text)
        records = group_records(lines)
        output = serialize_records(records, "\r\n")
        assert output == text

    def test_empty_records_list(self) -> None:
        assert serialize_records([], "\n") == ""

    def test_single_record_no_children(self) -> None:
        rec = _record("TRLR")
        output = serialize_records([rec], "\n")
        assert output == "0 TRLR\n"

    def test_non_ascii_roundtrip(self) -> None:
        text = "0 HEAD\n0 @I1@ INDI\n1 NAME Ren\u00e9 /Descartes/\n0 TRLR\n"
        lines = parse_lines(text)
        records = group_records(lines)
        output = serialize_records(records, "\n")
        assert output == text

    def test_trailing_line_ending_present(self) -> None:
        rec = _record("HEAD")
        output = serialize_records([rec], "\n")
        assert output.endswith("\n")

    def test_multiple_children_joined(self) -> None:
        rec = _record(
            "INDI",
            xref="@I1@",
            children=[
                _line(1, "NAME", "Alice"),
                _line(1, "SEX", "F"),
            ],
        )
        output = serialize_records([rec], "\n")
        expected_lines = ["0 @I1@ INDI", "1 NAME Alice", "1 SEX F", ""]
        assert output == "\n".join(expected_lines)
