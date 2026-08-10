from __future__ import annotations

import itertools
import random
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pytest
from ged4py import GedcomReader

# Deliberately the real private symbol, not a copy: hand-inlining this pattern is
# how three earlier attempts at the parity fix shipped a gate that agreed with the
# bug. Under the ged4py>=0.5.2,<0.6 pin a rename should break this test loudly.
from ged4py.parser import _RE_GEDCOM_LINE

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

    def test_internal_tab_is_not_a_delimiter(self) -> None:
        # ged4py's delimiters are literal spaces, so a tab between fields makes
        # the line unparseable there. `filter` used to accept it, which meant a
        # tab-separated line was a record here and not to `validate`.
        line = parse_line("0\t@I1@\tINDI", 1)
        assert line.tag == ""
        assert line.raw == "0\t@I1@\tINDI"

    def test_leading_tab_still_parses(self) -> None:
        # A *leading* tab is stripped before matching, exactly as ged4py does.
        line = parse_line("\t0 @I6@ INDI", 1)
        assert line.level == 0
        assert line.xref == "@I6@"
        assert line.tag == "INDI"
        assert line.raw == "\t0 @I6@ INDI"

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


# ---------------------------------------------------------------------------
# Lines ged4py parses that `filter` used to miss
# ---------------------------------------------------------------------------

# Each of these is a level-0 record to GedcomReader. Under the old hand-written
# pattern none of them matched, so they were kept with tag="" -- copied verbatim
# into the "filtered" output while the summary counted them as removed.
SMUGGLED = [
    pytest.param(" 0 @I2@ INDI", "@I2@", "INDI", id="leading-space"),
    pytest.param("\t0 @I6@ INDI", "@I6@", "INDI", id="leading-tab"),
    pytest.param("000 @I3@ INDI", "@I3@", "INDI", id="three-digit-level"),
    pytest.param("0@I4@ INDI", "@I4@", "INDI", id="no-delimiter-before-xref"),
    pytest.param("0 @I5@ FOO-BAR", "@I5@", "FOO-BAR", id="hyphen-in-tag"),
]


class TestGed4pyDivergences:
    @pytest.mark.parametrize(("raw", "xref", "tag"), SMUGGLED)
    def test_level0_divergence_now_parses(self, raw: str, xref: str, tag: str) -> None:
        line = parse_line(raw, 1)
        assert line.level == 0
        assert line.xref == xref
        assert line.tag == tag

    def test_hyphen_in_custom_sub_tag(self) -> None:
        line = parse_line("1 _MY-TAG x", 1)
        assert line.level == 1
        assert line.tag == "_MY-TAG"
        assert line.value == "x"

    @pytest.mark.parametrize(("raw", "xref", "tag"), SMUGGLED)
    def test_divergence_is_a_record_boundary(
        self, raw: str, xref: str, tag: str
    ) -> None:
        # The security-relevant consequence: these start records now, so every
        # strip/subtree transform can actually see and remove them.
        records = group_records(parse_lines(f"0 HEAD\n{raw}\n1 NOTE x\n0 TRLR\n"))
        assert [r.xref for r in records] == [None, xref, None]
        assert records[1].tag == tag

    def test_raw_is_untouched_by_the_lstrip(self) -> None:
        line = parse_line("  \t0 @I2@ INDI", 4)
        assert line.tag == "INDI"
        # The strip happens for matching only; serialize_records writes raw back.
        assert line.raw == "  \t0 @I2@ INDI"


class TestNarrowedAcceptance:
    """Lines `filter` used to accept and now rejects, to agree with ged4py."""

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("0 @.X@ INDI", id="xref-starts-with-dot"),
            pytest.param("0 @ X@ INDI", id="xref-starts-with-space"),
        ],
    )
    def test_xref_first_character_is_constrained(self, raw: str) -> None:
        # ged4py's xref class is @[A-Z-a-z0-9][^@]*@ -- the first character after
        # the @ must be alphanumeric.
        assert parse_line(raw, 1).tag == ""

    def test_narrowed_xref_is_no_longer_a_record_boundary(self) -> None:
        records = group_records(parse_lines("0 @I1@ INDI\n0 @.X@ INDI\n1 NAME X\n"))
        assert len(records) == 1
        assert records[0].xref == "@I1@"
        # It and its subtree now hang off the preceding record, as they do to ged4py.
        assert [c.raw for c in records[0].children] == ["0 @.X@ INDI", "1 NAME X"]

    def test_unicode_digit_level_rejected(self) -> None:
        # Without re.A on the decoded pattern, \d would accept U+0660 here while
        # ged4py's bytes pattern never could -- and int("٠١") is 1.
        assert parse_line("٠ @IEVIL@ INDI", 1).tag == ""

    def test_unicode_whitespace_prefix_rejected(self) -> None:
        # bytes.lstrip() does not remove NBSP, so neither may we. A bare
        # str.lstrip() would strip it and parse a record ged4py never sees.
        line = parse_line("\xa00 @IEVIL@ INDI", 1)
        assert line.tag == ""
        assert line.raw == "\xa00 @IEVIL@ INDI"

    def test_absurdly_long_level_rejected(self) -> None:
        # ged4py's level group is unbounded \d+; CPython's int() refuses past
        # 4300 digits, which would otherwise be an uncaught ValueError.
        raw = "9" * 5000 + " INDI"
        line = parse_line(raw, 3)
        assert line.tag == ""
        assert line.level == 0
        assert line.raw == raw


# ---------------------------------------------------------------------------
# Parity gate: `filter` must see exactly the lines ged4py's lexer sees
# ---------------------------------------------------------------------------

# Every character str.isspace() accepts that bytes.lstrip() does not remove.
# Derived, not hand-listed: an earlier draft of this file capped the scan at
# 0x3000 and thereby excluded U+3000 itself, which is the whole point.
UNICODE_ONLY_WS = {c for c in map(chr, range(sys.maxunicode + 1)) if c.isspace()} - set(
    " \t\r\n\x0b\x0c"
)
assert len(UNICODE_ONLY_WS) == 23, sorted(UNICODE_ONLY_WS)

# NUL, every real terminator, the delimiters, the characters that decide the xref
# and tag classes, Unicode digits, an accented letter -- plus the whitespace above.
# Shorten the sample lengths if this gets slow; never shorten the alphabet. A
# trimmed alphabet is how two earlier fuzzers reported zero violations while real
# divergences (`.` in an xref, NBSP in front of a level) sat in the code.
GATE_ALPHABET = sorted(
    set(" \t\r\n\x0b\x0c\x00.-_@/+%[]^0123456789AZazIND")
    | {"٠", "０", "é"}
    | UNICODE_ONLY_WS
)


def _ged4py_parses(s: str) -> re.Match[bytes] | None:
    """Mirror ged4py's real pipeline -- preprocessing included.

    ``GedcomReader.gedcom_lines`` does not match the raw line: it matches
    ``line.lstrip().rstrip(b"\\r\\n")`` on **bytes** (ged4py/parser.py:388).
    Comparing regex to regex without that step is what let three earlier
    attempts at this fix pass their own gate.
    """
    return _RE_GEDCOM_LINE.match(s.encode().lstrip().rstrip(b"\r\n"))


def _filter_parses(s: str) -> GedcomLine | None:
    # Calls production parse_line on purpose. Restating the strip set here makes
    # the gate vacuous for the one hand-written thing it exists to guard:
    # measured, a bare lstrip() in production yields 480 violations through this
    # form and 0 through a restated copy.
    line = parse_line(s, 1)
    return line if line.tag else None


def _disagreement(s: str) -> str | None:
    """Return a description of how the two parsers differ on ``s``, or None.

    What this still tests now that the pattern is derived from ged4py's: not the
    grammar -- that is shared by construction and cannot drift. It tests the two
    things that are still hand-written and can. First, the lstrip strip-set, since
    ged4py works in bytes and ``str.lstrip()`` with no argument removes 23 more
    characters. Second, whether ``re.A`` on the decoded copy really does reproduce
    the bytes pattern's semantics, which is what keeps a Unicode digit from being
    a level number here and nowhere else. Do not delete this as tautological.
    """
    ged = _ged4py_parses(s)
    line = _filter_parses(s)
    if ged is None:
        if line is not None:
            return f"filter parsed {s!r} as {line!r}; ged4py did not"
        return None
    if line is None:
        return f"ged4py parsed {s!r} as {ged.groups()!r}; filter did not"

    xref = ged["xref"]
    value = ged["value"]
    expected = (
        int(ged["level"].decode("ascii")),
        None if xref is None else xref.decode("utf-8"),
        ged["tag"].decode("ascii"),
        None if value is None else value.decode("utf-8"),
    )
    actual = (line.level, line.xref, line.tag, line.value)
    if actual != expected:
        return f"{s!r}: filter gave {actual!r}, ged4py gave {expected!r}"
    return None


def _run_gate(samples: Iterable[str]) -> None:
    violations = [v for v in map(_disagreement, samples) if v is not None]
    assert not violations, (
        f"{len(violations)} line(s) parse differently in `filter` and ged4py. "
        f"First few: {violations[:5]}"
    )


class TestGed4pyParity:
    def test_exhaustive_short_lines(self) -> None:
        alphabet = GATE_ALPHABET
        _run_gate(
            "".join(combo)
            for length in (1, 2, 3)
            for combo in itertools.product(alphabet, repeat=length)
        )

    def test_random_longer_lines(self) -> None:
        # Seeded: an unseeded fuzzer that passes here and fails in CI is worse
        # than no fuzzer at all.
        # A deterministic fuzz corpus, not a security primitive.
        rng = random.Random(0x6ED4)  # noqa: S311
        alphabet = GATE_ALPHABET
        _run_gate(
            "".join(rng.choices(alphabet, k=rng.randint(1, 12))) for _ in range(100_000)
        )

    @pytest.mark.parametrize(
        "raw",
        [
            "0 @I1@ INDI",
            " 0 @I2@ INDI",
            "\t0 @I6@ INDI",
            "000 @I3@ INDI",
            "0@I4@ INDI",
            "0 @I5@ FOO-BAR",
            "1 _MY-TAG x",
            "0 @.X@ INDI",
            "0 @ X@ INDI",
            "0\t@I1@\tINDI",
            "٠0 @IEVIL@ INDI",
            "٠ @IEVIL@ INDI",
            " 0 @IEVIL@ INDI",
            "　0 @IEVIL@ INDI",
            "\x1c0 @IEVIL@ INDI",
            "\x850 @IEVIL@ INDI",
            "0 @I1@ INDI\r",
            "  \t\v\f0 @I1@ INDI",
            "1 NAME René /Dupont/",
            "",
        ],
    )
    def test_named_cases_agree(self, raw: str) -> None:
        assert _disagreement(raw) is None
