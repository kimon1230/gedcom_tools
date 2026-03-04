from __future__ import annotations

import re

import pytest

from gedcom_tools.commands.search.query import parse_query

# ---------------------------------------------------------------------------
# Successful parsing
# ---------------------------------------------------------------------------


class TestBareAndExplicitFields:
    def test_bare_value_defaults_to_name(self) -> None:
        q = parse_query("Smith")
        assert len(q.terms) == 1
        t = q.terms[0]
        assert t.field == "name"
        assert t.operator == ":"
        assert t.value == "Smith"

    def test_explicit_field_surname(self) -> None:
        q = parse_query("surname:Smith")
        t = q.terms[0]
        assert t.field == "surname"
        assert t.operator == ":"
        assert t.value == "Smith"

    def test_multiple_terms(self) -> None:
        q = parse_query("surname:Smith born:1850")
        assert len(q.terms) == 2
        assert q.terms[0].field == "surname"
        assert q.terms[0].value == "Smith"
        assert q.terms[1].field == "born"
        assert q.terms[1].value == "1850"

    def test_quoted_multi_word_value(self) -> None:
        q = parse_query('place:"New York"')
        t = q.terms[0]
        assert t.field == "place"
        assert t.value == "New York"

    def test_obrien_single_quotes_are_literal(self) -> None:
        q = parse_query("surname:O'Brien")
        assert q.terms[0].value == "O'Brien"

    def test_operator_at_position_zero_tilde(self) -> None:
        q = parse_query("~Schmidt")
        t = q.terms[0]
        assert t.field == "name"
        assert t.operator == "~"
        assert t.value == "Schmidt"

    def test_colon_in_value(self) -> None:
        # First colon splits field from value; subsequent colons stay in value
        q = parse_query("place:St:Louis")
        t = q.terms[0]
        assert t.field == "place"
        assert t.value == "St:Louis"

    def test_exact_match_operator(self) -> None:
        q = parse_query("surname=Schmidt")
        t = q.terms[0]
        assert t.operator == "="
        assert t.value == "Schmidt"

    def test_phonetic_operator(self) -> None:
        q = parse_query("surname~Schmidt")
        t = q.terms[0]
        assert t.operator == "~"
        assert t.value == "Schmidt"

    def test_field_names_are_case_insensitive(self) -> None:
        q = parse_query("BORN:1850")
        assert q.terms[0].field == "born"

    def test_mixed_case_field(self) -> None:
        q = parse_query("SurName:Jones")
        assert q.terms[0].field == "surname"


class TestDateParsing:
    def test_date_range(self) -> None:
        q = parse_query("born:1800-1850")
        t = q.terms[0]
        assert t.date_range == (1800, 1850)

    def test_single_year(self) -> None:
        q = parse_query("born:1850")
        t = q.terms[0]
        assert t.date_range == (1850, 1850)

    def test_died_single_year(self) -> None:
        q = parse_query("died:1920")
        assert q.terms[0].date_range == (1920, 1920)

    def test_died_range(self) -> None:
        q = parse_query("died:1900-1950")
        assert q.terms[0].date_range == (1900, 1950)

    def test_non_date_field_has_no_date_range(self) -> None:
        q = parse_query("surname:Smith")
        assert q.terms[0].date_range is None

    def test_short_years(self) -> None:
        q = parse_query("born:80-120")
        assert q.terms[0].date_range == (80, 120)


class TestSexField:
    @pytest.mark.parametrize("value", ["M", "F", "U", "X"])
    def test_valid_sex_values(self, value: str) -> None:
        q = parse_query(f"sex:{value}")
        assert q.terms[0].value == value
        assert q.terms[0].field == "sex"


class TestXrefFields:
    def test_ancestor_xref(self) -> None:
        q = parse_query("ancestor:@I123@")
        t = q.terms[0]
        assert t.field == "ancestor"
        assert t.value == "@I123@"

    def test_descendant_xref(self) -> None:
        q = parse_query("descendant:@I5@")
        t = q.terms[0]
        assert t.field == "descendant"
        assert t.value == "@I5@"

    def test_xref_with_underscores(self) -> None:
        q = parse_query("ancestor:@I_123_ABC@")
        assert q.terms[0].value == "@I_123_ABC@"


class TestQueryOptions:
    def test_regex_mode_passthrough(self) -> None:
        q = parse_query("Smith", regex_mode=True)
        assert q.regex_mode is True

    def test_fuzzy_dates_passthrough(self) -> None:
        q = parse_query("born:1850", fuzzy_dates=5)
        assert q.fuzzy_dates == 5

    def test_limit_passthrough(self) -> None:
        q = parse_query("Smith", limit=10)
        assert q.limit == 10

    def test_count_only_passthrough(self) -> None:
        q = parse_query("Smith", count_only=True)
        assert q.count_only is True

    def test_defaults(self) -> None:
        q = parse_query("Smith")
        assert q.regex_mode is False
        assert q.fuzzy_dates is None
        assert q.limit is None
        assert q.count_only is False


# ---------------------------------------------------------------------------
# Wildcards
# ---------------------------------------------------------------------------


class TestWildcards:
    def test_asterisk_detected(self) -> None:
        q = parse_query("name:Sm*th")
        assert q.terms[0].is_wildcard is True

    def test_question_mark_detected(self) -> None:
        q = parse_query("name:Fo?kes")
        assert q.terms[0].is_wildcard is True

    def test_wildcards_disabled_in_regex_mode(self) -> None:
        q = parse_query("name:Sm*th", regex_mode=True)
        assert q.terms[0].is_wildcard is False

    def test_wildcards_disabled_for_exact_operator(self) -> None:
        q = parse_query("name=Sm*th")
        assert q.terms[0].is_wildcard is False

    def test_wildcards_disabled_for_phonetic_operator(self) -> None:
        q = parse_query("name~Sm*th")
        assert q.terms[0].is_wildcard is False

    def test_no_wildcard_when_absent(self) -> None:
        q = parse_query("name:Smith")
        assert q.terms[0].is_wildcard is False


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestEmptyInputErrors:
    def test_empty_string(self) -> None:
        with pytest.raises(ValueError, match="No search query"):
            parse_query("")

    def test_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="No search query"):
            parse_query("   \t  ")

    def test_none_treated_as_empty(self) -> None:
        with pytest.raises(ValueError, match="No search query"):
            parse_query(None)


class TestMissingValueErrors:
    def test_field_with_no_value(self) -> None:
        with pytest.raises(ValueError, match="Missing value for field 'name'"):
            parse_query("name:")


class TestUnknownFieldErrors:
    def test_unknown_field(self) -> None:
        with pytest.raises(ValueError, match=re.escape("Unknown field 'foo'")):
            parse_query("foo:bar")

    def test_error_lists_valid_fields(self) -> None:
        with pytest.raises(ValueError, match="Valid fields:"):
            parse_query("foo:bar")


class TestPhoneticOperatorErrors:
    @pytest.mark.parametrize(
        "query,fragment",
        [
            ("born~1850", "not supported for date fields"),
            ("died~1920", "not supported for date fields"),
        ],
    )
    def test_tilde_on_date_fields(self, query: str, fragment: str) -> None:
        with pytest.raises(ValueError, match=fragment):
            parse_query(query)

    @pytest.mark.parametrize(
        "query",
        [
            "place~York",
            "sex~M",
            "ancestor~@I1@",
        ],
    )
    def test_tilde_on_non_name_fields(self, query: str) -> None:
        with pytest.raises(ValueError, match="only supported for name fields"):
            parse_query(query)


class TestDateFormatErrors:
    def test_non_numeric_date(self) -> None:
        with pytest.raises(ValueError, match="Invalid date format 'abc'"):
            parse_query("born:abc")

    def test_trailing_dash(self) -> None:
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_query("born:1800-")

    def test_leading_dash(self) -> None:
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_query("born:-1850")

    def test_reversed_range(self) -> None:
        with pytest.raises(
            ValueError, match=re.escape("start year (1900) is after end year (1800)")
        ):
            parse_query("born:1900-1800")

    def test_range_with_exact_operator(self) -> None:
        with pytest.raises(ValueError, match="Date ranges require the : operator"):
            parse_query("born=1800-1850")


class TestSexValidationErrors:
    def test_multi_char_sex(self) -> None:
        with pytest.raises(ValueError, match="single characters"):
            parse_query("sex:Male")


class TestXrefValidationErrors:
    def test_missing_at_signs(self) -> None:
        with pytest.raises(ValueError, match="Invalid identifier format"):
            parse_query("ancestor:I1")

    def test_partial_at_signs(self) -> None:
        with pytest.raises(ValueError, match="Invalid identifier format"):
            parse_query("descendant:@I1")

    def test_error_suggests_correct_format(self) -> None:
        with pytest.raises(ValueError, match=re.escape("ancestor:@I1@")):
            parse_query("ancestor:I1")


class TestRegexErrors:
    def test_invalid_regex_pattern(self) -> None:
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            parse_query("name:[invalid", regex_mode=True)

    def test_nested_quantifiers(self) -> None:
        with pytest.raises(ValueError, match="nested quantifiers"):
            parse_query("name:(a+)+", regex_mode=True)

    def test_error_suggests_removing_regex(self) -> None:
        with pytest.raises(ValueError, match="remove --regex"):
            parse_query("name:[invalid", regex_mode=True)

    def test_quantified_inner_group(self) -> None:
        with pytest.raises(ValueError, match="quantified group"):
            parse_query(r"name:(a*b)+", regex_mode=True)

    def test_overlapping_alternation(self) -> None:
        with pytest.raises(ValueError, match="alternation"):
            parse_query(r"name:(a|b)+", regex_mode=True)

    def test_pattern_too_long(self) -> None:
        long_pattern = "a" * 257
        with pytest.raises(ValueError, match="too long"):
            parse_query(f"name:{long_pattern}", regex_mode=True)

    def test_pattern_at_max_length_accepted(self) -> None:
        ok_pattern = "a" * 256
        q = parse_query(f"name:{ok_pattern}", regex_mode=True)
        assert q.terms[0].value == ok_pattern

    def test_too_many_nested_groups(self) -> None:
        # 4 levels of nesting → rejected (max 3)
        with pytest.raises(ValueError, match="nested groups"):
            parse_query(r"name:((((a))))", regex_mode=True)

    def test_three_nested_groups_accepted(self) -> None:
        # Exactly 3 levels → accepted
        q = parse_query(r"name:(a(b(c)))", regex_mode=True)
        assert len(q.terms) == 1

    def test_valid_complex_regex_accepted(self) -> None:
        q = parse_query(r"name:^(John|Jane)\s+\w+$", regex_mode=True)
        assert q.terms[0].value == r"^(John|Jane)\s+\w+$"

    def test_escaped_parens_not_counted(self) -> None:
        # Escaped parens should not count toward nesting depth
        q = parse_query(r"name:\(literal\)", regex_mode=True)
        assert len(q.terms) == 1


class TestWildcardErrors:
    def test_too_broad_pattern(self) -> None:
        with pytest.raises(ValueError, match="too broad"):
            parse_query("name:S*")

    def test_all_wildcards(self) -> None:
        with pytest.raises(ValueError, match="too broad"):
            parse_query("name:***")

    def test_two_chars_plus_wildcard(self) -> None:
        with pytest.raises(ValueError, match="too broad"):
            parse_query("name:Sm*")

    def test_three_chars_passes(self) -> None:
        # Exactly 3 non-wildcard chars — should pass
        q = parse_query("name:Smi*")
        assert q.terms[0].is_wildcard is True


class TestTildeExpansionErrors:
    def test_home_linux_path(self) -> None:
        with pytest.raises(ValueError, match="home directory path"):
            parse_query("surname~/home/user/Schmidt")

    def test_home_macos_path(self) -> None:
        with pytest.raises(ValueError, match="home directory path"):
            parse_query("surname~/Users/user/Schmidt")

    def test_suggests_single_quotes(self) -> None:
        with pytest.raises(ValueError, match="single quotes"):
            parse_query("surname~/home/user/Schmidt")


# ---------------------------------------------------------------------------
# Mode interactions
# ---------------------------------------------------------------------------


class TestModeInteractions:
    def test_regex_does_not_validate_exact_operator(self) -> None:
        # = operator should skip regex validation even with regex_mode
        q = parse_query("surname=[invalid", regex_mode=True)
        assert q.terms[0].operator == "="
        assert q.terms[0].value == "[invalid"

    def test_regex_does_not_validate_phonetic_operator(self) -> None:
        q = parse_query("name~[invalid", regex_mode=True)
        assert q.terms[0].operator == "~"
        assert q.terms[0].value == "[invalid"

    def test_regex_skips_date_fields(self) -> None:
        # Date fields have their own validation; regex shouldn't interfere
        q = parse_query("born:1850", regex_mode=True)
        assert q.terms[0].date_range == (1850, 1850)

    def test_regex_skips_xref_fields(self) -> None:
        q = parse_query("ancestor:@I1@", regex_mode=True)
        assert q.terms[0].value == "@I1@"

    def test_wildcards_not_detected_in_regex_mode(self) -> None:
        q = parse_query("name:Sm*th", regex_mode=True)
        assert q.terms[0].is_wildcard is False

    def test_duplicate_fields_produce_multiple_terms(self) -> None:
        q = parse_query("born:1850 born:1860")
        assert len(q.terms) == 2
        assert q.terms[0].date_range == (1850, 1850)
        assert q.terms[1].date_range == (1860, 1860)

    def test_valid_regex_accepted(self) -> None:
        q = parse_query(r"name:\bSmith\b", regex_mode=True)
        assert q.terms[0].value == r"\bSmith\b"

    def test_regex_with_place_field(self) -> None:
        q = parse_query("place:New.*York", regex_mode=True)
        assert q.terms[0].value == "New.*York"
