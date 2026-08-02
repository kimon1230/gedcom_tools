"""Data collection from GEDCOM files for export."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ged4py.model import Pointer
from ged4py.parser import GedcomReader

from gedcom_tools.commands.export.models import (
    ExportFamily,
    ExportIndividual,
    ExportResult,
)
from gedcom_tools.dates import (
    extract_year_from_date,
    extract_year_latest_from_date,
    is_phrase_date,
)
from gedcom_tools.utils import (
    count_sources_recursive,
    detect_encoding,
    extract_xref,
    normalize_display,
    parse_name_record,
)

if TYPE_CHECKING:
    from ged4py.model import Record


def _extract_place(record: Record, event_tag: str) -> str:
    event = record.sub_tag(event_tag)
    if event is None:
        return ""
    plac = event.sub_tag("PLAC")
    if plac is None or plac.value is None:
        return ""
    return normalize_display(str(plac.value))


def _extract_year(record: Record, path: str) -> int | None:
    date_rec = record.sub_tag(path)
    if date_rec is None or date_rec.value is None:
        return None
    return extract_year_from_date(date_rec.value)


def _extract_year_latest(record: Record, path: str) -> int | None:
    date_rec = record.sub_tag(path)
    if date_rec is None or date_rec.value is None:
        return None
    return extract_year_latest_from_date(date_rec.value)


def _extract_date_str(record: Record, path: str) -> str:
    """Extract the canonical date string from a GEDCOM date sub-record.

    Returns ged4py's canonical representation (e.g. "ABT 1850"),
    not necessarily the verbatim original GEDCOM text.
    """
    date_rec = record.sub_tag(path)
    if date_rec is None or date_rec.value is None:
        return ""
    if is_phrase_date(date_rec.value):
        phrase = getattr(date_rec.value, "phrase", None)
        return str(phrase) if phrase else ""
    return str(date_rec.value)


def _detect_living_marker(record: Record) -> str:
    """Check for custom living/not-living tags from genealogy software.

    Recognized tags: _LVG (Legacy/FTM), _LIVING (RootsMagic),
    _LVNG (FTM variant), _CONF_FLAG (PAF), _NLIV (Brother's Keeper).
    """
    from gedcom_tools.commands.export.models import _LIVING_TAGS, _NOT_LIVING_TAGS

    for sub in record.sub_records:
        if sub.tag in _NOT_LIVING_TAGS:
            return sub.tag
        if sub.tag in _LIVING_TAGS:
            return sub.tag
    return ""


def _extract_suffix(name_record: Record) -> str:
    """Extract suffix from ged4py NAME tuple (index 2)."""
    val = name_record.value
    if val is not None and isinstance(val, tuple) and len(val) > 2:
        suffix = val[2]
        return str(suffix) if suffix else ""
    return ""


def _build_individual(record: Record, xref: str) -> ExportIndividual:
    name_records = [sub for sub in record.sub_records if sub.tag == "NAME"]

    given = ""
    surname = ""
    suffix = ""
    alt_names: list[tuple[str, str]] = []

    for i, name_rec in enumerate(name_records):
        g, s = parse_name_record(name_rec)
        if i == 0:
            given = g
            surname = s
            suffix = _extract_suffix(name_rec)
        else:
            alt_names.append((normalize_display(g), normalize_display(s)))

    given = normalize_display(given)
    surname = normalize_display(surname)
    suffix = normalize_display(suffix)

    sex = ""
    sex_rec = record.sub_tag("SEX")
    if sex_rec and sex_rec.value:
        sex = str(sex_rec.value).upper().strip()

    # Birth: date string + year + place, with fallbacks
    birth_date = _extract_date_str(record, "BIRT/DATE")
    birth_year = _extract_year(record, "BIRT/DATE")
    birth_year_latest = _extract_year_latest(record, "BIRT/DATE")
    birth_place = _extract_place(record, "BIRT")

    # Fallback for birth year: CHR, then BAPM (year only, not date string)
    for fallback_path in ("CHR/DATE", "BAPM/DATE"):
        if birth_year is not None:
            break
        birth_year = _extract_year(record, fallback_path)
        birth_year_latest = _extract_year_latest(record, fallback_path)

    # Death: date string + year + place
    death_date = _extract_date_str(record, "DEAT/DATE")
    death_year = _extract_year(record, "DEAT/DATE")
    death_place = _extract_place(record, "DEAT")

    # Fallback for death year: BURI (year only)
    if death_year is None:
        death_year = _extract_year(record, "BURI/DATE")

    # Burial
    burial_date = _extract_date_str(record, "BURI/DATE")
    burial_place = _extract_place(record, "BURI")

    # Occupations, notes, family links via sub_records iteration
    occupations: list[str] = []
    notes: list[str] = []
    famc_xref = ""
    fams_xrefs: list[str] = []

    for sub in record.sub_records:
        if sub.tag == "OCCU" and sub.value:
            occupations.append(str(sub.value))
        elif sub.tag == "NOTE":
            if isinstance(sub, Pointer):
                continue
            if sub.value is not None:
                text = str(sub.value).strip()
                if text:
                    notes.append(text)
        elif sub.tag == "FAMC" and sub.value:
            ref = extract_xref(sub.value)
            if ref and not famc_xref:
                famc_xref = ref
        elif sub.tag == "FAMS" and sub.value:
            ref = extract_xref(sub.value)
            if ref:
                fams_xrefs.append(ref)

    source_count = count_sources_recursive(record)
    living_marker = _detect_living_marker(record)

    return ExportIndividual(
        xref=xref,
        given_name=given,
        surname=surname,
        suffix=suffix,
        sex=sex,
        birth_date=birth_date,
        birth_year=birth_year,
        birth_year_latest=birth_year_latest,
        birth_place=birth_place,
        death_date=death_date,
        death_year=death_year,
        death_place=death_place,
        burial_date=burial_date,
        burial_place=burial_place,
        occupations=occupations,
        source_count=source_count,
        famc_xref=famc_xref,
        fams_xrefs=fams_xrefs,
        living_marker=living_marker,
        alt_names=alt_names,
        notes=notes,
    )


def _build_family(record: Record, xref: str, name_map: dict[str, str]) -> ExportFamily:
    husband_xref = ""
    wife_xref = ""
    children_xrefs: list[str] = []

    for sub in record.sub_records:
        if sub.tag == "HUSB" and sub.value:
            ref = extract_xref(sub.value)
            if ref:
                husband_xref = ref
        elif sub.tag == "WIFE" and sub.value:
            ref = extract_xref(sub.value)
            if ref:
                wife_xref = ref
        elif sub.tag == "CHIL" and sub.value:
            ref = extract_xref(sub.value)
            if ref:
                children_xrefs.append(ref)

    marriage_date = _extract_date_str(record, "MARR/DATE")
    marriage_year = _extract_year(record, "MARR/DATE")
    marriage_place = _extract_place(record, "MARR")

    return ExportFamily(
        xref=xref,
        husband_xref=husband_xref,
        husband_name=name_map.get(husband_xref, ""),
        wife_xref=wife_xref,
        wife_name=name_map.get(wife_xref, ""),
        marriage_date=marriage_date,
        marriage_year=marriage_year,
        marriage_place=marriage_place,
        child_count=len(children_xrefs),
        children_xrefs=children_xrefs,
    )


def collect_export_data(file_path: Path) -> ExportResult:
    """Extract all individuals and families from a GEDCOM file."""
    encoding_info = detect_encoding(file_path)

    individuals: list[ExportIndividual] = []
    name_map: dict[str, str] = {}
    families: list[ExportFamily] = []

    with GedcomReader(str(file_path)) as reader:
        for record in reader.records0("INDI"):
            xref = record.xref_id
            if not xref:
                continue
            indi = _build_individual(record, xref)
            individuals.append(indi)
            # Build display name for family denormalization
            parts = [indi.given_name, indi.surname]
            if indi.suffix:
                parts.append(indi.suffix)
            name_map[xref] = " ".join(p for p in parts if p)

        for record in reader.records0("FAM"):
            xref = record.xref_id
            if not xref:
                continue
            families.append(_build_family(record, xref, name_map))

    return ExportResult(
        file_path=str(file_path),
        encoding=encoding_info.encoding,
        individual_count=len(individuals),
        family_count=len(families),
        individuals=individuals,
        families=families,
    )
