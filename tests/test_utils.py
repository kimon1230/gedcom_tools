from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gedcom_tools.constants import EXIT_ERROR, EXIT_USAGE_ERROR
from gedcom_tools.utils import (
    count_sources_recursive,
    detect_encoding,
    extract_xref,
    validate_input_file,
)


class TestDetectEncoding:
    def test_utf8_no_bom(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR UTF-8\n0 TRLR\n")
        info = detect_encoding(ged)
        assert info.encoding == "UTF-8"
        assert info.has_bom is False
        assert info.declared_charset == "UTF-8"

    def test_utf8_with_bom(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_bytes(b"\xef\xbb\xbf0 HEAD\n1 CHAR UTF-8\n0 TRLR\n")
        info = detect_encoding(ged)
        assert info.encoding == "UTF-8"
        assert info.has_bom is True
        assert info.declared_charset == "UTF-8"

    def test_no_char_header(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n0 TRLR\n")
        info = detect_encoding(ged)
        assert info.encoding == "UTF-8"
        assert info.has_bom is False
        assert info.declared_charset is None

    def test_bom_with_conflicting_char_raises(self, tmp_path: Path) -> None:
        from ged4py.parser import CodecError

        ged = tmp_path / "test.ged"
        ged.write_bytes(b"\xef\xbb\xbf0 HEAD\n1 CHAR ASCII\n0 TRLR\n")
        with pytest.raises(CodecError):
            detect_encoding(ged)

    def test_declared_charset_used_when_no_bom(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR ASCII\n0 TRLR\n")
        info = detect_encoding(ged)
        assert info.encoding == "ASCII"
        assert info.has_bom is False
        assert info.declared_charset == "ASCII"

    def test_declared_charset_uppercased(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR utf-8\n0 TRLR\n")
        info = detect_encoding(ged)
        assert info.encoding == "UTF-8"

    def test_ansel_charset_detected(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR ANSEL\n0 TRLR\n")
        info = detect_encoding(ged)
        assert info.encoding == "ANSEL"
        assert info.declared_charset == "ANSEL"


class TestExtractXref:
    def test_none_input(self) -> None:
        assert extract_xref(None) is None

    def test_valid_xref_string(self) -> None:
        assert extract_xref("@I1@") == "@I1@"

    def test_xref_with_numbers(self) -> None:
        assert extract_xref("@F123@") == "@F123@"

    def test_missing_closing_at(self) -> None:
        assert extract_xref("@I1") is None

    def test_missing_opening_at(self) -> None:
        assert extract_xref("I1@") is None

    def test_empty_string(self) -> None:
        assert extract_xref("") is None

    def test_pointer_object_with_xref_id(self) -> None:
        pointer = MagicMock()
        pointer.xref_id = "@I42@"
        pointer.__str__ = lambda self: "some string"
        assert extract_xref(pointer) == "@I42@"

    def test_pointer_object_with_none_xref_id(self) -> None:
        pointer = MagicMock()
        pointer.xref_id = None
        pointer.__str__ = lambda self: "some string"
        assert extract_xref(pointer) is None

    def test_plain_string(self) -> None:
        assert extract_xref("John Doe") is None

    def test_integer_input(self) -> None:
        assert extract_xref(42) is None


class TestValidateInputFile:
    def test_valid_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.ged"
        f.write_text("content")
        assert validate_input_file(f) is None

    def test_nonexistent_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = validate_input_file(Path("/nonexistent/file.ged"))
        assert result == EXIT_USAGE_ERROR
        assert "not found" in capsys.readouterr().err.lower()

    def test_directory_instead_of_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = validate_input_file(tmp_path)
        assert result == EXIT_USAGE_ERROR
        assert "not a file" in capsys.readouterr().err.lower()

    def test_unreadable_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "noperm.ged"
        f.write_text("content")
        f.chmod(0o000)
        try:
            result = validate_input_file(f)
            assert result == EXIT_ERROR
            assert "permission denied" in capsys.readouterr().err.lower()
        finally:
            f.chmod(0o644)


class TestCountSourcesRecursive:
    def test_no_sub_records(self) -> None:
        rec = MagicMock()
        rec.sub_records = []
        assert count_sources_recursive(rec) == 0

    def test_single_sour(self) -> None:
        sour = MagicMock()
        sour.tag = "SOUR"
        sour.sub_records = []
        rec = MagicMock()
        rec.sub_records = [sour]
        assert count_sources_recursive(rec) == 1

    def test_nested_sour(self) -> None:
        inner_sour = MagicMock()
        inner_sour.tag = "SOUR"
        inner_sour.sub_records = []
        birt = MagicMock()
        birt.tag = "BIRT"
        birt.sub_records = [inner_sour]
        rec = MagicMock()
        rec.sub_records = [birt]
        assert count_sources_recursive(rec) == 1

    def test_non_sour_tags_ignored(self) -> None:
        note = MagicMock()
        note.tag = "NOTE"
        note.sub_records = []
        rec = MagicMock()
        rec.sub_records = [note]
        assert count_sources_recursive(rec) == 0
