"""Reference validation for GEDCOM cross-references."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from gedcom_tools.validation.issues import (
    ErrorCode,
    RecordInfo,
    UsageInfo,
    ValidationIssue,
)


@dataclass
class ReferenceValidator:
    """Validates cross-references between GEDCOM records.

    Collects xref definitions and usages during parsing, then validates
    for unresolved references, duplicates, and orphaned records.
    """

    definitions: dict[str, RecordInfo] = field(default_factory=dict)
    usages: dict[str, list[UsageInfo]] = field(
        default_factory=lambda: defaultdict(list)
    )
    indi_connections: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    fam_members: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def collect_definition(
        self, xref: str, record_type: str, line: int
    ) -> ValidationIssue | None:
        """Record an xref definition. Returns an issue if duplicate."""
        if xref in self.definitions:
            existing = self.definitions[xref]
            return ValidationIssue(
                code=ErrorCode.E002_DUPLICATE_XREF,
                message=f"Duplicate definition of {xref} "
                f"(first defined at line {existing.line} as {existing.record_type})",
                line=line,
                xref=xref,
            )

        self.definitions[xref] = RecordInfo(
            xref=xref, record_type=record_type, line=line
        )
        return None

    def collect_usage(self, xref: str, line: int, context: str) -> None:
        """Record where an xref is referenced."""
        self.usages[xref].append(UsageInfo(line=line, context=context))

    def collect_indi_family_link(self, indi_xref: str, fam_xref: str) -> None:
        """Record that an individual is linked to a family."""
        self.indi_connections[indi_xref].add(fam_xref)

    def collect_fam_member(self, fam_xref: str, member_xref: str) -> None:
        """Record that a family has a member (HUSB, WIFE, or CHIL)."""
        self.fam_members[fam_xref].add(member_xref)

    def validate(self) -> list[ValidationIssue]:
        """Validate all collected references and return issues."""
        issues: list[ValidationIssue] = []

        issues.extend(self._check_unresolved_xrefs())
        issues.extend(self._check_orphaned_records())
        issues.extend(self._check_isolated_individuals())
        issues.extend(self._check_empty_families())

        return issues

    def _check_unresolved_xrefs(self) -> list[ValidationIssue]:
        """Check for xrefs that are used but not defined."""
        issues = []

        for xref, usage_list in self.usages.items():
            if xref not in self.definitions:
                # Report at first usage location
                first_usage = usage_list[0]
                issues.append(
                    ValidationIssue(
                        code=ErrorCode.E001_UNRESOLVED_XREF,
                        message=f"Reference to undefined {xref}",
                        line=first_usage.line,
                        xref=xref,
                        context=first_usage.context,
                    )
                )

        return issues

    def _check_orphaned_records(self) -> list[ValidationIssue]:
        """Check for NOTE, OBJE, SOUR, REPO records that are never referenced."""
        issues = []

        orphan_codes = {
            "NOTE": ErrorCode.W010_ORPHANED_NOTE,
            "OBJE": ErrorCode.W011_ORPHANED_OBJE,
            "SOUR": ErrorCode.W012_ORPHANED_SOUR,
            "REPO": ErrorCode.W013_ORPHANED_REPO,
        }

        for xref, info in self.definitions.items():
            if info.record_type in orphan_codes:
                if xref not in self.usages or len(self.usages[xref]) == 0:
                    issues.append(
                        ValidationIssue(
                            code=orphan_codes[info.record_type],
                            message=f"{info.record_type} record is never referenced",
                            line=info.line,
                            xref=xref,
                        )
                    )

        return issues

    def _check_isolated_individuals(self) -> list[ValidationIssue]:
        """Check for individuals with no family connections (FAMS or FAMC)."""
        issues = []

        for xref, info in self.definitions.items():
            if info.record_type == "INDI":
                if xref not in self.indi_connections or not self.indi_connections[xref]:
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W014_ISOLATED_INDI,
                            message="Individual has no family connections",
                            line=info.line,
                            xref=xref,
                        )
                    )

        return issues

    def _check_empty_families(self) -> list[ValidationIssue]:
        """Check for families with no HUSB, WIFE, or CHIL."""
        issues = []

        for xref, info in self.definitions.items():
            if info.record_type == "FAM":
                if xref not in self.fam_members or not self.fam_members[xref]:
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W015_EMPTY_FAM,
                            message="Family has no members",
                            line=info.line,
                            xref=xref,
                        )
                    )

        return issues
