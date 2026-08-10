from __future__ import annotations

import pytest
from rapidfuzz.distance import JaroWinkler

from gedcom_tools.commands.compare.models import CompareIndividual, MatchScore
from gedcom_tools.commands.compare.scorer import score_pair


def _ind(
    xref: str = "@I1@",
    source: str = "A",
    surname_normalized: str = "",
    given_name_normalized: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    birth_place_normalized: str = "",
    death_place_normalized: str = "",
    sex: str = "",
    surname_phonetic: str = "",
    surname_phonetic_alt: str = "",
    given_phonetic: str = "",
    given_phonetic_alt: str = "",
    alt_surnames_normalized: list[str] | None = None,
    alt_given_names_normalized: list[str] | None = None,
    **kwargs: object,
) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file=source,
        surname_normalized=surname_normalized,
        given_name_normalized=given_name_normalized,
        birth_year=birth_year,
        death_year=death_year,
        birth_place_normalized=birth_place_normalized,
        death_place_normalized=death_place_normalized,
        sex=sex,
        surname_phonetic=surname_phonetic,
        surname_phonetic_alt=surname_phonetic_alt,
        given_phonetic=given_phonetic,
        given_phonetic_alt=given_phonetic_alt,
        alt_surnames_normalized=alt_surnames_normalized or [],
        alt_given_names_normalized=alt_given_names_normalized or [],
        **kwargs,
    )


class TestYearProximity:
    def _pair_with_years(self, year_a: int, year_b: int) -> MatchScore:
        a = _ind(
            xref="@I1@",
            source="A",
            surname_normalized="smith",
            given_name_normalized="john",
            surname_phonetic="S530",
            sex="M",
            birth_year=year_a,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            surname_phonetic="S530",
            sex="M",
            birth_year=year_b,
        )
        return score_pair(a, b)

    def test_exact_year_match(self) -> None:
        result = self._pair_with_years(1850, 1850)
        assert result.field_scores["Birth Year"] == pytest.approx(1.0)

    def test_one_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1851)
        assert result.field_scores["Birth Year"] == pytest.approx(0.85)

    def test_two_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1852)
        assert result.field_scores["Birth Year"] == pytest.approx(0.70)

    def test_three_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1853)
        assert result.field_scores["Birth Year"] == pytest.approx(0.50)

    def test_five_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1855)
        assert result.field_scores["Birth Year"] == pytest.approx(0.25)

    def test_seven_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1857)
        assert result.field_scores["Birth Year"] == pytest.approx(0.10)

    def test_ten_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1860)
        assert result.field_scores["Birth Year"] == pytest.approx(0.05)

    def test_beyond_ten_years(self) -> None:
        result = self._pair_with_years(1850, 1861)
        assert result.field_scores["Birth Year"] == pytest.approx(0.0)

    def test_four_year_diff(self) -> None:
        result = self._pair_with_years(1850, 1854)
        assert result.field_scores["Birth Year"] == pytest.approx(0.25)


class TestPlaceScoring:
    def _pair_with_places(self, place_a: str, place_b: str) -> MatchScore:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            birth_place_normalized=place_a,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            birth_place_normalized=place_b,
        )
        return score_pair(a, b)

    def test_identical_places(self) -> None:
        result = self._pair_with_places("london, england", "london, england")
        assert result.field_scores["Birth Place"] == pytest.approx(1.0)

    def test_different_granularity(self) -> None:
        result = self._pair_with_places("london, england", "london, middlesex, england")
        assert result.field_scores["Birth Place"] == pytest.approx(1.0)

    def test_completely_different(self) -> None:
        result = self._pair_with_places("london, england", "paris, france")
        # JW("london","paris")=0.0, JW("england","france")~0.37
        # greedy: shorter=2, avg of best matches — both scores are low
        assert result.field_scores["Birth Place"] < 0.3

    def test_single_component_match(self) -> None:
        result = self._pair_with_places("london", "london")
        assert result.field_scores["Birth Place"] == pytest.approx(1.0)

    def test_consumption_prevents_double_match(self) -> None:
        result = self._pair_with_places(
            "springfield, springfield", "springfield, illinois"
        )
        # First springfield matches and consumes springfield from B,
        # second springfield matches against "illinois" (low JW)
        assert result.field_scores["Birth Place"] < 1.0
        assert result.field_scores["Birth Place"] == pytest.approx(0.7190, abs=0.01)


class TestNameScoring:
    def _pair_with_surnames(self, name_a: str, name_b: str) -> MatchScore:
        a = _ind(
            surname_normalized=name_a, given_name_normalized="john", birth_year=1850
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized=name_b,
            given_name_normalized="john",
            birth_year=1850,
        )
        return score_pair(a, b)

    def test_identical_names(self) -> None:
        result = self._pair_with_surnames("smith", "smith")
        assert result.field_scores["Surname"] == pytest.approx(1.0)

    def test_similar_names_jw(self) -> None:
        result = self._pair_with_surnames("smith", "smyth")
        assert result.field_scores["Surname"] > 0.8

    def test_different_names(self) -> None:
        result = self._pair_with_surnames("smith", "jones")
        assert result.field_scores["Surname"] == pytest.approx(0.0)


class TestMultiNameCartesian:
    def test_alt_surname_match(self) -> None:
        a = _ind(
            surname_normalized="jones",
            given_name_normalized="john",
            alt_surnames_normalized=["williams"],
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="williams",
            given_name_normalized="john",
            birth_year=1850,
        )
        result = score_pair(a, b)
        # "williams" from A's alts matches "williams" primary on B
        assert result.field_scores["Surname"] == pytest.approx(1.0)

    def test_alt_to_alt_match(self) -> None:
        a = _ind(
            surname_normalized="jones",
            given_name_normalized="john",
            alt_surnames_normalized=["williams"],
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="brown",
            given_name_normalized="john",
            alt_surnames_normalized=["williams"],
            birth_year=1850,
        )
        result = score_pair(a, b)
        # A's alt "williams" matches B's alt "williams"
        assert result.field_scores["Surname"] == pytest.approx(1.0)

    def test_best_match_wins(self) -> None:
        a = _ind(
            surname_normalized="jones",
            given_name_normalized="john",
            alt_surnames_normalized=["williams", "smith"],
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="brown",
            given_name_normalized="john",
            alt_surnames_normalized=["smyth"],
            birth_year=1850,
        )
        result = score_pair(a, b)
        # Best match is "smith" vs "smyth" (JW ~0.89), beats jones/brown (0.0)
        expected_jw = JaroWinkler.similarity("smith", "smyth")
        assert result.field_scores["Surname"] == pytest.approx(expected_jw, abs=0.001)


class TestPhoneticBonus:
    def test_bonus_applied_in_range(self) -> None:
        # becker vs baker: JW ~0.765, in [0.50, 0.85] range
        base_jw = JaroWinkler.similarity("becker", "baker")
        assert 0.50 <= base_jw <= 0.85  # sanity check

        a = _ind(
            surname_normalized="becker",
            given_name_normalized="john",
            surname_phonetic="B260",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="baker",
            given_name_normalized="john",
            surname_phonetic="B260",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.field_scores["Surname"] == pytest.approx(
            base_jw + 0.05, abs=0.001
        )

    def test_no_bonus_above_range(self) -> None:
        # johnson vs jonson: JW ~0.962, above 0.85
        base_jw = JaroWinkler.similarity("johnson", "jonson")
        assert base_jw > 0.85  # sanity check

        a = _ind(
            surname_normalized="johnson",
            given_name_normalized="john",
            surname_phonetic="J525",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="jonson",
            given_name_normalized="john",
            surname_phonetic="J525",
            birth_year=1850,
        )
        result = score_pair(a, b)
        # No bonus applied — JW is already above 0.85
        assert result.field_scores["Surname"] == pytest.approx(base_jw, abs=0.001)

    def test_no_bonus_below_range(self) -> None:
        # baker vs stone: JW ~0.467, below 0.50
        base_jw = JaroWinkler.similarity("baker", "stone")
        assert base_jw < 0.50  # sanity check

        a = _ind(
            surname_normalized="baker",
            given_name_normalized="john",
            surname_phonetic="B260",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="stone",
            given_name_normalized="john",
            surname_phonetic="B260",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.field_scores["Surname"] == pytest.approx(base_jw, abs=0.001)

    def test_no_bonus_different_soundex(self) -> None:
        # becker vs baker: JW ~0.765, in range, but different Soundex codes
        base_jw = JaroWinkler.similarity("becker", "baker")
        assert 0.50 <= base_jw <= 0.85  # sanity check

        a = _ind(
            surname_normalized="becker",
            given_name_normalized="john",
            surname_phonetic="B260",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="baker",
            given_name_normalized="john",
            surname_phonetic="B460",
            birth_year=1850,
        )
        result = score_pair(a, b)
        # No bonus — Soundex codes differ
        assert result.field_scores["Surname"] == pytest.approx(base_jw, abs=0.001)

    def test_metaphone_cross_code_bonus(self) -> None:
        # Primary codes differ, but A's alt matches B's primary → bonus applies
        base_jw = JaroWinkler.similarity("becker", "baker")
        assert 0.50 <= base_jw <= 0.85

        a = _ind(
            surname_normalized="becker",
            given_name_normalized="john",
            surname_phonetic="PKR",
            surname_phonetic_alt="PKR",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="baker",
            given_name_normalized="john",
            surname_phonetic="PKR",
            surname_phonetic_alt="",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.field_scores["Surname"] == pytest.approx(
            base_jw + 0.05, abs=0.001
        )

    def test_metaphone_no_bonus_no_overlap(self) -> None:
        # No codes overlap → no bonus even with metaphone
        base_jw = JaroWinkler.similarity("becker", "baker")
        assert 0.50 <= base_jw <= 0.85

        a = _ind(
            surname_normalized="becker",
            given_name_normalized="john",
            surname_phonetic="AAA",
            surname_phonetic_alt="BBB",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="baker",
            given_name_normalized="john",
            surname_phonetic="CCC",
            surname_phonetic_alt="DDD",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.field_scores["Surname"] == pytest.approx(base_jw, abs=0.001)

    def test_empty_codes_no_bonus(self) -> None:
        # Both sides have empty phonetic codes → no bonus
        base_jw = JaroWinkler.similarity("becker", "baker")
        assert 0.50 <= base_jw <= 0.85

        a = _ind(
            surname_normalized="becker",
            given_name_normalized="john",
            surname_phonetic="",
            surname_phonetic_alt="",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="baker",
            given_name_normalized="john",
            surname_phonetic="",
            surname_phonetic_alt="",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.field_scores["Surname"] == pytest.approx(base_jw, abs=0.001)


class TestSexHandling:
    def _rich_pair(self, sex_a: str, sex_b: str, **kwargs: object) -> MatchScore:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
            sex=sex_a,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
            sex=sex_b,
        )
        return score_pair(a, b, **kwargs)

    def test_same_sex_scored(self) -> None:
        result = self._rich_pair("M", "M")
        assert "Sex" in result.field_scores
        assert result.field_scores["Sex"] == pytest.approx(1.0)

    def test_both_empty_sex_skipped(self) -> None:
        result = self._rich_pair("", "")
        assert "Sex" not in result.field_scores

    def test_one_empty_sex_skipped(self) -> None:
        result = self._rich_pair("M", "")
        assert "Sex" not in result.field_scores

    def test_mismatch_penalty(self) -> None:
        same_sex = self._rich_pair("M", "M")
        mismatch = self._rich_pair("M", "F")
        assert "Sex" not in mismatch.field_scores
        # Total should be ~0.7x the same-sex total (sans the sex weight contribution)
        assert mismatch.total < same_sex.total
        assert mismatch.sex_penalty is True
        assert same_sex.sex_penalty is False

    def test_mismatch_reject(self) -> None:
        result = self._rich_pair("M", "F", reject_sex_mismatch=True)
        assert result.total == pytest.approx(0.0)
        assert result.classification == "non_match"


class TestClassification:
    def test_certain_with_four_fields(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
            sex="M",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
            sex="M",
        )
        result = score_pair(a, b)
        assert result.classification == "certain"
        assert result.comparable_field_count >= 4

    def test_probable_with_moderate_score(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smyth",
            given_name_normalized="jon",
            birth_year=1852,
            death_year=1923,
            birth_place_normalized="london, middlesex, england",
        )
        result = score_pair(a, b)
        assert result.classification == "probable"
        assert result.total >= 0.65
        assert result.total < 0.85

    def test_non_match_low_score(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="jones",
            given_name_normalized="mary",
            birth_year=1900,
            death_year=1980,
        )
        result = score_pair(a, b)
        assert result.classification == "non_match"
        assert result.total < 0.65

    def test_three_fields_capped_at_probable(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.comparable_field_count == 3
        # Even with perfect scores, 3 fields caps at probable
        assert result.classification == "probable"

    def test_name_only_capped_at_probable(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            sex="M",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            sex="M",
        )
        result = score_pair(a, b)
        # 3 fields (Surname, Given Name, Sex) but no corroborating fields
        assert result.name_only is True
        assert result.classification != "certain"

    def test_fewer_than_three_fields(self) -> None:
        a = _ind(surname_normalized="smith", given_name_normalized="john")
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
        )
        result = score_pair(a, b)
        assert result.comparable_field_count == 2
        assert result.classification == "non_match"

    def test_custom_thresholds(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
        )
        # certain_threshold above 1.0 makes "certain" unreachable
        result = score_pair(a, b, certain_threshold=1.01)
        assert result.classification == "probable"

        # Lowering probable_threshold lets moderate matches pass
        low = score_pair(a, b, probable_threshold=0.10)
        assert low.classification in ("certain", "probable")


class TestInsufficientData:
    def test_insufficient_few_fields(self) -> None:
        a = _ind(surname_normalized="smith", given_name_normalized="john")
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
        )
        result = score_pair(a, b)
        assert result.comparable_field_count == 2
        assert result.insufficient_data is True

    def test_insufficient_no_corroboration(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            sex="M",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            sex="M",
        )
        result = score_pair(a, b)
        # 3 fields but none are corroborating (no years/places)
        assert result.comparable_field_count == 3
        assert result.insufficient_data is True

    def test_sufficient_with_corroboration(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
        )
        result = score_pair(a, b)
        assert result.comparable_field_count == 3
        assert result.insufficient_data is False

    def test_name_only_flag(self) -> None:
        a = _ind(surname_normalized="smith", given_name_normalized="john")
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
        )
        result = score_pair(a, b)
        assert result.name_only is True


class TestEdgeCases:
    def test_empty_individuals(self) -> None:
        a = _ind()
        b = _ind(xref="@I2@", source="B")
        result = score_pair(a, b)
        assert result.total == pytest.approx(0.0)
        assert result.comparable_field_count == 0

    def test_identical_individuals(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
            death_place_normalized="manchester, england",
            sex="M",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
            death_year=1920,
            birth_place_normalized="london, england",
            death_place_normalized="manchester, england",
            sex="M",
        )
        result = score_pair(a, b)
        assert result.total == pytest.approx(1.0)
        assert result.classification == "certain"
        assert result.comparable_field_count == 7

    def test_missing_year_skipped(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_year=1850,
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
        )
        result = score_pair(a, b)
        assert "Birth Year" not in result.field_scores

    def test_missing_place_skipped(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_place_normalized="london, england",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
        )
        result = score_pair(a, b)
        assert "Birth Place" not in result.field_scores


class TestLazyRapidfuzzImport:
    """rapidfuzz costs ~30 ms to import and cli.py reaches this module on
    every invocation, so the dependency is bound on first score instead of at
    import time. This test file imports it eagerly at the top, so both checks
    have to run in a clean interpreter.
    """

    def _probe(self, body: str) -> str:
        import subprocess
        import sys

        # Fixed argv, no shell: sys.executable -c on a literal body.
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", body],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_cli_import_does_not_pull_in_rapidfuzz(self) -> None:
        assert (
            self._probe(
                "import sys, gedcom_tools.cli; print('rapidfuzz' in sys.modules)"
            )
            == "False"
        )

    def test_scoring_pulls_it_in_on_demand(self) -> None:
        # The other half of the deal: deferred, not dropped.
        assert (
            self._probe(
                "import sys;"
                "from gedcom_tools.commands.compare.scorer import _best_name_jw;"
                "_best_name_jw('smith', [], 'smyth', []);"
                "print('rapidfuzz' in sys.modules)"
            )
            == "True"
        )

    def test_place_scoring_works_without_a_module_level_binding(self) -> None:
        a = _ind(
            surname_normalized="smith",
            given_name_normalized="john",
            birth_place_normalized="london, england",
        )
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smith",
            given_name_normalized="john",
            birth_place_normalized="london, england",
        )
        assert score_pair(a, b).field_scores["Birth Place"] == 1.0

    def test_name_scoring_matches_a_direct_jarowinkler_call(self) -> None:
        a = _ind(surname_normalized="smith", given_name_normalized="john")
        b = _ind(
            xref="@I2@",
            source="B",
            surname_normalized="smyth",
            given_name_normalized="john",
        )
        result = score_pair(a, b)
        assert result.field_scores["Surname"] == pytest.approx(
            round(JaroWinkler.similarity("smith", "smyth"), 4)
        )
