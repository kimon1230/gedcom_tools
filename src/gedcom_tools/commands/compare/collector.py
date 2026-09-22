from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ged4py.parser import GedcomReader

from gedcom_tools.commands.compare.models import CompareIndividual

if TYPE_CHECKING:
    from ged4py.model import Record
from gedcom_tools.dates import (
    BIRTH_EVENT_TAGS,
    DEATH_EVENT_TAGS,
    extract_year_from_date,
)
from gedcom_tools.utils import (
    extract_xref,
    normalize_compare,
    normalize_display,
    parse_name_record,
)


def _decade_key(year: int | None) -> str:
    if year is None:
        return ""
    return f"{(year // 10) * 10}s"


def _extract_place(record: Record, event_tag: str) -> str:
    event = record.sub_tag(event_tag)
    if event is None:
        return ""
    plac = event.sub_tag("PLAC")
    if plac is None or plac.value is None:
        return ""
    return str(plac.value)


def _first_year(record: Record, tags: tuple[str, ...]) -> int | None:
    """Year of the first of these events that yields one, in tag order."""
    for tag in tags:
        year = _extract_year(record, f"{tag}/DATE")
        if year is not None:
            return year
    return None


def _extract_year(record: Record, path: str) -> int | None:
    date_rec = record.sub_tag(path)
    if date_rec is None or date_rec.value is None:
        return None
    return extract_year_from_date(date_rec.value)


def collect_individuals(
    file_path: Path, source_label: str, algorithm: str = "soundex"
) -> list[CompareIndividual]:
    """Extract CompareIndividual records from a GEDCOM file."""
    individuals: list[CompareIndividual] = []

    with GedcomReader(str(file_path)) as reader:
        for record in reader.records0("INDI"):
            xref = record.xref_id
            if not xref:
                continue
            individuals.append(_build_individual(record, xref, source_label, algorithm))

    return individuals


def _build_individual(
    record: Record, xref: str, source_label: str, algorithm: str = "soundex"
) -> CompareIndividual:
    from gedcom_tools.phonetics import phonetic_encode

    name_records = [sub for sub in record.sub_records if sub.tag == "NAME"]

    given = ""
    surname = ""
    alt_givens: list[str] = []
    alt_surnames: list[str] = []

    for i, name_rec in enumerate(name_records):
        g, s = parse_name_record(name_rec)
        if i == 0:
            given = g
            surname = s
        else:
            if g and g != given:
                alt_givens.append(g)
            if s and s != surname:
                alt_surnames.append(s)

    given_display = normalize_display(given)
    surname_display = normalize_display(surname)
    full_name = f"{given_display} {surname_display}".strip()

    sex = ""
    sex_rec = record.sub_tag("SEX")
    if sex_rec and sex_rec.value:
        raw = str(sex_rec.value).upper().strip()
        if raw in ("M", "F"):
            sex = raw

    # Preferred tag first, then the fallbacks - christening/baptism for birth,
    # burial for death. Same tuples the validator walks, so a recovery path
    # added here cannot leave W035 blind to the dates it creates.
    birth_year = _first_year(record, BIRTH_EVENT_TAGS)
    death_year = _first_year(record, DEATH_EVENT_TAGS)

    birth_place = normalize_display(_extract_place(record, "BIRT"))
    death_place = normalize_display(_extract_place(record, "DEAT"))

    famc_xref: str | None = None
    fams_xrefs: list[str] = []
    for sub in record.sub_records:
        if sub.tag == "FAMC" and sub.value:
            ref = extract_xref(sub.value)
            if ref and famc_xref is None:
                famc_xref = ref
        elif sub.tag == "FAMS" and sub.value:
            ref = extract_xref(sub.value)
            if ref:
                fams_xrefs.append(ref)

    given_norm = normalize_compare(given_display)
    surname_norm = normalize_compare(surname_display)
    alt_givens_display = [normalize_display(g) for g in alt_givens]
    alt_surnames_display = [normalize_display(s) for s in alt_surnames]

    s_p, s_a = phonetic_encode(surname_norm, algorithm)
    g_p, g_a = phonetic_encode(given_norm, algorithm)

    return CompareIndividual(
        xref=xref,
        source_file=source_label,
        given_name=given_display,
        surname=surname_display,
        full_name=full_name,
        sex=sex,
        birth_year=birth_year,
        birth_place=birth_place,
        death_year=death_year,
        death_place=death_place,
        famc_xref=famc_xref,
        fams_xrefs=fams_xrefs,
        alt_surnames=alt_surnames_display,
        alt_given_names=alt_givens_display,
        given_name_normalized=given_norm,
        surname_normalized=surname_norm,
        birth_place_normalized=normalize_compare(birth_place),
        death_place_normalized=normalize_compare(death_place),
        alt_surnames_normalized=[normalize_compare(s) for s in alt_surnames_display],
        alt_given_names_normalized=[normalize_compare(g) for g in alt_givens_display],
        surname_phonetic=s_p,
        surname_phonetic_alt=s_a,
        given_phonetic=g_p,
        given_phonetic_alt=g_a,
        birth_decade=_decade_key(birth_year),
        death_decade=_decade_key(death_year),
    )
