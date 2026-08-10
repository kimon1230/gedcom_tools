from __future__ import annotations

from pathlib import Path

import pytest

from gedcom_tools import progress
from gedcom_tools.commands.compare.formatters import format_text as compare_text
from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    CompareResult,
    MatchPair,
    MatchScore,
)
from gedcom_tools.commands.convert.transcoder import ConvertResult
from gedcom_tools.commands.duplicates.formatters import format_text as duplicates_text
from gedcom_tools.commands.duplicates.models import DuplicatesResult
from gedcom_tools.commands.filter.models import FilterResult, RecordCounts
from gedcom_tools.commands.languages import EventMatch, LanguageRow, LanguagesResult
from gedcom_tools.progress import ASCII_GLYPHS, UNICODE_GLYPHS, Colors
from gedcom_tools.utils import EncodingInfo


@pytest.fixture
def force_ascii(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(progress, "_ascii_forced", True)


def _colors() -> Colors:
    return Colors(force_disable=True)


def _encoding() -> EncodingInfo:
    return EncodingInfo(encoding="UTF-8", has_bom=False, declared_charset="UTF-8")


def _ind(xref: str, source: str, full_name: str) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file=source,
        full_name=full_name,
        sex="M",
        birth_year=1850,
        death_year=1920,
    )


def _score(field_scores: dict[str, float] | None = None) -> MatchScore:
    return MatchScore(
        total=0.95,
        field_scores=field_scores or {},
        classification="certain",
        comparable_field_count=4,
        sex_penalty=True,
    )


def _pair(score: MatchScore | None = None) -> MatchPair:
    return MatchPair(
        individual_a=_ind("@I1@", "A", "John Smith"),
        individual_b=_ind("@I2@", "B", "John Smith"),
        score=score or _score(),
        field_diffs=[],
    )


def _compare_result() -> CompareResult:
    return CompareResult(
        file_a="tree1.ged",
        file_b="tree2.ged",
        encoding_a=_encoding(),
        encoding_b=_encoding(),
        total_a=100,
        total_b=80,
        certain_matches=[_pair()],
        probable_matches=[],
        unique_to_a=[],
        unique_to_b=[],
    )


def _duplicates_result(score: MatchScore | None = None) -> DuplicatesResult:
    return DuplicatesResult(
        file="family.ged",
        encoding=_encoding(),
        total_individuals=200,
        certain_matches=[_pair(score)],
        probable_matches=[],
    )


def _convert_result() -> ConvertResult:
    return ConvertResult(
        source_file=Path("input.ged"),
        output_file=Path("output.ged"),
        source_encoding="ANSEL",
        target_encoding="UTF-8",
        source_codec="gedcom",
        target_codec="utf-8",
        lines_total=10,
        lines_over_limit=0,
        normalized=False,
        bom_added=False,
        bom_stripped=None,
        dry_run=False,
    )


def _filter_result() -> FilterResult:
    return FilterResult(
        source_path="tree.ged",
        output_path="trimmed.ged",
        source_counts=RecordCounts(indi=120),
        output_counts=RecordCounts(indi=100),
        removed_counts=RecordCounts(indi=20),
        dangling_lines_removed=0,
        empty_families_removed=0,
        dry_run=False,
    )


def _languages_table_result() -> LanguagesResult:
    return LanguagesResult(
        file_path="tree.ged",
        encoding_info=_encoding(),
        rows=[
            LanguageRow("English", "en", 10, 5, 20),
            LanguageRow("Greek", "el", 5, 2, 8),
        ],
        total_texts=50,
    )


def _languages_filter_result() -> LanguagesResult:
    return LanguagesResult(
        file_path="tree.ged",
        encoding_info=_encoding(),
        total_texts=5,
        language_filter="el",
        language_filter_name="Greek",
        event_matches=[EventMatch("@I1@", "BIRT", "Eleni")],
    )


class TestAsciiDecorations:
    def test_compare_pair_glyph(self, force_ascii: None) -> None:
        out = compare_text(_compare_result(), _colors())
        assert "<->" in out
        out.encode("ascii")

    def test_duplicates_pair_glyph(self, force_ascii: None) -> None:
        out = duplicates_text(_duplicates_result(), _colors())
        assert "<->" in out
        out.encode("ascii")

    def test_compare_times_glyph(self, force_ascii: None) -> None:
        out = compare_text(_compare_result(), _colors(), verbose=True)
        assert "x0.70" in out
        out.encode("ascii")

    def test_duplicates_times_glyph(self, force_ascii: None) -> None:
        # duplicates gates its score line on field_scores as well as verbose
        result = _duplicates_result(_score(field_scores={"Surname": 1.0}))
        out = duplicates_text(result, _colors(), verbose=True)
        assert "x0.70" in out
        out.encode("ascii")

    def test_convert_arrow_glyph(self, force_ascii: None) -> None:
        out = _convert_result().format_text(_colors(), quiet=True)
        assert "->" in out
        out.encode("ascii")

    def test_filter_arrow_glyph(self, force_ascii: None) -> None:
        out = _filter_result().format_text(_colors(), quiet=True)
        assert "->" in out
        out.encode("ascii")

    def test_languages_rule_glyph(self, force_ascii: None) -> None:
        out = _languages_table_result().format_text(_colors())
        assert "  " + "-" * 53 in out.split("\n")
        out.encode("ascii")

    def test_languages_dash_glyph(self, force_ascii: None) -> None:
        out = _languages_filter_result().format_text(_colors())
        assert "  -- " in out
        out.encode("ascii")


class TestDefaultDecorations:
    """Unicode counterparts for the sites nothing else asserts on."""

    def test_convert_arrow_glyph(self) -> None:
        out = _convert_result().format_text(_colors(), quiet=True)
        assert " → " in out

    def test_filter_arrow_glyph(self) -> None:
        out = _filter_result().format_text(_colors(), quiet=True)
        assert " → " in out

    def test_languages_dash_glyph(self) -> None:
        out = _languages_filter_result().format_text(_colors())
        assert "  — " in out


def test_rule_glyph_is_one_character_wide() -> None:
    # rule is multiplied by 53 to draw the languages table separator, so a
    # two-character value would silently double the table width.
    assert len(UNICODE_GLYPHS.rule) == len(ASCII_GLYPHS.rule) == 1
