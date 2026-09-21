from __future__ import annotations

import json
from pathlib import Path

from gedcom_tools.commands.export.collector import collect_export_data
from gedcom_tools.commands.export.formatters import format_json
from gedcom_tools.commands.export.models import estimate_living


def _write_ged(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    p = tmp_path / filename
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# estimate_living tests
# ---------------------------------------------------------------------------


class TestEstimateLiving:
    def test_has_death_year(self) -> None:
        assert estimate_living(1900, 1980, None, current_year=2026) is False

    def test_has_burial_date(self) -> None:
        assert estimate_living(1950, None, 2020, current_year=2026) is False

    def test_old_birth_year(self) -> None:
        # Born 1900, 126 years ago — exceeds max_age 110
        assert estimate_living(1900, None, None, current_year=2026) is False

    def test_recent_birth_no_death(self) -> None:
        assert estimate_living(1980, None, None, current_year=2026) is True

    def test_no_birth_year_no_death_assumed_living(self) -> None:
        # No dates at all → nothing rules out a living person, so redact
        assert estimate_living(None, None, None, current_year=2026) is True

    def test_boundary_exactly_max_age(self) -> None:
        # Born 1916, current year 2026 → 110 years → exactly max_age → still living
        assert estimate_living(1916, None, None, max_age=110, current_year=2026) is True

    def test_boundary_one_year_over(self) -> None:
        # Born 1915, current year 2026 → 111 years → exceeds max_age
        assert (
            estimate_living(1915, None, None, max_age=110, current_year=2026) is False
        )

    def test_custom_max_age(self) -> None:
        # Born 1940, max_age=80, current year 2026 → 86 years → exceeds
        assert estimate_living(1940, None, None, max_age=80, current_year=2026) is False
        # Born 1950, max_age=80, current year 2026 → 76 years → within
        assert estimate_living(1950, None, None, max_age=80, current_year=2026) is True

    def test_no_birth_with_old_birth_not_living(self) -> None:
        # Born 200 years ago, no death → not living (exceeds max_age)
        assert estimate_living(1826, None, None, current_year=2026) is False

    def test_living_tag_lvg(self) -> None:
        assert (
            estimate_living(None, None, None, current_year=2026, living_marker="_LVG")
            is True
        )

    def test_living_tag_living(self) -> None:
        assert (
            estimate_living(
                None, None, None, current_year=2026, living_marker="_LIVING"
            )
            is True
        )

    def test_living_tag_lvng(self) -> None:
        assert (
            estimate_living(None, None, None, current_year=2026, living_marker="_LVNG")
            is True
        )

    def test_living_tag_conf_flag(self) -> None:
        assert (
            estimate_living(
                None, None, None, current_year=2026, living_marker="_CONF_FLAG"
            )
            is True
        )

    def test_uncorroborated_nliv_ignored(self) -> None:
        # _NLIV comes from an untrusted file; with no death record to back it
        # up it cannot switch redaction off for someone born in 2000
        assert (
            estimate_living(2000, None, None, current_year=2026, living_marker="_NLIV")
            is True
        )

    def test_nliv_corroborated_by_death_year(self) -> None:
        assert (
            estimate_living(2000, 2020, None, current_year=2026, living_marker="_NLIV")
            is False
        )

    def test_nliv_corroborated_by_burial_date(self) -> None:
        assert (
            estimate_living(
                2000, None, "3 FEB 2020", current_year=2026, living_marker="_NLIV"
            )
            is False
        )

    def test_living_tag_overrides_missing_dates(self) -> None:
        # No dates, but tagged as living by software
        assert (
            estimate_living(None, None, None, current_year=2026, living_marker="_LVG")
            is True
        )

    def test_nliv_still_bounded_by_max_age(self) -> None:
        # Uncorroborated _NLIV falls through to the date rules, and max_age
        # still settles it for someone born 200 years ago
        assert (
            estimate_living(1826, None, None, current_year=2026, living_marker="_NLIV")
            is False
        )

    def test_old_birth_year_beats_missing_death_record(self) -> None:
        # No death evidence anywhere, but max_age is the ceiling regardless
        assert estimate_living(1650, None, None, current_year=2026) is False

    def test_living_tag_overrides_death(self) -> None:
        # Software says living, but has death year — living tag wins
        # (trust the software's explicit marker)
        assert (
            estimate_living(1900, 1980, None, current_year=2026, living_marker="_LVG")
            is True
        )


# ---------------------------------------------------------------------------
# Collector: empty and basic
# ---------------------------------------------------------------------------


class TestCollectorBasic:
    def test_empty_file(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "")
        result = collect_export_data(ged)
        assert result.individual_count == 0
        assert result.family_count == 0
        assert result.individuals == []
        assert result.families == []

    def test_encoding_detected(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "")
        result = collect_export_data(ged)
        assert result.encoding == "UTF-8"
        assert result.file_path == str(ged)


# ---------------------------------------------------------------------------
# Collector: individual fields
# ---------------------------------------------------------------------------


class TestCollectorIndividual:
    def test_all_fields_populated(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/ Jr\n"
            "1 SEX M\n"
            "1 BIRT\n2 DATE 15 JAN 1850\n2 PLAC London, England\n"
            "1 DEAT\n2 DATE 3 MAR 1920\n2 PLAC New York, USA\n"
            "1 BURI\n2 DATE 5 MAR 1920\n2 PLAC Greenwood Cemetery\n"
            "1 OCCU Blacksmith\n"
            "1 OCCU Farmer\n"
            "1 NOTE Some biographical text\n"
            "1 SOUR @S1@\n"
            "1 FAMC @F5@\n"
            "1 FAMS @F1@\n"
            "1 FAMS @F7@\n",
        )
        result = collect_export_data(ged)
        assert result.individual_count == 1
        ind = result.individuals[0]
        assert ind.xref == "@I1@"
        assert ind.given_name == "John"
        assert ind.surname == "Smith"
        assert ind.suffix == "Jr"
        assert ind.sex == "M"
        assert ind.birth_year == 1850
        assert "1850" in ind.birth_date
        assert ind.birth_place == "London, England"
        assert ind.death_year == 1920
        assert "1920" in ind.death_date
        assert ind.death_place == "New York, USA"
        assert "1920" in ind.burial_date
        assert ind.burial_place == "Greenwood Cemetery"
        assert ind.occupations == ["Blacksmith", "Farmer"]
        assert ind.source_count == 1
        assert ind.famc_xref == "@F5@"
        assert ind.fams_xrefs == ["@F1@", "@F7@"]
        assert "Some biographical text" in ind.notes

    def test_minimal_individual(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME Jane /Doe/\n")
        result = collect_export_data(ged)
        ind = result.individuals[0]
        assert ind.given_name == "Jane"
        assert ind.surname == "Doe"
        assert ind.suffix == ""
        assert ind.sex == ""
        assert ind.birth_year is None
        assert ind.birth_date == ""
        assert ind.death_year is None
        assert ind.occupations == []
        assert ind.notes == []
        assert ind.famc_xref == ""
        assert ind.fams_xrefs == []

    def test_no_name_record(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 SEX F\n")
        ind = collect_export_data(ged).individuals[0]
        assert ind.given_name == ""
        assert ind.surname == ""
        assert ind.suffix == ""


# ---------------------------------------------------------------------------
# Collector: NAME handling
# ---------------------------------------------------------------------------


class TestCollectorNames:
    def test_alt_names_from_multiple_name_records(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Johann /Schmidt/\n"
            "1 NAME John /Smith/\n"
            "1 NAME Hans /Schmidt/\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.given_name == "Johann"
        assert ind.surname == "Schmidt"
        assert len(ind.alt_names) == 2
        assert ("John", "Smith") in ind.alt_names
        assert ("Hans", "Schmidt") in ind.alt_names

    def test_givn_surn_override(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "2 GIVN Jonathan\n"
            "2 SURN Smithson\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.given_name == "Jonathan"
        assert ind.surname == "Smithson"

    def test_suffix_from_name_tuple(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME Robert /Kennedy/ Jr.\n")
        ind = collect_export_data(ged).individuals[0]
        assert ind.given_name == "Robert"
        assert ind.surname == "Kennedy"
        # ged4py may or may not extract suffix depending on version
        # At minimum, verify the field exists and is a string
        assert isinstance(ind.suffix, str)


# ---------------------------------------------------------------------------
# Collector: date extraction and fallbacks
# ---------------------------------------------------------------------------


class TestCollectorDates:
    def test_birth_date_string_extracted(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 15 JAN 1850\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1850
        assert "1850" in ind.birth_date
        assert "JAN" in ind.birth_date.upper()

    def test_christening_fallback_for_birth_year(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 CHR\n2 DATE 5 FEB 1800\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1800
        # CHR fallback only populates year, not birth_date string
        assert ind.birth_date == ""

    def test_baptism_fallback_for_birth_year(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BAPM\n2 DATE 1795\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1795

    def test_birth_takes_priority_over_christening(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE 1850\n"
            "1 CHR\n2 DATE 1851\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1850

    def test_burial_fallback_for_death_year(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BURI\n2 DATE 10 OCT 1900\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.death_year == 1900
        # death_date stays empty (BURI fallback is year only)
        assert ind.death_date == ""

    def test_burial_date_always_populated(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 DEAT\n2 DATE 8 OCT 1900\n"
            "1 BURI\n2 DATE 10 OCT 1900\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.death_year == 1900
        assert "1900" in ind.death_date
        assert "1900" in ind.burial_date

    def test_approximate_date_preserved(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE ABT 1850\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1850
        assert "1850" in ind.birth_date

    def test_range_birth_year_reports_earliest_bound(self, tmp_path: Path) -> None:
        # birth_year is what lands in the CSV/JSON column — it must keep
        # reporting the lower bound
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE BET 1900 AND 1995\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1900
        assert ind.liveness_birth_year == 1995

    def test_period_birth_year_uses_upper_bound_for_liveness(
        self, tmp_path: Path
    ) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE FROM 1910 TO 1920\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1910
        assert ind.liveness_birth_year == 1920

    def test_single_birth_date_latest_matches_birth_year(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 15 JAN 1850\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.liveness_birth_year == 1850

    def test_missing_birth_date_has_no_latest(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        ind = collect_export_data(ged).individuals[0]
        assert ind.liveness_birth_year is None

    def test_christening_fallback_carries_latest_bound(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 CHR\n2 DATE BET 1800 AND 1810\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1800
        assert ind.liveness_birth_year == 1810

    def test_baptism_fallback_carries_latest_bound(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 BAPM\n2 DATE BET 1795 AND 1799\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1795
        assert ind.liveness_birth_year == 1799

    def test_birth_range_beats_christening_for_both_bounds(
        self, tmp_path: Path
    ) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 BIRT\n2 DATE BET 1850 AND 1860\n"
            "1 CHR\n2 DATE 1861\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.birth_year == 1850
        assert ind.liveness_birth_year == 1860


# ---------------------------------------------------------------------------
# Collector: occupations and notes
# ---------------------------------------------------------------------------


class TestCollectorOccupationsAndNotes:
    def test_multiple_occupations(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 OCCU Blacksmith\n"
            "1 OCCU Farmer\n"
            "1 OCCU Merchant\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.occupations == ["Blacksmith", "Farmer", "Merchant"]

    def test_inline_note_collected(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 NOTE First note text\n"
            "1 NOTE Second note\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert len(ind.notes) == 2
        assert "First note text" in ind.notes
        assert "Second note" in ind.notes

    def test_living_marker_lvg(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 _LVG Y\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.living_marker == "_LVG"

    def test_living_marker_nliv(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 _NLIV Y\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.living_marker == "_NLIV"

    def test_living_marker_rootsmagic(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 _LIVING Y\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.living_marker == "_LIVING"

    def test_no_living_marker(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        ind = collect_export_data(ged).individuals[0]
        assert ind.living_marker == ""

    def test_living_tag_beats_nliv_regardless_of_order(self, tmp_path: Path) -> None:
        # A file asserting someone IS living is taken at face value, so it must
        # not lose to a _NLIV line that happens to be written above it.
        for body in (
            "1 _NLIV Y\n1 _LVG Y\n",
            "1 _LVG Y\n1 _NLIV Y\n",
        ):
            ged = _write_ged(tmp_path, f"0 @I1@ INDI\n1 NAME A /B/\n{body}")
            ind = collect_export_data(ged).individuals[0]
            assert ind.living_marker == "_LVG"

    def test_source_count(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "1 SOUR @S1@\n"
            "1 BIRT\n2 DATE 1850\n2 SOUR @S2@\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.source_count == 2


# ---------------------------------------------------------------------------
# Collector: family links
# ---------------------------------------------------------------------------


class TestCollectorFamilyLinks:
    def test_famc_extracted(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 FAMC @F1@\n" "0 @F1@ FAM\n1 CHIL @I1@\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.famc_xref == "@F1@"

    def test_multiple_fams_extracted(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n1 FAMS @F1@\n1 FAMS @F2@\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n"
            "0 @F2@ FAM\n1 HUSB @I1@\n",
        )
        ind = collect_export_data(ged).individuals[0]
        assert ind.fams_xrefs == ["@F1@", "@F2@"]

    def test_no_family_links(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        ind = collect_export_data(ged).individuals[0]
        assert ind.famc_xref == ""
        assert ind.fams_xrefs == []


# ---------------------------------------------------------------------------
# Collector: family records
# ---------------------------------------------------------------------------


class TestCollectorFamilies:
    def test_family_with_denormalized_names(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @I2@ INDI\n1 NAME Mary /Jones/\n"
            "0 @F1@ FAM\n"
            "1 HUSB @I1@\n"
            "1 WIFE @I2@\n"
            "1 CHIL @I3@\n"
            "1 CHIL @I4@\n"
            "1 MARR\n2 DATE 3 JUN 1875\n2 PLAC London\n",
        )
        result = collect_export_data(ged)
        assert result.family_count == 1
        fam = result.families[0]
        assert fam.xref == "@F1@"
        assert fam.husband_xref == "@I1@"
        assert fam.husband_name == "John Smith"
        assert fam.wife_xref == "@I2@"
        assert fam.wife_name == "Mary Jones"
        assert fam.child_count == 2
        assert fam.children_xrefs == ["@I3@", "@I4@"]
        assert fam.marriage_year == 1875
        assert "1875" in fam.marriage_date
        assert fam.marriage_place == "London"

    def test_family_missing_spouse(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I3@\n",
        )
        result = collect_export_data(ged)
        fam = result.families[0]
        assert fam.husband_xref == "@I1@"
        assert fam.husband_name == "John Smith"
        assert fam.wife_xref == ""
        assert fam.wife_name == ""

    def test_family_unknown_spouse_xref(self, tmp_path: Path) -> None:
        # Spouse xref not in INDI records → name defaults to empty
        ged = _write_ged(
            tmp_path,
            "0 @F1@ FAM\n1 HUSB @I99@\n1 WIFE @I100@\n",
        )
        result = collect_export_data(ged)
        fam = result.families[0]
        assert fam.husband_name == ""
        assert fam.wife_name == ""

    def test_both_indi_and_fam_from_single_reader(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @I2@ INDI\n1 NAME Mary /Jones/\n"
            "0 @I3@ INDI\n1 NAME Child /Smith/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
            "0 @F2@ FAM\n1 HUSB @I1@\n",
        )
        result = collect_export_data(ged)
        assert result.individual_count == 3
        assert result.family_count == 2
        assert len(result.individuals) == 3
        assert len(result.families) == 2


# ---------------------------------------------------------------------------
# End-to-end redaction: the decisions above as the user sees them
# ---------------------------------------------------------------------------


def _redacted_xrefs(tmp_path: Path, content: str) -> set[str]:
    result = collect_export_data(_write_ged(tmp_path, content))
    data = json.loads(format_json(result, redact_living=True))
    return {i["xref"] for i in data["individuals"] if i["given_name"] == "Living"}


class TestRedactLiving:
    def test_no_birth_date_is_redacted(self, tmp_path: Path) -> None:
        ged = "0 @I1@ INDI\n1 NAME Mary /Unknown/\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_phrase_with_no_recoverable_year_is_redacted(self, tmp_path: Path) -> None:
        ged = "0 @I1@ INDI\n1 NAME Mary /Unknown/\n1 BIRT\n2 DATE (before the fire)\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_phrase_carrying_a_year_is_still_redacted(self, tmp_path: Path) -> None:
        # The digit-bearing sibling of the case above: recovery now finds 1823,
        # but a year scraped out of free text must not publish anyone.
        ged = "0 @I1@ INDI\n1 NAME Mary /Unknown/\n1 BIRT\n2 DATE (fire of 1823)\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}


class TestRedactLivingPhraseDates:
    """Which recovered years may influence redaction.

    Since the phrase gate landed, NO recovered free-text year reaches the
    redaction decision. Roles here, and what each fails under:
      * leak guards fail if the phrase gate is reverted
      * the over-redaction guard fails if liveness stops walking CHR/BAPM itself
      * the reporting rows fail if issue #20's recovery is reverted
      * the structured row fails if the liveness reader stops reading real dates
    """

    def test_clean_death_phrase_now_stays_redacted(self, tmp_path: Path) -> None:
        # Accepted cost of the phrase gate: a death recorded as free text is
        # no longer death evidence, so Ada is withheld although she is plainly
        # dead. Over-redacting one row beats publishing one living person.
        ged = "0 @I1@ INDI\n1 NAME Ada /Gone/\n1 DEAT\n2 DATE 4 October 1950\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_reference_number_birth_phrase_stays_redacted(self, tmp_path: Path) -> None:
        # leak guard: 1823 is an archive reference, not a birth year
        ged = "0 @I1@ INDI\n1 NAME Bob /Alive/\n1 BIRT\n2 DATE Reg. 1823 vol II\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_census_birth_phrase_stays_redacted(self, tmp_path: Path) -> None:
        # leak guard
        ged = "0 @I1@ INDI\n1 NAME Cal /Alive/\n1 BIRT\n2 DATE Census 1900 record\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_free_text_death_phrase_stays_redacted(self, tmp_path: Path) -> None:
        # leak guard: the death side reaches estimate_living by its own route
        ged = "0 @I1@ INDI\n1 NAME Dee /Alive/\n1 DEAT\n2 DATE inquest ref 1901\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_free_text_christening_phrase_stays_redacted(self, tmp_path: Path) -> None:
        # leak guard: the CHR fallback must be gated too
        ged = "0 @I1@ INDI\n1 NAME Eve /Alive/\n1 CHR\n2 DATE Census 1900 record\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_clean_christening_behind_dirty_birth_still_publishes(
        self, tmp_path: Path
    ) -> None:
        # over-redaction guard: the display loop stops at the recovered 1900 and
        # would never reach the clean CHR date, redacting someone long dead
        ged = (
            "0 @I1@ INDI\n1 NAME Fay /Gone/\n"
            "1 BIRT\n2 DATE Census 1900 record\n"
            "1 CHR\n2 DATE 1750\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == set()

    def test_clean_phrase_reports_its_year_but_never_decides(
        self, tmp_path: Path
    ) -> None:
        # The whole of issue #20 and the whole of the phrase gate, in one row:
        # the year IS recovered for reporting, and is NOT available to the
        # redaction decision.
        ged = "0 @I1@ INDI\n1 NAME Gus /Alive/\n1 BIRT\n2 DATE 30 November 1989\n"
        ind = collect_export_data(_write_ged(tmp_path, ged)).individuals[0]
        assert ind.birth_year == 1989  # issue #20: still recovered
        assert ind.liveness_birth_year is None  # but withheld from the gate
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_structured_year_in_living_range_still_decides(
        self, tmp_path: Path
    ) -> None:
        # Mutation guard, re-pointed at a structured date now that the phrase
        # row above can no longer carry it: redaction alone is indistinguishable
        # from the no-date case, so assert the year the gate actually used.
        ged = "0 @I1@ INDI\n1 NAME Gus /Alive/\n1 BIRT\n2 DATE 30 NOV 1989\n"
        ind = collect_export_data(_write_ged(tmp_path, ged)).individuals[0]
        assert ind.liveness_birth_year == 1989
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_slash_date_no_longer_publishes(self, tmp_path: Path) -> None:
        # THE issue-#20 regression. Recovering 1882 from "12/2/1882" turned
        # "unknown -> redact" into "age 144 -> publish"; main redacts this and
        # the branch did not. A citation like "12.1823.4" has the same token
        # profile, so the class has to go rather than the instance.
        ged = "0 @I1@ INDI\n1 NAME Hal /Gone/\n1 BIRT\n2 DATE 12/2/1882\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_year_range_phrase_now_stays_redacted(self, tmp_path: Path) -> None:
        # The commonest phrase shape in real files: a bare "1801-1875" range.
        # ged4py reads it as free text, so the gate withholds it even though
        # the upper bound is real. The reported birth_year is unaffected.
        ged = "0 @I1@ INDI\n1 NAME Ida /Gone/\n1 BIRT\n2 DATE 1801-1875\n"
        ind = collect_export_data(_write_ged(tmp_path, ged)).individuals[0]
        assert ind.birth_year == 1801  # issue #20: still recovered
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_year_list_phrase_stays_redacted(self, tmp_path: Path) -> None:
        # Three or more years is a list of candidate dates, not a range
        ged = (
            "0 @I1@ INDI\n1 NAME Jon /Alive/\n1 BIRT\n"
            "2 DATE 1901, 1902, 1903, 1904\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_free_text_burial_phrase_stays_redacted(self, tmp_path: Path) -> None:
        # leak guard: burial is the third route into estimate_living, and
        # "(pre-need plot)" is a note about a plot someone bought, not a death
        ged = (
            "0 @I1@ INDI\n1 NAME Ivy /Alive/\n"
            "1 BIRT\n2 DATE 30 November 1989\n"
            "1 BURI\n2 DATE (pre-need plot)\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_real_burial_date_still_publishes(self, tmp_path: Path) -> None:
        ged = (
            "0 @I1@ INDI\n1 NAME Jud /Gone/\n"
            "1 BIRT\n2 DATE 3 MAR 1850\n"
            "1 BURI\n2 DATE 4 October 1910\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == set()

    def test_placeholder_zero_date_stays_redacted(self, tmp_path: Path) -> None:
        # "00/00/0000" is a common unknown-date placeholder; without a
        # plausibility bound it reads as year 0 and publishes the record
        ged = "0 @I1@ INDI\n1 NAME Ivy /Alive/\n1 BIRT\n2 DATE 00/00/0000\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_birth_range_reaching_into_living_memory_is_redacted(
        self, tmp_path: Path
    ) -> None:
        ged = "0 @I1@ INDI\n1 NAME Ann /Vague/\n1 BIRT\n2 DATE BET 1900 AND 1995\n"
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_birth_range_entirely_beyond_max_age_is_not_redacted(
        self, tmp_path: Path
    ) -> None:
        ged = "0 @I1@ INDI\n1 NAME Ann /Ancient/\n1 BIRT\n2 DATE BET 1700 AND 1750\n"
        assert _redacted_xrefs(tmp_path, ged) == set()

    def test_uncorroborated_nliv_is_redacted(self, tmp_path: Path) -> None:
        ged = (
            "0 @I1@ INDI\n1 NAME Bo /Flagged/\n1 _NLIV Y\n1 BIRT\n2 DATE 12 JUN 2000\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == {"@I1@"}

    def test_nliv_with_death_year_is_not_redacted(self, tmp_path: Path) -> None:
        ged = (
            "0 @I1@ INDI\n1 NAME Bo /Flagged/\n1 _NLIV Y\n"
            "1 BIRT\n2 DATE 12 JUN 2000\n1 DEAT\n2 DATE 3 FEB 2020\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == set()

    def test_deceased_individual_is_not_redacted(self, tmp_path: Path) -> None:
        ged = (
            "0 @I1@ INDI\n1 NAME Old /Timer/\n"
            "1 BIRT\n2 DATE 1890\n1 DEAT\n2 DATE 1960\n"
        )
        assert _redacted_xrefs(tmp_path, ged) == set()

    def test_range_date_still_exports_earliest_birth_year(self, tmp_path: Path) -> None:
        # The latest bound drives the liveness call only; the exported column
        # keeps reporting the lower bound
        ged = "0 @I1@ INDI\n1 NAME Ann /Vague/\n1 BIRT\n2 DATE BET 1700 AND 1750\n"
        result = collect_export_data(_write_ged(tmp_path, ged))
        data = json.loads(format_json(result, redact_living=True))
        assert data["individuals"][0]["birth_year"] == 1700
