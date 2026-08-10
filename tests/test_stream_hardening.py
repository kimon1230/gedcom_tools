import io
import sys
from pathlib import Path

import pytest

from gedcom_tools import cli
from gedcom_tools.cli import _harden_streams, main, scrub_terminal_controls
from gedcom_tools.constants import EXIT_SUCCESS

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_hardening_sentinel(monkeypatch):
    monkeypatch.setattr(cli, "_streams_hardened", False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)


def _wrapper(encoding="cp1252", errors="strict"):
    # newline="" keeps these tests about encoding: without it, Windows
    # translates \n to \r\n on write and the byte comparisons drift.
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors=errors, newline="")


class _FakeTty:
    """A TTY-reporting stream that records how it was reconfigured.

    TextIOWrapper.isatty() delegates to its buffer, so a BytesIO-backed
    wrapper can never report True.
    """

    encoding = "cp1252"
    errors = "strict"

    def __init__(self):
        self.calls = []

    def isatty(self):
        return True

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)


def _install(monkeypatch, stdout, stderr=None):
    stderr = stderr if stderr is not None else _wrapper()
    for name, stream in (("stdout", stdout), ("stderr", stderr)):
        monkeypatch.setattr(sys, name, stream)
        monkeypatch.setattr(sys, f"__{name}__", stream)
    return stdout, stderr


def test_redirected_stream_becomes_utf8(monkeypatch):
    out, _ = _install(monkeypatch, _wrapper())
    _harden_streams()
    assert out.encoding == "utf-8"
    # reconfigure(encoding=...) resets errors to strict unless passed together.
    assert out.errors == "backslashreplace"


def test_redirected_stream_then_writes_astral_text(monkeypatch):
    out, _ = _install(monkeypatch, _wrapper())
    _harden_streams()
    out.write("Ζωγράφου → Müller ✓\n")
    out.flush()
    assert out.buffer.getvalue().decode("utf-8") == "Ζωγράφου → Müller ✓\n"


def test_tty_keeps_encoding_and_only_gains_error_handler(monkeypatch):
    tty = _FakeTty()
    _install(monkeypatch, tty)
    _harden_streams()
    assert tty.calls == [{"errors": "backslashreplace"}]


def test_stream_without_reconfigure_is_skipped(monkeypatch):
    _install(monkeypatch, io.StringIO())
    _harden_streams()  # must not raise


def test_stream_whose_reconfigure_raises_is_skipped(monkeypatch):
    class Hostile(_FakeTty):
        def reconfigure(self, **kwargs):
            raise ValueError("detached buffer")

    _install(monkeypatch, Hostile())
    _harden_streams()


def test_none_stream_is_skipped(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "__stdout__", None)
    _harden_streams()


def test_wrapped_stream_is_left_alone(monkeypatch):
    """pytest's CaptureIO is a TextIOWrapper subclass with a working
    reconfigure(); without the identity guard it would be mutated."""
    real = _wrapper()
    substitute = _wrapper()
    monkeypatch.setattr(sys, "__stdout__", real)
    monkeypatch.setattr(sys, "stdout", substitute)
    monkeypatch.setattr(sys, "stderr", _wrapper())
    monkeypatch.setattr(sys, "__stderr__", _wrapper())
    _harden_streams()
    assert substitute.encoding == "cp1252"


def test_pythonioencoding_keeps_user_encoding(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    out, _ = _install(monkeypatch, _wrapper())
    _harden_streams()
    assert out.encoding == "cp1252"
    assert out.errors == "backslashreplace"


def test_pythonioencoding_with_explicit_handler_is_untouched(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252:strict")
    out, _ = _install(monkeypatch, _wrapper())
    _harden_streams()
    assert out.encoding == "cp1252"
    assert out.errors == "strict"


def test_hardening_is_idempotent(monkeypatch):
    tty = _FakeTty()
    _install(monkeypatch, tty)
    _harden_streams()
    _harden_streams()
    assert len(tty.calls) == 1


class _TtyBytes(io.BytesIO):
    """A buffer that claims to be a terminal, so the wrapper above it does too."""

    def isatty(self):
        return True


def _tty_wrapper():
    return io.TextIOWrapper(_TtyBytes(), encoding="utf-8", errors="strict", newline="")


# Window title set, screen clear, an 8-bit CSI (which json.dumps passes through
# raw), and a right-to-left override - all spelled inside a given name.
OSC = "\x1b]0;pwned\x07"
# The right-to-left override stays an escape on purpose: pasted raw, it
# reorders this file in the editor of whoever reads it next.
SPOOFED_NAME = f"Bob{OSC}\x1b[2J\x9b31m\u202e"

RLO_UTF8 = "\u202e".encode()
C1_CSI_UTF8 = "\x9b".encode()


def _spoofed_file(tmp_path):
    path = tmp_path / "spoofed.ged"
    path.write_text(
        "0 HEAD\n"
        "1 SOUR test\n"
        "1 GEDC\n"
        "2 VERS 5.5.1\n"
        "2 FORM LINEAGE-LINKED\n"
        "1 CHAR UTF-8\n"
        "0 @I1@ INDI\n"
        f"1 NAME {SPOOFED_NAME} /Zed/\n"
        "1 SEX M\n"
        "0 TRLR\n",
        encoding="utf-8",
    )
    return path


class TestScrubTerminalControls:
    def test_osc_c1_and_bidi_are_dropped(self):
        scrubbed = scrub_terminal_controls(f"a{SPOOFED_NAME}b")
        raw = scrubbed.encode("utf-8")
        assert b"\x1b" not in raw
        assert b"\x07" not in raw
        assert C1_CSI_UTF8 not in raw
        # An OSC stripped by a CSI-only regex leaves its payload on screen.
        assert b"]0;pwned" not in raw
        assert not set(scrubbed) & cli.BIDI_CHARS
        assert scrubbed.startswith("aBob")

    def test_every_bidi_character_goes(self):
        assert scrub_terminal_controls("".join(cli.BIDI_CHARS)) == ""

    def test_layout_whitespace_is_kept(self):
        text = "name\tvalue\r\nnext\n"
        assert scrub_terminal_controls(text) == text

    def test_our_own_colour_and_erase_codes_survive(self):
        # Colour only ever reaches a terminal, which is the one branch the
        # filter sits on: stripping SGR here would disable colour outright.
        line = "\r\x1b[K\x1b[32m✓ \x1b[2m[1/3]\x1b[0m done\x1b[0m"
        assert scrub_terminal_controls(line) == line

    @pytest.mark.parametrize(
        "sequence", ["\x1b[2J", "\x1b[1;1H", "\x1b[?25l", "\x1b[3A"]
    )
    def test_other_escape_sequences_go(self, sequence):
        assert scrub_terminal_controls(f"x{sequence}y") == "xy"

    def test_unterminated_osc_loses_its_escape(self):
        assert "\x1b" not in scrub_terminal_controls("\x1b]0;still typing")


class TestTerminalControlFilter:
    def test_writelines_is_filtered_too(self):
        target = _wrapper(encoding="utf-8")
        wrapped = cli._TerminalControlFilter(target)
        wrapped.writelines([f"a{OSC}b\n", "c\n"])
        wrapped.flush()
        assert target.buffer.getvalue() == b"ab\nc\n"

    def test_write_reports_the_length_it_was_given(self):
        wrapped = cli._TerminalControlFilter(_wrapper(encoding="utf-8"))
        assert wrapped.write("a\x1b[2Jb") == 6

    def test_everything_else_reaches_the_real_stream(self):
        target = _wrapper(encoding="utf-8")
        wrapped = cli._TerminalControlFilter(target)
        assert wrapped.encoding == "utf-8"
        assert wrapped.isatty() is False


class TestTerminalOutputIsFiltered:
    """One command through the real CLI, on both formatters: the filter is
    installed once, and this is what proves it is installed at all."""

    def _run(self, monkeypatch, argv):
        out = _tty_wrapper()
        _install(monkeypatch, out, _tty_wrapper())
        code = main(argv)
        out.flush()
        return code, out.buffer.getvalue()

    def test_text_output(self, monkeypatch, tmp_path):
        code, data = self._run(
            monkeypatch, ["search", str(_spoofed_file(tmp_path)), "surname=Zed"]
        )
        assert code == EXIT_SUCCESS
        assert b"Zed" in data
        assert b"]0;pwned" not in data
        assert b"\x07" not in data
        assert b"\x1b[2J" not in data
        assert C1_CSI_UTF8 not in data
        assert RLO_UTF8 not in data
        # The report's own colours are still there.
        assert b"\x1b[36m" in data

    def test_json_output(self, monkeypatch, tmp_path):
        code, data = self._run(
            monkeypatch,
            ["--format", "json", "search", str(_spoofed_file(tmp_path)), "surname=Zed"],
        )
        assert code == EXIT_SUCCESS
        assert b'"surname": "Zed"' in data
        # json.dumps escapes the C0 bytes for us but not these two.
        assert C1_CSI_UTF8 not in data
        assert RLO_UTF8 not in data


class TestFileDestinedOutputIsNotFiltered:
    """Two ways to end up with a file on disk, neither of which may lose a
    byte: a command that opens the file itself, and a shell redirection."""

    def test_filter_writes_the_bytes_it_read(self, monkeypatch, tmp_path):
        source = _spoofed_file(tmp_path)
        target = tmp_path / "filtered.ged"
        _install(monkeypatch, _tty_wrapper(), _tty_wrapper())
        assert main(["filter", str(source), "-o", str(target), "--strip-notes"]) == 0
        written = target.read_bytes()
        assert OSC.encode("utf-8") in written
        assert C1_CSI_UTF8 in written
        assert RLO_UTF8 in written

    def test_export_through_redirected_stdout_keeps_the_bytes(
        self, monkeypatch, tmp_path
    ):
        out, _ = _install(monkeypatch, _wrapper())
        assert main(["export", str(_spoofed_file(tmp_path)), "--to", "csv"]) == 0
        out.flush()
        written = out.buffer.getvalue()
        assert OSC.encode("utf-8") in written
        assert C1_CSI_UTF8 in written
        assert RLO_UTF8 in written


class TestNonAsciiDataSurvivesRedirection:
    """The reported crash, at the level that actually matters: the tool's
    own glyphs are a small part of it, the user's names are the rest."""

    fixture = FIXTURES_DIR / "non_ascii_names.ged"

    def _run(self, monkeypatch, argv):
        out, _ = _install(monkeypatch, _wrapper())
        code = main(argv)
        out.flush()
        return code, out.buffer.getvalue().decode("utf-8")

    def test_search_text_output(self, monkeypatch):
        code, text = self._run(
            monkeypatch, ["--no-color", "search", str(self.fixture), "surname=Ζωγράφου"]
        )
        assert code == EXIT_SUCCESS
        assert "Ζωγράφου" in text

    def test_search_json_output(self, monkeypatch):
        # search/formatter.py dumps with ensure_ascii=False, so the codec sees
        # the raw characters. Must be a name outside cp1252 to be a real
        # regression test - Muller-with-umlaut encodes fine and proves nothing.
        code, text = self._run(
            monkeypatch,
            ["--format", "json", "search", str(self.fixture), "surname=Ζωγράφου"],
        )
        assert code == EXIT_SUCCESS
        assert "Ζωγράφου" in text

    def test_validate_report(self, monkeypatch):
        code, text = self._run(
            monkeypatch, ["--no-color", "validate", str(self.fixture), "--full"]
        )
        assert code == EXIT_SUCCESS
        assert "Valid" in text
