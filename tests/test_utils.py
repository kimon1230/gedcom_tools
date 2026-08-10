from __future__ import annotations

import codecs
import errno
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ged4py.parser import CodecError

from gedcom_tools import utils
from gedcom_tools.constants import EXIT_ERROR, EXIT_USAGE_ERROR
from gedcom_tools.utils import (
    _CHAR_SCAN_WINDOW,
    count_sources_recursive,
    detect_encoding,
    extract_xref,
    parse_name_record,
    validate_input_file,
    write_output_securely,
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

    def test_unknown_charset_raises_without_bom(self, tmp_path: Path) -> None:
        # The BOM-conflict raise above is covered; this is the other arm, where
        # the codec name alone is unresolvable.
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR NOSUCHTHING\n0 TRLR\n", encoding="utf-8")
        with pytest.raises(CodecError, match="NOSUCHTHING"):
            detect_encoding(ged)

    def test_extra_whitespace_around_char(self, tmp_path: Path) -> None:
        # Behaviour change: this used to yield ' ANSEL', leading space and all,
        # which then flowed into the encoding field and into JSON output.
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1  CHAR  ANSEL\n0 TRLR\n", encoding="utf-8")
        info = detect_encoding(ged)
        assert info.declared_charset == "ANSEL"
        assert info.encoding == "ANSEL"

    def test_trailing_whitespace_stripped(self, tmp_path: Path) -> None:
        # Behaviour change: previously 'ANSEL   '.
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR ANSEL   \n0 TRLR\n", encoding="utf-8")
        assert detect_encoding(ged).declared_charset == "ANSEL"

    def test_tab_separated_after_blank_line(self, tmp_path: Path) -> None:
        # Behaviour change: this raised ParserError before.
        ged = tmp_path / "test.ged"
        ged.write_text("\n0 HEAD\n1\tCHAR\tANSEL\n0 TRLR\n", encoding="utf-8")
        assert detect_encoding(ged).declared_charset == "ANSEL"

    def test_junk_line_before_head(self, tmp_path: Path) -> None:
        # Behaviour change: this raised ParserError before. A stray first line is
        # no reason to refuse to read a perfectly good CHAR record.
        ged = tmp_path / "test.ged"
        ged.write_text("hello world\n0 HEAD\n1 CHAR ANSEL\n0 TRLR\n", encoding="utf-8")
        assert detect_encoding(ged).declared_charset == "ANSEL"

    def test_lowercase_char_tag_ignored(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 char ANSEL\n0 TRLR\n", encoding="utf-8")
        assert detect_encoding(ged).declared_charset is None

    def test_valueless_char_line_ignored(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n1 CHAR\n0 TRLR\n", encoding="utf-8")
        assert detect_encoding(ged).declared_charset is None

    def test_char_in_a_later_record_not_picked_up(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_text("0 HEAD\n0 @I1@ INDI\n1 CHAR ANSEL\n0 TRLR\n", encoding="utf-8")
        assert detect_encoding(ged).declared_charset is None

    def test_multibyte_character_at_the_window_boundary(self, tmp_path: Path) -> None:
        # Decoding the whole probe buffer would raise UnicodeDecodeError here.
        # The scan only decodes the extracted charset value, so it cannot.
        window = _CHAR_SCAN_WINDOW
        head = b"0 HEAD\n"
        while len(head) < window - 1:
            head += b"1 NOTE " + b"x" * 60 + b"\n"
        ged = tmp_path / "test.ged"
        ged.write_bytes(head[: window - 1] + "é".encode() + b"\n1 CHAR UTF-8\n0 TRLR\n")
        assert detect_encoding(ged).encoding == "UTF-8"

    def test_declared_ascii_with_non_ascii_body_byte(self, tmp_path: Path) -> None:
        # A file that lies about its own codec still resolves; guess_codec never
        # decodes body bytes and neither do we.
        ged = tmp_path / "test.ged"
        ged.write_bytes(
            b"0 HEAD\n1 CHAR ASCII\n0 @I1@ INDI\n1 NAME M\xfcller\n0 TRLR\n"
        )
        assert detect_encoding(ged).declared_charset == "ASCII"

    def test_cr_only_line_terminators(self, tmp_path: Path) -> None:
        ged = tmp_path / "test.ged"
        ged.write_bytes(b"0 HEAD\r1 CHAR ANSEL\r0 TRLR\r")
        assert detect_encoding(ged).declared_charset == "ANSEL"

    def test_char_straddling_the_scan_window(self, tmp_path: Path) -> None:
        """A `1 CHAR ANSEL` split across the 64 KB cut must not become 'ANS'.

        This one file exercises both halves of the bounded scan: the partial-line
        drop, without which the truncated match wins, and the reconciliation that
        hands the file to the reader once the window runs out mid-header.
        """
        ged = _straddling_char_file(tmp_path / "padded.ged")
        info = detect_encoding(ged)
        assert info.declared_charset == "ANSEL"
        assert info.encoding == "ANSEL"


def _straddling_char_file(path: Path) -> Path:
    """Pad a HEAD so `1 CHAR ANSEL` spans the scan window, cut mid-value.

    The last complete bytes before the cut are `1 CHAR ANS` -- enough to satisfy
    the three-token match, and wrong.
    """
    window = _CHAR_SCAN_WINDOW
    start = window - len(b"1 CHAR ANS")
    head = b"0 HEAD\n"
    filler = b"1 NOTE " + b"p" * 60 + b"\n"
    while len(head) + len(filler) <= start:
        head += filler
    head += b"1 NOTE " + b"q" * (start - len(head) - 8) + b"\n"
    assert len(head) == start, "padding arithmetic drifted"
    data = head + b"1 CHAR ANSEL\n0 TRLR\n"
    assert data[:window].rsplit(b"\n", 1)[-1] == b"1 CHAR ANS"
    path.write_bytes(data)
    return path


class TestDetectEncodingPathTaken:
    """Which implementation served the request, not just what it returned.

    Every other case here passes identically under the bounded scan or the
    reader, so a fast path that always raised would revert the speedup with a
    green suite.
    """

    @pytest.mark.parametrize(
        "name,data,expected",
        [
            ("utf8", b"0 HEAD\n1 CHAR UTF-8\n0 TRLR\n", "UTF-8"),
            ("ansel", b"0 HEAD\n1 CHAR ANSEL\n0 TRLR\n", "ANSEL"),
            ("no_char", b"0 HEAD\n0 TRLR\n", None),
            # CR-only guards the BinaryFileCR wrapper specifically: drop it and a
            # plain handle sends this file to the reader.
            ("cr_only", b"0 HEAD\r1 CHAR ANSEL\r0 TRLR\r", "ANSEL"),
        ],
    )
    def test_reader_is_never_constructed(
        self, tmp_path: Path, name: str, data: bytes, expected: str | None
    ) -> None:
        ged = tmp_path / f"{name}.ged"
        ged.write_bytes(data)

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("GedcomReader was constructed on the fast path")

        with patch("gedcom_tools.utils.GedcomReader", explode):
            info = detect_encoding(ged)

        assert info.declared_charset == expected

    def test_charless_header_in_a_big_file_stays_on_the_fast_path(
        self, tmp_path: Path
    ) -> None:
        """A file with no `1 CHAR` must not pay for a full lex just to say so.

        The window fills up on any file past 64 KB, and without the
        end-of-header check that alone is taken as "the CHAR line might be
        further in" -- sending every such file to the reader, which is the
        cost the bounded scan exists to avoid.
        """
        ged = tmp_path / "no_char.ged"
        body = ["0 HEAD", "1 SOUR Test", "0 @I1@ INDI", "1 NAME A /X/"]
        while sum(len(line) + 1 for line in body) <= _CHAR_SCAN_WINDOW:
            n = len(body)
            body.append(f"0 @I{n}@ INDI")
            body.append(f"1 NAME Padding{n} /Filler/")
        body.append("0 TRLR")
        ged.write_bytes(("\n".join(body) + "\n").encode("utf-8"))
        assert ged.stat().st_size >= _CHAR_SCAN_WINDOW
        assert b"1 CHAR" not in ged.read_bytes()

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("GedcomReader was constructed on the fast path")

        with patch("gedcom_tools.utils.GedcomReader", explode):
            info = detect_encoding(ged)

        assert info.declared_charset is None

    def test_fallback_is_reachable(self, tmp_path: Path) -> None:
        ged = _straddling_char_file(tmp_path / "padded.ged")
        real = utils.GedcomReader
        calls: list[str] = []

        def counting(path: str, *args: object, **kwargs: object) -> object:
            calls.append(path)
            return real(path, *args, **kwargs)

        with patch("gedcom_tools.utils.GedcomReader", counting):
            info = detect_encoding(ged)

        assert calls == [str(ged)]
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
        command: str = "Filter",
    ) -> str | None:
        from gedcom_tools.utils import check_output_safety

        return check_output_safety(
            input_path, output_path, force=force, dry_run=dry_run, command=command
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

    def test_message_names_the_calling_command(self, tmp_path: Path) -> None:
        inp = tmp_path / "file.ged"
        inp.write_text("data", encoding="utf-8")
        result = self._check(inp, inp, command="Convert")
        assert result is not None
        assert "Convert always produces a new file." in result
        assert "Filter" not in result

    def test_command_name_in_resolve_fallback(self, tmp_path: Path) -> None:
        # samefile() raises FileNotFoundError when the path does not exist,
        # so this drives the resolve() branch rather than the stat comparison.
        missing = tmp_path / "not-created-yet.ged"
        result = self._check(missing, missing, command="Convert")
        assert result is not None
        assert "Convert always produces a new file." in result


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

    def test_del_stripped(self) -> None:
        assert self._sanitize("a\x7fb") == "ab"

    def test_c1_csi_introducer_stripped(self) -> None:
        # U+009B is the 8-bit form of ESC[. A function whose job is removing
        # escape introducers that let this one through was the whole defect.
        assert self._sanitize("boom \x9b[2J bad") == "boom [2J bad"

    def test_c1_upper_boundary_stripped(self) -> None:
        assert self._sanitize("a\x9fb") == "ab"

    def test_nbsp_preserved(self) -> None:
        # The upper boundary matters: widening one further eats NBSP, which is
        # ordinary text, and nothing else would notice.
        assert self._sanitize("a\xa0b") == "a\xa0b"

    def test_latin_extended_preserved(self) -> None:
        assert self._sanitize("a\u0100b") == "a\u0100b"

    def test_newline_deliberately_preserved(self) -> None:
        # Not an oversight -- stripping \x0a would mangle every legitimately
        # multi-line message to stop a low-value forged-"Error:" spoof.
        assert self._sanitize("line1\nline2") == "line1\nline2"

    def test_combined_threats(self) -> None:
        msg = "\x1b[31m\x00bad\u202epath\u200e"
        result = self._sanitize(msg)
        assert result == "badpath"
        assert "\x1b" not in result
        assert "\x00" not in result
        assert "\u202e" not in result
        assert "\u200e" not in result


class TestReportError:
    def _report(self, e: Exception, capsys) -> str:
        from gedcom_tools.utils import report_error

        report_error(e)
        return capsys.readouterr().err

    def test_names_the_exception_type(self, capsys) -> None:
        err = self._report(ValueError("bad year"), capsys)
        assert err.splitlines()[0] == "Error: ValueError: bad year"

    def test_key_error_repr_is_still_readable(self, capsys) -> None:
        # str(KeyError) quotes the key, so a bare "Error: 'x'" would be useless.
        err = self._report(KeyError("indi_count"), capsys)
        assert err.splitlines()[0] == "Error: KeyError: 'indi_count'"

    def test_verbose_hint_follows(self, capsys) -> None:
        err = self._report(RuntimeError("nope"), capsys)
        assert err.splitlines()[1] == "Re-run with --verbose for a full traceback."

    def test_message_is_sanitized(self, capsys) -> None:
        err = self._report(ValueError("\x1b[31mred\x00\u202eflip"), capsys)
        assert err.splitlines()[0] == "Error: ValueError: redflip"

    def test_empty_message(self, capsys) -> None:
        err = self._report(RuntimeError(), capsys)
        assert err.splitlines()[0] == "Error: RuntimeError: "

    def test_nothing_goes_to_stdout(self, capsys) -> None:
        from gedcom_tools.utils import report_error

        report_error(ValueError("boom"))
        assert capsys.readouterr().out == ""


posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="O_NOFOLLOW and file modes are POSIX-only guarantees",
)


def _spy_on_os_open(
    monkeypatch: pytest.MonkeyPatch, target: Path
) -> list[tuple[int, int]]:
    """Record (flags, mode) for every os.open of `target`."""
    calls: list[tuple[int, int]] = []
    real_open = os.open

    def recording_open(path, flags, mode=0o777, **kwargs):  # type: ignore[no-untyped-def]
        if Path(path) == target:
            calls.append((flags, mode))
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)
    return calls


class TestWriteOutputSecurely:
    def test_writes_bytes(self, tmp_path: Path) -> None:
        out = tmp_path / "out.ged"
        assert write_output_securely(out, b"0 HEAD\n", force=False) is None
        assert out.read_bytes() == b"0 HEAD\n"

    def test_writes_text_in_the_given_encoding(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        assert write_output_securely(out, "Ångström", force=False) is None
        assert out.read_text(encoding="utf-8") == "Ångström"

    def test_non_utf8_encoding_is_honoured(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_output_securely(out, "café", force=False, encoding="latin-1")
        assert out.read_bytes() == b"caf\xe9"

    def test_existing_file_without_force_is_refused(self, tmp_path: Path) -> None:
        out = tmp_path / "out.ged"
        out.write_text("keep me", encoding="utf-8")
        result = write_output_securely(out, b"new", force=False)
        assert result is not None
        assert "already exists" in result
        assert "--force" in result
        assert out.read_text(encoding="utf-8") == "keep me"

    @pytest.mark.parametrize("force", [False, True])
    def test_directory_target_is_refused_with_actionable_advice(
        self, tmp_path: Path, force: bool
    ) -> None:
        # A directory also raises EEXIST under O_EXCL, so it would otherwise
        # be reported as "use --force" - advice that leads straight to an
        # unhandled EISDIR. Both spellings must say the same true thing.
        out = tmp_path / "somedir"
        out.mkdir()
        result = write_output_securely(out, b"new", force=force)
        assert result is not None
        assert "is a directory" in result
        assert "--force" not in result
        assert out.is_dir()

    def test_force_overwrites_a_regular_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.ged"
        out.write_text("stale and much longer than the replacement", encoding="utf-8")
        assert write_output_securely(out, b"new", force=True) is None
        assert out.read_bytes() == b"new"

    def test_unexpected_oserror_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Anything that is not "exists" or "is a symlink" is a real failure and
        # must not be flattened into a returned message.
        out = tmp_path / "out.ged"

        def failing_open(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError(errno.EIO, "disk fell over")

        monkeypatch.setattr(os, "open", failing_open)
        with pytest.raises(OSError, match="disk fell over"):
            write_output_securely(out, b"data", force=False)

    def test_non_regular_target_is_written_through(self, tmp_path: Path) -> None:
        # /dev/null cannot be created, truncated or chmod-ed; the atomic path
        # would refuse it, so it takes the plain one.
        devnull = Path(os.devnull)
        assert write_output_securely(devnull, b"data", force=False) is None

    @posix_only
    def test_non_regular_target_accepts_text_too(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            assert write_output_securely(fifo, "hello", force=False) is None
            assert os.read(reader, 16) == b"hello"
        finally:
            os.close(reader)

    @posix_only
    def test_dangling_symlink_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "elsewhere" / "stolen.csv"
        target.parent.mkdir()
        link = tmp_path / "out.csv"
        link.symlink_to(target)

        result = write_output_securely(link, b"private data", force=False)

        assert result == "Error: Output path is a symlink; refusing to follow it."
        assert not target.exists()

    @posix_only
    def test_symlink_with_force_is_refused_too(self, tmp_path: Path) -> None:
        victim = tmp_path / "important.txt"
        victim.write_text("someone else's file", encoding="utf-8")
        victim.chmod(0o644)
        link = tmp_path / "out.ged"
        link.symlink_to(victim)

        result = write_output_securely(link, b"private data", force=True)

        # Deliberately not the "use --force" message: --force is not the answer.
        assert result == "Error: Output path is a symlink; refusing to follow it."
        assert victim.read_text(encoding="utf-8") == "someone else's file"
        assert victim.stat().st_mode & 0o777 == 0o644

    @posix_only
    def test_created_file_is_owner_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out.ged"
        calls = _spy_on_os_open(monkeypatch, out)
        monkeypatch.setattr(
            os, "chmod", lambda *a, **kw: pytest.fail("os.chmod widened the window")
        )

        assert write_output_securely(out, b"private data", force=False) is None

        assert len(calls) == 1
        flags, mode = calls[0]
        assert flags & os.O_EXCL
        assert flags & os.O_NOFOLLOW
        assert not flags & os.O_TRUNC
        assert mode == 0o600
        assert out.stat().st_mode & 0o777 == 0o600
        assert out.read_bytes() == b"private data"

    @posix_only
    def test_force_reopens_with_truncate_and_tightens_the_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # O_TRUNC keeps whatever mode the file already had, so a loose one has
        # to be tightened through the descriptor.
        out = tmp_path / "out.ged"
        out.write_text("world readable", encoding="utf-8")
        out.chmod(0o644)
        calls = _spy_on_os_open(monkeypatch, out)

        assert write_output_securely(out, b"private data", force=True) is None

        flags, mode = calls[0]
        assert flags & os.O_TRUNC
        assert not flags & os.O_EXCL
        assert flags & os.O_NOFOLLOW
        assert out.stat().st_mode & 0o777 == 0o600

    def test_flag_lookup_survives_a_platform_without_o_nofollow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Windows has no O_NOFOLLOW; the getattr fallbacks are what keep the
        # CI matrix from raising AttributeError on every file-output run.
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
        out = tmp_path / "out.ged"
        assert write_output_securely(out, b"data", force=False) is None
        assert out.read_bytes() == b"data"

    @posix_only
    def test_symlink_to_a_fifo_is_refused(self, tmp_path: Path) -> None:
        # A link is not a device, however much stat() insists otherwise. Reader
        # held open so a write-through would succeed rather than block — the
        # test has to fail loudly if the guard ever regresses.
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        link = tmp_path / "out.csv"
        link.symlink_to(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            result = write_output_securely(link, "leaked", force=False)

            assert result == "Error: Output path is a symlink; refusing to follow it."
            # No writer ever opened the pipe, so the non-blocking read reports
            # EOF rather than data.
            assert os.read(reader, 16) == b""
        finally:
            os.close(reader)

    @posix_only
    def test_symlink_to_a_regular_file_is_refused(self, tmp_path: Path) -> None:
        victim = tmp_path / "important.csv"
        victim.write_text("someone else's file", encoding="utf-8")
        link = tmp_path / "out.csv"
        link.symlink_to(victim)

        result = write_output_securely(link, "leaked", force=False)

        assert result == "Error: Output path is a symlink; refusing to follow it."
        assert victim.read_text(encoding="utf-8") == "someone else's file"

    def test_character_device_still_takes_the_fast_path(self) -> None:
        # /dev/null is the real thing, not a link to it, so the lstat gate has
        # to let it through.
        assert write_output_securely(Path(os.devnull), "data", force=False) is None

    @posix_only
    def test_real_fifo_still_takes_the_fast_path(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            assert write_output_securely(fifo, b"through", force=False) is None
            assert os.read(reader, 16) == b"through"
        finally:
            os.close(reader)


class TestWriteOutputSecurelyNewlines:
    # These assert on-disk bytes because the bug they pin is invisible to
    # csv.reader: newline=None makes TextIOWrapper expand \n to os.linesep, so
    # csv.writer's own \r\n reaches a Windows disk as \r\r\n and reads back as a
    # blank row between every real one. POSIX linesep is already \n, so these
    # pass either way here — their job is to hold the line on Windows.
    ROWS = "id,name\r\nI1,Smith\r\n"

    def test_crlf_is_not_expanded(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_output_securely(out, self.ROWS, force=False)
        raw = out.read_bytes()
        assert b"\r\r\n" not in raw
        assert raw == b"id,name\r\nI1,Smith\r\n"

    def test_bare_lf_stays_bare(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        write_output_securely(out, "one\ntwo\n", force=False)
        raw = out.read_bytes()
        assert b"\r\n" not in raw
        assert raw == b"one\ntwo\n"

    def test_force_overwrite_does_not_translate_either(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        out.write_text("stale", encoding="utf-8")
        write_output_securely(out, self.ROWS, force=True)
        assert out.read_bytes() == b"id,name\r\nI1,Smith\r\n"

    @posix_only
    def test_fast_path_crlf_is_not_expanded(self, tmp_path: Path) -> None:
        # Path.write_text has the same newline=None default, so the FIFO branch
        # needs its own proof.
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            write_output_securely(fifo, self.ROWS, force=False)
            assert os.read(reader, 64) == b"id,name\r\nI1,Smith\r\n"
        finally:
            os.close(reader)

    @posix_only
    def test_fast_path_bare_lf_stays_bare(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            write_output_securely(fifo, "one\ntwo\n", force=False)
            assert os.read(reader, 64) == b"one\ntwo\n"
        finally:
            os.close(reader)


# codecs.lookup resolves byte-to-byte transforms too, so --from base64 used to
# pass validation and then die inside the decode with a LookupError nobody can
# act on. These live here rather than next to TestResolveSourceCodec in
# test_convert.py because the predicate being guarded is a utils-level one.

NON_TEXT_CODECS = ["base64", "hex", "zlib", "rot13", "bz2", "uu", "quopri"]

TEXT_CODECS = [
    ("utf-8", "utf-8"),
    ("ascii", "ascii"),
    ("latin-1", "iso8859-1"),
    ("cp1252", "cp1252"),
    ("utf-16-le", "utf-16-le"),
    ("iso-8859-1", "iso8859-1"),
]


class TestLookupTextCodec:
    @pytest.mark.parametrize("name", NON_TEXT_CODECS)
    def test_transforms_are_not_text(self, name: str) -> None:
        assert utils._lookup_text_codec(name) is None

    def test_unregistered_name(self) -> None:
        assert utils._lookup_text_codec("not-a-codec") is None

    @pytest.mark.parametrize(("name", "canonical"), TEXT_CODECS)
    def test_text_codecs_canonicalized(self, name: str, canonical: str) -> None:
        assert utils._lookup_text_codec(name) == canonical

    def test_ansel_codec_survives(self) -> None:
        # Rejecting this would break every ANSEL file the tool handles.
        assert utils._lookup_text_codec("gedcom") == "gedcom"

    def test_codecinfo_without_the_private_flag_is_accepted(self) -> None:
        # _is_text_encoding is private, so the getattr default has to fail open.
        class Exotic:
            name = "weird-8"

        with patch("codecs.lookup", return_value=Exotic()):
            assert utils._lookup_text_codec("weird-8") == "weird-8"


class TestResolveSourceCodecRejectsNonTextCodecs:
    INFO = utils.EncodingInfo(encoding="UTF-8")

    @pytest.mark.parametrize("name", NON_TEXT_CODECS)
    def test_override_rejected(self, name: str) -> None:
        with pytest.raises(ValueError, match="Unknown source encoding"):
            utils.resolve_source_codec(self.INFO, name)

    @pytest.mark.parametrize(("name", "canonical"), TEXT_CODECS)
    def test_override_still_resolves(self, name: str, canonical: str) -> None:
        assert utils.resolve_source_codec(self.INFO, name) == canonical

    @pytest.mark.parametrize("name", ["gedcom", "ansel", "ANSEL"])
    def test_ansel_override_still_resolves(self, name: str) -> None:
        assert utils.resolve_source_codec(self.INFO, name) == "gedcom"

    @pytest.mark.parametrize("name", NON_TEXT_CODECS)
    def test_detected_charset_rejected(self, name: str) -> None:
        # A file declaring "1 CHAR zlib" gets the same treatment.
        info = utils.EncodingInfo(encoding=name)
        with pytest.raises(ValueError, match="Cannot determine source encoding"):
            utils.resolve_source_codec(info, None)

    def test_error_names_the_offending_value(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown source encoding: base64$"):
            utils.resolve_source_codec(self.INFO, "base64")


class TestAutoDeclaredCodecs:
    """The allowlist a file's own ``1 CHAR`` value is judged against."""

    @pytest.mark.parametrize("name", sorted(utils.AUTO_DECLARED_CODECS))
    def test_every_member_resolves_to_itself(self, name: str) -> None:
        # Entries are stored canonical, so the gate can compare them directly
        # against _lookup_text_codec's output. iso8859-12 is the trap here: it
        # does not exist, and only an enumerated list keeps it out.
        assert codecs.lookup(name).name == name

    @pytest.mark.parametrize("name", sorted(utils.AUTO_DECLARED_CODECS))
    def test_no_member_invents_line_breaks(self, name: str) -> None:
        # The whole point of the gate: a codec that turns some other byte into
        # \n or \r lets a NOTE value become structure once filter/convert split
        # the decoded text. cp037 does exactly that with 0x25, which is why
        # this is an allowlist and not a rule about single-byte charmaps.
        #
        # One-directional on purpose. The converse does not hold -- a lone 0x0a
        # decodes to '' under all three utf-16 entries.
        for i in range(256):
            decoded = bytes([i]).decode(name, errors="ignore")
            if "\n" in decoded or "\r" in decoded:
                assert i in (
                    0x0A,
                    0x0D,
                ), f"{name} turns byte {i:#04x} into a line break"

    @pytest.mark.parametrize("name", sorted(utils.AUTO_DECLARED_CODECS))
    def test_the_sweep_actually_decodes_something(self, name: str) -> None:
        # errors="ignore" makes it easy to assert nothing about 256 empty
        # strings. The utf-16 codecs need a second byte before they produce
        # anything at all; everything else must manage it on one.
        if any(bytes([i]).decode(name, errors="ignore") for i in range(256)):
            return
        assert any(
            bytes([i, j]).decode(name, errors="ignore")
            for i in range(256)
            for j in range(256)
        ), f"{name} decoded nothing at all -- the sweep above proved nothing"

    def test_cp037_would_fail_the_line_break_sweep(self) -> None:
        # Pins the counter-example the sweep exists to catch, so a future
        # addition of an EBCDIC page cannot pass unnoticed.
        assert bytes([0x25]).decode("cp037") == "\n"
        assert "cp037" not in utils.AUTO_DECLARED_CODECS

    def test_ansel_is_not_a_member(self) -> None:
        # SOURCE_ENCODING_MAP answers "ANSEL" long before the gate, and
        # codecs.lookup("gedcom") only works after ansel.register().
        assert "gedcom" not in utils.AUTO_DECLARED_CODECS
        assert utils.SOURCE_ENCODING_MAP["ANSEL"] == "gedcom"

    def test_iso8859_12_is_not_a_codec(self) -> None:
        with pytest.raises(LookupError):
            codecs.lookup("iso8859-12")
