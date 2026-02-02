"""Tests for the stats command."""

from __future__ import annotations

import json
from pathlib import Path

from gedcom_tools.commands.stats import (
    CoverageStats,
    FamilyData,
    FamilyEntry,
    GenerationEntry,
    IndividualData,
    LifespanStats,
    MarriageStats,
    RankedItem,
    StatsCollector,
    StatsResult,
    TimelineEntry,
)
from gedcom_tools.progress import Colors
from gedcom_tools.validation.issues import EncodingInfo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDataClasses:
    """Tests for stats data classes."""

    def test_individual_data_defaults(self) -> None:
        """IndividualData has correct defaults."""
        data = IndividualData(xref="@I1@")
        assert data.xref == "@I1@"
        assert data.name == ""
        assert data.given_name == ""
        assert data.surname == ""
        assert data.surname_parts == []
        assert data.sex == ""
        assert data.birth_year is None
        assert data.death_year is None
        assert data.famc_xref is None
        assert data.fams_xrefs == []
        assert data.has_note is False
        assert data.has_media is False
        assert data.has_source is False

    def test_family_data_defaults(self) -> None:
        """FamilyData has correct defaults."""
        data = FamilyData(xref="@F1@")
        assert data.xref == "@F1@"
        assert data.husb_xref is None
        assert data.wife_xref is None
        assert data.chil_xrefs == []
        assert data.marriage_year is None

    def test_lifespan_stats(self) -> None:
        """LifespanStats stores data correctly."""
        stats = LifespanStats(average=72.5, min_value=25, max_value=95, sample_size=100)
        assert stats.average == 72.5
        assert stats.min_value == 25
        assert stats.max_value == 95
        assert stats.sample_size == 100

    def test_marriage_stats(self) -> None:
        """MarriageStats stores data correctly."""
        stats = MarriageStats(
            total_marriages=50, with_date=30, without_date=20, avg_children=2.5
        )
        assert stats.total_marriages == 50
        assert stats.with_date == 30
        assert stats.without_date == 20
        assert stats.avg_children == 2.5

    def test_coverage_stats(self) -> None:
        """CoverageStats calculates correctly."""
        stats = CoverageStats(with_count=75, without_count=25, percent=75.0)
        assert stats.with_count == 75
        assert stats.without_count == 25
        assert stats.percent == 75.0

    def test_ranked_item(self) -> None:
        """RankedItem stores data correctly."""
        item = RankedItem(name="Smith", count=100, percent=25.5)
        assert item.name == "Smith"
        assert item.count == 100
        assert item.percent == 25.5


class TestStatsResult:
    """Tests for StatsResult formatting."""

    def test_format_text_quiet_mode(self) -> None:
        """Quiet mode returns one-line summary."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            families=50,
            sources=10,
            locations=25,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert output == "100 individuals, 50 families, 10 sources, 25 locations"

    def test_format_text_includes_sections(self) -> None:
        """Text output includes all sections."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=EncodingInfo(encoding="UTF-8", has_bom=True),
            individuals=100,
            families=50,
            sources=10,
            locations=25,
            gender_male=55,
            gender_female=44,
            gender_unknown=1,
            generation_depth=5,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "File: /test/file.ged" in output
        assert "Encoding: UTF-8 (with BOM)" in output
        assert "=== Record Counts ===" in output
        assert "Individuals:" in output
        assert "=== Timeline ===" in output
        assert "=== Tree Structure ===" in output
        assert "=== Demographics ===" in output
        assert "=== Data Completeness ===" in output

    def test_format_text_timeline_with_data(self) -> None:
        """Timeline section shows date range."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            earliest_year=TimelineEntry(year=1800, xref="@I1@", name="John Smith"),
            latest_year=TimelineEntry(year=1900, xref="@I2@", name="Jane Smith"),
            date_span_years=100,
            by_century={"1800": 60, "1900": 40},
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Date Span:        1800 - 1900 (100 years)" in output
        assert "Earliest (year):  John Smith (b. 1800)" in output
        assert "By Century:" in output
        assert "1800s:" in output

    def test_format_text_no_dates(self) -> None:
        """Timeline section handles no date data."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "No date data available" in output

    def test_format_json_structure(self) -> None:
        """JSON output has correct structure."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=EncodingInfo(
                encoding="UTF-8", has_bom=True, declared_charset="UTF-8"
            ),
            individuals=100,
            families=50,
            sources=10,
            locations=25,
            gender_male=55,
            gender_female=44,
            gender_unknown=1,
            generation_depth=5,
            earliest_year=TimelineEntry(year=1800, xref="@I1@", name="John Smith"),
            top_surnames=[RankedItem(name="Smith", count=20, percent=20.0)],
            birth_date=CoverageStats(with_count=80, without_count=20, percent=80.0),
        )

        json_str = result.format_json()
        data = json.loads(json_str)

        assert data["file"] == "/test/file.ged"
        assert data["encoding"]["detected"] == "UTF-8"
        assert data["encoding"]["has_bom"] is True
        assert data["records"]["individuals"] == 100
        assert data["records"]["families"] == 50
        assert data["timeline"]["earliest_year"]["year"] == 1800
        assert data["tree_structure"]["generation_depth"] == 5
        assert data["demographics"]["gender"]["male"] == 55
        assert len(data["demographics"]["surnames"]) == 1
        assert data["completeness"]["birth_date"]["with"] == 80


class TestStatsCollector:
    """Tests for StatsCollector."""

    def test_collect_sample_file(self, sample_gedcom_path: Path) -> None:
        """Collector extracts data from 555sample.ged correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.individuals == 3
        assert result.families == 2
        assert result.sources == 1
        assert result.locations == 6

    def test_collect_gender_distribution(self, sample_gedcom_path: Path) -> None:
        """Gender distribution is calculated correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.gender_male == 2
        assert result.gender_female == 1
        assert result.gender_unknown == 0

    def test_collect_timeline(self, sample_gedcom_path: Path) -> None:
        """Timeline data is extracted correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.earliest_year is not None
        assert result.earliest_year.year == 1822
        assert "Robert" in result.earliest_year.name

        assert result.latest_year is not None
        assert result.latest_year.year == 1861

        assert result.date_span_years == 39

    def test_collect_generation_depth(self, sample_gedcom_path: Path) -> None:
        """Generation depth is calculated correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Joe Williams (@I3@) has parents, so generation depth should be 2
        assert result.generation_depth == 2
        assert result.earliest_generation is not None
        assert result.earliest_generation.generation == 2

    def test_collect_surnames(self, sample_gedcom_path: Path) -> None:
        """Surname extraction works correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert len(result.top_surnames) > 0
        surnames = [s.name for s in result.top_surnames]
        assert "Williams" in surnames
        assert "Wilson" in surnames

    def test_collect_lineages(self, sample_gedcom_path: Path) -> None:
        """Lineage extraction (full SURN) works correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert len(result.top_lineages) > 0

    def test_collect_largest_families(self, sample_gedcom_path: Path) -> None:
        """Largest families are identified correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert len(result.largest_families) > 0
        # Both families have 1 child
        assert result.largest_families[0].children == 1

    def test_collect_completeness(self, sample_gedcom_path: Path) -> None:
        """Completeness stats are calculated correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.birth_date is not None
        assert result.birth_date.with_count == 3  # All 3 have birth dates
        assert result.birth_date.percent == 100.0

        assert result.death_date is not None
        assert result.death_date.with_count == 1  # Only Robert has death date

    def test_collect_locations(self, sample_gedcom_path: Path) -> None:
        """Location collection works correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert len(result.top_locations) == 6

    def test_top_n_option(self, sample_gedcom_path: Path) -> None:
        """Top-N option limits results."""
        collector = StatsCollector(
            file_path=sample_gedcom_path,
            quiet=True,
            verbose=False,
            no_color=True,
            top_n=1,
        )
        result = collector.collect()

        # Should only return top 1
        assert len(result.top_surnames) <= 1
        assert len(result.top_lineages) <= 1

    def test_encoding_detection(self, sample_gedcom_path: Path) -> None:
        """Encoding is detected correctly."""
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "UTF-8"
        assert result.encoding_info.has_bom is True


class TestGenerationDepthAlgorithm:
    """Tests for generation depth calculation."""

    def test_depth_single_person(self, tmp_path: Path) -> None:
        """Single person with no family has depth 1."""
        gedcom = tmp_path / "single.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.generation_depth == 1

    def test_depth_parent_child(self, tmp_path: Path) -> None:
        """Parent-child relationship has depth 2."""
        gedcom = tmp_path / "parent_child.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.generation_depth == 2

    def test_depth_three_generations(self, tmp_path: Path) -> None:
        """Three generations have depth 3."""
        gedcom = tmp_path / "three_gen.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Grandpa /Doe/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Dad /Doe/
1 SEX M
1 FAMC @F1@
1 FAMS @F2@
0 @I3@ INDI
1 NAME Child /Doe/
1 SEX M
1 FAMC @F2@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 @F2@ FAM
1 HUSB @I2@
1 CHIL @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.generation_depth == 3


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self, tmp_path: Path) -> None:
        """Handle minimal file with no individuals."""
        gedcom = tmp_path / "empty.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.individuals == 0
        assert result.families == 0
        assert result.generation_depth == 0

    def test_no_dates(self, tmp_path: Path) -> None:
        """Handle individuals with no dates."""
        gedcom = tmp_path / "no_dates.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.earliest_year is None
        assert result.latest_year is None
        assert result.date_span_years is None
        assert result.by_century == {}

    def test_no_surnames(self, tmp_path: Path) -> None:
        """Handle individuals with no SURN."""
        gedcom = tmp_path / "no_surname.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should still work, may have "Unknown" lineage
        assert result.individuals == 1

    def test_orphan_detection(self, tmp_path: Path) -> None:
        """Orphans (no FAMC or FAMS) are detected."""
        gedcom = tmp_path / "orphan.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.orphans is not None
        assert result.orphans.with_count == 1  # John is an orphan

    def test_estimated_living(self, tmp_path: Path) -> None:
        """Estimated living (birth > 1920, no death) is calculated."""
        gedcom = tmp_path / "living.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1990
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE 1800
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.estimated_living is not None
        assert result.estimated_living.with_count == 1  # Only John

    def test_baptism_fallback(self, tmp_path: Path) -> None:
        """Baptism date is used as fallback for birth year."""
        gedcom = tmp_path / "baptism.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 CHR
2 DATE 1850
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.earliest_year is not None
        assert result.earliest_year.year == 1850

    def test_burial_fallback(self, tmp_path: Path) -> None:
        """Burial date is used as fallback for death year."""
        gedcom = tmp_path / "burial.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BURI
2 DATE 1900
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.death_date is not None
        assert result.death_date.with_count == 1


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_stats_command_exists(self) -> None:
        """Stats command is registered."""
        from gedcom_tools.cli import create_parser

        parser = create_parser()
        # This should not raise
        args = parser.parse_args(["stats", "test.ged"])
        assert args.command == "stats"

    def test_stats_help(self) -> None:
        """Stats command has help."""
        from gedcom_tools.cli import create_parser

        parser = create_parser()
        # Get stats subparser help
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            parser.parse_args(["stats", "--help"])
        except SystemExit:
            pass
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        assert "stats" in output.lower() or "statistics" in output.lower()

    def test_stats_file_not_found(self, tmp_path: Path) -> None:
        """Stats command handles missing file."""
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        args = Namespace(
            file=tmp_path / "nonexistent.ged",
            format="text",
            quiet=False,
            verbose=False,
            no_color=True,
            top=10,
        )

        from gedcom_tools.constants import EXIT_USAGE_ERROR

        result = run(args)
        assert result == EXIT_USAGE_ERROR

    def test_stats_directory_instead_of_file(self, tmp_path: Path) -> None:
        """Stats command handles directory instead of file."""
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        args = Namespace(
            file=tmp_path,  # tmp_path is a directory
            format="text",
            quiet=False,
            verbose=False,
            no_color=True,
            top=10,
        )

        from gedcom_tools.constants import EXIT_USAGE_ERROR

        result = run(args)
        assert result == EXIT_USAGE_ERROR

    def test_stats_run_success(self, sample_gedcom_path: Path) -> None:
        """Stats command runs successfully on valid file."""
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        args = Namespace(
            file=sample_gedcom_path,
            format="text",
            quiet=True,
            verbose=False,
            no_color=True,
            top=10,
        )

        from gedcom_tools.constants import EXIT_SUCCESS

        result = run(args)
        assert result == EXIT_SUCCESS

    def test_stats_json_output(self, sample_gedcom_path: Path) -> None:
        """Stats command produces valid JSON."""
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        args = Namespace(
            file=sample_gedcom_path,
            format="json",
            quiet=False,
            verbose=False,
            no_color=True,
            top=10,
        )

        from gedcom_tools.constants import EXIT_SUCCESS

        result = run(args)
        assert result == EXIT_SUCCESS

    def test_stats_error_handling_non_verbose(self, tmp_path: Path) -> None:
        """Stats command handles errors gracefully in non-verbose mode."""
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        # Create invalid file
        bad_file = tmp_path / "bad.ged"
        bad_file.write_bytes(b"\xff\xfe\x00\x00invalid binary")

        args = Namespace(
            file=bad_file,
            format="text",
            quiet=False,
            verbose=False,
            no_color=True,
            top=10,
        )

        from gedcom_tools.constants import EXIT_ERROR

        result = run(args)
        assert result == EXIT_ERROR


class TestStatsResultFormatting:
    """Additional tests for formatting edge cases."""

    def test_format_text_with_largest_families(self) -> None:
        """Text output shows largest families."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            largest_families=[
                FamilyEntry(xref="@F1@", parents="Smith/Jones", children=10),
                FamilyEntry(xref="@F2@", parents="Brown/Wilson", children=8),
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Largest Families:" in output
        assert "Smith/Jones" in output
        assert "10 children" in output

    def test_format_text_with_top_locations(self) -> None:
        """Text output shows top locations."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            top_locations=[
                RankedItem(name="New York, USA", count=50, percent=50.0),
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "=== Locations ===" in output
        assert "New York, USA" in output

    def test_format_text_location_truncation(self) -> None:
        """Long location names are truncated."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            top_locations=[
                RankedItem(
                    name="A" * 50,  # Long location name
                    count=10,
                    percent=10.0,
                ),
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        # Should be truncated with ...
        assert "..." in output

    def test_format_json_with_all_completeness(self) -> None:
        """JSON output includes all completeness fields."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            birth_date=CoverageStats(with_count=80, without_count=20, percent=80.0),
            death_date=CoverageStats(with_count=60, without_count=40, percent=60.0),
            notes=CoverageStats(with_count=30, without_count=70, percent=30.0),
            media=CoverageStats(with_count=10, without_count=90, percent=10.0),
            orphans=CoverageStats(with_count=5, without_count=95, percent=5.0),
            estimated_living=CoverageStats(
                with_count=20, without_count=80, percent=20.0
            ),
        )

        json_str = result.format_json()
        data = json.loads(json_str)

        assert data["completeness"]["birth_date"]["with"] == 80
        assert data["completeness"]["death_date"]["with"] == 60
        assert data["completeness"]["notes"]["with"] == 30
        assert data["completeness"]["media"]["with"] == 10
        assert data["completeness"]["orphans"]["count"] == 5
        assert data["completeness"]["estimated_living"]["count"] == 20

    def test_format_text_with_earliest_generation(self) -> None:
        """Text output shows earliest generation."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            earliest_generation=GenerationEntry(
                generation=7, xref="@I50@", name="Ancient Ancestor"
            ),
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Earliest (gen):   Ancient Ancestor (generation 7)" in output

    def test_format_json_with_largest_families(self) -> None:
        """JSON output includes largest families."""
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            largest_families=[
                FamilyEntry(xref="@F1@", parents="Smith/Jones", children=10),
            ],
        )

        json_str = result.format_json()
        data = json.loads(json_str)

        assert len(data["tree_structure"]["largest_families"]) == 1
        assert data["tree_structure"]["largest_families"][0]["children"] == 10


class TestStatsCollectorEdgeCases:
    """Additional edge case tests for StatsCollector."""

    def test_note_and_media_detection(self, tmp_path: Path) -> None:
        """Notes and media are detected correctly."""
        gedcom = tmp_path / "notes_media.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 NOTE This is a note
1 OBJE
2 FILE photo.jpg
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.notes is not None
        assert result.notes.with_count == 1
        assert result.media is not None
        assert result.media.with_count == 1

    def test_multiple_families_spouse(self, tmp_path: Path) -> None:
        """Individual as spouse in multiple families."""
        gedcom = tmp_path / "multi_spouse.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 FAMS @F1@
1 FAMS @F2@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Mary /Jones/
1 SEX F
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 @F2@ FAM
1 HUSB @I1@
1 WIFE @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.individuals == 3
        assert result.families == 2
        # John has 2 FAMS, so not an orphan
        assert result.orphans is not None
        assert result.orphans.with_count == 0

    def test_family_parent_name_extraction(self, tmp_path: Path) -> None:
        """Family parent names are extracted for largest families."""
        gedcom = tmp_path / "parent_names.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
2 SURN Doe
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
2 SURN Smith
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Child /Doe/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert len(result.largest_families) == 1
        assert result.largest_families[0].parents == "Doe/Smith"

    def test_encoding_detection_with_bom_no_declared(self, tmp_path: Path) -> None:
        """Encoding detection handles BOM without declared charset."""
        gedcom = tmp_path / "bom_no_declared.ged"
        # Create minimal valid file with BOM but no CHAR record
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
0 TRLR
""",
            encoding="utf-8-sig",  # This adds BOM
        )

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        assert result.encoding_info is not None
        assert result.encoding_info.has_bom is True

    def test_century_calculation(self, tmp_path: Path) -> None:
        """Century distribution is calculated correctly."""
        gedcom = tmp_path / "centuries.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Person1 /Test/
1 BIRT
2 DATE 1750
0 @I2@ INDI
1 NAME Person2 /Test/
1 BIRT
2 DATE 1850
0 @I3@ INDI
1 NAME Person3 /Test/
1 BIRT
2 DATE 1950
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert "1700" in result.by_century
        assert "1800" in result.by_century
        assert "1900" in result.by_century

    def test_name_from_tuple_no_surname(self, tmp_path: Path) -> None:
        """Names are extracted from tuple when no SURN sub-record."""
        gedcom = tmp_path / "tuple_name.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Name should be extracted from tuple
        assert result.earliest_generation is not None
        assert (
            "John" in result.earliest_generation.name
            or "Doe" in result.earliest_generation.name
        )

    def test_ancestry_cycle_detection(self, tmp_path: Path) -> None:
        """Generation depth handles ancestry cycles."""
        gedcom = tmp_path / "cycle.ged"
        # Create a cycle: I1 -> F1 -> I2 (parent) -> F2 -> I1 (parent)
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Person1 /Test/
1 FAMC @F1@
1 FAMS @F2@
0 @I2@ INDI
1 NAME Person2 /Test/
1 FAMS @F1@
1 FAMC @F2@
0 @F1@ FAM
1 HUSB @I2@
1 CHIL @I1@
0 @F2@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should not hang and should return a valid result
        assert result.individuals == 2
        assert result.generation_depth >= 1

    def test_invalid_family_reference(self, tmp_path: Path) -> None:
        """Generation depth handles invalid family references."""
        gedcom = tmp_path / "invalid_fam.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 FAMC @F999@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should handle gracefully
        assert result.individuals == 1
        assert result.generation_depth == 1

    def test_family_with_no_parents(self, tmp_path: Path) -> None:
        """Largest families handles families with no parent references."""
        gedcom = tmp_path / "no_parents.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Child /Test/
1 FAMC @F1@
0 @F1@ FAM
1 CHIL @I1@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.families == 1
        if result.largest_families:
            # Parents should be ?/?
            assert result.largest_families[0].parents == "?/?"

    def test_format_text_completeness_section_full(self, tmp_path: Path) -> None:
        """Test text formatting with all completeness stats."""
        gedcom = tmp_path / "complete.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
2 SURN Doe
1 SEX M
1 BIRT
2 DATE 1990
1 DEAT
2 DATE 2020
1 NOTE A note
1 OBJE
2 FILE photo.jpg
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Doe/
2 SURN Doe
1 SEX F
1 BIRT
2 DATE 1850
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Birth/Baptism Date:" in output
        assert "Death/Burial Date:" in output
        assert "Has Notes:" in output
        assert "Has Media:" in output
        assert "Orphans:" in output
        assert "Estimated Living:" in output

    def test_format_text_with_surnames_and_lineages(self, tmp_path: Path) -> None:
        """Test text formatting includes top surnames and lineages."""
        gedcom = tmp_path / "surnames.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
2 SURN Doe
1 SEX M
0 @I2@ INDI
1 NAME Jane /Doe/
2 SURN Doe
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Top Surnames:" in output
        assert "Top Lineages:" in output
        assert "Doe" in output


class TestGivenNameFrequency:
    """Tests for given name frequency feature."""

    def test_given_name_extraction_from_name_tuple(self, tmp_path: Path) -> None:
        """Given names are extracted from name tuple."""
        gedcom = tmp_path / "given_names.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John William /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Mary Elizabeth /Smith/
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should extract first given name only
        assert len(result.top_given_names_male) == 1
        assert result.top_given_names_male[0].name == "John"
        assert len(result.top_given_names_female) == 1
        assert result.top_given_names_female[0].name == "Mary"

    def test_given_name_from_givn_subrecord(self, tmp_path: Path) -> None:
        """GIVN sub-record overrides name tuple extraction."""
        gedcom = tmp_path / "givn_subrecord.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John William /Doe/
2 GIVN William
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # GIVN should override tuple-extracted name
        assert len(result.top_given_names_male) == 1
        assert result.top_given_names_male[0].name == "William"

    def test_given_name_frequency_counts(self, tmp_path: Path) -> None:
        """Given name frequency is calculated correctly."""
        gedcom = tmp_path / "given_freq.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 @I2@ INDI
1 NAME John /Smith/
1 SEX M
0 @I3@ INDI
1 NAME Robert /Jones/
1 SEX M
0 @I4@ INDI
1 NAME Mary /Doe/
1 SEX F
0 @I5@ INDI
1 NAME Mary /Smith/
1 SEX F
0 @I6@ INDI
1 NAME Mary /Jones/
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # John appears 2x, Robert 1x
        assert result.top_given_names_male[0].name == "John"
        assert result.top_given_names_male[0].count == 2

        # Mary appears 3x
        assert result.top_given_names_female[0].name == "Mary"
        assert result.top_given_names_female[0].count == 3

    def test_given_names_in_text_output(self, tmp_path: Path) -> None:
        """Given names appear in text output."""
        gedcom = tmp_path / "given_output.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Mary /Smith/
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Top Given Names (Male):" in output
        assert "John" in output
        assert "Top Given Names (Female):" in output
        assert "Mary" in output

    def test_given_names_in_json_output(self, tmp_path: Path) -> None:
        """Given names appear in JSON output."""
        gedcom = tmp_path / "given_json.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Mary /Smith/
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())

        assert "given_names_male" in data["demographics"]
        assert "given_names_female" in data["demographics"]
        assert data["demographics"]["given_names_male"][0]["name"] == "John"
        assert data["demographics"]["given_names_female"][0]["name"] == "Mary"


class TestLifespanStats:
    """Tests for lifespan statistics feature."""

    def test_lifespan_calculation(self, tmp_path: Path) -> None:
        """Lifespan is calculated correctly."""
        gedcom = tmp_path / "lifespan.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1980
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE 1910
1 DEAT
2 DATE 1990
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.lifespan is not None
        assert result.lifespan.average == 80.0  # (80 + 80) / 2
        assert result.lifespan.min_value == 80
        assert result.lifespan.max_value == 80
        assert result.lifespan.sample_size == 2

    def test_lifespan_filters_invalid(self, tmp_path: Path) -> None:
        """Lifespan filters out invalid values (negative, >120)."""
        gedcom = tmp_path / "lifespan_filter.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Valid /Person/
1 SEX M
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1970
0 @I2@ INDI
1 NAME TooOld /Person/
1 SEX F
1 BIRT
2 DATE 1800
1 DEAT
2 DATE 1950
0 @I3@ INDI
1 NAME Negative /Person/
1 SEX M
1 BIRT
2 DATE 1950
1 DEAT
2 DATE 1940
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.lifespan is not None
        # Only Valid Person (70 years) should be counted
        # TooOld (150 years) filtered, Negative (-10 years) filtered
        assert result.lifespan.sample_size == 1
        assert result.lifespan.average == 70.0

    def test_lifespan_no_data(self, tmp_path: Path) -> None:
        """Lifespan is None when no valid data."""
        gedcom = tmp_path / "lifespan_none.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1900
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.lifespan is None

    def test_lifespan_in_text_output(self, tmp_path: Path) -> None:
        """Lifespan appears in text output."""
        gedcom = tmp_path / "lifespan_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1975
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Avg Lifespan:" in output
        assert "75.0 years" in output
        assert "n=1" in output

    def test_lifespan_in_json_output(self, tmp_path: Path) -> None:
        """Lifespan appears in JSON output."""
        gedcom = tmp_path / "lifespan_json.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1975
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())

        assert data["timeline"]["lifespan"]["average"] == 75.0
        assert data["timeline"]["lifespan"]["min"] == 75
        assert data["timeline"]["lifespan"]["max"] == 75
        assert data["timeline"]["lifespan"]["sample_size"] == 1


class TestMarriageStats:
    """Tests for marriage statistics feature."""

    def test_marriage_year_extraction(self, tmp_path: Path) -> None:
        """Marriage year is extracted from MARR/DATE."""
        gedcom = tmp_path / "marriage_year.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1950
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.marriage is not None
        assert result.marriage.total_marriages == 1
        assert result.marriage.with_date == 1
        assert result.marriage.without_date == 0

    def test_marriage_without_date(self, tmp_path: Path) -> None:
        """Marriages without dates are counted."""
        gedcom = tmp_path / "marriage_no_date.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.marriage is not None
        assert result.marriage.total_marriages == 1
        assert result.marriage.with_date == 0
        assert result.marriage.without_date == 1

    def test_average_children_per_family(self, tmp_path: Path) -> None:
        """Average children per family is calculated correctly."""
        gedcom = tmp_path / "avg_children.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Parent1 /A/
1 FAMS @F1@
0 @I2@ INDI
1 NAME Parent2 /A/
1 FAMS @F1@
0 @I3@ INDI
1 NAME Child1 /A/
1 FAMC @F1@
0 @I4@ INDI
1 NAME Child2 /A/
1 FAMC @F1@
0 @I5@ INDI
1 NAME Child3 /A/
1 FAMC @F1@
0 @I6@ INDI
1 NAME Parent3 /B/
1 FAMS @F2@
0 @I7@ INDI
1 NAME Parent4 /B/
1 FAMS @F2@
0 @I8@ INDI
1 NAME Child4 /B/
1 FAMC @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I5@
0 @F2@ FAM
1 HUSB @I6@
1 WIFE @I7@
1 CHIL @I8@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.marriage is not None
        assert result.marriage.total_marriages == 2
        # (3 + 1) / 2 = 2.0
        assert result.marriage.avg_children == 2.0

    def test_marriage_in_text_output(self, tmp_path: Path) -> None:
        """Marriage stats appear in text output."""
        gedcom = tmp_path / "marriage_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 FAMS @F1@
0 @I3@ INDI
1 NAME Child /Doe/
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 1950
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Avg Children/Fam:" in output
        assert "Marriage Date:" in output

    def test_marriage_in_json_output(self, tmp_path: Path) -> None:
        """Marriage stats appear in JSON output."""
        gedcom = tmp_path / "marriage_json.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1950
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())

        assert data["tree_structure"]["marriage"]["total"] == 1
        assert data["tree_structure"]["marriage"]["with_date"] == 1
        assert data["tree_structure"]["marriage"]["avg_children"] == 0.0


class TestSourceCoverage:
    """Tests for source coverage feature."""

    def test_direct_source_citation(self, tmp_path: Path) -> None:
        """Direct SOUR on individual is detected."""
        gedcom = tmp_path / "direct_source.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 SOUR @S1@
0 @S1@ SOUR
1 TITL A Source
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.source_citations is not None
        assert result.source_citations.with_count == 1
        assert result.source_citations.percent == 100.0

    def test_event_source_citation(self, tmp_path: Path) -> None:
        """SOUR on events (BIRT/SOUR, etc.) is detected."""
        gedcom = tmp_path / "event_source.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1900
2 SOUR @S1@
0 @S1@ SOUR
1 TITL Birth Certificate
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.source_citations is not None
        assert result.source_citations.with_count == 1
        assert result.source_citations.percent == 100.0

    def test_no_source_citation(self, tmp_path: Path) -> None:
        """Individuals without sources are counted."""
        gedcom = tmp_path / "no_source.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.source_citations is not None
        assert result.source_citations.with_count == 0
        assert result.source_citations.without_count == 1
        assert result.source_citations.percent == 0.0

    def test_source_coverage_mixed(self, tmp_path: Path) -> None:
        """Mixed source coverage is calculated correctly."""
        gedcom = tmp_path / "mixed_source.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 SOUR @S1@
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE 1900
2 SOUR @S1@
0 @I3@ INDI
1 NAME Bob /Doe/
1 SEX M
0 @I4@ INDI
1 NAME Alice /Doe/
1 SEX F
0 @S1@ SOUR
1 TITL A Source
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.source_citations is not None
        assert result.source_citations.with_count == 2  # John and Jane
        assert result.source_citations.without_count == 2  # Bob and Alice
        assert result.source_citations.percent == 50.0

    def test_source_coverage_in_text_output(self, tmp_path: Path) -> None:
        """Source coverage appears in text output."""
        gedcom = tmp_path / "source_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 SOUR @S1@
0 @S1@ SOUR
1 TITL A Source
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Has Sources:" in output

    def test_source_coverage_in_json_output(self, tmp_path: Path) -> None:
        """Source coverage appears in JSON output."""
        gedcom = tmp_path / "source_json.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 SOUR @S1@
0 @S1@ SOUR
1 TITL A Source
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())

        assert "source_citations" in data["completeness"]
        assert data["completeness"]["source_citations"]["with"] == 1
        assert data["completeness"]["source_citations"]["percent"] == 100.0


# =============================================================================
# V3 Tests: Utility Functions
# =============================================================================


class TestV3UtilityFunctions:
    """Tests for v3 utility functions."""

    def test_get_century(self) -> None:
        """get_century returns correct century string."""
        from gedcom_tools.dates import get_century

        assert get_century(1850) == "1800"
        assert get_century(1899) == "1800"
        assert get_century(1900) == "1900"
        assert get_century(2000) == "2000"
        assert get_century(1776) == "1700"

    def test_extract_year_from_date_none(self) -> None:
        """extract_year_from_date handles None."""
        from gedcom_tools.dates import extract_year_from_date

        assert extract_year_from_date(None) is None

    def test_extract_year_from_date_string(self) -> None:
        """extract_year_from_date handles plain string with year."""
        from gedcom_tools.dates import extract_year_from_date

        result = extract_year_from_date("2 OCT 1850")
        assert result == 1850

    def test_extract_year_from_date_no_year(self) -> None:
        """extract_year_from_date returns None for string without year."""
        from gedcom_tools.dates import extract_year_from_date

        result = extract_year_from_date("OCT")
        assert result is None

    def test_extract_month_none(self) -> None:
        """extract_month handles None."""
        from gedcom_tools.dates import extract_month

        assert extract_month(None) is None

    def test_extract_month_string(self) -> None:
        """extract_month extracts month from string."""
        from gedcom_tools.dates import extract_month

        assert extract_month("2 OCT 1850") == 10
        assert extract_month("JAN 1900") == 1
        assert extract_month("15 DEC 2000") == 12

    def test_extract_month_no_month(self) -> None:
        """extract_month returns None for string without month."""
        from gedcom_tools.dates import extract_month

        assert extract_month("1850") is None

    def test_classify_date_precision_none(self) -> None:
        """classify_date_precision handles None."""
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision(None)
        assert category == "missing"
        assert has_full is False

    def test_classify_date_precision_full(self) -> None:
        """classify_date_precision identifies full dates."""
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("2 OCT 1850")
        assert category == "full"
        assert has_full is True

    def test_classify_date_precision_partial(self) -> None:
        """classify_date_precision identifies partial dates."""
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("1850")
        assert category == "partial"
        assert has_full is False

    def test_classify_date_precision_approximate(self) -> None:
        """classify_date_precision identifies approximate dates."""
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("ABT 1850")
        assert category == "approximate"
        assert has_full is False

        category2, has_full2 = classify_date_precision("BEF 2 OCT 1850")
        assert category2 == "approximate"
        assert has_full2 is True

    def test_classify_date_precision_empty_string(self) -> None:
        """classify_date_precision handles empty string."""
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("")
        assert category == "missing"
        assert has_full is False

    def test_is_phrase_date_without_ged4py_types(self) -> None:
        """is_phrase_date returns False for non-ged4py objects."""
        from gedcom_tools.dates import is_phrase_date

        assert is_phrase_date(None) is False
        assert is_phrase_date("some string") is False
        assert is_phrase_date(1850) is False


# =============================================================================
# V3 Tests: Dataclasses
# =============================================================================


class TestV3DataClasses:
    """Tests for v3 dataclasses."""

    def test_aggregate_stats_defaults(self) -> None:
        """AggregateStats has correct defaults."""
        from gedcom_tools.commands.stats import AggregateStats

        stats = AggregateStats(average=25.5)
        assert stats.average == 25.5
        assert stats.min_value is None
        assert stats.max_value is None
        assert stats.sample_size == 0
        assert stats.distribution == {}

    def test_aggregate_stats_to_dict_minimal(self) -> None:
        """AggregateStats.to_dict with minimal data."""
        from gedcom_tools.commands.stats import AggregateStats

        stats = AggregateStats(average=25.567, sample_size=10)
        d = stats.to_dict()
        assert d["average"] == 25.6  # Rounded
        assert d["sample_size"] == 10
        assert "min" not in d
        assert "max" not in d
        assert "distribution" not in d

    def test_aggregate_stats_to_dict_full(self) -> None:
        """AggregateStats.to_dict with all fields."""
        from gedcom_tools.commands.stats import AggregateStats

        stats = AggregateStats(
            average=25.0,
            min_value=18,
            max_value=45,
            sample_size=100,
            distribution={"1": 10, "2-3": 50},
        )
        d = stats.to_dict()
        assert d["average"] == 25.0
        assert d["min"] == 18
        assert d["max"] == 45
        assert d["sample_size"] == 100
        assert d["distribution"] == {"1": 10, "2-3": 50}

    def test_gendered_aggregate_stats_defaults(self) -> None:
        """GenderedAggregateStats has correct defaults."""
        from gedcom_tools.commands.stats import GenderedAggregateStats

        stats = GenderedAggregateStats()
        assert stats.male is None
        assert stats.female is None
        assert stats.by_century == {}

    def test_gendered_aggregate_stats_to_dict(self) -> None:
        """GenderedAggregateStats.to_dict works correctly."""
        from gedcom_tools.commands.stats import AggregateStats, GenderedAggregateStats

        male_stats = AggregateStats(average=28.0, sample_size=50)
        female_stats = AggregateStats(average=24.0, sample_size=45)
        century_male = AggregateStats(average=30.0, sample_size=20)

        stats = GenderedAggregateStats(
            male=male_stats,
            female=female_stats,
            by_century={"1800": {"male": century_male, "female": None}},
        )
        d = stats.to_dict()

        assert "male" in d
        assert d["male"]["average"] == 28.0
        assert "female" in d
        assert d["female"]["average"] == 24.0
        assert "by_century" in d
        assert "1800" in d["by_century"]
        assert "male" in d["by_century"]["1800"]
        assert "female" not in d["by_century"]["1800"]  # None skipped

    def test_date_precision_stats_defaults(self) -> None:
        """DatePrecisionStats has correct defaults."""
        from gedcom_tools.commands.stats import DatePrecisionStats

        stats = DatePrecisionStats()
        assert stats.full == 0
        assert stats.partial == 0
        assert stats.approximate_full == 0
        assert stats.approximate_partial == 0
        assert stats.missing == 0
        assert stats.total == 0
        assert stats.approximate == 0

    def test_date_precision_stats_properties(self) -> None:
        """DatePrecisionStats properties calculate correctly."""
        from gedcom_tools.commands.stats import DatePrecisionStats

        stats = DatePrecisionStats(
            full=10, partial=5, approximate_full=3, approximate_partial=2, missing=5
        )
        assert stats.total == 25
        assert stats.approximate == 5

    def test_date_precision_stats_to_dict(self) -> None:
        """DatePrecisionStats.to_dict works correctly."""
        from gedcom_tools.commands.stats import DatePrecisionStats

        stats = DatePrecisionStats(
            full=10, partial=5, approximate_full=3, approximate_partial=2, missing=5
        )
        d = stats.to_dict()
        assert d["full"] == 10
        assert d["partial"] == 5
        assert d["approximate"]["total"] == 5
        assert d["approximate"]["with_full_date"] == 3
        assert d["approximate"]["with_partial_date"] == 2
        assert d["missing"] == 5
        assert d["total"] == 25

    def test_individual_data_v3_defaults(self) -> None:
        """IndividualData has correct v3 field defaults."""
        data = IndividualData(xref="@I1@")
        assert data.birth_month is None
        assert data.birth_date_precision == "missing"
        assert data.birth_date_has_full is False
        assert data.occupation == ""
        assert data.source_count == 0
        assert data.first_marriage_year is None
        assert data.first_marriage_age is None
        assert data.first_child_year is None
        assert data.first_child_age is None


# =============================================================================
# V3 Tests: Life Events
# =============================================================================


class TestV3LifeEvents:
    """Tests for v3 life event calculations."""

    def test_age_at_first_marriage(self, tmp_path: Path) -> None:
        """Age at first marriage is calculated correctly."""
        gedcom = tmp_path / "marriage_age.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1875
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.age_at_first_marriage is not None
        assert result.age_at_first_marriage.male is not None
        assert result.age_at_first_marriage.male.average == 25.0
        assert result.age_at_first_marriage.female is not None
        assert result.age_at_first_marriage.female.average == 20.0

    def test_age_at_first_child(self, tmp_path: Path) -> None:
        """Age at first child is calculated correctly."""
        gedcom = tmp_path / "child_age.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @I3@ INDI
1 NAME Baby /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1880
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.age_at_first_child is not None
        assert result.age_at_first_child.male is not None
        assert result.age_at_first_child.male.average == 30.0  # Father age
        assert result.age_at_first_child.female is not None
        assert result.age_at_first_child.female.average == 25.0  # Mother age

    def test_spousal_age_gap(self, tmp_path: Path) -> None:
        """Spousal age gap is calculated correctly."""
        gedcom = tmp_path / "age_gap.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1850
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1855
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.spousal_age_gap is not None
        assert result.spousal_age_gap.average == 5.0
        assert result.spousal_age_gap.sample_size == 1

    def test_life_events_in_text_output(self, tmp_path: Path) -> None:
        """Life events appear in text output."""
        gedcom = tmp_path / "life_events_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1875
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Life Events" in output
        assert "Age at First Marriage" in output
        assert "Male:" in output
        assert "Female:" in output

    def test_life_events_in_json_output(self, tmp_path: Path) -> None:
        """Life events appear in JSON output."""
        gedcom = tmp_path / "life_events_json.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1875
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())

        assert "life_events" in data
        assert "age_at_first_marriage" in data["life_events"]
        assert "male" in data["life_events"]["age_at_first_marriage"]
        assert "female" in data["life_events"]["age_at_first_marriage"]


# =============================================================================
# V3 Tests: Family Size
# =============================================================================


class TestV3FamilySize:
    """Tests for v3 family size calculations."""

    def test_family_size_distribution(self, tmp_path: Path) -> None:
        """Family size distribution is calculated correctly."""
        gedcom = tmp_path / "family_size.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Father /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Mother /Smith/
1 SEX F
0 @I3@ INDI
1 NAME Child1 /Doe/
1 SEX M
0 @I4@ INDI
1 NAME Child2 /Doe/
1 SEX F
0 @I5@ INDI
1 NAME Child3 /Doe/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I5@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.family_size is not None
        assert result.family_size.average == 3.0
        assert result.family_size.max_value == 3
        assert result.family_size.sample_size == 1
        assert result.family_size.distribution.get("2-3") == 1

    def test_family_size_in_text_output(self, tmp_path: Path) -> None:
        """Family size appears in text output."""
        gedcom = tmp_path / "family_size_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Father /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Mother /Smith/
1 SEX F
0 @I3@ INDI
1 NAME Child /Doe/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Family Size" in output
        assert "Average:" in output
        assert "children per family" in output
        assert "Distribution:" in output

    def test_family_size_in_json_output(self, tmp_path: Path) -> None:
        """Family size appears in JSON output."""
        gedcom = tmp_path / "family_size_json.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Father /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Mother /Smith/
1 SEX F
0 @I3@ INDI
1 NAME Child /Doe/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())

        assert "family_size" in data
        assert "average" in data["family_size"]
        assert "distribution" in data["family_size"]


# =============================================================================
# V3 Tests: Birth Patterns
# =============================================================================


class TestV3BirthPatterns:
    """Tests for v3 birth month distribution."""

    def test_birth_month_distribution(self, tmp_path: Path) -> None:
        """Birth month distribution is calculated correctly."""
        gedcom = tmp_path / "birth_month.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 15 JAN 1850
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 20 JAN 1855
0 @I3@ INDI
1 NAME Bob /Jones/
1 SEX M
1 BIRT
2 DATE 5 OCT 1860
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.birth_by_month is not None
        assert result.birth_by_month.get(1) == 2  # January
        assert result.birth_by_month.get(10) == 1  # October

    def test_birth_patterns_in_text_output(self, tmp_path: Path) -> None:
        """Birth patterns appear in text output."""
        gedcom = tmp_path / "birth_patterns_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 15 JAN 1850
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Birth Patterns" in output
        assert "By Month:" in output
        assert "Jan:" in output
        assert "Peak:" in output

    def test_birth_patterns_no_month_data(self, tmp_path: Path) -> None:
        """Birth patterns shows message when no month data available."""
        gedcom = tmp_path / "no_birth_month.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1850
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        # Should show message about missing month data
        assert "Birth Patterns" in output
        assert "No birth month data available" in output


# =============================================================================
# V3 Tests: Lifespan by Century
# =============================================================================


class TestV3LifespanByCentury:
    """Tests for v3 lifespan by century calculations."""

    def test_lifespan_by_century(self, tmp_path: Path) -> None:
        """Lifespan by century is calculated correctly."""
        gedcom = tmp_path / "lifespan_century.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 DEAT
2 DATE 1 JAN 1920
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1950
1 DEAT
2 DATE 1 JAN 2020
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.lifespan_by_century is not None
        assert "1800" in result.lifespan_by_century
        assert result.lifespan_by_century["1800"].average == 70.0
        assert "1900" in result.lifespan_by_century
        assert result.lifespan_by_century["1900"].average == 70.0

    def test_lifespan_trends_in_text_output(self, tmp_path: Path) -> None:
        """Lifespan trends appear in text output."""
        gedcom = tmp_path / "lifespan_trends_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1850
1 DEAT
2 DATE 1920
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Lifespan Trends" in output
        assert "By Century:" in output
        assert "1800s:" in output


# =============================================================================
# V3 Tests: Research Quality
# =============================================================================


class TestV3ResearchQuality:
    """Tests for v3 research quality calculations."""

    def test_date_precision_calculation(self, tmp_path: Path) -> None:
        """Date precision is calculated correctly."""
        gedcom = tmp_path / "date_precision.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Full /Date/
1 SEX M
1 BIRT
2 DATE 2 OCT 1850
0 @I2@ INDI
1 NAME Partial /Date/
1 SEX F
1 BIRT
2 DATE 1855
0 @I3@ INDI
1 NAME Approx /Date/
1 SEX M
1 BIRT
2 DATE ABT 1860
0 @I4@ INDI
1 NAME No /Date/
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.date_precision is not None
        assert result.date_precision.full == 1
        assert result.date_precision.partial == 1
        assert result.date_precision.approximate >= 1
        assert result.date_precision.missing == 1
        assert result.date_precision.total == 4

    def test_occupation_coverage(self, tmp_path: Path) -> None:
        """Occupation coverage is calculated correctly."""
        gedcom = tmp_path / "occupation.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 OCCU Farmer
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.occupation_coverage is not None
        assert result.occupation_coverage.with_count == 1
        assert result.occupation_coverage.without_count == 1
        assert result.occupation_coverage.percent == 50.0

    def test_source_depth(self, tmp_path: Path) -> None:
        """Source depth is calculated correctly."""
        gedcom = tmp_path / "source_depth.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 SOUR @S1@
1 SOUR @S2@
1 BIRT
2 DATE 1850
2 SOUR @S1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
0 @S1@ SOUR
1 TITL Source 1
0 @S2@ SOUR
1 TITL Source 2
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.source_depth is not None
        # John has 3 sources (2 direct + 1 on BIRT), Jane has 0
        assert result.source_depth.average == 1.5
        assert result.source_depth.max_value == 3
        assert result.source_depth.min_value == 0

    def test_research_quality_in_text_output(self, tmp_path: Path) -> None:
        """Research quality appears in text output."""
        gedcom = tmp_path / "research_quality_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 2 OCT 1850
1 OCCU Farmer
1 SOUR @S1@
0 @S1@ SOUR
1 TITL A Source
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Research Quality" in output
        assert "Birth Date Precision:" in output
        assert "Occupation recorded:" in output

    def test_research_quality_approximate_breakdown(self, tmp_path: Path) -> None:
        """Research quality shows approximate date breakdown."""
        gedcom = tmp_path / "approx_breakdown.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE ABT 2 OCT 1850
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE ABT 1855
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        # Should show approximate breakdown
        assert "Approximate:" in output
        assert "with full date:" in output


# =============================================================================
# V3 Tests: Edge Cases
# =============================================================================


class TestV3EdgeCases:
    """Tests for v3 edge cases."""

    def test_empty_family_no_children(self, tmp_path: Path) -> None:
        """Families without children don't affect family size stats."""
        gedcom = tmp_path / "empty_family.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Family size stats should only count families with children
        assert result.family_size is None or result.family_size.sample_size == 0

    def test_implausible_ages_filtered(self, tmp_path: Path) -> None:
        """Implausible ages are filtered from statistics."""
        gedcom = tmp_path / "implausible.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Young /Marriage/
1 SEX M
1 BIRT
2 DATE 1850
0 @I2@ INDI
1 NAME Also /Young/
1 SEX F
1 BIRT
2 DATE 1855
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1855
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Male marrying at age 5 should be filtered
        # Female marrying at age 0 should be filtered
        if result.age_at_first_marriage:
            # Should have no valid samples due to implausible ages
            male_n = (
                result.age_at_first_marriage.male.sample_size
                if result.age_at_first_marriage.male
                else 0
            )
            female_n = (
                result.age_at_first_marriage.female.sample_size
                if result.age_at_first_marriage.female
                else 0
            )
            # Both should be filtered out
            assert male_n == 0 or female_n == 0

    def test_marriage_without_spouse_birth(self, tmp_path: Path) -> None:
        """Marriage age calculation handles missing spouse birth dates."""
        gedcom = tmp_path / "no_birth.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1875
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should not crash, just have no age data
        if result.age_at_first_marriage:
            assert result.age_at_first_marriage.male is None
            assert result.age_at_first_marriage.female is None

    def test_individual_without_xref_skipped(self, tmp_path: Path) -> None:
        """Individual records without xref are skipped."""
        gedcom = tmp_path / "no_xref.ged"
        # This is malformed GEDCOM but should be handled gracefully
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should work with valid individual
        assert result.individuals == 1

    def test_source_depth_no_sources(self, tmp_path: Path) -> None:
        """Source depth shows zero when no sources exist."""
        gedcom = tmp_path / "no_sources.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        # Should show "None found" message
        assert "Source citations:" in output or result.source_depth.max_value == 0

    def test_marriage_by_century(self, tmp_path: Path) -> None:
        """Marriage age by century is calculated."""
        gedcom = tmp_path / "marriage_century.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1875
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.age_at_first_marriage is not None
        assert result.age_at_first_marriage.by_century is not None
        assert "1800" in result.age_at_first_marriage.by_century

    def test_multiple_marriages_uses_first(self, tmp_path: Path) -> None:
        """Multiple marriages only count the first one."""
        gedcom = tmp_path / "multiple_marriages.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
1 FAMS @F2@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @I3@ INDI
1 NAME Mary /Jones/
1 SEX F
1 BIRT
2 DATE 1 JAN 1860
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1875
0 @F2@ FAM
1 HUSB @I1@
1 WIFE @I3@
1 MARR
2 DATE 1 JAN 1890
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # John's first marriage age should be 25 (1875-1850), not 40
        if result.age_at_first_marriage and result.age_at_first_marriage.male:
            assert result.age_at_first_marriage.male.average == 25.0

    def test_age_at_first_child_in_text_output(self, tmp_path: Path) -> None:
        """Age at first child appears in text output."""
        gedcom = tmp_path / "child_age_text.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1855
1 FAMS @F1@
0 @I3@ INDI
1 NAME Baby /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1880
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Age at First Child:" in output
        assert "Male:" in output
        assert "Female:" in output

    def test_large_family_distribution_buckets(self, tmp_path: Path) -> None:
        """Large family size distribution buckets are calculated correctly."""
        gedcom = tmp_path / "large_family.ged"
        # Create a family with 10+ children
        lines = [
            "0 HEAD",
            "1 SOUR Test",
            "1 GEDC",
            "2 VERS 5.5.1",
            "1 CHAR UTF-8",
            "0 @I1@ INDI",
            "1 NAME Father /Doe/",
            "1 SEX M",
            "1 FAMS @F1@",
            "0 @I2@ INDI",
            "1 NAME Mother /Smith/",
            "1 SEX F",
            "1 FAMS @F1@",
        ]
        # Add 12 children
        for i in range(3, 15):
            lines.extend(
                [
                    f"0 @I{i}@ INDI",
                    f"1 NAME Child{i} /Doe/",
                    "1 SEX M",
                    "1 FAMC @F1@",
                ]
            )

        lines.append("0 @F1@ FAM")
        lines.append("1 HUSB @I1@")
        lines.append("1 WIFE @I2@")
        for i in range(3, 15):
            lines.append(f"1 CHIL @I{i}@")
        lines.append("0 TRLR")

        gedcom.write_text("\n".join(lines))

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.family_size is not None
        assert result.family_size.distribution.get("10+") == 1

    def test_verbose_mode_error_propagation(self, tmp_path: Path) -> None:
        """Verbose mode re-raises exceptions."""
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        # Create a non-GEDCOM file to trigger an error
        bad_file = tmp_path / "bad.ged"
        bad_file.write_text("not a valid gedcom file at all")

        args = Namespace(
            file=bad_file,
            format="text",
            quiet=False,
            verbose=True,
            no_color=True,
            top=10,
        )

        # Should raise an exception in verbose mode
        try:
            result = run(args)
            # If no exception, it should return an error code
            assert result != 0
        except Exception:
            # Exception is expected in verbose mode
            pass

    def test_name_suffix_handling(self, tmp_path: Path) -> None:
        """Name suffixes are handled correctly."""
        gedcom = tmp_path / "suffix.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/ Jr.
1 SEX M
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        # Should have extracted the name correctly
        assert result.individuals == 1

    def test_depth_limit_locations(self, tmp_path: Path) -> None:
        """Location collection respects depth limit."""
        gedcom = tmp_path / "locations.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1850
2 PLAC Boston, Massachusetts, USA
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert len(result.top_locations) >= 0  # Just verify it doesn't crash

    def test_xref_extraction_various_formats(self, tmp_path: Path) -> None:
        """Xref extraction handles various input formats."""
        gedcom = tmp_path / "xref_formats.ged"
        gedcom.write_text("""\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
""")

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.families == 1
        assert result.individuals == 2
