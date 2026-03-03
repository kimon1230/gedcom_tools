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
    indi_as_child: dict[str, set[str]] = field(default_factory=dict)
    indi_as_spouse: dict[str, set[str]] = field(default_factory=dict)
    fam_children: dict[str, set[str]] = field(default_factory=dict)
    fam_spouses: dict[str, set[str]] = field(default_factory=dict)

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

    def collect_indi_as_child(self, indi_xref: str, fam_xref: str) -> None:
        """Record that an individual references a family via FAMC."""
        self.indi_as_child.setdefault(indi_xref, set()).add(fam_xref)

    def collect_indi_as_spouse(self, indi_xref: str, fam_xref: str) -> None:
        """Record that an individual references a family via FAMS."""
        self.indi_as_spouse.setdefault(indi_xref, set()).add(fam_xref)

    def collect_fam_child(self, fam_xref: str, child_xref: str) -> None:
        """Record that a family lists an individual as CHIL."""
        self.fam_children.setdefault(fam_xref, set()).add(child_xref)

    def collect_fam_spouse(self, fam_xref: str, spouse_xref: str) -> None:
        """Record that a family lists an individual as HUSB or WIFE."""
        self.fam_spouses.setdefault(fam_xref, set()).add(spouse_xref)

    def validate(self) -> list[ValidationIssue]:
        """Validate all collected references and return issues."""
        issues: list[ValidationIssue] = []

        issues.extend(self._check_unresolved_xrefs())
        issues.extend(self._check_orphaned_records())
        issues.extend(self._check_isolated_individuals())
        issues.extend(self._check_empty_families())
        issues.extend(self._check_asymmetric_links())

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
                connections = self.indi_as_child.get(
                    xref, set()
                ) | self.indi_as_spouse.get(xref, set())
                if not connections:
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
                members = self.fam_children.get(xref, set()) | self.fam_spouses.get(
                    xref, set()
                )
                if not members:
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W015_EMPTY_FAM,
                            message="Family has no members",
                            line=info.line,
                            xref=xref,
                        )
                    )

        return issues

    def _check_asymmetric_links(self) -> list[ValidationIssue]:
        """Check for one-sided family-individual cross-references."""
        issues: list[ValidationIssue] = []

        # Child links: FAM lists CHIL but INDI doesn't reference FAM as parent
        for fam_xref, children in self.fam_children.items():
            for child_xref in children:
                if child_xref not in self.definitions:
                    continue
                if fam_xref not in self.definitions:
                    continue
                if fam_xref not in self.indi_as_child.get(child_xref, set()):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W016_ASYMMETRIC_CHILD_LINK,
                            message=f"{child_xref} listed as child in {fam_xref} "
                            f"but does not reference {fam_xref} as parent family",
                            xref=child_xref,
                        )
                    )

        # Child links: INDI references FAM as parent but FAM doesn't list INDI as CHIL
        for indi_xref, fam_set in self.indi_as_child.items():
            for fam_xref in fam_set:
                if fam_xref not in self.definitions:
                    continue
                if indi_xref not in self.definitions:
                    continue
                if indi_xref not in self.fam_children.get(fam_xref, set()):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W016_ASYMMETRIC_CHILD_LINK,
                            message=f"{indi_xref} references {fam_xref} as parent "
                            f"family but is not listed as child",
                            xref=indi_xref,
                        )
                    )

        # Spouse links: FAM lists HUSB/WIFE but INDI doesn't reference FAM as spousal
        for fam_xref, spouses in self.fam_spouses.items():
            for spouse_xref in spouses:
                if spouse_xref not in self.definitions:
                    continue
                if fam_xref not in self.definitions:
                    continue
                if fam_xref not in self.indi_as_spouse.get(spouse_xref, set()):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W017_ASYMMETRIC_SPOUSE_LINK,
                            message=f"{spouse_xref} listed as spouse in {fam_xref} "
                            f"but does not reference {fam_xref} as spousal family",
                            xref=spouse_xref,
                        )
                    )

        # Spouse links: INDI references FAM as spousal but FAM doesn't list as HUSB/WIFE
        for indi_xref, fam_set in self.indi_as_spouse.items():
            for fam_xref in fam_set:
                if fam_xref not in self.definitions:
                    continue
                if indi_xref not in self.definitions:
                    continue
                if indi_xref not in self.fam_spouses.get(fam_xref, set()):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W017_ASYMMETRIC_SPOUSE_LINK,
                            message=f"{indi_xref} references {fam_xref} as spousal "
                            f"family but is not listed as spouse",
                            xref=indi_xref,
                        )
                    )

        return issues
