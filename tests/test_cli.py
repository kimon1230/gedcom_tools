import pytest

from gedcom_tools import __version__
from gedcom_tools.cli import main
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR


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
    from gedcom_tools.constants import EXIT_ERROR

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
        "0 TRLR\n"
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
    gedcom_file.write_text("0 HEAD\n0 TRLR\n")

    result = main(["validate", str(gedcom_file)])
    assert result != EXIT_SUCCESS
    assert "error" in capsys.readouterr().err.lower()


def test_verbose_reraises_exceptions(tmp_path, monkeypatch):
    from gedcom_tools.commands import validate

    monkeypatch.setattr(validate, "run", _raise_error)

    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n0 TRLR\n")

    with pytest.raises(RuntimeError, match="boom"):
        main(["--verbose", "validate", str(f)])


# ---------------------------------------------------------------------------
# Stats command smoke tests
# ---------------------------------------------------------------------------


def test_stats_basic(sample_gedcom_path):
    assert main(["stats", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_stats_json_format(sample_gedcom_path, capsys):
    assert main(["--format", "json", "stats", str(sample_gedcom_path)]) == EXIT_SUCCESS
    import json

    data = json.loads(capsys.readouterr().out)
    assert "records" in data
    assert data["records"]["individuals"] > 0


def test_stats_quiet_mode(sample_gedcom_path, capsys):
    assert main(["-q", "stats", str(sample_gedcom_path)]) == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "individuals" in out
    assert "===" not in out  # Quiet mode omits section headers


def test_stats_top_n_flag(sample_gedcom_path):
    assert main(["stats", "--top", "5", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_stats_missing_file():
    assert main(["stats", "nonexistent.ged"]) == EXIT_USAGE_ERROR


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


def test_validate_royal92_ansel(capsys):
    """ANSEL-encoded royal92.ged should not produce E009."""
    from pathlib import Path

    from gedcom_tools.constants import EXIT_ERROR

    royal92 = Path(__file__).parent / "fixtures" / "royal92.ged"
    result = main(["validate", "--full", str(royal92)])
    assert result == EXIT_ERROR  # has real errors, but not E009

    out = capsys.readouterr().out
    assert "E009" not in out


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
