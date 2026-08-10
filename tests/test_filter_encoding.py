from __future__ import annotations

from pathlib import Path

import pytest

from gedcom_tools.cli import main
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR

# "+AAo-" is UTF-7 for U+000A. Read as ASCII the NOTE value is a single line;
# decoded as UTF-7 it becomes three, the last two of them a level-0 record that
# was never in the file. Written out as ASCII bytes -- the whole point is that
# the payload is unremarkable ASCII until the header picks the decoder.
SMUGGLE_UTF7 = (
    "0 HEAD\n"
    "1 SOUR TEST\n"
    "1 GEDC\n"
    "2 VERS 5.5.1\n"
    "1 CHAR UTF-7\n"
    "0 @I1@ INDI\n"
    "1 NAME John /Smith/\n"
    "1 NOTE +AAo-0 @IEVIL@ INDI+AAo-1 NAME Forged /Record/\n"
    "0 TRLR\n"
)

PLAIN_GED = (
    "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n"
    "0 @I1@ INDI\n1 NAME John /Smith/\n1 NOTE plain\n0 TRLR\n"
)


def _write(path: Path, content: str, encoding: str = "ascii") -> Path:
    ged = path / "in.ged"
    ged.write_bytes(content.encode(encoding))
    return ged


def _filter(src: Path, out: Path, *extra: str) -> int:
    argv = ["--no-color", "filter", str(src), "-o", str(out), "--strip-notes"]
    argv.extend(extra)
    return main(argv)


class TestFilterRefusesSmuggledCodec:
    def test_declared_utf7_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write(tmp_path, SMUGGLE_UTF7)
        out = tmp_path / "out.ged"
        code = _filter(src, out)
        assert code == EXIT_USAGE_ERROR
        assert "Cannot determine source encoding" in capsys.readouterr().err
        assert not out.exists()

    def test_no_forged_record_reaches_the_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write(tmp_path, SMUGGLE_UTF7)
        out = tmp_path / "out.ged"
        _filter(src, out)
        capsys.readouterr()
        assert not out.exists()


class TestFilterFromOverride:
    def test_from_utf7_still_processes_the_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The gate is about the file choosing its own decoder. Asking for utf-7
        # explicitly is a legitimate, if unwise, thing to do.
        src = _write(tmp_path, SMUGGLE_UTF7)
        out = tmp_path / "out.ged"
        code = _filter(src, out, "--from", "utf-7")
        assert code == EXIT_SUCCESS
        assert out.exists()

    def test_from_ordinary_encoding(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write(tmp_path, PLAIN_GED, encoding="utf-8")
        out = tmp_path / "out.ged"
        code = _filter(src, out, "--from", "utf-8")
        assert code == EXIT_SUCCESS
        assert "NOTE plain" not in out.read_text(encoding="utf-8")

    def test_from_skips_detection_on_an_unreadable_char_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A junk CHAR value is exactly the case --from exists to rescue.
        src = _write(tmp_path, PLAIN_GED.replace("1 CHAR UTF-8", "1 CHAR NOSUCHTHING"))
        out = tmp_path / "out.ged"
        code = _filter(src, out, "--from", "utf-8")
        assert code == EXIT_SUCCESS

    def test_undecodable_from_is_a_clean_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Unguarded this reaches cli.py as "Error: UnicodeDecodeError: ...".
        src = _write(tmp_path, PLAIN_GED.replace("John", "José"), encoding="utf-8")
        out = tmp_path / "out.ged"
        code = _filter(src, out, "--from", "ascii")
        err = capsys.readouterr().err
        assert code == EXIT_USAGE_ERROR
        assert "UnicodeDecodeError" not in err
        assert "Traceback" not in err
        assert err.startswith("Error: ")
        assert not out.exists()

    def test_unknown_from_value_is_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write(tmp_path, PLAIN_GED, encoding="utf-8")
        out = tmp_path / "out.ged"
        code = _filter(src, out, "--from", "not-a-codec")
        assert code == EXIT_USAGE_ERROR
        assert "Unknown source encoding" in capsys.readouterr().err
