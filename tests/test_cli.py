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
    assert result != EXIT_SUCCESS
    assert "not found" in capsys.readouterr().err.lower()


def test_validate_directory_instead_of_file(tmp_path, capsys):
    result = main(["validate", str(tmp_path)])
    assert result != EXIT_SUCCESS
    assert "not a file" in capsys.readouterr().err.lower()


def test_validate_basic(temp_gedcom_file, capsys):
    result = main(["validate", str(temp_gedcom_file)])
    assert result == EXIT_SUCCESS
    assert "not yet implemented" in capsys.readouterr().out.lower()


def test_validate_quick_mode(temp_gedcom_file, capsys):
    assert main(["validate", "--quick", str(temp_gedcom_file)]) == EXIT_SUCCESS
    assert "quick" in capsys.readouterr().out.lower()


def test_validate_full_mode(temp_gedcom_file, capsys):
    assert main(["validate", "--full", str(temp_gedcom_file)]) == EXIT_SUCCESS
    assert "full" in capsys.readouterr().out.lower()


def test_validate_sample_file(sample_gedcom_path):
    assert main(["validate", str(sample_gedcom_path)]) == EXIT_SUCCESS


def test_format_json_accepted(temp_gedcom_file):
    assert main(["--format", "json", "validate", str(temp_gedcom_file)]) == EXIT_SUCCESS


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
