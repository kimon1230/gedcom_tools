from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

import ansel  # type: ignore[import-untyped]
import pytest

from gedcom_tools.commands.convert import run
from gedcom_tools.commands.convert.transcoder import (
    CODEC_TO_CHAR,
    ConvertResult,
    count_long_lines,
    resolve_target_codec,
    transcode,
    update_char_header,
)
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.progress import Colors
from gedcom_tools.utils import BOMS, EncodingInfo, resolve_source_codec, strip_bom

ansel.register()

MINIMAL_GED = (
    "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
    "0 @I1@ INDI\n1 NAME John /Smith/\n0 TRLR\n"
)


def _write_ged(path: Path, content: str = MINIMAL_GED) -> Path:
    ged = path / "test.ged"
    ged.write_text(content, encoding="utf-8")
    return ged


def _make_args(
    file_path: Path,
    to_encoding: str,
    output: Path,
    **kwargs: object,
) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "file": file_path,
        "to_encoding": to_encoding,
        "output": output,
        "from_encoding": None,
        "force": False,
        "bom": False,
        "no_normalize": False,
        "dry_run": False,
        "verbose": False,
        "quiet": False,
        "no_color": True,
        "format": "text",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# TestResolveSourceCodec
# ---------------------------------------------------------------------------


class TestResolveSourceCodec:
    def test_ansel_from_detect(self) -> None:
        info = EncodingInfo(encoding="ANSEL")
        assert resolve_source_codec(info, None) == "gedcom"

    def test_utf8_from_detect(self) -> None:
        info = EncodingInfo(encoding="UTF-8")
        assert resolve_source_codec(info, None) == "utf-8"

    def test_utf16le_from_detect(self) -> None:
        info = EncodingInfo(encoding="UTF-16-LE")
        assert resolve_source_codec(info, None) == "utf-16-le"

    def test_utf16be_from_detect(self) -> None:
        info = EncodingInfo(encoding="UTF-16-BE")
        assert resolve_source_codec(info, None) == "utf-16-be"

    def test_override_gedcom_name(self) -> None:
        info = EncodingInfo(encoding="UTF-8")
        assert resolve_source_codec(info, "ansel") == "gedcom"

    def test_override_python_name(self) -> None:
        info = EncodingInfo(encoding="UTF-8")
        result = resolve_source_codec(info, "latin-1")
        assert result == "iso8859-1"

    def test_override_invalid(self) -> None:
        info = EncodingInfo(encoding="UTF-8")
        with pytest.raises(ValueError, match="Unknown source encoding"):
            resolve_source_codec(info, "not-a-codec")

    def test_ascii_from_detect(self) -> None:
        info = EncodingInfo(encoding="ASCII")
        assert resolve_source_codec(info, None) == "ascii"

    def test_unicode_from_detect(self) -> None:
        info = EncodingInfo(encoding="UNICODE")
        assert resolve_source_codec(info, None) == "utf-16-le"

    def test_case_insensitive_lookup(self) -> None:
        # "Utf-8" is not in SOURCE_ENCODING_MAP, but "utf-8" is in GEDCOM_CHARSETS
        info = EncodingInfo(encoding="Utf-8")
        assert resolve_source_codec(info, None) == "utf-8"

    def test_detect_fallback_codecs_lookup(self) -> None:
        # "iso-8859-1" is not in SOURCE_ENCODING_MAP or GEDCOM_CHARSETS,
        # but codecs.lookup("iso-8859-1") succeeds.
        info = EncodingInfo(encoding="iso-8859-1")
        assert resolve_source_codec(info, None) == "iso8859-1"

    def test_detect_unknown_encoding_raises(self) -> None:
        info = EncodingInfo(encoding="BOGUS-ENCODING")
        with pytest.raises(ValueError, match="Cannot determine source encoding"):
            resolve_source_codec(info, None)


# ---------------------------------------------------------------------------
# TestResolveTargetCodec
# ---------------------------------------------------------------------------


class TestResolveTargetCodec:
    def test_utf8(self) -> None:
        assert resolve_target_codec("utf-8") == "utf-8"

    def test_ansel(self) -> None:
        assert resolve_target_codec("ansel") == "gedcom"

    def test_ascii(self) -> None:
        assert resolve_target_codec("ascii") == "ascii"

    def test_unicode(self) -> None:
        assert resolve_target_codec("unicode") == "utf-16-le"


# ---------------------------------------------------------------------------
# TestStripBom
# ---------------------------------------------------------------------------


class TestStripBom:
    def test_utf8_bom(self) -> None:
        data = b"\xef\xbb\xbfHello"
        stripped, enc = strip_bom(data)
        assert stripped == b"Hello"
        assert enc == "utf-8"

    def test_utf16le_bom(self) -> None:
        data = b"\xff\xfeH\x00e\x00"
        stripped, enc = strip_bom(data)
        assert stripped == b"H\x00e\x00"
        assert enc == "utf-16-le"

    def test_utf16be_bom(self) -> None:
        data = b"\xfe\xff\x00H\x00e"
        stripped, enc = strip_bom(data)
        assert stripped == b"\x00H\x00e"
        assert enc == "utf-16-be"

    def test_no_bom(self) -> None:
        data = b"plain text"
        stripped, enc = strip_bom(data)
        assert stripped == data
        assert enc is None

    def test_empty(self) -> None:
        stripped, enc = strip_bom(b"")
        assert stripped == b""
        assert enc is None

    def test_utf8_bom_priority(self) -> None:
        # UTF-8 BOM (3 bytes) followed by bytes that look like UTF-16-LE BOM
        data = b"\xef\xbb\xbf\xff\xfe"
        stripped, enc = strip_bom(data)
        assert stripped == b"\xff\xfe"
        assert enc == "utf-8"

    def test_returns_bom_encoding(self) -> None:
        for bom_name, bom_bytes in BOMS.items():
            _, enc = strip_bom(bom_bytes + b"data")
            assert enc == bom_name


# ---------------------------------------------------------------------------
# TestUpdateCharHeader
# ---------------------------------------------------------------------------


class TestUpdateCharHeader:
    def test_replace_existing(self) -> None:
        text = "0 HEAD\n1 CHAR UTF-8\n0 TRLR\n"
        result = update_char_header(text, "ANSEL")
        assert "1 CHAR ANSEL" in result
        assert "1 CHAR UTF-8" not in result

    def test_replace_empty_char(self) -> None:
        text = "0 HEAD\n1 CHAR\n0 TRLR\n"
        result = update_char_header(text, "UTF-8")
        assert "1 CHAR UTF-8" in result

    def test_insert_when_missing_with_subrecords(self) -> None:
        text = "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n0 @I1@ INDI\n0 TRLR\n"
        result = update_char_header(text, "UTF-8")
        assert "1 CHAR UTF-8" in result
        # CHAR should appear after HEAD line
        lines = result.split("\n")
        head_idx = next(i for i, ln in enumerate(lines) if ln.startswith("0 HEAD"))
        char_idx = next(i for i, ln in enumerate(lines) if "1 CHAR UTF-8" in ln)
        assert char_idx == head_idx + 1

    def test_insert_when_missing_no_subrecords(self) -> None:
        text = "0 HEAD\n0 @I1@ INDI\n0 TRLR\n"
        result = update_char_header(text, "UTF-8")
        assert "1 CHAR UTF-8" in result

    def test_preserves_other_lines(self) -> None:
        text = "0 HEAD\n1 SOUR TEST\n1 CHAR UTF-8\n0 @I1@ INDI\n0 TRLR\n"
        result = update_char_header(text, "ANSEL")
        assert "1 SOUR TEST" in result
        assert "0 @I1@ INDI" in result
        assert "0 TRLR" in result

    def test_crlf_line_endings(self) -> None:
        text = "0 HEAD\r\n1 CHAR UTF-8\r\n0 TRLR\r\n"
        result = update_char_header(text, "ANSEL")
        assert "1 CHAR ANSEL\r\n" in result

    def test_crlf_insert_uses_crlf(self) -> None:
        text = "0 HEAD\r\n1 SOUR TEST\r\n0 TRLR\r\n"
        result = update_char_header(text, "UTF-8")
        assert "1 CHAR UTF-8\r\n" in result

    def test_no_head_raises_error(self) -> None:
        text = "1 SOUR TEST\n0 TRLR\n"
        with pytest.raises(ValueError, match="No HEAD record found"):
            update_char_header(text, "UTF-8")

    def test_does_not_match_charset(self) -> None:
        # "1 CHARSET ANSI" should NOT be matched by the CHAR regex
        text = "0 HEAD\n1 CHARSET ANSI\n1 CHAR UTF-8\n0 TRLR\n"
        result = update_char_header(text, "ANSEL")
        assert "1 CHARSET ANSI" in result
        assert "1 CHAR ANSEL" in result


# ---------------------------------------------------------------------------
# TestCountLongLines
# ---------------------------------------------------------------------------


class TestCountLongLines:
    def test_all_short(self) -> None:
        text = "short line\nanother\nthird\n"
        total, over = count_long_lines(text, "utf-8")
        assert total == 3
        assert over == 0

    def test_some_long(self) -> None:
        short = "ok\n"
        long_line = "x" * 256 + "\n"
        text = short + long_line + short
        total, over = count_long_lines(text, "utf-8")
        assert total == 3
        assert over == 1

    def test_utf8_multibyte(self) -> None:
        # Each "\u00e9" is 2 bytes in UTF-8. 128 of them = 256 bytes > 255 limit.
        line = "\u00e9" * 128 + "\n"
        total, over = count_long_lines(line, "utf-8")
        assert total == 1
        assert over == 1

    def test_empty(self) -> None:
        total, over = count_long_lines("", "utf-8")
        assert total == 0
        assert over == 0

    def test_utf16le_byte_lengths(self) -> None:
        # In UTF-16-LE, each ASCII char is 2 bytes. 128 chars = 256 bytes > 255.
        line = "a" * 128 + "\n"
        total, over = count_long_lines(line, "utf-16-le")
        assert total == 1
        assert over == 1


# ---------------------------------------------------------------------------
# TestTranscode
# ---------------------------------------------------------------------------


class TestTranscodeFileSizeLimit:
    def test_oversized_file_rejected(self, tmp_path: Path) -> None:
        from gedcom_tools.constants import MAX_FILE_SIZE_BYTES

        src = tmp_path / "big.ged"
        with open(src, "wb") as f:
            f.seek(MAX_FILE_SIZE_BYTES + 1)
            f.write(b"\x00")
        out = tmp_path / "out.ged"
        with pytest.raises(ValueError, match="too large"):
            transcode(
                src,
                out,
                source_codec="utf-8",
                target_codec="utf-8",
                target_char="UTF-8",
                normalize=False,
                add_bom=False,
                dry_run=False,
            )

    def test_error_includes_size_and_limit(self, tmp_path: Path) -> None:
        from gedcom_tools.constants import MAX_FILE_SIZE_BYTES

        src = tmp_path / "big.ged"
        with open(src, "wb") as f:
            f.seek(MAX_FILE_SIZE_BYTES + 1)
            f.write(b"\x00")
        out = tmp_path / "out.ged"
        with pytest.raises(ValueError, match="500 MB"):
            transcode(
                src,
                out,
                source_codec="utf-8",
                target_codec="utf-8",
                target_char="UTF-8",
                normalize=False,
                add_bom=False,
                dry_run=False,
            )


class TestTranscode:
    def test_utf8_to_utf8(self, tmp_path: Path) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "John /Smith/" in content
        assert result.lines_total > 0

    def test_utf8_to_utf16(self, tmp_path: Path) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-16-le",
            target_char="UNICODE",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        raw = out.read_bytes()
        text = raw.decode("utf-16-le")
        assert "1 CHAR UNICODE" in text
        assert result.target_encoding == "UNICODE"

    def test_utf16_source_to_utf8(self, tmp_path: Path) -> None:
        src = tmp_path / "src.ged"
        bom = b"\xff\xfe"
        encoded = MINIMAL_GED.encode("utf-16-le")
        src.write_bytes(bom + encoded)
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-16-le",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        content = out.read_text(encoding="utf-8")
        assert "1 CHAR UTF-8" in content
        assert result.bom_stripped == "utf-16-le"

    def test_nfc_normalization(self, tmp_path: Path) -> None:
        # NFD: e followed by combining acute accent
        nfd_name = "e\u0301"
        ged_text = MINIMAL_GED.replace("John", nfd_name)
        src = tmp_path / "src.ged"
        src.write_text(ged_text, encoding="utf-8")
        out = tmp_path / "out.ged"
        transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=True,
            add_bom=False,
            dry_run=False,
        )
        content = out.read_text(encoding="utf-8")
        assert "\u00e9" in content
        # The NFD form should be gone
        assert "e\u0301" not in content

    def test_no_normalize(self, tmp_path: Path) -> None:
        nfd_name = "e\u0301"
        ged_text = MINIMAL_GED.replace("John", nfd_name)
        src = tmp_path / "src.ged"
        src.write_text(ged_text, encoding="utf-8")
        out = tmp_path / "out.ged"
        transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        content = out.read_text(encoding="utf-8")
        # NFD should be preserved when normalize=False
        nfc = unicodedata.normalize("NFC", content)
        assert content != nfc  # content still has NFD sequences

    def test_bom_stripped(self, tmp_path: Path) -> None:
        src = tmp_path / "src.ged"
        src.write_bytes(b"\xef\xbb\xbf" + MINIMAL_GED.encode("utf-8"))
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        assert result.bom_stripped == "utf-8"

    def test_bom_added(self, tmp_path: Path) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=True,
            dry_run=False,
        )
        raw = out.read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"

    def test_bom_ignored_ascii(self, tmp_path: Path) -> None:
        # ASCII is not in BOM_ENCODINGS, so run() would set add_bom=False.
        # Calling transcode with add_bom=False for ascii target: no BOM.
        ascii_ged = "0 HEAD\n1 SOUR TEST\n1 CHAR ASCII\n0 TRLR\n"
        src = tmp_path / "src.ged"
        src.write_text(ascii_ged, encoding="ascii")
        out = tmp_path / "out.ged"
        transcode(
            src,
            out,
            source_codec="ascii",
            target_codec="ascii",
            target_char="ASCII",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        raw = out.read_bytes()
        # No BOM prefix
        assert raw[:3] != b"\xef\xbb\xbf"
        assert raw[:2] != b"\xff\xfe"
        assert raw[:2] != b"\xfe\xff"

    def test_char_updated(self, tmp_path: Path) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-16-le",
            target_char="UNICODE",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        content = out.read_bytes().decode("utf-16-le")
        assert "1 CHAR UNICODE" in content
        assert "1 CHAR UTF-8" not in content

    def test_dry_run_no_write(self, tmp_path: Path) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=True,
        )
        assert not out.exists()
        assert result.dry_run is True
        assert result.lines_total > 0

    def test_decode_error(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.ged"
        # 0x80 is not valid UTF-8 start byte
        src.write_bytes(b"0 HEAD\n1 CHAR UTF-8\n\x80\n0 TRLR\n")
        out = tmp_path / "out.ged"
        with pytest.raises(ValueError, match="Failed to decode"):
            transcode(
                src,
                out,
                source_codec="utf-8",
                target_codec="utf-8",
                target_char="UTF-8",
                normalize=False,
                add_bom=False,
                dry_run=False,
            )

    def test_encode_error_utf8_to_ascii(self, tmp_path: Path) -> None:
        ged_text = MINIMAL_GED.replace("John", "\u00e9mile")
        src = tmp_path / "src.ged"
        src.write_text(ged_text, encoding="utf-8")
        out = tmp_path / "out.ged"
        with pytest.raises(ValueError, match=r"U\+00E9"):
            transcode(
                src,
                out,
                source_codec="utf-8",
                target_codec="ascii",
                target_char="ASCII",
                normalize=False,
                add_bom=False,
                dry_run=False,
            )

    def test_line_endings_crlf_preserved(self, tmp_path: Path) -> None:
        crlf_ged = MINIMAL_GED.replace("\n", "\r\n")
        src = tmp_path / "src.ged"
        src.write_text(crlf_ged, encoding="utf-8", newline="")
        out = tmp_path / "out.ged"
        transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        raw = out.read_bytes()
        assert b"\r\n" in raw

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "empty.ged"
        src.write_bytes(b"")
        out = tmp_path / "out.ged"
        with pytest.raises(ValueError, match="File is empty"):
            transcode(
                src,
                out,
                source_codec="utf-8",
                target_codec="utf-8",
                target_char="UTF-8",
                normalize=False,
                add_bom=False,
                dry_run=False,
            )

    def test_bom_stripped_value(self, tmp_path: Path) -> None:
        src = tmp_path / "bom.ged"
        src.write_bytes(BOMS["utf-16-le"] + MINIMAL_GED.encode("utf-16-le"))
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-16-le",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        assert result.bom_stripped == "utf-16-le"

    def test_source_encoding_label(self, tmp_path: Path) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        result = transcode(
            src,
            out,
            source_codec="utf-8",
            target_codec="utf-8",
            target_char="UTF-8",
            normalize=False,
            add_bom=False,
            dry_run=False,
        )
        assert result.source_encoding == CODEC_TO_CHAR["utf-8"]
        assert result.source_encoding == "UTF-8"


# ---------------------------------------------------------------------------
# TestConvertResultFormatText
# ---------------------------------------------------------------------------


class TestConvertResultFormatText:
    def _make_result(self, **kwargs: object) -> ConvertResult:
        defaults: dict[str, object] = {
            "source_file": Path("input.ged"),
            "output_file": Path("output.ged"),
            "source_encoding": "UTF-8",
            "target_encoding": "UTF-8",
            "source_codec": "utf-8",
            "target_codec": "utf-8",
            "lines_total": 10,
            "lines_over_limit": 0,
            "normalized": False,
            "bom_added": False,
            "bom_stripped": None,
            "dry_run": False,
        }
        defaults.update(kwargs)
        return ConvertResult(**defaults)

    def test_quiet_dry_run(self) -> None:
        result = self._make_result(dry_run=True)
        colors = Colors(force_disable=True)
        text = result.format_text(colors, quiet=True)
        assert "(dry run)" in text
        assert "Converted" in text

    def test_bom_stripped_label(self) -> None:
        result = self._make_result(bom_stripped="utf-8")
        colors = Colors(force_disable=True)
        text = result.format_text(colors, quiet=False)
        assert "stripped" in text

    def test_bom_added_label(self) -> None:
        result = self._make_result(bom_added=True)
        colors = Colors(force_disable=True)
        text = result.format_text(colors, quiet=False)
        assert "added" in text

    def test_lines_over_limit_warning(self) -> None:
        result = self._make_result(lines_over_limit=5)
        colors = Colors(force_disable=True)
        text = result.format_text(colors, quiet=False)
        assert "5 lines" in text
        assert "255-byte" in text

    def test_dry_run_verbose(self) -> None:
        result = self._make_result(dry_run=True)
        colors = Colors(force_disable=True)
        text = result.format_text(colors, quiet=False)
        assert "dry run" in text
        assert "no file written" in text

    def test_format_json(self) -> None:
        result = self._make_result()
        output = json.loads(result.format_json())
        assert output["source_encoding"] == "UTF-8"
        assert output["target_encoding"] == "UTF-8"
        assert "gedcom_tools_version" in output


# ---------------------------------------------------------------------------
# TestConvertRun
# ---------------------------------------------------------------------------


class TestConvertRun:
    def test_basic_roundtrip(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "John /Smith/" in content

    def test_overwrite_protection(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        out.write_text("existing", encoding="utf-8")
        code = run(_make_args(src, "utf-8", out))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "already exists" in captured.err

    def test_force_overwrite(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        out.write_text("existing", encoding="utf-8")
        code = run(_make_args(src, "utf-8", out, force=True))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "John /Smith/" in content

    def test_same_file_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        # Use force=True to bypass overwrite protection (output exists = input)
        code = run(_make_args(src, "utf-8", src, force=True))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "resolves to the input" in captured.err

    def test_same_file_via_symlink(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        link = tmp_path / "link.ged"
        link.symlink_to(src)
        # Use force=True to bypass overwrite protection (symlink exists)
        code = run(_make_args(src, "utf-8", link, force=True))
        assert code == EXIT_ERROR
        captured = capsys.readouterr()
        assert "resolves to the input" in captured.err

    def test_missing_input(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "nonexistent.ged"
        out = tmp_path / "out.ged"
        code = run(_make_args(missing, "utf-8", out))
        assert code == EXIT_USAGE_ERROR

    def test_invalid_source(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Write valid GEDCOM with latin-1 high bytes, then try to decode as UTF-8.
        # detect_encoding sees "1 CHAR ASCII" and ged4py parses fine,
        # but --from utf-8 override makes transcode fail on the high byte.
        latin1_ged = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR ASCII\n"
            "0 @I1@ INDI\n1 NAME Ren\xe9 /Test/\n0 TRLR\n"
        )
        src = tmp_path / "bad.ged"
        src.write_bytes(latin1_ged.encode("latin-1"))
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, from_encoding="utf-8"))
        assert code == EXIT_ERROR

    def test_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, dry_run=True))
        assert code == EXIT_SUCCESS
        assert not out.exists()
        captured = capsys.readouterr()
        assert "dry run" in captured.out

    def test_quiet_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, quiet=True))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        output_text = captured.out.strip()
        # Quiet mode produces a single-line summary
        assert output_text.count("\n") == 0
        assert "Converted" in output_text

    def test_json_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, format="json"))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["source_encoding"] == "UTF-8"
        assert data["target_encoding"] == "UTF-8"
        assert "gedcom_tools_version" in data

    def test_bom_flag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, bom=True))
        assert code == EXIT_SUCCESS
        raw = out.read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"

    def test_no_normalize_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # With ANSEL source, normalize would normally be True.
        # Use --no-normalize to skip it. We'll test via --from override.
        nfd_name = "e\u0301"
        ged_text = MINIMAL_GED.replace("John", nfd_name)
        src = tmp_path / "src.ged"
        src.write_text(ged_text, encoding="utf-8")
        out = tmp_path / "out.ged"
        code = run(
            _make_args(
                src,
                "utf-8",
                out,
                from_encoding="utf-8",
                no_normalize=True,
            )
        )
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # NFD sequence should be preserved
        assert "e\u0301" in content

    def test_long_line_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        long_line = "1 NOTE " + "x" * 260
        ged_text = MINIMAL_GED.replace("1 NAME John /Smith/", long_line)
        src = tmp_path / "src.ged"
        src.write_text(ged_text, encoding="utf-8")
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out))
        assert code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "255-byte" in captured.err or "exceed" in captured.err

    def test_from_override_latin1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Write a latin-1 encoded file
        latin1_text = (
            "0 HEAD\n1 SOUR TEST\n1 CHAR ASCII\n"
            "0 @I1@ INDI\n1 NAME \xe9mile /Duval/\n0 TRLR\n"
        )
        src = tmp_path / "src.ged"
        src.write_bytes(latin1_text.encode("latin-1"))
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, from_encoding="latin-1"))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        assert "\u00e9mile" in content

    def test_invalid_from_encoding(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_ged(tmp_path)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, from_encoding="not-a-codec"))
        assert code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert "Unknown source encoding" in captured.err

    def test_from_override_ansel(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Build a minimal ANSEL-encoded file with high-byte ANSEL sequences.
        # ANSEL: combining acute (0xE2) precedes base char 'e' (0x65) -> e-acute
        ansel_bytes = (
            b"0 HEAD\r\n"
            b"1 SOUR TEST\r\n"
            b"1 CHAR ANSEL\r\n"
            b"0 @I1@ INDI\r\n"
            b"1 NAME \xe2" + b"emile /Duval/\r\n"
            b"0 TRLR\r\n"
        )
        src = tmp_path / "src.ged"
        src.write_bytes(ansel_bytes)
        out = tmp_path / "out.ged"
        code = run(_make_args(src, "utf-8", out, from_encoding="ansel"))
        assert code == EXIT_SUCCESS
        content = out.read_text(encoding="utf-8")
        # ANSEL codec decodes \xe2 + e as e + combining acute (NFD).
        # run() normalizes ANSEL sources to NFC by default.
        assert "\u00e9" in content or "e\u0301" in content
