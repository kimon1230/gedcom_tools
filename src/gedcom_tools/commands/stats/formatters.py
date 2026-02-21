"""Stats result and output formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gedcom_tools.commands.stats.models import (
    AggregateStats,
    CoverageStats,
    DatePrecisionStats,
    FamilyEntry,
    GenderedAggregateStats,
    GenerationEntry,
    LifespanStats,
    MarriageStats,
    RankedItem,
    TimelineEntry,
)

if TYPE_CHECKING:
    from gedcom_tools.progress import Colors
    from gedcom_tools.utils import EncodingInfo


@dataclass
class StatsResult:

    file_path: str
    encoding_info: EncodingInfo | None

    # Record counts
    individuals: int = 0
    families: int = 0
    sources: int = 0
    locations: int = 0
    distinct_languages: int = 0

    # Timeline
    earliest_year: TimelineEntry | None = None
    latest_year: TimelineEntry | None = None
    earliest_generation: GenerationEntry | None = None
    date_span_years: int | None = None
    by_century: dict[str, int] = field(default_factory=dict)

    # Tree structure
    generation_depth: int = 0
    largest_families: list[FamilyEntry] = field(default_factory=list)

    # Demographics
    gender_male: int = 0
    gender_female: int = 0
    gender_unknown: int = 0
    top_surnames: list[RankedItem] = field(default_factory=list)
    top_lineages: list[RankedItem] = field(default_factory=list)
    top_given_names_male: list[RankedItem] = field(default_factory=list)
    top_given_names_female: list[RankedItem] = field(default_factory=list)

    # Lifespan
    lifespan: LifespanStats | None = None

    # Marriage
    marriage: MarriageStats | None = None

    # Locations
    top_locations: list[RankedItem] = field(default_factory=list)

    # Completeness
    birth_date: CoverageStats | None = None
    death_date: CoverageStats | None = None
    source_citations: CoverageStats | None = None
    notes: CoverageStats | None = None
    media: CoverageStats | None = None
    isolated: CoverageStats | None = None
    estimated_living: CoverageStats | None = None

    # Life Events
    age_at_first_marriage: GenderedAggregateStats | None = None
    age_at_first_child: GenderedAggregateStats | None = None
    spousal_age_gap: AggregateStats | None = None

    # Family patterns
    family_size: AggregateStats | None = None  # Only families with 1+ children
    birth_by_month: dict[int, int] = field(default_factory=dict)
    lifespan_by_century: dict[str, AggregateStats] = field(default_factory=dict)

    # Research quality
    date_precision: DatePrecisionStats | None = None
    occupation_coverage: CoverageStats | None = None
    source_depth: AggregateStats | None = None

    def format_text(self, colors: Colors, quiet: bool = False) -> str:
        if quiet:
            return (
                f"{self.individuals:,} individuals, "
                f"{self.families:,} families, "
                f"{self.sources:,} sources, "
                f"{self.locations:,} locations, "
                f"{self.distinct_languages} language(s)"
            )

        lines: list[str] = []

        # Header
        lines.append(f"File: {self.file_path}")
        if self.encoding_info:
            lines.append(f"Encoding: {self.encoding_info}")
        lines.append("")

        # Record Counts
        lines.append(f"{colors.cyan}=== Record Counts ==={colors.reset}")
        lines.append(f"  Individuals:      {self.individuals:>8,}")
        lines.append(f"  Families:         {self.families:>8,}")
        lines.append(f"  Sources:          {self.sources:>8,}")
        lines.append(f"  Locations:        {self.locations:>8,}")
        lines.append(f"  Distinct Languages:{self.distinct_languages:>7,}")
        lines.append("")

        # Timeline
        lines.append(f"{colors.cyan}=== Timeline ==={colors.reset}")
        if self.date_span_years is not None and self.earliest_year and self.latest_year:
            lines.append(
                f"  Date Span:        {self.earliest_year.year} - "
                f"{self.latest_year.year} ({self.date_span_years} years)"
            )
        if self.earliest_year:
            lines.append(
                f"  Earliest (year):  {self.earliest_year.name} "
                f"(b. {self.earliest_year.year})"
            )
        if self.earliest_generation:
            lines.append(
                f"  Earliest (gen):   {self.earliest_generation.name} "
                f"(generation {self.earliest_generation.generation})"
            )
        if self.lifespan:
            lines.append(
                f"  Avg Lifespan:     {self.lifespan.average:.1f} years "
                f"(n={self.lifespan.sample_size:,}, "
                f"range {self.lifespan.min_value}-{self.lifespan.max_value})"
            )
        if self.by_century:
            lines.append("")
            lines.append("  By Century:")
            for century, count in sorted(self.by_century.items()):
                pct = (count / self.individuals * 100) if self.individuals else 0
                lines.append(f"    {century}s:         {count:>5} ({pct:.1f}%)")
        if not self.earliest_year and not self.by_century:
            lines.append("  No date data available")
        lines.append("")

        # Tree Structure
        lines.append(f"{colors.cyan}=== Tree Structure ==={colors.reset}")
        lines.append(f"  Generation Depth: {self.generation_depth} generations")
        if self.marriage:
            lines.append(
                f"  Avg Children/Fam: {self.marriage.avg_children:.1f} "
                f"(across {self.marriage.total_marriages:,} families)"
            )
        if self.largest_families:
            lines.append("")
            lines.append("  Largest Families:")
            for i, fam in enumerate(self.largest_families, 1):
                lines.append(
                    f"    {i}. {fam.parents} ({fam.xref})     "
                    f"{fam.children} children"
                )
        lines.append("")

        # Demographics
        lines.append(f"{colors.cyan}=== Demographics ==={colors.reset}")
        lines.append("  Gender:")
        total = self.individuals or 1  # Avoid division by zero
        lines.append(
            f"    Male:           {self.gender_male:>5} "
            f"({self.gender_male / total * 100:.1f}%)"
        )
        lines.append(
            f"    Female:         {self.gender_female:>5} "
            f"({self.gender_female / total * 100:.1f}%)"
        )
        lines.append(
            f"    Unknown:        {self.gender_unknown:>5} "
            f"({self.gender_unknown / total * 100:.1f}%)"
        )

        if self.top_surnames:
            lines.append("")
            lines.append("  Top Surnames:")
            for i, item in enumerate(self.top_surnames, 1):
                lines.append(
                    f"    {i:>2}. {item.name:<20} {item.count:>5} ({item.percent:.1f}%)"
                )

        if self.top_lineages:
            lines.append("")
            lines.append("  Top Lineages:")
            for i, item in enumerate(self.top_lineages, 1):
                lines.append(
                    f"    {i:>2}. {item.name:<20} {item.count:>5} ({item.percent:.1f}%)"
                )

        if self.top_given_names_male:
            lines.append("")
            lines.append("  Top Given Names (Male):")
            for i, item in enumerate(self.top_given_names_male, 1):
                lines.append(
                    f"    {i:>2}. {item.name:<20} {item.count:>5} ({item.percent:.1f}%)"
                )

        if self.top_given_names_female:
            lines.append("")
            lines.append("  Top Given Names (Female):")
            for i, item in enumerate(self.top_given_names_female, 1):
                lines.append(
                    f"    {i:>2}. {item.name:<20} {item.count:>5} ({item.percent:.1f}%)"
                )
        lines.append("")

        # Locations
        if self.top_locations:
            lines.append(f"{colors.cyan}=== Locations ==={colors.reset}")
            lines.append("  Top Places:")
            for i, item in enumerate(self.top_locations, 1):
                # Truncate long place names
                place = item.name[:35] + "..." if len(item.name) > 38 else item.name
                lines.append(
                    f"    {i:>2}. {place:<38} {item.count:>5} ({item.percent:.1f}%)"
                )
            lines.append("")

        # Data Completeness
        lines.append(f"{colors.cyan}=== Data Completeness ==={colors.reset}")
        if self.birth_date:
            lines.append(
                f"  Birth/Baptism Date:   {self.birth_date.with_count:>5} / "
                f"{self.individuals:,} ({self.birth_date.percent:.1f}%)"
            )
        if self.death_date:
            lines.append(
                f"  Death/Burial Date:    {self.death_date.with_count:>5} / "
                f"{self.individuals:,} ({self.death_date.percent:.1f}%)"
            )
        if self.marriage:
            marr_pct = (
                self.marriage.with_date / max(1, self.marriage.total_marriages) * 100
            )
            lines.append(
                f"  Marriage Date:        {self.marriage.with_date:>5} / "
                f"{self.marriage.total_marriages:,} ({marr_pct:.1f}%)"
            )
        if self.source_citations:
            lines.append(
                f"  Has Sources:          {self.source_citations.with_count:>5} / "
                f"{self.individuals:,} ({self.source_citations.percent:.1f}%)"
            )
        if self.notes:
            lines.append(
                f"  Has Notes:            {self.notes.with_count:>5} / "
                f"{self.individuals:,} ({self.notes.percent:.1f}%)"
            )
        if self.media:
            lines.append(
                f"  Has Media:            {self.media.with_count:>5} / "
                f"{self.individuals:,} ({self.media.percent:.1f}%)"
            )
        if self.isolated:
            lines.append(
                f"  Isolated:             {self.isolated.with_count:>5} / "
                f"{self.individuals:,} ({self.isolated.percent:.1f}%)"
            )
        if self.estimated_living:
            lines.append(
                f"  Estimated Living:     {self.estimated_living.with_count:>5} / "
                f"{self.individuals:,} ({self.estimated_living.percent:.1f}%)"
            )

        # Life Events
        if (
            self.age_at_first_marriage
            or self.age_at_first_child
            or self.spousal_age_gap
        ):
            lines.append("")
            lines.append(f"{colors.cyan}=== Life Events ==={colors.reset}")

            if self.age_at_first_marriage:
                lines.append("  Age at First Marriage:")
                if self.age_at_first_marriage.male:
                    m = self.age_at_first_marriage.male
                    lines.append(
                        f"    Male:    {m.average:.1f} years "
                        f"(n={m.sample_size}, range {m.min_value}-{m.max_value})"
                    )
                if self.age_at_first_marriage.female:
                    f = self.age_at_first_marriage.female
                    lines.append(
                        f"    Female:  {f.average:.1f} years "
                        f"(n={f.sample_size}, range {f.min_value}-{f.max_value})"
                    )

                if self.age_at_first_marriage.by_century:
                    lines.append("    By Century:")
                    for century, genders in sorted(
                        self.age_at_first_marriage.by_century.items()
                    ):
                        parts = []
                        total_n = 0
                        male_stats = genders.get("male")
                        female_stats = genders.get("female")
                        if male_stats:
                            parts.append(f"M {male_stats.average:.1f}")
                            total_n += male_stats.sample_size
                        if female_stats:
                            parts.append(f"F {female_stats.average:.1f}")
                            total_n += female_stats.sample_size
                        if parts:
                            lines.append(
                                f"      {century}s:  {', '.join(parts)} (n={total_n})"
                            )

            if self.age_at_first_child:
                lines.append("  Age at First Child:")
                if self.age_at_first_child.male:
                    m = self.age_at_first_child.male
                    lines.append(
                        f"    Male:    {m.average:.1f} years "
                        f"(n={m.sample_size}, range {m.min_value}-{m.max_value})"
                    )
                if self.age_at_first_child.female:
                    f = self.age_at_first_child.female
                    lines.append(
                        f"    Female:  {f.average:.1f} years "
                        f"(n={f.sample_size}, range {f.min_value}-{f.max_value})"
                    )

            if self.spousal_age_gap:
                g = self.spousal_age_gap
                lines.append(
                    f"  Spousal Age Gap: {g.average:.1f} years avg "
                    f"(n={g.sample_size}, range {g.min_value}-{g.max_value})"
                )

        # Family Size
        if self.family_size:
            lines.append("")
            lines.append(f"{colors.cyan}=== Family Size ==={colors.reset}")
            fs = self.family_size
            lines.append(
                f"  Average: {fs.average:.1f} children per family (n={fs.sample_size})"
            )
            if fs.distribution:
                lines.append("  Distribution:")
                for bucket in ["1", "2-3", "4-6", "7-9", "10+"]:
                    count = fs.distribution.get(bucket, 0)
                    pct = count / fs.sample_size * 100 if fs.sample_size else 0
                    label = "1 child:" if bucket == "1" else f"{bucket} children:"
                    lines.append(f"    {label:15} {count:>5} ({pct:.0f}%)")
            lines.append(f"  Largest: {fs.max_value} children")

        # Birth Patterns
        if self.birth_by_month:
            total = sum(self.birth_by_month.values())
            if total > 0:
                lines.append("")
                lines.append(f"{colors.cyan}=== Birth Patterns ==={colors.reset}")
                lines.append("  By Month:")
                month_names = [
                    "Jan",
                    "Feb",
                    "Mar",
                    "Apr",
                    "May",
                    "Jun",
                    "Jul",
                    "Aug",
                    "Sep",
                    "Oct",
                    "Nov",
                    "Dec",
                ]

                for row in range(4):
                    cols = []
                    for col in range(3):
                        month = row * 3 + col + 1
                        if month <= 12:
                            count = self.birth_by_month.get(month, 0)
                            pct = count / total * 100
                            cols.append(
                                f"{month_names[month-1]}:  {count:>4} ({pct:>4.0f}%)"
                            )
                    if cols:
                        lines.append("    " + "   ".join(cols))

                peak_month = max(
                    self.birth_by_month.keys(),
                    key=lambda m: self.birth_by_month.get(m, 0),
                )
                peak_count = self.birth_by_month[peak_month]
                peak_pct = peak_count / total * 100
                lines.append(f"  Peak: {month_names[peak_month-1]} ({peak_pct:.0f}%)")
        elif self.individuals > 0:
            # Explain why section is missing
            lines.append("")
            lines.append(f"{colors.cyan}=== Birth Patterns ==={colors.reset}")
            lines.append(
                "  No birth month data available (dates may be approximate or missing)"
            )

        # Lifespan Trends
        if self.lifespan_by_century:
            lines.append("")
            lines.append(f"{colors.cyan}=== Lifespan Trends ==={colors.reset}")
            lines.append("  By Century:")
            for century, stats in sorted(self.lifespan_by_century.items()):
                avg = stats.average
                n = stats.sample_size
                lines.append(f"    {century}s:  {avg:.1f} years (n={n})")

        # Research Quality
        if self.date_precision or self.occupation_coverage or self.source_depth:
            lines.append("")
            lines.append(f"{colors.cyan}=== Research Quality ==={colors.reset}")

            if self.date_precision:
                dp = self.date_precision
                total = dp.total
                if total > 0:
                    lines.append("  Birth Date Precision:")
                    lines.append(
                        f"    {'Full (day/month/year):':<25} {dp.full:>5} "
                        f"({dp.full/total*100:.0f}%)"
                    )
                    lines.append(
                        f"    {'Partial (month/year):':<25} {dp.partial:>5} "
                        f"({dp.partial/total*100:.0f}%)"
                    )
                    lines.append(
                        f"    {'Approximate:':<25} {dp.approximate:>5} "
                        f"({dp.approximate/total*100:.0f}%)"
                    )
                    if dp.approximate > 0:
                        lines.append(
                            f"      {'- with full date:':<23} {dp.approximate_full:>5}"
                        )
                        lines.append(
                            f"      {'- with partial date:':<23} "
                            f"{dp.approximate_partial:>5}"
                        )
                    lines.append(
                        f"    {'Missing:':<25} {dp.missing:>5} "
                        f"({dp.missing/total*100:.0f}%)"
                    )

            if self.occupation_coverage:
                oc = self.occupation_coverage
                lines.append(
                    f"  Occupation recorded: {oc.with_count:,} / "
                    f"{oc.with_count + oc.without_count:,} ({oc.percent:.1f}%)"
                )

            if self.source_depth:
                sd = self.source_depth
                if sd.max_value == 0:
                    lines.append("  Source citations:    None found")
                else:
                    lines.append(
                        f"  Avg sources/person:  {sd.average:.1f} "
                        f"(range {sd.min_value}-{sd.max_value})"
                    )

        return "\n".join(lines)

    def format_json(self) -> str:
        data: dict[str, Any] = {
            "file": self.file_path,
            "encoding": None,
            "records": {
                "individuals": self.individuals,
                "families": self.families,
                "sources": self.sources,
                "locations": self.locations,
                "distinct_languages": self.distinct_languages,
            },
            "timeline": {
                "earliest_year": None,
                "latest_year": None,
                "earliest_generation": None,
                "date_span_years": self.date_span_years,
                "by_century": self.by_century,
                "lifespan": None,
            },
            "tree_structure": {
                "generation_depth": self.generation_depth,
                "largest_families": [
                    {"xref": f.xref, "parents": f.parents, "children": f.children}
                    for f in self.largest_families
                ],
                "marriage": None,
            },
            "demographics": {
                "gender": {
                    "male": self.gender_male,
                    "female": self.gender_female,
                    "unknown": self.gender_unknown,
                },
                "surnames": [
                    {"name": s.name, "count": s.count, "percent": round(s.percent, 1)}
                    for s in self.top_surnames
                ],
                "lineages": [
                    {
                        "name": lin.name,
                        "count": lin.count,
                        "percent": round(lin.percent, 1),
                    }
                    for lin in self.top_lineages
                ],
                "given_names_male": [
                    {"name": g.name, "count": g.count, "percent": round(g.percent, 1)}
                    for g in self.top_given_names_male
                ],
                "given_names_female": [
                    {"name": g.name, "count": g.count, "percent": round(g.percent, 1)}
                    for g in self.top_given_names_female
                ],
            },
            "locations": [
                {
                    "place": loc.name,
                    "count": loc.count,
                    "percent": round(loc.percent, 1),
                }
                for loc in self.top_locations
            ],
            "completeness": {},
        }

        # Encoding
        if self.encoding_info:
            data["encoding"] = {
                "detected": self.encoding_info.encoding,
                "has_bom": self.encoding_info.has_bom,
                "declared": self.encoding_info.declared_charset,
            }

        # Timeline entries
        if self.earliest_year:
            data["timeline"]["earliest_year"] = {
                "year": self.earliest_year.year,
                "xref": self.earliest_year.xref,
                "name": self.earliest_year.name,
            }
        if self.latest_year:
            data["timeline"]["latest_year"] = {
                "year": self.latest_year.year,
                "xref": self.latest_year.xref,
                "name": self.latest_year.name,
            }
        if self.earliest_generation:
            data["timeline"]["earliest_generation"] = {
                "generation": self.earliest_generation.generation,
                "xref": self.earliest_generation.xref,
                "name": self.earliest_generation.name,
            }
        if self.lifespan:
            data["timeline"]["lifespan"] = {
                "average": self.lifespan.average,
                "min": self.lifespan.min_value,
                "max": self.lifespan.max_value,
                "sample_size": self.lifespan.sample_size,
            }

        # Marriage stats
        if self.marriage:
            data["tree_structure"]["marriage"] = self.marriage.to_dict()

        # Completeness
        if self.birth_date:
            data["completeness"]["birth_date"] = {
                "with": self.birth_date.with_count,
                "without": self.birth_date.without_count,
                "percent": self.birth_date.percent,
            }
        if self.death_date:
            data["completeness"]["death_date"] = {
                "with": self.death_date.with_count,
                "without": self.death_date.without_count,
                "percent": self.death_date.percent,
            }
        if self.source_citations:
            data["completeness"]["source_citations"] = {
                "with": self.source_citations.with_count,
                "without": self.source_citations.without_count,
                "percent": self.source_citations.percent,
            }
        if self.notes:
            data["completeness"]["notes"] = {
                "with": self.notes.with_count,
                "without": self.notes.without_count,
                "percent": self.notes.percent,
            }
        if self.media:
            data["completeness"]["media"] = {
                "with": self.media.with_count,
                "without": self.media.without_count,
                "percent": self.media.percent,
            }
        if self.isolated:
            data["completeness"]["isolated"] = {
                "count": self.isolated.with_count,
                "percent": self.isolated.percent,
            }
        if self.estimated_living:
            data["completeness"]["estimated_living"] = {
                "count": self.estimated_living.with_count,
                "percent": self.estimated_living.percent,
            }

        # Life events
        data["life_events"] = {}
        if self.age_at_first_marriage:
            data["life_events"][
                "age_at_first_marriage"
            ] = self.age_at_first_marriage.to_dict()
        if self.age_at_first_child:
            data["life_events"][
                "age_at_first_child"
            ] = self.age_at_first_child.to_dict()
        if self.spousal_age_gap:
            data["life_events"]["spousal_age_gap"] = self.spousal_age_gap.to_dict()

        # Family size
        data["family_size"] = self.family_size.to_dict() if self.family_size else None

        # Birth patterns
        if self.birth_by_month:
            total = sum(self.birth_by_month.values())
            if total > 0:
                peak = max(
                    self.birth_by_month.keys(),
                    key=lambda m: self.birth_by_month.get(m, 0),
                )
                data["birth_patterns"] = {
                    "by_month": self.birth_by_month,
                    "peak_month": peak,
                    "total": total,
                }
            else:
                data["birth_patterns"] = None
        else:
            data["birth_patterns"] = None

        # Lifespan trends
        if self.lifespan_by_century:
            data["lifespan_trends"] = {
                "by_century": {
                    century: stats.to_dict()
                    for century, stats in sorted(self.lifespan_by_century.items())
                }
            }
        else:
            data["lifespan_trends"] = None

        # Research quality
        data["research_quality"] = {}
        if self.date_precision:
            data["research_quality"]["date_precision"] = self.date_precision.to_dict()
        if self.occupation_coverage:
            data["research_quality"][
                "occupation_coverage"
            ] = self.occupation_coverage.to_dict()
        if self.source_depth:
            data["research_quality"]["source_depth"] = self.source_depth.to_dict()

        return json.dumps(data, indent=2)
