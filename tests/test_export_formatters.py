from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from gedcom_tools.commands.export import run
from gedcom_tools.commands.export.formatters import (
    _CSV_TRIGGERS,
    _FAM_CSV_COLUMNS,
    _INDI_CSV_COLUMNS,
    _csv_safe,
    _redact_individual_csv,
    format_csv,
    format_json,
)
from gedcom_tools.commands.export.models import (
    ExportFamily,
    ExportIndividual,
    ExportResult,
)
from gedcom_tools.constants import EXIT_SUCCESS


def _indi(
    xref: str = "@I1@",
    given_name: str = "John",
    surname: str = "Smith",
    suffix: str = "",
    sex: str = "M",
    birth_date: str = "15 JAN 1850",
    birth_year: int | None = 1850,
    birth_place: str = "London, England",
    death_date: str = "ABT 1920",
    death_year: int | None = 1920,
    death_place: str = "New York, USA",
    burial_date: str = "",
    burial_place: str = "",
    occupations: list[str] | None = None,
    source_count: int = 3,
    famc_xref: str = "@F5@",
    fams_xrefs: list[str] | None = None,
    living_marker: str = "",
    alt_names: list[tuple[str, str]] | None = None,
    notes: list[str] | None = None,
) -> ExportIndividual:
    return ExportIndividual(
        xref=xref,
        given_name=given_name,
        surname=surname,
        suffix=suffix,
        sex=sex,
        birth_date=birth_date,
        birth_year=birth_year,
        birth_place=birth_place,
        death_date=death_date,
        death_year=death_year,
        death_place=death_place,
        burial_date=burial_date,
        burial_place=burial_place,
        occupations=occupations or ["Blacksmith"],
        source_count=source_count,
        famc_xref=famc_xref,
        fams_xrefs=fams_xrefs if fams_xrefs is not None else ["@F1@", "@F7@"],
        living_marker=living_marker,
        alt_names=alt_names or [],
        notes=notes or [],
    )


def _fam(
    xref: str = "@F1@",
    husband_xref: str = "@I1@",
    husband_name: str = "John Smith",
    wife_xref: str = "@I2@",
    wife_name: str = "Mary Jones",
    marriage_date: str = "3 JUN 1875",
    marriage_year: int | None = 1875,
    marriage_place: str = "St. Mary's Church, London",
    child_count: int = 2,
    children_xrefs: list[str] | None = None,
) -> ExportFamily:
    return ExportFamily(
        xref=xref,
        husband_xref=husband_xref,
        husband_name=husband_name,
        wife_xref=wife_xref,
        wife_name=wife_name,
        marriage_date=marriage_date,
        marriage_year=marriage_year,
        marriage_place=marriage_place,
        child_count=child_count,
        children_xrefs=(
            children_xrefs if children_xrefs is not None else ["@I3@", "@I4@"]
        ),
    )


def _result(
    individuals: list[ExportIndividual] | None = None,
    families: list[ExportFamily] | None = None,
) -> ExportResult:
    indis = individuals if individuals is not None else [_indi()]
    fams = families if families is not None else [_fam()]
    return ExportResult(
        file_path="tree.ged",
        encoding="UTF-8",
        individual_count=len(indis),
        family_count=len(fams),
        individuals=indis,
        families=fams,
    )


# ---------------------------------------------------------------------------
# CSV — individuals
# ---------------------------------------------------------------------------


class TestCsvIndividuals:
    def test_header_and_data_row(self) -> None:
        out = format_csv(_result(), include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        header = rows[0]
        assert header[0] == "xref"
        assert header[-1] == "fams_xrefs"
        assert len(header) == 17
        data = rows[1]
        assert data[0] == "@I1@"
        assert data[1] == "John"
        assert data[2] == "Smith"
        assert data[4] == "M"

    def test_bom_present(self) -> None:
        out = format_csv(_result(), include_bom=True)
        assert out[0] == "\ufeff"

    def test_no_bom(self) -> None:
        out = format_csv(_result(), include_bom=False)
        assert out[0] != "\ufeff"

    def test_multi_value_fams_xrefs(self) -> None:
        out = format_csv(_result(), include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][-1] == "@F1@;@F7@"

    def test_occupations_joined_with_semicolon_space(self) -> None:
        indi = _indi(occupations=["Blacksmith", "Farmer"])
        out = format_csv(_result(individuals=[indi]), include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][13] == "Blacksmith; Farmer"

    def test_empty_fields(self) -> None:
        indi = ExportIndividual(
            xref="@I1@",
            given_name="John",
            surname="Smith",
        )
        out = format_csv(_result(individuals=[indi]), include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][3] == ""  # suffix
        assert rows[1][11] == ""  # burial_date
        assert rows[1][13] == ""  # occupations
        assert rows[1][-1] == ""  # fams_xrefs

    def test_special_characters_quoted(self) -> None:
        indi = _indi(birth_place='London, "Greater" Area')
        out = format_csv(_result(individuals=[indi]), include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][7] == 'London, "Greater" Area'

    def test_none_year_renders_empty(self) -> None:
        indi = _indi(birth_year=None, death_year=None)
        out = format_csv(_result(individuals=[indi]), include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][6] == ""  # birth_year
        assert rows[1][9] == ""  # death_year

    def test_redact_living_individual(self) -> None:
        living = _indi(
            xref="@I9@",
            given_name="Alice",
            surname="Modern",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        out = format_csv(
            _result(individuals=[living]),
            include_bom=False,
            redact_living=True,
            max_age=110,
        )
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        row = rows[1]
        assert row[0] == "@I9@"  # xref preserved
        assert row[1] == "Living"  # given_name
        assert row[2] == ""  # surname cleared
        assert row[5] == ""  # birth_date cleared
        assert row[6] == ""  # birth_year cleared

    def test_dead_individual_not_redacted(self) -> None:
        dead = _indi(death_year=1920)
        out = format_csv(
            _result(individuals=[dead]),
            include_bom=False,
            redact_living=True,
        )
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][1] == "John"


# ---------------------------------------------------------------------------
# CSV — families
# ---------------------------------------------------------------------------


class TestCsvFamilies:
    def test_header_and_data_row(self) -> None:
        out = format_csv(_result(), table="families", include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        header = rows[0]
        assert header[0] == "xref"
        assert header[-1] == "children_xrefs"
        assert len(header) == 10
        data = rows[1]
        assert data[0] == "@F1@"
        assert data[2] == "John Smith"

    def test_children_xrefs_semicolon(self) -> None:
        out = format_csv(_result(), table="families", include_bom=False)
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][-1] == "@I3@;@I4@"

    def test_redacted_living_spouse_name(self) -> None:
        living = _indi(
            xref="@I1@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        fam = _fam(husband_xref="@I1@", husband_name="John Smith")
        out = format_csv(
            _result(individuals=[living], families=[fam]),
            table="families",
            include_bom=False,
            redact_living=True,
        )
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][2] == "Living"


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


class TestJsonFormat:
    def test_full_structure(self) -> None:
        out = format_json(_result())
        data = json.loads(out)
        assert "meta" in data
        assert "individuals" in data
        assert "families" in data

    def test_meta_section(self) -> None:
        out = format_json(_result())
        data = json.loads(out)
        meta = data["meta"]
        assert meta["file"] == "tree.ged"
        assert meta["filename"] == "tree.ged"
        assert meta["encoding"] == "UTF-8"
        assert meta["individual_count"] == 1
        assert meta["family_count"] == 1
        assert meta["redacted_living"] is False
        from gedcom_tools import __version__

        assert meta["gedcom_tools_version"] == __version__

    def test_meta_filename_is_basename(self) -> None:
        result = _result()
        result.file_path = "/some/deep/path/family.ged"
        out = format_json(result)
        data = json.loads(out)
        assert data["meta"]["filename"] == "family.ged"
        assert data["meta"]["file"] == "/some/deep/path/family.ged"

    def test_individual_all_fields(self) -> None:
        indi = _indi(
            alt_names=[("Johann", "Schmidt")],
            notes=["A biographical note"],
        )
        out = format_json(_result(individuals=[indi]))
        data = json.loads(out)
        ind = data["individuals"][0]
        assert ind["xref"] == "@I1@"
        assert ind["given_name"] == "John"
        assert ind["surname"] == "Smith"
        assert ind["sex"] == "M"
        assert ind["birth_year"] == 1850
        assert ind["death_year"] == 1920

    def test_occupations_as_array(self) -> None:
        indi = _indi(occupations=["Blacksmith", "Farmer"])
        out = format_json(_result(individuals=[indi]))
        data = json.loads(out)
        assert data["individuals"][0]["occupations"] == ["Blacksmith", "Farmer"]

    def test_alt_names_as_objects(self) -> None:
        indi = _indi(alt_names=[("Johann", "Schmidt"), ("Jean", "Forgeron")])
        out = format_json(_result(individuals=[indi]))
        data = json.loads(out)
        alt = data["individuals"][0]["alt_names"]
        assert len(alt) == 2
        assert alt[0] == {"given": "Johann", "surname": "Schmidt"}

    def test_notes_as_array(self) -> None:
        indi = _indi(notes=["Note one", "Note two"])
        out = format_json(_result(individuals=[indi]))
        data = json.loads(out)
        assert data["individuals"][0]["notes"] == ["Note one", "Note two"]

    def test_null_year(self) -> None:
        indi = _indi(birth_year=None)
        out = format_json(_result(individuals=[indi]))
        data = json.loads(out)
        assert data["individuals"][0]["birth_year"] is None

    def test_ensure_ascii_false(self) -> None:
        indi = _indi(given_name="Müller", birth_place="München")
        out = format_json(_result(individuals=[indi]))
        assert "Müller" in out
        assert "München" in out

    def test_table_ignored_for_json(self) -> None:
        """JSON always includes both individuals and families."""
        out = format_json(_result())
        data = json.loads(out)
        assert len(data["individuals"]) == 1
        assert len(data["families"]) == 1

    def test_redacted_living_individual(self) -> None:
        living = _indi(
            xref="@I9@",
            given_name="Alice",
            surname="Modern",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
            alt_names=[("Alicia", "Moderna")],
            notes=["Private note"],
        )
        out = format_json(
            _result(individuals=[living]),
            redact_living=True,
            max_age=110,
        )
        data = json.loads(out)
        ind = data["individuals"][0]
        assert ind["given_name"] == "Living"
        assert ind["surname"] == ""
        assert ind["birth_date"] == ""
        assert ind["birth_year"] is None
        assert ind["alt_names"] == []
        assert ind["notes"] == []
        assert data["meta"]["redacted_living"] is True

    def test_redacted_living_spouse_in_family(self) -> None:
        living = _indi(
            xref="@I1@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        fam = _fam(husband_xref="@I1@", husband_name="John Smith")
        out = format_json(
            _result(individuals=[living], families=[fam]),
            redact_living=True,
        )
        data = json.loads(out)
        assert data["families"][0]["husband_name"] == "Living"

    def test_family_fields(self) -> None:
        out = format_json(_result())
        data = json.loads(out)
        fam = data["families"][0]
        assert fam["xref"] == "@F1@"
        assert fam["husband_xref"] == "@I1@"
        assert fam["husband_name"] == "John Smith"
        assert fam["marriage_year"] == 1875
        assert fam["child_count"] == 2
        assert fam["children_xrefs"] == ["@I3@", "@I4@"]


# ---------------------------------------------------------------------------
# Xref redaction — CSV
# ---------------------------------------------------------------------------


class TestCsvXrefRedaction:
    def test_redacted_csv_clears_family_xrefs(self) -> None:
        living = _indi(
            xref="@I9@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
            famc_xref="@F5@",
            fams_xrefs=["@F1@", "@F7@"],
        )
        out = format_csv(
            _result(individuals=[living]),
            include_bom=False,
            redact_living=True,
        )
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        row = rows[1]
        assert row[15] == ""  # famc_xref cleared
        assert row[16] == ""  # fams_xrefs cleared

    def test_family_csv_redacts_living_spouse_xrefs(self) -> None:
        living = _indi(
            xref="@I1@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        fam = _fam(
            husband_xref="@I1@",
            wife_xref="@I2@",
            children_xrefs=["@I1@", "@I3@"],
        )
        out = format_csv(
            _result(individuals=[living], families=[fam]),
            table="families",
            include_bom=False,
            redact_living=True,
        )
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        row = rows[1]
        assert row[1] == ""  # husband_xref cleared (living)
        assert row[3] == "@I2@"  # wife_xref kept (not living)
        xrefs = row[9].split(";")
        assert xrefs[0] == ""  # child @I1@ cleared
        assert xrefs[1] == "@I3@"  # child @I3@ kept


# ---------------------------------------------------------------------------
# Xref redaction — JSON
# ---------------------------------------------------------------------------


class TestJsonXrefRedaction:
    def test_redacted_json_clears_family_xrefs(self) -> None:
        living = _indi(
            xref="@I9@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
            famc_xref="@F5@",
            fams_xrefs=["@F1@"],
        )
        out = format_json(
            _result(individuals=[living]),
            redact_living=True,
        )
        data = json.loads(out)
        ind = data["individuals"][0]
        assert ind["famc_xref"] == ""
        assert ind["fams_xrefs"] == []

    def test_family_json_redacts_living_xrefs(self) -> None:
        living = _indi(
            xref="@I1@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        fam = _fam(
            husband_xref="@I1@",
            wife_xref="@I2@",
            children_xrefs=["@I1@", "@I3@"],
        )
        out = format_json(
            _result(individuals=[living], families=[fam]),
            redact_living=True,
        )
        data = json.loads(out)
        fam_data = data["families"][0]
        assert fam_data["husband_xref"] == ""
        assert fam_data["husband_name"] == "Living"
        assert fam_data["wife_xref"] == "@I2@"
        assert fam_data["children_xrefs"] == ["", "@I3@"]

    def test_no_dates_is_redacted(self) -> None:
        """Nothing in the record rules out a living person, so the row is redacted."""
        unknown = _indi(
            xref="@I5@",
            birth_year=None,
            death_year=None,
            death_date="",
            burial_date="",
        )
        out = format_json(
            _result(individuals=[unknown]),
            redact_living=True,
        )
        data = json.loads(out)
        ind = data["individuals"][0]
        assert ind["given_name"] == "Living"

    def test_living_tag_causes_redaction(self) -> None:
        """Individual with _LVG tag is redacted regardless of dates."""
        tagged = _indi(
            xref="@I6@",
            birth_year=None,
            death_year=None,
            death_date="",
            burial_date="",
            living_marker="_LVG",
        )
        out = format_json(
            _result(individuals=[tagged]),
            redact_living=True,
        )
        data = json.loads(out)
        ind = data["individuals"][0]
        assert ind["given_name"] == "Living"

    def test_uncorroborated_nliv_tag_still_redacts(self) -> None:
        """_NLIV alone is a file's unverified claim — it needs death evidence."""
        tagged = _indi(
            xref="@I7@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
            living_marker="_NLIV",
        )
        out = format_json(
            _result(individuals=[tagged]),
            redact_living=True,
        )
        data = json.loads(out)
        ind = data["individuals"][0]
        assert ind["given_name"] == "Living"

    def test_nliv_tag_with_death_evidence_prevents_redaction(self) -> None:
        tagged = _indi(
            xref="@I8@",
            birth_year=2000,
            death_year=2020,
            death_date="3 FEB 2020",
            burial_date="",
            living_marker="_NLIV",
        )
        out = format_json(
            _result(individuals=[tagged]),
            redact_living=True,
        )
        data = json.loads(out)
        assert data["individuals"][0]["given_name"] == "John"


# ---------------------------------------------------------------------------
# Marriage data redaction
# ---------------------------------------------------------------------------


def _living(xref: str) -> ExportIndividual:
    return _indi(
        xref=xref,
        birth_year=2000,
        death_year=None,
        death_date="",
        burial_date="",
    )


def _deceased(xref: str) -> ExportIndividual:
    return _indi(xref=xref, birth_year=1850, death_year=1920, death_date="ABT 1920")


def _fam_csv_marriage(
    individuals: list[ExportIndividual], fam: ExportFamily
) -> tuple[str, str, str]:
    """Return (marriage_date, marriage_year, marriage_place) from a families CSV."""
    out = format_csv(
        _result(individuals=individuals, families=[fam]),
        table="families",
        include_bom=False,
        redact_living=True,
    )
    row = list(csv.reader(io.StringIO(out)))[1]
    return row[5], row[6], row[7]


def _fam_json_marriage(
    individuals: list[ExportIndividual], fam: ExportFamily
) -> dict[str, Any]:
    out = format_json(
        _result(individuals=individuals, families=[fam]),
        redact_living=True,
    )
    fam_data: dict[str, Any] = json.loads(out)["families"][0]
    return fam_data


class TestMarriageRedaction:
    """A wedding date and named venue re-identify a couple both of whose names
    were redacted, so either spouse being living blanks the marriage columns."""

    def test_csv_blanks_marriage_when_both_spouses_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        assert _fam_csv_marriage([_living("@I1@"), _living("@I2@")], fam) == (
            "",
            "",
            "",
        )

    def test_csv_blanks_marriage_when_only_husband_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        assert _fam_csv_marriage([_living("@I1@"), _deceased("@I2@")], fam) == (
            "",
            "",
            "",
        )

    def test_csv_blanks_marriage_when_only_wife_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        assert _fam_csv_marriage([_deceased("@I1@"), _living("@I2@")], fam) == (
            "",
            "",
            "",
        )

    def test_csv_keeps_marriage_when_neither_spouse_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        assert _fam_csv_marriage([_deceased("@I1@"), _deceased("@I2@")], fam) == (
            "3 JUN 1875",
            "1875",
            "St. Mary's Church, London",
        )

    def test_csv_keeps_marriage_when_only_a_child_is_living(self) -> None:
        # Redacting a child does not make the parents' wedding identifying.
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@", children_xrefs=["@I3@"])
        individuals = [_deceased("@I1@"), _deceased("@I2@"), _living("@I3@")]
        assert _fam_csv_marriage(individuals, fam) == (
            "3 JUN 1875",
            "1875",
            "St. Mary's Church, London",
        )

    def test_json_blanks_marriage_when_both_spouses_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        fam_data = _fam_json_marriage([_living("@I1@"), _living("@I2@")], fam)
        assert fam_data["marriage_date"] == ""
        assert fam_data["marriage_year"] is None
        assert fam_data["marriage_place"] == ""

    def test_json_blanks_marriage_when_only_husband_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        fam_data = _fam_json_marriage([_living("@I1@"), _deceased("@I2@")], fam)
        assert fam_data["marriage_date"] == ""
        assert fam_data["marriage_year"] is None
        assert fam_data["marriage_place"] == ""

    def test_json_blanks_marriage_when_only_wife_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        fam_data = _fam_json_marriage([_deceased("@I1@"), _living("@I2@")], fam)
        assert fam_data["marriage_date"] == ""
        assert fam_data["marriage_year"] is None
        assert fam_data["marriage_place"] == ""

    def test_json_keeps_marriage_when_neither_spouse_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        fam_data = _fam_json_marriage([_deceased("@I1@"), _deceased("@I2@")], fam)
        assert fam_data["marriage_date"] == "3 JUN 1875"
        assert fam_data["marriage_year"] == 1875
        assert fam_data["marriage_place"] == "St. Mary's Church, London"

    def test_marriage_survives_without_redact_living(self) -> None:
        fam = _fam(husband_xref="@I1@", wife_xref="@I2@")
        out = format_json(_result(individuals=[_living("@I1@")], families=[fam]))
        assert json.loads(out)["families"][0]["marriage_date"] == "3 JUN 1875"

    def test_family_with_no_spouse_xrefs_keeps_marriage(self) -> None:
        # An empty husband/wife xref must not be matched against living_xrefs.
        fam = _fam(husband_xref="", wife_xref="", husband_name="", wife_name="")
        fam_data = _fam_json_marriage([_living("@I9@")], fam)
        assert fam_data["marriage_date"] == "3 JUN 1875"


# ---------------------------------------------------------------------------
# JSON redaction metadata
# ---------------------------------------------------------------------------


class TestRedactionMetadata:
    def test_count_matches_redacted_individuals(self) -> None:
        individuals = [
            _living("@I1@"),
            _living("@I2@"),
            _deceased("@I3@"),
            _deceased("@I4@"),
            _deceased("@I5@"),
        ]
        data = json.loads(format_json(_result(individuals), redact_living=True))
        redacted = [i for i in data["individuals"] if i["given_name"] == "Living"]
        assert data["meta"]["redacted_count"] == 2
        assert data["meta"]["redacted_count"] == len(redacted)
        assert data["meta"]["redacted_living"] is True

    def test_count_is_zero_without_redact_living(self) -> None:
        data = json.loads(format_json(_result([_living("@I1@"), _deceased("@I2@")])))
        assert data["meta"]["redacted_count"] == 0
        assert data["meta"]["redacted_living"] is False

    def test_count_is_zero_when_nobody_is_living(self) -> None:
        data = json.loads(
            format_json(_result([_deceased("@I1@")]), redact_living=True),
        )
        assert data["meta"]["redacted_count"] == 0
        assert data["meta"]["redacted_living"] is True


# ---------------------------------------------------------------------------
# CSV formula injection
# ---------------------------------------------------------------------------


INJECTION_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME {name}
1 SEX M
0 TRLR
"""


def _export_csv(tmp_path: Path, name: str, table: str = "individuals") -> list[str]:
    """Run a real export over a GEDCOM whose NAME carries an injection payload."""
    ged = tmp_path / "inject.ged"
    ged.write_text(INJECTION_GED.format(name=name), encoding="utf-8")
    out_file = tmp_path / "out.csv"
    args = argparse.Namespace(
        file=ged,
        table=table,
        no_bom=True,
        output=out_file,
        force=True,
        redact_living=False,
        max_age=110,
        quiet=True,
        verbose=False,
        no_color=True,
    )
    assert run(args) == EXIT_SUCCESS
    rows = list(csv.reader(io.StringIO(out_file.read_text(encoding="utf-8"))))
    return rows[1]


class TestCsvSafe:
    @pytest.mark.parametrize("trigger", ["=", "+", "-", "@", "\t", "\r"])
    def test_every_trigger_is_prefixed(self, trigger: str) -> None:
        assert _csv_safe(f"{trigger}cmd") == f"'{trigger}cmd"

    def test_empty_string_survives(self) -> None:
        # Redacted rows are mostly empty cells; value[0] would raise on them.
        assert _csv_safe("") == ""

    def test_bare_minus_is_prefixed(self) -> None:
        assert _csv_safe("-") == "'-"

    def test_bare_at_is_prefixed(self) -> None:
        assert _csv_safe("@") == "'@"

    def test_ordinary_text_untouched(self) -> None:
        assert _csv_safe("Smith") == "Smith"

    def test_trigger_away_from_start_untouched(self) -> None:
        assert _csv_safe("Jean-Luc") == "Jean-Luc"

    def test_already_prefixed_value_gains_nothing(self) -> None:
        assert _csv_safe("'=cmd") == "'=cmd"


class TestCsvInjectionFormatters:
    def test_dde_payload_in_given_name_is_neutralised(self) -> None:
        indi = _indi(given_name="=cmd|' /C calc'!A0")
        rows = list(
            csv.reader(io.StringIO(format_csv(_result([indi]), include_bom=False)))
        )
        assert rows[1][1] == "'=cmd|' /C calc'!A0"

    def test_place_and_occupation_are_neutralised(self) -> None:
        indi = _indi(birth_place="+HYPERLINK(1)", occupations=["@SUM(1+1)"])
        rows = list(
            csv.reader(io.StringIO(format_csv(_result([indi]), include_bom=False)))
        )
        assert rows[1][7] == "'+HYPERLINK(1)"
        assert rows[1][13] == "'@SUM(1+1)"

    def test_dates_are_neutralised(self) -> None:
        indi = _indi(birth_date="-1+1", death_date="=2", burial_date="@3")
        rows = list(
            csv.reader(io.StringIO(format_csv(_result([indi]), include_bom=False)))
        )
        assert rows[1][5] == "'-1+1"
        assert rows[1][8] == "'=2"
        assert rows[1][11] == "'@3"

    def test_numeric_columns_keep_their_value(self) -> None:
        indi = _indi(birth_year=1850, death_year=1920, source_count=3)
        rows = list(
            csv.reader(io.StringIO(format_csv(_result([indi]), include_bom=False)))
        )
        assert rows[1][6] == "1850"
        assert rows[1][9] == "1920"
        assert rows[1][14] == "3"

    def test_xref_columns_keep_their_at_signs(self) -> None:
        rows = list(csv.reader(io.StringIO(format_csv(_result(), include_bom=False))))
        assert rows[1][0] == "@I1@"
        assert rows[1][15] == "@F5@"
        assert rows[1][16] == "@F1@;@F7@"

    def test_ordinary_row_is_not_rewritten(self) -> None:
        rows = list(csv.reader(io.StringIO(format_csv(_result(), include_bom=False))))
        assert rows[1][1] == "John"
        assert rows[1][2] == "Smith"
        assert rows[1][7] == "London, England"

    def test_family_names_and_place_are_neutralised(self) -> None:
        fam = _fam(
            husband_name="=cmd|' /C calc'!A0",
            wife_name="-2+3",
            marriage_date="+1",
            marriage_place="@Rome",
        )
        out = format_csv(_result(families=[fam]), table="families", include_bom=False)
        row = list(csv.reader(io.StringIO(out)))[1]
        assert row[2] == "'=cmd|' /C calc'!A0"
        assert row[4] == "'-2+3"
        assert row[5] == "'+1"
        assert row[7] == "'@Rome"

    def test_family_xrefs_and_counts_unchanged(self) -> None:
        out = format_csv(_result(), table="families", include_bom=False)
        row = list(csv.reader(io.StringIO(out)))[1]
        assert row[0] == "@F1@"
        assert row[1] == "@I1@"
        assert row[3] == "@I2@"
        assert row[6] == "1875"
        assert row[8] == "2"
        assert row[9] == "@I3@;@I4@"

    def test_redacted_spouse_name_still_defused(self) -> None:
        living = _indi(
            xref="@I2@",
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        fam = _fam(husband_name="=cmd", wife_xref="@I2@", wife_name="=evil")
        out = format_csv(
            _result(individuals=[living], families=[fam]),
            table="families",
            include_bom=False,
            redact_living=True,
        )
        row = list(csv.reader(io.StringIO(out)))[1]
        assert row[2] == "'=cmd"  # husband is dead, payload defused
        assert row[3] == ""  # wife xref redacted
        assert row[4] == "Living"  # wife payload replaced outright

    def test_json_output_keeps_the_raw_value(self) -> None:
        # The apostrophe is a CSV-only concession; JSON consumers see the truth.
        indi = _indi(given_name="=cmd|' /C calc'!A0")
        data = json.loads(format_json(_result([indi])))
        assert data["individuals"][0]["given_name"] == "=cmd|' /C calc'!A0"


class TestRedactedRowInjection:
    def _redacted_row(
        self,
        given_name: str = "Alice",
        sex: str = "M",
        birth_place: str = "London",
    ) -> list[str]:
        living = _indi(
            xref="@I9@",
            given_name=given_name,
            sex=sex,
            birth_place=birth_place,
            birth_year=2000,
            death_year=None,
            death_date="",
            burial_date="",
        )
        out = format_csv(
            _result(individuals=[living]), include_bom=False, redact_living=True
        )
        return list(csv.reader(io.StringIO(out)))[1]

    def test_empty_cells_do_not_crash(self) -> None:
        # Eleven of these cells are empty; an unguarded value[0] would raise.
        row = self._redacted_row()
        assert row[1] == "Living"
        assert row[2:4] == ["", ""]
        assert row[4] == "M"
        assert row[5:14] == [""] * 9

    def test_direct_call_on_bare_individual(self) -> None:
        indi = ExportIndividual(xref="@I1@", given_name="", surname="", sex="")
        assert _redact_individual_csv(indi) == [
            "@I1@",
            "Living",
            *[""] * 12,
            "0",
            "",
            "",
        ]

    def test_sex_field_is_neutralised(self) -> None:
        row = self._redacted_row(sex="=cmd")
        assert row[4] == "'=cmd"

    def test_payload_fields_are_dropped_entirely(self) -> None:
        row = self._redacted_row(given_name="=cmd", birth_place="@evil")
        assert row[1] == "Living"
        assert row[7] == ""


class TestCsvInjectionEndToEnd:
    # TAB is eaten by ged4py as the tag/value delimiter and CR aborts the parse,
    # so only these four payloads can actually reach a cell.
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ("=cmd|calc!A0", "'=cmd|calc!A0"),
            ("+cmd", "'+cmd"),
            ("-1+1", "'-1+1"),
            ("@SUM(1)", "'@SUM(1)"),
        ],
    )
    def test_trigger_leading_a_name(
        self, tmp_path: Path, payload: str, expected: str
    ) -> None:
        row = _export_csv(tmp_path, f"{payload} /Smith/")
        assert row[1] == expected

    def test_full_dde_payload(self, tmp_path: Path) -> None:
        # The slashes in " /C calc" make ged4py split the name, so only the
        # head of the payload lands in given_name — it still has to be defused.
        row = _export_csv(tmp_path, "=cmd|' /C calc'!A0 /Smith/")
        assert row[1].startswith("'=")

    def test_ordinary_name_exports_verbatim(self, tmp_path: Path) -> None:
        row = _export_csv(tmp_path, "John /Smith/")
        assert row[1] == "John"
        assert row[2] == "Smith"


# ---------------------------------------------------------------------------
# CSV/JSON redaction parity
# ---------------------------------------------------------------------------


def _undo_csv_safe(cell: str) -> str:
    """Invert _csv_safe so a cell can be compared with the value JSON carries.

    Only an apostrophe that guards a trigger character is stripped, so a name
    that genuinely begins with one survives.
    """
    if len(cell) > 1 and cell[0] == "'" and cell[1] in _CSV_TRIGGERS:
        return cell[1:]
    return cell


def _canon(cell: str, value: Any) -> tuple[Any, Any]:
    """Put one CSV cell and its JSON counterpart on the same footing.

    CSV carries strings only: None arrives as "", ints as digits, lists as a
    ";"-joined run (occupations join on "; ", hence the strip). Empty entries
    inside a list are kept -- a redacted child is a blank slot, not a missing
    one, and dropping it would hide a length mismatch.
    """
    if isinstance(value, list):
        parts = [item.strip() for item in cell.split(";")] if cell else []
        return parts, [str(item).strip() for item in value]
    return cell, "" if value is None else str(value)


def _diff_columns(
    csv_row: dict[str, str], json_row: dict[str, Any], columns: list[str]
) -> dict[str, tuple[Any, Any]]:
    diffs = {}
    for column in columns:
        from_csv, from_json = _canon(_undo_csv_safe(csv_row[column]), json_row[column])
        if from_csv != from_json:
            diffs[column] = (from_csv, from_json)
    return diffs


def _parity_tree() -> tuple[list[ExportIndividual], list[ExportFamily]]:
    """A tree that puts both redacted and untouched rows through both writers.

    @F1@ has a living husband and a living child, so it exercises every mask
    the family writers apply. @F2@ is entirely deceased and carries formula
    payloads, so the untouched path and the _csv_safe guard are covered too.
    """
    payload_spouse = _indi(
        xref="@I5@",
        birth_place="+HYPERLINK(1)",
        occupations=["Blacksmith", "@Farmer"],
    )
    individuals = [
        _living("@I1@"),
        _deceased("@I2@"),
        _living("@I3@"),
        _deceased("@I4@"),
        payload_spouse,
        _deceased("@I6@"),
    ]
    families = [
        _fam(
            xref="@F1@",
            husband_xref="@I1@",
            wife_xref="@I2@",
            children_xrefs=["@I3@", "@I4@"],
        ),
        _fam(
            xref="@F2@",
            husband_xref="@I5@",
            husband_name="=cmd",
            wife_xref="@I6@",
            wife_name="-2+3",
            marriage_place="@Rome",
            children_xrefs=[],
        ),
    ]
    return individuals, families


def _parity_export() -> tuple[list[dict[str, str]], list[dict[str, str]], Any]:
    """Export one tree three ways with redaction on.

    CSV rows come back keyed by the column constants the formatter itself
    writes, so a new column joins the comparison without touching this file.
    """
    individuals, families = _parity_tree()
    result = _result(individuals=individuals, families=families)
    indi_csv = format_csv(result, include_bom=False, redact_living=True)
    fam_csv = format_csv(
        result, table="families", include_bom=False, redact_living=True
    )
    data = json.loads(format_json(result, redact_living=True))
    indi_rows = list(csv.reader(io.StringIO(indi_csv)))[1:]
    fam_rows = list(csv.reader(io.StringIO(fam_csv)))[1:]
    return (
        [dict(zip(_INDI_CSV_COLUMNS, row, strict=True)) for row in indi_rows],
        [dict(zip(_FAM_CSV_COLUMNS, row, strict=True)) for row in fam_rows],
        data,
    )


class TestRedactionParity:
    """The family masking block is duplicated verbatim between the CSV and the
    JSON writer, and each writer recomputes living_xrefs for itself. Nothing is
    shared, so a redaction rule added to one writer and not the other would
    leak on the format nobody re-checked. These tests compare the two outputs
    field by field instead of extracting a helper.

    The individual paths are a different shape and are compared only on their
    common columns -- see test_individual_json_carries_two_extra_keys.
    """

    def test_undo_csv_safe_inverts_the_guard(self) -> None:
        # If this drifts, every comparison below turns into a false mismatch.
        for value in ["=cmd", "-1+1", "@Rome", "+1", "Smith", "", "O'Brien"]:
            assert _undo_csv_safe(_csv_safe(value)) == value

    def test_family_column_sets_are_identical(self) -> None:
        _, _, data = _parity_export()
        for fam in data["families"]:
            assert set(fam) == set(_FAM_CSV_COLUMNS)

    def test_family_masking_agrees_across_formats(self) -> None:
        _, fam_rows, data = _parity_export()
        assert len(fam_rows) == len(data["families"])
        for csv_row, json_row in zip(fam_rows, data["families"], strict=True):
            diffs = _diff_columns(csv_row, json_row, _FAM_CSV_COLUMNS)
            assert not diffs, f"{json_row['xref']} (csv, json): {diffs}"

    def test_individual_masking_agrees_on_shared_columns(self) -> None:
        indi_rows, _, data = _parity_export()
        assert len(indi_rows) == len(data["individuals"])
        for csv_row, json_row in zip(indi_rows, data["individuals"], strict=True):
            diffs = _diff_columns(csv_row, json_row, _INDI_CSV_COLUMNS)
            assert not diffs, f"{json_row['xref']} (csv, json): {diffs}"

    def test_individual_json_carries_two_extra_keys(self) -> None:
        # The individual writers genuinely diverge: _redact_individual_csv
        # builds positional cells, _individual_to_dict(redacted=True) returns
        # these two on top of them because CSV has no column to put them in.
        # A third extra key means a field was added to one writer only, which
        # is the leak this whole class exists to catch -- decide deliberately
        # whether CSV needs it before widening this set.
        _, _, data = _parity_export()
        for indi in data["individuals"]:
            assert set(indi) - set(_INDI_CSV_COLUMNS) == {"alt_names", "notes"}
