from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gedcom_tools.constants import EXIT_ERROR, EXIT_USAGE_ERROR
from gedcom_tools.utils import (
    count_sources_recursive,
    detect_encoding,
    extract_xref,
    parse_name_record,
    validate_input_file,
)


class TestDetectEncoding:
    def test_utf8_no_bom(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR UTF-8\n0 TRLR\n", encoding="utf-8")
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
        ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
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
        ged.write_text("0 HEAD\n1 CHAR ASCII\n0 TRLR\n", encoding="utf-8")
        info = detect_encoding(ged)
        assert info.encoding == "ASCII"
        assert info.has_bom is False
        assert info.declared_charset == "ASCII"

    def test_declared_charset_uppercased(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR utf-8\n0 TRLR\n", encoding="utf-8")
        info = detect_encoding(ged)
        assert info.encoding == "UTF-8"

    def test_ansel_charset_detected(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR ANSEL\n0 TRLR\n", encoding="utf-8")
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
        f.write_text("content", encoding="utf-8")
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

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="chmod(0o000) leaves the owner read access on Windows",
    )
    def test_unreadable_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "noperm.ged"
        f.write_text("content", encoding="utf-8")
        f.chmod(0o000)
        try:
            result = validate_input_file(f)
            assert result == EXIT_ERROR
            assert "permission denied" in capsys.readouterr().err.lower()
        finally:
            f.chmod(0o644)

    def test_unreadable_file_without_chmod(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Same branch as above, minus the OS permission model.

        chmod(0o000) is a no-op for read access on Windows, so the test above
        cannot run there. This one exercises the handler everywhere.
        """
        f = tmp_path / "noperm.ged"
        f.write_text("content", encoding="utf-8")
        with patch("os.access", return_value=False):
            result = validate_input_file(f)
        assert result == EXIT_ERROR
        assert "permission denied" in capsys.readouterr().err.lower()


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


def _make_name_rec(value, sub_records=None):
    rec = MagicMock()
    rec.value = value
    rec.sub_records = sub_records or []
    return rec


class TestParseNameRecord:
    def test_normal_tuple(self) -> None:
        rec = _make_name_rec(("John William", "Smith", "Jr."))
        given, surname = parse_name_record(rec)
        assert given == "John William"
        assert surname == "Smith"

    def test_given_is_none(self) -> None:
        rec = _make_name_rec((None, "Doe", ""))
        assert parse_name_record(rec) == ("", "Doe")

    def test_surname_is_none(self) -> None:
        rec = _make_name_rec(("Maria", None, ""))
        assert parse_name_record(rec) == ("Maria", "")

    def test_both_none_in_tuple(self) -> None:
        rec = _make_name_rec((None, None, None))
        assert parse_name_record(rec) == ("", "")

    def test_givn_overrides_tuple(self) -> None:
        givn = MagicMock()
        givn.tag = "GIVN"
        givn.value = "Jonathan"
        rec = _make_name_rec(("John", "Smith", ""), sub_records=[givn])
        given, surname = parse_name_record(rec)
        assert given == "Jonathan"
        assert surname == "Smith"

    def test_surn_overrides_tuple(self) -> None:
        surn = MagicMock()
        surn.tag = "SURN"
        surn.value = "Smithson"
        rec = _make_name_rec(("John", "Smith", ""), sub_records=[surn])
        given, surname = parse_name_record(rec)
        assert given == "John"
        assert surname == "Smithson"

    def test_both_givn_and_surn_override(self) -> None:
        givn = MagicMock()
        givn.tag = "GIVN"
        givn.value = "Jonathan"
        surn = MagicMock()
        surn.tag = "SURN"
        surn.value = "Smithson"
        rec = _make_name_rec(("John", "Smith", ""), sub_records=[givn, surn])
        assert parse_name_record(rec) == ("Jonathan", "Smithson")

    def test_non_tuple_value_fallback(self) -> None:
        # some GEDCOM writers put the raw "John /Smith/" string as value
        rec = _make_name_rec("John /Smith/")
        assert parse_name_record(rec) == ("John /Smith/", "")

    def test_none_value(self) -> None:
        rec = _make_name_rec(None)
        assert parse_name_record(rec) == ("", "")

    def test_none_record(self) -> None:
        assert parse_name_record(None) == ("", "")


class TestCheckOutputSafety:
    def _check(
        self,
        input_path: Path,
        output_path: Path,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> str | None:
        from gedcom_tools.utils import check_output_safety

        return check_output_safety(
            input_path, output_path, force=force, dry_run=dry_run
        )

    def test_safe_path_returns_none(self, tmp_path: Path) -> None:
        inp = tmp_path / "input.ged"
        inp.write_text("data", encoding="utf-8")
        out = tmp_path / "output.ged"
        assert self._check(inp, out) is None

    def test_nonexistent_parent_dir(self, tmp_path: Path) -> None:
        inp = tmp_path / "input.ged"
        inp.write_text("data", encoding="utf-8")
        out = tmp_path / "nosuchdir" / "output.ged"
        result = self._check(inp, out)
        assert result is not None
        assert "does not exist" in result

    def test_same_file_blocked(self, tmp_path: Path) -> None:
        inp = tmp_path / "file.ged"
        inp.write_text("data", encoding="utf-8")
        result = self._check(inp, inp)
        assert result is not None
        assert "resolves to the input" in result

    def test_same_file_via_symlink(self, tmp_path: Path) -> None:
        inp = tmp_path / "file.ged"
        inp.write_text("data", encoding="utf-8")
        link = tmp_path / "link.ged"
        link.symlink_to(inp)
        result = self._check(inp, link)
        assert result is not None
        assert "resolves to the input" in result

    def test_existing_output_without_force(self, tmp_path: Path) -> None:
        inp = tmp_path / "input.ged"
        inp.write_text("data", encoding="utf-8")
        out = tmp_path / "output.ged"
        out.write_text("existing", encoding="utf-8")
        result = self._check(inp, out)
        assert result is not None
        assert "already exists" in result

    def test_existing_output_with_force(self, tmp_path: Path) -> None:
        inp = tmp_path / "input.ged"
        inp.write_text("data", encoding="utf-8")
        out = tmp_path / "output.ged"
        out.write_text("existing", encoding="utf-8")
        assert self._check(inp, out, force=True) is None

    def test_dry_run_skips_overwrite_check(self, tmp_path: Path) -> None:
        inp = tmp_path / "input.ged"
        inp.write_text("data", encoding="utf-8")
        out = tmp_path / "output.ged"
        out.write_text("existing", encoding="utf-8")
        assert self._check(inp, out, dry_run=True) is None

    def test_same_file_still_blocked_during_dry_run(self, tmp_path: Path) -> None:
        inp = tmp_path / "file.ged"
        inp.write_text("data", encoding="utf-8")
        result = self._check(inp, inp, dry_run=True)
        assert result is not None
        assert "resolves to the input" in result


class TestSanitizeError:
    def _sanitize(self, msg: str) -> str:
        from gedcom_tools.utils import sanitize_error

        return sanitize_error(msg)

    def test_normal_text_preserved(self) -> None:
        assert self._sanitize("File not found: test.ged") == "File not found: test.ged"

    def test_tabs_preserved(self) -> None:
        assert self._sanitize("col1\tcol2") == "col1\tcol2"

    def test_non_latin_unicode_preserved(self) -> None:
        assert self._sanitize("Ελληνικά 日本語") == "Ελληνικά 日本語"

    def test_c0_controls_stripped(self) -> None:
        assert self._sanitize("bad\x00\x01\x02text") == "badtext"

    def test_null_byte_stripped(self) -> None:
        assert self._sanitize("hello\x00world") == "helloworld"

    def test_ansi_escape_stripped(self) -> None:
        assert self._sanitize("normal\x1b[31mred\x1b[0m") == "normalred"

    def test_ansi_complex_sequence_stripped(self) -> None:
        assert self._sanitize("\x1b[1;32;40mBOLD\x1b[0m") == "BOLD"

    def test_bidi_override_stripped(self) -> None:
        assert self._sanitize("hello\u202eevil\u202c") == "helloevil"

    def test_lrm_stripped(self) -> None:
        assert self._sanitize("left\u200eright") == "leftright"

    def test_rlm_stripped(self) -> None:
        assert self._sanitize("left\u200fright") == "leftright"

    def test_alm_stripped(self) -> None:
        assert self._sanitize("text\u061cmore") == "textmore"

    def test_line_separator_stripped(self) -> None:
        assert self._sanitize("line1\u2028line2") == "line1line2"

    def test_paragraph_separator_stripped(self) -> None:
        assert self._sanitize("para1\u2029para2") == "para1para2"

    def test_lri_rli_fsi_pdi_stripped(self) -> None:
        assert self._sanitize("a\u2066b\u2067c\u2068d\u2069e") == "abcde"

    def test_empty_string(self) -> None:
        assert self._sanitize("") == ""

    def test_combined_threats(self) -> None:
        msg = "\x1b[31m\x00bad\u202epath\u200e"
        result = self._sanitize(msg)
        assert result == "badpath"
        assert "\x1b" not in result
        assert "\x00" not in result
        assert "\u202e" not in result
        assert "\u200e" not in result
