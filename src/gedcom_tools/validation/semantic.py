"""Semantic validation for genealogical logic."""

from __future__ import annotations

from dataclasses import dataclass, field

from gedcom_tools.constants import (
    MAX_LIFESPAN,
    MAX_PARENT_AGE_AT_BIRTH,
    MIN_PARENT_AGE,
)
from gedcom_tools.validation.issues import (
    ErrorCode,
    FamilyInfo,
    IndividualInfo,
    ValidationIssue,
)


@dataclass
class SemanticValidator:
    """Validates genealogical logic and plausibility.

    Checks for ancestry cycles, date logic, and age plausibility.
    """

    individuals: dict[str, IndividualInfo] = field(default_factory=dict)
    families: dict[str, FamilyInfo] = field(default_factory=dict)
    _reported_cycles: set[frozenset[str]] = field(default_factory=set)

    def collect_individual(self, info: IndividualInfo) -> None:
        """Record individual data for later validation."""
        self.individuals[info.xref] = info

    def collect_family(self, info: FamilyInfo) -> None:
        """Record family data for later validation."""
        self.families[info.xref] = info

    def validate(self) -> list[ValidationIssue]:
        """Run all semantic validations and return issues."""
        issues: list[ValidationIssue] = []

        issues.extend(self._check_ancestry_cycles())
        issues.extend(self._check_date_logic())
        issues.extend(self._check_age_plausibility())

        return issues

    def _check_ancestry_cycles(self) -> list[ValidationIssue]:
        """Detect cycles in ancestry using DFS.

        A cycle exists if following parent links from an individual
        eventually leads back to that individual.
        """
        issues = []
        visited_global: set[str] = set()

        for start_xref in self.individuals:
            if start_xref in visited_global:
                continue

            # DFS with path tracking
            path: list[str] = []
            path_set: set[str] = set()
            stack = [(start_xref, False)]

            while stack:
                xref, processed = stack.pop()

                if processed:
                    path.pop()
                    path_set.remove(xref)
                    continue

                if xref in path_set:
                    # Found a cycle - deduplicate by normalizing cycle representation
                    cycle_start = path.index(xref)
                    cycle = path[cycle_start:] + [xref]
                    cycle_members = frozenset(cycle[:-1])
                    if cycle_members not in self._reported_cycles:
                        self._reported_cycles.add(cycle_members)
                        issues.append(
                            ValidationIssue(
                                code=ErrorCode.E010_ANCESTRY_CYCLE,
                                message=f"Ancestry cycle detected: {' → '.join(cycle)}",
                                line=self.individuals[start_xref].line,
                                xref=start_xref,
                            )
                        )
                    continue

                if xref in visited_global:
                    continue

                visited_global.add(xref)
                path.append(xref)
                path_set.add(xref)
                stack.append((xref, True))

                # Add parents to stack
                indi = self.individuals.get(xref)
                if indi:
                    for fam_xref in indi.famc_xrefs:
                        fam = self.families.get(fam_xref)
                        if fam:
                            if fam.husb_xref:
                                stack.append((fam.husb_xref, False))
                            if fam.wife_xref:
                                stack.append((fam.wife_xref, False))

        return issues

    def _check_date_logic(self) -> list[ValidationIssue]:
        """Check for impossible date relationships."""
        issues = []

        for xref, indi in self.individuals.items():
            # Death before birth
            if (
                indi.birth_year is not None
                and indi.death_year is not None
                and indi.death_year < indi.birth_year
            ):
                death = indi.death_year
                birth = indi.birth_year
                issues.append(
                    ValidationIssue(
                        code=ErrorCode.E011_DEATH_BEFORE_BIRTH,
                        message=f"Death ({death}) before birth ({birth})",
                        line=indi.line,
                        xref=xref,
                    )
                )

            # Birth before parent's birth
            if indi.birth_year is not None:
                for fam_xref in indi.famc_xrefs:
                    fam = self.families.get(fam_xref)
                    if not fam:
                        continue

                    for parent_xref in [fam.husb_xref, fam.wife_xref]:
                        if not parent_xref:
                            continue
                        parent = self.individuals.get(parent_xref)
                        if (
                            parent
                            and parent.birth_year is not None
                            and indi.birth_year < parent.birth_year
                        ):
                            issues.append(
                                ValidationIssue(
                                    code=ErrorCode.E012_BIRTH_BEFORE_PARENT,
                                    message=f"Born ({indi.birth_year}) before parent "
                                    f"{parent_xref} ({parent.birth_year})",
                                    line=indi.line,
                                    xref=xref,
                                )
                            )

        # Marriage before birth
        for fam_xref, fam in self.families.items():
            if fam.marriage_year is None:
                continue

            for spouse_xref in [fam.husb_xref, fam.wife_xref]:
                if not spouse_xref:
                    continue
                spouse = self.individuals.get(spouse_xref)
                if (
                    spouse
                    and spouse.birth_year is not None
                    and fam.marriage_year < spouse.birth_year
                ):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W024_MARRIAGE_BEFORE_BIRTH,
                            message=f"Marriage ({fam.marriage_year}) before "
                            f"{spouse_xref} birth ({spouse.birth_year})",
                            line=fam.line,
                            xref=fam_xref,
                        )
                    )

            # Child born before marriage (just a warning)
            for child_xref in fam.chil_xrefs:
                child = self.individuals.get(child_xref)
                if (
                    child
                    and child.birth_year is not None
                    and child.birth_year < fam.marriage_year
                ):
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W025_CHILD_BEFORE_MARRIAGE,
                            message=f"Child {child_xref} born ({child.birth_year}) "
                            f"before marriage ({fam.marriage_year})",
                            line=fam.line,
                            xref=fam_xref,
                        )
                    )

        return issues

    def _check_age_plausibility(self) -> list[ValidationIssue]:
        """Check for implausible ages."""
        issues = []

        for xref, indi in self.individuals.items():
            # Age at death
            if indi.birth_year is not None and indi.death_year is not None:
                age = indi.death_year - indi.birth_year
                if age > MAX_LIFESPAN:
                    issues.append(
                        ValidationIssue(
                            code=ErrorCode.W023_AGE_AT_DEATH_IMPLAUSIBLE,
                            message=f"Age at death ({age}) exceeds {MAX_LIFESPAN}",
                            line=indi.line,
                            xref=xref,
                        )
                    )

        # Parent age at child's birth
        for _fam_xref, fam in self.families.items():
            for child_xref in fam.chil_xrefs:
                child = self.individuals.get(child_xref)
                if not child or child.birth_year is None:
                    continue

                # Check father
                if fam.husb_xref:
                    father = self.individuals.get(fam.husb_xref)
                    if father and father.birth_year is not None:
                        age = child.birth_year - father.birth_year
                        husb = fam.husb_xref
                        if age < MIN_PARENT_AGE:
                            issues.append(
                                ValidationIssue(
                                    code=ErrorCode.W020_PARENT_TOO_YOUNG,
                                    message=f"Father {husb} was {age} at birth",
                                    line=child.line,
                                    xref=child_xref,
                                )
                            )
                        elif age > MAX_PARENT_AGE_AT_BIRTH:
                            issues.append(
                                ValidationIssue(
                                    code=ErrorCode.W022_FATHER_TOO_OLD,
                                    message=f"Father {husb} was {age} at birth",
                                    line=child.line,
                                    xref=child_xref,
                                )
                            )

                # Check mother
                if fam.wife_xref:
                    mother = self.individuals.get(fam.wife_xref)
                    if mother and mother.birth_year is not None:
                        age = child.birth_year - mother.birth_year
                        wife = fam.wife_xref
                        if age < MIN_PARENT_AGE:
                            issues.append(
                                ValidationIssue(
                                    code=ErrorCode.W020_PARENT_TOO_YOUNG,
                                    message=f"Mother {wife} was {age} at birth",
                                    line=child.line,
                                    xref=child_xref,
                                )
                            )
                        elif age > MAX_PARENT_AGE_AT_BIRTH:
                            issues.append(
                                ValidationIssue(
                                    code=ErrorCode.W021_MOTHER_TOO_OLD,
                                    message=f"Mother {wife} was {age} at birth",
                                    line=child.line,
                                    xref=child_xref,
                                )
                            )

        return issues
