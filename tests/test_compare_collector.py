from __future__ import annotations

from pathlib import Path

from gedcom_tools.commands.compare.collector import collect_individuals
from gedcom_tools.utils import normalize_compare, normalize_display


def _write_ged(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    p = tmp_path / filename
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n", encoding="utf-8")
    return p


class TestNormalizeDisplay:
    def test_nfc_composition(self) -> None:
        # NFD e + combining acute → NFC é
        nfd_e = "e\u0301"
        assert normalize_display(nfd_e) == "\u00e9"

    def test_empty_string(self) -> None:
        assert normalize_display("") == ""

    def test_ascii_unchanged(self) -> None:
        assert normalize_display("John") == "John"


class TestNormalizeCompare:
    def test_strips_diacritics(self) -> None:
        assert normalize_compare("José") == "jose"

    def test_umlaut_stripped(self) -> None:
        assert normalize_compare("Müller") == "muller"

    def test_lowercased(self) -> None:
        assert normalize_compare("SMITH") == "smith"

    def test_empty_string(self) -> None:
        assert normalize_compare("") == ""

    def test_nfd_input_handled(self) -> None:
        # ANSEL codec produces NFD — should still normalize correctly
        nfd = "Mu\u0308ller"  # M + u + combining diaeresis + ller
        assert normalize_compare(nfd) == "muller"

    def test_accent_grave(self) -> None:
        assert normalize_compare("Bogotá") == "bogota"

    def test_cedilla(self) -> None:
        assert normalize_compare("François") == "francois"


class TestCollectBasic:
    def test_single_individual(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n")
        result = collect_individuals(ged, "A")
        assert len(result) == 1
        ind = result[0]
        assert ind.xref == "@I1@"
        assert ind.source_file == "A"
        assert ind.given_name == "John"
        assert ind.surname == "Smith"
        assert ind.full_name == "John Smith"
        assert ind.sex == "M"

    def test_empty_file(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "")
        assert collect_individuals(ged, "B") == []

    def test_multiple_individuals(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n" "0 @I2@ INDI\n1 NAME Mary /Jones/\n",
        )
        result = collect_individuals(ged, "A")
        assert len(result) == 2
        xrefs = {ind.xref for ind in result}
        assert xrefs == {"@I1@", "@I2@"}

    def test_source_label_propagated(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME Test /Person/\n")
        result = collect_individuals(ged, "B")
        assert result[0].source_file == "B"


class TestNameExtraction:
    def test_givn_surn_override(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n2 GIVN Jonathan\n2 SURN Smithson\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.given_name == "Jonathan"
        assert ind.surname == "Smithson"

    def test_multi_name_records(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Mary /Williams/\n"
            "1 NAME Mary /Johnson/\n"
            "1 NAME Marie /Williams/\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.given_name == "Mary"
        assert ind.surname == "Williams"
        # Johnson is alt surname (different from primary)
        assert "Johnson" in ind.alt_surnames
        # Marie is alt given (different from primary)
        assert "Marie" in ind.alt_given_names
        # Williams again wouldn't be added as alt (same as primary)
        assert ind.alt_surnames.count("Johnson") == 1

    def test_no_name_record(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 SEX M\n")
        ind = collect_individuals(ged, "A")[0]
        assert ind.given_name == ""
        assert ind.surname == ""
        assert ind.full_name == ""

    def test_diacritics_in_name(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Jos\u00e9 /M\u00fcller/\n",
        )
        ind = collect_individuals(ged, "A")[0]
        # Display: NFC preserved
        assert ind.given_name == "Jos\u00e9"
        assert ind.surname == "M\u00fcller"
        # Normalized: diacritics stripped, lowercased
        assert ind.given_name_normalized == "jose"
        assert ind.surname_normalized == "muller"


class TestSexExtraction:
    def test_male(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX M\n")
        assert collect_individuals(ged, "A")[0].sex == "M"

    def test_female(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX F\n")
        assert collect_individuals(ged, "A")[0].sex == "F"

    def test_unknown_sex_becomes_empty(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n1 SEX U\n")
        assert collect_individuals(ged, "A")[0].sex == ""

    def test_missing_sex(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        assert collect_individuals(ged, "A")[0].sex == ""


class TestDatesAndPlaces:
    def test_birth_and_death(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1 JAN 1850\n2 PLAC London, England\n"
            "1 DEAT\n2 DATE 15 MAR 1920\n2 PLAC Manchester\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_year == 1850
        assert ind.death_year == 1920
        assert ind.birth_place == "London, England"
        assert ind.death_place == "Manchester"

    def test_christening_fallback(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 CHR\n2 DATE 5 FEB 1800\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_year == 1800

    def test_burial_fallback_for_death(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BURI\n2 DATE 10 OCT 1900\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.death_year == 1900

    def test_birth_date_takes_priority_over_chr(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1850\n"
            "1 CHR\n2 DATE 1851\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_year == 1850

    def test_no_dates(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_year is None
        assert ind.death_year is None
        assert ind.birth_place == ""
        assert ind.death_place == ""

    def test_place_normalization(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n" "1 BIRT\n2 PLAC M\u00fcnchen, Bayern\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_place == "M\u00fcnchen, Bayern"
        assert ind.birth_place_normalized == "munchen, bayern"


class TestFamilyLinks:
    def test_famc_extracted(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 FAMC @F1@\n" "0 @F1@ FAM\n1 CHIL @I1@\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.famc_xref == "@F1@"

    def test_fams_extracted(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 FAMS @F1@\n1 FAMS @F2@\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n"
            "0 @F2@ FAM\n1 HUSB @I1@\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.fams_xrefs == ["@F1@", "@F2@"]

    def test_no_family_links(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        ind = collect_individuals(ged, "A")[0]
        assert ind.famc_xref is None
        assert ind.fams_xrefs == []


class TestBlockingKeys:
    def test_phonetic_precomputed(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        ind = collect_individuals(ged, "A")[0]
        assert ind.surname_phonetic != ""
        assert ind.given_phonetic != ""
        # Smith → S530 (from normalized "smith")
        assert ind.surname_phonetic == "S530"

    def test_decade_keys(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1853\n"
            "1 DEAT\n2 DATE 1921\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_decade == "1850s"
        assert ind.death_decade == "1920s"

    def test_no_dates_no_decades(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        ind = collect_individuals(ged, "A")[0]
        assert ind.birth_decade == ""
        assert ind.death_decade == ""

    def test_no_name_no_phonetic(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 SEX M\n")
        ind = collect_individuals(ged, "A")[0]
        assert ind.surname_phonetic == ""
        assert ind.given_phonetic == ""


class TestAltNameNormalization:
    def test_alt_names_normalized(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Mar\u00eda /Garc\u00eda/\n"
            "1 NAME Mary /Garcia/\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert "Mary" in ind.alt_given_names
        assert "Garcia" in ind.alt_surnames
        # Normalized alt names
        assert "mary" in ind.alt_given_names_normalized
        assert "garcia" in ind.alt_surnames_normalized

    def test_duplicate_alt_name_not_added(self, tmp_path: Path) -> None:
        # Second NAME has same surname as primary — not added as alt
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n" "1 NAME John /Smith/\n" "1 NAME Jack /Smith/\n",
        )
        ind = collect_individuals(ged, "A")[0]
        assert "Jack" in ind.alt_given_names
        assert ind.alt_surnames == []  # Smith is same as primary


class TestMetaphoneCollector:
    def test_metaphone_produces_alt_codes(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        ind = collect_individuals(ged, "A", algorithm="metaphone")[0]
        assert ind.surname_phonetic != ""
        assert ind.given_phonetic != ""
        # Metaphone produces alt codes (may or may not be empty depending on name)
        # But the fields should exist
        assert isinstance(ind.surname_phonetic_alt, str)
        assert isinstance(ind.given_phonetic_alt, str)

    def test_soundex_alt_is_always_empty(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        ind = collect_individuals(ged, "A", algorithm="soundex")[0]
        assert ind.surname_phonetic_alt == ""
        assert ind.given_phonetic_alt == ""
        # Primary codes should still be set
        assert ind.surname_phonetic == "S530"
        assert ind.given_phonetic != ""
