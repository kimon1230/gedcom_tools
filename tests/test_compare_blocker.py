from __future__ import annotations

from gedcom_tools.commands.compare.blocker import (
    DEFAULT_MAX_BLOCK_SIZE,
    describe_oversized_blocks,
    generate_candidates,
)
from gedcom_tools.commands.compare.models import CompareIndividual


def _ind(
    xref: str,
    source: str = "A",
    surname_phonetic: str = "",
    surname_phonetic_alt: str = "",
    given_phonetic: str = "",
    given_phonetic_alt: str = "",
    birth_decade: str = "",
    death_decade: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    **kwargs: object,
) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file=source,
        surname_phonetic=surname_phonetic,
        surname_phonetic_alt=surname_phonetic_alt,
        given_phonetic=given_phonetic,
        given_phonetic_alt=given_phonetic_alt,
        birth_decade=birth_decade,
        death_decade=death_decade,
        birth_year=birth_year,
        death_year=death_year,
        **kwargs,
    )


class TestPass1SurnameBirth:
    def test_matching_soundex_and_decade(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="S530", birth_decade="1850s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs

    def test_same_soundex_different_decade(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="S530", birth_decade="1900s")]
        pairs = generate_candidates(a, b)
        # Pass 1 won't fire — different decades. No other keys either.
        assert ("@I1@", "@I2@") not in pairs

    def test_different_soundex_same_decade(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="J500", birth_decade="1850s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") not in pairs


class TestPass2SurnameDeath:
    def test_surname_death_match_without_birth(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="M460", death_decade="1920s")]
        b = [_ind("@I2@", "B", surname_phonetic="M460", death_decade="1920s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs


class TestPass3GivenBirth:
    def test_given_name_catches_surname_change(self) -> None:
        # Different surname (marriage) but same given name + birth decade
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="S530",
                given_phonetic="M600",
                birth_decade="1870s",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_phonetic="J520",
                given_phonetic="M600",
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
        a = [_ind("@I1@", "A", surname_phonetic="S530", given_phonetic="J500")]
        b = [_ind("@I2@", "B", surname_phonetic="S530", given_phonetic="J500")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs


class TestMultiPassUnion:
    def test_same_pair_from_two_passes_appears_once(self) -> None:
        # Will match on pass 1 (surname+birth) AND pass 2 (surname+death)
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="S530",
                birth_decade="1850s",
                death_decade="1920s",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_phonetic="S530",
                birth_decade="1850s",
                death_decade="1920s",
            )
        ]
        pairs = generate_candidates(a, b)
        assert pairs == {("@I1@", "@I2@")}

    def test_distinct_pairs_from_different_passes(self) -> None:
        a = [
            _ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I3@", "A", birth_year=1900, death_year=1960),
        ]
        b = [
            _ind("@I2@", "B", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I4@", "B", birth_year=1900, death_year=1960),
        ]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs
        assert ("@I3@", "@I4@") in pairs


class TestBlockSizeCap:
    def test_oversized_block_skipped(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        # 3 B individuals with same key, max_block_size=2
        b = [
            _ind("@I10@", "B", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I11@", "B", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I12@", "B", surname_phonetic="S530", birth_decade="1850s"),
        ]
        pairs = generate_candidates(a, b, max_block_size=2)
        # Block has 3 members, exceeds cap of 2 — all skipped
        assert len(pairs) == 0

    def test_block_at_limit_still_included(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [
            _ind("@I10@", "B", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I11@", "B", surname_phonetic="S530", birth_decade="1850s"),
        ]
        pairs = generate_candidates(a, b, max_block_size=2)
        assert ("@I1@", "@I10@") in pairs
        assert ("@I1@", "@I11@") in pairs


class TestOversizedBlockReporting:
    def test_skipped_key_reported(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [
            _ind(f"@I1{n}@", "B", surname_phonetic="S530", birth_decade="1850s")
            for n in range(3)
        ]
        skipped: set[str] = set()
        generate_candidates(a, b, max_block_size=2, oversized_keys=skipped)
        assert skipped == {"S530|1850s"}

    def test_one_fat_block_counts_once_not_once_per_individual(self) -> None:
        # The size check sits inside the loop over side A, so a naive counter
        # would report 40 skipped groups here instead of 1.
        a = [
            _ind(f"@A{n}@", "A", surname_phonetic="S530", birth_decade="1850s")
            for n in range(40)
        ]
        b = [
            _ind(f"@B{n}@", "B", surname_phonetic="S530", birth_decade="1850s")
            for n in range(600)
        ]
        skipped: set[str] = set()
        pairs = generate_candidates(a, b, oversized_keys=skipped)
        assert len(skipped) == 1
        assert pairs == set()

    def test_distinct_keys_counted_separately(self) -> None:
        a = [
            _ind("@A1@", "A", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@A2@", "A", surname_phonetic="J525", birth_decade="1900s"),
        ]
        b = [
            _ind(f"@B{n}@", "B", surname_phonetic="S530", birth_decade="1850s")
            for n in range(3)
        ] + [
            _ind(f"@C{n}@", "B", surname_phonetic="J525", birth_decade="1900s")
            for n in range(3)
        ]
        skipped: set[str] = set()
        generate_candidates(a, b, max_block_size=2, oversized_keys=skipped)
        assert len(skipped) == 2

    def test_no_oversized_block_leaves_set_empty(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="S530", birth_decade="1850s")]
        skipped: set[str] = set()
        generate_candidates(a, b, oversized_keys=skipped)
        assert skipped == set()

    def test_block_at_limit_not_reported(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [
            _ind("@I10@", "B", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I11@", "B", surname_phonetic="S530", birth_decade="1850s"),
        ]
        skipped: set[str] = set()
        generate_candidates(a, b, max_block_size=2, oversized_keys=skipped)
        assert skipped == set()

    def test_key_absent_from_side_b_not_reported(self) -> None:
        # A's key has no block at all -- nothing was dropped, so nothing to say.
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="J525", birth_decade="1900s")]
        skipped: set[str] = set()
        generate_candidates(a, b, max_block_size=1, oversized_keys=skipped)
        assert skipped == set()

    def test_multi_key_pass_reports_alt_code_key(self) -> None:
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="SM0",
                surname_phonetic_alt="XMT",
                birth_decade="1850s",
            )
        ]
        b = [
            _ind(
                f"@B{n}@",
                "B",
                surname_phonetic="XMT",
                surname_phonetic_alt="SMT",
                birth_decade="1850s",
            )
            for n in range(3)
        ]
        skipped: set[str] = set()
        generate_candidates(
            a, b, max_block_size=2, algorithm="metaphone", oversized_keys=skipped
        )
        assert "XMT|1850s" in skipped

    def test_soundex_run_ignores_multi_key_blocks(self) -> None:
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="SM0",
                surname_phonetic_alt="XMT",
                birth_decade="1850s",
            )
        ]
        b = [
            _ind(
                f"@B{n}@",
                "B",
                surname_phonetic="XMT",
                surname_phonetic_alt="SMT",
                birth_decade="1850s",
            )
            for n in range(3)
        ]
        skipped: set[str] = set()
        generate_candidates(a, b, max_block_size=2, oversized_keys=skipped)
        assert skipped == set()

    def test_omitting_the_set_still_works(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [
            _ind(f"@B{n}@", "B", surname_phonetic="S530", birth_decade="1850s")
            for n in range(3)
        ]
        assert generate_candidates(a, b, max_block_size=2) == set()

    def test_same_key_from_two_passes_counted_once(self) -> None:
        # Pass 1 (surname+birth) and pass 3 (given+birth) both produce
        # "S530|1850s" here; it is one key string, so one skipped group.
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="S530",
                given_phonetic="S530",
                birth_decade="1850s",
            )
        ]
        b = [
            _ind(
                f"@B{n}@",
                "B",
                surname_phonetic="S530",
                given_phonetic="S530",
                birth_decade="1850s",
            )
            for n in range(3)
        ]
        skipped: set[str] = set()
        generate_candidates(a, b, max_block_size=2, oversized_keys=skipped)
        # "S530|1850s" is produced by both passes and appears once.  Pass 5
        # (surname + given) contributes a genuinely different group.
        assert skipped == {"S530|1850s", "S530|S530"}


class TestDescribeOversizedBlocks:
    def test_singular_wording(self) -> None:
        msg = describe_oversized_blocks(1, 500)
        assert "1 blocking group exceeded" in msg
        assert "was skipped" in msg

    def test_plural_wording(self) -> None:
        msg = describe_oversized_blocks(3, 500)
        assert "3 blocking groups exceeded" in msg
        assert "were skipped" in msg

    def test_names_the_flag_that_actually_exists(self) -> None:
        msg = describe_oversized_blocks(2, 1200)
        # Rendered without a thousands separator: the advice below tells the
        # user to re-run with a larger value, and type=int rejects "1,200".
        assert "--max-block-size 1200" in msg
        assert "Re-run with a larger --max-block-size" in msg

    def test_default_constant_matches_signature_default(self) -> None:
        assert DEFAULT_MAX_BLOCK_SIZE == 500


class TestEdgeCases:
    def test_empty_a_list(self) -> None:
        b = [_ind("@I2@", "B", surname_phonetic="S530", birth_decade="1850s")]
        assert generate_candidates([], b) == set()

    def test_empty_b_list(self) -> None:
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        assert generate_candidates(a, []) == set()

    def test_no_blocking_keys_never_paired(self) -> None:
        # Individual with nothing useful — blank everything
        ghost = _ind("@I1@", "A")
        b = [
            _ind(
                "@I2@",
                "B",
                surname_phonetic="S530",
                given_phonetic="J500",
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
            _ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s"),
            _ind("@I3@", "A", surname_phonetic="S530", birth_decade="1850s"),
        ]
        b = [_ind("@I2@", "B", surname_phonetic="S530", birth_decade="1850s")]
        pairs = generate_candidates(a, b)
        assert ("@I1@", "@I2@") in pairs
        assert ("@I3@", "@I2@") in pairs
        assert len(pairs) == 2


class TestSecondaryCodePasses:
    def test_metaphone_cross_code_surname_birth(self) -> None:
        # Smith: primary=SM0, alt=XMT. Schmidt: primary=XMT, alt=SMT.
        # Primary codes differ → soundex misses. Multi-key pass catches
        # because A's alt=XMT matches B's primary=XMT in the same block.
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="SM0",
                surname_phonetic_alt="XMT",
                birth_decade="1850s",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_phonetic="XMT",
                surname_phonetic_alt="SMT",
                birth_decade="1850s",
            )
        ]
        # Without metaphone passes, primary codes differ so no match
        pairs_soundex = generate_candidates(a, b, algorithm="soundex")
        assert ("@I1@", "@I2@") not in pairs_soundex
        # With metaphone multi-key passes, cross-code match found
        pairs_meta = generate_candidates(a, b, algorithm="metaphone")
        assert ("@I1@", "@I2@") in pairs_meta

    def test_metaphone_cross_code_surname_given(self) -> None:
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="SM0",
                surname_phonetic_alt="XMT",
                given_phonetic="JN",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_phonetic="XMT",
                surname_phonetic_alt="SMT",
                given_phonetic="JN",
            )
        ]
        pairs = generate_candidates(a, b, algorithm="metaphone")
        assert ("@I1@", "@I2@") in pairs

    def test_soundex_no_extra_passes(self) -> None:
        # With soundex, alt codes are empty so extra passes produce nothing
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="J500", birth_decade="1850s")]
        pairs = generate_candidates(a, b, algorithm="soundex")
        assert ("@I1@", "@I2@") not in pairs

    def test_empty_alt_no_extra_keys(self) -> None:
        # surname_phonetic_alt empty → multi-key functions only produce primary key
        a = [_ind("@I1@", "A", surname_phonetic="S530", birth_decade="1850s")]
        b = [_ind("@I2@", "B", surname_phonetic="S530", birth_decade="1850s")]
        # Even with metaphone algorithm, if alt is empty, only primary keys used
        pairs = generate_candidates(a, b, algorithm="metaphone")
        # Still matches via primary (pass 1)
        assert ("@I1@", "@I2@") in pairs

    def test_same_alt_same_primary_no_duplicate_key(self) -> None:
        # When alt == primary, multi-key function should not produce duplicate key
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="XMT",
                surname_phonetic_alt="XMT",
                birth_decade="1850s",
            )
        ]
        b = [
            _ind(
                "@I2@",
                "B",
                surname_phonetic="XMT",
                surname_phonetic_alt="XMT",
                birth_decade="1850s",
            )
        ]
        pairs = generate_candidates(a, b, algorithm="metaphone")
        assert ("@I1@", "@I2@") in pairs


class TestDeduplication:
    def test_cross_pass_dedup(self) -> None:
        # This individual matches on pass 1, 2, 3, 4, and 5 — still one pair
        a = [
            _ind(
                "@I1@",
                "A",
                surname_phonetic="S530",
                given_phonetic="J500",
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
                surname_phonetic="S530",
                given_phonetic="J500",
                birth_decade="1850s",
                death_decade="1920s",
                birth_year=1853,
                death_year=1921,
            )
        ]
        pairs = generate_candidates(a, b)
        assert pairs == {("@I1@", "@I2@")}
