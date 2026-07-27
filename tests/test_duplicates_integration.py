from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from gedcom_tools.commands.compare.models import CompareIndividual, MatchScore
from gedcom_tools.commands.duplicates import (
    _deduplicate_single_file,
    _normalize_candidates,
    run,
)
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR


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
    file_path: Path,
    fmt: str = "text",
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = True,
    certain_threshold: float = 0.85,
    probable_threshold: float = 0.65,
    show_matches: str = "all",
    limit: int | None = None,
    reject_sex_mismatch: bool = False,
    phonetic: str = "soundex",
) -> argparse.Namespace:
    return argparse.Namespace(
        file=file_path,
        format=fmt,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
        certain_threshold=certain_threshold,
        probable_threshold=probable_threshold,
        show_matches=show_matches,
        limit=limit,
        reject_sex_mismatch=reject_sex_mismatch,
        phonetic=phonetic,
    )


# ---------------------------------------------------------------------------
# _normalize_candidates unit tests
# ---------------------------------------------------------------------------


class TestNormalizeCandidates:
    def test_empty_set(self) -> None:
        assert _normalize_candidates(set()) == set()

    def test_all_self_pairs(self) -> None:
        raw = {("@I1@", "@I1@"), ("@I2@", "@I2@")}
        assert _normalize_candidates(raw) == set()

    def test_all_symmetric_pairs(self) -> None:
        raw = {("@I1@", "@I2@"), ("@I2@", "@I1@")}
        result = _normalize_candidates(raw)
        assert result == {("@I1@", "@I2@")}

    def test_mixed_input(self) -> None:
        raw = {
            ("@I1@", "@I1@"),  # self-pair
            ("@I2@", "@I1@"),  # reverse of canonical
            ("@I3@", "@I4@"),  # already canonical
            ("@I4@", "@I3@"),  # reverse duplicate
        }
        result = _normalize_candidates(raw)
        assert ("@I1@", "@I1@") not in result
        assert ("@I1@", "@I2@") in result
        assert ("@I3@", "@I4@") in result
        assert len(result) == 2

    def test_already_canonical(self) -> None:
        raw = {("@I1@", "@I2@"), ("@I3@", "@I5@")}
        result = _normalize_candidates(raw)
        assert result == raw

    def test_single_pair(self) -> None:
        raw = {("@I5@", "@I2@")}
        result = _normalize_candidates(raw)
        assert result == {("@I2@", "@I5@")}


# ---------------------------------------------------------------------------
# _deduplicate_single_file unit tests
# ---------------------------------------------------------------------------


def _make_individual(xref: str, name: str = "") -> CompareIndividual:
    return CompareIndividual(xref=xref, source_file="test", full_name=name)


def _make_score(total: float, classification: str = "probable") -> MatchScore:
    return MatchScore(
        total=total,
        field_scores={},
        classification=classification,
        comparable_field_count=4,
    )


class TestDeduplicateSingleFile:
    def test_empty_input(self) -> None:
        certain, probable = _deduplicate_single_file([])
        assert certain == []
        assert probable == []

    def test_single_pair_certain(self) -> None:
        a = _make_individual("@I1@", "Alice")
        b = _make_individual("@I2@", "Alice Copy")
        score = _make_score(0.95, "certain")
        certain, probable = _deduplicate_single_file([(a, b, score)])
        assert len(certain) == 1
        assert len(probable) == 0
        assert certain[0].individual_a.xref == "@I1@"
        assert certain[0].individual_b.xref == "@I2@"

    def test_single_pair_probable(self) -> None:
        a = _make_individual("@I1@")
        b = _make_individual("@I2@")
        score = _make_score(0.75, "probable")
        certain, probable = _deduplicate_single_file([(a, b, score)])
        assert len(certain) == 0
        assert len(probable) == 1

    def test_non_match_skipped(self) -> None:
        a = _make_individual("@I1@")
        b = _make_individual("@I2@")
        score = _make_score(0.30, "non_match")
        certain, probable = _deduplicate_single_file([(a, b, score)])
        assert certain == []
        assert probable == []

    def test_three_way_overlap_highest_wins(self) -> None:
        a = _make_individual("@I1@", "Alice")
        b = _make_individual("@I2@", "Alice B")
        c = _make_individual("@I3@", "Alice C")
        # I1-I2 is highest scoring, I1-I3 lower
        score_ab = _make_score(0.92, "certain")
        score_ac = _make_score(0.88, "certain")
        scored = [(a, b, score_ab), (a, c, score_ac)]
        certain, probable = _deduplicate_single_file(scored)
        # Only I1-I2 kept (highest score), I3 remains unmatched
        assert len(certain) == 1
        assert certain[0].individual_a.xref == "@I1@"
        assert certain[0].individual_b.xref == "@I2@"

    def test_greedy_ordering(self) -> None:
        # Three disjoint pairs — all should be kept
        pairs = []
        for i in range(3):
            a = _make_individual(f"@I{2*i+1}@")
            b = _make_individual(f"@I{2*i+2}@")
            pairs.append((a, b, _make_score(0.90 - i * 0.05, "certain")))
        certain, probable = _deduplicate_single_file(pairs)
        assert len(certain) == 3

    def test_single_used_set_prevents_reuse(self) -> None:
        # I1 matched with I2 (high score), then I2 matched with I3 (lower)
        i1 = _make_individual("@I1@")
        i2 = _make_individual("@I2@")
        i3 = _make_individual("@I3@")
        scored = [
            (i1, i2, _make_score(0.95, "certain")),
            (i2, i3, _make_score(0.80, "probable")),
        ]
        certain, probable = _deduplicate_single_file(scored)
        # I2 is used by I1-I2 pair, so I2-I3 is blocked
        assert len(certain) == 1
        assert len(probable) == 0
        used_xrefs = {certain[0].individual_a.xref, certain[0].individual_b.xref}
        assert "@I2@" in used_xrefs


# ---------------------------------------------------------------------------
# Threshold validation
# ---------------------------------------------------------------------------


class TestThresholdValidation:
    def test_out_of_range_certain(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        result = run(_make_args(f, certain_threshold=1.5))
        assert result == EXIT_USAGE_ERROR
        assert "between 0.0 and 1.0" in capsys.readouterr().err

    def test_out_of_range_probable_negative(self, tmp_path: Path) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        result = run(_make_args(f, probable_threshold=-0.1))
        assert result == EXIT_USAGE_ERROR

    def test_equal_thresholds(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        result = run(_make_args(f, certain_threshold=0.70, probable_threshold=0.70))
        assert result == EXIT_USAGE_ERROR
        assert "must be greater" in capsys.readouterr().err

    def test_certain_less_than_probable(self, tmp_path: Path) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        result = run(_make_args(f, certain_threshold=0.50, probable_threshold=0.80))
        assert result == EXIT_USAGE_ERROR

    def test_boundary_values_allowed(self, tmp_path: Path) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "A", "B", "M"),
            ],
        )
        # 0.0 and 1.0 are valid
        result = run(_make_args(f, certain_threshold=1.0, probable_threshold=0.0))
        assert result == EXIT_SUCCESS


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------


class TestFileValidation:
    def test_missing_file(self, tmp_path: Path) -> None:
        fake = tmp_path / "nonexistent.ged"
        result = run(_make_args(fake))
        assert result != EXIT_SUCCESS

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="chmod(0o000) leaves the owner read access on Windows",
    )
    def test_unreadable_file(self, tmp_path: Path) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        f.chmod(0o000)
        result = run(_make_args(f))
        assert result != EXIT_SUCCESS
        f.chmod(0o644)  # restore for cleanup

    def test_unreadable_file_without_chmod(self, tmp_path: Path) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        with patch("os.access", return_value=False):
            assert run(_make_args(f)) != EXIT_SUCCESS


# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------


class TestEndToEndDuplicates:
    def test_exact_duplicates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Certain Duplicates" in output or "Probable Duplicates" in output
        assert "@I1@" in output
        assert "@I2@" in output

    def test_variant_name_duplicates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "Jon", "Smyth", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "@I1@" in output
        assert "@I2@" in output

    def test_no_duplicates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920),
                _indi_block("@I2@", "Maria", "Garcia", "F", 1900, 1975),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Certain duplicates:      0" in output
        assert "Probable duplicates:     0" in output

    def test_empty_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Individuals scanned:     0" in output

    def test_single_individual(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [_indi_block("@I1@", "Alice", "Jones", "F", 1880)],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Certain duplicates:      0" in output

    def test_self_pairs_never_in_results(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [_indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London")],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # A single individual cannot be a self-duplicate
        assert "Certain Duplicates" not in output

    def test_symmetric_pairs_appear_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # Count occurrences of the pair — should appear exactly once
        lines_with_both = [
            line for line in output.splitlines() if "@I1@" in line and "@I2@" in line
        ]
        assert len(lines_with_both) == 1

    def test_no_individual_in_multiple_pairs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Three near-identical individuals — one should remain unmatched
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I3@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # Count how many times each xref appears in match lines (with ↔)
        match_lines = [line for line in output.splitlines() if "\u2194" in line]
        all_xrefs_in_matches: list[str] = []
        for line in match_lines:
            for xref in ["@I1@", "@I2@", "@I3@"]:
                if xref in line:
                    all_xrefs_in_matches.append(xref)
        # Each xref should appear at most once across all match lines
        for xref in ["@I1@", "@I2@", "@I3@"]:
            assert all_xrefs_in_matches.count(xref) <= 1


# ---------------------------------------------------------------------------
# Format modes
# ---------------------------------------------------------------------------


class TestFormatModes:
    def test_text_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920),
            ],
        )
        result = run(_make_args(f, fmt="text"))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "File:" in output
        assert "Duplicate Scan Summary" in output

    def test_json_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920),
            ],
        )
        result = run(_make_args(f, fmt="json"))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "file" in data
        assert "total_individuals" in data
        assert "certain_duplicates" in data
        assert "probable_duplicates" in data
        assert "certain_duplicates_total" in data
        assert "probable_duplicates_total" in data

    def test_quiet_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920),
            ],
        )
        result = run(_make_args(f, quiet=True))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out.strip()
        # Quiet mode: "<N> certain, <N> probable"
        assert "certain" in output
        assert "probable" in output
        # Should be a single line
        assert "\n" not in output

    def test_verbose_shows_scores(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f, verbose=True))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "[Scores:" in output


# ---------------------------------------------------------------------------
# --limit
# ---------------------------------------------------------------------------


class TestLimit:
    def test_limit_sentinel_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Default limit for text is 50 (more than we produce)
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f, fmt="text", limit=None))
        assert result == EXIT_SUCCESS

    def test_limit_sentinel_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Default limit for JSON is 0 (unlimited)
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f, fmt="json", limit=None))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        # Unlimited: total == array length
        assert data["certain_duplicates_total"] == len(data["certain_duplicates"])

    def test_limit_truncates_with_total(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Create multiple duplicate pairs by using different xrefs but same names
        individuals = []
        for i in range(1, 7):
            individuals.append(
                _indi_block(f"@I{i}@", "John", "Smith", "M", 1850, 1920, "London")
            )
        f = _write_gedcom(tmp_path / "test.ged", individuals)
        result = run(_make_args(f, fmt="json", limit=1))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        # With limit=1, arrays are truncated but totals reflect full count
        total_certain = data["certain_duplicates_total"]
        total_probable = data["probable_duplicates_total"]
        total_matches = total_certain + total_probable
        if total_matches > 1:
            displayed = len(data["certain_duplicates"]) + len(
                data["probable_duplicates"]
            )
            assert displayed <= 2  # at most 1 per section


# ---------------------------------------------------------------------------
# --reject-sex-mismatch
# ---------------------------------------------------------------------------


class TestRejectSexMismatch:
    def test_sex_mismatch_without_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "Alex", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "Alex", "Smith", "F", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f, reject_sex_mismatch=False))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # Without flag, sex mismatch gets penalty but may still match
        assert "Duplicate Scan Summary" in output

    def test_sex_mismatch_with_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "Alex", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "Alex", "Smith", "F", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f, reject_sex_mismatch=True))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # With flag, sex mismatch → non_match, so no duplicates
        assert "Certain duplicates:      0" in output
        assert "Probable duplicates:     0" in output


# ---------------------------------------------------------------------------
# Sparse-record classification
# ---------------------------------------------------------------------------


class TestSparseRecordClassification:
    def test_three_fields_caps_at_probable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # given + surname + sex = 3 fields, no corroborating → probable at best
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M"),
                _indi_block("@I2@", "John", "Smith", "M"),
            ],
        )
        result = run(_make_args(f, certain_threshold=0.85, probable_threshold=0.65))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # Should not be classified as "certain" even with perfect match
        assert (
            "Certain duplicates:      0" in output or "Certain Duplicates" not in output
        )

    def test_fewer_than_three_fields_absent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Only surname (1 field) → non_match, absent from results
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", surname="Smith"),
                _indi_block("@I2@", surname="Smith"),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Certain duplicates:      0" in output
        assert "Probable duplicates:     0" in output

    def test_insufficient_data_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 3 fields (given + surname + sex), no dates/places → insufficient_data
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M"),
                _indi_block("@I2@", "John", "Smith", "M"),
            ],
        )
        result = run(_make_args(f))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        if "Probable Duplicates" in output:
            assert "low confidence" in output


# ---------------------------------------------------------------------------
# by_xref guard (defensive, mocked)
# ---------------------------------------------------------------------------


class TestByXrefGuard:
    def test_stale_xref_skipped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        # Inject a stale xref pair into candidates that doesn't exist in by_xref
        original_normalize = _normalize_candidates

        def patched_normalize(raw: set[tuple[str, str]]) -> set[tuple[str, str]]:
            result = original_normalize(raw)
            result.add(("@I1@", "@ISTALE@"))
            return result

        with patch(
            "gedcom_tools.commands.duplicates._normalize_candidates",
            side_effect=patched_normalize,
        ):
            result = run(_make_args(f))

        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        # Stale xref should be silently skipped, no crash
        assert "@ISTALE@" not in output


# ---------------------------------------------------------------------------
# JSON structure validation
# ---------------------------------------------------------------------------


class TestJsonStructure:
    def test_source_file_omitted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M", 1850, 1920, "London"),
                _indi_block("@I2@", "John", "Smith", "M", 1850, 1920, "London"),
            ],
        )
        result = run(_make_args(f, fmt="json"))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        # source_file should not appear in individual dicts
        for section in ["certain_duplicates", "probable_duplicates"]:
            for pair in data[section]:
                assert "source_file" not in pair["individual_a"]
                assert "source_file" not in pair["individual_b"]

    def test_encoding_block(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(tmp_path / "test.ged", [])
        result = run(_make_args(f, fmt="json"))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        enc = data["encoding"]
        assert "detected" in enc
        assert "has_bom" in enc
        assert "declared" in enc

    def test_insufficient_data_in_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block("@I1@", "John", "Smith", "M"),
                _indi_block("@I2@", "John", "Smith", "M"),
            ],
        )
        result = run(_make_args(f, fmt="json"))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        all_matches = data["certain_duplicates"] + data["probable_duplicates"]
        if all_matches:
            # All 3-field matches should have insufficient_data
            for match in all_matches:
                assert match.get("insufficient_data") is True


# ---------------------------------------------------------------------------
# 555sample.ged regression
# ---------------------------------------------------------------------------


class TestSampleFile:
    @pytest.fixture()
    def sample_path(self) -> Path:
        p = Path(__file__).parent / "555sample.ged"
        if not p.exists():
            pytest.skip("555sample.ged not available")
        return p

    def test_runs_without_error(
        self, sample_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = run(_make_args(sample_path))
        assert result == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Duplicate Scan Summary" in output

    def test_json_valid(
        self, sample_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = run(_make_args(sample_path, fmt="json"))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data["total_individuals"], int)


class TestMetaphoneDuplicates:
    def test_metaphone_finds_variant_spellings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Catherine and Katherine: same person, different first-letter spelling
        # Soundex gives different codes (C365 vs K365), metaphone matches
        f = _write_gedcom(
            tmp_path / "test.ged",
            [
                _indi_block(
                    "@I1@",
                    "Catherine",
                    "Smith",
                    "F",
                    1850,
                    1920,
                    "London",
                ),
                _indi_block(
                    "@I2@",
                    "Katherine",
                    "Smith",
                    "F",
                    1850,
                    1920,
                    "London",
                ),
            ],
        )
        # With metaphone, they should be found as duplicates
        result = run(_make_args(f, fmt="json", phonetic="metaphone"))
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        all_matches = data["certain_duplicates"] + data["probable_duplicates"]
        matched_xrefs = set()
        for m in all_matches:
            matched_xrefs.add(m["individual_a"]["xref"])
            matched_xrefs.add(m["individual_b"]["xref"])
        assert "@I1@" in matched_xrefs
        assert "@I2@" in matched_xrefs
