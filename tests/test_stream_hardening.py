import io
import sys
from pathlib import Path

import pytest

from gedcom_tools import cli
from gedcom_tools.cli import _harden_streams, main
from gedcom_tools.constants import EXIT_SUCCESS

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_hardening_sentinel(monkeypatch):
    monkeypatch.setattr(cli, "_streams_hardened", False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)


def _wrapper(encoding="cp1252", errors="strict"):
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors=errors)


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
    out.write("Ανδρέου → Müller ✓\n")
    out.flush()
    assert out.buffer.getvalue().decode("utf-8") == "Ανδρέου → Müller ✓\n"


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
            monkeypatch, ["--no-color", "search", str(self.fixture), "surname=Ανδρέου"]
        )
        assert code == EXIT_SUCCESS
        assert "Ανδρέου" in text

    def test_search_json_output(self, monkeypatch):
        # search/formatter.py dumps with ensure_ascii=False, so the codec sees
        # the raw characters. Must be a name outside cp1252 to be a real
        # regression test - Muller-with-umlaut encodes fine and proves nothing.
        code, text = self._run(
            monkeypatch,
            ["--format", "json", "search", str(self.fixture), "surname=Ανδρέου"],
        )
        assert code == EXIT_SUCCESS
        assert "Ανδρέου" in text

    def test_validate_report(self, monkeypatch):
        code, text = self._run(
            monkeypatch, ["--no-color", "validate", str(self.fixture), "--full"]
        )
        assert code == EXIT_SUCCESS
        assert "Valid" in text
