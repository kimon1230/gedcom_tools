from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from gedcom_tools.commands.filter import run
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.utils import BOMS

MINIMAL_GED = (
    "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
    "0 @I1@ INDI\n1 NAME John /Smith/\n1 SOUR @S1@\n2 PAGE 42\n1 NOTE @N1@\n"
    "0 @I2@ INDI\n1 NAME Jane /Doe/\n1 _CUSTOM value\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
    "0 @S1@ SOUR\n1 TITL Birth Certificate\n"
    "0 @N1@ NOTE This is a note\n"
    "0 TRLR\n"
)

FIXTURES = Path(__file__).parent / "fixtures"


def _write_ged(path: Path, content: str = MINIMAL_GED) -> Path:
    ged = path / "test.ged"
    ged.write_text(content, encoding="utf-8")
    return ged


def _make_args(file_path: Path, output: Path, **kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "file": file_path,
        "output": output,
        "force": False,
        "dry_run": False,
        "strip_custom_tags": False,
        "strip_notes": False,
        "strip_sources": False,
        "strip_multimedia": False,
        "strip_tag": [],
        "verbose": False,
        "quiet": False,
        "no_color": True,
        "format": "text",
        "subtree": None,
        "ancestors": None,
        "descendants": 0,
        "include_spouses": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# TestFilterStripCustomTags
# ---------------------------------------------------------------------------


class TestFilterStripCustomTags:
    def test_removes_custom_tags(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_custom_tags=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        for line in content.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                tag = parts[2] if parts[1].startswith("@") else parts[1]
                assert not tag.startswith("_"), f"Custom tag not removed: {line}"

    def test_custom_tags_with_children_removed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Test\n1 _PRIV Y\n2 _PRIVCHILD data\n1 SEX M\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_custom_tags=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "_PRIV" not in content
        assert "_PRIVCHILD" not in content
        assert "1 SEX M" in content


# ---------------------------------------------------------------------------
# TestFilterStripNotes
# ---------------------------------------------------------------------------


class TestFilterStripNotes:
    def test_removes_note_records_and_inline_refs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # Top-level NOTE record removed
        assert "0 @N1@ NOTE" not in content
        # Inline NOTE reference removed from INDI
        assert "NOTE @N1@" not in content
        # Other records preserved
        assert "John /Smith/" in content
        assert "0 @S1@ SOUR" in content

    def test_dangling_note_pointers_cleaned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # NOTE record removed, then dangling pointer lines to it get cleaned
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "@N1@" not in content


# ---------------------------------------------------------------------------
# TestFilterStripSources
# ---------------------------------------------------------------------------


class TestFilterStripSources:
    def test_removes_sour_records_and_citations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_sources=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "0 @S1@ SOUR" not in content
        # Inline SOUR + its PAGE child removed
        assert "SOUR @S1@" not in content
        assert "PAGE 42" not in content

    def test_dangling_source_pointers_cleaned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_sources=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "@S1@" not in content


# ---------------------------------------------------------------------------
# TestFilterStripMultimedia
# ---------------------------------------------------------------------------


class TestFilterStripMultimedia:
    def test_removes_obje_records(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Test\n1 OBJE @O1@\n"
            "0 @O1@ OBJE\n1 FILE photo.jpg\n2 FORM JPEG\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "0 @O1@ OBJE" not in content
        assert "OBJE @O1@" not in content
        assert "1 NAME Test" in content


# ---------------------------------------------------------------------------
# TestFilterStripTag
# ---------------------------------------------------------------------------


class TestFilterStripTag:
    def test_strips_specified_tag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_tag=["NAME"]))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        for line in content.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                tag = parts[2] if parts[1].startswith("@") else parts[1]
                assert tag != "NAME", f"NAME tag not stripped: {line}"

    def test_lowercase_input_uppercased(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_tag=["name"]))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # NAME lines should be gone even though user typed "name"
        assert "1 NAME" not in content


# ---------------------------------------------------------------------------
# TestFilterCombined
# ---------------------------------------------------------------------------


class TestFilterCombined:
    def test_notes_and_custom_tags(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True, strip_custom_tags=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "NOTE" not in content
        assert "_CUSTOM" not in content
        assert "John /Smith/" in content

    def test_sources_and_multimedia(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Test\n1 SOUR @S1@\n1 OBJE @O1@\n"
            "0 @S1@ SOUR\n1 TITL Book\n"
            "0 @O1@ OBJE\n1 FILE pic.jpg\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_sources=True, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "@S1@" not in content
        assert "@O1@" not in content
        assert "1 NAME Test" in content


# ---------------------------------------------------------------------------
# TestFilterDryRun
# ---------------------------------------------------------------------------


class TestFilterDryRun:
    def test_no_output_file_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, dry_run=True, strip_notes=True))
        assert code == EXIT_SUCCESS
        assert not out.exists()

    def test_result_text_contains_dry_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, dry_run=True, strip_notes=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "dry run" in captured.out

    def test_dry_run_quiet_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, dry_run=True, strip_notes=True, quiet=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "(dry run)" in captured.out


# ---------------------------------------------------------------------------
# TestFilterForce
# ---------------------------------------------------------------------------


class TestFilterForce:
    def test_overwrites_existing_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        out.write_text("existing content", encoding="utf-8")
        code = run(_make_args(src, out, force=True, strip_notes=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "existing content" not in content
        assert "John /Smith/" in content


# ---------------------------------------------------------------------------
# TestFilterErrors
# ---------------------------------------------------------------------------


class TestFilterErrors:
    def test_no_filters_specified(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "At least one filter option is required" in captured.err

    def test_same_file_protection(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        code = run(_make_args(src, src, force=True, strip_notes=True))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "resolves to the input" in captured.err

    def test_output_nonexistent_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "nonexistent_dir" / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_missing_input_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "nonexistent.ged"
        out = tmp_path / "out.ged"
        code = run(_make_args(missing, out, strip_notes=True))
        assert code == EXIT_USAGE_ERROR

    def test_no_head_or_trlr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = "0 @I1@ INDI\n1 NAME Test\n"
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "missing HEAD or TRLR" in captured.err

    def test_overwrite_protection(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        out.write_text("existing", encoding="utf-8")
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "already exists" in captured.err


# ---------------------------------------------------------------------------
# TestFilterRoundTrip
# ---------------------------------------------------------------------------


class TestFilterRoundTrip:
    def test_no_matching_tags_byte_identical(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # strip_multimedia but file has no OBJE -> output identical
        ged = "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Test\n0 TRLR\n"
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        assert src.read_bytes() == out.read_bytes()

    def test_crlf_preserved(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = (
            "0 HEAD\r\n1 SOUR TEST\r\n1 CHAR UTF-8\r\n"
            "0 @I1@ INDI\r\n1 NAME Test\r\n"
            "0 TRLR\r\n"
        )
        src = tmp_path / "crlf.ged"
        src.write_bytes(ged.encode("utf-8"))
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        raw = out.read_bytes()
        assert b"\r\n" in raw

    def test_bom_preserved(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Test\n0 TRLR\n"
        src = tmp_path / "bom.ged"
        src.write_bytes(BOMS["utf-8"] + ged.encode("utf-8"))
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        raw = out.read_bytes()
        assert raw[:3] == BOMS["utf-8"]

    def test_utf8_stays_utf8(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Ren\u00e9\n0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "Ren\u00e9" in content


# ---------------------------------------------------------------------------
# TestFilterJsonOutput
# ---------------------------------------------------------------------------


class TestFilterJsonOutput:
    def test_json_structure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True, format="json"))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "source_file" in data
        assert "output_file" in data
        assert "source" in data
        assert "output" in data
        assert "removed" in data
        assert "dry_run" in data
        assert "gedcom_tools_version" in data
        assert data["removed"]["notes"] >= 1

    def test_json_dry_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True, format="json", dry_run=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["dry_run"] is True


# ---------------------------------------------------------------------------
# TestFilterQuietMode
# ---------------------------------------------------------------------------


class TestFilterQuietMode:
    def test_quiet_single_line_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True, quiet=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        text = captured.out.strip()
        assert text.count("\n") == 0
        assert "Filtered" in text


# ---------------------------------------------------------------------------
# TestFilter555Sample
# ---------------------------------------------------------------------------


class TestFilter555Sample:
    def test_strip_sources_from_555sample(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = FIXTURES / "555sample.ged"
        if not src.exists():
            pytest.skip("555sample.ged not found")
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_sources=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # File should still parse (HEAD and TRLR present)
        assert "0 HEAD" in content
        assert "0 TRLR" in content
        # Source records should be gone
        for line in content.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1].startswith("@") and parts[2] == "SOUR":
                pytest.fail(f"SOUR record not removed: {line}")

    def test_strip_sources_record_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = FIXTURES / "555sample.ged"
        if not src.exists():
            pytest.skip("555sample.ged not found")
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_sources=True, format="json"))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["source"]["sources"] >= 1
        assert data["removed"]["sources"] >= 1
        assert data["output"]["sources"] == 0


# ---------------------------------------------------------------------------
# TestFilterEmptyFamilyCascade
# ---------------------------------------------------------------------------


class TestFilterEmptyFamilyCascade:
    def test_empty_family_removed_and_dangling_cleaned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Stripping HUSB+WIFE+CHIL via strip_tag empties the family,
        # which triggers cascade removal and dangling pointer cleanup
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME John\n1 FAMS @F1@\n"
            "0 @I2@ INDI\n1 NAME Jane\n1 FAMS @F1@\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 MARR\n2 DATE 1 JAN 1900\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        # Strip HUSB and WIFE tags - family becomes empty (no HUSB/WIFE/CHIL left)
        code = run(_make_args(src, out, strip_tag=["HUSB", "WIFE"]))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # FAM record should be gone (emptied)
        assert "0 @F1@ FAM" not in content
        # FAMS references to removed FAM should be cleaned
        assert "FAMS @F1@" not in content

    def test_cascade_counts_in_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME John\n1 FAMS @F1@\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 MARR\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_tag=["HUSB"], format="json"))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["empty_families_removed"] >= 1
        assert data["dangling_lines_removed"] >= 1


# ---------------------------------------------------------------------------
# TestFilterEncodings
# ---------------------------------------------------------------------------


class TestFilterEncodings:
    def test_bom_roundtrip(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged_text = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n" "0 @I1@ INDI\n1 NAME Test\n0 TRLR\n"
        )
        bom = BOMS["utf-8"]
        src = tmp_path / "bom.ged"
        src.write_bytes(bom + ged_text.encode("utf-8"))
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_multimedia=True))
        assert code == EXIT_SUCCESS
        raw = out.read_bytes()
        assert raw[:3] == bom
        # Content after BOM should decode cleanly
        content = raw[3:].decode("utf-8")
        assert "0 HEAD" in content

    def test_crlf_roundtrip(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ged_text = (
            "0 HEAD\r\n1 SOUR TEST\r\n1 CHAR UTF-8\r\n"
            "0 @I1@ INDI\r\n1 NAME Test\r\n1 _CUSTOM data\r\n"
            "0 TRLR\r\n"
        )
        src = tmp_path / "crlf.ged"
        src.write_bytes(ged_text.encode("utf-8"))
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_custom_tags=True))
        assert code == EXIT_SUCCESS
        raw = out.read_bytes()
        text = raw.decode("utf-8")
        # All line endings should be CRLF
        lines = text.split("\r\n")
        # Last element is empty string after final CRLF
        assert lines[-1] == ""
        # No bare LF (every \n should be preceded by \r)
        assert "\n" not in text.replace("\r\n", "")


# ---------------------------------------------------------------------------
# TestFilterTextOutput
# ---------------------------------------------------------------------------


class TestFilterTextOutput:
    def test_text_includes_file_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "File:" in captured.out

    def test_text_includes_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Filter Results" in captured.out

    def test_text_includes_record_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_notes=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Individuals" in captured.out
        assert "Notes" in captured.out
        assert "Output" in captured.out

    def test_dangling_count_displayed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Strip INDI records; FAM's HUSB/WIFE pointers become dangling.
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME John\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 MARR\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, strip_tag=["INDI"]))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Dangling references cleaned" in captured.out


# ---------------------------------------------------------------------------
# Subtree GEDCOM fixtures
# ---------------------------------------------------------------------------

# Family tree:
#   @I4@ (Grandfather) + @I5@ (Grandmother) -> @I2@ (Father), @I7@ (Uncle)
#   @I2@ (Father) + @I3@ (Mother) -> @I1@ (Child), @I6@ (Sibling)
#   @I1@ (Child) + @I8@ (Spouse) -> @I9@ (ChildOfChild)
SUBTREE_GED = (
    "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
    "0 @I1@ INDI\n1 NAME Child /Smith/\n1 FAMC @F1@\n1 FAMS @F3@\n"
    "0 @I2@ INDI\n1 NAME Father /Smith/\n1 FAMS @F1@\n1 FAMC @F2@\n"
    "0 @I3@ INDI\n1 NAME Mother /Jones/\n1 FAMS @F1@\n"
    "0 @I4@ INDI\n1 NAME Grandfather /Smith/\n1 FAMS @F2@\n"
    "0 @I5@ INDI\n1 NAME Grandmother /Brown/\n1 FAMS @F2@\n"
    "0 @I6@ INDI\n1 NAME Sibling /Smith/\n1 FAMC @F1@\n"
    "0 @I7@ INDI\n1 NAME Uncle /Smith/\n1 FAMC @F2@\n"
    "0 @I8@ INDI\n1 NAME Spouse /Wilson/\n1 FAMS @F3@\n"
    "0 @I9@ INDI\n1 NAME ChildOfChild /Smith/\n1 FAMC @F3@\n"
    "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I3@\n1 CHIL @I1@\n1 CHIL @I6@\n"
    "0 @F2@ FAM\n1 HUSB @I4@\n1 WIFE @I5@\n1 CHIL @I2@\n1 CHIL @I7@\n"
    "0 @F3@ FAM\n1 HUSB @I1@\n1 WIFE @I8@\n1 CHIL @I9@\n"
    "0 @S1@ SOUR\n1 TITL Birth Certificate\n"
    "0 @N1@ NOTE A family note\n"
    "0 TRLR\n"
)

SUBTREE_WITH_DEPS_GED = (
    "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
    "0 @I1@ INDI\n1 NAME Test /Person/\n1 SOUR @S1@\n"
    "0 @I2@ INDI\n1 NAME Other /Person/\n"
    "0 @S1@ SOUR\n1 TITL Certificate\n1 REPO @R1@\n"
    "0 @R1@ REPO\n1 NAME Archive\n"
    "0 @S2@ SOUR\n1 TITL Unused Source\n"
    "0 TRLR\n"
)


def _xrefs_in_output(content: str) -> set[str]:
    """Extract all level-0 xrefs from output GEDCOM text."""
    xrefs: set[str] = set()
    for line in content.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "0" and parts[1].startswith("@"):
            xrefs.add(parts[1])
    return xrefs


# ---------------------------------------------------------------------------
# TestFilterSubtree
# ---------------------------------------------------------------------------


class TestFilterSubtree:
    def test_subtree_root_only(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Extract just @I1@ with no ancestors/descendants."""
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", ancestors=0))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        xrefs = _xrefs_in_output(content)
        assert "@I1@" in xrefs
        # No ancestors or descendants
        assert "@I2@" not in xrefs
        assert "@I9@" not in xrefs
        # HEAD/TRLR preserved
        assert "0 HEAD" in content
        assert "0 TRLR" in content

    def test_subtree_with_ancestors_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Extract @I1@ with 1 generation of ancestors (parents only)."""
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", ancestors=1))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        xrefs = _xrefs_in_output(content)
        # Root + parents
        assert "@I1@" in xrefs
        assert "@I2@" in xrefs
        assert "@I3@" in xrefs
        # Grandparents not included (depth 1)
        assert "@I4@" not in xrefs
        assert "@I5@" not in xrefs

    def test_subtree_with_descendants_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Extract @I1@ with 1 generation of descendants."""
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", ancestors=0, descendants=1))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        xrefs = _xrefs_in_output(content)
        assert "@I1@" in xrefs
        assert "@I9@" in xrefs
        # No ancestors
        assert "@I2@" not in xrefs

    def test_subtree_with_include_spouses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Extract @I1@ ancestors=0 with spouses included."""
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(
            _make_args(src, out, subtree="@I1@", ancestors=0, include_spouses=True)
        )
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        xrefs = _xrefs_in_output(content)
        assert "@I1@" in xrefs
        assert "@I8@" in xrefs  # spouse of @I1@
        # Parents not included (ancestors=0)
        assert "@I2@" not in xrefs

    def test_subtree_combined_with_strip(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Subtree extraction + strip-custom-tags applied together."""
        ged = (
            "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
            "0 @I1@ INDI\n1 NAME Test /Person/\n1 _PRIV Y\n"
            "0 @I2@ INDI\n1 NAME Other /Person/\n1 _PRIV N\n"
            "0 TRLR\n"
        )
        src = _write_ged(tmp_path, ged)
        out = tmp_path / "out.ged"
        code = run(
            _make_args(src, out, subtree="@I1@", ancestors=0, strip_custom_tags=True)
        )
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        xrefs = _xrefs_in_output(content)
        assert "@I1@" in xrefs
        assert "@I2@" not in xrefs
        # Custom tags stripped from kept records
        assert "_PRIV" not in content

    def test_subtree_keeps_dependent_sour(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Subtree keeps SOUR records referenced by kept individuals."""
        src = _write_ged(tmp_path, SUBTREE_WITH_DEPS_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", ancestors=0))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        xrefs = _xrefs_in_output(content)
        assert "@I1@" in xrefs
        # @S1@ referenced by @I1@
        assert "@S1@" in xrefs
        # @R1@ referenced transitively by @S1@
        assert "@R1@" in xrefs
        # @I2@ and @S2@ not kept
        assert "@I2@" not in xrefs
        assert "@S2@" not in xrefs

    def test_subtree_preserves_head_trlr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """HEAD and TRLR always preserved in subtree output."""
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", ancestors=0))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "0 HEAD" in content
        assert "0 TRLR" in content


# ---------------------------------------------------------------------------
# TestFilterSubtreeErrors
# ---------------------------------------------------------------------------


class TestFilterSubtreeErrors:
    def test_ancestors_without_subtree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, ancestors=2))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "--ancestors requires --subtree" in captured.err

    def test_descendants_without_subtree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, descendants=1))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "--descendants requires --subtree" in captured.err

    def test_include_spouses_without_subtree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, include_spouses=True))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "--include-spouses requires --subtree" in captured.err

    def test_invalid_xref_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="I1"))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "Invalid xref format" in captured.err

    def test_nonexistent_xref(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        # Valid xref format but individual doesn't exist in file
        with pytest.raises(ValueError, match="not found in file"):
            run(_make_args(src, out, subtree="@I999@"))

    def test_negative_ancestors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", ancestors=-1))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "--ancestors must be non-negative" in captured.err

    def test_negative_descendants(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path, SUBTREE_GED)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, out, subtree="@I1@", descendants=-1))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "--descendants must be non-negative" in captured.err


# ---------------------------------------------------------------------------
# TestFilterSubtree555Sample
# ---------------------------------------------------------------------------


class TestFilterSubtree555Sample:
    def test_subtree_on_known_individual(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = FIXTURES / "555sample.ged"
        if not src.exists():
            pytest.skip("555sample.ged not found")
        out = tmp_path / "out.ged"
        # @I1@ is the first individual in 555sample.ged
        code = run(_make_args(src, out, subtree="@I1@", ancestors=1, format="json"))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # Output must have structural integrity
        assert "0 HEAD" in content
        assert "0 TRLR" in content
        # Should have fewer records than the full file
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["output"]["total"] < data["source"]["total"]
