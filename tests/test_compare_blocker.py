from __future__ import annotations

from gedcom_tools.commands.compare.blocker import generate_candidates
from gedcom_tools.commands.compare.models import CompareIndividual


def _ind(
    xref: str,
    source: str = "A",
    surname_soundex: str = "",
    given_name_soundex: str = "",
    birth_decade: str = "",
    death_decade: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    **kwargs: object,
) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file=source,
        surname_soundex=surname_soundex,
        given_name_soundex=given_name_soundex,
        birth_decade=birth_decade,
        death_decade=death_decade,
        birth_year=birth_year,
        death_year=death_year,
        **kwargs,
    )


class TestPass1SurnameBirth:
    def test_matching_soundex_and_decade(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_soundex="S530", birth_decade="1850s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs

    def test_same_soundex_different_decade(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_soundex="S530", birth_decade="1900s")]
        pairs = generate_candidates(a, b)
        # Pass 1 won't fire — different decades. No other keys either.
        assert ("@I1@", "@I2@") not in pairs

    def test_different_soundex_same_decade(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_soundex="J500", birth_decade="1850s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") not in pairs


class TestPass2SurnameDeath:
    def test_surname_death_match_without_birth(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="M460", death_decade="1920s")]
        b = [_ind("@I2@", "B", surname_soundex="M460", death_decade="1920s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs


class TestPass3GivenBirth:
    def test_given_name_catches_surname_change(self) -> None:
        # Different surname (marriage) but same given name + birth decade
        a = [
            _ind(
                "@I1@",
                "A",
                surname_soundex="S530",
                given_name_soundex="M600",
                birth_decade="1870s",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_soundex="J520",
                given_name_soundex="M600",
                birth_decade="1870s",
            )
        ]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs


class TestPass4ExactYears:
    def test_both_years_match(self) -> None:
        a = [_ind("@I1@", "A", birth_year=1812, death_year=1879)]
        b = [_ind("@I2@", "B", birth_year=1812, death_year=1879)]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs

    def test_one_missing_year_no_match(self) -> None:
        a = [_ind("@I1@", "A", birth_year=1812, death_year=1879)]
        b = [_ind("@I2@", "B", birth_year=1812)]  # no death year
        pairs = generate_candidates(a, b)
        # Pass 4 requires both years present on both sides
        assert ("@I1@", "@I2@") not in pairs


class TestPass5SurnameGiven:
    def test_dateless_records_matched_by_names(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", given_name_soundex="J500")]
        b = [_ind("@I2@", "B", surname_soundex="S530", given_name_soundex="J500")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs


class TestMultiPassUnion:
    def test_same_pair_from_two_passes_appears_once(self) -> None:
        # Will match on pass 1 (surname+birth) AND pass 2 (surname+death)
        a = [
            _ind(
                "@I1@",
                "A",
                surname_soundex="S530",
                birth_decade="1850s",
                death_decade="1920s",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_soundex="S530",
                birth_decade="1850s",
                death_decade="1920s",
            )
        ]
        pairs = generate_candidates(a, b)
        assert pairs == {("@I1@", "@I2@")}

    def test_distinct_pairs_from_different_passes(self) -> None:
        a = [
            _ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s"),
            _ind("@I3@", "A", birth_year=1900, death_year=1960),
        ]
        b = [
            _ind("@I2@", "B", surname_soundex="S530", birth_decade="1850s"),
            _ind("@I4@", "B", birth_year=1900, death_year=1960),
        ]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs
        assert ("@I3@", "@I4@") in pairs


class TestBlockSizeCap:
    def test_oversized_block_skipped(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s")]
        # 3 B individuals with same key, max_block_size=2
        b = [
            _ind("@I10@", "B", surname_soundex="S530", birth_decade="1850s"),
            _ind("@I11@", "B", surname_soundex="S530", birth_decade="1850s"),
            _ind("@I12@", "B", surname_soundex="S530", birth_decade="1850s"),
        ]
        pairs = generate_candidates(a, b, max_block_size=2)
        # Block has 3 members, exceeds cap of 2 — all skipped
        assert len(pairs) == 0

    def test_block_at_limit_still_included(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s")]
        b = [
            _ind("@I10@", "B", surname_soundex="S530", birth_decade="1850s"),
            _ind("@I11@", "B", surname_soundex="S530", birth_decade="1850s"),
        ]
        pairs = generate_candidates(a, b, max_block_size=2)
        assert ("@I1@", "@I10@") in pairs
        assert ("@I1@", "@I11@") in pairs


class TestEdgeCases:
    def test_empty_a_list(self) -> None:
        b = [_ind("@I2@", "B", surname_soundex="S530", birth_decade="1850s")]
        assert generate_candidates([], b) == set()

    def test_empty_b_list(self) -> None:
        a = [_ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s")]
        assert generate_candidates(a, []) == set()

    def test_no_blocking_keys_never_paired(self) -> None:
        # Individual with nothing useful — blank everything
        ghost = _ind("@I1@", "A")
        b = [
            _ind(
                "@I2@",
                "B",
                surname_soundex="S530",
                given_name_soundex="J500",
                birth_decade="1850s",
                death_decade="1920s",
                birth_year=1853,
                death_year=1921,
            )
        ]
        pairs = generate_candidates([ghost], b)
        assert len(pairs) == 0

    def test_multiple_a_matching_one_b(self) -> None:
        a = [
            _ind("@I1@", "A", surname_soundex="S530", birth_decade="1850s"),
            _ind("@I3@", "A", surname_soundex="S530", birth_decade="1850s"),
        ]
        b = [_ind("@I2@", "B", surname_soundex="S530", birth_decade="1850s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs
        assert ("@I3@", "@I2@") in pairs
        assert len(pairs) == 2


class TestDeduplication:
    def test_cross_pass_dedup(self) -> None:
        # This individual matches on pass 1, 2, 3, 4, and 5 — still one pair
        a = [
            _ind(
                "@I1@",
                "A",
                surname_soundex="S530",
                given_name_soundex="J500",
                birth_decade="1850s",
                death_decade="1920s",
                birth_year=1853,
                death_year=1921,
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_soundex="S530",
                given_name_soundex="J500",
                birth_decade="1850s",
                death_decade="1920s",
                birth_year=1853,
                death_year=1921,
            )
        ]
        pairs = generate_candidates(a, b)
        assert pairs == {("@I1@", "@I2@")}
