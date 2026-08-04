from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from gedcom_tools.cli import create_parser, main
from gedcom_tools.commands.compare import register_subcommand, run
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR


def _parse(argv: list[str]) -> argparse.Namespace:
    """Args built the way the CLI builds them: real dest names, real defaults."""
    return create_parser().parse_args(argv)


def _run_cli(argv: list[str]) -> int:
    """Drive the published entry point end to end, parser and dispatch included."""
    return main(argv)


def _write_gedcom(path: Path, individuals: list[str]) -> Path:
    lines = [
        "0 HEAD",
        "1 SOUR TEST",
        "1 GEDC",
        "2 VERS 5.5.1",
        "1 CHAR UTF-8",
    ]
    for indi in individuals:
        lines.append(indi)
    lines.append("0 TRLR")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _indi_block(
    xref: str,
    given: str = "",
    surname: str = "",
    sex: str = "",
    birth_year: int | None = None,
    death_year: int | None = None,
    birth_place: str = "",
    death_place: str = "",
) -> str:
    lines = [f"0 {xref} INDI"]
    if given or surname:
        lines.append(f"1 NAME {given} /{surname}/")
    if sex:
        lines.append(f"1 SEX {sex}")
    if birth_year is not None or birth_place:
        lines.append("1 BIRT")
        if birth_year is not None:
            lines.append(f"2 DATE {birth_year}")
        if birth_place:
            lines.append(f"2 PLAC {birth_place}")
    if death_year is not None or death_place:
        lines.append("1 DEAT")
        if death_year is not None:
            lines.append(f"2 DATE {death_year}")
        if death_place:
            lines.append(f"2 PLAC {death_place}")
    return "\n".join(lines)


def _make_args(
    file_a: Path,
    file_b: Path,
    fmt: str = "text",
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = True,
    certain_threshold: float = 0.85,
    probable_threshold: float = 0.65,
    show_matches: str = "all",
    list_unique: bool = False,
    limit: int | None = None,
    reject_sex_mismatch: bool = False,
    phonetic: str = "soundex",
    max_block_size: int = 500,
) -> argparse.Namespace:
    argv = [f"--format={fmt}"]
    if quiet:
        argv.append("--quiet")
    if verbose:
        argv.append("--verbose")
    if no_color:
        argv.append("--no-color")
    argv += [
        "compare",
        str(file_a),
        str(file_b),
        f"--certain-threshold={certain_threshold}",
        f"--probable-threshold={probable_threshold}",
        f"--show-matches={show_matches}",
        f"--phonetic={phonetic}",
        f"--max-block-size={max_block_size}",
    ]
    if list_unique:
        argv.append("--list-unique")
    if reject_sex_mismatch:
        argv.append("--reject-sex-mismatch")
    # Left off entirely when None, so the parser's own default is what runs.
    if limit is not None:
        argv.append(f"--limit={limit}")
    return _parse(argv)


# Distinct enough that no two share a Soundex code, so the given-name passes
# never produce a block of their own.
_CROWD_GIVEN_NAMES = ["Alan", "Bertha", "Carl", "Dora", "Egbert", "Fiona"]


def _crowded_surname_file(path: Path, xref_prefix: str, count: int) -> Path:
    """People who all share one surname + birth decade, i.e. one fat block."""
    return _write_gedcom(
        path,
        [
            _indi_block(
                f"@{xref_prefix}{n}@",
                _CROWD_GIVEN_NAMES[n],
                "Smith",
                "M",
                birth_year=1850 + n,
            )
            for n in range(count)
        ],
    )


# Shared individual blocks for File A
_FILE_A_INDIVIDUALS = [
    _indi_block(
        "@I1@",
        "John",
        "Smith",
        "M",
        birth_year=1850,
        death_year=1920,
        birth_place="London, England",
    ),
    _indi_block(
        "@I2@",
        "Mary",
        "Johnson",
        "F",
        birth_year=1872,
        death_year=1945,
    ),
    _indi_block(
        "@I3@",
        "Robert",
        "Williams",
        "M",
        birth_year=1900,
    ),
]

# Shared individual blocks for File B
_FILE_B_INDIVIDUALS = [
    _indi_block(
        "@I10@",
        "John",
        "Smith",
        "M",
        birth_year=1850,
        death_year=1920,
        birth_place="London, Middlesex, England",
    ),
    _indi_block(
        "@I11@",
        "Mary",
        "Johnson",
        "F",
        birth_year=1872,
        death_year=1945,
    ),
    _indi_block(
        "@I12@",
        "Alice",
        "Brown",
        "F",
        birth_year=1830,
    ),
]


def _create_pair(tmp_path: Path) -> tuple[Path, Path]:
    file_a = _write_gedcom(tmp_path / "a.ged", _FILE_A_INDIVIDUALS)
    file_b = _write_gedcom(tmp_path / "b.ged", _FILE_B_INDIVIDUALS)
    return file_a, file_b


class _DeadStream:
    """A stderr whose every write fails the way a closed pipe does."""

    def __init__(self) -> None:
        self.attempts = 0

    def write(self, text: str) -> int:
        self.attempts += 1
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")

    def isatty(self) -> bool:
        return False


class TestRegisterSubcommand:
    def test_parser_created(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_subcommand(subparsers)

        args = parser.parse_args(
            [
                "compare",
                "a.ged",
                "b.ged",
                "--certain-threshold",
                "0.90",
                "--probable-threshold",
                "0.70",
                "--show-matches",
                "certain",
                "--list-unique",
                "--limit",
                "10",
                "--reject-sex-mismatch",
            ]
        )
        assert args.file_a == Path("a.ged")
        assert args.file_b == Path("b.ged")
        assert args.certain_threshold == 0.90
        assert args.probable_threshold == 0.70
        assert args.show_matches == "certain"
        assert args.list_unique is True
        assert args.limit == 10
        assert args.reject_sex_mismatch is True


class TestValidation:
    def test_missing_file_a(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.ged"
        real = _write_gedcom(tmp_path / "b.ged", [])
        args = _make_args(missing, real)
        assert run(args) == EXIT_USAGE_ERROR

    def test_missing_file_b(self, tmp_path: Path) -> None:
        real = _write_gedcom(tmp_path / "a.ged", [])
        missing = tmp_path / "nope.ged"
        args = _make_args(real, missing)
        assert run(args) == EXIT_USAGE_ERROR

    def test_same_file_detection(self, tmp_path: Path, capsys) -> None:
        f = _write_gedcom(tmp_path / "same.ged", [])
        args = _make_args(f, f)
        assert run(args) == EXIT_USAGE_ERROR
        assert "same file" in capsys.readouterr().err.lower()

    def test_same_file_verdict_survives_a_dead_stderr(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # quiet=True is load-bearing: without it PhaseTracker's first write hits
        # the closed pipe and aborts run() before it can self-compare, so the
        # test would pass for the wrong reason.
        f = _write_gedcom(tmp_path / "same.ged", _FILE_A_INDIVIDUALS)
        monkeypatch.setattr(sys, "stderr", _DeadStream())
        args = _make_args(f, f, quiet=True)
        assert run(args) == EXIT_USAGE_ERROR

    def test_dead_stderr_swallows_only_the_message(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # The guard must not reach further than the print: a comparison that
        # never happened cannot have written to stdout.
        f = _write_gedcom(tmp_path / "same.ged", _FILE_A_INDIVIDUALS)
        stderr = _DeadStream()
        monkeypatch.setattr(sys, "stderr", stderr)
        with io.StringIO() as stdout:
            monkeypatch.setattr(sys, "stdout", stdout)
            assert run(_make_args(f, f, quiet=True)) == EXIT_USAGE_ERROR
            assert stdout.getvalue() == ""
        assert stderr.attempts == 1

    def test_invalid_certain_threshold(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, certain_threshold=1.5)
        assert run(args) == EXIT_USAGE_ERROR

    def test_invalid_probable_threshold(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, probable_threshold=-0.1)
        assert run(args) == EXIT_USAGE_ERROR

    def test_certain_not_greater_than_probable(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, certain_threshold=0.50, probable_threshold=0.65)
        assert run(args) == EXIT_USAGE_ERROR


class TestBasicPipeline:
    def test_successful_comparison(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b)
        assert run(args) == EXIT_SUCCESS

    def test_text_output_has_summary(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="text")
        run(args)
        assert "=== Comparison Summary ===" in capsys.readouterr().out

    def test_json_output_valid(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="json")
        run(args)
        data = json.loads(capsys.readouterr().out)
        assert "certain_matches" in data
        assert "probable_matches" in data
        assert "unique_to_a" in data
        assert "unique_to_b" in data
        assert "total_a" in data
        assert "total_b" in data

    def test_quiet_output_single_line(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, quiet=True)
        run(args)
        out = capsys.readouterr().out.strip()
        assert "\n" not in out
        assert "certain" in out

    def test_matching_individuals_found(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="json")
        run(args)
        data = json.loads(capsys.readouterr().out)

        # John Smith (I1 <-> I10) and Mary Johnson (I2 <-> I11) should match
        all_matches = data["certain_matches"] + data["probable_matches"]
        matched_pairs = {
            (m["individual_a"]["xref"], m["individual_b"]["xref"]) for m in all_matches
        }
        assert ("@I1@", "@I10@") in matched_pairs
        assert ("@I2@", "@I11@") in matched_pairs


class TestFlags:
    def test_show_certain_only(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="json", show_matches="certain")
        run(args)
        data = json.loads(capsys.readouterr().out)
        assert data["probable_matches"] == []

    def test_show_probable_only(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="json", show_matches="probable")
        run(args)
        data = json.loads(capsys.readouterr().out)
        assert data["certain_matches"] == []

    def test_list_unique(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="json", list_unique=True)
        run(args)
        data = json.loads(capsys.readouterr().out)
        unique_a_xrefs = {u["xref"] for u in data["unique_to_a"]}
        unique_b_xrefs = {u["xref"] for u in data["unique_to_b"]}
        # Robert Williams only in A, Alice Brown only in B
        assert "@I3@" in unique_a_xrefs
        assert "@I12@" in unique_b_xrefs

    def test_limit_truncates(self, tmp_path: Path, capsys) -> None:
        # Build files with many overlapping individuals
        indis_a = [
            _indi_block(
                f"@I{i}@",
                f"Person{i}",
                "Commonname",
                "M",
                birth_year=1800 + i,
                death_year=1870 + i,
            )
            for i in range(1, 11)
        ]
        indis_b = [
            _indi_block(
                f"@J{i}@",
                f"Person{i}",
                "Commonname",
                "M",
                birth_year=1800 + i,
                death_year=1870 + i,
            )
            for i in range(1, 11)
        ]
        fa = _write_gedcom(tmp_path / "a.ged", indis_a)
        fb = _write_gedcom(tmp_path / "b.ged", indis_b)

        # Control run. Ten identical people on both sides all score 1.0, so
        # every pair lands in certain_matches and probable_matches stays empty.
        # Without this the limited assertion below would also pass on a bucket
        # that was empty to begin with.
        run(_make_args(fa, fb, fmt="json", limit=0))
        unlimited = json.loads(capsys.readouterr().out)
        assert len(unlimited["certain_matches"]) >= 2

        run(_make_args(fa, fb, fmt="json", limit=1))
        limited = json.loads(capsys.readouterr().out)
        assert len(limited["certain_matches"]) == 1
        assert limited["certain_matches_total"] == len(unlimited["certain_matches"])


class TestLimitDefaulting:
    def test_text_default_limit(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="text", limit=None)
        rc = run(args)
        assert rc == EXIT_SUCCESS
        # No crash — text limit defaults to 50 internally

    def test_json_default_limit(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, fmt="json", limit=None)
        run(args)
        data = json.loads(capsys.readouterr().out)
        # JSON default is unlimited — all items present
        all_matches = data["certain_matches"] + data["probable_matches"]
        matched_xrefs = {m["individual_a"]["xref"] for m in all_matches}
        # Both matching individuals should be present (not truncated)
        assert "@I1@" in matched_xrefs and "@I2@" in matched_xrefs


class TestExitCodes:
    def test_success_exit_code(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        assert run(_make_args(a, b)) == EXIT_SUCCESS

    def test_file_not_found_exit_code(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.ged"
        real = _write_gedcom(tmp_path / "b.ged", [])
        assert run(_make_args(missing, real)) == EXIT_USAGE_ERROR

    def test_threshold_error_exit_code(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        args = _make_args(a, b, certain_threshold=0.50, probable_threshold=0.65)
        assert run(args) == EXIT_USAGE_ERROR


class TestEdgeCases:
    def test_empty_files(self, tmp_path: Path, capsys) -> None:
        fa = _write_gedcom(tmp_path / "a.ged", [])
        fb = _write_gedcom(tmp_path / "b.ged", [])
        args = _make_args(fa, fb, fmt="json")
        rc = run(args)
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert data["certain_matches"] == []
        assert data["probable_matches"] == []
        assert data["total_a"] == 0
        assert data["total_b"] == 0

    def test_no_overlap(self, tmp_path: Path, capsys) -> None:
        fa = _write_gedcom(
            tmp_path / "a.ged",
            [
                _indi_block(
                    "@I1@", "Unique", "Alpha", "M", birth_year=1800, death_year=1870
                )
            ],
        )
        fb = _write_gedcom(
            tmp_path / "b.ged",
            [
                _indi_block(
                    "@I1@", "Different", "Omega", "F", birth_year=1950, death_year=2020
                )
            ],
        )
        args = _make_args(fa, fb, fmt="json", list_unique=True)
        rc = run(args)
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert data["certain_matches"] == []
        assert data["probable_matches"] == []
        assert len(data["unique_to_a"]) == 1
        assert len(data["unique_to_b"]) == 1

    def test_identical_individuals(self, tmp_path: Path, capsys) -> None:
        block = _indi_block(
            "@I1@",
            "George",
            "Washington",
            "M",
            birth_year=1732,
            death_year=1799,
            birth_place="Westmoreland, Virginia",
            death_place="Mount Vernon, Virginia",
        )
        fa = _write_gedcom(tmp_path / "a.ged", [block])
        # Same data, different xref in file B
        block_b = _indi_block(
            "@I99@",
            "George",
            "Washington",
            "M",
            birth_year=1732,
            death_year=1799,
            birth_place="Westmoreland, Virginia",
            death_place="Mount Vernon, Virginia",
        )
        fb = _write_gedcom(tmp_path / "b.ged", [block_b])
        args = _make_args(fa, fb, fmt="json")
        rc = run(args)
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert len(data["certain_matches"]) == 1
        pair = data["certain_matches"][0]
        assert pair["individual_a"]["xref"] == "@I1@"
        assert pair["individual_b"]["xref"] == "@I99@"
        assert pair["score"] >= 0.85


class TestMetaphoneIntegration:
    def test_metaphone_option_accepted(self, tmp_path: Path, capsys) -> None:
        fa = _write_gedcom(
            tmp_path / "a.ged",
            [
                _indi_block(
                    "@I1@",
                    "John",
                    "Smith",
                    "M",
                    birth_year=1850,
                    death_year=1920,
                    birth_place="London, England",
                ),
            ],
        )
        fb = _write_gedcom(
            tmp_path / "b.ged",
            [
                _indi_block(
                    "@I2@",
                    "John",
                    "Smith",
                    "M",
                    birth_year=1850,
                    death_year=1920,
                    birth_place="London, England",
                ),
            ],
        )
        args = _make_args(fa, fb, fmt="json", phonetic="metaphone")
        rc = run(args)
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert len(data["certain_matches"]) == 1

    def test_metaphone_cross_code_blocking(self, tmp_path: Path, capsys) -> None:
        # Use surnames with different soundex first letters but shared metaphone.
        # Only blocking key is surname+birth — no given names, different death years,
        # no exact year combo.
        fa = _write_gedcom(
            tmp_path / "a.ged",
            [
                _indi_block(
                    "@I1@",
                    "John",
                    "Catherine",
                    "M",
                    birth_year=1850,
                    birth_place="London",
                ),
            ],
        )
        fb = _write_gedcom(
            tmp_path / "b.ged",
            [
                _indi_block(
                    "@I2@",
                    "James",
                    "Katherine",
                    "M",
                    birth_year=1853,
                    birth_place="London",
                ),
            ],
        )
        # Soundex: surname Catherine(C365) vs Katherine(K365) — different.
        # Given names differ too (J500 vs J520). No death year combo.
        # Only possible blocking pass: surname+birth decade.
        # Soundex surname codes differ → no candidates → no match.
        args_sx = _make_args(fa, fb, fmt="json", phonetic="soundex")
        run(args_sx)
        data_sx = json.loads(capsys.readouterr().out)
        assert data_sx["certain_matches"] + data_sx["probable_matches"] == []

        # Metaphone: Catherine and Katherine produce same codes.
        # Multi-key blocking catches them via shared code + birth decade.
        args_mp = _make_args(fa, fb, fmt="json", phonetic="metaphone")
        run(args_mp)
        data_mp = json.loads(capsys.readouterr().out)
        mp_matches = data_mp["certain_matches"] + data_mp["probable_matches"]
        assert len(mp_matches) >= 1


class TestOversizedBlockWarning:
    def _pair(self, tmp_path: Path) -> tuple[Path, Path]:
        fa = _write_gedcom(
            tmp_path / "a.ged",
            [_indi_block("@I1@", "John", "Smith", "M", birth_year=1850)],
        )
        fb = _crowded_surname_file(tmp_path / "b.ged", "B", 4)
        return fa, fb

    def test_warning_names_the_group_count(self, tmp_path: Path, capsys) -> None:
        fa, fb = self._pair(tmp_path)
        assert run(_make_args(fa, fb, max_block_size=2)) == EXIT_SUCCESS
        err = capsys.readouterr().err
        # One surname block was dropped, not one per individual on side A.
        assert "1 blocking group exceeded --max-block-size 2" in err
        assert "some matches may be missing" in err

    def test_count_reaches_json_consumers(self, tmp_path: Path, capsys) -> None:
        fa, fb = self._pair(tmp_path)
        assert run(_make_args(fa, fb, fmt="json", max_block_size=2)) == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert json.loads(captured.out)["oversized_blocks_skipped"] == 1
        assert "--max-block-size" in captured.err

    def test_quiet_still_says_the_answer_is_incomplete(
        self, tmp_path: Path, capsys
    ) -> None:
        fa, fb = self._pair(tmp_path)
        assert run(_make_args(fa, fb, quiet=True, max_block_size=2)) == EXIT_SUCCESS
        assert "blocking group" in capsys.readouterr().err

    def test_nothing_skipped_is_silent(self, tmp_path: Path, capsys) -> None:
        fa, fb = self._pair(tmp_path)
        assert run(_make_args(fa, fb, fmt="json")) == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "blocking group" not in captured.err
        assert "oversized_blocks_skipped" not in json.loads(captured.out)

    def test_raising_the_cap_recovers_the_matches(self, tmp_path: Path, capsys) -> None:
        # Four namesakes: every blocking pass puts them in the same group, so
        # a low cap leaves no route to the match at all.
        fa = _write_gedcom(
            tmp_path / "a.ged",
            [_indi_block("@I1@", "Alan", "Smith", "M", birth_year=1850)],
        )
        fb = _write_gedcom(
            tmp_path / "b.ged",
            [
                _indi_block(f"@B{n}@", "Alan", "Smith", "M", birth_year=1850 + n)
                for n in range(4)
            ],
        )

        run(_make_args(fa, fb, fmt="json", max_block_size=2))
        capped = json.loads(capsys.readouterr().out)

        run(_make_args(fa, fb, fmt="json", max_block_size=10))
        full = json.loads(capsys.readouterr().out)

        assert capped["certain_matches_total"] + capped["probable_matches_total"] == 0
        assert capped["oversized_blocks_skipped"] == 3
        assert full["certain_matches_total"] + full["probable_matches_total"] == 1
        assert "oversized_blocks_skipped" not in full

    def test_zero_cap_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        fa, fb = self._pair(tmp_path)
        assert run(_make_args(fa, fb, max_block_size=0)) == EXIT_USAGE_ERROR
        assert "--max-block-size must be at least 1" in capsys.readouterr().err

    def test_flag_is_registered(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_subcommand(subparsers)
        args = parser.parse_args(["compare", "a.ged", "b.ged", "--max-block-size", "5"])
        assert args.max_block_size == 5
        default_args = parser.parse_args(["compare", "a.ged", "b.ged"])
        assert default_args.max_block_size == 500


class TestCliEndToEnd:
    """No hand-built Namespace anywhere: argv in, exit status out."""

    def test_compare_via_main(self, tmp_path: Path, capsys) -> None:
        a, b = _create_pair(tmp_path)
        rc = _run_cli(["--format", "json", "--no-color", "compare", str(a), str(b)])
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        matched = {
            m["individual_a"]["xref"]
            for m in data["certain_matches"] + data["probable_matches"]
        }
        assert "@I1@" in matched

    def test_compare_flags_survive_the_real_parser(
        self, tmp_path: Path, capsys
    ) -> None:
        a, b = _create_pair(tmp_path)
        rc = _run_cli(
            [
                "--format",
                "json",
                "--no-color",
                "compare",
                str(a),
                str(b),
                "--list-unique",
                "--show-matches",
                "certain",
                "--phonetic",
                "metaphone",
                "--max-block-size",
                "50",
            ]
        )
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert data["probable_matches"] == []
        assert {u["xref"] for u in data["unique_to_a"]} >= {"@I3@"}

    def test_threshold_error_reaches_the_exit_status(self, tmp_path: Path) -> None:
        a, b = _create_pair(tmp_path)
        rc = _run_cli(
            [
                "compare",
                str(a),
                str(b),
                "--certain-threshold",
                "0.50",
                "--probable-threshold",
                "0.65",
            ]
        )
        assert rc == EXIT_USAGE_ERROR
