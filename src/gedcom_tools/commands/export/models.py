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
    living_marker: str = ""
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


# Custom GEDCOM tags used by genealogy software to mark living status.
# Living: Legacy Family Tree / Family Tree Maker (_LVG, _LVNG),
#         RootsMagic (_LIVING), PAF (_CONF_FLAG).
# Not living: Brother's Keeper (_NLIV).
_LIVING_TAGS = frozenset({"_LVG", "_LIVING", "_LVNG", "_CONF_FLAG"})
_NOT_LIVING_TAGS = frozenset({"_NLIV"})


def estimate_living(
    birth_year: int | None,
    death_year: int | None,
    burial_date: str,
    max_age: int = 110,
    current_year: int | None = None,
    living_marker: str = "",
) -> bool:
    """Estimate whether an individual is living.

    Priority order:
    1. Custom GEDCOM tags (_NLIV → not living; _LVG/_LIVING/_LVNG/_CONF_FLAG → living)
    2. Death year or burial date present → not living
    3. Birth/baptism/christening year within max_age and no death → living
    4. Everything else (no dates, ancient dates, unknown) → not living
    """
    current_year = current_year or datetime.date.today().year

    if living_marker in _NOT_LIVING_TAGS:
        return False
    if living_marker in _LIVING_TAGS:
        return True

    if death_year is not None:
        return False
    if burial_date:
        return False

    if birth_year is not None and current_year - birth_year <= max_age:
        return True

    return False
