from __future__ import annotations

import re

from gedcom_tools.commands.search.models import (
    MatchDetail,
    SearchIndividual,
    SearchMatch,
    SearchQuery,
    SearchTerm,
)
from gedcom_tools.phonetics import soundex
from gedcom_tools.utils import normalize_compare

_RELATIONSHIP_FIELDS = frozenset({"ancestor", "descendant"})

_pattern_cache: dict[str, re.Pattern[str]] = {}


def _wildcard_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate wildcard pattern to anchored regex.

    Splits on * and ?, re.escape() each literal segment,
    rejoins with .* and . respectively. Anchored at both ends.
    """
    key = f"wc:{pattern}"
    cached = _pattern_cache.get(key)
    if cached is not None:
        return cached
    star_parts = pattern.split("*")
    escaped: list[str] = []
    for part in star_parts:
        q_parts = part.split("?")
        escaped.append(".".join(re.escape(seg) for seg in q_parts))
    compiled = re.compile("^" + ".*".join(escaped) + "$", re.IGNORECASE)
    _pattern_cache[key] = compiled
    return compiled


def _compile_regex(pattern: str) -> re.Pattern[str]:
    cached = _pattern_cache.get(pattern)
    if cached is not None:
        return cached
    compiled = re.compile(pattern, re.IGNORECASE)
    _pattern_cache[pattern] = compiled
    return compiled


def _get_match_type(term: SearchTerm, query: SearchQuery) -> str:
    if term.date_range is not None:
        return "range"
    if term.operator == "=":
        return "exactly"
    if term.operator == "~":
        return "sounds_like"
    if term.is_wildcard:
        return "pattern"
    if query.regex_mode and term.operator == ":":
        return "regex"
    return "contains"


def _text_match(
    value_norm: str, query_norm: str, term: SearchTerm, query: SearchQuery
) -> bool:
    if term.operator == "=":
        return value_norm == query_norm
    if term.is_wildcard:
        return bool(_wildcard_to_regex(query_norm).search(value_norm))
    if query.regex_mode:
        return bool(_compile_regex(term.value).search(value_norm))
    return query_norm in value_norm


def _soundex_match(value_sx: str, query_sx: str) -> bool:
    return bool(value_sx and query_sx and value_sx == query_sx)


def _date_match(
    year: int | None,
    term: SearchTerm,
    approximate: bool,
    fuzzy_dates: int | None,
) -> bool:
    if year is None or term.date_range is None:
        return False
    start, end = term.date_range
    if approximate and fuzzy_dates is not None:
        return (start - fuzzy_dates) <= year <= (end + fuzzy_dates)
    return start <= year <= end


# --- Name field matching ---


def _match_name_text(
    ind: SearchIndividual, query_norm: str, term: SearchTerm, query: SearchQuery
) -> str | None:
    if _text_match(ind.full_name_norm, query_norm, term, query):
        return ind.full_name
    if _text_match(ind.given_name_norm, query_norm, term, query):
        return ind.given_name
    if _text_match(ind.surname_norm, query_norm, term, query):
        return ind.surname
    for i, (g_norm, s_norm) in enumerate(ind.alt_names_norm):
        alt_full = f"{g_norm} {s_norm}".strip()
        if _text_match(alt_full, query_norm, term, query):
            g, s = ind.alt_names[i]
            return f"{g} {s}".strip()
        if _text_match(g_norm, query_norm, term, query):
            return ind.alt_names[i][0]
        if _text_match(s_norm, query_norm, term, query):
            return ind.alt_names[i][1]
    return None


def _match_name_soundex(ind: SearchIndividual, query_sx: str) -> str | None:
    if _soundex_match(ind.surname_soundex, query_sx):
        return ind.surname
    if _soundex_match(ind.given_name_soundex, query_sx):
        return ind.given_name
    for i, (g_sx, s_sx) in enumerate(ind.alt_soundex):
        if _soundex_match(s_sx, query_sx):
            return ind.alt_names[i][1]
        if _soundex_match(g_sx, query_sx):
            return ind.alt_names[i][0]
    return None


# --- Given/Surname field matching ---


def _match_given_text(
    ind: SearchIndividual, query_norm: str, term: SearchTerm, query: SearchQuery
) -> str | None:
    if _text_match(ind.given_name_norm, query_norm, term, query):
        return ind.given_name
    for i, (g_norm, _) in enumerate(ind.alt_names_norm):
        if _text_match(g_norm, query_norm, term, query):
            return ind.alt_names[i][0]
    return None


def _match_given_soundex(ind: SearchIndividual, query_sx: str) -> str | None:
    if _soundex_match(ind.given_name_soundex, query_sx):
        return ind.given_name
    for i, (g_sx, _) in enumerate(ind.alt_soundex):
        if _soundex_match(g_sx, query_sx):
            return ind.alt_names[i][0]
    return None


def _match_surname_text(
    ind: SearchIndividual, query_norm: str, term: SearchTerm, query: SearchQuery
) -> str | None:
    if _text_match(ind.surname_norm, query_norm, term, query):
        return ind.surname
    for i, (_, s_norm) in enumerate(ind.alt_names_norm):
        if _text_match(s_norm, query_norm, term, query):
            return ind.alt_names[i][1]
    return None


def _match_surname_soundex(ind: SearchIndividual, query_sx: str) -> str | None:
    if _soundex_match(ind.surname_soundex, query_sx):
        return ind.surname
    for i, (_, s_sx) in enumerate(ind.alt_soundex):
        if _soundex_match(s_sx, query_sx):
            return ind.alt_names[i][1]
    return None


# --- Place field matching ---


def _match_place_text(
    ind: SearchIndividual, query_norm: str, term: SearchTerm, query: SearchQuery
) -> str | None:
    if ind.birth_place_norm and _text_match(
        ind.birth_place_norm, query_norm, term, query
    ):
        return ind.birth_place
    if ind.death_place_norm and _text_match(
        ind.death_place_norm, query_norm, term, query
    ):
        return ind.death_place
    return None


# --- Term matching dispatch ---


def _match_term(
    ind: SearchIndividual, term: SearchTerm, query: SearchQuery
) -> MatchDetail | None:
    field = term.field
    query_norm = normalize_compare(term.value)
    match_type = _get_match_type(term, query)

    # Date fields
    if field == "born":
        if _date_match(
            ind.birth_year, term, ind.birth_year_approximate, query.fuzzy_dates
        ):
            return MatchDetail("born", str(ind.birth_year), term.value, "range")
        return None

    if field == "died":
        if _date_match(
            ind.death_year, term, ind.death_year_approximate, query.fuzzy_dates
        ):
            return MatchDetail("died", str(ind.death_year), term.value, "range")
        return None

    # Sex field
    if field == "sex":
        sex_norm = ind.sex.lower()
        if _text_match(sex_norm, query_norm, term, query):
            return MatchDetail("sex", ind.sex, term.value, match_type)
        return None

    # Soundex matching (name fields only — validated by query parser)
    if term.operator == "~":
        query_sx = soundex(query_norm)
        matched: str | None = None
        if field == "name":
            matched = _match_name_soundex(ind, query_sx)
        elif field == "given":
            matched = _match_given_soundex(ind, query_sx)
        elif field == "surname":
            matched = _match_surname_soundex(ind, query_sx)
        if matched is not None:
            return MatchDetail(field, matched, term.value, "sounds_like")
        return None

    # Text matching (substring/exact/wildcard/regex)
    matched = None
    if field == "name":
        matched = _match_name_text(ind, query_norm, term, query)
    elif field == "given":
        matched = _match_given_text(ind, query_norm, term, query)
    elif field == "surname":
        matched = _match_surname_text(ind, query_norm, term, query)
    elif field == "place":
        matched = _match_place_text(ind, query_norm, term, query)

    if matched is not None:
        return MatchDetail(field, matched, term.value, match_type)
    return None


def match_individual(
    individual: SearchIndividual,
    query: SearchQuery,
    relationship_xrefs: set[str] | None = None,
) -> SearchMatch | None:
    """Match an individual against all query terms (AND logic).

    relationship_xrefs: pre-computed set from ancestor/descendant BFS.
    If provided, individual must be in the set to match.
    """
    if relationship_xrefs is not None and individual.xref not in relationship_xrefs:
        return None

    details: list[MatchDetail] = []

    for term in query.terms:
        if term.field in _RELATIONSHIP_FIELDS:
            continue

        detail = _match_term(individual, term, query)
        if detail is None:
            return None
        details.append(detail)

    # No non-relationship terms matched and no relationship constraint
    if not details and relationship_xrefs is None:
        return None

    return SearchMatch(individual=individual, details=details)
