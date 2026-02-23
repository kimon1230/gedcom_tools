from __future__ import annotations

from gedcom_tools.commands.compare.dedup import deduplicate_matches
from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    MatchScore,
)


def _ind(
    xref: str,
    source: str = "A",
    given_name: str = "",
    surname: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    birth_place: str = "",
    death_place: str = "",
    sex: str = "",
    **kwargs: object,
) -> CompareIndividual:
    return CompareIndividual(
        xref=xref,
        source_file=source,
        given_name=given_name,
        surname=surname,
        birth_year=birth_year,
        death_year=death_year,
        birth_place=birth_place,
        death_place=death_place,
        sex=sex,
        **kwargs,
    )


def _score(
    total: float,
    classification: str,
    field_scores: dict[str, float] | None = None,
    insufficient_data: bool = False,
    name_only: bool = False,
    comparable_field_count: int = 4,
) -> MatchScore:
    return MatchScore(
        total=total,
        field_scores=field_scores or {},
        classification=classification,
        insufficient_data=insufficient_data,
        name_only=name_only,
        comparable_field_count=comparable_field_count,
    )


class TestGreedyAssignment:
    def test_single_certain_pair(self):
        a = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b = _ind("@I2@", source="B", given_name="John", surname="Smith")
        pairs = [(a, b, _score(0.95, "certain"))]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 1
        assert len(probable) == 0
        assert certain[0].individual_a.xref == "@I1@"
        assert certain[0].individual_b.xref == "@I2@"

    def test_single_probable_pair(self):
        a = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b = _ind("@I2@", source="B", given_name="Jon", surname="Smith")
        pairs = [(a, b, _score(0.70, "probable"))]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 0
        assert len(probable) == 1
        assert probable[0].individual_a.xref == "@I1@"

    def test_best_score_wins(self):
        a1 = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b2 = _ind("@I2@", source="B", given_name="John", surname="Smith")
        b3 = _ind("@I3@", source="B", given_name="Jon", surname="Smith")
        pairs = [
            (a1, b2, _score(0.90, "certain")),
            (a1, b3, _score(0.70, "probable")),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 1
        assert certain[0].individual_b.xref == "@I2@"
        assert len(probable) == 0
        # @I3@ unmatched — not in any output
        all_b_xrefs = [p.individual_b.xref for p in certain + probable]
        assert "@I3@" not in all_b_xrefs

    def test_one_to_many_resolution(self):
        a1 = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b2 = _ind("@I2@", source="B", given_name="John", surname="Smith")
        b3 = _ind("@I3@", source="B", given_name="John", surname="Smyth")
        pairs = [
            (a1, b2, _score(0.95, "certain")),
            (a1, b3, _score(0.88, "certain")),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 1
        assert certain[0].individual_b.xref == "@I2@"
        all_b_xrefs = [p.individual_b.xref for p in certain + probable]
        assert "@I3@" not in all_b_xrefs

    def test_many_to_one_resolution(self):
        a1 = _ind("@I1@", source="A", given_name="John", surname="Smith")
        a3 = _ind("@I3@", source="A", given_name="Johan", surname="Smith")
        b2 = _ind("@I2@", source="B", given_name="John", surname="Smith")
        pairs = [
            (a1, b2, _score(0.92, "certain")),
            (a3, b2, _score(0.85, "certain")),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 1
        assert certain[0].individual_a.xref == "@I1@"
        assert certain[0].individual_b.xref == "@I2@"
        all_a_xrefs = [p.individual_a.xref for p in certain + probable]
        assert "@I3@" not in all_a_xrefs


class TestNonMatchFiltering:
    def test_non_matches_excluded(self):
        a = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b = _ind("@I2@", source="B", given_name="Maria", surname="Garcia")
        pairs = [(a, b, _score(0.40, "non_match"))]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 0
        assert len(probable) == 0

    def test_non_match_doesnt_block(self):
        a1 = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b2 = _ind("@I2@", source="B", given_name="Maria", surname="Garcia")
        b3 = _ind("@I3@", source="B", given_name="Jon", surname="Smith")
        pairs = [
            (a1, b2, _score(0.40, "non_match")),
            (a1, b3, _score(0.70, "probable")),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(probable) == 1
        assert probable[0].individual_a.xref == "@I1@"
        assert probable[0].individual_b.xref == "@I3@"

    def test_all_non_matches(self):
        pairs = [
            (
                _ind("@I1@", source="A"),
                _ind("@I2@", source="B"),
                _score(0.30, "non_match"),
            ),
            (
                _ind("@I3@", source="A"),
                _ind("@I4@", source="B"),
                _score(0.25, "non_match"),
            ),
            (
                _ind("@I5@", source="A"),
                _ind("@I6@", source="B"),
                _score(0.10, "non_match"),
            ),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 0
        assert len(probable) == 0


class TestFieldDiffs:
    def test_identical_individuals_no_diffs(self):
        a = _ind(
            "@I1@",
            source="A",
            given_name="John",
            surname="Smith",
            birth_year=1850,
            death_year=1920,
            birth_place="London",
            death_place="Paris",
            sex="M",
        )
        b = _ind(
            "@I2@",
            source="B",
            given_name="John",
            surname="Smith",
            birth_year=1850,
            death_year=1920,
            birth_place="London",
            death_place="Paris",
            sex="M",
        )
        pairs = [(a, b, _score(0.98, "certain"))]

        certain, _ = deduplicate_matches(pairs)

        assert certain[0].field_diffs == []

    def test_name_difference(self):
        a = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b = _ind("@I2@", source="B", given_name="Jon", surname="Smith")
        pairs = [(a, b, _score(0.80, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        name_diff = [d for d in diffs if d.field == "Given Name"]
        assert len(name_diff) == 1
        assert name_diff[0].value_a == "John"
        assert name_diff[0].value_b == "Jon"

    def test_year_difference(self):
        a = _ind("@I1@", source="A", birth_year=1850)
        b = _ind("@I2@", source="B", birth_year=1852)
        pairs = [(a, b, _score(0.75, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        year_diff = [d for d in diffs if d.field == "Birth Year"]
        assert len(year_diff) == 1
        assert year_diff[0].value_a == "1850"
        assert year_diff[0].value_b == "1852"

    def test_missing_year_shows_question_mark(self):
        a = _ind("@I1@", source="A", birth_year=1850)
        b = _ind("@I2@", source="B", birth_year=None)
        pairs = [(a, b, _score(0.65, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        year_diff = [d for d in diffs if d.field == "Birth Year"]
        assert len(year_diff) == 1
        assert year_diff[0].value_a == "1850"
        assert year_diff[0].value_b == "?"

    def test_both_years_missing_no_diff(self):
        a = _ind("@I1@", source="A", birth_year=None)
        b = _ind("@I2@", source="B", birth_year=None)
        pairs = [(a, b, _score(0.60, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        year_fields = [d.field for d in diffs]
        assert "Birth Year" not in year_fields

    def test_place_difference(self):
        a = _ind("@I1@", source="A", birth_place="London")
        b = _ind("@I2@", source="B", birth_place="London, England")
        pairs = [(a, b, _score(0.72, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        place_diff = [d for d in diffs if d.field == "Birth Place"]
        assert len(place_diff) == 1
        assert place_diff[0].value_a == "London"
        assert place_diff[0].value_b == "London, England"

    def test_sex_difference(self):
        a = _ind("@I1@", source="A", sex="M")
        b = _ind("@I2@", source="B", sex="F")
        pairs = [(a, b, _score(0.60, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        sex_diff = [d for d in diffs if d.field == "Sex"]
        assert len(sex_diff) == 1
        assert sex_diff[0].value_a == "M"
        assert sex_diff[0].value_b == "F"

    def test_multiple_diffs(self):
        a = _ind(
            "@I1@",
            source="A",
            given_name="John",
            surname="Smith",
            birth_year=1850,
            death_year=1920,
            birth_place="London",
            death_place="Paris",
            sex="M",
        )
        b = _ind(
            "@I2@",
            source="B",
            given_name="Jon",
            surname="Smyth",
            birth_year=1852,
            death_year=1921,
            birth_place="Bristol",
            death_place="Lyon",
            sex="F",
        )
        pairs = [(a, b, _score(0.65, "probable"))]

        _, probable = deduplicate_matches(pairs)

        diffs = probable[0].field_diffs
        diff_fields = [d.field for d in diffs]
        assert diff_fields == [
            "Given Name",
            "Surname",
            "Birth Year",
            "Death Year",
            "Birth Place",
            "Death Place",
            "Sex",
        ]


class TestCertainProbableSplitting:
    def test_mixed_classifications(self):
        pairs = [
            (
                _ind("@I1@", source="A", given_name="John", surname="Smith"),
                _ind("@I2@", source="B", given_name="John", surname="Smith"),
                _score(0.95, "certain"),
            ),
            (
                _ind("@I3@", source="A", given_name="Jane", surname="Doe"),
                _ind("@I4@", source="B", given_name="Jane", surname="Doe"),
                _score(0.72, "probable"),
            ),
            (
                _ind("@I5@", source="A", given_name="Bob", surname="Brown"),
                _ind("@I6@", source="B", given_name="Alice", surname="Green"),
                _score(0.40, "non_match"),
            ),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 1
        assert len(probable) == 1
        assert certain[0].individual_a.xref == "@I1@"
        assert probable[0].individual_a.xref == "@I3@"

    def test_all_certain(self):
        pairs = [
            (
                _ind("@I1@", source="A", given_name="John", surname="Smith"),
                _ind("@I2@", source="B", given_name="John", surname="Smith"),
                _score(0.95, "certain"),
            ),
            (
                _ind("@I3@", source="A", given_name="Jane", surname="Doe"),
                _ind("@I4@", source="B", given_name="Jane", surname="Doe"),
                _score(0.92, "certain"),
            ),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 2
        assert len(probable) == 0

    def test_all_probable(self):
        pairs = [
            (
                _ind("@I1@", source="A", given_name="John", surname="Smith"),
                _ind("@I2@", source="B", given_name="Jon", surname="Smith"),
                _score(0.72, "probable"),
            ),
            (
                _ind("@I3@", source="A", given_name="Jane", surname="Doe"),
                _ind("@I4@", source="B", given_name="Janet", surname="Doe"),
                _score(0.68, "probable"),
            ),
        ]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 0
        assert len(probable) == 2


class TestEdgeCases:
    def test_empty_input(self):
        certain, probable = deduplicate_matches([])

        assert certain == []
        assert probable == []

    def test_single_pair(self):
        a = _ind("@I1@", source="A", given_name="John", surname="Smith")
        b = _ind("@I2@", source="B", given_name="John", surname="Smith")
        pairs = [(a, b, _score(0.80, "probable"))]

        certain, probable = deduplicate_matches(pairs)

        assert len(certain) == 0
        assert len(probable) == 1
        assert probable[0].individual_a.xref == "@I1@"

    def test_score_ordering(self):
        pairs = [
            (
                _ind("@I1@", source="A", given_name="Alice"),
                _ind("@I2@", source="B", given_name="Alice"),
                _score(0.70, "probable"),
            ),
            (
                _ind("@I3@", source="A", given_name="Bob"),
                _ind("@I4@", source="B", given_name="Bob"),
                _score(0.95, "certain"),
            ),
            (
                _ind("@I5@", source="A", given_name="Carol"),
                _ind("@I6@", source="B", given_name="Carol"),
                _score(0.80, "probable"),
            ),
        ]

        certain, probable = deduplicate_matches(pairs)

        # All three are independent (no shared xrefs), so all accepted
        assert len(certain) == 1
        assert len(probable) == 2
        assert certain[0].individual_a.xref == "@I3@"

    def test_stable_sort_tiebreaker(self):
        a1 = _ind("@I1@", source="A", given_name="John", surname="Smith")
        a3 = _ind("@I3@", source="A", given_name="Jane", surname="Smith")
        b2 = _ind("@I2@", source="B", given_name="John", surname="Smith")
        b4 = _ind("@I4@", source="B", given_name="Jane", surname="Smith")
        pairs = [
            (a1, b2, _score(0.85, "certain")),
            (a3, b4, _score(0.85, "certain")),
        ]

        certain, probable = deduplicate_matches(pairs)

        # Both have same score; both are independent, so both accepted
        # First in input wins the earlier slot due to stable sort
        assert len(certain) == 2
        assert certain[0].individual_a.xref == "@I1@"
        assert certain[1].individual_a.xref == "@I3@"
