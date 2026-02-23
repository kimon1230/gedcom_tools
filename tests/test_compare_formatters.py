from __future__ import annotations

import json

from gedcom_tools.commands.compare.formatters import format_json, format_text
from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    CompareResult,
    FieldDiff,
    MatchPair,
    MatchScore,
)
from gedcom_tools.progress import Colors
from gedcom_tools.utils import EncodingInfo


def _colors() -> Colors:
    """Colors with ANSI disabled for testable output."""
    return Colors(force_disable=True)


def _ind(
    xref: str,
    source: str = "A",
    full_name: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    **kwargs: object,
) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file=source,
        full_name=full_name,
        birth_year=birth_year,
        death_year=death_year,
        **kwargs,
    )


def _score(
    total: float = 0.95,
    classification: str = "certain",
    field_scores: dict[str, float] | None = None,
    insufficient_data: bool = False,
    name_only: bool = False,
    comparable_field_count: int = 4,
    sex_penalty: bool = False,
) -> MatchScore:
    return MatchScore(
        total=total,
        field_scores=field_scores or {},
        classification=classification,
        insufficient_data=insufficient_data,
        name_only=name_only,
        comparable_field_count=comparable_field_count,
        sex_penalty=sex_penalty,
    )


def _pair(
    ind_a: CompareIndividual,
    ind_b: CompareIndividual,
    score: MatchScore | None = None,
    field_diffs: list[FieldDiff] | None = None,
) -> MatchPair:
    return MatchPair(
        individual_a=ind_a,
        individual_b=ind_b,
        score=score or _score(),
        field_diffs=field_diffs or [],
    )


def _encoding(
    encoding: str = "UTF-8",
    has_bom: bool = False,
    declared_charset: str | None = "UTF-8",
) -> EncodingInfo:
    return EncodingInfo(
        encoding=encoding, has_bom=has_bom, declared_charset=declared_charset
    )


def _result(
    certain: list[MatchPair] | None = None,
    probable: list[MatchPair] | None = None,
    unique_a: list[CompareIndividual] | None = None,
    unique_b: list[CompareIndividual] | None = None,
    total_a: int = 100,
    total_b: int = 80,
) -> CompareResult:
    return CompareResult(
        file_a="/path/to/tree1.ged",
        file_b="/path/to/tree2.ged",
        encoding_a=_encoding("UTF-8"),
        encoding_b=_encoding("ANSEL", declared_charset="ANSEL"),
        total_a=total_a,
        total_b=total_b,
        certain_matches=certain or [],
        probable_matches=probable or [],
        unique_to_a=unique_a or [],
        unique_to_b=unique_b or [],
    )


_MATCH_A = _ind("@I1@", "A", full_name="John Smith", birth_year=1850, death_year=1920)
_MATCH_B = _ind("@I2@", "B", full_name="John Smith", birth_year=1850, death_year=1920)
_DIFF = [FieldDiff(field="Birth Place", value_a="London", value_b="London, England")]


class TestTextHeader:
    def test_file_names_shown(self) -> None:
        output = format_text(_result(), _colors())
        assert "File A:" in output
        assert "File B:" in output
        assert "tree1.ged" in output
        assert "tree2.ged" in output

    def test_encoding_shown(self) -> None:
        output = format_text(_result(), _colors())
        assert "Encoding A:" in output
        assert "Encoding B:" in output
        assert "UTF-8" in output
        assert "ANSEL" in output


class TestTextSummary:
    def test_summary_section_present(self) -> None:
        output = format_text(_result(), _colors())
        assert "=== Comparison Summary ===" in output

    def test_summary_counts(self) -> None:
        result = _result(
            certain=[_pair(_MATCH_A, _MATCH_B)],
            unique_a=[_ind("@I10@", "A", full_name="Alice Jones")],
            total_a=1_500,
            total_b=2_000,
        )
        output = format_text(result, _colors())
        assert "1,500" in output
        assert "2,000" in output

    def test_summary_always_shown(self) -> None:
        result = _result(
            certain=[_pair(_MATCH_A, _MATCH_B)],
            unique_a=[_ind("@I10@", "A")],
        )
        output_certain = format_text(result, _colors(), show_matches="certain")
        output_unique = format_text(result, _colors(), list_unique=True)
        assert "=== Comparison Summary ===" in output_certain
        assert "=== Comparison Summary ===" in output_unique


class TestTextCertainMatches:
    def test_certain_match_displayed(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B)
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "John Smith" in output
        assert "@I1@" in output
        assert "@I2@" in output
        assert "1850" in output

    def test_field_diffs_shown(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B, field_diffs=_DIFF)
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "Birth Place" in output
        assert '"London"' in output or "London" in output
        assert '"London, England"' in output or "London, England" in output
        assert "(A)" in output
        assert "(B)" in output

    def test_no_diffs_message(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B, field_diffs=[])
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "(no differences)" in output

    def test_score_shown(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B, score=_score(total=0.92))
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "0.92" in output

    def test_arrow_separator(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B)
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "\u2194" in output


class TestTextProbableMatches:
    def test_probable_section_shown(self) -> None:
        prob_a = _ind("@I3@", "A", full_name="Mary Brown", birth_year=1870)
        prob_b = _ind("@I4@", "B", full_name="Mary Browne", birth_year=1870)
        pair = _pair(
            prob_a, prob_b, score=_score(total=0.75, classification="probable")
        )
        result = _result(probable=[pair])
        output = format_text(result, _colors())
        assert "Mary Brown" in output
        assert "Mary Browne" in output

    def test_show_certain_hides_probable(self) -> None:
        prob_a = _ind("@I3@", "A", full_name="Mary Brown", birth_year=1870)
        prob_b = _ind("@I4@", "B", full_name="Mary Browne", birth_year=1870)
        pair = _pair(
            prob_a, prob_b, score=_score(total=0.75, classification="probable")
        )
        result = _result(probable=[pair])
        output = format_text(result, _colors(), show_matches="certain")
        assert "Mary Brown" not in output
        assert "Mary Browne" not in output

    def test_show_probable_hides_certain(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B)
        result = _result(certain=[pair])
        output = format_text(result, _colors(), show_matches="probable")
        assert "Certain Matches" not in output


class TestTextVerbose:
    def test_verbose_shows_field_scores(self) -> None:
        scores = {"Surname": 1.0, "Birth Year": 0.85}
        pair = _pair(_MATCH_A, _MATCH_B, score=_score(field_scores=scores))
        result = _result(certain=[pair])
        output = format_text(result, _colors(), verbose=True)
        assert "Scores:" in output
        assert "Surname" in output

    def test_non_verbose_no_scores(self) -> None:
        scores = {"Surname": 1.0, "Birth Year": 0.85}
        pair = _pair(_MATCH_A, _MATCH_B, score=_score(field_scores=scores))
        result = _result(certain=[pair])
        output = format_text(result, _colors(), verbose=False)
        assert "Scores:" not in output


class TestTextUnique:
    def test_list_unique_shows_individuals(self) -> None:
        unique = [_ind("@I10@", "A", full_name="Alice Jones", birth_year=1900)]
        result = _result(unique_a=unique)
        output = format_text(result, _colors(), list_unique=True)
        assert "Alice Jones" in output
        assert "@I10@" in output

    def test_no_list_unique_shows_tip(self) -> None:
        unique = [_ind("@I10@", "A", full_name="Alice Jones")]
        result = _result(unique_a=unique)
        output = format_text(result, _colors(), list_unique=False)
        assert "--list-unique" in output

    def test_no_tip_when_no_unique(self) -> None:
        result = _result(unique_a=[], unique_b=[])
        output = format_text(result, _colors(), list_unique=False)
        assert "--list-unique" not in output


class TestTextLimit:
    def test_limit_truncates_matches(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", "A", full_name=f"Person {i}"),
                _ind(f"@I{i + 10}@", "B", full_name=f"Person {i}"),
            )
            for i in range(3)
        ]
        result = _result(certain=pairs)
        output = format_text(result, _colors(), limit=1)
        assert "Person 0" in output
        assert "2 more" in output

    def test_limit_truncates_unique(self) -> None:
        unique = [_ind(f"@I{i}@", "A", full_name=f"Unique {i}") for i in range(4)]
        result = _result(unique_a=unique)
        output = format_text(result, _colors(), list_unique=True, limit=2)
        assert "Unique 0" in output
        assert "Unique 1" in output
        assert "2 more" in output

    def test_limit_zero_shows_all(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", "A", full_name=f"Person {i}"),
                _ind(f"@I{i + 10}@", "B", full_name=f"Person {i}"),
            )
            for i in range(5)
        ]
        result = _result(certain=pairs)
        output = format_text(result, _colors(), limit=0)
        for i in range(5):
            assert f"Person {i}" in output

    def test_truncation_header_shows_total(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", "A", full_name=f"Person {i}"),
                _ind(f"@I{i + 10}@", "B", full_name=f"Person {i}"),
            )
            for i in range(5)
        ]
        result = _result(certain=pairs)
        output = format_text(result, _colors(), limit=2)
        assert "5 total" in output
        assert "showing first 2" in output or "first 2" in output


class TestTextQuiet:
    def test_quiet_mode_single_line(self) -> None:
        result = _result(
            certain=[_pair(_MATCH_A, _MATCH_B)],
            unique_a=[_ind("@I10@", "A")],
        )
        output = format_text(result, _colors(), quiet=True)
        lines = [line for line in output.strip().splitlines() if line.strip()]
        assert len(lines) == 1

    def test_quiet_mode_format(self) -> None:
        result = _result(
            certain=[_pair(_MATCH_A, _MATCH_B)],
            probable=[
                _pair(
                    _ind("@I3@", "A", full_name="X"),
                    _ind("@I4@", "B", full_name="Y"),
                    score=_score(classification="probable"),
                )
            ],
            unique_a=[_ind("@I10@", "A")],
            unique_b=[_ind("@I20@", "B"), _ind("@I21@", "B")],
        )
        output = format_text(result, _colors(), quiet=True).strip()
        assert "1 certain" in output
        assert "1 probable" in output

    def test_quiet_uses_filenames(self) -> None:
        result = _result(unique_a=[_ind("@I10@", "A")])
        output = format_text(result, _colors(), quiet=True).strip()
        assert "tree1.ged" in output
        assert "/path/to" not in output


class TestTextEdgeCases:
    def test_empty_results(self) -> None:
        result = _result()
        output = format_text(result, _colors())
        assert "=== Comparison Summary ===" in output
        assert "0" in output

    def test_missing_years_display(self) -> None:
        ind_a = _ind("@I1@", "A", full_name="No Years")
        ind_b = _ind("@I2@", "B", full_name="No Years")
        pair = _pair(ind_a, ind_b)
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "?" in output

    def test_empty_name_shows_unknown(self) -> None:
        ind_a = _ind("@I1@", "A", full_name="")
        ind_b = _ind("@I2@", "B", full_name="")
        pair = _pair(ind_a, ind_b)
        result = _result(certain=[pair])
        output = format_text(result, _colors())
        assert "Unknown" in output


class TestJsonStructure:
    def test_top_level_keys(self) -> None:
        data = json.loads(format_json(_result()))
        expected = {
            "file_a",
            "file_b",
            "encoding_a",
            "encoding_b",
            "total_a",
            "total_b",
            "certain_matches",
            "certain_matches_total",
            "probable_matches",
            "probable_matches_total",
            "unique_to_a",
            "unique_to_a_total",
            "unique_to_b",
            "unique_to_b_total",
        }
        assert expected <= set(data.keys())

    def test_encoding_structure(self) -> None:
        data = json.loads(format_json(_result()))
        enc = data["encoding_a"]
        assert "detected" in enc or "encoding" in enc
        assert "has_bom" in enc
        assert "declared" in enc or "declared_charset" in enc

    def test_valid_json(self) -> None:
        output = format_json(_result())
        parsed = json.loads(output)
        assert isinstance(parsed, dict)


class TestJsonMatches:
    def test_match_pair_structure(self) -> None:
        pair = _pair(
            _MATCH_A,
            _MATCH_B,
            score=_score(field_scores={"Surname": 1.0}),
            field_diffs=_DIFF,
        )
        data = json.loads(format_json(_result(certain=[pair])))
        match = data["certain_matches"][0]
        assert "individual_a" in match
        assert "individual_b" in match
        assert "score" in match
        assert "classification" in match
        assert "field_scores" in match
        assert "differences" in match

    def test_individual_summary(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B)
        data = json.loads(format_json(_result(certain=[pair])))
        ind = data["certain_matches"][0]["individual_a"]
        assert "xref" in ind
        assert "name" in ind
        assert "birth_year" in ind
        assert "death_year" in ind

    def test_differences_list(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B, field_diffs=_DIFF)
        data = json.loads(format_json(_result(certain=[pair])))
        diff = data["certain_matches"][0]["differences"][0]
        assert "field" in diff
        assert "value_a" in diff
        assert "value_b" in diff
        assert diff["field"] == "Birth Place"
        assert diff["value_a"] == "London"
        assert diff["value_b"] == "London, England"


class TestJsonFlags:
    def test_show_certain_empties_probable(self) -> None:
        prob_pair = _pair(
            _ind("@I3@", "A", full_name="X"),
            _ind("@I4@", "B", full_name="Y"),
            score=_score(classification="probable"),
        )
        data = json.loads(
            format_json(_result(probable=[prob_pair]), show_matches="certain")
        )
        assert data["probable_matches"] == []

    def test_show_probable_empties_certain(self) -> None:
        cert_pair = _pair(_MATCH_A, _MATCH_B)
        data = json.loads(
            format_json(_result(certain=[cert_pair]), show_matches="probable")
        )
        assert data["certain_matches"] == []

    def test_list_unique_false_empties_unique(self) -> None:
        result = _result(unique_a=[_ind("@I10@", "A", full_name="Solo")])
        data = json.loads(format_json(result, list_unique=False))
        assert data["unique_to_a"] == []
        assert data["unique_to_b"] == []

    def test_list_unique_true_includes_unique(self) -> None:
        unique = [_ind("@I10@", "A", full_name="Solo Person")]
        result = _result(unique_a=unique)
        data = json.loads(format_json(result, list_unique=True))
        assert len(data["unique_to_a"]) == 1
        assert data["unique_to_a"][0]["xref"] == "@I10@"

    def test_limit_truncates_json(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", "A", full_name=f"Person {i}"),
                _ind(f"@I{i + 10}@", "B", full_name=f"Person {i}"),
            )
            for i in range(5)
        ]
        data = json.loads(format_json(_result(certain=pairs), limit=2))
        assert len(data["certain_matches"]) == 2
        assert data["certain_matches_total"] == 5


class TestJsonEdgeCases:
    def test_empty_results(self) -> None:
        data = json.loads(format_json(_result()))
        assert data["certain_matches"] == []
        assert data["probable_matches"] == []
        assert data["unique_to_a"] == []
        assert data["unique_to_b"] == []

    def test_null_years(self) -> None:
        ind_a = _ind("@I1@", "A", full_name="No Years")
        ind_b = _ind("@I2@", "B", full_name="No Years")
        pair = _pair(ind_a, ind_b)
        data = json.loads(format_json(_result(certain=[pair])))
        ind = data["certain_matches"][0]["individual_a"]
        assert ind["birth_year"] is None
        assert ind["death_year"] is None


class TestJsonTotals:
    def test_totals_equal_array_lengths(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", "A", full_name=f"Person {i}"),
                _ind(f"@I{i + 10}@", "B", full_name=f"Person {i}"),
            )
            for i in range(3)
        ]
        unique = [_ind("@I99@", "A", full_name="Solo")]
        result = _result(certain=pairs, unique_a=unique)
        data = json.loads(format_json(result, list_unique=True))
        assert data["certain_matches_total"] == len(data["certain_matches"])
        assert data["probable_matches_total"] == len(data["probable_matches"])
        assert data["unique_to_a_total"] == len(data["unique_to_a"])
        assert data["unique_to_b_total"] == len(data["unique_to_b"])

    def test_totals_reflect_show_matches_filter(self) -> None:
        cert_pair = _pair(_MATCH_A, _MATCH_B)
        prob_pair = _pair(
            _ind("@I3@", "A", full_name="X"),
            _ind("@I4@", "B", full_name="Y"),
            score=_score(classification="probable"),
        )
        result = _result(certain=[cert_pair], probable=[prob_pair])
        data = json.loads(format_json(result, show_matches="certain"))
        assert data["certain_matches_total"] == 1
        assert data["probable_matches_total"] == 0


class TestSexPenaltyDisplay:
    def test_verbose_shows_sex_penalty(self) -> None:
        pair = _pair(
            _MATCH_A,
            _MATCH_B,
            score=_score(
                field_scores={"Surname": 1.0, "Given Name": 0.9},
                sex_penalty=True,
            ),
        )
        result = _result(certain=[pair])
        output = format_text(result, _colors(), verbose=True)
        assert "Sex mismatch" in output
        assert "\u00d70.70" in output

    def test_verbose_no_penalty_no_label(self) -> None:
        pair = _pair(
            _MATCH_A,
            _MATCH_B,
            score=_score(
                field_scores={"Surname": 1.0, "Given Name": 0.9},
                sex_penalty=False,
            ),
        )
        result = _result(certain=[pair])
        output = format_text(result, _colors(), verbose=True)
        assert "Sex mismatch" not in output

    def test_sex_penalty_true_in_json(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B, score=_score(sex_penalty=True))
        data = json.loads(format_json(_result(certain=[pair])))
        assert data["certain_matches"][0]["sex_penalty"] is True

    def test_sex_penalty_false_in_json(self) -> None:
        pair = _pair(_MATCH_A, _MATCH_B, score=_score(sex_penalty=False))
        data = json.loads(format_json(_result(certain=[pair])))
        assert data["certain_matches"][0]["sex_penalty"] is False
