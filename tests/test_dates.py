"""Tests for date handling utilities."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ged4py.parser import GedcomReader

from gedcom_tools.dates import (
    APPROX_PREFIXES,
    MONTH_PATTERN,
    MONTH_TO_NUM,
    classify_date_precision,
    count_sources_recursive,
    extract_month,
    extract_year_from_date,
    get_century,
    is_phrase_date,
)


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

    def test_phrase_type_returns_none(self):
        """Test that PHRASE type dates return None."""
        try:
            from ged4py.date import DateValueTypes

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.PHRASE
            # PHRASE has NO .date, .date1, or .year
            del mock_date.date
            del mock_date.date1
            del mock_date.year

            assert extract_year_from_date(mock_date) is None
        except ImportError:
            pytest.skip("ged4py not available")


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

    def test_phrase_type_returns_none(self):
        """Test that PHRASE type dates return None."""
        try:
            from ged4py.date import DateValueTypes

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.PHRASE
            del mock_date.date
            del mock_date.date1

            assert extract_month(mock_date) is None
        except ImportError:
            pytest.skip("ged4py not available")


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

    def test_mock_phrase_is_missing(self):
        """Test that PHRASE type is classified as missing."""
        try:
            from ged4py.date import DateValueTypes

            mock_date = MagicMock()
            mock_date.kind = DateValueTypes.PHRASE
            del mock_date.date
            del mock_date.date1

            result = classify_date_precision(mock_date)
            assert result == ("missing", False)
        except ImportError:
            pytest.skip("ged4py not available")


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
