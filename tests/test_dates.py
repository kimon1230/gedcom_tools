from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ged4py.date import DateValue
from ged4py.parser import GedcomReader

from gedcom_tools.dates import (
    APPROX_PREFIXES,
    MONTH_PATTERN,
    MONTH_TO_NUM,
    classify_date_precision,
    extract_month,
    extract_year_from_date,
    extract_year_latest_from_date,
    extract_year_latest_trusted,
    extract_year_trusted,
    get_century,
    is_clean_date_phrase,
    is_phrase_date,
)
from gedcom_tools.utils import count_sources_recursive


class TestMonthConstants:
    def test_month_to_num_has_all_months(self):
        assert len(MONTH_TO_NUM) == 12
        assert MONTH_TO_NUM["JAN"] == 1
        assert MONTH_TO_NUM["DEC"] == 12

    def test_month_pattern_matches_months(self):
        assert MONTH_PATTERN.search("15 OCT 1850")
        assert MONTH_PATTERN.search("jan 1900")
        assert not MONTH_PATTERN.search("1850")

    def test_approx_prefixes_are_strings(self):
        assert all(isinstance(p, str) for p in APPROX_PREFIXES)
        assert "ABT" in APPROX_PREFIXES
        assert "BEF" in APPROX_PREFIXES


class TestGetCentury:
    def test_1800s(self):
        assert get_century(1850) == "1800"

    def test_1900s(self):
        assert get_century(1999) == "1900"

    def test_2000s(self):
        assert get_century(2020) == "2000"

    def test_boundary(self):
        assert get_century(1900) == "1900"
        assert get_century(1899) == "1800"


class TestIsPhraseDate:
    def test_none_returns_false(self):
        assert not is_phrase_date(None)

    def test_string_returns_false(self):
        assert not is_phrase_date("1850")

    def test_mock_phrase_type(self):
        """Test with mocked PHRASE DateValue."""
        try:
            from ged4py.date import DateValueTypes

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.PHRASE
            assert is_phrase_date(mock_date)
        except ImportError:
            pytest.skip("ged4py not available")


class TestExtractYearFromDate:
    def test_none_returns_none(self):
        assert extract_year_from_date(None) is None

    def test_string_with_year(self):
        assert extract_year_from_date("15 OCT 1850") == 1850
        assert extract_year_from_date("1920") == 1920

    def test_string_abt(self):
        assert extract_year_from_date("ABT 1850") == 1850

    def test_string_bef_aft(self):
        assert extract_year_from_date("BEF 1900") == 1900
        assert extract_year_from_date("AFT 1850") == 1850

    def test_string_range(self):
        assert extract_year_from_date("BET 1850 AND 1860") == 1850

    def test_no_year_returns_none(self):
        assert extract_year_from_date("unknown") is None
        assert extract_year_from_date("") is None

    def test_mock_simple_date(self):
        """Test with mock ged4py DateValueSimple structure."""
        mock_cal = MagicMock()
        mock_cal.year = 1850

        mock_date = MagicMock()
        mock_date.date = mock_cal
        # Ensure .year attribute doesn't exist at top level
        del mock_date.year

        assert extract_year_from_date(mock_date) == 1850

    def test_mock_range_date(self):
        """Test with mock ged4py DateValueRange structure (.date1)."""
        mock_cal = MagicMock()
        mock_cal.year = 1850

        mock_date = MagicMock()
        mock_date.date1 = mock_cal
        mock_date.date = None
        del mock_date.year

        assert extract_year_from_date(mock_date) == 1850

    def test_mock_with_year_attr(self):
        """Test forward compatibility - .year at top level."""
        mock_date = MagicMock()
        mock_date.year = 1920
        mock_date.date = None

        assert extract_year_from_date(mock_date) == 1920

    def test_phrase_without_a_year_is_none(self):
        assert extract_year_from_date(DateValue.parse("(during the war)")) is None

    def test_phrase_year_is_recovered(self):
        assert extract_year_from_date(DateValue.parse("30 November 1989")) == 1989

    def test_phrase_slash_date_year_is_recovered(self):
        assert extract_year_from_date(DateValue.parse("12/2/1882")) == 1882


class _Bound:
    def __init__(self, year: object) -> None:
        self.year = year


class _RangeStub:
    """Stands in for a ged4py Range whose upper bound is unusable."""

    def __init__(self, date2_year: object) -> None:
        self.date1 = _Bound(1900)
        self.date2 = _Bound(date2_year)


class TestExtractYearLatest:
    def test_none(self) -> None:
        assert extract_year_latest_from_date(None) is None

    def test_phrase_date(self) -> None:
        assert (
            extract_year_latest_from_date(DateValue.parse("(during the war)")) is None
        )

    def test_simple_date(self) -> None:
        assert extract_year_latest_from_date(DateValue.parse("15 JAN 1850")) == 1850

    def test_approximate_date(self) -> None:
        assert extract_year_latest_from_date(DateValue.parse("ABT 1850")) == 1850

    def test_range(self) -> None:
        assert (
            extract_year_latest_from_date(DateValue.parse("BET 1900 AND 1995")) == 1995
        )

    def test_period(self) -> None:
        assert (
            extract_year_latest_from_date(DateValue.parse("FROM 1900 TO 1995")) == 1995
        )

    def test_open_ended_period(self) -> None:
        # "FROM 1900" has no upper bound at all
        assert extract_year_latest_from_date(DateValue.parse("FROM 1900")) == 1900

    def test_earliest_extractor_unchanged_for_range(self) -> None:
        assert extract_year_from_date(DateValue.parse("BET 1900 AND 1995")) == 1900

    def test_plain_string_range_takes_last_year(self) -> None:
        assert extract_year_latest_from_date("BET 1900 AND 1995") == 1995

    def test_plain_string_without_year(self) -> None:
        assert extract_year_latest_from_date("sometime long ago") is None

    def test_upper_bound_missing_year_falls_back(self) -> None:
        assert extract_year_latest_from_date(_RangeStub(None)) == 1900

    def test_upper_bound_unparseable_year_falls_back(self) -> None:
        assert extract_year_latest_from_date(_RangeStub("not-a-year")) == 1900


class TestExtractMonth:
    def test_none_returns_none(self):
        assert extract_month(None) is None

    def test_string_with_month(self):
        assert extract_month("15 OCT 1850") == 10
        assert extract_month("JAN 1920") == 1

    def test_string_lowercase(self):
        assert extract_month("15 oct 1850") == 10

    def test_no_month_returns_none(self):
        assert extract_month("1850") is None
        assert extract_month("unknown") is None

    def test_mock_with_date_month(self):
        """Test with mock ged4py structure."""
        mock_cal = MagicMock()
        mock_cal.month = "OCT"

        mock_date = MagicMock()
        mock_date.date = mock_cal

        assert extract_month(mock_date) == 10

    def test_mock_with_date1_month(self):
        """Test with mock ged4py range structure."""
        mock_cal = MagicMock()
        mock_cal.month = "MAR"

        mock_date = MagicMock()
        mock_date.date = None
        mock_date.date1 = mock_cal

        assert extract_month(mock_date) == 3

    def test_phrase_without_a_month_is_none(self):
        assert extract_month(DateValue.parse("(during the war)")) is None

    def test_phrase_full_month_name_is_recovered(self):
        assert extract_month(DateValue.parse("30 November 1989")) == 11

    def test_month_survives_a_year_less_phrase(self):
        # royal92 carries "2 DATE 10 JAN" — no year, but the month is real
        assert extract_month(DateValue.parse("10 JAN")) == 1


class TestClassifyDatePrecision:
    def test_none_is_missing(self):
        result = classify_date_precision(None)
        assert result == ("missing", False)

    def test_full_date_string(self):
        result = classify_date_precision("15 OCT 1850")
        assert result[0] == "full"
        assert result[1] is True

    def test_partial_year_only(self):
        result = classify_date_precision("1850")
        assert result[0] == "partial"
        assert result[1] is False

    def test_partial_month_year(self):
        result = classify_date_precision("OCT 1850")
        assert result[0] == "partial"
        assert result[1] is False

    def test_approximate_abt(self):
        result = classify_date_precision("ABT 1850")
        assert result[0] == "approximate"

    def test_approximate_bef(self):
        result = classify_date_precision("BEF 1850")
        assert result[0] == "approximate"

    def test_approximate_with_full_date(self):
        result = classify_date_precision("ABT 15 OCT 1850")
        assert result[0] == "approximate"
        assert result[1] is True

    def test_empty_string_is_missing(self):
        result = classify_date_precision("")
        assert result == ("missing", False)

    def test_mock_ged4py_simple(self):
        """Test with mock ged4py DateValueSimple."""
        try:
            from ged4py.date import DateValueTypes

            mock_cal = MagicMock()
            mock_cal.year = 1850
            mock_cal.month = "OCT"
            mock_cal.day = 15

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.SIMPLE
            mock_date.date = mock_cal

            result = classify_date_precision(mock_date)
            assert result == ("full", True)
        except ImportError:
            pytest.skip("ged4py not available")

    def test_mock_ged4py_about(self):
        """Test with mock ged4py ABOUT type."""
        try:
            from ged4py.date import DateValueTypes

            mock_cal = MagicMock()
            mock_cal.year = 1850
            mock_cal.month = None
            mock_cal.day = None

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.ABOUT
            mock_date.date = mock_cal

            result = classify_date_precision(mock_date)
            assert result[0] == "approximate"
            assert result[1] is False
        except ImportError:
            pytest.skip("ged4py not available")

    def test_phrase_without_a_year_is_missing(self):
        assert classify_date_precision(DateValue.parse("(during the war)")) == (
            "missing",
            False,
        )

    def test_phrase_full_date_is_full(self):
        assert classify_date_precision(DateValue.parse("30 November 1989")) == (
            "full",
            True,
        )


class TestCountSourcesRecursive:
    def test_empty_record(self):
        """Record with no sub-records returns 0."""
        mock_record = MagicMock()
        mock_record.sub_records = []

        assert count_sources_recursive(mock_record) == 0

    def test_single_source(self):
        """Record with one SOUR sub-record returns 1."""
        mock_sour = MagicMock()
        mock_sour.tag = "SOUR"
        mock_sour.sub_records = []

        mock_record = MagicMock()
        mock_record.sub_records = [mock_sour]

        assert count_sources_recursive(mock_record) == 1

    def test_multiple_sources(self):
        """Record with multiple SOUR sub-records."""
        mock_sour1 = MagicMock()
        mock_sour1.tag = "SOUR"
        mock_sour1.sub_records = []

        mock_sour2 = MagicMock()
        mock_sour2.tag = "SOUR"
        mock_sour2.sub_records = []

        mock_note = MagicMock()
        mock_note.tag = "NOTE"
        mock_note.sub_records = []

        mock_record = MagicMock()
        mock_record.sub_records = [mock_sour1, mock_note, mock_sour2]

        assert count_sources_recursive(mock_record) == 2

    def test_nested_source(self):
        """Source inside another sub-record."""
        mock_sour = MagicMock()
        mock_sour.tag = "SOUR"
        mock_sour.sub_records = []

        mock_birt = MagicMock()
        mock_birt.tag = "BIRT"
        mock_birt.sub_records = [mock_sour]

        mock_record = MagicMock()
        mock_record.sub_records = [mock_birt]

        assert count_sources_recursive(mock_record) == 1

    def test_deeply_nested_sources(self):
        """Sources at multiple nesting levels."""
        # Level 3: SOUR under DATE under BIRT
        mock_sour_deep = MagicMock()
        mock_sour_deep.tag = "SOUR"
        mock_sour_deep.sub_records = []

        mock_date = MagicMock()
        mock_date.tag = "DATE"
        mock_date.sub_records = [mock_sour_deep]

        # Level 2: SOUR under BIRT
        mock_sour_mid = MagicMock()
        mock_sour_mid.tag = "SOUR"
        mock_sour_mid.sub_records = []

        mock_birt = MagicMock()
        mock_birt.tag = "BIRT"
        mock_birt.sub_records = [mock_date, mock_sour_mid]

        # Level 1: SOUR at top level
        mock_sour_top = MagicMock()
        mock_sour_top.tag = "SOUR"
        mock_sour_top.sub_records = []

        mock_record = MagicMock()
        mock_record.sub_records = [mock_birt, mock_sour_top]

        assert count_sources_recursive(mock_record) == 3

    def test_no_sources_with_other_tags(self):
        """Record with sub-records but no SOUR."""
        mock_name = MagicMock()
        mock_name.tag = "NAME"
        mock_name.sub_records = []

        mock_birt = MagicMock()
        mock_birt.tag = "BIRT"
        mock_birt.sub_records = []

        mock_record = MagicMock()
        mock_record.sub_records = [mock_name, mock_birt]

        assert count_sources_recursive(mock_record) == 0


class TestExtractYearEdgeCases:
    def test_year_attr_with_invalid_value(self):
        """ValueError/TypeError in .year conversion falls back to string."""
        mock_date = MagicMock()
        mock_date.year = "not_a_number"
        mock_date.date = None
        mock_date.date1 = None
        mock_date.__str__ = lambda self: "ABT 1850"
        assert extract_year_from_date(mock_date) == 1850

    def test_date_attr_year_invalid(self):
        """ValueError in .date.year conversion falls back to string."""
        mock_cal = MagicMock()
        mock_cal.year = "invalid"
        mock_date = MagicMock()
        mock_date.date = mock_cal
        mock_date.date1 = None
        del mock_date.year
        mock_date.__str__ = lambda self: "1920"
        assert extract_year_from_date(mock_date) == 1920

    def test_date1_attr_year_invalid(self):
        """ValueError in .date1.year conversion falls back to string."""
        mock_cal = MagicMock()
        mock_cal.year = "bad"
        mock_date = MagicMock()
        mock_date.date = None
        mock_date.date1 = mock_cal
        del mock_date.year
        mock_date.__str__ = lambda self: "BET 1800 AND 1900"
        assert extract_year_from_date(mock_date) == 1800

    def test_no_year_anywhere_returns_none(self):
        """All paths exhausted, no year found."""
        mock_date = MagicMock()
        mock_date.date = None
        mock_date.date1 = None
        del mock_date.year
        mock_date.__str__ = lambda self: "no date here"
        assert extract_year_from_date(mock_date) is None


class TestExtractMonthEdgeCases:
    def test_month_from_string_fallback(self):
        """Month extracted via regex when no .date/.date1."""
        mock_date = MagicMock()
        mock_date.date = None
        mock_date.date1 = None
        mock_date.__str__ = lambda self: "15 MAR 1850"
        assert extract_month(mock_date) == 3

    def test_no_month_in_string(self):
        """No month found in any path."""
        mock_date = MagicMock()
        mock_date.date = None
        mock_date.date1 = None
        mock_date.__str__ = lambda self: "1850"
        assert extract_month(mock_date) is None

    def test_empty_string_date(self):
        assert extract_month("") is None


class TestClassifyDatePrecisionEdgeCases:
    def test_circa_prefix(self):
        assert classify_date_precision("CIRCA 1850") == ("approximate", False)

    def test_c_dot_prefix(self):
        assert classify_date_precision("C. 1850") == ("approximate", False)

    def test_from_prefix(self):
        assert classify_date_precision("FROM 1850") == ("approximate", False)

    def test_int_prefix(self):
        assert classify_date_precision("INT 1850") == ("approximate", False)

    def test_no_year_only_month(self):
        """Date with month but no year → missing."""
        assert classify_date_precision("ABT MAR") == ("missing", False)

    def test_invalid_day_32(self):
        """Day > 31 is not treated as a day."""
        result = classify_date_precision("32 JAN 1850")
        assert result[0] == "partial"  # Has month+year but no valid day

    def test_invalid_day_0(self):
        """Day == 0 is not treated as a day."""
        result = classify_date_precision("0 JAN 1850")
        assert result[0] == "partial"

    def test_single_digit_day(self):
        """Single-digit day is valid."""
        result = classify_date_precision("5 JAN 1850")
        assert result == ("full", True)

    def test_whitespace_only(self):
        assert classify_date_precision("   ") == ("missing", False)

    def test_ged4py_range_type(self):
        """Range type uses .date1 and is approximate."""
        try:
            from ged4py.date import DateValueTypes

            mock_cal = MagicMock()
            mock_cal.year = 1850
            mock_cal.month = "JAN"
            mock_cal.day = 15

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.RANGE
            mock_date.date = None
            mock_date.date1 = mock_cal

            result = classify_date_precision(mock_date)
            assert result == ("approximate", True)
        except ImportError:
            pytest.skip("ged4py not available")


class TestRealGedcomDates:
    def test_extract_year_from_real_parsed_date(self):
        """Test with actual ged4py parsed date from fixture."""
        fixtures = Path(__file__).parent / "fixtures"

        with GedcomReader(str(fixtures / "555sample.ged")) as reader:
            for record in reader.records0():
                if record.tag == "INDI":
                    birt = record.sub_tag("BIRT")
                    if birt:
                        date_rec = birt.sub_tag("DATE")
                        if date_rec and date_rec.value:
                            year = extract_year_from_date(date_rec.value)
                            if year:
                                assert 1800 <= year <= 2000
                            return
        pytest.skip("No birth dates in fixture")


# ---------------------------------------------------------------------------
# Phrase dates: ged4py parses only MAY/JUNE/JULY as full month names, so most
# real-world "30 November 1989" dates arrive as free text.
# ---------------------------------------------------------------------------

FULL_MONTH_NAMES = [
    ("January", 1),
    ("February", 2),
    ("March", 3),
    ("April", 4),
    ("May", 5),
    ("June", 6),
    ("July", 7),
    ("August", 8),
    ("September", 9),
    ("October", 10),
    ("November", 11),
    ("December", 12),
]


@pytest.mark.parametrize("name,number", FULL_MONTH_NAMES)
def test_full_month_names_resolve(name: str, number: int) -> None:
    date_val = DateValue.parse(f"3 {name} 1900")
    assert extract_year_from_date(date_val) == 1900
    assert extract_month(date_val) == number
    assert classify_date_precision(date_val) == ("full", True)


@pytest.mark.parametrize("text", ["3 JUNE 1900", "3 JULY 1900", "4 July 1776"])
def test_month_names_ged4py_parses_itself(text: str) -> None:
    # These come back as SIMPLE with .month set to "JUNE"/"JULY" verbatim,
    # which the 3-letter MONTH_TO_NUM keys used to miss entirely.
    assert extract_month(DateValue.parse(text)) is not None


PHRASE_CASES = [
    # text, year, latest, month, precision
    ("30 November 1989", 1989, 1989, 11, "full"),
    ("12/2/1882", 1882, 1882, None, "partial"),
    ("10 JAN", None, None, 1, "missing"),
    ("Christmas 1901", 1901, 1901, None, "partial"),
    ("sometime in the 90s", None, None, None, "missing"),
    ("unknown", None, None, None, "missing"),
    ("Deceased 1900", 1900, 1900, None, "partial"),
    ("Maybe 1905", 1905, 1905, None, "partial"),
    ("Tombstone erected 1901", 1901, 1901, None, "partial"),
    ("born 1990, per 1890 bible", 1990, 1990, None, "partial"),
]


@pytest.mark.parametrize("text,year,latest,month,precision", PHRASE_CASES)
def test_phrase_extraction(
    text: str,
    year: int | None,
    latest: int | None,
    month: int | None,
    precision: str,
) -> None:
    date_val = DateValue.parse(text)
    assert extract_year_from_date(date_val) == year
    assert extract_year_latest_from_date(date_val) == latest
    assert extract_month(date_val) == month
    assert classify_date_precision(date_val)[0] == precision


@pytest.mark.parametrize("text,year,latest,month,precision", PHRASE_CASES)
def test_year_and_precision_agree(
    text: str,
    year: int | None,
    latest: int | None,
    month: int | None,
    precision: str,
) -> None:
    # A populated year and a "missing" precision would let stats put someone in
    # the timeline while its own precision breakdown says the date is absent.
    date_val = DateValue.parse(text)
    assert (extract_year_from_date(date_val) is None) == (
        classify_date_precision(date_val)[0] == "missing"
    )


def test_latest_year_takes_the_largest_not_the_last() -> None:
    # Word order in free text is not chronological
    assert extract_year_latest_from_date(DateValue.parse("born 1990, per 1890")) == 1990


def test_tombstone_phrase_is_not_approximate() -> None:
    # "Tombstone..." starts with TO, which a startswith() prefix scan would
    # have read as the TO range marker
    assert classify_date_precision(DateValue.parse("Tombstone erected 1901"))[0] == (
        "partial"
    )


def test_c_prefix_is_still_approximate() -> None:
    assert classify_date_precision(DateValue.parse("C. 1900"))[0] == "approximate"


def test_bare_date_line_is_handled(tmp_path: Path) -> None:
    # "2 DATE" with no value parses to a phrase whose .phrase is None, and it
    # still passes the callers' `value is None` guard
    ged = tmp_path / "bare.ged"
    ged.write_text(
        "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
        "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE\n0 TRLR\n",
        encoding="utf-8",
    )
    with GedcomReader(str(ged)) as reader:
        record = next(reader.records0("INDI"))
        value = record.sub_tag("BIRT/DATE").value

    assert extract_year_from_date(value) is None
    assert extract_year_latest_from_date(value) is None
    assert extract_month(value) is None
    assert classify_date_precision(value) == ("missing", False)


CLEAN_PHRASES = [
    "30 November 1989",
    "12/2/1882",
    "1801-1875",
    "4 October 1950",
    "1900",
    "12-2-1882",
    "30 November 1989.",
]
DIRTY_PHRASES = [
    "Census 1900 record",
    "Reg. 1823 vol II",
    "1901, 1902, 1903, 1904",
    "born 1990, per 1890 bible",
    "sometime in the 90s",
    "10 JAN",
    "00/00/0000",
    "(MAY) 1900",
    "",
]


@pytest.mark.parametrize("text", CLEAN_PHRASES)
def test_clean_date_phrase_accepted(text: str) -> None:
    assert is_clean_date_phrase(text) is True


@pytest.mark.parametrize("text", DIRTY_PHRASES)
def test_free_text_phrase_rejected(text: str) -> None:
    assert is_clean_date_phrase(text) is False


def test_year_bound_is_pinned_to_the_injected_clock() -> None:
    # One year of slack, so next year is in and the year after is out
    assert is_clean_date_phrase("3 JAN 2027", current_year=2026) is True
    assert is_clean_date_phrase("3 JAN 2028", current_year=2026) is False


def test_year_below_the_plausible_floor_is_rejected() -> None:
    assert is_clean_date_phrase("0999") is False
    assert is_clean_date_phrase("1000") is True


def test_trusted_year_drops_a_free_text_year() -> None:
    dirty = DateValue.parse("Reg. 1823 vol II")
    assert extract_year_from_date(dirty) == 1823
    assert extract_year_trusted(dirty) is None


def test_trusted_year_keeps_a_clean_phrase_year() -> None:
    clean = DateValue.parse("30 November 1989")
    assert extract_year_trusted(clean) == 1989


def test_trusted_year_passes_structured_dates_through() -> None:
    assert extract_year_trusted(DateValue.parse("15 JAN 1850")) == 1850


# ged4py does not validate month tokens, so junk parses as a SIMPLE date
# rather than a phrase and never reaches the free-text gate.
UNVALIDATED_MONTH_DATES = ["Reg 1823", "Vol 1823", "12 Vol 1823"]


@pytest.mark.parametrize("text", UNVALIDATED_MONTH_DATES)
def test_junk_month_is_not_trusted(text: str) -> None:
    date_val = DateValue.parse(text)
    assert is_phrase_date(date_val) is False  # it is SIMPLE, not a phrase
    assert extract_year_from_date(date_val) == 1823  # still reported
    assert extract_year_trusted(date_val) is None  # but not acted on
    assert extract_year_latest_trusted(date_val) is None


@pytest.mark.parametrize("text", ["3 JUNE 1900", "15 JAN 1850", "4 July 1776"])
def test_real_months_stay_trusted(text: str) -> None:
    assert extract_year_trusted(DateValue.parse(text)) is not None


def test_range_upper_bound_is_trusted() -> None:
    assert extract_year_latest_trusted(DateValue.parse("BET 1900 AND 1995")) == 1995


def test_digit_soup_is_rejected() -> None:
    # An archive citation tokenizes to pure digits; cap the small numbers
    assert is_clean_date_phrase("1 1 1 1 1850") is False
    assert is_clean_date_phrase("99 88 77 1850") is False


# ged4py validates neither month tokens nor years, so a "structured" date is
# not proof of a date. These all reach estimate_living if left untrusted.
IMPLAUSIBLE_STRUCTURED = [
    "3/1990",  # read as the dual year 3, not March 1990
    "1/1985",
    "1 JAN 0002",
    "25 DEC 9999",
    "0007",
]


@pytest.mark.parametrize("text", IMPLAUSIBLE_STRUCTURED)
def test_implausible_structured_year_is_not_trusted(text: str) -> None:
    assert extract_year_trusted(DateValue.parse(text)) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1 JAN 1900", 1900),
        ("1750/51", 1750),  # dual date, the older year is real
        ("@#DHEBREW@ 1 TSH 5786", 5786),  # Hebrew years are out of range by design
    ],
)
def test_plausible_structured_year_survives(text: str, expected: int) -> None:
    assert extract_year_trusted(DateValue.parse(text)) == expected


def test_reversed_range_uses_the_larger_bound() -> None:
    # A range written backwards must not age the person out
    assert extract_year_latest_trusted(DateValue.parse("BET 2010 AND 1823")) == 2010
    assert extract_year_latest_trusted(DateValue.parse("BET 1900 AND 1995")) == 1995


def test_junk_month_on_the_upper_bound_is_caught() -> None:
    # date2 is the bound the liveness reader consumes, so it needs the same check
    assert extract_year_latest_trusted(DateValue.parse("BET 1900 AND Reg 1823")) is None
