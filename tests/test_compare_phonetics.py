from __future__ import annotations

import pytest

from gedcom_tools.phonetics import (
    double_metaphone,
    phonetic_codes_match,
    phonetic_encode,
    soundex,
)


class TestSoundex:
    def test_robert(self) -> None:
        assert soundex("Robert") == "R163"

    def test_rupert_matches_robert(self) -> None:
        assert soundex("Rupert") == "R163"

    def test_smith(self) -> None:
        assert soundex("Smith") == "S530"

    def test_smythe_matches_smith(self) -> None:
        assert soundex("Smythe") == "S530"

    def test_adjacent_duplicates_collapsed(self) -> None:
        # S and C both map to 2, but H between them is transparent
        assert soundex("Ashcraft") == "A261"

    def test_short_name_padded(self) -> None:
        assert soundex("Lee") == "L000"

    def test_single_char(self) -> None:
        assert soundex("A") == "A000"

    def test_empty_string(self) -> None:
        assert soundex("") == ""

    def test_washington(self) -> None:
        assert soundex("Washington") == "W252"

    def test_gutierrez(self) -> None:
        assert soundex("Gutierrez") == "G362"

    def test_hw_transparent_between_same_codes(self) -> None:
        # P and F both map to 1; first letter P, F collapsed
        result = soundex("Pfister")
        assert result == "P236"

    def test_non_alpha_stripped(self) -> None:
        assert soundex("O'Brien") == soundex("OBrien")

    @pytest.mark.parametrize("variant", ["smith", "SMITH", "Smith", "sMiTh"])
    def test_case_insensitive(self, variant: str) -> None:
        assert soundex(variant) == "S530"


class TestDoubleMetaphone:
    def test_returns_two_codes(self) -> None:
        p, s = double_metaphone("Smith")
        assert isinstance(p, str) and isinstance(s, str)
        assert p  # primary is non-empty

    def test_empty_string(self) -> None:
        assert double_metaphone("") == ("", "")

    def test_non_alpha_only(self) -> None:
        assert double_metaphone("123!@#") == ("", "")

    def test_lee_primary_nonempty(self) -> None:
        p, _ = double_metaphone("Lee")
        assert p

    def test_diacritic_handling_muller(self) -> None:
        p, _ = double_metaphone("Müller")
        assert p

    def test_apostrophe_stripped(self) -> None:
        # O'Brien should produce same codes as OBrien
        assert double_metaphone("O'Brien") == double_metaphone("OBrien")

    def test_hyphenated_name(self) -> None:
        p, _ = double_metaphone("Lloyd-Webber")
        assert p

    def test_case_insensitive(self) -> None:
        assert double_metaphone("smith") == double_metaphone("SMITH")

    def test_smith_schmidt_share_code(self) -> None:
        sp, ss = double_metaphone("Smith")
        kp, ks = double_metaphone("Schmidt")
        all_smith = {c for c in (sp, ss) if c}
        all_schmidt = {c for c in (kp, ks) if c}
        assert (
            all_smith & all_schmidt
        ), "Smith and Schmidt should share a metaphone code"

    def test_muller_miller_share_code(self) -> None:
        mp, ms = double_metaphone("Müller")
        ip, is_ = double_metaphone("Miller")
        all_muller = {c for c in (mp, ms) if c}
        all_miller = {c for c in (ip, is_) if c}
        assert (
            all_muller & all_miller
        ), "Müller and Miller should share a metaphone code"


class TestPhoneticEncode:
    def test_soundex_mode(self) -> None:
        p, s = phonetic_encode("Smith", "soundex")
        assert p == "S530"
        assert s == ""

    def test_metaphone_mode(self) -> None:
        p, s = phonetic_encode("Smith", "metaphone")
        assert p  # non-empty primary

    def test_unknown_algorithm_raises(self) -> None:
        with pytest.raises(ValueError, match="nysiis"):
            phonetic_encode("Smith", "nysiis")

    def test_default_is_soundex(self) -> None:
        assert phonetic_encode("Smith") == ("S530", "")


class TestPhoneticCodesMatch:
    def test_same_primary(self) -> None:
        assert phonetic_codes_match("A", "", "A", "") is True

    def test_no_overlap(self) -> None:
        assert phonetic_codes_match("A", "", "B", "") is False

    def test_all_empty(self) -> None:
        assert phonetic_codes_match("", "", "", "") is False

    def test_shared_via_alt(self) -> None:
        assert phonetic_codes_match("A", "B", "B", "C") is True

    def test_primary_to_alt(self) -> None:
        assert phonetic_codes_match("A", "", "", "A") is True

    def test_alt_to_primary(self) -> None:
        assert phonetic_codes_match("", "A", "A", "") is True

    def test_alt_to_alt(self) -> None:
        assert phonetic_codes_match("", "A", "", "A") is True

    def test_empty_a_nonempty_b(self) -> None:
        assert phonetic_codes_match("", "", "A", "B") is False

    def test_nonempty_a_empty_b(self) -> None:
        assert phonetic_codes_match("A", "B", "", "") is False

    def test_duplicate_primary_alt(self) -> None:
        # a has same primary and alt — still matches
        assert phonetic_codes_match("A", "A", "A", "B") is True

    def test_catherine_katherine_soundex_no_match(self) -> None:
        # Different initial letters → different soundex codes
        cp, ca = phonetic_encode("Catherine", "soundex")
        kp, ka = phonetic_encode("Katherine", "soundex")
        assert phonetic_codes_match(cp, ca, kp, ka) is False

    def test_catherine_katherine_metaphone_match(self) -> None:
        # Same pronunciation → same metaphone codes despite different spelling
        cp, ca = phonetic_encode("Catherine", "metaphone")
        kp, ka = phonetic_encode("Katherine", "metaphone")
        assert phonetic_codes_match(cp, ca, kp, ka) is True

    def test_smith_schmidt_metaphone_match(self) -> None:
        sp, sa = phonetic_encode("Smith", "metaphone")
        kp, ka = phonetic_encode("Schmidt", "metaphone")
        assert phonetic_codes_match(sp, sa, kp, ka) is True
