"""CSV and JSON formatters for the export command."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

from gedcom_tools import __version__
from gedcom_tools.commands.export.models import estimate_living

if TYPE_CHECKING:
    from gedcom_tools.commands.export.models import (
        ExportFamily,
        ExportIndividual,
        ExportResult,
    )

_INDI_CSV_COLUMNS = [
    "xref",
    "given_name",
    "surname",
    "suffix",
    "sex",
    "birth_date",
    "birth_year",
    "birth_place",
    "death_date",
    "death_year",
    "death_place",
    "burial_date",
    "burial_place",
    "occupations",
    "source_count",
    "famc_xref",
    "fams_xrefs",
]

_FAM_CSV_COLUMNS = [
    "xref",
    "husband_xref",
    "husband_name",
    "wife_xref",
    "wife_name",
    "marriage_date",
    "marriage_year",
    "marriage_place",
    "child_count",
    "children_xrefs",
]


def _redact_individual_csv(indi: ExportIndividual) -> list[str]:
    """Build a redacted CSV row for a living individual."""
    return [
        indi.xref,
        "Living",
        "",  # surname
        "",  # suffix
        indi.sex,
        "",  # birth_date
        "",  # birth_year
        "",  # birth_place
        "",  # death_date
        "",  # death_year
        "",  # death_place
        "",  # burial_date
        "",  # burial_place
        "",  # occupations
        str(indi.source_count),
        indi.famc_xref,
        ";".join(indi.fams_xrefs),
    ]


def _individual_csv_row(indi: ExportIndividual) -> list[str]:
    return [
        indi.xref,
        indi.given_name,
        indi.surname,
        indi.suffix,
        indi.sex,
        indi.birth_date,
        str(indi.birth_year) if indi.birth_year is not None else "",
        indi.birth_place,
        indi.death_date,
        str(indi.death_year) if indi.death_year is not None else "",
        indi.death_place,
        indi.burial_date,
        indi.burial_place,
        "; ".join(indi.occupations),
        str(indi.source_count),
        indi.famc_xref,
        ";".join(indi.fams_xrefs),
    ]


def _family_csv_row(
    fam: ExportFamily, living_xrefs: set[str] | None = None
) -> list[str]:
    husband_name = fam.husband_name
    wife_name = fam.wife_name
    if living_xrefs:
        if fam.husband_xref in living_xrefs:
            husband_name = "Living"
        if fam.wife_xref in living_xrefs:
            wife_name = "Living"
    return [
        fam.xref,
        fam.husband_xref,
        husband_name,
        fam.wife_xref,
        wife_name,
        fam.marriage_date,
        str(fam.marriage_year) if fam.marriage_year is not None else "",
        fam.marriage_place,
        str(fam.child_count),
        ";".join(fam.children_xrefs),
    ]


def format_csv(
    result: ExportResult,
    table: str = "individuals",
    include_bom: bool = True,
    redact_living: bool = False,
    max_age: int = 110,
) -> str:
    buf = io.StringIO()
    if include_bom:
        buf.write("\ufeff")

    writer = csv.writer(buf)

    living_xrefs: set[str] | None = None
    if redact_living:
        living_xrefs = {
            indi.xref
            for indi in result.individuals
            if estimate_living(
                indi.birth_year, indi.death_year, indi.burial_date, max_age=max_age
            )
        }

    if table == "families":
        writer.writerow(_FAM_CSV_COLUMNS)
        for fam in result.families:
            writer.writerow(_family_csv_row(fam, living_xrefs))
    else:
        writer.writerow(_INDI_CSV_COLUMNS)
        for indi in result.individuals:
            if living_xrefs and indi.xref in living_xrefs:
                writer.writerow(_redact_individual_csv(indi))
            else:
                writer.writerow(_individual_csv_row(indi))

    return buf.getvalue()


def _individual_to_dict(
    indi: ExportIndividual, redacted: bool = False
) -> dict[str, Any]:
    if redacted:
        return {
            "xref": indi.xref,
            "given_name": "Living",
            "surname": "",
            "suffix": "",
            "sex": indi.sex,
            "birth_date": "",
            "birth_year": None,
            "birth_place": "",
            "death_date": "",
            "death_year": None,
            "death_place": "",
            "burial_date": "",
            "burial_place": "",
            "occupations": [],
            "source_count": indi.source_count,
            "famc_xref": indi.famc_xref,
            "fams_xrefs": list(indi.fams_xrefs),
            "alt_names": [],
            "notes": [],
        }
    return {
        "xref": indi.xref,
        "given_name": indi.given_name,
        "surname": indi.surname,
        "suffix": indi.suffix,
        "sex": indi.sex,
        "birth_date": indi.birth_date,
        "birth_year": indi.birth_year,
        "birth_place": indi.birth_place,
        "death_date": indi.death_date,
        "death_year": indi.death_year,
        "death_place": indi.death_place,
        "burial_date": indi.burial_date,
        "burial_place": indi.burial_place,
        "occupations": list(indi.occupations),
        "source_count": indi.source_count,
        "famc_xref": indi.famc_xref,
        "fams_xrefs": list(indi.fams_xrefs),
        "alt_names": [{"given": g, "surname": s} for g, s in indi.alt_names],
        "notes": list(indi.notes),
    }


def _family_to_dict(
    fam: ExportFamily, living_xrefs: set[str] | None = None
) -> dict[str, Any]:
    husband_name = fam.husband_name
    wife_name = fam.wife_name
    if living_xrefs:
        if fam.husband_xref in living_xrefs:
            husband_name = "Living"
        if fam.wife_xref in living_xrefs:
            wife_name = "Living"
    return {
        "xref": fam.xref,
        "husband_xref": fam.husband_xref,
        "husband_name": husband_name,
        "wife_xref": fam.wife_xref,
        "wife_name": wife_name,
        "marriage_date": fam.marriage_date,
        "marriage_year": fam.marriage_year,
        "marriage_place": fam.marriage_place,
        "child_count": fam.child_count,
        "children_xrefs": list(fam.children_xrefs),
    }


def format_json(
    result: ExportResult,
    redact_living: bool = False,
    max_age: int = 110,
) -> str:
    living_xrefs: set[str] | None = None
    if redact_living:
        living_xrefs = {
            indi.xref
            for indi in result.individuals
            if estimate_living(
                indi.birth_year, indi.death_year, indi.burial_date, max_age=max_age
            )
        }

    data: dict[str, Any] = {
        "meta": {
            "file": result.file_path,
            "encoding": result.encoding,
            "gedcom_tools_version": __version__,
            "individual_count": result.individual_count,
            "family_count": result.family_count,
            "redacted_living": redact_living,
        },
        "individuals": [
            _individual_to_dict(
                indi, redacted=living_xrefs is not None and indi.xref in living_xrefs
            )
            for indi in result.individuals
        ],
        "families": [_family_to_dict(fam, living_xrefs) for fam in result.families],
    }

    return json.dumps(data, indent=2, ensure_ascii=False)
