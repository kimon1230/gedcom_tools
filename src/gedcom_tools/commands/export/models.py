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
    # Years for estimate_living, kept separate from the reported ones above.
    # A year scraped out of free text is good enough to report but not to
    # decide whether to publish a living person's details, so these are set
    # from a stricter source and never fall back to the reported fields.
    liveness_birth_year: int | None = None
    liveness_death_year: int | None = None
    liveness_burial_year: int | None = None


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
    burial_year: int | None,
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
    4. Death year or burial year → not living. Both are read the same strict
       way as the birth year: "2 DATE (pre-need plot)" is text, not evidence
       that someone has died.
    5. Everything else, including an absent or unparseable birth date → living.
    """
    current_year = current_year or datetime.date.today().year

    has_death_evidence = death_year is not None or burial_year is not None

    if living_marker in _LIVING_TAGS:
        return True
    if living_marker in _NOT_LIVING_TAGS and has_death_evidence:
        return False

    if birth_year is not None and current_year - birth_year > max_age:
        return False

    if has_death_evidence:
        return False

    return True
