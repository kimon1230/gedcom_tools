from __future__ import annotations

import pytest

from gedcom_tools.commands.compare.phonetics import soundex


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
