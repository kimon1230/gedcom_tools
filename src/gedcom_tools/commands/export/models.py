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
    # Upper bound of a range/period birth date ("BET 1900 AND 1995" -> 1995).
    # Not exported; only liveness estimation reads it.
    birth_year_latest: int | None = None
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

    @property
    def liveness_birth_year(self) -> int | None:
        """Birth year to feed to estimate_living: latest bound when there is one."""
        if self.birth_year_latest is not None:
            return self.birth_year_latest
        return self.birth_year


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

    This drives --redact-living, so unknown means living: a wrong "living"
    over-redacts one row, a wrong "not living" publishes a real person's
    details. Priority order:

    1. _LVG/_LIVING/_LVNG/_CONF_FLAG → living. A file claiming someone IS
       living fails safe, so it is taken at face value.
    2. _NLIV → not living, but only when the same record carries independent
       death evidence. The tag comes from a file we did not write and would
       otherwise be a switch for turning redaction off wholesale.
    3. Birth year older than max_age → not living, whether or not the record
       has a death date. max_age is the ceiling on a plausible lifespan, and it
       is what keeps rule 5 from resurrecting every undated ancestor.
    4. Death year or burial date → not living.
    5. Everything else, including an absent or unparseable birth date → living.
    """
    current_year = current_year or datetime.date.today().year

    has_death_evidence = death_year is not None or bool(burial_date)

    if living_marker in _LIVING_TAGS:
        return True
    if living_marker in _NOT_LIVING_TAGS and has_death_evidence:
        return False

    if birth_year is not None and current_year - birth_year > max_age:
        return False

    if has_death_evidence:
        return False

    return True
