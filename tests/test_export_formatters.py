from __future__ import annotations

import csv
import io
import json

from gedcom_tools.commands.export.formatters import format_csv, format_json
from gedcom_tools.commands.export.models import (
    ExportFamily,
    ExportIndividual,
    ExportResult,
)


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

    def test_no_dates_not_redacted(self) -> None:
        """Individual with no dates at all is not redacted (not inferred as living)."""
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
        assert ind["given_name"] == "John"  # not redacted

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

    def test_nliv_tag_prevents_redaction(self) -> None:
        """Individual with _NLIV tag is not redacted even with recent birth."""
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
        assert ind["given_name"] == "John"  # not redacted
