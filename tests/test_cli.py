import argparse
import errno
import io
import subprocess
import sys
from pathlib import Path

import pytest

from gedcom_tools import __version__, cli
from gedcom_tools.cli import main
from gedcom_tools.commands import stats
from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "gedcom-tools" in out
    assert "validate" in out


def test_no_command_shows_help(capsys):
    assert main([]) == EXIT_USAGE_ERROR
    assert "usage:" in capsys.readouterr().out.lower()


def test_verbose_and_quiet_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        main(["--verbose", "--quiet", "validate", "test.ged"])
    assert exc.value.code == 2


def test_validate_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["validate", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--quick" in out
    assert "--full" in out


def test_validate_missing_file(capsys):
    result = main(["validate", "nonexistent.ged"])
    assert result == EXIT_USAGE_ERROR
    assert "not found" in capsys.readouterr().err.lower()


def test_validate_directory_instead_of_file(tmp_path, capsys):
    result = main(["validate", str(tmp_path)])
    assert result == EXIT_USAGE_ERROR
    assert "not a file" in capsys.readouterr().err.lower()


def test_validate_basic(temp_gedcom_file, capsys):
    result = main(["validate", str(temp_gedcom_file)])
    assert result == EXIT_SUCCESS
    out = capsys.readouterr().out.lower()
    assert "valid" in out


def test_validate_quick_mode(temp_gedcom_file, capsys):
    assert main(["validate", "--quick", str(temp_gedcom_file)]) == EXIT_SUCCESS
    out = capsys.readouterr().out.lower()
    assert "valid" in out


def test_validate_full_mode(temp_gedcom_file, capsys):
    assert main(["validate", "--full", str(temp_gedcom_file)]) == EXIT_SUCCESS
    out = capsys.readouterr().out.lower()
    assert "valid" in out


def test_validate_sample_file(sample_gedcom_path):
    assert main(["validate", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_format_json_accepted(temp_gedcom_file):
    assert main(["--format", "json", "validate", str(temp_gedcom_file)]) == EXIT_SUCCESS


def test_no_color_flag_accepted(temp_gedcom_file):
    assert main(["--no-color", "validate", str(temp_gedcom_file)]) == EXIT_SUCCESS


def test_quiet_mode_valid_file_no_output(temp_gedcom_file, capsys):
    """Quiet mode on valid file produces no stdout output."""
    assert main(["-q", "validate", str(temp_gedcom_file)]) == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert out == ""


def test_quiet_mode_errors_only(tmp_path, capsys):
    """Quiet mode shows only errors, not warnings or file info."""

    # Create file with an error (unresolved xref)
    ged = tmp_path / "bad.ged"
    ged.write_text(
        "0 HEAD\n"
        "1 GEDC\n"
        "2 VERS 5.5.1\n"
        "1 CHAR UTF-8\n"
        "0 @I1@ INDI\n"
        "1 NAME Test /Person/\n"
        "1 FAMC @F99@\n"
        "0 TRLR\n",
        encoding="utf-8",
    )

    result = main(["-q", "validate", "--full", str(ged)])
    assert result == EXIT_ERROR

    out = capsys.readouterr().out
    # Should contain error
    assert "[E001]" in out
    # Should NOT contain file info or warnings
    assert "File:" not in out
    assert "Encoding:" not in out
    assert "[W0" not in out  # No warning codes


def _raise_error(args):
    raise RuntimeError("boom")


def test_exception_handling(tmp_path, capsys, monkeypatch):
    from gedcom_tools.commands import validate

    monkeypatch.setattr(validate, "run", _raise_error)

    gedcom_file = tmp_path / "test.ged"
    gedcom_file.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")

    result = main(["validate", str(gedcom_file)])
    assert result != EXIT_SUCCESS
    assert "error" in capsys.readouterr().err.lower()


def test_verbose_reraises_exceptions(tmp_path, monkeypatch):
    from gedcom_tools.commands import validate

    monkeypatch.setattr(validate, "run", _raise_error)

    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="boom"):
        main(["--verbose", "validate", str(f)])


# ---------------------------------------------------------------------------
# Stats command smoke tests
# ---------------------------------------------------------------------------


# The five below run the whole stats pipeline, which builds a real
# GedcomLanguageDetector and fetches a 126 MB model on a cold cache. None of them
# asserts anything about detected languages, so the conftest stub stands in. The
# two that never reach the collector are left alone.


@pytest.mark.usefixtures("_fast_lingua")
def test_stats_basic(sample_gedcom_path):
    assert main(["stats", str(sample_gedcom_path)]) == EXIT_SUCCESS


@pytest.mark.usefixtures("_fast_lingua")
def test_stats_json_format(sample_gedcom_path, capsys):
    assert main(["--format", "json", "stats", str(sample_gedcom_path)]) == EXIT_SUCCESS
    import json

    data = json.loads(capsys.readouterr().out)
    assert "records" in data
    assert data["records"]["individuals"] > 0


@pytest.mark.usefixtures("_fast_lingua")
def test_stats_quiet_mode(sample_gedcom_path, capsys):
    assert main(["-q", "stats", str(sample_gedcom_path)]) == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "individuals" in out
    assert "===" not in out  # Quiet mode omits section headers


@pytest.mark.usefixtures("_fast_lingua")
def test_stats_top_n_flag(sample_gedcom_path):
    assert main(["stats", "--top", "5", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_stats_missing_file():
    assert main(["stats", "nonexistent.ged"]) == EXIT_USAGE_ERROR


@pytest.mark.usefixtures("_fast_lingua")
def test_stats_no_color(sample_gedcom_path):
    assert main(["--no-color", "stats", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_stats_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["stats", "--help"])
    assert exc.value.code == 0
    assert "--top" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Isolated command smoke tests
# ---------------------------------------------------------------------------


def test_isolated_basic(sample_gedcom_path):
    assert main(["isolated", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_isolated_json_format(sample_gedcom_path, capsys):
    assert (
        main(["--format", "json", "isolated", str(sample_gedcom_path)]) == EXIT_SUCCESS
    )
    import json

    data = json.loads(capsys.readouterr().out)
    assert "summary" in data
    assert "total_individuals" in data["summary"]


def test_isolated_quiet_mode(sample_gedcom_path, capsys):
    assert main(["-q", "isolated", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_isolated_missing_file():
    assert main(["isolated", "nonexistent.ged"]) == EXIT_USAGE_ERROR


def test_isolated_no_color(sample_gedcom_path):
    assert main(["--no-color", "isolated", str(sample_gedcom_path)]) == EXIT_SUCCESS


# ---------------------------------------------------------------------------
# ANSEL encoding support
# ---------------------------------------------------------------------------


def test_validate_royal92_ansel():
    """ANSEL-encoded royal92.ged is readable; validate reports its data errors."""

    from gedcom_tools.constants import EXIT_ERROR

    royal92 = Path(__file__).parent / "fixtures" / "royal92.ged"
    result = main(["validate", "--full", str(royal92)])
    assert result == EXIT_ERROR  # the fixture carries genuine data errors


class TestAsciiFlag:
    def test_ascii_flag_switches_decorations(self, capsys, temp_gedcom_file):
        assert main(["--ascii", "--no-color", "validate", str(temp_gedcom_file)]) == 0
        captured = capsys.readouterr()
        assert "[OK] Valid" in captured.out
        assert "✓" not in captured.out
        (captured.out + captured.err).encode("ascii")

    def test_default_keeps_unicode(self, capsys, temp_gedcom_file):
        assert main(["--no-color", "validate", str(temp_gedcom_file)]) == 0
        assert "✓ Valid" in capsys.readouterr().out

    def test_env_var_switches_decorations(self, capsys, monkeypatch, temp_gedcom_file):
        monkeypatch.setenv("GEDCOM_TOOLS_ASCII", "1")
        assert main(["--no-color", "validate", str(temp_gedcom_file)]) == 0
        assert "[OK] Valid" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

# Run the CLI the way a shell would, without depending on the console script
# being on PATH in whatever environment the suite is running in.
_RUN_CLI = "from gedcom_tools.cli import main; raise SystemExit(main())"


def test_broken_pipe_exits_success(tmp_path):
    """`gedcom-tools ... | head -1` must not report failure.

    Needs a real pipe: the interpreter's shutdown flush is part of what goes
    wrong, and that only happens in a separate process.
    """
    sample = Path(__file__).parent / "fixtures" / "555sample.ged"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _RUN_CLI,
            "--format",
            "json",
            "convert",
            str(sample),
            "--to",
            "utf-8",
            "--output",
            str(tmp_path / "out.ged"),
            "--dry-run",
        ],
        stdout=subprocess.PIPE,
        # Captured, not discarded. This fails on Windows with status 120 -
        # CPython's shutdown-flush failure - and the only artifact that says
        # why is the "Exception ignored in: <_io.TextIOWrapper name='<stdout>'>"
        # line the interpreter prints on that path. DEVNULL threw it away, so
        # every red run reported a bare `assert 120 == 0` and nothing else.
        stderr=subprocess.PIPE,
    )
    # Closing the read end is head walking away once it has the line it
    # wanted: every later write on the child's side gets EPIPE.
    assert proc.stdout is not None
    proc.stdout.close()
    _, err = proc.communicate(timeout=120)
    assert proc.returncode == EXIT_SUCCESS, err.decode(errors="replace")


@pytest.mark.parametrize(
    "err",
    [errno.EPIPE, errno.ESHUTDOWN, errno.EINVAL],
    ids=["EPIPE", "ESHUTDOWN", "EINVAL"],
)
def test_reader_gone_errnos_exit_success(monkeypatch, err):
    """A closed reader is a clean exit whichever errno the platform picks.

    EINVAL is the Windows spelling and is not a BrokenPipeError, which is how
    it escaped both arms into the generic handler and produced exit 120.
    """

    def burst(args):
        raise OSError(err, "reader went away")

    monkeypatch.setattr(stats, "run", burst)
    # StringIO has no fileno, so _silence_stdout's dup2 no-ops. With pytest's
    # real capture fd it would redirect that to devnull and break capturing
    # for the rest of the session.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    args = argparse.Namespace(command="stats", verbose=False)
    assert cli._run_command(args) == EXIT_SUCCESS


@pytest.mark.parametrize(
    "err", [errno.ENOSPC, errno.EACCES, errno.EIO], ids=["ENOSPC", "EACCES", "EIO"]
)
def test_non_pipe_errnos_still_fail_loudly(monkeypatch, capsys, err):
    """The errno gate is the whole point: a real I/O failure must not silence.

    Unguarded, the outer arm returns EXIT_SUCCESS for anything OSError-shaped,
    so a full disk or an unwritable path would be reported as a clean run.
    """

    def burst(args):
        raise OSError(err, "a real failure")

    monkeypatch.setattr(stats, "run", burst)
    args = argparse.Namespace(command="stats", verbose=False)
    assert cli._run_command(args) == EXIT_ERROR
    assert "Error:" in capsys.readouterr().err


def test_broken_pipe_handler_survives_fdless_stdout(monkeypatch, tmp_path):
    """The devnull redirect must not blow up when stdout has no real fd."""

    def burst(args):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(stats, "run", burst)
    # StringIO.fileno() raises io.UnsupportedOperation; a captured or wrapped
    # stdout behaves the same way, and there is no fd to redirect anyway.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert main(["stats", str(tmp_path / "any.ged")]) == EXIT_SUCCESS


class _FlushBreaksStdout(io.StringIO):
    """A stdout whose buffered writes only fail once the reader is gone.

    Subclassing StringIO rather than mocking is deliberate: the devnull
    redirect calls `fileno()`, and StringIO raises the
    `io.UnsupportedOperation` that redirect already swallows.
    """

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def test_flush_broken_pipe_keeps_the_commands_exit_code(monkeypatch, tmp_path):
    """A verdict the handler already reached must survive a closed pipe."""

    def failed(args):
        return EXIT_ERROR

    monkeypatch.setattr(stats, "run", failed)
    monkeypatch.setattr(sys, "stdout", _FlushBreaksStdout())
    assert main(["stats", str(tmp_path / "any.ged")]) == EXIT_ERROR


def test_flush_broken_pipe_silences_stdout(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "_silence_stdout", lambda: calls.append("flush"))
    monkeypatch.setattr(stats, "run", lambda args: EXIT_SUCCESS)
    monkeypatch.setattr(sys, "stdout", _FlushBreaksStdout())

    assert main(["stats", str(tmp_path / "any.ged")]) == EXIT_SUCCESS
    assert calls == ["flush"]


def test_handler_broken_pipe_silences_stdout(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "_silence_stdout", lambda: calls.append("handler"))

    def burst(args):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(stats, "run", burst)

    assert main(["stats", str(tmp_path / "any.ged")]) == EXIT_SUCCESS
    assert calls == ["handler"]


def test_flush_failure_that_is_not_a_broken_pipe_is_reported(
    monkeypatch, tmp_path, capsys
):
    """Only EPIPE is benign; other flush failures still get the error path."""

    class _FlushRaisesEncodingError(io.StringIO):
        def flush(self) -> None:
            raise UnicodeEncodeError("utf-8", "x", 0, 1, "nope")

    monkeypatch.setattr(stats, "run", lambda args: EXIT_SUCCESS)
    monkeypatch.setattr(sys, "stdout", _FlushRaisesEncodingError())

    assert main(["stats", str(tmp_path / "any.ged")]) == EXIT_ERROR
    assert "UnicodeEncodeError" in capsys.readouterr().err


def test_unexpected_error_names_the_exception(monkeypatch, sample_gedcom_path, capsys):
    def boom(args):
        raise KeyError("indi_count")

    monkeypatch.setattr(stats, "run", boom)

    assert main(["stats", str(sample_gedcom_path)]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "KeyError: 'indi_count'" in err
    assert "--verbose" in err


def test_handler_and_cli_render_an_error_identically(
    monkeypatch, sample_gedcom_path, capsys
):
    """The same exception must look the same whoever reports it.

    Which layer catches a failure is an implementation detail; a user typing
    `stats` and a user typing anything routed through cli.py should not see
    two different renderings of one error.
    """

    def boom(*args, **kwargs):
        raise KeyError("indi_count")

    # Reported by the command handler: stats catches it before cli.py sees it.
    monkeypatch.setattr(stats, "StatsCollector", boom)
    assert main(["stats", str(sample_gedcom_path)]) == EXIT_ERROR
    handler_err = capsys.readouterr().err

    # Reported by cli.py: the whole handler is gone, so nothing catches it first.
    monkeypatch.setattr(stats, "run", boom)
    assert main(["stats", str(sample_gedcom_path)]) == EXIT_ERROR
    cli_err = capsys.readouterr().err

    assert handler_err == cli_err
    assert "KeyError: 'indi_count'" in handler_err
