from __future__ import annotations

from dataclasses import dataclass, field

from gedcom_tools.utils import EncodingInfo


@dataclass
class CompareIndividual:
    """Parsed individual record ready for comparison."""

    xref: str
    source_file: str  # "A" or "B" for origin tracking

    # Display values (NFC-normalized, original casing)
    given_name: str = ""
    surname: str = ""
    full_name: str = ""  # "Given Surname" for display
    sex: str = ""  # M/F/""
    birth_year: int | None = None
    birth_place: str = ""
    death_year: int | None = None
    death_place: str = ""
    famc_xref: str | None = None
    fams_xrefs: list[str] = field(default_factory=list)

    # Alternate names (multi-NAME records)
    alt_surnames: list[str] = field(default_factory=list)
    alt_given_names: list[str] = field(default_factory=list)

    # Normalized values (for comparison — NFC → strip diacritics → lowercase)
    given_name_normalized: str = ""
    surname_normalized: str = ""
    birth_place_normalized: str = ""
    death_place_normalized: str = ""
    alt_surnames_normalized: list[str] = field(default_factory=list)
    alt_given_names_normalized: list[str] = field(default_factory=list)

    # Precomputed blocking keys
    surname_soundex: str = ""
    given_name_soundex: str = ""
    birth_decade: str = ""  # e.g. "1850s"
    death_decade: str = ""  # e.g. "1920s"


@dataclass
class MatchScore:
    """Weighted similarity score between two individuals."""

    total: float  # 0.0-1.0
    field_scores: dict[str, float]  # per-field breakdown
    classification: str  # "certain", "probable", "non_match"
    insufficient_data: bool = False
    """Set when fewer than 3 comparable fields exist or when no corroborating
    fields (dates, places) were compared.  Can coexist with probable
    classification -- signals a match backed by thin evidence."""
    name_only: bool = False  # True if no corroborating fields compared
    comparable_field_count: int = 0
    sex_penalty: bool = False


@dataclass
class FieldDiff:
    """Single field difference between two matched individuals."""

    field: str  # Human-readable: "Given Name", "Birth Year", etc.
    value_a: str  # value in file A (display form — always str, never None)
    value_b: str  # value in file B (display form — "?" for missing int fields)


@dataclass
class MatchPair:
    """A pair of individuals from files A and B with their match score."""

    individual_a: CompareIndividual
    individual_b: CompareIndividual
    score: MatchScore
    field_diffs: list[FieldDiff]


@dataclass
class CompareResult:
    """Full comparison output between two GEDCOM files."""

    file_a: str
    file_b: str
    encoding_a: EncodingInfo
    encoding_b: EncodingInfo
    total_a: int
    total_b: int
    certain_matches: list[MatchPair]
    probable_matches: list[MatchPair]
    unique_to_a: list[CompareIndividual]
    unique_to_b: list[CompareIndividual]
