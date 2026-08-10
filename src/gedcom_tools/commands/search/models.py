from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from gedcom_tools.utils import EncodingInfo, normalize_compare


@dataclass
class SearchTerm:
    field: str  # "name", "surname", "born", "place", "ancestor", etc.
    operator: str  # ":", "=", "~"
    value: str  # raw query value
    is_wildcard: bool  # auto-detected * or ? (always False when regex_mode)
    date_range: tuple[int, int] | None  # parsed from "1800-1850" (inclusive)
    # (primary, secondary) codes for `value`, or ("", "") for every operator
    # other than "~". Populated by parse_query(), which owns the algorithm
    # choice -- there is deliberately no default, so a hand-built term cannot
    # quietly become an empty code that matches nothing.
    phonetic_codes: tuple[str, str]
    # normalize_compare(value). Query-invariant, so it is computed once here
    # instead of once per individual inside the match loop.
    # `dataclasses.field` is spelled out because the attribute above shadows
    # the bare name inside this class body.
    value_norm: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.value_norm = normalize_compare(self.value)


@dataclass
class SearchQuery:
    terms: list[SearchTerm]
    regex_mode: bool
    fuzzy_dates: int | None  # ±N years, or None
    limit: int | None
    count_only: bool
    phonetic_algo: str = "soundex"


@dataclass
class MatchDetail:
    field: str  # which field matched
    matched_value: str  # value in the GEDCOM record
    query_term: str  # what the user searched for
    match_type: str  # "contains", "exactly", "pattern", "sounds_like", "regex", "range"


@dataclass
class SearchIndividual:
    xref: str
    given_name: str
    surname: str
    full_name: str  # "Given Surname" (display form)
    sex: str  # raw uppercase: M, F, U, X, or ""
    birth_year: int | None
    birth_year_approximate: bool  # True if ABT/EST/CAL/BEF/AFT/BET
    birth_place: str
    death_year: int | None
    death_year_approximate: bool
    death_place: str
    alt_names: list[tuple[str, str]] = field(default_factory=list)  # [(given, surname)]
    # Normalized versions for matching
    given_name_norm: str = ""
    surname_norm: str = ""
    full_name_norm: str = ""
    birth_place_norm: str = ""
    death_place_norm: str = ""
    alt_names_norm: list[tuple[str, str]] = field(default_factory=list)
    # Pre-computed phonetic codes
    surname_phonetic: str = ""
    surname_phonetic_alt: str = ""
    given_phonetic: str = ""
    given_phonetic_alt: str = ""
    alt_phonetic: list[tuple[str, str]] = field(default_factory=list)
    alt_phonetic_alt: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SearchMatch:
    individual: SearchIndividual
    details: list[MatchDetail]


@dataclass
class SearchResult:
    file_path: str
    query_string: str
    encoding: EncodingInfo
    total_individuals: int
    matches: list[SearchMatch]
    truncated: bool  # True if --limit hit
