"""Data models for the filter command."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from gedcom_tools import __version__
from gedcom_tools.progress import Colors

UNLIMITED_DEPTH: int = 2**20


@dataclass
class GedcomLine:
    level: int
    xref: str | None
    tag: str
    value: str | None
    raw: str
    line_number: int


@dataclass
class GedcomRecord:
    header: GedcomLine
    children: list[GedcomLine]

    @property
    def xref(self) -> str | None:
        return self.header.xref

    @property
    def tag(self) -> str:
        return self.header.tag


@dataclass
class RecordCounts:
    indi: int = 0
    fam: int = 0
    note: int = 0
    sour: int = 0
    obje: int = 0
    repo: int = 0
    subm: int = 0
    other: int = 0

    @property
    def total(self) -> int:
        return (
            self.indi
            + self.fam
            + self.note
            + self.sour
            + self.obje
            + self.repo
            + self.subm
            + self.other
        )


@dataclass
class FilterSpec:
    strip_custom_tags: bool = False
    strip_notes: bool = False
    strip_sources: bool = False
    strip_multimedia: bool = False
    strip_tags: list[str] = field(default_factory=list)
    subtree_root: str | None = None
    ancestor_depth: int | None = None
    descendant_depth: int = 0
    include_spouses: bool = False


@dataclass
class FilterResult:
    source_path: str
    output_path: str
    source_counts: RecordCounts
    output_counts: RecordCounts
    removed_counts: RecordCounts
    dangling_lines_removed: int
    empty_families_removed: int
    dry_run: bool

    def format_text(self, colors: Colors, quiet: bool) -> str:
        if quiet:
            line = (
                f"Filtered {self.source_path} "
                f"({self.source_counts.total:,} \u2192 "
                f"{self.output_counts.total:,} records) "
                f"\u2192 {self.output_path}"
            )
            if self.dry_run:
                line += " (dry run)"
            return line

        rows: list[tuple[str, int, int, int]] = []
        for label, src, out, rem in [
            (
                "Individuals",
                self.source_counts.indi,
                self.output_counts.indi,
                self.removed_counts.indi,
            ),
            (
                "Families",
                self.source_counts.fam,
                self.output_counts.fam,
                self.removed_counts.fam,
            ),
            (
                "Notes",
                self.source_counts.note,
                self.output_counts.note,
                self.removed_counts.note,
            ),
            (
                "Sources",
                self.source_counts.sour,
                self.output_counts.sour,
                self.removed_counts.sour,
            ),
            (
                "Multimedia",
                self.source_counts.obje,
                self.output_counts.obje,
                self.removed_counts.obje,
            ),
            (
                "Repositories",
                self.source_counts.repo,
                self.output_counts.repo,
                self.removed_counts.repo,
            ),
            (
                "Submitters",
                self.source_counts.subm,
                self.output_counts.subm,
                self.removed_counts.subm,
            ),
            (
                "Other",
                self.source_counts.other,
                self.output_counts.other,
                self.removed_counts.other,
            ),
        ]:
            if src > 0 or out > 0 or rem > 0:
                rows.append((label, src, out, rem))

        lines: list[str] = [
            f"File: {self.source_path}",
            "",
            f"{colors.cyan}=== Filter Results ==={colors.reset}",
            "",
            f"  {'Record Type':<15} {'Source':>8} {'Output':>8} {'Removed':>8}",
            f"  {'-' * 15} {'-' * 8} {'-' * 8} {'-' * 8}",
        ]

        for label, src, out, rem in rows:
            lines.append(f"  {label:<15} {src:>8,} {out:>8,} {rem:>8,}")

        lines.append(f"  {'-' * 15} {'-' * 8} {'-' * 8} {'-' * 8}")
        lines.append(
            f"  {'Total':<15} {self.source_counts.total:>8,} "
            f"{self.output_counts.total:>8,} {self.removed_counts.total:>8,}"
        )

        if self.dangling_lines_removed > 0:
            lines.append(
                f"\n  Dangling references cleaned: {self.dangling_lines_removed:,}"
            )
        if self.empty_families_removed > 0:
            lines.append(
                f"  Empty families removed:      {self.empty_families_removed:,}"
            )

        lines.append(f"\n  Output: {self.output_path}")

        if self.dry_run:
            lines.append("\n  (dry run \u2014 no file written)")

        return "\n".join(lines)

    def format_json(self) -> str:
        def _counts_dict(c: RecordCounts) -> dict[str, int]:
            return {
                "individuals": c.indi,
                "families": c.fam,
                "notes": c.note,
                "sources": c.sour,
                "multimedia": c.obje,
                "repositories": c.repo,
                "submitters": c.subm,
                "other": c.other,
                "total": c.total,
            }

        from pathlib import Path as _Path

        data = {
            "source_file": self.source_path,
            "source_filename": _Path(self.source_path).name,
            "output_file": self.output_path,
            "output_filename": _Path(self.output_path).name,
            "source": _counts_dict(self.source_counts),
            "output": _counts_dict(self.output_counts),
            "removed": _counts_dict(self.removed_counts),
            "dangling_lines_removed": self.dangling_lines_removed,
            "empty_families_removed": self.empty_families_removed,
            "dry_run": self.dry_run,
            "gedcom_tools_version": __version__,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
