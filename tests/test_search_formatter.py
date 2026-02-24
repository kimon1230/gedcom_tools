from __future__ import annotations

import json

from gedcom_tools.commands.search.formatter import (
    format_count,
    format_json,
    format_text,
)
from gedcom_tools.commands.search.models import (
    MatchDetail,
    SearchIndividual,
    SearchMatch,
    SearchResult,
)
from gedcom_tools.progress import Colors
from gedcom_tools.utils import EncodingInfo


def _colors() -> Colors:
    return Colors(force_disable=True)


def _encoding(
    encoding: str = "UTF-8",
    has_bom: bool = False,
    declared_charset: str | None = "UTF-8",
) -> EncodingInfo:
    return EncodingInfo(
        encoding=encoding, has_bom=has_bom, declared_charset=declared_charset
    )


def _make_individual(
    xref: str = "@I1@",
    given: str = "John",
    surname: str = "Smith",
    full_name: str = "John Smith",
    sex: str = "M",
    birth_year: int | None = 1850,
    death_year: int | None = 1920,
    birth_place: str = "London, England",
    death_place: str = "Manchester",
    birth_approx: bool = False,
    death_approx: bool = False,
    alt_names: list[tuple[str, str]] | None = None,
) -> SearchIndividual:
    return SearchIndividual(
        xref=xref,
        given_name=given,
        surname=surname,
        full_name=full_name,
        sex=sex,
        birth_year=birth_year,
        birth_year_approximate=birth_approx,
        birth_place=birth_place,
        death_year=death_year,
        death_year_approximate=death_approx,
        death_place=death_place,
        alt_names=alt_names or [],
    )


def _make_detail(
    field: str = "surname",
    matched_value: str = "Smith",
    query_term: str = "Smith",
    match_type: str = "contains",
) -> MatchDetail:
    return MatchDetail(
        field=field,
        matched_value=matched_value,
        query_term=query_term,
        match_type=match_type,
    )


def _make_result(
    matches: list[SearchMatch] | None = None,
    total_individuals: int = 100,
    truncated: bool = False,
    file_path: str = "/data/tree.ged",
    query_string: str = "surname:Smith",
) -> SearchResult:
    return SearchResult(
        file_path=file_path,
        query_string=query_string,
        encoding=_encoding(),
        total_individuals=total_individuals,
        matches=matches or [],
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Empty file case
# ---------------------------------------------------------------------------


class TestFormatTextEmpty:
    def test_zero_individuals_returns_short_message(self) -> None:
        result = _make_result(total_individuals=0)
        output = format_text(result, _colors())
        assert output == "No individuals found in file."

    def test_zero_individuals_ignores_quiet(self) -> None:
        result = _make_result(total_individuals=0)
        output = format_text(result, _colors(), quiet=True)
        assert output == "No individuals found in file."

    def test_zero_individuals_ignores_verbose(self) -> None:
        result = _make_result(total_individuals=0)
        output = format_text(result, _colors(), verbose=True)
        assert output == "No individuals found in file."


# ---------------------------------------------------------------------------
# No-matches case (individuals exist but nothing matched)
# ---------------------------------------------------------------------------


class TestFormatTextNormal:
    def test_header_shows_file_and_query(self) -> None:
        result = _make_result()
        output = format_text(result, _colors())
        assert "File: /data/tree.ged" in output
        assert "Query: surname:Smith" in output

    def test_no_matches_message(self) -> None:
        result = _make_result(matches=[])
        output = format_text(result, _colors())
        assert "No matches found." in output

    def test_no_matches_tip_text(self) -> None:
        result = _make_result(matches=[])
        output = format_text(result, _colors())
        assert "Tip:" in output
        assert "phonetic matching" in output
        assert "surname~Schmidt" in output

    def test_no_matches_shows_file_and_query(self) -> None:
        result = _make_result(matches=[])
        output = format_text(result, _colors())
        assert "File:" in output
        assert "Query:" in output

    def test_match_name_shown(self) -> None:
        ind = _make_individual(full_name="John Smith")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "John Smith" in output

    def test_match_xref_shown(self) -> None:
        ind = _make_individual(xref="@I42@")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "[@I42@]" in output

    def test_header_shows_count_and_total(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match], total_individuals=500)
        output = format_text(result, _colors())
        assert "1" in output
        assert "500" in output

    def test_header_uses_thousand_separator(self) -> None:
        matches = [
            SearchMatch(
                individual=_make_individual(xref=f"@I{i}@", full_name=f"P {i}"),
                details=[_make_detail()],
            )
            for i in range(3)
        ]
        result = _make_result(matches=matches, total_individuals=12_000)
        output = format_text(result, _colors())
        assert "12,000" in output

    def test_header_section_marker(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "=== Search Results" in output

    def test_match_detail_shown(self) -> None:
        detail = _make_detail(
            field="surname",
            matched_value="Smith",
            query_term="Smith",
            match_type="contains",
        )
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Matched:" in output
        assert "surname" in output

    def test_no_trailing_blank_line(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert not output.endswith("\n")

    def test_lifespan_in_match_line(self) -> None:
        ind = _make_individual(birth_year=1850, death_year=1920)
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "(1850-1920)" in output

    def test_multiple_matches_all_shown(self) -> None:
        inds = [
            _make_individual(xref=f"@I{i}@", full_name=f"Person {i}") for i in range(3)
        ]
        matches = [
            SearchMatch(individual=ind, details=[_make_detail()]) for ind in inds
        ]
        result = _make_result(matches=matches)
        output = format_text(result, _colors())
        for i in range(3):
            assert f"Person {i}" in output


# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------


class TestFormatTextQuiet:
    def test_quiet_one_line_per_match(self) -> None:
        inds = [
            _make_individual(xref=f"@I{i}@", full_name=f"Person {i}") for i in range(3)
        ]
        matches = [
            SearchMatch(individual=ind, details=[_make_detail()]) for ind in inds
        ]
        result = _make_result(matches=matches)
        output = format_text(result, _colors(), quiet=True)
        lines = output.splitlines()
        assert len(lines) == 3

    def test_quiet_format_contains_name_lifespan_xref(self) -> None:
        ind = _make_individual(
            full_name="John Smith", birth_year=1850, death_year=1920, xref="@I1@"
        )
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors(), quiet=True)
        assert "John Smith" in output
        assert "(1850-1920)" in output
        assert "[@I1@]" in output

    def test_quiet_no_file_header(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors(), quiet=True)
        assert "File:" not in output
        assert "Query:" not in output

    def test_quiet_no_born_died_lines(self) -> None:
        ind = _make_individual(birth_year=1850, death_year=1920)
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors(), quiet=True)
        assert "Born:" not in output
        assert "Died:" not in output

    def test_quiet_no_matches_returns_empty(self) -> None:
        result = _make_result(matches=[])
        output = format_text(result, _colors(), quiet=True)
        assert output == ""

    def test_quiet_missing_years_use_question_mark(self) -> None:
        ind = _make_individual(birth_year=None, death_year=None)
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors(), quiet=True)
        assert "(?-?)" in output


# ---------------------------------------------------------------------------
# Born/Died line formatting
# ---------------------------------------------------------------------------


class TestBornDiedFormatting:
    def test_born_line_with_place(self) -> None:
        ind = _make_individual(birth_year=1850, birth_place="London, England")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Born: 1850, London, England" in output

    def test_born_line_without_place(self) -> None:
        ind = _make_individual(birth_year=1850, birth_place="")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Born: 1850" in output
        assert "Born: 1850," not in output

    def test_died_line_with_place(self) -> None:
        ind = _make_individual(death_year=1920, death_place="Manchester")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Died: 1920, Manchester" in output

    def test_died_line_without_place(self) -> None:
        ind = _make_individual(death_year=1920, death_place="")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Died: 1920" in output
        assert "Died: 1920," not in output

    def test_born_omitted_when_year_none(self) -> None:
        ind = _make_individual(birth_year=None, birth_place="London")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Born:" not in output

    def test_died_omitted_when_year_none(self) -> None:
        ind = _make_individual(death_year=None, death_place="Manchester")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Died:" not in output

    def test_born_died_both_omitted_when_both_none(self) -> None:
        ind = _make_individual(birth_year=None, death_year=None)
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "Born:" not in output
        assert "Died:" not in output

    def test_born_line_indented(self) -> None:
        ind = _make_individual(birth_year=1850, birth_place="")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        for line in output.splitlines():
            if "Born:" in line:
                assert line.startswith("    ")
                break

    def test_died_line_indented(self) -> None:
        ind = _make_individual(death_year=1920, death_place="")
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        for line in output.splitlines():
            if "Died:" in line:
                assert line.startswith("    ")
                break


# ---------------------------------------------------------------------------
# Match type text templates
# ---------------------------------------------------------------------------


class TestFormatTextMatchTypes:
    def test_contains_template(self) -> None:
        detail = _make_detail(field="surname", query_term="Smi", match_type="contains")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert 'surname contains "Smi"' in output

    def test_exactly_template(self) -> None:
        detail = _make_detail(field="given", query_term="John", match_type="exactly")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert 'given exactly "John"' in output

    def test_pattern_template(self) -> None:
        detail = _make_detail(field="surname", query_term="Sm*th", match_type="pattern")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert 'surname matches pattern "Sm*th"' in output

    def test_sounds_like_template(self) -> None:
        detail = _make_detail(
            field="surname",
            matched_value="Schmidt",
            query_term="Smith",
            match_type="sounds_like",
        )
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert 'surname "Schmidt" sounds like "Smith"' in output

    def test_regex_template(self) -> None:
        detail = _make_detail(field="place", query_term="lon.*eng", match_type="regex")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert 'place matches "lon.*eng"' in output

    def test_range_template_no_quotes(self) -> None:
        detail = _make_detail(field="born", query_term="1800-1900", match_type="range")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "born in 1800-1900" in output
        # range value must NOT be quoted
        assert 'born in "1800-1900"' not in output

    def test_multiple_details_joined_with_comma(self) -> None:
        details = [
            _make_detail(field="surname", query_term="Smith", match_type="contains"),
            _make_detail(field="born", query_term="1850", match_type="range"),
        ]
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=details)
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        matched_line = next(line for line in output.splitlines() if "Matched:" in line)
        assert "," in matched_line


# ---------------------------------------------------------------------------
# Verbose mode (Soundex code display)
# ---------------------------------------------------------------------------


class TestFormatTextVerbose:
    def test_verbose_shows_soundex_code_for_sounds_like(self) -> None:
        detail = _make_detail(
            field="surname",
            matched_value="Schmidt",
            query_term="Smith",
            match_type="sounds_like",
        )
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors(), verbose=True)
        # Soundex of "smith" → S530
        assert "(S530)" in output

    def test_verbose_soundex_code_appended_to_sounds_like(self) -> None:
        detail = _make_detail(
            field="surname",
            matched_value="Schmidt",
            query_term="Schmidt",
            match_type="sounds_like",
        )
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output_verbose = format_text(result, _colors(), verbose=True)
        output_normal = format_text(result, _colors(), verbose=False)
        # verbose adds parens with soundex, normal does not
        assert "(" in output_verbose
        assert output_verbose != output_normal

    def test_non_verbose_no_soundex_code(self) -> None:
        detail = _make_detail(
            field="surname",
            matched_value="Schmidt",
            query_term="Smith",
            match_type="sounds_like",
        )
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        output = format_text(result, _colors(), verbose=False)
        assert "S530" not in output

    def test_verbose_no_effect_on_contains(self) -> None:
        detail = _make_detail(
            field="surname", query_term="Smith", match_type="contains"
        )
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        normal = format_text(result, _colors(), verbose=False)
        verbose = format_text(result, _colors(), verbose=True)
        assert normal == verbose

    def test_verbose_no_effect_on_exactly(self) -> None:
        detail = _make_detail(field="surname", query_term="Smith", match_type="exactly")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        assert format_text(result, _colors(), verbose=False) == format_text(
            result, _colors(), verbose=True
        )

    def test_verbose_no_effect_on_range(self) -> None:
        detail = _make_detail(field="born", query_term="1800-1900", match_type="range")
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[detail])
        result = _make_result(matches=[match])
        assert format_text(result, _colors(), verbose=False) == format_text(
            result, _colors(), verbose=True
        )


# ---------------------------------------------------------------------------
# Truncated flag
# ---------------------------------------------------------------------------


class TestFormatTextTruncated:
    def test_truncated_appends_limit_message(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match], truncated=True)
        output = format_text(result, _colors())
        assert "results limited to 1" in output
        assert "--limit 0" in output

    def test_not_truncated_no_limit_message(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match], truncated=False)
        output = format_text(result, _colors())
        assert "--limit 0" not in output

    def test_truncated_message_shows_match_count(self) -> None:
        inds = [
            _make_individual(xref=f"@I{i}@", full_name=f"Person {i}") for i in range(5)
        ]
        matches = [
            SearchMatch(individual=ind, details=[_make_detail()]) for ind in inds
        ]
        result = _make_result(matches=matches, truncated=True)
        output = format_text(result, _colors())
        assert "results limited to 5" in output

    def test_truncated_zero_matches_no_message(self) -> None:
        # truncated flag with zero matches is pathological, but should not crash
        result = _make_result(matches=[], truncated=True)
        output = format_text(result, _colors())
        assert "No matches found." in output


# ---------------------------------------------------------------------------
# format_json structure
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_returns_valid_json(self) -> None:
        result = _make_result()
        parsed = json.loads(format_json(result))
        assert isinstance(parsed, dict)

    def test_top_level_keys_present(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        required = {
            "file",
            "query",
            "encoding",
            "total_individuals",
            "match_count",
            "truncated",
            "matches",
        }
        assert required <= set(data.keys())

    def test_file_and_query_values(self) -> None:
        result = _make_result(file_path="/trees/my.ged", query_string="name:Jones")
        data = json.loads(format_json(result))
        assert data["file"] == "/trees/my.ged"
        assert data["query"] == "name:Jones"

    def test_total_individuals_value(self) -> None:
        result = _make_result(total_individuals=250)
        data = json.loads(format_json(result))
        assert data["total_individuals"] == 250

    def test_match_count_equals_len_matches(self) -> None:
        inds = [
            _make_individual(xref=f"@I{i}@", full_name=f"Person {i}") for i in range(4)
        ]
        matches = [SearchMatch(individual=ind, details=[]) for ind in inds]
        result = _make_result(matches=matches)
        data = json.loads(format_json(result))
        assert data["match_count"] == 4
        assert len(data["matches"]) == 4

    def test_truncated_flag_true(self) -> None:
        result = _make_result(truncated=True)
        data = json.loads(format_json(result))
        assert data["truncated"] is True

    def test_truncated_flag_false(self) -> None:
        result = _make_result(truncated=False)
        data = json.loads(format_json(result))
        assert data["truncated"] is False

    def test_encoding_subkeys(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        enc = data["encoding"]
        assert "detected" in enc
        assert "has_bom" in enc
        assert "declared" in enc

    def test_encoding_values(self) -> None:
        result = SearchResult(
            file_path="/f.ged",
            query_string="",
            encoding=EncodingInfo(
                encoding="ANSEL", has_bom=False, declared_charset="ANSEL"
            ),
            total_individuals=0,
            matches=[],
            truncated=False,
        )
        data = json.loads(format_json(result))
        assert data["encoding"]["detected"] == "ANSEL"
        assert data["encoding"]["has_bom"] is False
        assert data["encoding"]["declared"] == "ANSEL"

    def test_encoding_declared_null_when_none(self) -> None:
        result = SearchResult(
            file_path="/f.ged",
            query_string="",
            encoding=EncodingInfo(
                encoding="UTF-8", has_bom=False, declared_charset=None
            ),
            total_individuals=0,
            matches=[],
            truncated=False,
        )
        data = json.loads(format_json(result))
        assert data["encoding"]["declared"] is None

    def test_empty_matches_array(self) -> None:
        result = _make_result(matches=[])
        data = json.loads(format_json(result))
        assert data["matches"] == []


# ---------------------------------------------------------------------------
# format_json per-match fields
# ---------------------------------------------------------------------------


class TestFormatJsonFields:
    def _single_match_data(
        self,
        ind: SearchIndividual | None = None,
        details: list[MatchDetail] | None = None,
    ) -> dict:  # type: ignore[type-arg]
        if ind is None:
            ind = _make_individual()
        match = SearchMatch(individual=ind, details=details or [])
        result = _make_result(matches=[match])
        data = json.loads(format_json(result))
        return data["matches"][0]

    def test_individual_fields_present(self) -> None:
        entry = self._single_match_data()
        required = {
            "xref",
            "given_name",
            "surname",
            "sex",
            "birth_year",
            "birth_year_approximate",
            "birth_place",
            "death_year",
            "death_year_approximate",
            "death_place",
            "alt_names",
            "match_details",
        }
        assert required <= set(entry.keys())

    def test_individual_values(self) -> None:
        ind = _make_individual(
            xref="@I5@",
            given="Mary",
            surname="Jones",
            sex="F",
            birth_year=1880,
            death_year=1955,
            birth_place="Dublin",
            death_place="Cork",
            birth_approx=True,
            death_approx=False,
        )
        entry = self._single_match_data(ind)
        assert entry["xref"] == "@I5@"
        assert entry["given_name"] == "Mary"
        assert entry["surname"] == "Jones"
        assert entry["sex"] == "F"
        assert entry["birth_year"] == 1880
        assert entry["birth_year_approximate"] is True
        assert entry["birth_place"] == "Dublin"
        assert entry["death_year"] == 1955
        assert entry["death_year_approximate"] is False
        assert entry["death_place"] == "Cork"

    def test_null_birth_year(self) -> None:
        ind = _make_individual(birth_year=None)
        entry = self._single_match_data(ind)
        assert entry["birth_year"] is None

    def test_null_death_year(self) -> None:
        ind = _make_individual(death_year=None)
        entry = self._single_match_data(ind)
        assert entry["death_year"] is None

    def test_alt_names_structure(self) -> None:
        ind = _make_individual(alt_names=[("Marie", "Dupont"), ("Maria", "Schmidt")])
        entry = self._single_match_data(ind)
        assert len(entry["alt_names"]) == 2
        first = entry["alt_names"][0]
        assert "given" in first
        assert "surname" in first
        assert first["given"] == "Marie"
        assert first["surname"] == "Dupont"

    def test_alt_names_empty(self) -> None:
        ind = _make_individual(alt_names=[])
        entry = self._single_match_data(ind)
        assert entry["alt_names"] == []

    def test_full_name_not_in_json(self) -> None:
        ind = _make_individual(full_name="John Smith")
        entry = self._single_match_data(ind)
        assert "full_name" not in entry

    def test_norm_fields_not_in_json(self) -> None:
        ind = _make_individual()
        entry = self._single_match_data(ind)
        for key in entry:
            assert not key.endswith(
                "_norm"
            ), f"Unexpected normalized field in JSON: {key}"

    def test_soundex_fields_not_in_json(self) -> None:
        ind = _make_individual()
        entry = self._single_match_data(ind)
        for key in entry:
            assert "soundex" not in key, f"Unexpected soundex field in JSON: {key}"

    def test_match_details_key_mapping(self) -> None:
        detail = MatchDetail(
            field="surname",
            matched_value="Schmid",
            query_term="Schmidt",
            match_type="sounds_like",
        )
        entry = self._single_match_data(details=[detail])
        md = entry["match_details"][0]
        # Internal field names must be remapped in JSON output
        assert "field" in md
        assert "value" in md  # matched_value → value
        assert "query" in md  # query_term → query
        assert "type" in md  # match_type → type
        assert "matched_value" not in md
        assert "query_term" not in md
        assert "match_type" not in md

    def test_match_details_values(self) -> None:
        detail = MatchDetail(
            field="born",
            matched_value="1850",
            query_term="1800-1900",
            match_type="range",
        )
        entry = self._single_match_data(details=[detail])
        md = entry["match_details"][0]
        assert md["field"] == "born"
        assert md["value"] == "1850"
        assert md["query"] == "1800-1900"
        assert md["type"] == "range"

    def test_match_details_empty(self) -> None:
        entry = self._single_match_data(details=[])
        assert entry["match_details"] == []

    def test_multiple_match_details(self) -> None:
        details = [
            MatchDetail(
                field="surname",
                matched_value="Smith",
                query_term="Smith",
                match_type="contains",
            ),
            MatchDetail(
                field="born",
                matched_value="1850",
                query_term="1800-1900",
                match_type="range",
            ),
        ]
        entry = self._single_match_data(details=details)
        assert len(entry["match_details"]) == 2


# ---------------------------------------------------------------------------
# format_count
# ---------------------------------------------------------------------------


class TestFormatCount:
    def test_text_mode_bare_integer(self) -> None:
        ind = _make_individual()
        matches = [SearchMatch(individual=ind, details=[]) for _ in range(7)]
        result = _make_result(matches=matches)
        output = format_count(result, json_mode=False)
        assert output == "7"

    def test_text_mode_zero(self) -> None:
        result = _make_result(matches=[])
        output = format_count(result, json_mode=False)
        assert output == "0"

    def test_json_mode_structure(self) -> None:
        ind = _make_individual()
        matches = [SearchMatch(individual=ind, details=[]) for _ in range(3)]
        result = _make_result(matches=matches)
        output = format_count(result, json_mode=True)
        data = json.loads(output)
        assert data == {"count": 3}

    def test_json_mode_zero(self) -> None:
        result = _make_result(matches=[])
        output = format_count(result, json_mode=True)
        data = json.loads(output)
        assert data == {"count": 0}

    def test_json_mode_default_false(self) -> None:
        result = _make_result(matches=[])
        output = format_count(result)
        assert output == "0"

    def test_text_mode_is_just_integer_string(self) -> None:
        # No labels, no extra text — just the number
        ind = _make_individual()
        matches = [SearchMatch(individual=ind, details=[]) for _ in range(12)]
        result = _make_result(matches=matches)
        output = format_count(result, json_mode=False)
        assert output.strip() == "12"
        assert output.isdigit()


# ---------------------------------------------------------------------------
# Colors disabled (no ANSI bleed)
# ---------------------------------------------------------------------------


class TestColorsDisabled:
    def test_no_ansi_codes_in_output(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "\033[" not in output

    def test_header_still_visible_without_color(self) -> None:
        ind = _make_individual()
        match = SearchMatch(individual=ind, details=[_make_detail()])
        result = _make_result(matches=[match])
        output = format_text(result, _colors())
        assert "=== Search Results" in output
