"""Data models for stats command."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndividualData:
    """Collected data about an individual for stats."""

    xref: str
    name: str = ""
    given_name: str = ""  # First/given name for given name frequency
    surname: str = ""  # Full SURN value (for lineages)
    surname_parts: list[str] = field(default_factory=list)  # Split parts (for surnames)
    sex: str = ""  # M, F, or empty
    birth_year: int | None = None
    death_year: int | None = None
    famc_xref: str | None = None  # Child of family
    fams_xrefs: list[str] = field(default_factory=list)  # Spouse in families
    has_note: bool = False
    has_media: bool = False
    has_source: bool = False  # Has any source citation

    # Demographics
    birth_month: int | None = None  # 1-12, for birth month distribution
    birth_date_precision: str = "missing"  # "full", "partial", "approximate", "missing"
    birth_date_has_full: bool = (
        False  # True if date has day/month/year (even if approx)
    )
    occupation: str = ""  # First occupation found
    source_count: int = 0  # Number of source citations (recursive)

    # Life events (populated after initial collection)
    first_marriage_year: int | None = None
    first_marriage_age: int | None = None
    first_marriage_fam_xref: str | None = None  # For age gap deduplication
    spouse_birth_year: int | None = None
    first_child_year: int | None = None
    first_child_age: int | None = None


@dataclass
class FamilyData:
    """Collected data about a family for stats."""

    xref: str
    husb_xref: str | None = None
    wife_xref: str | None = None
    chil_xrefs: list[str] = field(default_factory=list)
    marriage_year: int | None = None


@dataclass
class TimelineEntry:
    """Represents an individual for timeline display."""

    year: int
    xref: str
    name: str


@dataclass
class GenerationEntry:
    """Represents an individual for generation depth display."""

    generation: int
    xref: str
    name: str


@dataclass
class FamilyEntry:
    """Represents a family for largest families display."""

    xref: str
    parents: str
    children: int


@dataclass
class RankedItem:
    """A name/place with count and percentage."""

    name: str
    count: int
    percent: float


@dataclass
class AggregateStats:
    """Generic aggregate statistics for any numeric measurement."""

    average: float
    min_value: int | None = None
    max_value: int | None = None
    sample_size: int = 0
    distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "average": round(self.average, 1),
            "sample_size": self.sample_size,
        }
        if self.min_value is not None:
            result["min"] = self.min_value
        if self.max_value is not None:
            result["max"] = self.max_value
        if self.distribution:
            result["distribution"] = self.distribution
        return result


@dataclass
class GenderedAggregateStats:
    """Aggregate stats split by gender with optional century breakdown."""

    male: AggregateStats | None = None
    female: AggregateStats | None = None
    by_century: dict[str, dict[str, AggregateStats | None]] = field(
        default_factory=dict
    )
    # by_century: {"1800": {"male": AggregateStats | None, "female": ...}, ...}

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.male:
            result["male"] = self.male.to_dict()
        if self.female:
            result["female"] = self.female.to_dict()
        if self.by_century:
            result["by_century"] = {}
            for century, genders in self.by_century.items():
                result["by_century"][century] = {}
                for gender, stats in genders.items():
                    if stats is not None:  # Skip None values
                        result["by_century"][century][gender] = stats.to_dict()
        return result


@dataclass
class DatePrecisionStats:
    """Date precision breakdown with sub-classification for approximate dates."""

    full: int = 0  # day/month/year (e.g., "2 Oct 1822")
    partial: int = 0  # month/year or year only (e.g., "1850", "Oct 1850")
    approximate_full: int = 0  # ABT/BEF/etc. with day/month/year
    approximate_partial: int = 0  # ABT/BEF/etc. with year only
    missing: int = 0  # No date at all

    @property
    def total(self) -> int:
        return (
            self.full
            + self.partial
            + self.approximate_full
            + self.approximate_partial
            + self.missing
        )

    @property
    def approximate(self) -> int:
        """Total approximate dates (for backward compat display)."""
        return self.approximate_full + self.approximate_partial

    def to_dict(self) -> dict[str, Any]:
        return {
            "full": self.full,
            "partial": self.partial,
            "approximate": {
                "total": self.approximate,
                "with_full_date": self.approximate_full,
                "with_partial_date": self.approximate_partial,
            },
            "missing": self.missing,
            "total": self.total,
        }


@dataclass
class CoverageStats:
    """Coverage statistics with count/total."""

    with_count: int
    without_count: int
    percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "with": self.with_count,
            "without": self.without_count,
            "percent": round(self.percent, 1),
        }


@dataclass
class LifespanStats:
    """Lifespan statistics."""

    average: float
    min_value: int
    max_value: int
    sample_size: int  # Number of individuals with both birth and death

    def to_dict(self) -> dict[str, Any]:
        return {
            "average": round(self.average, 1),
            "min": self.min_value,
            "max": self.max_value,
            "sample_size": self.sample_size,
        }


@dataclass
class MarriageStats:
    """Marriage statistics."""

    total_marriages: int
    with_date: int
    without_date: int
    avg_children: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total_marriages,
            "with_date": self.with_date,
            "without_date": self.without_date,
            "avg_children": round(self.avg_children, 1),
        }
