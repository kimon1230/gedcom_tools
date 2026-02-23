from __future__ import annotations

from rapidfuzz.distance import JaroWinkler

from gedcom_tools.commands.compare.models import CompareIndividual, MatchScore

_WEIGHTS: dict[str, float] = {
    "Surname": 0.30,
    "Given Name": 0.20,
    "Birth Year": 0.20,
    "Death Year": 0.10,
    "Birth Place": 0.10,
    "Death Place": 0.05,
    "Sex": 0.05,
}

_CORROBORATING_FIELDS: set[str] = {
    "Birth Year",
    "Death Year",
    "Birth Place",
    "Death Place",
}

_YEAR_BANDS: list[tuple[int, float]] = [
    (0, 1.0),
    (1, 0.85),
    (2, 0.70),
    (3, 0.50),
    (5, 0.25),
    (7, 0.10),
    (10, 0.05),
]


def _year_proximity(year_a: int, year_b: int) -> float:
    diff = abs(year_a - year_b)
    for threshold, score in _YEAR_BANDS:
        if diff <= threshold:
            return score
    return 0.0


def _best_name_jw(
    primary_a: str,
    alts_a: list[str],
    primary_b: str,
    alts_b: list[str],
) -> float:
    candidates_a = [s for s in [primary_a] + alts_a if s]
    candidates_b = [s for s in [primary_b] + alts_b if s]
    if not candidates_a or not candidates_b:
        return 0.0
    best = 0.0
    for ca in candidates_a:
        for cb in candidates_b:
            sim = JaroWinkler.similarity(ca, cb)
            if sim > best:
                best = sim
    return best


def _place_similarity(place_a: str, place_b: str) -> float:
    parts_a = [p.strip() for p in place_a.split(",") if p.strip()]
    parts_b = [p.strip() for p in place_b.split(",") if p.strip()]
    if not parts_a or not parts_b:
        return 0.0

    if len(parts_a) <= len(parts_b):
        shorter, longer = parts_a, list(parts_b)
    else:
        shorter, longer = parts_b, list(parts_a)

    total = 0.0
    for comp in shorter:
        best_score = 0.0
        best_idx = 0
        for i, candidate in enumerate(longer):
            sim = JaroWinkler.similarity(comp, candidate)
            if sim > best_score:
                best_score = sim
                best_idx = i
        total += best_score
        longer.pop(best_idx)

    return total / len(shorter)


def score_pair(
    a: CompareIndividual,
    b: CompareIndividual,
    certain_threshold: float = 0.85,
    probable_threshold: float = 0.65,
    reject_sex_mismatch: bool = False,
) -> MatchScore:
    """Score a candidate pair and classify the match."""
    field_scores: dict[str, float] = {}
    applicable_weights: dict[str, float] = {}
    sex_penalty = False

    # Surname
    candidates_a = [s for s in [a.surname_normalized] + a.alt_surnames_normalized if s]
    candidates_b = [s for s in [b.surname_normalized] + b.alt_surnames_normalized if s]
    if candidates_a and candidates_b:
        jw = _best_name_jw(
            a.surname_normalized,
            a.alt_surnames_normalized,
            b.surname_normalized,
            b.alt_surnames_normalized,
        )
        if (
            a.surname_soundex
            and b.surname_soundex
            and a.surname_soundex == b.surname_soundex
            and 0.50 <= jw <= 0.85
        ):
            jw = min(jw + 0.05, 1.0)
        field_scores["Surname"] = jw
        applicable_weights["Surname"] = _WEIGHTS["Surname"]

    # Given Name
    candidates_a = [
        s for s in [a.given_name_normalized] + a.alt_given_names_normalized if s
    ]
    candidates_b = [
        s for s in [b.given_name_normalized] + b.alt_given_names_normalized if s
    ]
    if candidates_a and candidates_b:
        field_scores["Given Name"] = _best_name_jw(
            a.given_name_normalized,
            a.alt_given_names_normalized,
            b.given_name_normalized,
            b.alt_given_names_normalized,
        )
        applicable_weights["Given Name"] = _WEIGHTS["Given Name"]

    # Birth Year
    if a.birth_year is not None and b.birth_year is not None:
        field_scores["Birth Year"] = _year_proximity(a.birth_year, b.birth_year)
        applicable_weights["Birth Year"] = _WEIGHTS["Birth Year"]

    # Death Year
    if a.death_year is not None and b.death_year is not None:
        field_scores["Death Year"] = _year_proximity(a.death_year, b.death_year)
        applicable_weights["Death Year"] = _WEIGHTS["Death Year"]

    # Birth Place
    if a.birth_place_normalized and b.birth_place_normalized:
        field_scores["Birth Place"] = _place_similarity(
            a.birth_place_normalized, b.birth_place_normalized
        )
        applicable_weights["Birth Place"] = _WEIGHTS["Birth Place"]

    # Death Place
    if a.death_place_normalized and b.death_place_normalized:
        field_scores["Death Place"] = _place_similarity(
            a.death_place_normalized, b.death_place_normalized
        )
        applicable_weights["Death Place"] = _WEIGHTS["Death Place"]

    # Sex
    if a.sex and b.sex:
        if a.sex == b.sex:
            field_scores["Sex"] = 1.0
            applicable_weights["Sex"] = _WEIGHTS["Sex"]
        else:
            if reject_sex_mismatch:
                return MatchScore(
                    total=0.0,
                    field_scores={},
                    classification="non_match",
                    comparable_field_count=0,
                )
            sex_penalty = True

    # Counts
    comparable_count = len(field_scores)
    corroborating_count = sum(1 for f in field_scores if f in _CORROBORATING_FIELDS)
    name_only = corroborating_count == 0 and comparable_count > 0
    # Insufficient when we lack either breadth (<3 fields) or depth (no
    # corroborating date/place fields).  Can coexist with "probable" --
    # e.g. name+sex match with high JW but no dates or places.
    # Consumers should treat insufficient_data + probable as low-confidence.
    insufficient = comparable_count < 3 or corroborating_count == 0

    # Weighted average
    if not applicable_weights:
        total = 0.0
    else:
        weight_sum = sum(applicable_weights.values())
        total = (
            sum(field_scores[f] * applicable_weights[f] for f in field_scores)
            / weight_sum
        )

    # Sex penalty
    if sex_penalty:
        total *= 0.7

    # Classification
    if comparable_count < 3:
        classification = "non_match"
    elif name_only:
        classification = "probable" if total >= probable_threshold else "non_match"
    elif comparable_count < 4:
        classification = "probable" if total >= probable_threshold else "non_match"
    else:
        if total >= certain_threshold:
            classification = "certain"
        elif total >= probable_threshold:
            classification = "probable"
        else:
            classification = "non_match"

    return MatchScore(
        total=round(total, 4),
        field_scores={k: round(v, 4) for k, v in field_scores.items()},
        classification=classification,
        insufficient_data=insufficient,
        name_only=name_only,
        comparable_field_count=comparable_count,
        sex_penalty=sex_penalty,
    )
