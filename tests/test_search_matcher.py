from __future__ import annotations

from gedcom_tools.commands.search.matcher import match_individual
from gedcom_tools.commands.search.models import (
    SearchIndividual,
    SearchQuery,
    SearchTerm,
)
from gedcom_tools.phonetics import soundex
from gedcom_tools.utils import normalize_compare, normalize_display


def _make_individual(
    xref: str = "@I1@",
    given: str = "John",
    surname: str = "Smith",
    sex: str = "M",
    birth_year: int | None = 1850,
    birth_approx: bool = False,
    birth_place: str = "London, England",
    death_year: int | None = 1920,
    death_approx: bool = False,
    death_place: str = "Manchester",
    alt_names: list[tuple[str, str]] | None = None,
) -> SearchIndividual:
    given_disp = normalize_display(given)
    surname_disp = normalize_display(surname)
    full_name = f"{given_disp} {surname_disp}".strip()

    given_norm = normalize_compare(given_disp)
    surname_norm = normalize_compare(surname_disp)
    full_name_norm = normalize_compare(full_name)
    birth_place_disp = normalize_display(birth_place)
    death_place_disp = normalize_display(death_place)
    birth_place_norm = normalize_compare(birth_place_disp)
    death_place_norm = normalize_compare(death_place_disp)

    alts = alt_names or []
    alt_disp = [(normalize_display(g), normalize_display(s)) for g, s in alts]
    alt_norm = [(normalize_compare(g), normalize_compare(s)) for g, s in alt_disp]
    alt_sx = [(soundex(g_n), soundex(s_n)) for g_n, s_n in alt_norm]

    return SearchIndividual(
        xref=xref,
        given_name=given_disp,
        surname=surname_disp,
        full_name=full_name,
        sex=sex,
        birth_year=birth_year,
        birth_year_approximate=birth_approx,
        birth_place=birth_place_disp,
        death_year=death_year,
        death_year_approximate=death_approx,
        death_place=death_place_disp,
        alt_names=alt_disp,
        given_name_norm=given_norm,
        surname_norm=surname_norm,
        full_name_norm=full_name_norm,
        birth_place_norm=birth_place_norm,
        death_place_norm=death_place_norm,
        alt_names_norm=alt_norm,
        surname_soundex=soundex(surname_norm),
        given_name_soundex=soundex(given_norm),
        alt_soundex=alt_sx,
    )


def _term(
    field: str = "name",
    operator: str = ":",
    value: str = "Smith",
    is_wildcard: bool = False,
    date_range: tuple[int, int] | None = None,
) -> SearchTerm:
    return SearchTerm(
        field=field,
        operator=operator,
        value=value,
        is_wildcard=is_wildcard,
        date_range=date_range,
    )


def _query(
    terms: list[SearchTerm],
    regex_mode: bool = False,
    fuzzy_dates: int | None = None,
) -> SearchQuery:
    return SearchQuery(
        terms=terms,
        regex_mode=regex_mode,
        fuzzy_dates=fuzzy_dates,
        limit=None,
        count_only=False,
    )


# ---------------------------------------------------------------------------
# Substring matching
# ---------------------------------------------------------------------------


class TestSubstringMatch:
    def test_name_contains(self) -> None:
        ind = _make_individual(given="John", surname="Smith")
        result = match_individual(ind, _query([_term(value="Smi")]))
        assert result is not None
        assert result.details[0].match_type == "contains"

    def test_case_insensitive(self) -> None:
        ind = _make_individual(surname="Smith")
        result = match_individual(ind, _query([_term(value="SMITH")]))
        assert result is not None

    def test_surname_substring(self) -> None:
        ind = _make_individual(surname="Blacksmith")
        result = match_individual(ind, _query([_term(field="surname", value="smith")]))
        assert result is not None
        assert result.details[0].matched_value == "Blacksmith"

    def test_given_substring(self) -> None:
        ind = _make_individual(given="Jonathan")
        result = match_individual(ind, _query([_term(field="given", value="Jon")]))
        assert result is not None

    def test_no_match(self) -> None:
        ind = _make_individual(given="John", surname="Smith")
        result = match_individual(ind, _query([_term(value="Williams")]))
        assert result is None

    def test_place_matches_birth(self) -> None:
        ind = _make_individual(birth_place="London, England")
        result = match_individual(ind, _query([_term(field="place", value="London")]))
        assert result is not None
        assert result.details[0].matched_value == "London, England"

    def test_place_matches_death(self) -> None:
        ind = _make_individual(birth_place="", death_place="Manchester")
        result = match_individual(
            ind, _query([_term(field="place", value="Manchester")])
        )
        assert result is not None
        assert result.details[0].matched_value == "Manchester"

    def test_place_no_match(self) -> None:
        ind = _make_individual(birth_place="London", death_place="Manchester")
        result = match_individual(ind, _query([_term(field="place", value="Berlin")]))
        assert result is None

    def test_name_matches_full_name(self) -> None:
        ind = _make_individual(given="John", surname="Smith")
        result = match_individual(ind, _query([_term(value="John Smith")]))
        assert result is not None
        assert result.details[0].matched_value == "John Smith"


# ---------------------------------------------------------------------------
# Exact matching
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_exact_surname(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", operator="=", value="Smith")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "exactly"

    def test_exact_rejects_substring(self) -> None:
        ind = _make_individual(surname="Blacksmith")
        q = _query([_term(field="surname", operator="=", value="Smith")])
        result = match_individual(ind, q)
        assert result is None

    def test_exact_case_insensitive(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", operator="=", value="SMITH")])
        result = match_individual(ind, q)
        assert result is not None

    def test_exact_place(self) -> None:
        ind = _make_individual(birth_place="London, England")
        q = _query([_term(field="place", operator="=", value="London, England")])
        result = match_individual(ind, q)
        assert result is not None

    def test_exact_place_partial_no_match(self) -> None:
        ind = _make_individual(birth_place="London, England")
        q = _query([_term(field="place", operator="=", value="London")])
        result = match_individual(ind, q)
        assert result is None


# ---------------------------------------------------------------------------
# Wildcard matching
# ---------------------------------------------------------------------------


class TestWildcardMatch:
    def test_asterisk_middle(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", value="Sm*th", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "pattern"

    def test_asterisk_end(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", value="Smi*", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is not None

    def test_question_mark(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", value="Sm?th", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is not None

    def test_question_mark_wrong_length(self) -> None:
        ind = _make_individual(surname="Smythe")
        q = _query([_term(field="surname", value="Sm?th", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is None

    def test_anchored_rejects_partial(self) -> None:
        ind = _make_individual(surname="Blacksmith")
        q = _query([_term(field="surname", value="Smi*", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is None

    def test_metacharacter_escaping(self) -> None:
        ind = _make_individual(surname="Smith.Jr")
        q = _query([_term(field="surname", value="Smi*.Jr", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is not None

    def test_dot_not_treated_as_regex_wildcard(self) -> None:
        # "Smith-Jr" should NOT match "Smi*.Jr" because dot is escaped
        ind = _make_individual(surname="Smith-Jr")
        q = _query([_term(field="surname", value="Smi*.Jr", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is None

    def test_wildcard_on_name_field(self) -> None:
        ind = _make_individual(given="John", surname="Smith")
        q = _query([_term(field="name", value="John*Smith", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is not None

    def test_wildcard_place(self) -> None:
        ind = _make_individual(birth_place="London, England")
        q = _query([_term(field="place", value="Lon*", is_wildcard=True)])
        result = match_individual(ind, q)
        assert result is not None


# ---------------------------------------------------------------------------
# Soundex matching
# ---------------------------------------------------------------------------


class TestSoundexMatch:
    def test_soundex_surname(self) -> None:
        ind = _make_individual(surname="Schmidt")
        q = _query([_term(field="surname", operator="~", value="Schmid")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "sounds_like"

    def test_soundex_no_match(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", operator="~", value="Johnson")])
        result = match_individual(ind, q)
        assert result is None

    def test_soundex_given(self) -> None:
        ind = _make_individual(given="John")
        q = _query([_term(field="given", operator="~", value="Jon")])
        result = match_individual(ind, q)
        assert result is not None

    def test_soundex_name_field_checks_surname(self) -> None:
        ind = _make_individual(surname="Schmidt")
        q = _query([_term(field="name", operator="~", value="Schmidt")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Schmidt"

    def test_soundex_empty_name(self) -> None:
        ind = _make_individual(given="", surname="")
        q = _query([_term(field="name", operator="~", value="Smith")])
        result = match_individual(ind, q)
        assert result is None

    def test_soundex_matched_value_is_display_form(self) -> None:
        ind = _make_individual(surname="Schmid")
        q = _query([_term(field="surname", operator="~", value="Schmidt")])
        result = match_individual(ind, q)
        assert result is not None
        # matched_value should be the individual's display surname
        assert result.details[0].matched_value == "Schmid"


# ---------------------------------------------------------------------------
# Regex matching
# ---------------------------------------------------------------------------


class TestRegexMatch:
    def test_regex_surname(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", value=r"\bsmith\b")], regex_mode=True)
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "regex"

    def test_regex_case_insensitive(self) -> None:
        ind = _make_individual(surname="Schmidt")
        q = _query([_term(field="surname", value="sch.*dt")], regex_mode=True)
        result = match_individual(ind, q)
        assert result is not None

    def test_regex_no_match(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query([_term(field="surname", value="^jones$")], regex_mode=True)
        result = match_individual(ind, q)
        assert result is None

    def test_regex_does_not_affect_exact(self) -> None:
        ind = _make_individual(surname="Smith")
        q = _query(
            [_term(field="surname", operator="=", value="Smith")], regex_mode=True
        )
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "exactly"

    def test_regex_does_not_affect_soundex(self) -> None:
        ind = _make_individual(surname="Schmidt")
        q = _query(
            [_term(field="surname", operator="~", value="Schmidt")], regex_mode=True
        )
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "sounds_like"

    def test_regex_place(self) -> None:
        ind = _make_individual(birth_place="London, England")
        q = _query([_term(field="place", value="lond.*eng")], regex_mode=True)
        result = match_individual(ind, q)
        assert result is not None


# ---------------------------------------------------------------------------
# Date range matching
# ---------------------------------------------------------------------------


class TestDateRangeMatch:
    def test_single_year(self) -> None:
        ind = _make_individual(birth_year=1850)
        q = _query([_term(field="born", value="1850", date_range=(1850, 1850))])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].match_type == "range"
        assert result.details[0].matched_value == "1850"

    def test_year_in_range(self) -> None:
        ind = _make_individual(birth_year=1850)
        q = _query([_term(field="born", value="1800-1900", date_range=(1800, 1900))])
        result = match_individual(ind, q)
        assert result is not None

    def test_year_outside_range(self) -> None:
        ind = _make_individual(birth_year=1750)
        q = _query([_term(field="born", value="1800-1900", date_range=(1800, 1900))])
        result = match_individual(ind, q)
        assert result is None

    def test_boundary_start(self) -> None:
        ind = _make_individual(birth_year=1800)
        q = _query([_term(field="born", value="1800-1900", date_range=(1800, 1900))])
        result = match_individual(ind, q)
        assert result is not None

    def test_boundary_end(self) -> None:
        ind = _make_individual(birth_year=1900)
        q = _query([_term(field="born", value="1800-1900", date_range=(1800, 1900))])
        result = match_individual(ind, q)
        assert result is not None

    def test_death_year(self) -> None:
        ind = _make_individual(death_year=1920)
        q = _query([_term(field="died", value="1920", date_range=(1920, 1920))])
        result = match_individual(ind, q)
        assert result is not None

    def test_none_year_no_match(self) -> None:
        ind = _make_individual(birth_year=None)
        q = _query([_term(field="born", value="1850", date_range=(1850, 1850))])
        result = match_individual(ind, q)
        assert result is None


# ---------------------------------------------------------------------------
# Fuzzy dates
# ---------------------------------------------------------------------------


class TestFuzzyDates:
    def test_expanded_range_match(self) -> None:
        # birth_year=1855, range=1800-1850, fuzzy=5 → expands to 1795-1855
        ind = _make_individual(birth_year=1855, birth_approx=True)
        q = _query(
            [_term(field="born", value="1800-1850", date_range=(1800, 1850))],
            fuzzy_dates=5,
        )
        result = match_individual(ind, q)
        assert result is not None

    def test_not_applied_to_exact_dates(self) -> None:
        # birth_year=1855, NOT approximate → fuzzy expansion doesn't apply
        ind = _make_individual(birth_year=1855, birth_approx=False)
        q = _query(
            [_term(field="born", value="1800-1850", date_range=(1800, 1850))],
            fuzzy_dates=5,
        )
        result = match_individual(ind, q)
        assert result is None

    def test_fuzzy_death(self) -> None:
        ind = _make_individual(death_year=1925, death_approx=True)
        q = _query(
            [_term(field="died", value="1920", date_range=(1920, 1920))],
            fuzzy_dates=5,
        )
        result = match_individual(ind, q)
        assert result is not None

    def test_outside_expanded_range(self) -> None:
        # 1860 > 1855 (1850+5) → no match even with fuzzy
        ind = _make_individual(birth_year=1860, birth_approx=True)
        q = _query(
            [_term(field="born", value="1800-1850", date_range=(1800, 1850))],
            fuzzy_dates=5,
        )
        result = match_individual(ind, q)
        assert result is None

    def test_fuzzy_expands_start(self) -> None:
        # birth_year=1795, range=1800-1850, fuzzy=5 → expands to 1795-1855
        ind = _make_individual(birth_year=1795, birth_approx=True)
        q = _query(
            [_term(field="born", value="1800-1850", date_range=(1800, 1850))],
            fuzzy_dates=5,
        )
        result = match_individual(ind, q)
        assert result is not None

    def test_no_fuzzy_when_none(self) -> None:
        # fuzzy_dates=None means no expansion even for approximate
        ind = _make_individual(birth_year=1855, birth_approx=True)
        q = _query(
            [_term(field="born", value="1800-1850", date_range=(1800, 1850))],
            fuzzy_dates=None,
        )
        result = match_individual(ind, q)
        assert result is None


# ---------------------------------------------------------------------------
# Sex matching
# ---------------------------------------------------------------------------


class TestSexMatch:
    def test_match(self) -> None:
        ind = _make_individual(sex="M")
        result = match_individual(ind, _query([_term(field="sex", value="M")]))
        assert result is not None

    def test_no_match(self) -> None:
        ind = _make_individual(sex="M")
        result = match_individual(ind, _query([_term(field="sex", value="F")]))
        assert result is None

    def test_case_insensitive(self) -> None:
        ind = _make_individual(sex="F")
        result = match_individual(ind, _query([_term(field="sex", value="f")]))
        assert result is not None

    def test_empty_sex_no_match(self) -> None:
        ind = _make_individual(sex="")
        result = match_individual(ind, _query([_term(field="sex", value="M")]))
        assert result is None

    def test_nonstandard_sex_value(self) -> None:
        ind = _make_individual(sex="X")
        result = match_individual(ind, _query([_term(field="sex", value="X")]))
        assert result is not None


# ---------------------------------------------------------------------------
# Alt names
# ---------------------------------------------------------------------------


class TestAltNames:
    def test_surname_matches_alt(self) -> None:
        ind = _make_individual(surname="Williams", alt_names=[("Marie", "Johnson")])
        q = _query([_term(field="surname", value="Johnson")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Johnson"

    def test_given_matches_alt(self) -> None:
        ind = _make_individual(
            given="Mary", surname="Williams", alt_names=[("Marie", "Johnson")]
        )
        q = _query([_term(field="given", value="Marie")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Marie"

    def test_soundex_matches_alt_surname(self) -> None:
        ind = _make_individual(surname="Williams", alt_names=[("", "Schmidt")])
        q = _query([_term(field="surname", operator="~", value="Schmid")])
        result = match_individual(ind, q)
        assert result is not None

    def test_name_field_matches_alt_full(self) -> None:
        ind = _make_individual(
            given="Mary",
            surname="Williams",
            alt_names=[("Marie", "Johnson")],
        )
        q = _query([_term(value="Marie Johnson")])
        result = match_individual(ind, q)
        assert result is not None

    def test_multiple_alt_names(self) -> None:
        ind = _make_individual(
            given="Mary",
            surname="Williams",
            alt_names=[("Maria", "Garcia"), ("Marie", "Johnson")],
        )
        q = _query([_term(field="surname", value="Garcia")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Garcia"

    def test_soundex_given_alt(self) -> None:
        ind = _make_individual(
            given="Mary", surname="Williams", alt_names=[("Jon", "Smith")]
        )
        q = _query([_term(field="given", operator="~", value="John")])
        result = match_individual(ind, q)
        assert result is not None


# ---------------------------------------------------------------------------
# AND logic
# ---------------------------------------------------------------------------


class TestAndLogic:
    def test_all_match(self) -> None:
        ind = _make_individual(surname="Smith", sex="M", birth_year=1850)
        q = _query(
            [
                _term(field="surname", value="Smith"),
                _term(field="sex", value="M"),
                _term(field="born", value="1850", date_range=(1850, 1850)),
            ]
        )
        result = match_individual(ind, q)
        assert result is not None
        assert len(result.details) == 3

    def test_one_fails(self) -> None:
        ind = _make_individual(surname="Smith", sex="M")
        q = _query(
            [
                _term(field="surname", value="Smith"),
                _term(field="sex", value="F"),
            ]
        )
        result = match_individual(ind, q)
        assert result is None

    def test_first_fails_short_circuits(self) -> None:
        ind = _make_individual(surname="Jones", sex="M")
        q = _query(
            [
                _term(field="surname", value="Smith"),
                _term(field="sex", value="M"),
            ]
        )
        result = match_individual(ind, q)
        assert result is None


# ---------------------------------------------------------------------------
# Relationship pre-filter
# ---------------------------------------------------------------------------


class TestRelationshipPreFilter:
    def test_in_set(self) -> None:
        ind = _make_individual(xref="@I1@")
        q = _query([_term(value="John")])
        result = match_individual(ind, q, relationship_xrefs={"@I1@", "@I2@"})
        assert result is not None

    def test_not_in_set(self) -> None:
        ind = _make_individual(xref="@I3@")
        q = _query([_term(value="John")])
        result = match_individual(ind, q, relationship_xrefs={"@I1@", "@I2@"})
        assert result is None

    def test_relationship_only_query(self) -> None:
        ind = _make_individual(xref="@I1@")
        q = _query([_term(field="ancestor", value="@I99@")])
        result = match_individual(ind, q, relationship_xrefs={"@I1@"})
        assert result is not None
        assert result.details == []

    def test_relationship_plus_field(self) -> None:
        ind = _make_individual(xref="@I1@", surname="Smith")
        q = _query(
            [
                _term(field="ancestor", value="@I99@"),
                _term(field="surname", value="Smith"),
            ]
        )
        result = match_individual(ind, q, relationship_xrefs={"@I1@"})
        assert result is not None
        assert len(result.details) == 1
        assert result.details[0].field == "surname"

    def test_empty_set_no_match(self) -> None:
        ind = _make_individual(xref="@I1@")
        q = _query([_term(field="ancestor", value="@I99@")])
        result = match_individual(ind, q, relationship_xrefs=set())
        assert result is None

    def test_none_set_no_filter(self) -> None:
        ind = _make_individual(xref="@I1@")
        q = _query([_term(value="John")])
        result = match_individual(ind, q, relationship_xrefs=None)
        assert result is not None


# ---------------------------------------------------------------------------
# Diacritic handling
# ---------------------------------------------------------------------------


class TestDiacritics:
    def test_query_without_diacritics_matches(self) -> None:
        ind = _make_individual(surname="M\u00fcller")
        q = _query([_term(field="surname", value="Muller")])
        result = match_individual(ind, q)
        assert result is not None

    def test_query_with_diacritics_matches_plain(self) -> None:
        ind = _make_individual(surname="Muller")
        q = _query([_term(field="surname", value="M\u00fcller")])
        result = match_individual(ind, q)
        assert result is not None

    def test_diacritic_exact_match(self) -> None:
        ind = _make_individual(surname="M\u00fcller")
        q = _query([_term(field="surname", operator="=", value="Muller")])
        result = match_individual(ind, q)
        assert result is not None

    def test_diacritic_soundex(self) -> None:
        ind = _make_individual(surname="M\u00fcller")
        q = _query([_term(field="surname", operator="~", value="Muller")])
        result = match_individual(ind, q)
        assert result is not None

    def test_matched_value_preserves_display(self) -> None:
        ind = _make_individual(surname="M\u00fcller")
        q = _query([_term(field="surname", value="muller")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "M\u00fcller"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_given_name(self) -> None:
        ind = _make_individual(given="", surname="Smith")
        q = _query([_term(field="given", value="John")])
        result = match_individual(ind, q)
        assert result is None

    def test_empty_surname(self) -> None:
        ind = _make_individual(given="John", surname="")
        q = _query([_term(field="surname", value="Smith")])
        result = match_individual(ind, q)
        assert result is None

    def test_both_places_match_returns_birth(self) -> None:
        ind = _make_individual(
            birth_place="London, England", death_place="London, England"
        )
        q = _query([_term(field="place", value="London")])
        result = match_individual(ind, q)
        assert result is not None
        # Birth place checked first
        assert result.details[0].matched_value == "London, England"

    def test_no_places(self) -> None:
        ind = _make_individual(birth_place="", death_place="")
        q = _query([_term(field="place", value="London")])
        result = match_individual(ind, q)
        assert result is None

    def test_name_exact_matches_full_name(self) -> None:
        ind = _make_individual(given="John", surname="Smith")
        q = _query([_term(field="name", operator="=", value="John Smith")])
        result = match_individual(ind, q)
        assert result is not None

    def test_name_exact_does_not_match_partial(self) -> None:
        ind = _make_individual(given="John", surname="Smith")
        q = _query([_term(field="name", operator="=", value="John")])
        result = match_individual(ind, q)
        assert result is not None
        # Matches given_name (exact match against "john")
        assert result.details[0].matched_value == "John"

    def test_name_exact_matches_surname(self) -> None:
        # Exercises name → surname exact match path (not full_name, not given)
        ind = _make_individual(given="John", surname="Smith")
        q = _query([_term(field="name", operator="=", value="Smith")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Smith"

    def test_name_exact_matches_alt_given(self) -> None:
        # Exact match on alt given_name (not alt full name)
        ind = _make_individual(
            given="Mary", surname="Williams", alt_names=[("Marie", "Williams")]
        )
        q = _query([_term(field="name", operator="=", value="Marie")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Marie"

    def test_name_exact_matches_alt_surname(self) -> None:
        # Exact match on alt surname (not alt full name)
        ind = _make_individual(
            given="Mary", surname="Williams", alt_names=[("Mary", "Johnson")]
        )
        q = _query([_term(field="name", operator="=", value="Johnson")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Johnson"

    def test_name_soundex_matches_given(self) -> None:
        # Name field soundex matching on given_name (not surname)
        ind = _make_individual(given="John", surname="Williams")
        q = _query([_term(field="name", operator="~", value="Jon")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "John"

    def test_name_soundex_matches_alt_surname(self) -> None:
        ind = _make_individual(
            given="Mary", surname="Williams", alt_names=[("", "Schmidt")]
        )
        q = _query([_term(field="name", operator="~", value="Schmid")])
        result = match_individual(ind, q)
        assert result is not None

    def test_name_soundex_matches_alt_given(self) -> None:
        # Alt surname soundex doesn't match, but alt given soundex does
        ind = _make_individual(
            given="Mary", surname="Williams", alt_names=[("Jon", "Unrelated")]
        )
        q = _query([_term(field="name", operator="~", value="John")])
        result = match_individual(ind, q)
        assert result is not None
        assert result.details[0].matched_value == "Jon"

    def test_given_soundex_no_match(self) -> None:
        ind = _make_individual(given="John")
        q = _query([_term(field="given", operator="~", value="Williams")])
        result = match_individual(ind, q)
        assert result is None

    def test_died_no_match(self) -> None:
        ind = _make_individual(death_year=1920)
        q = _query([_term(field="died", value="1800", date_range=(1800, 1800))])
        result = match_individual(ind, q)
        assert result is None

    def test_died_none_year(self) -> None:
        ind = _make_individual(death_year=None)
        q = _query([_term(field="died", value="1920", date_range=(1920, 1920))])
        result = match_individual(ind, q)
        assert result is None

    def test_empty_terms_no_relationship(self) -> None:
        # Safety guard: no terms and no relationship set → None
        ind = _make_individual()
        q = _query([])
        result = match_individual(ind, q, relationship_xrefs=None)
        assert result is None

    def test_regex_cache_hit(self) -> None:
        # Two individuals with the same regex pattern — tests cache hit path
        ind1 = _make_individual(surname="Smith")
        ind2 = _make_individual(xref="@I2@", surname="Smythe")
        q = _query([_term(field="surname", value="sm.*th")], regex_mode=True)
        r1 = match_individual(ind1, q)
        r2 = match_individual(ind2, q)
        assert r1 is not None
        assert r2 is not None
