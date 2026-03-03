"""Data models for the export command."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass
class ExportIndividual:
    xref: str
    given_name: str = ""
    surname: str = ""
    suffix: str = ""
    sex: str = ""
    birth_date: str = ""
    birth_year: int | None = None
    birth_place: str = ""
    death_date: str = ""
    death_year: int | None = None
    death_place: str = ""
    burial_date: str = ""
    burial_place: str = ""
    occupations: list[str] = field(default_factory=list)
    source_count: int = 0
    famc_xref: str = ""
    fams_xrefs: list[str] = field(default_factory=list)
    # JSON-only fields (richer than CSV)
    alt_names: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ExportFamily:
    xref: str
    husband_xref: str = ""
    husband_name: str = ""
    wife_xref: str = ""
    wife_name: str = ""
    marriage_date: str = ""
    marriage_year: int | None = None
    marriage_place: str = ""
    child_count: int = 0
    children_xrefs: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    file_path: str
    encoding: str
    individual_count: int
    family_count: int
    individuals: list[ExportIndividual]
    families: list[ExportFamily]


def estimate_living(
    birth_year: int | None,
    death_year: int | None,
    burial_date: str,
    max_age: int = 110,
    current_year: int | None = None,
) -> bool:
    """Estimate whether an individual is living.

    max_age is inclusive — a person born exactly max_age years ago is
    still considered possibly living. current_year defaults to today's year.
    """
    current_year = current_year or datetime.date.today().year

    if death_year is not None:
        return False

    if burial_date:
        return False

    if birth_year is None:
        return False

    if current_year - birth_year > max_age:
        return False

    return True
