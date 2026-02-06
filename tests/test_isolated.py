"""Tests for the isolated command."""

from __future__ import annotations

import json
from pathlib import Path

from gedcom_tools.cli import main
from gedcom_tools.commands.isolated import (
    IsolatedIndividual,
    IsolatedResult,
    _collect_data,
)
from gedcom_tools.progress import Colors

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _write_gedcom(tmp_path: Path, name: str, body: str) -> Path:
    """Write a minimal GEDCOM file and return its path."""
    f = tmp_path / name
    f.write_text(
        f"0 HEAD\n1 SOUR Test\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n{body}0 TRLR\n"
    )
    return f


class TestIsolatedDetection:
    """Tests for isolation detection logic."""

    def test_all_connected_no_isolated(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "connected.ged",
            """\
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Kid /Doe/
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 3
        assert len(result.singletons) == 0
        assert len(result.pairs) == 0

    def test_single_isolated_individual(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "singleton.ged",
            """\
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 1
        assert len(result.singletons) == 1
        assert result.singletons[0].xref == "@I1@"
        assert result.singletons[0].name == "John Smith"

    def test_multiple_isolated_individuals(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "multi.ged",
            """\
0 @I1@ INDI
1 NAME Alice /A/
0 @I2@ INDI
1 NAME Bob /B/
0 @I3@ INDI
1 NAME Carol /C/
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 3
        assert len(result.singletons) == 3
        assert len(result.pairs) == 0

    def test_isolated_pair_spouses(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "pair.ged",
            """\
0 @I1@ INDI
1 NAME Husband /X/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Wife /X/
1 SEX F
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 2
        assert len(result.singletons) == 0
        assert len(result.pairs) == 1
        pair_xrefs = {result.pairs[0][0].xref, result.pairs[0][1].xref}
        assert pair_xrefs == {"@I1@", "@I2@"}

    def test_isolated_pair_parent_child(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "parent_child.ged",
            """\
0 @I1@ INDI
1 NAME Parent /Y/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Child /Y/
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 2
        assert len(result.singletons) == 0
        assert len(result.pairs) == 1

    def test_mixed_singletons_pair_and_connected(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "mixed.ged",
            """\
0 @I1@ INDI
1 NAME Singleton /One/
0 @I2@ INDI
1 NAME Singleton /Two/
0 @I3@ INDI
1 NAME Pair /A/
1 FAMS @F1@
0 @I4@ INDI
1 NAME Pair /B/
1 FAMS @F1@
0 @I5@ INDI
1 NAME Connected /One/
1 FAMS @F2@
0 @I6@ INDI
1 NAME Connected /Two/
1 FAMS @F2@
0 @I7@ INDI
1 NAME Connected /Three/
1 FAMC @F2@
0 @F1@ FAM
1 HUSB @I3@
1 WIFE @I4@
0 @F2@ FAM
1 HUSB @I5@
1 WIFE @I6@
1 CHIL @I7@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 7
        assert len(result.singletons) == 2
        assert len(result.pairs) == 1
        assert result.isolated_count == 4  # 2 singletons + 1 pair (2 people)

    def test_component_of_three_not_isolated(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "three.ged",
            """\
0 @I1@ INDI
1 NAME A /X/
1 FAMS @F1@
0 @I2@ INDI
1 NAME B /X/
1 FAMS @F1@
0 @I3@ INDI
1 NAME C /X/
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 3
        assert len(result.singletons) == 0
        assert len(result.pairs) == 0
        assert result.isolated_count == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = _write_gedcom(tmp_path, "empty.ged", "")
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 0
        assert len(result.singletons) == 0
        assert len(result.pairs) == 0

    def test_single_individual_is_singleton(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "one.ged",
            """\
0 @I1@ INDI
1 NAME Solo /Person/
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 1
        assert len(result.singletons) == 1

    def test_no_fam_records_all_singletons(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "no_fam.ged",
            """\
0 @I1@ INDI
1 NAME A /X/
0 @I2@ INDI
1 NAME B /X/
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 2
        assert len(result.singletons) == 2

    def test_fams_to_empty_fam_is_singleton(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "empty_fam.ged",
            """\
0 @I1@ INDI
1 NAME Ghost /Link/
1 FAMS @F1@
0 @F1@ FAM
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 1
        assert len(result.singletons) == 1

    def test_fams_to_nonexistent_fam_is_singleton(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "missing_fam.ged",
            """\
0 @I1@ INDI
1 NAME Dangling /Ref/
1 FAMS @F999@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 1
        assert len(result.singletons) == 1

    def test_fam_referencing_nonexistent_indi(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "ghost_indi.ged",
            """\
0 @I1@ INDI
1 NAME Real /Person/
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I999@
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.total_individuals == 1
        # @I999@ doesn't exist, so @I1@ is alone in its component
        assert len(result.singletons) == 1

    def test_birt_without_date(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "no_date.ged",
            """\
0 @I1@ INDI
1 NAME Test /Person/
1 BIRT
2 PLAC Somewhere
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.singletons[0].birth_year is None

    def test_birth_year_extracted(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "birth.ged",
            """\
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 15 MAR 1850
""",
        )
        result = _collect_data(f, quiet=True, verbose=False, no_color=True)
        assert result.singletons[0].birth_year == 1850
        assert result.singletons[0].sex == "M"

    def test_555sample_regression(self) -> None:
        result = _collect_data(
            FIXTURES_DIR / "555sample.ged",
            quiet=True,
            verbose=False,
            no_color=True,
        )
        assert result.total_individuals == 3
        assert result.isolated_count == 0


class TestIsolatedFormatting:
    """Tests for output formatting."""

    def test_text_output_with_results(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=100,
            singletons=[
                IsolatedIndividual(
                    xref="@I1@", name="John Smith", sex="M", birth_year=1850
                ),
            ],
            pairs=[
                [
                    IsolatedIndividual(
                        xref="@I2@", name="Robert Green", sex="M", birth_year=1810
                    ),
                    IsolatedIndividual(
                        xref="@I3@", name="Susan Green", sex="F", birth_year=1815
                    ),
                ]
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "File: /test/tree.ged" in output
        assert "=== Isolated Analysis ===" in output
        assert "Total individuals:" in output
        assert "100" in output
        assert "Isolated individuals:" in output
        assert "3" in output  # 1 singleton + 2 in pair
        assert "=== Singletons ===" in output
        assert "John Smith (@I1@)" in output
        assert "b. 1850" in output
        assert "=== Isolated Pairs ===" in output
        assert "Robert Green (@I2@)" in output
        assert "Susan Green (@I3@)" in output

    def test_text_output_no_isolated(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=50,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "File: /test/tree.ged" in output
        assert "Isolated individuals:" in output
        assert "=== Singletons ===" not in output  # No singletons section

    def test_quiet_with_results(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=100,
            singletons=[
                IsolatedIndividual(xref="@I1@", name="A"),
                IsolatedIndividual(xref="@I2@", name="B"),
            ],
            pairs=[
                [
                    IsolatedIndividual(xref="@I3@", name="C"),
                    IsolatedIndividual(xref="@I4@", name="D"),
                ]
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert output == "4 isolated (2 singletons, 1 pair)"

    def test_quiet_no_results(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=50,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert output == ""

    def test_json_output(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=100,
            singletons=[
                IsolatedIndividual(
                    xref="@I1@", name="John Smith", sex="M", birth_year=1850
                ),
            ],
            pairs=[
                [
                    IsolatedIndividual(xref="@I2@", name="A", sex="M"),
                    IsolatedIndividual(xref="@I3@", name="B", sex="F"),
                ]
            ],
        )
        data = json.loads(result.format_json())

        assert data["file"] == "/test/tree.ged"
        assert data["summary"]["total_individuals"] == 100
        assert data["summary"]["isolated_count"] == 3
        assert data["summary"]["singleton_count"] == 1
        assert data["summary"]["pair_count"] == 1
        assert len(data["singletons"]) == 1
        assert data["singletons"][0]["xref"] == "@I1@"
        assert data["singletons"][0]["birth_year"] == 1850
        assert len(data["pairs"]) == 1
        assert len(data["pairs"][0]) == 2

    def test_json_empty(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=50,
        )
        data = json.loads(result.format_json())
        assert data["summary"]["isolated_count"] == 0
        assert data["singletons"] == []
        assert data["pairs"] == []


class TestIsolatedCLI:
    """CLI integration tests."""

    def test_help_exits_zero(self) -> None:
        try:
            main(["isolated", "--help"])
        except SystemExit as e:
            assert e.code == 0

    def test_missing_file(self) -> None:
        result = main(["isolated", "/nonexistent/path.ged"])
        assert result == 2

    def test_555sample(self) -> None:
        result = main(["-q", "isolated", str(FIXTURES_DIR / "555sample.ged")])
        assert result == 0

    def test_json_format(self) -> None:
        result = main(
            ["-q", "--format", "json", "isolated", str(FIXTURES_DIR / "555sample.ged")]
        )
        assert result == 0

    def test_quiet_mode(self) -> None:
        result = main(["-q", "isolated", str(FIXTURES_DIR / "555sample.ged")])
        assert result == 0

    def test_isolated_fixture(self) -> None:
        result = main(
            [
                "-q",
                "--format",
                "json",
                "isolated",
                str(FIXTURES_DIR / "isolated_individual.ged"),
            ]
        )
        assert result == 0

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        result = main(["isolated", str(tmp_path)])
        assert result == 2

    def test_normal_text_output(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path,
            "test.ged",
            "0 @I1@ INDI\n1 NAME Solo /Person/\n",
        )
        result = main(["isolated", str(f)])
        assert result == 0

    def test_text_empty_individuals(self) -> None:
        result = IsolatedResult(
            file_path="/test/tree.ged",
            total_individuals=0,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)
        assert "Isolated individuals:     0" in output

    def test_permission_denied(self, tmp_path: Path) -> None:
        f = tmp_path / "noperm.ged"
        f.write_text("0 HEAD\n0 TRLR\n")
        f.chmod(0o000)
        result = main(["isolated", str(f)])
        f.chmod(0o644)  # restore for cleanup
        assert result == 1
