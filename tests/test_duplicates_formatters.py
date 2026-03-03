from __future__ import annotations

import json

from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    FieldDiff,
    MatchPair,
    MatchScore,
)
from gedcom_tools.commands.duplicates.formatters import format_json, format_text
from gedcom_tools.commands.duplicates.models import DuplicatesResult
from gedcom_tools.progress import Colors
from gedcom_tools.utils import EncodingInfo


def _colors(disabled: bool = True) -> Colors:
    return Colors(force_disable=disabled)


def _ind(
    xref: str,
    full_name: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    given_name: str = "",
    surname: str = "",
    sex: str = "",
    birth_place: str = "",
    death_place: str = "",
) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file="test.ged",
        full_name=full_name,
        given_name=given_name,
        surname=surname,
        sex=sex,
        birth_year=birth_year,
        death_year=death_year,
        birth_place=birth_place,
        death_place=death_place,
    )


def _score(
    total: float = 0.92,
    classification: str = "certain",
    field_scores: dict[str, float] | None = None,
    insufficient_data: bool = False,
    sex_penalty: bool = False,
) -> MatchScore:
    return MatchScore(
        total=total,
        field_scores=field_scores or {},
        classification=classification,
        comparable_field_count=4,
        insufficient_data=insufficient_data,
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


def _encoding() -> EncodingInfo:
    return EncodingInfo(encoding="UTF-8", has_bom=False, declared_charset="UTF-8")


def _result(
    certain: list[MatchPair] | None = None,
    probable: list[MatchPair] | None = None,
    total_individuals: int = 200,
) -> DuplicatesResult:
    return DuplicatesResult(
        file="family.ged",
        encoding=_encoding(),
        total_individuals=total_individuals,
        certain_matches=certain or [],
        probable_matches=probable or [],
    )


_ALICE_A = _ind("@I1@", "Alice Smith", 1850, 1920, "Alice", "Smith", "F", "London")
_ALICE_B = _ind("@I2@", "Alyce Smith", 1850, 1920, "Alyce", "Smith", "F", "London")
_GIVEN_DIFF = FieldDiff(field="Given Name", value_a="Alice", value_b="Alyce")


class TestTextSummary:
    def test_summary_section_present(self) -> None:
        output = format_text(_result(), _colors())
        assert "=== Duplicate Scan Summary ===" in output

    def test_file_shown(self) -> None:
        output = format_text(_result(), _colors())
        assert "File: family.ged" in output

    def test_counts_shown(self) -> None:
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[
                _pair(
                    _ind("@I3@", "Bob"),
                    _ind("@I4@", "Bobby"),
                    score=_score(0.72, "probable"),
                )
            ],
            total_individuals=250,
        )
        output = format_text(result, _colors())
        assert "250" in output
        assert "Certain duplicates:      1" in output
        assert "Probable duplicates:     1" in output

    def test_empty_results(self) -> None:
        output = format_text(_result(total_individuals=0), _colors())
        assert "Individuals scanned:     0" in output
        assert "Certain duplicates:      0" in output
        assert "Probable duplicates:     0" in output


class TestTextMatchDisplay:
    def test_match_names_and_xrefs(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, field_diffs=[_GIVEN_DIFF])
        output = format_text(_result(certain=[pair]), _colors())
        assert "Alice Smith" in output
        assert "Alyce Smith" in output
        assert "@I1@" in output
        assert "@I2@" in output

    def test_year_range(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B)
        output = format_text(_result(certain=[pair]), _colors())
        assert "1850-1920" in output

    def test_missing_years_show_question_mark(self) -> None:
        a = _ind("@I1@", "No Years")
        b = _ind("@I2@", "No Years")
        pair = _pair(a, b)
        output = format_text(_result(certain=[pair]), _colors())
        assert "?-?" in output

    def test_empty_name_shows_unknown(self) -> None:
        a = _ind("@I1@")
        b = _ind("@I2@")
        pair = _pair(a, b)
        output = format_text(_result(certain=[pair]), _colors())
        assert "Unknown" in output

    def test_arrow_separator(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B)
        output = format_text(_result(certain=[pair]), _colors())
        assert "\u2194" in output

    def test_score_shown(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, score=_score(0.88))
        output = format_text(_result(certain=[pair]), _colors())
        assert "0.88" in output

    def test_field_diffs_shown(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, field_diffs=[_GIVEN_DIFF])
        output = format_text(_result(certain=[pair]), _colors())
        assert 'Given Name: "Alice" vs "Alyce"' in output

    def test_no_diffs_message(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, field_diffs=[])
        output = format_text(_result(certain=[pair]), _colors())
        assert "(no differences)" in output

    def test_section_headers(self) -> None:
        certain_pair = _pair(_ALICE_A, _ALICE_B)
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(certain=[certain_pair], probable=[probable_pair])
        output = format_text(result, _colors())
        assert "=== Certain Duplicates (1) ===" in output
        assert "=== Probable Duplicates (1) ===" in output


class TestTextQuiet:
    def test_single_line_format(self) -> None:
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[
                _pair(
                    _ind("@I3@", "X"),
                    _ind("@I4@", "Y"),
                    score=_score(0.70, "probable"),
                )
            ],
        )
        output = format_text(result, _colors(), quiet=True)
        assert output.strip() == "1 certain, 1 probable"

    def test_no_summary_section(self) -> None:
        output = format_text(_result(), _colors(), quiet=True)
        assert "Duplicate Scan Summary" not in output
        assert "File:" not in output


class TestTextVerbose:
    def test_verbose_shows_field_scores(self) -> None:
        scores = {"Surname": 1.0, "Given Name": 0.82, "Birth Year": 1.0}
        pair = _pair(_ALICE_A, _ALICE_B, score=_score(field_scores=scores))
        output = format_text(_result(certain=[pair]), _colors(), verbose=True)
        assert "[Scores:" in output
        assert "Surname 1.00" in output
        assert "Given Name 0.82" in output

    def test_non_verbose_no_scores(self) -> None:
        scores = {"Surname": 1.0}
        pair = _pair(_ALICE_A, _ALICE_B, score=_score(field_scores=scores))
        output = format_text(_result(certain=[pair]), _colors(), verbose=False)
        assert "[Scores:" not in output

    def test_sex_penalty_in_verbose(self) -> None:
        pair = _pair(
            _ALICE_A,
            _ALICE_B,
            score=_score(field_scores={"Surname": 1.0}, sex_penalty=True),
        )
        output = format_text(_result(certain=[pair]), _colors(), verbose=True)
        assert "Sex mismatch" in output
        assert "\u00d70.70" in output

    def test_no_sex_penalty_label_when_false(self) -> None:
        pair = _pair(
            _ALICE_A,
            _ALICE_B,
            score=_score(field_scores={"Surname": 1.0}, sex_penalty=False),
        )
        output = format_text(_result(certain=[pair]), _colors(), verbose=True)
        assert "Sex mismatch" not in output


class TestTextShowMatches:
    def test_show_certain_hides_probable(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        output = format_text(result, _colors(), show_matches="certain")
        assert "Certain Duplicates" in output
        assert "Probable Duplicates" not in output
        assert "Bobby" not in output

    def test_show_probable_hides_certain(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        output = format_text(result, _colors(), show_matches="probable")
        assert "Certain Duplicates" not in output
        assert "Probable Duplicates" in output
        assert "Alice Smith" not in output

    def test_show_all_shows_both(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        output = format_text(result, _colors(), show_matches="all")
        assert "Certain Duplicates" in output
        assert "Probable Duplicates" in output

    def test_summary_always_shown_regardless_of_filter(self) -> None:
        result = _result(certain=[_pair(_ALICE_A, _ALICE_B)])
        output = format_text(result, _colors(), show_matches="probable")
        assert "=== Duplicate Scan Summary ===" in output
        assert "Certain duplicates:      1" in output


class TestTextLimit:
    def test_limit_truncates_with_message(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", f"Person {i}"),
                _ind(f"@I{i + 10}@", f"Person {i} Copy"),
            )
            for i in range(5)
        ]
        output = format_text(_result(certain=pairs), _colors(), limit=2)
        assert "Person 0" in output
        assert "Person 1" in output
        assert "3 more" in output
        assert "--limit 0" in output

    def test_limit_header_shows_total(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", f"Person {i}"),
                _ind(f"@I{i + 10}@", f"Person {i} Copy"),
            )
            for i in range(5)
        ]
        output = format_text(_result(certain=pairs), _colors(), limit=2)
        assert "5 total" in output
        assert "showing first 2" in output

    def test_limit_zero_shows_all(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", f"Person {i}"),
                _ind(f"@I{i + 10}@", f"Person {i} Copy"),
            )
            for i in range(5)
        ]
        output = format_text(_result(certain=pairs), _colors(), limit=0)
        for i in range(5):
            assert f"Person {i}" in output
        assert "more" not in output

    def test_limit_greater_than_count_shows_all(self) -> None:
        pairs = [_pair(_ALICE_A, _ALICE_B)]
        output = format_text(_result(certain=pairs), _colors(), limit=10)
        assert "Alice Smith" in output
        assert "more" not in output


class TestTextInsufficientData:
    def test_low_confidence_suffix(self) -> None:
        pair = _pair(
            _ALICE_A,
            _ALICE_B,
            score=_score(0.75, "probable", insufficient_data=True),
        )
        output = format_text(_result(probable=[pair]), _colors())
        assert "(low confidence)" in output

    def test_no_suffix_when_sufficient(self) -> None:
        pair = _pair(
            _ALICE_A,
            _ALICE_B,
            score=_score(0.92, insufficient_data=False),
        )
        output = format_text(_result(certain=[pair]), _colors())
        assert "(low confidence)" not in output


class TestTextNoColor:
    def test_no_ansi_codes(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B)
        output = format_text(_result(certain=[pair]), _colors(disabled=True))
        assert "\033[" not in output
        assert "=== Duplicate Scan Summary ===" in output
        assert "=== Certain Duplicates" in output


# ---------------------------------------------------------------------------
# JSON tests
# ---------------------------------------------------------------------------


class TestJsonStructure:
    def test_top_level_keys(self) -> None:
        data = json.loads(format_json(_result()))
        expected = {
            "file",
            "encoding",
            "total_individuals",
            "certain_duplicates",
            "certain_duplicates_total",
            "probable_duplicates",
            "probable_duplicates_total",
        }
        assert expected <= set(data.keys())

    def test_encoding_structure(self) -> None:
        data = json.loads(format_json(_result()))
        enc = data["encoding"]
        assert "detected" in enc
        assert "has_bom" in enc
        assert "declared" in enc

    def test_valid_json(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, field_diffs=[_GIVEN_DIFF])
        result = _result(certain=[pair])
        parsed = json.loads(format_json(result))
        assert isinstance(parsed, dict)

    def test_source_file_omitted(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B)
        data = json.loads(format_json(_result(certain=[pair])))
        match = data["certain_duplicates"][0]
        assert "source_file" not in match["individual_a"]
        assert "source_file" not in match["individual_b"]


class TestJsonMatchStructure:
    def test_match_pair_fields(self) -> None:
        pair = _pair(
            _ALICE_A,
            _ALICE_B,
            score=_score(field_scores={"Surname": 1.0}),
            field_diffs=[_GIVEN_DIFF],
        )
        data = json.loads(format_json(_result(certain=[pair])))
        match = data["certain_duplicates"][0]
        assert "individual_a" in match
        assert "individual_b" in match
        assert "score" in match
        assert "classification" in match
        assert "field_scores" in match
        assert "differences" in match

    def test_individual_fields(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B)
        data = json.loads(format_json(_result(certain=[pair])))
        ind = data["certain_duplicates"][0]["individual_a"]
        assert ind["xref"] == "@I1@"
        assert ind["name"] == "Alice Smith"
        assert ind["birth_year"] == 1850
        assert ind["death_year"] == 1920
        assert "given_name" in ind
        assert "surname" in ind
        assert "sex" in ind
        assert "birth_place" in ind
        assert "death_place" in ind

    def test_differences_list(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, field_diffs=[_GIVEN_DIFF])
        data = json.loads(format_json(_result(certain=[pair])))
        diff = data["certain_duplicates"][0]["differences"][0]
        assert diff["field"] == "Given Name"
        assert diff["value_a"] == "Alice"
        assert diff["value_b"] == "Alyce"

    def test_null_years(self) -> None:
        a = _ind("@I1@", "No Years")
        b = _ind("@I2@", "No Years")
        pair = _pair(a, b)
        data = json.loads(format_json(_result(certain=[pair])))
        ind = data["certain_duplicates"][0]["individual_a"]
        assert ind["birth_year"] is None
        assert ind["death_year"] is None

    def test_empty_name_shows_unknown(self) -> None:
        a = _ind("@I1@")
        b = _ind("@I2@")
        pair = _pair(a, b)
        data = json.loads(format_json(_result(certain=[pair])))
        assert data["certain_duplicates"][0]["individual_a"]["name"] == "Unknown"


class TestJsonShowMatches:
    def test_show_certain_empties_probable(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        data = json.loads(format_json(result, show_matches="certain"))
        assert len(data["certain_duplicates"]) == 1
        assert data["probable_duplicates"] == []
        assert data["probable_duplicates_total"] == 0

    def test_show_probable_empties_certain(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        data = json.loads(format_json(result, show_matches="probable"))
        assert data["certain_duplicates"] == []
        assert data["certain_duplicates_total"] == 0
        assert len(data["probable_duplicates"]) == 1

    def test_show_all_includes_both(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        data = json.loads(format_json(result, show_matches="all"))
        assert len(data["certain_duplicates"]) == 1
        assert len(data["probable_duplicates"]) == 1


class TestJsonLimit:
    def test_limit_truncates_arrays(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", f"Person {i}"),
                _ind(f"@I{i + 10}@", f"Person {i} Copy"),
            )
            for i in range(5)
        ]
        data = json.loads(format_json(_result(certain=pairs), limit=2))
        assert len(data["certain_duplicates"]) == 2
        assert data["certain_duplicates_total"] == 5

    def test_limit_zero_shows_all(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", f"Person {i}"),
                _ind(f"@I{i + 10}@", f"Person {i} Copy"),
            )
            for i in range(5)
        ]
        data = json.loads(format_json(_result(certain=pairs), limit=0))
        assert len(data["certain_duplicates"]) == 5
        assert data["certain_duplicates_total"] == 5

    def test_totals_equal_array_lengths_when_unlimited(self) -> None:
        pairs = [
            _pair(
                _ind(f"@I{i}@", f"Person {i}"),
                _ind(f"@I{i + 10}@", f"Person {i} Copy"),
            )
            for i in range(3)
        ]
        data = json.loads(format_json(_result(certain=pairs)))
        assert data["certain_duplicates_total"] == len(data["certain_duplicates"])
        assert data["probable_duplicates_total"] == len(data["probable_duplicates"])

    def test_totals_reflect_show_matches_filter(self) -> None:
        probable_pair = _pair(
            _ind("@I3@", "Bob"),
            _ind("@I4@", "Bobby"),
            score=_score(0.72, "probable"),
        )
        result = _result(
            certain=[_pair(_ALICE_A, _ALICE_B)],
            probable=[probable_pair],
        )
        data = json.loads(format_json(result, show_matches="certain"))
        assert data["certain_duplicates_total"] == 1
        assert data["probable_duplicates_total"] == 0


class TestJsonInsufficientData:
    def test_flag_present_when_set(self) -> None:
        pair = _pair(
            _ALICE_A,
            _ALICE_B,
            score=_score(0.75, "probable", insufficient_data=True),
        )
        data = json.loads(format_json(_result(probable=[pair])))
        match = data["probable_duplicates"][0]
        assert match["insufficient_data"] is True

    def test_flag_absent_when_not_set(self) -> None:
        pair = _pair(_ALICE_A, _ALICE_B, score=_score(insufficient_data=False))
        data = json.loads(format_json(_result(certain=[pair])))
        match = data["certain_duplicates"][0]
        assert "insufficient_data" not in match


class TestJsonEdgeCases:
    def test_empty_results(self) -> None:
        data = json.loads(format_json(_result()))
        assert data["certain_duplicates"] == []
        assert data["probable_duplicates"] == []
        assert data["certain_duplicates_total"] == 0
        assert data["probable_duplicates_total"] == 0
        assert data["total_individuals"] == 200

    def test_file_field(self) -> None:
        data = json.loads(format_json(_result()))
        assert data["file"] == "family.ged"
