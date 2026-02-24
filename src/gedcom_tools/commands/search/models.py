from __future__ import annotations

from dataclasses import dataclass, field

from gedcom_tools.utils import EncodingInfo


@dataclass
class SearchTerm:
    field: str  # "name", "surname", "born", "place", "ancestor", etc.
    operator: str  # ":", "=", "~"
    value: str  # raw query value
    is_wildcard: bool  # auto-detected * or ? (always False when regex_mode)
    date_range: tuple[int, int] | None  # parsed from "1800-1850" (inclusive)


@dataclass
class SearchQuery:
    terms: list[SearchTerm]
    regex_mode: bool
    fuzzy_dates: int | None  # ±N years, or None
    limit: int | None
    count_only: bool


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
    # Pre-computed Soundex codes
    surname_soundex: str = ""
    given_name_soundex: str = ""
    alt_soundex: list[tuple[str, str]] = field(default_factory=list)


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
