from __future__ import annotations

from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    CompareResult,
    FieldDiff,
    MatchPair,
    MatchScore,
)
from gedcom_tools.utils import EncodingInfo


class TestCompareIndividual:

    def test_defaults(self) -> None:
        ind = CompareIndividual(xref="@I1@", source_file="A")
        assert ind.xref == "@I1@"
        assert ind.source_file == "A"
        assert ind.given_name == ""
        assert ind.surname == ""
        assert ind.full_name == ""
        assert ind.sex == ""
        assert ind.birth_year is None
        assert ind.birth_place == ""
        assert ind.death_year is None
        assert ind.death_place == ""
        assert ind.famc_xref is None
        assert ind.fams_xrefs == []
        assert ind.alt_surnames == []
        assert ind.alt_given_names == []
        assert ind.given_name_normalized == ""
        assert ind.surname_normalized == ""
        assert ind.birth_place_normalized == ""
        assert ind.death_place_normalized == ""
        assert ind.alt_surnames_normalized == []
        assert ind.alt_given_names_normalized == []
        assert ind.surname_phonetic == ""
        assert ind.given_phonetic == ""
        assert ind.birth_decade == ""
        assert ind.death_decade == ""

    def test_full_construction(self) -> None:
        ind = CompareIndividual(
            xref="@I55@",
            source_file="B",
            given_name="Eleni",
            surname="Papadopoulos",
            full_name="Eleni Papadopoulos",
            sex="F",
            birth_year=1852,
            birth_place="Athens",
            death_year=1920,
            death_place="Patras",
            famc_xref="@F3@",
            fams_xrefs=["@F10@", "@F11@"],
            alt_surnames=["Papadopoulou"],
            alt_given_names=["Helen"],
            given_name_normalized="eleni",
            surname_normalized="papadopoulos",
            birth_place_normalized="athens",
            death_place_normalized="patras",
            alt_surnames_normalized=["papadopoulou"],
            alt_given_names_normalized=["helen"],
            surname_phonetic="P131",
            given_phonetic="E450",
            birth_decade="1850s",
            death_decade="1920s",
        )
        assert ind.given_name == "Eleni"
        assert ind.surname == "Papadopoulos"
        assert ind.birth_year == 1852
        assert ind.fams_xrefs == ["@F10@", "@F11@"]
        assert ind.alt_surnames == ["Papadopoulou"]
        assert ind.surname_phonetic == "P131"
        assert ind.birth_decade == "1850s"

    def test_list_fields_independent(self) -> None:
        a = CompareIndividual(xref="@I1@", source_file="A")
        b = CompareIndividual(xref="@I2@", source_file="B")
        a.fams_xrefs.append("@F1@")
        a.alt_surnames.append("Doe")
        a.alt_given_names.append("Johnny")
        a.alt_surnames_normalized.append("doe")
        a.alt_given_names_normalized.append("johnny")
        assert b.fams_xrefs == []
        assert b.alt_surnames == []
        assert b.alt_given_names == []
        assert b.alt_surnames_normalized == []
        assert b.alt_given_names_normalized == []


class TestMatchScore:

    def test_defaults(self) -> None:
        score = MatchScore(
            total=0.85, field_scores={"surname": 1.0}, classification="probable"
        )
        assert score.total == 0.85
        assert score.field_scores == {"surname": 1.0}
        assert score.classification == "probable"
        assert score.insufficient_data is False
        assert score.name_only is False
        assert score.comparable_field_count == 0

    def test_classification_stored(self) -> None:
        for label in ("certain", "probable", "non_match"):
            score = MatchScore(total=0.5, field_scores={}, classification=label)
            assert score.classification == label


class TestFieldDiff:

    def test_construction(self) -> None:
        diff = FieldDiff(field="Birth Year", value_a="1852", value_b="1853")
        assert diff.field == "Birth Year"
        assert diff.value_a == "1852"
        assert diff.value_b == "1853"


class TestMatchPair:

    def test_construction(self) -> None:
        ind_a = CompareIndividual(xref="@I1@", source_file="A", full_name="John Smith")
        ind_b = CompareIndividual(xref="@I5@", source_file="B", full_name="John Smyth")
        score = MatchScore(
            total=0.78,
            field_scores={"surname": 0.8, "given_name": 1.0},
            classification="probable",
            comparable_field_count=2,
        )
        diffs = [FieldDiff(field="Surname", value_a="Smith", value_b="Smyth")]
        pair = MatchPair(
            individual_a=ind_a,
            individual_b=ind_b,
            score=score,
            field_diffs=diffs,
        )
        assert pair.individual_a.xref == "@I1@"
        assert pair.individual_b.full_name == "John Smyth"
        assert pair.score.total == 0.78
        assert len(pair.field_diffs) == 1
        assert pair.field_diffs[0].field == "Surname"


class TestCompareResult:

    def test_construction(self) -> None:
        enc_a = EncodingInfo(encoding="UTF-8", has_bom=False)
        enc_b = EncodingInfo(encoding="ANSEL", declared_charset="ANSEL")
        ind_a = CompareIndividual(xref="@I1@", source_file="A")
        ind_b = CompareIndividual(xref="@I2@", source_file="B")
        score = MatchScore(
            total=0.95,
            field_scores={"surname": 1.0, "birth_year": 1.0},
            classification="certain",
            comparable_field_count=2,
        )
        pair = MatchPair(
            individual_a=ind_a,
            individual_b=ind_b,
            score=score,
            field_diffs=[],
        )
        result = CompareResult(
            file_a="tree_a.ged",
            file_b="tree_b.ged",
            encoding_a=enc_a,
            encoding_b=enc_b,
            total_a=150,
            total_b=200,
            certain_matches=[pair],
            probable_matches=[],
            unique_to_a=[CompareIndividual(xref="@I99@", source_file="A")],
            unique_to_b=[],
        )
        assert result.file_a == "tree_a.ged"
        assert result.encoding_b.encoding == "ANSEL"
        assert result.total_a == 150
        assert result.total_b == 200
        assert len(result.certain_matches) == 1
        assert result.probable_matches == []
        assert len(result.unique_to_a) == 1
        assert result.unique_to_b == []
