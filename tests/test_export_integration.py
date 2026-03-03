from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

import pytest

from gedcom_tools.commands.export import run
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_GED = FIXTURES / "555sample.ged"


def _write_ged(path: Path, content: str) -> Path:
    gedcom = path / "test.ged"
    gedcom.write_text(content, encoding="utf-8")
    return gedcom


def _make_args(
    file_path: Path,
    fmt: str = "text",
    table: str = "individuals",
    no_bom: bool = False,
    output: Path | None = None,
    force: bool = False,
    redact_living: bool = False,
    max_age: int = 110,
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = True,
) -> argparse.Namespace:
    ns = argparse.Namespace(
        file=file_path,
        table=table,
        no_bom=no_bom,
        output=output,
        force=force,
        redact_living=redact_living,
        max_age=max_age,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
    )
    if fmt != "text":
        ns.format = fmt
    return ns


MINIMAL_GED = """\
0 HEAD
1 SOUR TEST
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 BIRT
2 DATE 15 JAN 1850
2 PLAC London
1 DEAT
2 DATE 1920
0 @I2@ INDI
1 NAME Mary /Jones/
1 SEX F
1 BIRT
2 DATE 1855
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 3 JUN 1875
2 PLAC St. Marys Church
0 TRLR
"""


class TestCsvStdout:
    def test_default_csv_individuals_on_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        code = run(_make_args(ged))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert not out.startswith("\ufeff")
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[0][0] == "xref"
        assert len(rows) == 3  # header + 2 individuals

    def test_families_table_on_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        code = run(_make_args(ged, table="families"))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[0][0] == "xref"
        assert rows[0][1] == "husband_xref"
        assert len(rows) == 2  # header + 1 family


class TestJsonStdout:
    def test_json_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        code = run(_make_args(ged, fmt="json"))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "meta" in data
        assert len(data["individuals"]) == 2
        assert len(data["families"]) == 1

    def test_json_ignores_table_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        code = run(_make_args(ged, fmt="json", table="families"))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data["individuals"]) == 2
        assert len(data["families"]) == 1


class TestFileOutput:
    def test_csv_to_file_has_bom(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "out.csv"
        code = run(_make_args(ged, output=out_file))
        assert code == EXIT_SUCCESS
        content = out_file.read_text(encoding="utf-8")
        assert content.startswith("\ufeff")

    def test_csv_to_file_no_bom(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "out.csv"
        code = run(_make_args(ged, output=out_file, no_bom=True))
        assert code == EXIT_SUCCESS
        content = out_file.read_text(encoding="utf-8")
        assert not content.startswith("\ufeff")

    def test_json_to_file_no_bom(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "out.json"
        code = run(_make_args(ged, fmt="json", output=out_file))
        assert code == EXIT_SUCCESS
        content = out_file.read_text(encoding="utf-8")
        assert not content.startswith("\ufeff")
        data = json.loads(content)
        assert len(data["individuals"]) == 2

    def test_overwrite_protection(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "existing.csv"
        out_file.write_text("old data")
        code = run(_make_args(ged, output=out_file))
        assert code == EXIT_ERROR
        err = capsys.readouterr().err
        assert "already exists" in err
        assert out_file.read_text() == "old data"

    def test_force_overwrite(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "existing.csv"
        out_file.write_text("old data")
        code = run(_make_args(ged, output=out_file, force=True))
        assert code == EXIT_SUCCESS
        content = out_file.read_text(encoding="utf-8")
        assert "xref" in content


class TestRedaction:
    def test_redact_living(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        living_ged = """\
0 HEAD
1 SOUR TEST
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Alice /Modern/
1 SEX F
1 BIRT
2 DATE 2000
0 TRLR
"""
        ged = _write_ged(tmp_path, living_ged)
        code = run(_make_args(ged, redact_living=True))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][1] == "Living"
        assert rows[1][2] == ""

    def test_redact_living_custom_max_age(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged_content = """\
0 HEAD
1 SOUR TEST
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Ancient /Person/
1 SEX M
1 BIRT
2 DATE 1920
0 TRLR
"""
        ged = _write_ged(tmp_path, ged_content)
        # With max_age=90, born in 1920 is > 90 years ago → not living
        code = run(_make_args(ged, redact_living=True, max_age=90))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[1][1] == "Ancient"  # not redacted


class TestFormatMapping:
    def test_global_text_maps_to_csv(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        # format="text" (global default) should map to csv
        code = run(_make_args(ged, fmt="text"))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        reader = csv.reader(io.StringIO(out))
        rows = list(reader)
        assert rows[0][0] == "xref"


class TestErrorCases:
    def test_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.ged"
        code = run(_make_args(missing))
        assert code != EXIT_SUCCESS


class TestRegression:
    def test_555sample_counts(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = run(_make_args(SAMPLE_GED, fmt="json"))
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["meta"]["individual_count"] == 3
        assert data["meta"]["family_count"] == 2
        assert len(data["individuals"]) == 3
        assert len(data["families"]) == 2
