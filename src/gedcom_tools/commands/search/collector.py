from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ged4py.parser import GedcomReader

from gedcom_tools.commands.search.models import SearchIndividual
from gedcom_tools.dates import classify_date_precision, extract_year_from_date
from gedcom_tools.phonetics import soundex
from gedcom_tools.utils import (
    EncodingInfo,
    detect_encoding,
    normalize_compare,
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


def _extract_date_value(record: Record, path: str) -> object | None:
    date_rec = record.sub_tag(path)
    if date_rec is None or date_rec.value is None:
        return None
    return date_rec.value


def _extract_year(record: Record, path: str) -> int | None:
    val = _extract_date_value(record, path)
    return extract_year_from_date(val)


def _is_approximate(record: Record, path: str) -> bool:
    val = _extract_date_value(record, path)
    if val is None:
        return False
    category, _ = classify_date_precision(val)
    return category == "approximate"


def _resolve_birth(record: Record) -> tuple[int | None, bool, str]:
    """Return (year, approximate, place) using fallback chain."""
    for date_path, place_tag in [
        ("BIRT/DATE", "BIRT"),
        ("CHR/DATE", "CHR"),
        ("BAPM/DATE", "BAPM"),
    ]:
        year = _extract_year(record, date_path)
        if year is not None:
            approx = _is_approximate(record, date_path)
            place = _extract_place(record, place_tag)
            return year, approx, place

    # No year found in any fallback — still grab BIRT place if present
    place = _extract_place(record, "BIRT")
    return None, False, place


def _resolve_death(record: Record) -> tuple[int | None, bool, str]:
    """Return (year, approximate, place) using fallback chain."""
    for date_path, place_tag in [
        ("DEAT/DATE", "DEAT"),
        ("BURI/DATE", "BURI"),
    ]:
        year = _extract_year(record, date_path)
        if year is not None:
            approx = _is_approximate(record, date_path)
            place = _extract_place(record, place_tag)
            return year, approx, place

    place = _extract_place(record, "DEAT")
    return None, False, place


def _build_individual(record: Record, xref: str) -> SearchIndividual:
    name_records = [sub for sub in record.sub_records if sub.tag == "NAME"]

    given = ""
    surname = ""
    alt_names: list[tuple[str, str]] = []

    for i, name_rec in enumerate(name_records):
        g, s = parse_name_record(name_rec)
        if i == 0:
            given = g
            surname = s
        else:
            alt_names.append((g, s))

    given_display = normalize_display(given)
    surname_display = normalize_display(surname)
    full_name = f"{given_display} {surname_display}".strip()

    sex = ""
    sex_rec = record.sub_tag("SEX")
    if sex_rec and sex_rec.value:
        sex = str(sex_rec.value).upper().strip()

    birth_year, birth_approx, birth_place = _resolve_birth(record)
    death_year, death_approx, death_place = _resolve_death(record)

    alt_names_display = [
        (normalize_display(g), normalize_display(s)) for g, s in alt_names
    ]

    # Normalized fields
    given_norm = normalize_compare(given_display)
    surname_norm = normalize_compare(surname_display)
    full_name_norm = normalize_compare(full_name)
    birth_place_norm = normalize_compare(birth_place)
    death_place_norm = normalize_compare(death_place)
    alt_names_norm = [
        (normalize_compare(g), normalize_compare(s)) for g, s in alt_names_display
    ]

    # Soundex codes
    surname_sx = soundex(surname_norm)
    given_sx = soundex(given_norm)
    alt_sx = [(soundex(g_norm), soundex(s_norm)) for g_norm, s_norm in alt_names_norm]

    return SearchIndividual(
        xref=xref,
        given_name=given_display,
        surname=surname_display,
        full_name=full_name,
        sex=sex,
        birth_year=birth_year,
        birth_year_approximate=birth_approx,
        birth_place=birth_place,
        death_year=death_year,
        death_year_approximate=death_approx,
        death_place=death_place,
        alt_names=alt_names_display,
        given_name_norm=given_norm,
        surname_norm=surname_norm,
        full_name_norm=full_name_norm,
        birth_place_norm=birth_place_norm,
        death_place_norm=death_place_norm,
        alt_names_norm=alt_names_norm,
        surname_soundex=surname_sx,
        given_name_soundex=given_sx,
        alt_soundex=alt_sx,
    )


def collect_individuals(
    file_path: Path,
) -> tuple[list[SearchIndividual], EncodingInfo]:
    encoding_info = detect_encoding(file_path)
    individuals: list[SearchIndividual] = []

    with GedcomReader(str(file_path)) as reader:
        for record in reader.records0("INDI"):
            xref = record.xref_id
            if not xref:
                continue
            individuals.append(_build_individual(record, xref))

    return individuals, encoding_info
