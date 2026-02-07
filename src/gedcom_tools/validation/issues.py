"""Validation issue types and error codes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """Severity level of a validation issue."""

    ERROR = "error"
    WARNING = "warning"


class ErrorCode(Enum):
    """Error and warning codes for validation issues.

    E0xx = Errors (fatal issues that make the file invalid)
    W0xx = Warnings (issues that should be reviewed but don't invalidate the file)
    """

    # Errors: Structure and parsing
    E001_UNRESOLVED_XREF = "E001"
    E002_DUPLICATE_XREF = "E002"
    E003_INVALID_LEVEL = "E003"
    E004_MALFORMED_LINE = "E004"
    E005_MISSING_HEAD = "E005"
    E006_MISSING_TRLR = "E006"
    E007_CONTENT_AFTER_TRLR = "E007"
    E008_DECODE_FAILURE = "E008"
    # Errors: Semantic
    E010_ANCESTRY_CYCLE = "E010"
    E011_DEATH_BEFORE_BIRTH = "E011"
    E012_BIRTH_BEFORE_PARENT = "E012"

    # Errors: Version compliance (strict mode)
    E013_MISSING_GEDC = "E013"
    E014_MISSING_GEDC_VERS = "E014"
    E015_MISSING_SOUR = "E015"
    E016_MISSING_CHAR = "E016"

    # Warnings: Structure
    W002_TRAILING_WHITESPACE = "W002"
    W003_LINE_TOO_LONG = "W003"
    W004_CUSTOM_TAG = "W004"
    W005_MISSING_SUBM = "W005"

    # Warnings: References
    W010_ORPHANED_NOTE = "W010"
    W011_ORPHANED_OBJE = "W011"
    W012_ORPHANED_SOUR = "W012"
    W013_ORPHANED_REPO = "W013"
    W014_ISOLATED_INDI = "W014"
    W015_EMPTY_FAM = "W015"

    # Warnings: Semantic
    W020_PARENT_TOO_YOUNG = "W020"
    W021_MOTHER_TOO_OLD = "W021"
    W022_FATHER_TOO_OLD = "W022"
    W023_AGE_AT_DEATH_IMPLAUSIBLE = "W023"
    W024_MARRIAGE_BEFORE_BIRTH = "W024"
    W025_CHILD_BEFORE_MARRIAGE = "W025"

    # Warnings: Version compliance (strict mode)
    W030_ANSEL_DEPRECATED = "W030"
    W031_VERSION_MISMATCH = "W031"
    W032_LINE_TOO_LONG_STRICT = "W032"

    @property
    def severity(self) -> Severity:
        """Return the severity based on code prefix."""
        return Severity.ERROR if self.value.startswith("E") else Severity.WARNING

    @property
    def description(self) -> str:
        """Return a human-readable description of the error code."""
        descriptions = {
            # Errors
            "E001": "Unresolved cross-reference",
            "E002": "Duplicate cross-reference definition",
            "E003": "Invalid level number",
            "E004": "Malformed GEDCOM line",
            "E005": "Missing HEAD record",
            "E006": "Missing TRLR record",
            "E007": "Content after TRLR record",
            "E008": "Character encoding decode failure",
            "E010": "Ancestry cycle detected",
            "E011": "Death date before birth date",
            "E012": "Birth date before parent's birth",
            "E013": "Missing GEDC in HEAD",
            "E014": "Missing VERS in GEDC",
            "E015": "Missing SOUR in HEAD",
            "E016": "Missing CHAR in HEAD",
            # Warnings
            "W002": "Trailing whitespace",
            "W003": "Line exceeds recommended length",
            "W004": "Custom/non-standard tag",
            "W005": "Missing SUBM record",
            "W010": "Orphaned NOTE record",
            "W011": "Orphaned OBJE record",
            "W012": "Orphaned SOUR record",
            "W013": "Orphaned REPO record",
            "W014": "Individual with no family connections",
            "W015": "Family with no members",
            "W020": "Parent too young at child's birth",
            "W021": "Mother too old at child's birth",
            "W022": "Father too old at child's birth",
            "W023": "Implausible age at death",
            "W024": "Marriage before birth",
            "W025": "Child born before parents' marriage",
            "W030": "ANSEL encoding deprecated in GEDCOM 5.5.5",
            "W031": "Declared version does not match --strict version",
            "W032": "Line exceeds 255 byte limit (strict)",
        }
        return descriptions.get(self.value, "Unknown issue")


@dataclass
class ValidationIssue:
    """A single validation issue found in a GEDCOM file."""

    code: ErrorCode
    message: str
    line: int | None = None
    xref: str | None = None
    context: str | None = None

    @property
    def severity(self) -> Severity:
        """Return the severity of this issue."""
        return self.code.severity

    def __str__(self) -> str:
        """Return a human-readable representation."""
        parts = [f"[{self.code.value}]"]
        if self.line is not None:
            parts.append(f"Line {self.line}:")
        if self.xref:
            parts.append(f"({self.xref})")
        parts.append(self.message)
        return " ".join(parts)


@dataclass
class IndividualInfo:
    """Collected information about an individual for semantic validation."""

    xref: str
    line: int
    birth_year: int | None = None
    death_year: int | None = None
    sex: str | None = None
    famc_xrefs: list[str] = field(default_factory=list)
    fams_xrefs: list[str] = field(default_factory=list)


@dataclass
class FamilyInfo:
    """Collected information about a family for semantic validation."""

    xref: str
    line: int
    husb_xref: str | None = None
    wife_xref: str | None = None
    chil_xrefs: list[str] = field(default_factory=list)
    marriage_year: int | None = None


@dataclass
class RecordInfo:
    """Basic information about any record."""

    xref: str
    record_type: str
    line: int


@dataclass
class UsageInfo:
    """Information about where an xref is used."""

    line: int
    context: str
