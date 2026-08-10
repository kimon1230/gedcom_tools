from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from gedcom_tools.commands.stats import collector as stats_collector
from gedcom_tools.constants import EXIT_ERROR
from gedcom_tools.progress import Colors
from gedcom_tools.utils import EncodingInfo

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# StatsCollector builds a GedcomLanguageDetector for any file with INDI or FAM
# records, and on a cold cache that pulls a 126 MB model off a CDN. Nearly every
# test in here goes down that path, so the whole module runs against the stub
# from conftest; the handful of tests that care what the detector says install
# their own. See tests/conftest.py::_fast_lingua.
pytestmark = pytest.mark.usefixtures("_fast_lingua")


def _collector(ged: Path, *, top_n: int = 10) -> StatsCollector:
    """Build a collector for tests that need to inspect it after collection."""
    return StatsCollector(
        file_path=ged, quiet=True, verbose=False, no_color=True, top_n=top_n
    )


def _collect(ged: Path, *, top_n: int = 10) -> StatsResult:
    return _collector(ged, top_n=top_n).collect()


class TestDataClasses:

    def test_individual_data_defaults(self) -> None:
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
        data = FamilyData(xref="@F1@")
        assert data.xref == "@F1@"
        assert data.husb_xref is None
        assert data.wife_xref is None
        assert data.chil_xrefs == []
        assert data.marriage_year is None

    def test_lifespan_stats(self) -> None:
        stats = LifespanStats(average=72.5, min_value=25, max_value=95, sample_size=100)
        assert stats.average == 72.5
        assert stats.min_value == 25
        assert stats.max_value == 95
        assert stats.sample_size == 100

    def test_marriage_stats(self) -> None:
        stats = MarriageStats(
            total_marriages=50, with_date=30, without_date=20, avg_children=2.5
        )
        assert stats.total_marriages == 50
        assert stats.with_date == 30
        assert stats.without_date == 20
        assert stats.avg_children == 2.5

    def test_coverage_stats(self) -> None:
        stats = CoverageStats(with_count=75, without_count=25, percent=75.0)
        assert stats.with_count == 75
        assert stats.without_count == 25
        assert stats.percent == 75.0

    def test_ranked_item(self) -> None:
        item = RankedItem(name="Smith", count=100, percent=25.5)
        assert item.name == "Smith"
        assert item.count == 100
        assert item.percent == 25.5

    def test_aggregate_stats_defaults(self) -> None:
        from gedcom_tools.commands.stats import AggregateStats

        stats = AggregateStats(average=25.5)
        assert stats.average == 25.5
        assert stats.min_value is None
        assert stats.max_value is None
        assert stats.sample_size == 0
        assert stats.distribution == {}

    def test_aggregate_stats_to_dict_minimal(self) -> None:
        from gedcom_tools.commands.stats import AggregateStats

        stats = AggregateStats(average=25.567, sample_size=10)
        d = stats.to_dict()
        assert d["average"] == 25.6  # Rounded
        assert d["sample_size"] == 10
        assert "min" not in d
        assert "max" not in d
        assert "distribution" not in d

    def test_aggregate_stats_to_dict_full(self) -> None:
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
        from gedcom_tools.commands.stats import GenderedAggregateStats

        stats = GenderedAggregateStats()
        assert stats.male is None
        assert stats.female is None
        assert stats.by_century == {}

    def test_gendered_aggregate_stats_to_dict(self) -> None:
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
        from gedcom_tools.commands.stats import DatePrecisionStats

        stats = DatePrecisionStats(
            full=10, partial=5, approximate_full=3, approximate_partial=2, missing=5
        )
        assert stats.total == 25
        assert stats.approximate == 5

    def test_date_precision_stats_to_dict(self) -> None:
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

    def test_individual_data_extended_fields(self) -> None:
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


class TestResultOutput:

    def test_format_text_quiet_mode(self) -> None:
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
        assert (
            output
            == "100 individuals, 50 families, 10 sources, 25 locations, 0 language(s)"
        )

    def test_format_text_includes_sections(self) -> None:
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
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "No date data available" in output

    def test_format_json_structure(self) -> None:
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
        assert data["timeline"]["earliest_year"]["xref"] == "@I1@"
        assert "name" not in data["timeline"]["earliest_year"]
        assert data["filename"] == "file.ged"
        assert data["tree_structure"]["generation_depth"] == 5
        assert data["demographics"]["gender"]["male"] == 55
        assert len(data["demographics"]["surnames"]) == 1
        assert data["demographics"]["surnames"][0]["name"] == "Smith"
        assert data["demographics"]["surnames"][0]["count"] == 20
        assert data["demographics"]["surnames"][0]["percent"] == 20.0
        assert data["completeness"]["birth_date"]["with"] == 80

    def test_format_text_with_largest_families(self) -> None:
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

        assert "..." in output

    def test_format_json_with_all_completeness(self) -> None:
        result = StatsResult(
            file_path="/test/file.ged",
            encoding_info=None,
            individuals=100,
            birth_date=CoverageStats(with_count=80, without_count=20, percent=80.0),
            death_date=CoverageStats(with_count=60, without_count=40, percent=60.0),
            notes=CoverageStats(with_count=30, without_count=70, percent=30.0),
            media=CoverageStats(with_count=10, without_count=90, percent=10.0),
            isolated=CoverageStats(with_count=5, without_count=95, percent=5.0),
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
        assert data["completeness"]["isolated"]["count"] == 5
        assert data["completeness"]["estimated_living"]["count"] == 20

    def test_format_text_with_earliest_generation(self) -> None:
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


class TestCollectorBasic:

    def test_collect_sample_file(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert result.individuals == 3
        assert result.families == 2
        assert result.sources == 1
        assert result.locations == 6

    def test_collect_gender_distribution(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert result.gender_male == 2
        assert result.gender_female == 1
        assert result.gender_unknown == 0

    def test_collect_timeline(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert result.earliest_year is not None
        assert result.earliest_year.year == 1822
        assert "Robert" in result.earliest_year.name

        assert result.latest_year is not None
        assert result.latest_year.year == 1861

        assert result.date_span_years == 39

    def test_collect_generation_depth(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        # Joe Williams (@I3@) has parents, so generation depth should be 2
        assert result.generation_depth == 2
        assert result.earliest_generation is not None
        assert result.earliest_generation.generation == 2

    def test_collect_surnames(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert len(result.top_surnames) > 0
        surnames = [s.name for s in result.top_surnames]
        assert "Williams" in surnames
        assert "Wilson" in surnames

    def test_collect_lineages(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert len(result.top_lineages) > 0

    def test_collect_largest_families(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert len(result.largest_families) > 0
        # Both families have 1 child
        assert result.largest_families[0].children == 1

    def test_collect_completeness(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert result.birth_date is not None
        assert result.birth_date.with_count == 3  # All 3 have birth dates
        assert result.birth_date.percent == 100.0

        assert result.death_date is not None
        assert result.death_date.with_count == 1  # Only Robert has death date

    def test_collect_locations(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert len(result.top_locations) == 6
        location_names = [loc.name for loc in result.top_locations]
        assert all(name for name in location_names)  # No empty names
        assert any("Connecticut" in name for name in location_names)

    def test_top_n_option(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path, top_n=1)

        assert len(result.top_surnames) <= 1
        assert len(result.top_lineages) <= 1

    def test_encoding_detection(self, sample_gedcom_path: Path) -> None:
        result = _collect(sample_gedcom_path)

        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "UTF-8"
        assert result.encoding_info.has_bom is True

    def test_depth_single_person(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "single.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.generation_depth == 1

    def test_depth_parent_child(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "parent_child.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.generation_depth == 2

    def test_depth_three_generations(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "three_gen.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.generation_depth == 3


def _write_father_chain(path: Path, generations: int) -> None:
    """Write a pedigree that is a single unbroken father chain.

    @I1@ is the youngest; @I{generations}@ is the apical ancestor.
    """
    lines = ["0 HEAD", "1 SOUR Test", "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8"]

    for i in range(1, generations + 1):
        lines.append(f"0 @I{i}@ INDI")
        lines.append(f"1 NAME Person{i} /Chain/")
        lines.append("1 SEX M")
        if i < generations:
            lines.append(f"1 FAMC @F{i}@")
        if i > 1:
            lines.append(f"1 FAMS @F{i - 1}@")

    for i in range(1, generations):
        lines.append(f"0 @F{i}@ FAM")
        lines.append(f"1 HUSB @I{i + 1}@")
        lines.append(f"1 CHIL @I{i}@")

    lines.append("0 TRLR")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestGenerationDepthTraversal:

    def test_very_long_chain_does_not_overflow_stack(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "deep_chain.ged"
        _write_father_chain(gedcom, 3000)

        result = _collect(gedcom)

        assert result.generation_depth == 3000
        assert result.earliest_generation is not None
        assert result.earliest_generation.xref == "@I1@"

    def test_shared_ancestor_depth_is_order_independent(self, tmp_path: Path) -> None:
        # @S1@ is an ancestor of @X1@ twice over: once as the father (a
        # single hop) and once through a four-generation maternal line.
        gedcom = tmp_path / "pedigree_collapse.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @A1@ INDI
1 NAME Apex /Collapse/
1 SEX M
1 FAMS @FA1@
0 @A2@ INDI
1 NAME Second /Collapse/
1 SEX M
1 FAMC @FA1@
1 FAMS @FA2@
0 @A3@ INDI
1 NAME Third /Collapse/
1 SEX M
1 FAMC @FA2@
1 FAMS @FA3@
0 @S1@ INDI
1 NAME Shared /Collapse/
1 SEX M
1 FAMC @FA3@
1 FAMS @FM1@
1 FAMS @FX1@
0 @M1@ INDI
1 NAME Mother1 /Collapse/
1 SEX F
1 FAMC @FM1@
1 FAMS @FM2@
0 @M2@ INDI
1 NAME Mother2 /Collapse/
1 SEX F
1 FAMC @FM2@
1 FAMS @FM3@
0 @M3@ INDI
1 NAME Mother3 /Collapse/
1 SEX F
1 FAMC @FM3@
1 FAMS @FX1@
0 @X1@ INDI
1 NAME Descendant /Collapse/
1 SEX F
1 FAMC @FX1@
0 @FA1@ FAM
1 HUSB @A1@
1 CHIL @A2@
0 @FA2@ FAM
1 HUSB @A2@
1 CHIL @A3@
0 @FA3@ FAM
1 HUSB @A3@
1 CHIL @S1@
0 @FM1@ FAM
1 HUSB @S1@
1 CHIL @M1@
0 @FM2@ FAM
1 WIFE @M1@
1 CHIL @M2@
0 @FM3@ FAM
1 WIFE @M2@
1 CHIL @M3@
0 @FX1@ FAM
1 HUSB @S1@
1 WIFE @M3@
1 CHIL @X1@
0 TRLR
""",
            encoding="utf-8",
        )

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.generation_depth == 8
        assert result.earliest_generation is not None
        assert result.earliest_generation.xref == "@X1@"

        # The shared ancestor holds a node property, not a traversal
        # counter, so the memo must come out identical whichever end of
        # the file the outer loop starts from.
        forward: dict[str, int] = {}
        for xref in collector.individuals:
            collector._compute_generation_depth(xref, forward)

        backward: dict[str, int] = {}
        for xref in reversed(list(collector.individuals)):
            collector._compute_generation_depth(xref, backward)

        assert forward == backward
        assert forward["@S1@"] == 4
        assert forward["@M3@"] == 7
        assert forward["@X1@"] == 8

    def test_parent_cycle_terminates(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "cycle.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME First /Loop/
1 SEX M
1 FAMC @F2@
1 FAMS @F1@
0 @I2@ INDI
1 NAME Second /Loop/
1 SEX M
1 FAMC @F1@
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 @F2@ FAM
1 HUSB @I2@
1 CHIL @I1@
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.generation_depth == 2

    def test_self_parent_cycle_terminates(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "self_parent.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Own /Father/
1 SEX M
1 FAMC @F1@
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I1@
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.generation_depth == 1

    def test_five_generation_tree(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "five_gen.ged"
        _write_father_chain(gedcom, 5)

        result = _collect(gedcom)

        assert result.generation_depth == 5

    def test_individual_without_famc_is_depth_one(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_famc.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Alone /Rootless/
1 SEX F
0 @I2@ INDI
1 NAME Also /Rootless/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.generation_depth == 1
        assert collector._parent_xrefs("@I1@") == []

    def test_famc_pointing_at_missing_family_is_depth_one(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "dangling_famc.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Orphan /Pointer/
1 SEX M
1 FAMC @F99@
0 TRLR
""",
            encoding="utf-8",
        )

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()

        assert result.generation_depth == 1
        assert collector._parent_xrefs("@I1@") == []

    def test_famc_family_without_parents_is_depth_one(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "childless_parents.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Only /Child/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 CHIL @I1@
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.generation_depth == 1

    def test_unknown_xref_has_no_parents(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lookup.ged"
        _write_father_chain(gedcom, 2)

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        collector.collect()

        assert collector._parent_xrefs("@NOPE@") == []

    def test_memo_is_reused_across_calls(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "memo.ged"
        _write_father_chain(gedcom, 4)

        collector = StatsCollector(
            file_path=gedcom, quiet=True, verbose=False, no_color=True
        )
        collector.collect()

        memo: dict[str, int] = {}
        assert collector._compute_generation_depth("@I1@", memo) == 4
        assert memo == {"@I1@": 4, "@I2@": 3, "@I3@": 2, "@I4@": 1}

        # Second call for an already-resolved xref is a pure cache hit.
        assert collector._compute_generation_depth("@I3@", memo) == 2
        assert len(memo) == 4


class TestEdgeCases:

    def test_empty_file(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "empty.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 0
        assert result.families == 0
        assert result.generation_depth == 0

    def test_no_dates(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_dates.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.earliest_year is None
        assert result.latest_year is None
        assert result.date_span_years is None
        assert result.by_century == {}

    def test_no_surnames(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_surname.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 1

    def test_isolated_detection(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "orphan.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.isolated is not None
        assert result.isolated.with_count == 1  # John is isolated

    def test_estimated_living(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "living.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.estimated_living is not None
        assert result.estimated_living.with_count == 1  # Only John

    def test_baptism_fallback(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "baptism.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.earliest_year is not None
        assert result.earliest_year.year == 1850

    def test_burial_fallback(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "burial.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.death_date is not None
        assert result.death_date.with_count == 1

    def test_note_and_media_detection(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "notes_media.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.notes is not None
        assert result.notes.with_count == 1
        assert result.media is not None
        assert result.media.with_count == 1

    def test_multiple_families_spouse(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "multi_spouse.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 3
        assert result.families == 2
        # John has 2 FAMS, so not isolated
        assert result.isolated is not None
        assert result.isolated.with_count == 0

    def test_family_parent_name_extraction(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "parent_names.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert len(result.largest_families) == 1
        assert result.largest_families[0].parents == "Doe/Smith"

    def test_encoding_detection_with_bom_no_declared(self, tmp_path: Path) -> None:
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

        result = _collect(gedcom)
        assert result.encoding_info is not None
        assert result.encoding_info.has_bom is True

    def test_century_calculation(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "centuries.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert "1700" in result.by_century
        assert "1800" in result.by_century
        assert "1900" in result.by_century

    def test_name_from_tuple_no_surname(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "tuple_name.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.earliest_generation is not None
        assert (
            "John" in result.earliest_generation.name
            or "Doe" in result.earliest_generation.name
        )

    def test_ancestry_cycle_detection(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "cycle.ged"
        # Create a cycle: I1 -> F1 -> I2 (parent) -> F2 -> I1 (parent)
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 2
        assert result.generation_depth >= 1

    def test_invalid_family_reference(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "invalid_fam.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 FAMC @F999@
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 1
        assert result.generation_depth == 1

    def test_family_with_no_parents(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_parents.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.families == 1
        if result.largest_families:
            # Parents should be ?/?
            assert result.largest_families[0].parents == "?/?"

    def test_format_text_completeness_section_full(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "complete.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Birth/Baptism Date:" in output
        assert "Death/Burial Date:" in output
        assert "Has Notes:" in output
        assert "Has Media:" in output
        assert "Isolated:" in output
        assert "Estimated Living:" in output

    def test_format_text_with_surnames_and_lineages(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "surnames.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Top Surnames:" in output
        assert "Top Lineages:" in output
        assert "Doe" in output

    def test_empty_family_no_children(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "empty_family.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.family_size is None or result.family_size.sample_size == 0

    def test_implausible_ages_filtered(self, tmp_path: Path) -> None:
        # @I1@/@I2@ marry at 5 and 0; @I3@/@I4@ marry at 35 and 25. The second
        # couple is the control: without it a regression that stopped emitting
        # the statistic altogether would look identical to correct filtering.
        gedcom = tmp_path / "implausible.ged"
        gedcom.write_text(
            """\
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
1 FAMS @F1@
0 @I2@ INDI
1 NAME Also /Young/
1 SEX F
1 BIRT
2 DATE 1855
1 FAMS @F1@
0 @I3@ INDI
1 NAME Plausible /Groom/
1 SEX M
1 BIRT
2 DATE 1820
1 FAMS @F2@
0 @I4@ INDI
1 NAME Plausible /Bride/
1 SEX F
1 BIRT
2 DATE 1830
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1855
0 @F2@ FAM
1 HUSB @I3@
1 WIFE @I4@
1 MARR
2 DATE 1855
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.age_at_first_marriage is not None
        male = result.age_at_first_marriage.male
        female = result.age_at_first_marriage.female
        assert male is not None
        assert male.sample_size == 1
        assert male.average == 35.0
        assert female is not None
        assert female.sample_size == 1
        assert female.average == 25.0

    def test_marriage_without_spouse_birth(self, tmp_path: Path) -> None:
        # @I1@/@I2@ have no birth dates, so their marriage yields no age.
        # @I3@/@I4@ are the control that keeps the statistic populated.
        gedcom = tmp_path / "no_birth.ged"
        gedcom.write_text(
            """\
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
0 @I3@ INDI
1 NAME Dated /Groom/
1 SEX M
1 BIRT
2 DATE 1850
1 FAMS @F2@
0 @I4@ INDI
1 NAME Dated /Bride/
1 SEX F
1 BIRT
2 DATE 1855
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1875
0 @F2@ FAM
1 HUSB @I3@
1 WIFE @I4@
1 MARR
2 DATE 1875
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.age_at_first_marriage is not None
        male = result.age_at_first_marriage.male
        female = result.age_at_first_marriage.female
        assert male is not None
        assert male.sample_size == 1
        assert male.average == 25.0
        assert female is not None
        assert female.sample_size == 1
        assert female.average == 20.0

    def test_individual_without_xref_skipped(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_xref.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 1

    def test_source_depth_no_sources(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_sources.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Source citations:" in output or result.source_depth.max_value == 0

    def test_marriage_by_century(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "marriage_century.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.age_at_first_marriage is not None
        assert result.age_at_first_marriage.by_century is not None
        assert "1800" in result.age_at_first_marriage.by_century

    def test_multiple_marriages_uses_first(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "multiple_marriages.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        # John's first marriage age should be 25 (1875-1850), not 40
        assert result.age_at_first_marriage is not None
        assert result.age_at_first_marriage.male is not None
        assert result.age_at_first_marriage.male.average == 25.0

    def test_age_at_first_child_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "child_age_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Age at First Child:" in output
        assert "Male:" in output
        assert "Female:" in output

    def test_large_family_distribution_buckets(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "large_family.ged"
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

        gedcom.write_text("\n".join(lines), encoding="utf-8")

        result = _collect(gedcom)

        assert result.family_size is not None
        assert result.family_size.distribution.get("10+") == 1

    def test_verbose_mode_error_propagation(self, tmp_path: Path) -> None:
        from argparse import Namespace

        from gedcom_tools.commands.stats import run

        bad_file = tmp_path / "bad.ged"
        bad_file.write_text("not a valid gedcom file at all", encoding="utf-8")

        def make_args(*, verbose: bool) -> Namespace:
            return Namespace(
                file=bad_file,
                format="text",
                quiet=False,
                verbose=verbose,
                no_color=True,
                top=10,
            )

        # Verbose keeps the traceback: the parse failure escapes run().
        with pytest.raises(OSError, match="Unexpected EOF"):
            run(make_args(verbose=True))

        # Without it the same failure is reported as an exit code.
        assert run(make_args(verbose=False)) == EXIT_ERROR

    def test_name_suffix_handling(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "suffix.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/ Jr.
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 1

    def test_depth_limit_locations(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "locations.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert len(result.top_locations) >= 1
        assert any("Boston" in loc.name for loc in result.top_locations)

    def test_xref_extraction_various_formats(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "xref_formats.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.families == 1
        assert result.individuals == 2

    def test_families_but_no_individuals(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "fam_only.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 0
        assert result.families == 1
        assert result.generation_depth == 0
        assert result.gender_male == 0

    def test_individuals_but_no_families(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "indi_only.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Alice /Jones/
1 SEX F
0 @I2@ INDI
1 NAME Bob /Smith/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 2
        assert result.families == 0
        assert result.generation_depth == 1  # Each person is depth 1
        assert result.gender_male == 1
        assert result.gender_female == 1
        assert result.marriage is None

    def test_individual_with_no_name(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_name.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 SEX M
1 BIRT
2 DATE 1850
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.individuals == 1
        assert len(result.top_surnames) == 0


class TestEncodingDetectionFailure:
    """The OSError arm on the encoding phase.

    Driving this through `collect()` does not work: phase 2 opens its own
    GedcomReader on the same truncated file and raises the identical OSError
    with nothing to catch it, so the run dies before any assertion. The phase
    is called on its own instead.
    """

    @staticmethod
    def _truncated_header(tmp_path: Path) -> Path:
        # guess_codec runs off the end of the header and raises OSError.
        ged = tmp_path / "truncated.ged"
        ged.write_bytes(b"0 HEAD\n1 CHAR")
        return ged

    def test_warns_and_reports_unknown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        collector = StatsCollector(
            file_path=self._truncated_header(tmp_path),
            quiet=False,
            verbose=False,
            no_color=True,
        )

        collector._detect_encoding()

        assert collector.encoding_info is not None
        assert collector.encoding_info.encoding == "Unknown"
        assert "Could not detect encoding" in capsys.readouterr().err

    def test_quiet_suppresses_the_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        collector = StatsCollector(
            file_path=self._truncated_header(tmp_path),
            quiet=True,
            verbose=False,
            no_color=True,
        )

        collector._detect_encoding()

        assert collector.encoding_info is not None
        assert collector.encoding_info.encoding == "Unknown"
        assert capsys.readouterr().err == ""

    def test_warning_text_is_sanitized(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The truncated-header fixture above cannot test this: its OSError
        # carries no escape sequence, so the assertion would pass with the
        # sanitize_error call reverted. The exception has to be injected.
        # Patch the module-local name -- collector.py did `from ... import`.
        def _boom(_path: Path) -> EncodingInfo:
            raise OSError("boom \x1b[2J \x9b bad")

        monkeypatch.setattr(
            "gedcom_tools.commands.stats.collector.detect_encoding", _boom
        )
        collector = StatsCollector(
            file_path=tmp_path / "anything.ged",
            quiet=False,
            verbose=False,
            no_color=True,
        )

        collector._detect_encoding()

        err = capsys.readouterr().err
        assert "\x1b" not in err
        assert "\x9b" not in err
        assert "[2J" not in err
        assert "boom" in err and "bad" in err


class TestCLIIntegration:

    def test_stats_command_exists(self) -> None:
        from gedcom_tools.cli import create_parser

        parser = create_parser()
        # This should not raise
        args = parser.parse_args(["stats", "test.ged"])
        assert args.command == "stats"

    def test_stats_help(self) -> None:
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


class TestGivenNameFrequency:

    def test_given_name_extraction_from_name_tuple(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "given_names.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert len(result.top_given_names_male) == 1
        assert result.top_given_names_male[0].name == "John"
        assert len(result.top_given_names_female) == 1
        assert result.top_given_names_female[0].name == "Mary"

    def test_patronymic_name_ranks_its_given_name(self, tmp_path: Path) -> None:
        """`/Ivanov/ Ivan Ivanovich` puts the given name after the surname.

        ged4py hands that back as ("", "Ivanov", "Ivan Ivanovich"), and reading
        the third element as a suffix dropped the person from the rankings.
        """
        gedcom = tmp_path / "patronymic.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME /Ivanov/ Ivan Ivanovich
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        collector = _collector(gedcom)
        result = collector.collect()

        assert result.top_given_names_male[0].name == "Ivan"
        assert collector.individuals["@I1@"].name == "Ivanov Ivan Ivanovich"

    def test_suffix_does_not_displace_the_given_name(self, tmp_path: Path) -> None:
        """A real suffix must not reach the rankings, and must stay in `name`."""
        gedcom = tmp_path / "suffix_given.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Smith/ Jr.
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        collector = _collector(gedcom)
        result = collector.collect()

        indi = collector.individuals["@I1@"]
        assert indi.given_name == "John"
        assert indi.name == "John Smith Jr."
        assert result.top_given_names_male[0].name == "John"

    def test_bare_suffix_ranks_as_a_given_name(self, tmp_path: Path) -> None:
        """Documents the ambiguity we accepted rather than resolved.

        `/Smith/ Jr.` is indistinguishable from the patronymic form at the
        GEDCOM level, so the suffix is ranked as a given name. The patronymic
        spelling is far commoner, and the old behaviour - excluding the person
        from the rankings altogether - was the worse answer for both.
        """
        gedcom = tmp_path / "bare_suffix.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME /Smith/ Jr.
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        collector = _collector(gedcom)
        result = collector.collect()

        assert collector.individuals["@I1@"].name == "Smith Jr."
        assert result.top_given_names_male[0].name == "Jr."

    def test_given_name_from_givn_subrecord(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "givn_subrecord.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert len(result.top_given_names_male) == 1
        assert result.top_given_names_male[0].name == "William"

    def test_given_name_frequency_counts(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "given_freq.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        # John appears 2x, Robert 1x
        assert result.top_given_names_male[0].name == "John"
        assert result.top_given_names_male[0].count == 2

        # Mary appears 3x
        assert result.top_given_names_female[0].name == "Mary"
        assert result.top_given_names_female[0].count == 3

    def test_given_names_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "given_output.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Top Given Names (Male):" in output
        assert "John" in output
        assert "Top Given Names (Female):" in output
        assert "Mary" in output

    def test_given_names_in_json_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "given_json.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        data = json.loads(result.format_json())

        assert "given_names_male" in data["demographics"]
        assert "given_names_female" in data["demographics"]
        assert data["demographics"]["given_names_male"][0]["name"] == "John"
        assert data["demographics"]["given_names_female"][0]["name"] == "Mary"


class TestLifespanStats:

    def test_lifespan_calculation(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.lifespan is not None
        assert result.lifespan.average == 80.0  # (80 + 80) / 2
        assert result.lifespan.min_value == 80
        assert result.lifespan.max_value == 80
        assert result.lifespan.sample_size == 2

    def test_lifespan_filters_invalid(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan_filter.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.lifespan is not None
        # Only Valid Person (70 years) should be counted
        # TooOld (150 years) filtered, Negative (-10 years) filtered
        assert result.lifespan.sample_size == 1
        assert result.lifespan.average == 70.0

    def test_lifespan_no_data(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan_none.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.lifespan is None

    def test_lifespan_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Avg Lifespan:" in output
        assert "75.0 years" in output
        assert "n=1" in output

    def test_lifespan_in_json_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan_json.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        data = json.loads(result.format_json())

        assert data["timeline"]["lifespan"]["average"] == 75.0
        assert data["timeline"]["lifespan"]["min"] == 75
        assert data["timeline"]["lifespan"]["max"] == 75
        assert data["timeline"]["lifespan"]["sample_size"] == 1

    def test_lifespan_by_century(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan_century.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.lifespan_by_century is not None
        assert "1800" in result.lifespan_by_century
        assert result.lifespan_by_century["1800"].average == 70.0
        assert "1900" in result.lifespan_by_century
        assert result.lifespan_by_century["1900"].average == 70.0

    def test_lifespan_trends_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "lifespan_trends_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Lifespan Trends" in output
        assert "By Century:" in output
        assert "1800s:" in output
        assert "70.0 years" in output  # 1920 - 1850 = 70


class TestMarriageStats:

    def test_marriage_year_extraction(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "marriage_year.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.marriage is not None
        assert result.marriage.total_marriages == 1
        assert result.marriage.with_date == 1
        assert result.marriage.without_date == 0

    def test_marriage_without_date(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "marriage_no_date.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.marriage is not None
        assert result.marriage.total_marriages == 1
        assert result.marriage.with_date == 0
        assert result.marriage.without_date == 1

    def test_average_children_per_family(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "avg_children.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.marriage is not None
        assert result.marriage.total_marriages == 2
        # (3 + 1) / 2 = 2.0
        assert result.marriage.avg_children == 2.0

    def test_marriage_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "marriage_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Avg Children/Fam:" in output
        assert "1.0" in output  # 1 child / 1 family
        assert "across 1 families" in output
        assert "Marriage Date:" in output

    def test_marriage_in_json_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "marriage_json.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        data = json.loads(result.format_json())

        assert data["tree_structure"]["marriage"]["total"] == 1
        assert data["tree_structure"]["marriage"]["with_date"] == 1
        assert data["tree_structure"]["marriage"]["avg_children"] == 0.0

    def test_age_at_first_marriage(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "marriage_age.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.age_at_first_marriage is not None
        assert result.age_at_first_marriage.male is not None
        assert result.age_at_first_marriage.male.average == 25.0
        assert result.age_at_first_marriage.female is not None
        assert result.age_at_first_marriage.female.average == 20.0

    def test_age_at_first_child(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "child_age.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.age_at_first_child is not None
        assert result.age_at_first_child.male is not None
        assert result.age_at_first_child.male.average == 30.0  # Father age
        assert result.age_at_first_child.female is not None
        assert result.age_at_first_child.female.average == 25.0  # Mother age

    def test_spousal_age_gap(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "age_gap.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.spousal_age_gap is not None
        assert result.spousal_age_gap.average == 5.0
        assert result.spousal_age_gap.sample_size == 1

    def test_life_events_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "life_events_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Life Events" in output
        assert "Age at First Marriage" in output
        assert "Male:" in output
        assert "25.0 years" in output  # John: 1875 - 1850
        assert "Female:" in output
        assert "20.0 years" in output  # Jane: 1875 - 1855

    def test_life_events_in_json_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "life_events_json.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        data = json.loads(result.format_json())

        assert "life_events" in data
        assert "age_at_first_marriage" in data["life_events"]
        assert "male" in data["life_events"]["age_at_first_marriage"]
        assert "female" in data["life_events"]["age_at_first_marriage"]


class TestSourceCoverage:

    def test_direct_source_citation(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "direct_source.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.source_citations is not None
        assert result.source_citations.with_count == 1
        assert result.source_citations.percent == 100.0

    def test_event_source_citation(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "event_source.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.source_citations is not None
        assert result.source_citations.with_count == 1
        assert result.source_citations.percent == 100.0

    def test_no_source_citation(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_source.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.source_citations is not None
        assert result.source_citations.with_count == 0
        assert result.source_citations.without_count == 1
        assert result.source_citations.percent == 0.0

    def test_source_coverage_mixed(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "mixed_source.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.source_citations is not None
        assert result.source_citations.with_count == 2  # John and Jane
        assert result.source_citations.without_count == 2  # Bob and Alice
        assert result.source_citations.percent == 50.0

    def test_source_coverage_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "source_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Has Sources:" in output

    def test_source_coverage_in_json_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "source_json.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        data = json.loads(result.format_json())

        assert "source_citations" in data["completeness"]
        assert data["completeness"]["source_citations"]["with"] == 1
        assert data["completeness"]["source_citations"]["percent"] == 100.0


class TestDateParsing:

    def test_get_century(self) -> None:
        from gedcom_tools.dates import get_century

        assert get_century(1850) == "1800"
        assert get_century(1899) == "1800"
        assert get_century(1900) == "1900"
        assert get_century(2000) == "2000"
        assert get_century(1776) == "1700"

    def test_extract_year_from_date_none(self) -> None:
        from gedcom_tools.dates import extract_year_from_date

        assert extract_year_from_date(None) is None

    def test_extract_year_from_date_string(self) -> None:
        from gedcom_tools.dates import extract_year_from_date

        result = extract_year_from_date("2 OCT 1850")
        assert result == 1850

    def test_extract_year_from_date_no_year(self) -> None:
        from gedcom_tools.dates import extract_year_from_date

        result = extract_year_from_date("OCT")
        assert result is None

    def test_extract_month_none(self) -> None:
        from gedcom_tools.dates import extract_month

        assert extract_month(None) is None

    def test_extract_month_string(self) -> None:
        from gedcom_tools.dates import extract_month

        assert extract_month("2 OCT 1850") == 10
        assert extract_month("JAN 1900") == 1
        assert extract_month("15 DEC 2000") == 12

    def test_extract_month_no_month(self) -> None:
        from gedcom_tools.dates import extract_month

        assert extract_month("1850") is None

    def test_classify_date_precision_none(self) -> None:
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision(None)
        assert category == "missing"
        assert has_full is False

    def test_classify_date_precision_full(self) -> None:
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("2 OCT 1850")
        assert category == "full"
        assert has_full is True

    def test_classify_date_precision_partial(self) -> None:
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("1850")
        assert category == "partial"
        assert has_full is False

    def test_classify_date_precision_approximate(self) -> None:
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("ABT 1850")
        assert category == "approximate"
        assert has_full is False

        category2, has_full2 = classify_date_precision("BEF 2 OCT 1850")
        assert category2 == "approximate"
        assert has_full2 is True

    def test_classify_date_precision_empty_string(self) -> None:
        from gedcom_tools.dates import classify_date_precision

        category, has_full = classify_date_precision("")
        assert category == "missing"
        assert has_full is False

    def test_is_phrase_date_without_ged4py_types(self) -> None:
        from gedcom_tools.dates import is_phrase_date

        assert is_phrase_date(None) is False
        assert is_phrase_date("some string") is False
        assert is_phrase_date(1850) is False


class TestFamilySize:

    def test_family_size_distribution(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "family_size.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.family_size is not None
        assert result.family_size.average == 3.0
        assert result.family_size.max_value == 3
        assert result.family_size.sample_size == 1
        assert result.family_size.distribution.get("2-3") == 1

    def test_family_size_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "family_size_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Family Size" in output
        assert "Average:" in output
        assert "1.0 children per family" in output
        assert "(n=1)" in output
        assert "Distribution:" in output

    def test_family_size_in_json_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "family_size_json.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        data = json.loads(result.format_json())

        assert "family_size" in data
        assert "average" in data["family_size"]
        assert "distribution" in data["family_size"]


class TestBirthPatterns:

    def test_birth_month_distribution(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "birth_month.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.birth_by_month is not None
        assert result.birth_by_month.get(1) == 2  # January
        assert result.birth_by_month.get(10) == 1  # October

    def test_birth_patterns_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "birth_patterns_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Birth Patterns" in output
        assert "By Month:" in output
        assert "Jan:" in output
        assert "1" in output.split("Jan:")[1].split("\n")[0]  # Count appears after Jan:
        assert "Peak: Jan (100%)" in output

    def test_birth_patterns_no_month_data(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_birth_month.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Birth Patterns" in output
        assert "No birth month data available" in output

    def test_date_precision_calculation(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "date_precision.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.date_precision is not None
        assert result.date_precision.full == 1
        assert result.date_precision.partial == 1
        assert result.date_precision.approximate >= 1
        assert result.date_precision.missing == 1
        assert result.date_precision.total == 4

    def test_occupation_coverage(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "occupation.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.occupation_coverage is not None
        assert result.occupation_coverage.with_count == 1
        assert result.occupation_coverage.without_count == 1
        assert result.occupation_coverage.percent == 50.0

    def test_source_depth(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "source_depth.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)

        assert result.source_depth is not None
        # John has 3 sources (2 direct + 1 on BIRT), Jane has 0
        assert result.source_depth.average == 1.5
        assert result.source_depth.max_value == 3
        assert result.source_depth.min_value == 0

    def test_research_quality_in_text_output(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "research_quality_text.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Research Quality" in output
        assert "Birth Date Precision:" in output
        assert "Occupation recorded:" in output

    def test_research_quality_approximate_breakdown(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "approx_breakdown.ged"
        gedcom.write_text(
            """\
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
""",
            encoding="utf-8",
        )

        result = _collect(gedcom)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=False)

        assert "Approximate:" in output
        assert "with full date:" in output


class _ScriptDetector:
    """Stand-in for GedcomLanguageDetector that classifies by Unicode block.

    The real model costs seconds to load and these tests only care about which
    notes reach the detector, not about what it makes of them.
    """

    min_length = 20

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def detect(self, text: str) -> tuple[str, bool]:
        if len(text) < self.min_length:
            return ("unknown", True)
        for ch in text:
            if "Ͱ" <= ch <= "Ͽ":
                return ("el", False)
            if "Ѐ" <= ch <= "ӿ":
                return ("ru", False)
        return ("en", False)


NOTE_BUFFER_GEDCOM = """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Harker/
1 SEX M
1 NOTE @N1@
1 NOTE The harbour master kept a ledger of every vessel that wintered here.
1 BIRT
2 DATE 12 MAR 1847
2 NOTE @N2@
1 DEAT
2 NOTE
1 RESI
2 NOTE @N99@
0 @I2@ INDI
1 NAME Eleni /Papadaki/
1 SEX F
1 NOTE Η οικογένεια \
μετανάστευσε \
από τα βόρεια \
χωριά τον χειμώνα.
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 NOTE @N1@
1 MARR
2 NOTE Another English note, comfortably past the minimum length for detection.
0 @N1@ NOTE The family emigrated from the northern counties during the winter.
0 @N2@ NOTE Δεύτερη \
σημείωση στα \
ελληνικά με αρκετό \
κείμενο για \
ανίχνευση.
0 @N3@ NOTE Семья переехала \
из северных деревень \
зимой тысяча \
восемьсот сорок \
седьмого года.
0 TRLR
"""

FANOUT_NOTE = (
    "The parish register was rebound in 1893 and the earlier entries "
    "were recopied by hand."
)


def _fanout_gedcom(records: int) -> str:
    """A file where every individual points at the same top-level note."""
    lines = ["0 HEAD", "1 SOUR Test", "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8"]
    for i in range(1, records + 1):
        lines += [f"0 @I{i}@ INDI", f"1 NAME Person{i} /Shared/", "1 NOTE @N1@"]
    lines += [f"0 @N1@ NOTE {FANOUT_NOTE}", "0 TRLR", ""]
    return "\n".join(lines)


class TestNoteLanguageBuffering:
    """Language detection runs off one read of the file, not two.

    English lives in inline INDI/FAM notes and a referenced top-level note,
    Greek in an inline note and a pointer target, Russian only in @N3@ which
    nothing references - so the assertions cover the buffered walk, the
    pointer resolution and the unreferenced-note post-pass at once.
    """

    EXPECTED = {"en", "el", "ru"}

    @pytest.fixture
    def note_ged(self, tmp_path: Path) -> Path:
        path = tmp_path / "note_buffer.ged"
        path.write_text(NOTE_BUFFER_GEDCOM, encoding="utf-8")
        return path

    @pytest.fixture(autouse=True)
    def _stub_detector(
        self, monkeypatch: pytest.MonkeyPatch, _fast_lingua: None
    ) -> None:
        # Depends on _fast_lingua so the module-wide stub is installed first and
        # this one lands on top of it; relying on fixture ordering alone would
        # leave which stub wins up to pytest.
        monkeypatch.setattr(stats_collector, "GedcomLanguageDetector", _ScriptDetector)

    @staticmethod
    def _count_readers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Record every GedcomReader the collector opens."""
        opened: list[str] = []
        real = stats_collector.GedcomReader

        def spy(path: str, *args: object, **kwargs: object) -> object:
            opened.append(path)
            return real(path, *args, **kwargs)

        monkeypatch.setattr(stats_collector, "GedcomReader", spy)
        return opened

    def test_detects_within_budget_from_one_pass(
        self, note_ged: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened = self._count_readers(monkeypatch)

        collector = _collector(note_ged)
        result = collector.collect()

        assert collector.detected_languages == self.EXPECTED
        assert result.distinct_languages == 3
        assert collector._note_buffer_overflow is False
        assert len(opened) == 1

    def test_detects_the_same_set_over_budget(
        self, note_ged: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        budget = 200
        monkeypatch.setattr(StatsCollector, "max_note_buffer_bytes", budget)
        opened = self._count_readers(monkeypatch)

        collector = _collector(note_ged)
        result = collector.collect()

        assert collector.detected_languages == self.EXPECTED
        assert result.distinct_languages == 3
        assert collector._note_buffer_overflow is True
        # Pointer targets no longer contribute, so pin that the inline notes
        # alone are what blow the budget. Without this the test goes vacuous
        # the moment someone trims a note out of the fixture.
        assert collector._note_bytes > budget
        # The partial buffer is dropped, not detected on alongside the reread.
        assert collector._note_texts == []
        assert len(opened) == 2

    def test_pointer_targets_are_not_buffered(self, note_ged: Path) -> None:
        """@N1@ is referenced twice and buffered neither time."""
        collector = _collector(note_ged)
        collector.collect()

        shared = "The family emigrated from the northern counties during the winter."
        assert shared not in collector._note_texts
        # It still gets detected - via the note_lookup post-pass.
        assert collector.note_lookup["@N1@"] == shared
        assert "en" in collector.detected_languages

    def test_empty_note_is_skipped(self, note_ged: Path) -> None:
        collector = _collector(note_ged)
        collector.collect()

        assert all(text for text in collector._note_texts)

    def test_shared_note_reaches_the_detector_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gedcom = tmp_path / "fanout.ged"
        gedcom.write_text(_fanout_gedcom(40), encoding="utf-8")

        seen: list[str] = []

        class CountingDetector(_ScriptDetector):
            def detect(self, text: str) -> tuple[str, bool]:
                seen.append(text)
                return super().detect(text)

        monkeypatch.setattr(stats_collector, "GedcomLanguageDetector", CountingDetector)

        collector = _collector(gedcom)
        collector.collect()

        assert seen.count(FANOUT_NOTE) == 1
        assert collector.detected_languages == {"en"}

    def test_fan_out_does_not_trip_the_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gedcom = tmp_path / "fanout.ged"
        gedcom.write_text(_fanout_gedcom(40), encoding="utf-8")
        # One copy of the shared note would already overrun this.
        monkeypatch.setattr(StatsCollector, "max_note_buffer_bytes", 20)
        opened = self._count_readers(monkeypatch)

        collector = _collector(gedcom)
        collector.collect()

        assert collector._note_buffer_overflow is False
        assert collector._note_bytes == 0
        assert collector.detected_languages == {"en"}
        assert len(opened) == 1

    def test_no_notes_leaves_the_buffer_empty(self, tmp_path: Path) -> None:
        gedcom = tmp_path / "no_notes.ged"
        gedcom.write_text(
            """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
""",
            encoding="utf-8",
        )

        collector = _collector(gedcom)
        result = collector.collect()

        assert collector._note_texts == []
        assert collector._note_bytes == 0
        assert result.distinct_languages == 0
