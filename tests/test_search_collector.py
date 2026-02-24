from __future__ import annotations

from pathlib import Path

from gedcom_tools.commands.search.collector import collect_individuals
from gedcom_tools.commands.search.models import SearchIndividual
from gedcom_tools.phonetics import soundex
from gedcom_tools.utils import EncodingInfo


def _write_ged(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    p = tmp_path / filename
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n")
    return p


def _collect_one(tmp_path: Path, content: str) -> SearchIndividual:
    ged = _write_ged(tmp_path, content)
    individuals, _ = collect_individuals(ged)
    assert len(individuals) == 1
    return individuals[0]


# ---------------------------------------------------------------------------
# Basic collection
# ---------------------------------------------------------------------------


class TestCollectBasic:
    def test_single_individual_all_fields(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n"
            "1 BIRT\n2 DATE 1 JAN 1850\n2 PLAC London, England\n"
            "1 DEAT\n2 DATE 15 MAR 1920\n2 PLAC Manchester\n",
        )
        individuals, enc = collect_individuals(ged)
        assert len(individuals) == 1
        ind = individuals[0]
        assert ind.xref == "@I1@"
        assert ind.given_name == "John"
        assert ind.surname == "Smith"
        assert ind.full_name == "John Smith"
        assert ind.sex == "M"
        assert ind.birth_year == 1850
        assert ind.birth_place == "London, England"
        assert ind.death_year == 1920
        assert ind.death_place == "Manchester"

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "")
        individuals, _ = collect_individuals(ged)
        assert individuals == []

    def test_multiple_individuals(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @I2@ INDI\n1 NAME Mary /Jones/\n"
            "0 @I3@ INDI\n1 NAME Alice /Brown/\n",
        )
        individuals, _ = collect_individuals(ged)
        assert len(individuals) == 3
        xrefs = {ind.xref for ind in individuals}
        assert xrefs == {"@I1@", "@I2@", "@I3@"}

    def test_xref_extracted_correctly(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @PERSON99@ INDI\n1 NAME Test /User/\n")
        individuals, _ = collect_individuals(ged)
        assert individuals[0].xref == "@PERSON99@"

    def test_returns_encoding_info(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        _, enc = collect_individuals(ged)
        assert isinstance(enc, EncodingInfo)
        assert enc.declared_charset == "UTF-8"


# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------


class TestNameExtraction:
    def test_givn_surn_override(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n2 GIVN Jonathan\n2 SURN Smithson\n",
        )
        assert ind.given_name == "Jonathan"
        assert ind.surname == "Smithson"

    def test_multiple_name_records_primary_and_alt(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Mary /Williams/\n"
            "1 NAME Marie /Johnson/\n"
            "1 NAME Maria /Garcia/\n",
        )
        assert ind.given_name == "Mary"
        assert ind.surname == "Williams"
        assert len(ind.alt_names) == 2
        assert ("Marie", "Johnson") in ind.alt_names
        assert ("Maria", "Garcia") in ind.alt_names

    def test_no_name_record(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 SEX M\n")
        assert ind.given_name == ""
        assert ind.surname == ""
        assert ind.full_name == ""

    def test_diacritics_display_preserves_nfc(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Jos\u00e9 /M\u00fcller/\n",
        )
        # Display: NFC preserved
        assert ind.given_name == "Jos\u00e9"
        assert ind.surname == "M\u00fcller"

    def test_diacritics_normalized_stripped_and_lowered(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Jos\u00e9 /M\u00fcller/\n",
        )
        assert ind.given_name_norm == "jose"
        assert ind.surname_norm == "muller"

    def test_alt_names_are_tuples(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n1 NAME Jack /Smyth/\n",
        )
        assert ind.alt_names == [("Jack", "Smyth")]


# ---------------------------------------------------------------------------
# Sex extraction
# ---------------------------------------------------------------------------


class TestSexExtraction:
    def test_male(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX M\n")
        assert ind.sex == "M"

    def test_female(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX F\n")
        assert ind.sex == "F"

    def test_unknown_sex_stored_as_u(self, tmp_path: Path) -> None:
        # Unlike compare collector which filters U to "", search keeps it
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX U\n")
        assert ind.sex == "U"

    def test_x_sex_stored(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX X\n")
        assert ind.sex == "X"

    def test_missing_sex_empty_string(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        assert ind.sex == ""

    def test_lowercase_input_normalized_to_upper(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX f\n")
        assert ind.sex == "F"


# ---------------------------------------------------------------------------
# Dates and places
# ---------------------------------------------------------------------------


class TestDatesAndPlaces:
    def test_birth_year_and_place(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1 JAN 1850\n2 PLAC London, England\n",
        )
        assert ind.birth_year == 1850
        assert ind.birth_place == "London, England"

    def test_death_year_and_place(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 DEAT\n2 DATE 15 MAR 1920\n2 PLAC Manchester\n",
        )
        assert ind.death_year == 1920
        assert ind.death_place == "Manchester"

    def test_christening_fallback_for_birth(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 CHR\n2 DATE 5 FEB 1800\n2 PLAC Parish Church\n",
        )
        assert ind.birth_year == 1800
        assert ind.birth_place == "Parish Church"

    def test_baptism_fallback_when_chr_also_missing(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BAPM\n2 DATE 12 APR 1790\n2 PLAC Old Chapel\n",
        )
        assert ind.birth_year == 1790
        assert ind.birth_place == "Old Chapel"

    def test_burial_fallback_for_death(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BURI\n2 DATE 10 OCT 1900\n2 PLAC Cemetery Lane\n",
        )
        assert ind.death_year == 1900
        assert ind.death_place == "Cemetery Lane"

    def test_birt_date_takes_priority_over_chr(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1850\n"
            "1 CHR\n2 DATE 1851\n",
        )
        assert ind.birth_year == 1850

    def test_birt_date_takes_priority_over_bapm(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1830\n"
            "1 BAPM\n2 DATE 1831\n",
        )
        assert ind.birth_year == 1830

    def test_chr_takes_priority_over_bapm(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 CHR\n2 DATE 1810\n"
            "1 BAPM\n2 DATE 1811\n",
        )
        assert ind.birth_year == 1810

    def test_deat_date_takes_priority_over_buri(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 DEAT\n2 DATE 1900\n"
            "1 BURI\n2 DATE 1901\n",
        )
        assert ind.death_year == 1900

    def test_no_dates_returns_none(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        assert ind.birth_year is None
        assert ind.death_year is None

    def test_no_places_returns_empty_string(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        assert ind.birth_place == ""
        assert ind.death_place == ""

    def test_birth_place_without_date(self, tmp_path: Path) -> None:
        # BIRT event with place but no date: place still extracted
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 PLAC Vienna, Austria\n",
        )
        assert ind.birth_year is None
        assert ind.birth_place == "Vienna, Austria"

    def test_death_place_without_date(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n2 PLAC Berlin, Germany\n",
        )
        assert ind.death_year is None
        assert ind.death_place == "Berlin, Germany"

    def test_place_display_normalization(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n" "1 BIRT\n2 PLAC M\u00fcnchen, Bayern\n",
        )
        assert ind.birth_place == "M\u00fcnchen, Bayern"  # NFC preserved

    def test_place_compare_normalization(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n" "1 BIRT\n2 PLAC M\u00fcnchen, Bayern\n",
        )
        assert ind.birth_place_norm == "munchen, bayern"

    def test_chr_place_used_when_chr_date_selected(self, tmp_path: Path) -> None:
        # When CHR provides the date (no BIRT date), CHR place is used
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 CHR\n2 DATE 1800\n2 PLAC Parish of St Mary\n",
        )
        assert ind.birth_place == "Parish of St Mary"

    def test_buri_place_used_when_buri_date_selected(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n" "1 BURI\n2 DATE 1900\n2 PLAC Town Cemetery\n",
        )
        assert ind.death_place == "Town Cemetery"


# ---------------------------------------------------------------------------
# Approximate dates
# ---------------------------------------------------------------------------


class TestApproximateDates:
    def test_abt_is_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE ABT 1850\n",
        )
        assert ind.birth_year == 1850
        assert ind.birth_year_approximate is True

    def test_est_is_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE EST 1850\n",
        )
        assert ind.birth_year == 1850
        assert ind.birth_year_approximate is True

    def test_bef_is_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n2 DATE BEF 1900\n",
        )
        assert ind.death_year == 1900
        assert ind.death_year_approximate is True

    def test_aft_is_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE AFT 1800\n",
        )
        assert ind.birth_year == 1800
        assert ind.birth_year_approximate is True

    def test_exact_date_not_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 1 JAN 1850\n",
        )
        assert ind.birth_year == 1850
        assert ind.birth_year_approximate is False

    def test_year_only_not_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 1850\n",
        )
        assert ind.birth_year == 1850
        assert ind.birth_year_approximate is False

    def test_death_approximate_flag(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n2 DATE ABT 1920\n",
        )
        assert ind.death_year == 1920
        assert ind.death_year_approximate is True

    def test_no_date_not_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        assert ind.birth_year_approximate is False
        assert ind.death_year_approximate is False

    def test_cal_is_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE CAL 1875\n",
        )
        assert ind.birth_year == 1875
        assert ind.birth_year_approximate is True

    def test_chr_fallback_preserves_approximate(self, tmp_path: Path) -> None:
        # ABT on CHR date should still be flagged as approximate
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 CHR\n2 DATE ABT 1805\n",
        )
        assert ind.birth_year == 1805
        assert ind.birth_year_approximate is True

    def test_buri_fallback_preserves_approximate(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BURI\n2 DATE ABT 1910\n",
        )
        assert ind.death_year == 1910
        assert ind.death_year_approximate is True


# ---------------------------------------------------------------------------
# Soundex pre-computation
# ---------------------------------------------------------------------------


class TestSoundexPrecomputation:
    def test_surname_and_given_soundex_populated(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        assert ind.surname_soundex == "S530"
        assert ind.given_name_soundex == "J500"

    def test_empty_name_empty_soundex(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 SEX M\n")
        assert ind.surname_soundex == ""
        assert ind.given_name_soundex == ""

    def test_alt_names_have_alt_soundex(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n" "1 NAME John /Smith/\n" "1 NAME Jack /Smythe/\n",
        )
        assert len(ind.alt_soundex) == 1
        # alt_soundex entries are (given_soundex, surname_soundex) tuples
        given_sx, surname_sx = ind.alt_soundex[0]
        assert given_sx != ""
        assert surname_sx != ""

    def test_soundex_computed_from_normalized(self, tmp_path: Path) -> None:
        # Diacritics stripped before soundex computation
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Fran\u00e7ois /Gar\u00e7on/\n",
        )
        # "Fran\u00e7ois" normalizes to "francois", "Gar\u00e7on" to "garcon"
        # soundex is computed from those normalized forms
        expected_surname = soundex("garcon")
        expected_given = soundex("francois")
        assert ind.surname_soundex == expected_surname
        assert ind.given_name_soundex == expected_given

    def test_multiple_alt_soundex_entries(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "1 NAME Jack /Smythe/\n"
            "1 NAME Johann /Schmidt/\n",
        )
        assert len(ind.alt_soundex) == 2
        # Each tuple has (given_soundex, surname_soundex)
        for g_sx, s_sx in ind.alt_soundex:
            assert isinstance(g_sx, str)
            assert isinstance(s_sx, str)

    def test_only_given_name_has_soundex(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME John //\n")
        assert ind.given_name_soundex != ""
        assert ind.surname_soundex == ""

    def test_only_surname_has_soundex(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME /Smith/\n")
        assert ind.surname_soundex != ""
        assert ind.given_name_soundex == ""


# ---------------------------------------------------------------------------
# Full name construction
# ---------------------------------------------------------------------------


class TestFullName:
    def test_given_and_surname(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        assert ind.full_name == "John Smith"

    def test_full_name_norm(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Jos\u00e9 /M\u00fcller/\n",
        )
        assert ind.full_name_norm == "jose muller"

    def test_only_given_no_trailing_space(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME John //\n")
        assert ind.full_name == "John"
        assert not ind.full_name.endswith(" ")

    def test_only_surname_no_leading_space(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 NAME /Smith/\n")
        assert ind.full_name == "Smith"
        assert not ind.full_name.startswith(" ")

    def test_both_empty_returns_empty(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 SEX M\n")
        assert ind.full_name == ""

    def test_full_name_display_uses_display_values(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Ren\u00e9 /D\u00fcrer/\n",
        )
        # full_name should use the NFC display forms, not the normalized forms
        assert ind.full_name == "Ren\u00e9 D\u00fcrer"


# ---------------------------------------------------------------------------
# Normalized fields
# ---------------------------------------------------------------------------


class TestNormalizedFields:
    def test_all_norm_fields_populated(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "1 BIRT\n2 DATE 1850\n2 PLAC London, England\n"
            "1 DEAT\n2 DATE 1920\n2 PLAC Manchester\n",
        )
        assert ind.given_name_norm == "john"
        assert ind.surname_norm == "smith"
        assert ind.full_name_norm == "john smith"
        assert ind.birth_place_norm == "london, england"
        assert ind.death_place_norm == "manchester"

    def test_alt_names_norm(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Mar\u00eda /Garc\u00eda/\n"
            "1 NAME Mary /Garcia/\n",
        )
        assert len(ind.alt_names_norm) == 1
        g_norm, s_norm = ind.alt_names_norm[0]
        assert g_norm == "mary"
        assert s_norm == "garcia"

    def test_empty_fields_normalize_to_empty(self, tmp_path: Path) -> None:
        ind = _collect_one(tmp_path, "0 @I1@ INDI\n1 SEX M\n")
        assert ind.given_name_norm == ""
        assert ind.surname_norm == ""
        assert ind.birth_place_norm == ""
        assert ind.death_place_norm == ""

    def test_death_place_norm(self, tmp_path: Path) -> None:
        ind = _collect_one(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n" "1 DEAT\n2 PLAC Stra\u00dfburg, Elsass\n",
        )
        # \u00df (sharp s) has no combining diacritic — preserved but lowered
        assert ind.death_place_norm == "stra\u00dfburg, elsass"
