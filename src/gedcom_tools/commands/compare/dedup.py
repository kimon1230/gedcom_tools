from __future__ import annotations

from gedcom_tools.commands.compare.models import (
    CompareIndividual,
    FieldDiff,
    MatchPair,
    MatchScore,
)

_DIFF_FIELDS: list[tuple[str, str, bool]] = [
    ("Given Name", "given_name", False),
    ("Surname", "surname", False),
    ("Birth Year", "birth_year", True),
    ("Death Year", "death_year", True),
    ("Birth Place", "birth_place", False),
    ("Death Place", "death_place", False),
    ("Sex", "sex", False),
]


def _compute_field_diffs(a: CompareIndividual, b: CompareIndividual) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for label, attr, is_int in _DIFF_FIELDS:
        val_a = getattr(a, attr)
        val_b = getattr(b, attr)
        str_a = (
            str(val_a) if (is_int and val_a is not None) else ("?" if is_int else val_a)
        )
        str_b = (
            str(val_b) if (is_int and val_b is not None) else ("?" if is_int else val_b)
        )
        if str_a != str_b:
            diffs.append(FieldDiff(field=label, value_a=str_a, value_b=str_b))
    return diffs


def deduplicate_matches(
    scored_pairs: list[tuple[CompareIndividual, CompareIndividual, MatchScore]],
) -> tuple[list[MatchPair], list[MatchPair]]:
    """Greedy one-to-one deduplication. Returns (certain_matches, probable_matches)."""
    used_a: set[str] = set()
    used_b: set[str] = set()
    certain: list[MatchPair] = []
    probable: list[MatchPair] = []

    for a, b, score in sorted(scored_pairs, key=lambda t: t[2].total, reverse=True):
        if score.classification == "non_match":
            continue
        if a.xref in used_a or b.xref in used_b:
            continue
        used_a.add(a.xref)
        used_b.add(b.xref)
        diffs = _compute_field_diffs(a, b)
        pair = MatchPair(individual_a=a, individual_b=b, score=score, field_diffs=diffs)
        if score.classification == "certain":
            certain.append(pair)
        else:
            probable.append(pair)

    return certain, probable
