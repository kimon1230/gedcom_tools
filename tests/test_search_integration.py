from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from gedcom_tools.cli import create_parser, main
from gedcom_tools.commands.search import register_subcommand, run
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR

_FIXTURES = Path(__file__).parent / "fixtures"
_SAMPLE_GED = _FIXTURES / "555sample.ged"
_ROYAL_GED = _FIXTURES / "royal92.ged"


def _write_ged(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    p = tmp_path / filename
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n", encoding="utf-8")
    return p


def _args(
    file: Path,
    query: str,
    *,
    regex: bool = False,
    fuzzy_dates: int | None = None,
    limit: int | None = None,
    count: bool = False,
    format: str = "text",
    verbose: bool = False,
    quiet: bool = False,
    no_color: bool = True,
    phonetic: str = "soundex",
) -> argparse.Namespace:
    return argparse.Namespace(
        file=file,
        query=query,
        regex=regex,
        fuzzy_dates=fuzzy_dates,
        limit=limit,
        count=count,
        format=format,
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        phonetic=phonetic,
    )


_FAMILY_GED = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n1 BIRT\n2 DATE 1800\n"
    "0 @I2@ INDI\n1 NAME Mary /Jones/\n1 SEX F\n1 BIRT\n2 DATE 1830\n"
    "0 @I3@ INDI\n1 NAME James /Smith/\n1 SEX M\n1 BIRT\n2 DATE 1860\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestArgumentParsing:
    def test_search_registered_as_subcommand(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "tree.ged", "Smith"])
        assert args.command == "search"

    def test_positional_file_parsed(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "myfile.ged", "Smith"])
        assert args.file == Path("myfile.ged")

    def test_positional_query_parsed(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "myfile.ged", "surname:Jones"])
        assert args.query == "surname:Jones"

    def test_regex_flag_defaults_false(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith"])
        assert args.regex is False

    def test_regex_flag_set(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith", "--regex"])
        assert args.regex is True

    def test_fuzzy_dates_parsed(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "born:1850", "--fuzzy-dates", "5"])
        assert args.fuzzy_dates == 5

    def test_fuzzy_dates_defaults_none(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith"])
        assert args.fuzzy_dates is None

    def test_limit_parsed(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith", "--limit", "10"])
        assert args.limit == 10

    def test_limit_defaults_none(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith"])
        assert args.limit is None

    def test_count_flag_set(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith", "--count"])
        assert args.count is True

    def test_count_defaults_false(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        register_subcommand(subparsers)
        args = parser.parse_args(["search", "f.ged", "Smith"])
        assert args.count is False

    def test_global_format_json_via_main_parser(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--format", "json", "search", "f.ged", "Smith"])
        assert args.format == "json"

    def test_global_verbose_via_main_parser(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--verbose", "search", "f.ged", "Smith"])
        assert args.verbose is True

    def test_global_quiet_via_main_parser(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--quiet", "search", "f.ged", "Smith"])
        assert args.quiet is True

    def test_global_no_color_via_main_parser(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--no-color", "search", "f.ged", "Smith"])
        assert args.no_color is True


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_bare_name_search_finds_match(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n",
        )
        rc = run(_args(ged, "Smith"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Smith" in out

    def test_surname_exact_match(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @I2@ INDI\n1 NAME Anna /Smithson/\n",
        )
        rc = run(_args(ged, "surname=Smith"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Smith" in out
        assert "Smithson" not in out

    def test_soundex_finds_similar_surname(self, tmp_path: Path, capsys) -> None:
        # Schmidt and Smith share soundex S530
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Hans /Schmidt/\n1 SEX M\n",
        )
        rc = run(_args(ged, "surname~Smith"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Schmidt" in out

    def test_metaphone_finds_cross_language_match(self, tmp_path: Path, capsys) -> None:
        # Catherine/Katherine differ in soundex initial letter but match in metaphone
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Jane /Katherine/\n1 SEX F\n",
        )
        # Should NOT match with default soundex
        rc = run(_args(ged, "surname~Catherine"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Katherine" not in out

        # Should match with metaphone
        rc = run(_args(ged, "surname~Catherine", phonetic="metaphone"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Katherine" in out

    def test_date_range_search(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Early /Person/\n1 BIRT\n2 DATE 1810\n"
            "0 @I2@ INDI\n1 NAME Late /Person/\n1 BIRT\n2 DATE 1900\n",
        )
        rc = run(_args(ged, "born:1800-1850"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Early" in out
        assert "Late" not in out

    def test_place_substring_search(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME London /Person/\n"
            "1 BIRT\n2 PLAC London, England\n"
            "0 @I2@ INDI\n1 NAME Paris /Person/\n"
            "1 BIRT\n2 PLAC Paris, France\n",
        )
        rc = run(_args(ged, "place:England"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "London" in out
        assert "Paris" not in out

    def test_multiple_and_criteria_narrows_results(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n"
            "1 BIRT\n2 DATE 1850\n"
            "0 @I2@ INDI\n1 NAME Mary /Smith/\n1 SEX F\n"
            "1 BIRT\n2 DATE 1850\n",
        )
        rc = run(_args(ged, "surname:Smith sex:M"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "John" in out
        assert "Mary" not in out

    def test_no_matches_returns_success(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n",
        )
        rc = run(_args(ged, "surname:Nonexistent"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "No matches" in out

    def test_empty_file_returns_success(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "")
        rc = run(_args(ged, "Smith"))
        assert rc == EXIT_SUCCESS

    def test_no_matches_includes_tip(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "surname:Zymurgy"))
        out = capsys.readouterr().out
        assert "Tip:" in out

    def test_text_output_shows_file_header(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "Smith"))
        out = capsys.readouterr().out
        assert "File:" in out

    def test_text_output_shows_query(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "Smith"))
        out = capsys.readouterr().out
        assert "Query:" in out
        assert "Smith" in out

    def test_sex_filter(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Alice /Brown/\n1 SEX F\n"
            "0 @I2@ INDI\n1 NAME Bob /Brown/\n1 SEX M\n",
        )
        run(_args(ged, "sex:F"))
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "Bob" not in out

    def test_given_field_search(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME William /Jones/\n"
            "0 @I2@ INDI\n1 NAME Robert /Jones/\n",
        )
        run(_args(ged, "given:William"))
        out = capsys.readouterr().out
        assert "William" in out
        assert "Robert" not in out

    def test_result_count_shown_in_header(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n" "0 @I2@ INDI\n1 NAME Jane /Smith/\n",
        )
        run(_args(ged, "surname:Smith"))
        out = capsys.readouterr().out
        assert "2" in out

    def test_wildcard_asterisk_matches(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smythe/\n"
            "0 @I2@ INDI\n1 NAME Jane /Unrelated/\n",
        )
        run(_args(ged, "surname:Smy*"))
        out = capsys.readouterr().out
        assert "Smythe" in out
        assert "Unrelated" not in out


# ---------------------------------------------------------------------------
# Relationship + field matching
# ---------------------------------------------------------------------------


class TestRelationshipSearch:
    def test_ancestor_finds_descendants(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        rc = run(_args(ged, "ancestor:@I1@"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "James" in out

    def test_ancestor_excludes_root(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        run(_args(ged, "ancestor:@I1@"))
        out = capsys.readouterr().out
        assert "John Smith" not in out

    def test_ancestor_combined_with_surname(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        rc = run(_args(ged, "ancestor:@I1@ surname:Smith"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "James" in out
        # Mary Jones is a descendant but has surname Jones not Smith
        assert "Jones" not in out

    def test_descendant_finds_ancestors(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        rc = run(_args(ged, "descendant:@I3@"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        # I3's parents are I1 and I2
        assert "John" in out or "Mary" in out

    def test_invalid_xref_returns_usage_error(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        rc = run(_args(ged, "ancestor:@I999@"))
        assert rc == EXIT_USAGE_ERROR
        err = capsys.readouterr().err
        assert "@I999@" in err

    def test_invalid_xref_error_has_remediation(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        run(_args(ged, "ancestor:@I999@"))
        err = capsys.readouterr().err
        # Should tell user how to find the right xref
        assert (
            "search" in err.lower()
            or "identifier" in err.lower()
            or "found" in err.lower()
        )

    def test_ancestor_with_date_filter(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        # James (I3) born 1860, within range for ancestor:@I1@
        run(_args(ged, "ancestor:@I1@ born:1850-1900"))
        out = capsys.readouterr().out
        assert "James" in out

    def test_descendant_excludes_root(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        run(_args(ged, "descendant:@I3@"))
        out = capsys.readouterr().out
        assert "James Smith" not in out


# ---------------------------------------------------------------------------
# Mode interactions
# ---------------------------------------------------------------------------


class TestModeInteractions:
    def test_count_text_is_bare_integer(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n" "0 @I2@ INDI\n1 NAME Jane /Smith/\n",
        )
        run(_args(ged, "surname:Smith", count=True))
        out = capsys.readouterr().out.strip()
        assert out == "2"

    def test_count_json_outputs_count_key(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n" "0 @I2@ INDI\n1 NAME Jane /Smith/\n",
        )
        run(_args(ged, "surname:Smith", count=True, format="json"))
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data == {"count": 2}

    def test_count_zero_when_no_matches(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "surname:Xyz", count=True))
        out = capsys.readouterr().out.strip()
        assert out == "0"

    def test_count_reports_total_not_limited(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @I2@ INDI\n1 NAME Jane /Smith/\n"
            "0 @I3@ INDI\n1 NAME Jim /Smith/\n",
        )
        # --limit would cap results at 1, but --count should report the full total
        run(_args(ged, "surname:Smith", count=True, limit=1))
        out = capsys.readouterr().out.strip()
        assert out == "3"

    def test_limit_truncates_results(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Alice /Smith/\n"
            "0 @I2@ INDI\n1 NAME Bob /Smith/\n"
            "0 @I3@ INDI\n1 NAME Carol /Smith/\n",
        )
        run(_args(ged, "surname:Smith", limit=1))
        out = capsys.readouterr().out
        # Exactly one individual entry returned (not three)
        # Truncation notice should appear
        assert "limited to 1" in out

    def test_limit_sets_truncated_flag_in_json(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Alice /Smith/\n" "0 @I2@ INDI\n1 NAME Bob /Smith/\n",
        )
        run(_args(ged, "surname:Smith", limit=1, format="json"))
        data = json.loads(capsys.readouterr().out)
        assert data["truncated"] is True
        assert len(data["matches"]) == 1

    def test_no_truncation_when_limit_not_reached(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "surname:Smith", limit=10, format="json"))
        data = json.loads(capsys.readouterr().out)
        assert data["truncated"] is False

    def test_quiet_suppresses_headers(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "Smith", quiet=True))
        out = capsys.readouterr().out
        assert "File:" not in out
        assert "Query:" not in out
        assert "===" not in out

    def test_quiet_shows_names(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "Smith", quiet=True))
        out = capsys.readouterr().out
        assert "John Smith" in out

    def test_quiet_no_matches_returns_empty_output(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "surname:Xyz", quiet=True))
        out = capsys.readouterr().out.strip()
        assert out == ""

    def test_json_output_is_valid_json(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        rc = run(_args(ged, "Smith", format="json"))
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, dict)

    def test_json_output_structure(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "Smith", format="json"))
        data = json.loads(capsys.readouterr().out)
        assert "file" in data
        assert "query" in data
        assert "total_individuals" in data
        assert "match_count" in data
        assert "truncated" in data
        assert "matches" in data
        assert isinstance(data["matches"], list)

    def test_json_match_entry_structure(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n"
            "1 BIRT\n2 DATE 1850\n2 PLAC London\n",
        )
        run(_args(ged, "Smith", format="json"))
        data = json.loads(capsys.readouterr().out)
        assert len(data["matches"]) == 1
        match = data["matches"][0]
        assert "xref" in match
        assert "given_name" in match
        assert "surname" in match
        assert "match_details" in match
        assert isinstance(match["match_details"], list)

    def test_regex_mode_matches(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Smith/\n"
            "0 @I2@ INDI\n1 NAME Jane /Unrelated/\n",
        )
        run(_args(ged, r"name:Sm\w+", regex=True))
        out = capsys.readouterr().out
        assert "Smith" in out
        assert "Unrelated" not in out

    def test_fuzzy_dates_widens_range(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME Born /Earlier/\n1 BIRT\n2 DATE ABT 1855\n",
        )
        # Without fuzzy, 1850-1853 doesn't include 1855
        run(_args(ged, "born:1850-1853"))
        out_no_fuzzy = capsys.readouterr().out
        # With fuzzy=5, range extends to 1858
        run(_args(ged, "born:1850-1853", fuzzy_dates=5))
        out_fuzzy = capsys.readouterr().out
        assert "Earlier" not in out_no_fuzzy
        assert "Earlier" in out_fuzzy


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


class TestErrorMessages:
    def test_empty_query_returns_usage_error(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        rc = run(_args(ged, "   "))
        assert rc == EXIT_USAGE_ERROR
        err = capsys.readouterr().err
        assert "Error:" in err

    def test_empty_query_error_has_usage_hint(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, ""))
        err = capsys.readouterr().err
        assert "Usage:" in err or "usage:" in err.lower() or "gedcom-tools" in err

    def test_bad_date_format_returns_usage_error(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        rc = run(_args(ged, "born:notadate"))
        assert rc == EXIT_USAGE_ERROR
        err = capsys.readouterr().err
        assert "Error:" in err

    def test_bad_date_error_has_fix_suggestion(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "born:notadate"))
        err = capsys.readouterr().err
        # Should tell user correct format
        assert "YYYY" in err or "format" in err.lower()

    def test_phonetic_on_date_field_returns_usage_error(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        rc = run(_args(ged, "born~1850"))
        assert rc == EXIT_USAGE_ERROR

    def test_phonetic_on_date_error_is_helpful(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "born~1850"))
        err = capsys.readouterr().err
        assert "not supported" in err or "date" in err.lower()

    def test_invalid_xref_format_returns_usage_error(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        rc = run(_args(ged, "ancestor:I1"))
        assert rc == EXIT_USAGE_ERROR

    def test_invalid_xref_error_shows_correct_format(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        run(_args(ged, "ancestor:I1"))
        err = capsys.readouterr().err
        # Should show the @ delimited form
        assert "@I1@" in err

    def test_file_not_found_returns_error(self, tmp_path: Path, capsys) -> None:
        missing = tmp_path / "does_not_exist.ged"
        rc = run(_args(missing, "Smith"))
        assert rc != EXIT_SUCCESS
        err = capsys.readouterr().err
        assert err.strip()  # some error message present

    def test_unknown_field_returns_usage_error(self, tmp_path: Path, capsys) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        rc = run(_args(ged, "badfield:value"))
        assert rc == EXIT_USAGE_ERROR

    def test_unknown_field_error_lists_valid_fields(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "badfield:value"))
        err = capsys.readouterr().err
        # Should list valid fields in the error
        assert "surname" in err or "Valid fields" in err

    def test_reversed_date_range_error_suggests_fix(
        self, tmp_path: Path, capsys
    ) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        run(_args(ged, "born:1900-1800"))
        err = capsys.readouterr().err
        assert "Swap" in err or "swap" in err.lower() or "1800-1900" in err


# ---------------------------------------------------------------------------
# Regression tests with real files
# ---------------------------------------------------------------------------


class TestRegression:
    @pytest.mark.skipif(
        not _SAMPLE_GED.exists(),
        reason="555sample.ged not found",
    )
    def test_sample_search_williams(self, capsys) -> None:
        rc = run(_args(_SAMPLE_GED, "surname:Williams"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Williams" in out

    @pytest.mark.skipif(
        not _SAMPLE_GED.exists(),
        reason="555sample.ged not found",
    )
    def test_sample_search_no_crash(self, capsys) -> None:
        rc = run(_args(_SAMPLE_GED, "Smith"))
        assert rc == EXIT_SUCCESS

    @pytest.mark.skipif(
        not _SAMPLE_GED.exists(),
        reason="555sample.ged not found",
    )
    def test_sample_json_output_valid(self, capsys) -> None:
        rc = run(_args(_SAMPLE_GED, "Williams", format="json"))
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert "file" in data
        assert "query" in data
        assert "total_individuals" in data
        assert "match_count" in data
        assert "matches" in data

    @pytest.mark.skipif(
        not _SAMPLE_GED.exists(),
        reason="555sample.ged not found",
    )
    def test_sample_total_individuals_positive(self, capsys) -> None:
        run(_args(_SAMPLE_GED, "Williams", format="json"))
        data = json.loads(capsys.readouterr().out)
        assert data["total_individuals"] > 0

    @pytest.mark.skipif(
        not _SAMPLE_GED.exists(),
        reason="555sample.ged not found",
    )
    def test_sample_match_count_consistent(self, capsys) -> None:
        run(_args(_SAMPLE_GED, "surname:Williams", format="json"))
        data = json.loads(capsys.readouterr().out)
        assert data["match_count"] == len(data["matches"])

    @pytest.mark.skipif(
        not _SAMPLE_GED.exists(),
        reason="555sample.ged not found",
    )
    def test_sample_encoding_present_in_json(self, capsys) -> None:
        run(_args(_SAMPLE_GED, "Williams", format="json"))
        data = json.loads(capsys.readouterr().out)
        assert "encoding" in data
        assert "detected" in data["encoding"]

    @pytest.mark.skipif(
        not _ROYAL_GED.exists(),
        reason="royal92.ged not found",
    )
    def test_royal_search_victoria(self, capsys) -> None:
        rc = run(_args(_ROYAL_GED, "given:Victoria"))
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Victoria" in out

    @pytest.mark.skipif(
        not _ROYAL_GED.exists(),
        reason="royal92.ged not found",
    )
    def test_royal_json_match_xref_format(self, capsys) -> None:
        run(_args(_ROYAL_GED, "given:Victoria", format="json"))
        data = json.loads(capsys.readouterr().out)
        for match in data["matches"]:
            assert match["xref"].startswith("@")
            assert match["xref"].endswith("@")

    @pytest.mark.skipif(
        not _ROYAL_GED.exists(),
        reason="royal92.ged not found",
    )
    def test_royal_count_mode(self, capsys) -> None:
        run(_args(_ROYAL_GED, "given:Victoria", count=True))
        out = capsys.readouterr().out.strip()
        assert out.isdigit()
        assert int(out) > 0


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_success_with_matches(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        assert run(_args(ged, "Smith")) == EXIT_SUCCESS

    def test_success_with_no_matches(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        assert run(_args(ged, "surname:Zymurgy")) == EXIT_SUCCESS

    def test_query_parse_error_returns_usage_error(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        assert run(_args(ged, "")) == EXIT_USAGE_ERROR

    def test_unknown_field_returns_usage_error(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        assert run(_args(ged, "invalid_field:value")) == EXIT_USAGE_ERROR

    def test_file_not_found_returns_nonzero(self, tmp_path: Path) -> None:
        missing = tmp_path / "nowhere.ged"
        rc = run(_args(missing, "Smith"))
        assert rc != EXIT_SUCCESS

    def test_invalid_xref_in_query_returns_usage_error(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        # Malformed xref (missing @ delimiters) fails parse_query
        assert run(_args(ged, "ancestor:I1")) == EXIT_USAGE_ERROR

    def test_xref_not_in_file_returns_usage_error(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, _FAMILY_GED)
        assert run(_args(ged, "ancestor:@I999@")) == EXIT_USAGE_ERROR

    def test_via_main_cli_success(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME John /Smith/\n")
        rc = main(["--no-color", "search", str(ged), "Smith"])
        assert rc == EXIT_SUCCESS

    def test_via_main_cli_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.ged"
        rc = main(["--no-color", "search", str(missing), "Smith"])
        assert rc != EXIT_SUCCESS
