from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from ged4py import GedcomReader

from gedcom_tools.commands.filter.models import GedcomLine, GedcomRecord
from gedcom_tools.commands.filter.parser import (
    build_xref_tag_map,
    collect_xrefs,
    count_records,
    detect_line_ending,
    group_records,
    has_head_and_trlr,
    is_pointer_value,
    parse_line,
    parse_lines,
)
from gedcom_tools.commands.filter.writer import serialize_records

# ---------------------------------------------------------------------------
# parse_line
# ---------------------------------------------------------------------------


class TestParseLine:
    def test_full_line_with_all_components(self) -> None:
        line = parse_line("0 @I1@ INDI", 1)
        assert line.level == 0
        assert line.xref == "@I1@"
        assert line.tag == "INDI"
        assert line.value is None
        assert line.raw == "0 @I1@ INDI"
        assert line.line_number == 1

    def test_line_with_value(self) -> None:
        line = parse_line("1 NAME John /Smith/", 5)
        assert line.level == 1
        assert line.xref is None
        assert line.tag == "NAME"
        assert line.value == "John /Smith/"

    def test_xref_line_with_value(self) -> None:
        line = parse_line("0 @N1@ NOTE This is a note", 3)
        assert line.xref == "@N1@"
        assert line.tag == "NOTE"
        assert line.value == "This is a note"

    def test_no_value_line(self) -> None:
        line = parse_line("1 BIRT", 10)
        assert line.level == 1
        assert line.tag == "BIRT"
        assert line.value is None
        assert line.xref is None

    def test_custom_tag_with_underscore(self) -> None:
        line = parse_line("1 _CUSTOM some data", 7)
        assert line.tag == "_CUSTOM"
        assert line.value == "some data"

    def test_blank_line_preserved(self) -> None:
        line = parse_line("", 2)
        assert line.tag == ""
        assert line.level == 0
        assert line.xref is None
        assert line.value is None
        assert line.raw == ""

    def test_malformed_line_preserved(self) -> None:
        line = parse_line("not a gedcom line", 4)
        assert line.tag == ""
        assert line.raw == "not a gedcom line"
        assert line.level == 0

    def test_multi_digit_level(self) -> None:
        line = parse_line("12 CONT continued text", 6)
        assert line.level == 12
        assert line.tag == "CONT"
        assert line.value == "continued text"

    def test_leading_zero_level_stripped(self) -> None:
        line = parse_line("01 NAME Test", 8)
        assert line.level == 1
        assert line.tag == "NAME"
        assert line.value == "Test"

    def test_xref_with_dot(self) -> None:
        line = parse_line("0 @I1.2@ INDI", 1)
        assert line.xref == "@I1.2@"
        assert line.tag == "INDI"

    def test_xref_with_hyphen(self) -> None:
        line = parse_line("0 @NOTE-42@ NOTE", 1)
        assert line.xref == "@NOTE-42@"
        assert line.tag == "NOTE"

    def test_multiple_spaces_as_delimiter(self) -> None:
        line = parse_line("0  @I1@  INDI", 1)
        assert line.level == 0
        assert line.xref == "@I1@"
        assert line.tag == "INDI"

    def test_tab_as_delimiter(self) -> None:
        line = parse_line("0\t@I1@\tINDI", 1)
        assert line.level == 0
        assert line.xref == "@I1@"
        assert line.tag == "INDI"

    def test_value_with_spaces(self) -> None:
        line = parse_line("2 ADDR 123 Main Street, Apt 4B", 1)
        assert line.value == "123 Main Street, Apt 4B"

    def test_head_record(self) -> None:
        line = parse_line("0 HEAD", 1)
        assert line.level == 0
        assert line.xref is None
        assert line.tag == "HEAD"
        assert line.value is None

    def test_trlr_record(self) -> None:
        line = parse_line("0 TRLR", 1)
        assert line.tag == "TRLR"
        assert line.level == 0

    def test_raw_preserves_original(self) -> None:
        raw = "2 CONT some  extra   spaces"
        line = parse_line(raw, 1)
        assert line.raw == raw


# ---------------------------------------------------------------------------
# parse_lines
# ---------------------------------------------------------------------------


class TestParseLines:
    def test_empty_text(self) -> None:
        assert parse_lines("") == []

    def test_head_only(self) -> None:
        lines = parse_lines("0 HEAD\n1 CHAR UTF-8\n")
        assert len(lines) == 2
        assert lines[0].tag == "HEAD"
        assert lines[1].tag == "CHAR"
        assert lines[1].value == "UTF-8"

    def test_multi_record_file(self) -> None:
        text = "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME John\n0 TRLR\n"
        lines = parse_lines(text)
        assert len(lines) == 5
        assert lines[0].tag == "HEAD"
        assert lines[2].xref == "@I1@"
        assert lines[4].tag == "TRLR"

    def test_crlf_no_trailing_cr(self) -> None:
        text = "0 HEAD\r\n1 CHAR UTF-8\r\n0 TRLR\r\n"
        lines = parse_lines(text)
        assert len(lines) == 3
        for line in lines:
            assert "\r" not in line.raw
            assert "\n" not in line.raw

    def test_lf_input(self) -> None:
        text = "0 HEAD\n0 TRLR\n"
        lines = parse_lines(text)
        assert len(lines) == 2
        assert lines[0].raw == "0 HEAD"

    def test_preserves_raw_text(self) -> None:
        text = "0 HEAD\n1 NOTE Something with  spaces\n0 TRLR\n"
        lines = parse_lines(text)
        assert lines[1].raw == "1 NOTE Something with  spaces"

    def test_non_ascii_content(self) -> None:
        text = "0 @I1@ INDI\n1 NAME Ren\u00e9 /Dupont/\n"
        lines = parse_lines(text)
        assert lines[1].value == "Ren\u00e9 /Dupont/"
        assert "Ren\u00e9" in lines[1].raw

    def test_nfd_decomposed_preserved(self) -> None:
        # ANSEL-decoded text comes in NFD (decomposed); parser must not alter it
        nfd_name = unicodedata.normalize("NFD", "Ren\u00e9")
        text = f"0 @I1@ INDI\n1 NAME {nfd_name} /Dupont/\n"
        lines = parse_lines(text)
        # raw preserves the decomposed form
        assert nfd_name in lines[1].raw
        assert lines[1].value == f"{nfd_name} /Dupont/"

    def test_line_numbers_sequential(self) -> None:
        text = "0 HEAD\n1 CHAR UTF-8\n0 TRLR\n"
        lines = parse_lines(text)
        assert [ln.line_number for ln in lines] == [1, 2, 3]


# ---------------------------------------------------------------------------
# group_records
# ---------------------------------------------------------------------------


class TestGroupRecords:
    def test_single_record(self) -> None:
        lines = parse_lines("0 HEAD\n1 CHAR UTF-8\n")
        records = group_records(lines)
        assert len(records) == 1
        assert records[0].tag == "HEAD"
        assert len(records[0].children) == 1
        assert records[0].children[0].tag == "CHAR"

    def test_multiple_records(self) -> None:
        text = "0 HEAD\n0 @I1@ INDI\n1 NAME John\n0 TRLR\n"
        lines = parse_lines(text)
        records = group_records(lines)
        assert len(records) == 3
        assert records[0].tag == "HEAD"
        assert records[1].tag == "INDI"
        assert records[1].xref == "@I1@"
        assert len(records[1].children) == 1
        assert records[2].tag == "TRLR"

    def test_head_and_trlr_grouped(self) -> None:
        text = "0 HEAD\n1 SOUR MyApp\n1 CHAR UTF-8\n0 TRLR\n"
        lines = parse_lines(text)
        records = group_records(lines)
        assert records[0].tag == "HEAD"
        assert len(records[0].children) == 2
        assert records[-1].tag == "TRLR"
        assert len(records[-1].children) == 0

    def test_nested_children_grouped(self) -> None:
        text = (
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "2 GIVN John\n"
            "2 SURN Smith\n"
            "1 BIRT\n"
            "2 DATE 1 JAN 1900\n"
            "2 PLAC London\n"
        )
        lines = parse_lines(text)
        records = group_records(lines)
        assert len(records) == 1
        assert len(records[0].children) == 6

    def test_blank_lines_between_records(self) -> None:
        # Blank lines become tag="" at level 0 but are not valid level-0
        # records (tag is empty), so they get attached as children
        text = "0 HEAD\n\n0 TRLR\n"
        lines = parse_lines(text)
        records = group_records(lines)
        # Blank line has tag="" so it doesn't start a new record;
        # it becomes a child of HEAD
        assert len(records) == 2
        assert records[0].tag == "HEAD"
        assert len(records[0].children) == 1  # the blank line
        assert records[1].tag == "TRLR"

    def test_empty_list(self) -> None:
        assert group_records([]) == []

    def test_orphan_before_first_level0(self) -> None:
        # A malformed line before any level-0 record
        lines = [
            GedcomLine(
                level=0, xref=None, tag="", value=None, raw="garbage", line_number=1
            ),
            GedcomLine(
                level=0, xref=None, tag="HEAD", value=None, raw="0 HEAD", line_number=2
            ),
        ]
        records = group_records(lines)
        # Orphan gets wrapped in its own record, then HEAD follows
        assert len(records) == 2
        assert records[0].tag == ""
        assert records[1].tag == "HEAD"


# ---------------------------------------------------------------------------
# detect_line_ending
# ---------------------------------------------------------------------------


class TestDetectLineEnding:
    def test_crlf_detected(self) -> None:
        assert detect_line_ending("0 HEAD\r\n0 TRLR\r\n") == "\r\n"

    def test_lf_detected(self) -> None:
        assert detect_line_ending("0 HEAD\n0 TRLR\n") == "\n"

    def test_mixed_defaults_to_crlf(self) -> None:
        # If \r\n is present at all, return \r\n
        assert detect_line_ending("0 HEAD\r\n0 TRLR\n") == "\r\n"

    def test_no_newlines_defaults_to_lf(self) -> None:
        assert detect_line_ending("0 HEAD") == "\n"

    def test_bare_cr_defaults_to_lf(self) -> None:
        # \r without \n is not CRLF
        assert detect_line_ending("0 HEAD\r0 TRLR\r") == "\n"


# ---------------------------------------------------------------------------
# count_records
# ---------------------------------------------------------------------------


class TestCountRecords:
    def _make_record(self, tag: str, xref: str | None = None) -> GedcomRecord:
        header = GedcomLine(
            level=0, xref=xref, tag=tag, value=None, raw=f"0 {tag}", line_number=1
        )
        return GedcomRecord(header=header, children=[])

    def test_counts_all_known_types(self) -> None:
        records = [
            self._make_record("INDI", "@I1@"),
            self._make_record("INDI", "@I2@"),
            self._make_record("FAM", "@F1@"),
            self._make_record("NOTE", "@N1@"),
            self._make_record("SOUR", "@S1@"),
            self._make_record("OBJE", "@O1@"),
            self._make_record("REPO", "@R1@"),
            self._make_record("SUBM", "@U1@"),
        ]
        counts = count_records(records)
        assert counts.indi == 2
        assert counts.fam == 1
        assert counts.note == 1
        assert counts.sour == 1
        assert counts.obje == 1
        assert counts.repo == 1
        assert counts.subm == 1
        assert counts.other == 0
        assert counts.total == 8

    def test_unknown_types_go_to_other(self) -> None:
        records = [
            self._make_record("HEAD"),
            self._make_record("TRLR"),
            self._make_record("SUBN"),
        ]
        counts = count_records(records)
        assert counts.other == 3
        assert counts.total == 3

    def test_empty_list(self) -> None:
        counts = count_records([])
        assert counts.total == 0

    def test_mixed_known_and_unknown(self) -> None:
        records = [
            self._make_record("HEAD"),
            self._make_record("INDI", "@I1@"),
            self._make_record("FAM", "@F1@"),
            self._make_record("TRLR"),
        ]
        counts = count_records(records)
        assert counts.indi == 1
        assert counts.fam == 1
        assert counts.other == 2


# ---------------------------------------------------------------------------
# collect_xrefs
# ---------------------------------------------------------------------------


class TestCollectXrefs:
    def _make_record(self, tag: str, xref: str | None = None) -> GedcomRecord:
        header = GedcomLine(
            level=0, xref=xref, tag=tag, value=None, raw=f"0 {tag}", line_number=1
        )
        return GedcomRecord(header=header, children=[])

    def test_collects_all_xrefs(self) -> None:
        records = [
            self._make_record("INDI", "@I1@"),
            self._make_record("FAM", "@F1@"),
            self._make_record("SOUR", "@S1@"),
        ]
        xrefs = collect_xrefs(records)
        assert xrefs == {"@I1@", "@F1@", "@S1@"}

    def test_skips_non_xref_records(self) -> None:
        records = [
            self._make_record("HEAD"),
            self._make_record("INDI", "@I1@"),
            self._make_record("TRLR"),
        ]
        xrefs = collect_xrefs(records)
        assert xrefs == {"@I1@"}

    def test_empty_records(self) -> None:
        assert collect_xrefs([]) == set()


# ---------------------------------------------------------------------------
# has_head_and_trlr
# ---------------------------------------------------------------------------


class TestHasHeadAndTrlr:
    def _make_record(self, tag: str) -> GedcomRecord:
        header = GedcomLine(
            level=0, xref=None, tag=tag, value=None, raw=f"0 {tag}", line_number=1
        )
        return GedcomRecord(header=header, children=[])

    def test_valid_file(self) -> None:
        records = [self._make_record("HEAD"), self._make_record("TRLR")]
        assert has_head_and_trlr(records) is True

    def test_missing_head(self) -> None:
        records = [self._make_record("TRLR")]
        assert has_head_and_trlr(records) is False

    def test_missing_trlr(self) -> None:
        records = [self._make_record("HEAD")]
        assert has_head_and_trlr(records) is False

    def test_empty(self) -> None:
        assert has_head_and_trlr([]) is False

    def test_with_other_records(self) -> None:
        records = [
            self._make_record("HEAD"),
            self._make_record("INDI"),
            self._make_record("TRLR"),
        ]
        assert has_head_and_trlr(records) is True


# ---------------------------------------------------------------------------
# build_xref_tag_map
# ---------------------------------------------------------------------------


class TestBuildXrefTagMap:
    def _make_record(self, tag: str, xref: str | None = None) -> GedcomRecord:
        header = GedcomLine(
            level=0, xref=xref, tag=tag, value=None, raw=f"0 {tag}", line_number=1
        )
        return GedcomRecord(header=header, children=[])

    def test_maps_xrefs_to_tags(self) -> None:
        records = [
            self._make_record("INDI", "@I1@"),
            self._make_record("FAM", "@F1@"),
            self._make_record("SOUR", "@S1@"),
        ]
        xref_map = build_xref_tag_map(records)
        assert xref_map == {"@I1@": "INDI", "@F1@": "FAM", "@S1@": "SOUR"}

    def test_skips_records_without_xrefs(self) -> None:
        records = [
            self._make_record("HEAD"),
            self._make_record("INDI", "@I1@"),
            self._make_record("TRLR"),
        ]
        xref_map = build_xref_tag_map(records)
        assert xref_map == {"@I1@": "INDI"}

    def test_empty(self) -> None:
        assert build_xref_tag_map([]) == {}


# ---------------------------------------------------------------------------
# is_pointer_value
# ---------------------------------------------------------------------------


class TestIsPointerValue:
    def test_simple_pointer(self) -> None:
        assert is_pointer_value("@I1@") is True

    def test_family_pointer(self) -> None:
        assert is_pointer_value("@F42@") is True

    def test_pointer_with_dot(self) -> None:
        assert is_pointer_value("@I1.2@") is True

    def test_plain_text(self) -> None:
        assert is_pointer_value("John Smith") is False

    def test_pointer_with_trailing_text(self) -> None:
        assert is_pointer_value("@I1@ some text") is False

    def test_none(self) -> None:
        assert is_pointer_value(None) is False

    def test_empty_string(self) -> None:
        assert is_pointer_value("") is False

    def test_whitespace_padded(self) -> None:
        assert is_pointer_value("  @I1@  ") is True

    def test_at_signs_only(self) -> None:
        # @@ has no content between the @ signs
        assert is_pointer_value("@@") is False

    def test_pointer_with_hyphen(self) -> None:
        assert is_pointer_value("@NOTE-42@") is True


# ---------------------------------------------------------------------------
# Line terminators: only CRLF/CR/LF may split a line
# ---------------------------------------------------------------------------

# Separators str.splitlines() breaks on but GEDCOM (and ged4py) do not.
NON_TERMINATORS = [
    pytest.param("\v", id="VT-000B"),
    pytest.param("\f", id="FF-000C"),
    pytest.param("\x1c", id="FS-001C"),
    pytest.param("\x1d", id="GS-001D"),
    pytest.param("\x1e", id="RS-001E"),
    pytest.param("\x85", id="NEL-0085"),
    pytest.param("\u2028", id="LS-2028"),
    pytest.param("\u2029", id="PS-2029"),
]

FIXTURES = Path(__file__).parent / "fixtures"


def _smuggling_ged(separator: str) -> str:
    """A file whose single NOTE value hides a forged level-0 INDI record."""
    return (
        "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
        "0 @I1@ INDI\n1 NAME John /Smith/\n"
        f"1 NOTE harmless{separator}0 @I99@ INDI{separator}1 NAME Smuggled /Record/\n"
        "0 TRLR\n"
    )


class TestLineTerminators:
    @pytest.mark.parametrize("separator", NON_TERMINATORS)
    def test_separator_stays_inside_value(self, separator: str) -> None:
        lines = parse_lines(f"1 NOTE before{separator}after\n")
        assert len(lines) == 1
        assert lines[0].tag == "NOTE"
        assert lines[0].value == f"before{separator}after"

    @pytest.mark.parametrize("separator", NON_TERMINATORS)
    def test_separator_cannot_forge_a_record(self, separator: str) -> None:
        records = group_records(parse_lines(_smuggling_ged(separator)))
        assert [r.xref for r in records if r.tag == "INDI"] == ["@I1@"]

    @pytest.mark.parametrize("separator", NON_TERMINATORS)
    def test_agrees_with_ged4py_record_count(
        self, tmp_path: Path, separator: str
    ) -> None:
        # The security invariant: what ged4py (and so `validate`) treats as a
        # value must not become structure to `filter`.
        ged = tmp_path / "smuggle.ged"
        ged.write_bytes(_smuggling_ged(separator).encode("utf-8"))

        with GedcomReader(str(ged)) as reader:
            reference = {i.xref_id for i in reader.records0("INDI")}

        records = group_records(parse_lines(ged.read_text(encoding="utf-8")))
        assert {r.xref for r in records if r.tag == "INDI"} == reference

    @pytest.mark.parametrize("terminator", ["\n", "\r\n", "\r"])
    def test_real_terminators_still_split(self, terminator: str) -> None:
        lines = parse_lines(f"0 HEAD{terminator}0 TRLR{terminator}")
        assert [ln.tag for ln in lines] == ["HEAD", "TRLR"]

    def test_no_trailing_blank_line(self) -> None:
        lines = parse_lines("0 HEAD\n0 TRLR\n")
        assert len(lines) == 2
        assert lines[-1].tag == "TRLR"

    def test_final_line_without_terminator_kept(self) -> None:
        lines = parse_lines("0 HEAD\n0 TRLR")
        assert [ln.tag for ln in lines] == ["HEAD", "TRLR"]

    def test_only_one_trailing_empty_dropped(self) -> None:
        # A genuine blank line before EOF is content and must survive
        lines = parse_lines("0 HEAD\n\n0 TRLR\n")
        assert [ln.raw for ln in lines] == ["0 HEAD", "", "0 TRLR"]


class TestSerializeRoundTrip:
    @pytest.mark.parametrize(
        "name", ["555sample.ged", "non_ascii_names.ged", "missing_trlr.ged"]
    )
    def test_fixture_roundtrip_is_byte_identical(self, name: str) -> None:
        text = (FIXTURES / name).read_text(encoding="utf-8")
        records = group_records(parse_lines(text))
        assert serialize_records(records, detect_line_ending(text)) == text

    @pytest.mark.parametrize("terminator", ["\n", "\r\n"])
    def test_roundtrip_preserves_trailing_terminator(self, terminator: str) -> None:
        text = terminator.join(["0 HEAD", "1 CHAR UTF-8", "0 TRLR", ""])
        records = group_records(parse_lines(text))
        assert serialize_records(records, detect_line_ending(text)) == text
