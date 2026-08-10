from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path

import pytest

from gedcom_tools.commands.export import run
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_GED = FIXTURES / "555sample.ged"


def _write_ged(path: Path, content: str) -> Path:
    gedcom = path / "test.ged"
    gedcom.write_text(content, encoding="utf-8")
    return gedcom


def _make_args(
    file_path: Path,
    fmt: str = "text",
    to: str | None = None,
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
    # Both flags use argparse.SUPPRESS, so they are absent unless given.
    if fmt != "text":
        ns.format = fmt
    if to is not None:
        ns.to = to
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
        out_file.write_text("old data", encoding="utf-8")
        code = run(_make_args(ged, output=out_file))
        assert code == EXIT_ERROR
        err = capsys.readouterr().err
        assert "already exists" in err
        assert out_file.read_text(encoding="utf-8") == "old data"

    def test_force_overwrite(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "existing.csv"
        out_file.write_text("old data", encoding="utf-8")
        code = run(_make_args(ged, output=out_file, force=True))
        assert code == EXIT_SUCCESS
        content = out_file.read_text(encoding="utf-8")
        assert "xref" in content

    def test_output_onto_input_leaves_source_intact(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # --force must not let the export clobber the genealogy file it reads.
        ged = _write_ged(tmp_path, MINIMAL_GED)
        original = ged.read_bytes()
        code = run(_make_args(ged, output=ged, force=True))
        assert code == EXIT_ERROR
        assert ged.read_bytes() == original
        err = capsys.readouterr().err
        assert "resolves to the input file" in err
        assert "Export always produces a new file." in err
        assert "Error: Error:" not in err

    def test_output_onto_input_via_relative_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Same file reached by a different spelling still has to be caught.
        ged = _write_ged(tmp_path, MINIMAL_GED)
        original = ged.read_bytes()
        monkeypatch.chdir(tmp_path)
        code = run(_make_args(ged, output=Path("test.ged"), force=True))
        assert code == EXIT_ERROR
        assert ged.read_bytes() == original

    def test_missing_output_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        missing_dir = tmp_path / "nope"
        code = run(_make_args(ged, output=missing_dir / "out.csv"))
        assert code == EXIT_ERROR
        err = capsys.readouterr().err
        assert f"Error: Directory {missing_dir} does not exist" in err


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


MIXED_GED = """\
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
0 @I2@ INDI
1 NAME Bob /Modern/
1 SEX M
1 BIRT
2 DATE 2015
0 @I3@ INDI
1 NAME Old /Timer/
1 SEX M
1 BIRT
2 DATE 1890
1 DEAT
2 DATE 1960
0 TRLR
"""


class TestMaxAgeValidation:
    def test_zero_is_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # max_age 0 puts every dated individual past the plausible-lifespan
        # ceiling, disabling redaction while the metadata still claims it ran.
        ged = _write_ged(tmp_path, MIXED_GED)
        code = run(_make_args(ged, redact_living=True, max_age=0))
        assert code == EXIT_USAGE_ERROR
        assert "--max-age" in capsys.readouterr().err

    def test_negative_is_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MIXED_GED)
        assert run(_make_args(ged, max_age=-5)) == EXIT_USAGE_ERROR
        assert "--max-age" in capsys.readouterr().err

    def test_one_is_accepted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MIXED_GED)
        code = run(_make_args(ged, redact_living=True, max_age=1))
        assert code == EXIT_SUCCESS
        assert capsys.readouterr().out.startswith("xref,")

    def test_rejection_happens_before_the_file_is_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Nothing should be written to stdout when the option is refused.
        ged = _write_ged(tmp_path, MIXED_GED)
        assert run(_make_args(ged, redact_living=True, max_age=0)) == EXIT_USAGE_ERROR
        assert capsys.readouterr().out == ""


class TestRedactedCount:
    def test_count_matches_redacted_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MIXED_GED)
        code = run(_make_args(ged, to="json", redact_living=True))
        assert code == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        redacted = [i for i in data["individuals"] if i["given_name"] == "Living"]
        assert {i["xref"] for i in redacted} == {"@I1@", "@I2@"}
        assert data["meta"]["redacted_count"] == 2
        assert data["meta"]["redacted_living"] is True

    def test_count_is_zero_without_the_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MIXED_GED)
        code = run(_make_args(ged, to="json"))
        assert code == EXIT_SUCCESS
        meta = json.loads(capsys.readouterr().out)["meta"]
        assert meta["redacted_count"] == 0
        assert meta["redacted_living"] is False


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


posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="O_NOFOLLOW and file modes are POSIX-only guarantees",
)


class TestOutputPermissions:
    @posix_only
    def test_output_file_has_restrictive_permissions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Three separate claims: the descriptor was opened the strict way, the
        # bytes went through that descriptor, and nothing loosened it after.
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "out.csv"

        opens: list[tuple[int, int]] = []
        real_open = os.open

        def recording_open(path, flags, mode=0o777, **kwargs):  # type: ignore[no-untyped-def]
            if Path(path) == out_file:
                opens.append((flags, mode))
            return real_open(path, flags, mode, **kwargs)

        monkeypatch.setattr(os, "open", recording_open)
        monkeypatch.setattr(
            os, "chmod", lambda *a, **kw: pytest.fail("os.chmod was called")
        )

        code = run(_make_args(ged, output=out_file))

        assert code == EXIT_SUCCESS
        assert len(opens) == 1
        flags, mode = opens[0]
        assert flags & os.O_EXCL
        assert flags & os.O_NOFOLLOW
        assert mode == 0o600
        assert out_file.stat().st_mode & 0o777 == 0o600
        assert "xref" in out_file.read_text(encoding="utf-8")

    @posix_only
    def test_force_overwrite_still_lands_at_0600(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        out_file = tmp_path / "out.csv"
        out_file.write_text("old data", encoding="utf-8")
        out_file.chmod(0o644)
        code = run(_make_args(ged, output=out_file, force=True))
        assert code == EXIT_SUCCESS
        assert out_file.stat().st_mode & 0o777 == 0o600
        assert "xref" in out_file.read_text(encoding="utf-8")


class TestSymlinkOutput:
    @posix_only
    def test_dangling_symlink_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Path.exists() is False for a dangling link, so the pre-flight check
        # waves it through and the write is the only thing left to stop it.
        ged = _write_ged(tmp_path, MINIMAL_GED)
        target = tmp_path / "elsewhere" / "stolen.csv"
        target.parent.mkdir()
        link = tmp_path / "out.csv"
        link.symlink_to(target)

        code = run(_make_args(ged, output=link))

        assert code == EXIT_ERROR
        assert not target.exists()
        err = capsys.readouterr().err
        assert "Error: Output path is a symlink; refusing to follow it." in err

    @posix_only
    def test_symlink_is_refused_with_force_too(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        victim = tmp_path / "important.txt"
        victim.write_text("someone else's file", encoding="utf-8")
        victim.chmod(0o644)
        link = tmp_path / "out.csv"
        link.symlink_to(victim)

        code = run(_make_args(ged, output=link, force=True))

        assert code == EXIT_ERROR
        assert victim.read_text(encoding="utf-8") == "someone else's file"
        assert victim.stat().st_mode & 0o777 == 0o644
        err = capsys.readouterr().err
        assert "Error: Output path is a symlink; refusing to follow it." in err
        # "Use --force" would be advice that cannot work.
        assert "already exists" not in err

    def test_devnull_output_still_works(self, tmp_path: Path) -> None:
        # A character device is not creatable or truncatable; refusing it would
        # break a discard invocation that works today.
        ged = _write_ged(tmp_path, MINIMAL_GED)
        code = run(_make_args(ged, output=Path(os.devnull), force=True))
        assert code == EXIT_SUCCESS


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


class TestFormatResolution:
    """`--to` is the real flag; `--format` stays as a hidden alias."""

    def test_to_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        assert main(["export", "--to", "json", str(ged)]) == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert len(data["individuals"]) == 2

    def test_subparser_format_json_still_works(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        assert main(["export", "--format", "json", str(ged)]) == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert len(data["individuals"]) == 2

    def test_global_format_json_honoured(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        assert main(["--format", "json", "export", str(ged)]) == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert len(data["individuals"]) == 2

    def test_to_wins_over_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        code = main(["export", "--format", "json", "--to", "csv", str(ged)])
        assert code == EXIT_SUCCESS
        out = capsys.readouterr().out
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0][0] == "xref"

    def test_run_level_to_overrides_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = _write_ged(tmp_path, MINIMAL_GED)
        assert run(_make_args(ged, fmt="json", to="csv")) == EXIT_SUCCESS
        rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
        assert rows[0][0] == "xref"

    def test_global_text_means_csv(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        assert main(["--format", "text", "export", str(ged)]) == EXIT_SUCCESS
        rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
        assert rows[0][0] == "xref"

    def test_subparser_format_text_accepted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The alias used to reject "text" with a usage error, naming an option
        # --help does not even show.
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        assert main(["export", str(ged), "--format", "text"]) == EXIT_SUCCESS
        rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
        assert rows[0][0] == "xref"

    def test_format_text_matches_format_csv(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)

        assert main(["export", str(ged), "--format", "csv"]) == EXIT_SUCCESS
        as_csv = capsys.readouterr().out

        assert main(["export", str(ged), "--format", "text"]) == EXIT_SUCCESS
        assert capsys.readouterr().out == as_csv

    def test_both_format_positions_land_on_csv(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Global and alias positions share one Namespace slot; the fold in run()
        # is what makes them agree.
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)

        assert main(["--format", "text", "export", str(ged)]) == EXIT_SUCCESS
        global_position = capsys.readouterr().out

        assert main(["export", str(ged), "--format", "text"]) == EXIT_SUCCESS
        assert capsys.readouterr().out == global_position

    def test_to_still_rejects_text(self, tmp_path: Path) -> None:
        # --to is the visible option and text is not an export format; only the
        # hidden alias tolerates it.
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, MINIMAL_GED)
        with pytest.raises(SystemExit) as exc:
            main(["export", str(ged), "--to", "text"])
        assert exc.value.code == 2
