from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from ged4py.parser import GedcomReader

from gedcom_tools.commands.compare.models import CompareIndividual
from gedcom_tools.commands.compare.phonetics import soundex
from gedcom_tools.dates import extract_year_from_date
from gedcom_tools.utils import extract_xref, parse_name_record

if TYPE_CHECKING:
    from pathlib import Path

    from ged4py.model import Record


def normalize_display(text: str) -> str:
    """NFC normalization for consistent display across encodings."""
    return unicodedata.normalize("NFC", text) if text else ""


def normalize_compare(text: str) -> str:
    """Full normalization for matching: NFC → strip diacritics → lowercase."""
    if not text:
        return ""
    nfc = unicodedata.normalize("NFC", text)
    nfd = unicodedata.normalize("NFD", nfc)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return stripped.lower()


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


def _extract_year(record: Record, path: str) -> int | None:
    date_rec = record.sub_tag(path)
    if date_rec is None or date_rec.value is None:
        return None
    return extract_year_from_date(date_rec.value)


def collect_individuals(file_path: Path, source_label: str) -> list[CompareIndividual]:
    """Extract CompareIndividual records from a GEDCOM file."""
    individuals: list[CompareIndividual] = []

    with GedcomReader(str(file_path)) as reader:
        for record in reader.records0("INDI"):
            xref = record.xref_id
            if not xref:
                continue
            individuals.append(_build_individual(record, xref, source_label))

    return individuals


def _build_individual(
    record: Record, xref: str, source_label: str
) -> CompareIndividual:
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

    birth_year = _extract_year(record, "BIRT/DATE")
    death_year = _extract_year(record, "DEAT/DATE")

    # Fallbacks: christening/baptism for birth, burial for death
    if birth_year is None:
        birth_year = _extract_year(record, "CHR/DATE")
        if birth_year is None:
            birth_year = _extract_year(record, "BAPM/DATE")
    if death_year is None:
        death_year = _extract_year(record, "BURI/DATE")

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
        surname_soundex=soundex(surname_norm),
        given_name_soundex=soundex(given_norm),
        birth_decade=_decade_key(birth_year),
        death_decade=_decade_key(death_year),
    )
