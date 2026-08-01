"""Validation engine orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal

from ged4py.parser import CodecError, GedcomReader, IntegrityError, ParserError

from gedcom_tools.constants import VALID_SEX_VALUES
from gedcom_tools.dates import (
    classify_date_precision,
    extract_month,
    extract_year_from_date,
)
from gedcom_tools.progress import PhaseTracker
from gedcom_tools.utils import EncodingInfo, detect_encoding, extract_xref
from gedcom_tools.validation.issues import (
    ErrorCode,
    FamilyInfo,
    IndividualInfo,
    ValidationIssue,
)

if TYPE_CHECKING:
    from ged4py.model import Record
from gedcom_tools.validation.reference import ReferenceValidator
from gedcom_tools.validation.result import ValidationResult
from gedcom_tools.validation.semantic import SemanticValidator


class StopValidation(Exception):
    """Raised to stop validation early in quick mode."""

    pass


# Maximum recommended line length per GEDCOM spec
MAX_LINE_LENGTH = 255

# Maximum nesting depth per GEDCOM spec (level numbers 0-99)
MAX_NESTING_DEPTH = 99

# Maximum unique custom tags to warn about before suppressing
MAX_CUSTOM_TAG_WARNINGS = 10


class ValidationEngine:
    """Orchestrates the validation process.

    Runs validation in 4 phases:
    1. Detect encoding
    2. Parse structure and collect data
    3. Validate references
    4. Check semantics
    """

    def __init__(
        self,
        file_path: Path,
        mode: Literal["quick", "full"] = "quick",
        strict: str | None = None,
        quiet: bool = False,
        verbose: bool = False,
        no_color: bool = False,
        stream: IO[str] | None = None,
    ):
        self.file_path = file_path
        self.mode = mode
        self.strict = strict
        self.quiet = quiet
        self.verbose = verbose
        self.no_color = no_color
        self.stream = stream

        self.issues: list[ValidationIssue] = []
        self.encoding_info: EncodingInfo | None = None
        self.record_counts: dict[str, int] = {}

        self._ref_validator = ReferenceValidator()
        self._sem_validator = SemanticValidator()
        self._line_offsets: list[int] = []
        self._warned_custom_tags: set[str] = set()

    def validate(self) -> ValidationResult:
        """Run all validation phases and return results."""
        tracker = PhaseTracker(
            total_phases=4,
            stream=self.stream,
            no_color=self.no_color,
            quiet=self.quiet,
            verbose=self.verbose,
        )

        try:
            # Phase 1: Detect encoding
            with tracker.phase("Detecting encoding"):
                self._detect_encoding()

            # Phase 2: Parse structure
            with tracker.phase("Parsing structure") as spinner:
                self._parse_structure(spinner)

            # Phase 3: Validate references
            with tracker.phase("Validating references"):
                ref_issues = self._ref_validator.validate()
                self.issues.extend(ref_issues)

            # Phase 4: Check semantics
            with tracker.phase("Checking semantics"):
                sem_issues = self._sem_validator.validate()
                self.issues.extend(sem_issues)

        except StopValidation:
            pass

        return ValidationResult(
            file_path=str(self.file_path),
            issues=self.issues,
            encoding_info=self.encoding_info,
            record_counts=self.record_counts,
        )

    def _build_line_map(self) -> None:
        """Build offset-to-line mapping and check line-level issues.

        Checks:
        - W002: Trailing whitespace
        - W003: Line too long (soft warning, always checked)
        - W032: Line too long strict (only in --strict mode)
        """
        self._line_offsets = [0]
        with open(self.file_path, "rb") as f:
            offset = 0
            line_num = 0
            for line in f:
                line_num += 1
                line_content = line.rstrip(b"\r\n")

                # W002: Trailing whitespace
                if line_content != line_content.rstrip():
                    self._add_issue(
                        ErrorCode.W002_TRAILING_WHITESPACE,
                        "Line has trailing whitespace",
                        line=line_num,
                    )

                # W003/W032: Line length checks
                if len(line_content) > MAX_LINE_LENGTH:
                    if self.strict is not None:
                        self._add_issue(
                            ErrorCode.W032_LINE_TOO_LONG_STRICT,
                            f"Line exceeds {MAX_LINE_LENGTH} bytes "
                            f"({len(line_content)} bytes)",
                            line=line_num,
                        )
                    else:
                        self._add_issue(
                            ErrorCode.W003_LINE_TOO_LONG,
                            f"Line exceeds recommended {MAX_LINE_LENGTH} bytes "
                            f"({len(line_content)} bytes)",
                            line=line_num,
                        )

                offset += len(line)
                self._line_offsets.append(offset)

    def _offset_to_line(self, offset: int) -> int:
        """Convert byte offset to line number (1-indexed)."""
        if not self._line_offsets:
            return 0

        # Binary search for the line containing this offset
        lo, hi = 0, len(self._line_offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._line_offsets[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def _detect_encoding(self) -> None:
        """Detect file encoding."""
        try:
            self.encoding_info = detect_encoding(self.file_path)
        except CodecError as e:
            self._add_issue(
                ErrorCode.E008_DECODE_FAILURE,
                f"Failed to decode file: {e}",
            )
            if self.mode == "quick":
                raise StopValidation() from None
            return
        except ParserError as e:
            self._add_issue(
                ErrorCode.E004_MALFORMED_LINE,
                f"Parse error: {e}",
            )
            if self.mode == "quick":
                raise StopValidation() from None
            return
        except IntegrityError as e:
            self._add_issue(
                ErrorCode.E003_INVALID_LEVEL,
                f"Structure error: {e}",
            )
            if self.mode == "quick":
                raise StopValidation() from None
            return

    def _parse_structure(self, spinner: object) -> None:
        """Parse file structure and collect data for validation."""
        self._build_line_map()

        try:
            with GedcomReader(str(self.file_path)) as reader:
                # Check HEAD exists
                if reader.header is None:
                    self._add_issue(
                        ErrorCode.E005_MISSING_HEAD,
                        "File does not start with HEAD record",
                        line=1,
                    )
                    if self.mode == "quick":
                        raise StopValidation()
                else:
                    # Check for SUBM reference
                    subm = reader.header.sub_tag("SUBM", follow=False)
                    if subm is None:
                        self._add_issue(
                            ErrorCode.W005_MISSING_SUBM,
                            "No SUBM (submitter) record referenced in HEAD",
                            line=1,
                        )

                    # Version compliance checks (strict mode only)
                    self._validate_version_compliance(reader.header)

                # Process all level-0 records
                count = 0
                has_trlr = False

                for record in reader.records0():
                    count += 1
                    if hasattr(spinner, "update") and count % 100 == 0:
                        spinner.update(f" ({count:,} records)")

                    tag = record.tag
                    if not tag:
                        continue

                    offset = record.offset if record.offset else 0
                    rec_line = self._offset_to_line(offset)

                    # E007: Check for content after TRLR
                    if has_trlr:
                        self._add_issue(
                            ErrorCode.E007_CONTENT_AFTER_TRLR,
                            f"Record {tag} appears after TRLR",
                            line=rec_line,
                        )
                        if self.mode == "quick":
                            raise StopValidation()
                        continue

                    # Track record counts
                    self.record_counts[tag] = self.record_counts.get(tag, 0) + 1

                    # Check for TRLR
                    if tag == "TRLR":
                        has_trlr = True
                        continue

                    # W004: Check for custom tags (start with _)
                    if tag.startswith("_"):
                        self._add_issue(
                            ErrorCode.W004_CUSTOM_TAG,
                            f"Custom tag {tag} is non-standard",
                            line=rec_line,
                        )

                    # Check sub-records for custom tags
                    self._check_custom_tags(record)

                    # Collect xref definitions
                    xref_id = record.xref_id
                    if xref_id:
                        issue = self._ref_validator.collect_definition(
                            xref_id, tag, rec_line
                        )
                        if issue:
                            self.issues.append(issue)
                            if self.mode == "quick":
                                raise StopValidation()

                    # Process by record type
                    if tag == "INDI":
                        self._process_indi(record)
                    elif tag == "FAM":
                        self._process_fam(record)
                    else:
                        self._process_generic(record)

                if not has_trlr:
                    self._add_issue(
                        ErrorCode.E006_MISSING_TRLR,
                        "File does not end with TRLR record",
                    )
                    if self.mode == "quick":
                        raise StopValidation()

        except ParserError as e:
            self._add_issue(
                ErrorCode.E004_MALFORMED_LINE,
                f"Parse error: {e}",
            )
            if self.mode == "quick":
                raise StopValidation() from None

        except IntegrityError as e:
            self._add_issue(
                ErrorCode.E003_INVALID_LEVEL,
                f"Structure error: {e}",
            )
            if self.mode == "quick":
                raise StopValidation() from None

        except UnicodeDecodeError as e:
            self._add_issue(
                ErrorCode.E008_DECODE_FAILURE,
                f"Encoding error: {e}",
            )
            if self.mode == "quick":
                raise StopValidation() from None

    def _process_indi(self, record: Record) -> None:
        """Process an INDI record."""
        xref = record.xref_id
        if not xref:
            return  # INDI records should always have an xref

        offset = record.offset if record.offset else 0
        line = self._offset_to_line(offset)

        # Extract birth year and month (month only for non-approximate dates)
        birt_date_rec = record.sub_tag("BIRT/DATE")
        birth_year: int | None = None
        birth_month: int | None = None
        if birt_date_rec and birt_date_rec.value:
            birth_year = extract_year_from_date(birt_date_rec.value)
            precision, _ = classify_date_precision(birt_date_rec.value)
            if precision in ("full", "partial"):
                birth_month = extract_month(birt_date_rec.value)

        death_year = self._extract_year(record, "DEAT/DATE")

        # Extract sex and family links via single-pass sub_records iteration
        sex_value: str | None = None
        sex_count = 0
        famc_xrefs: list[str] = []
        fams_xrefs: list[str] = []

        for sub in record.sub_records:
            sub_offset = sub.offset if sub.offset else 0

            if sub.tag == "SEX":
                sex_count += 1
                raw = str(sub.value).upper().strip() if sub.value else ""
                if raw and raw not in VALID_SEX_VALUES:
                    self._add_issue(
                        ErrorCode.W028_INVALID_SEX,
                        f"SEX value '{raw}' not recognized " f"(expected M/F/U/X)",
                        line=self._offset_to_line(sub_offset),
                        xref=xref,
                    )
                elif raw and sex_value is None:
                    sex_value = raw

            elif sub.tag == "FAMC" and sub.value:
                fam_xref = self._extract_xref(sub.value)
                if fam_xref:
                    famc_xrefs.append(fam_xref)
                    self._ref_validator.collect_usage(
                        fam_xref,
                        self._offset_to_line(sub_offset),
                        f"FAMC reference in {xref}",
                    )
                    self._ref_validator.collect_indi_as_child(xref, fam_xref)

            elif sub.tag == "FAMS" and sub.value:
                fam_xref = self._extract_xref(sub.value)
                if fam_xref:
                    fams_xrefs.append(fam_xref)
                    self._ref_validator.collect_usage(
                        fam_xref,
                        self._offset_to_line(sub_offset),
                        f"FAMS reference in {xref}",
                    )
                    self._ref_validator.collect_indi_as_spouse(xref, fam_xref)

            # Check for direct pointer references (SOUR, NOTE, OBJE, REPO)
            elif sub.tag in ("SOUR", "NOTE", "OBJE", "REPO") and sub.value:
                ref_xref = self._extract_xref(sub.value)
                if ref_xref:
                    self._ref_validator.collect_usage(
                        ref_xref,
                        self._offset_to_line(sub_offset),
                        f"{sub.tag} reference in {xref}",
                    )

            # Check for nested pointer references
            self._collect_sub_xrefs_recursive(sub, xref, depth=1)

        if sex_count > 1:
            self._add_issue(
                ErrorCode.W027_MULTIPLE_SEX,
                f"Individual has {sex_count} SEX records " f"(expected at most 1)",
                line=line,
                xref=xref,
            )

        # Store for semantic validation
        self._sem_validator.collect_individual(
            IndividualInfo(
                xref=xref,
                line=line,
                birth_year=birth_year,
                birth_month=birth_month,
                death_year=death_year,
                sex=sex_value,
                famc_xrefs=famc_xrefs,
                fams_xrefs=fams_xrefs,
            )
        )

    def _process_fam(self, record: Record) -> None:
        """Process a FAM record."""
        xref = record.xref_id
        if not xref:
            return  # FAM records should always have an xref

        offset = record.offset if record.offset else 0
        line = self._offset_to_line(offset)

        husb_xref: str | None = None
        wife_xref: str | None = None
        chil_xrefs: list[str] = []
        marriage_year = self._extract_year(record, "MARR/DATE")

        for sub in record.sub_records:
            sub_offset = sub.offset if sub.offset else 0
            if sub.tag == "HUSB" and sub.value:
                husb_xref = self._extract_xref(sub.value)
                if husb_xref:
                    self._ref_validator.collect_usage(
                        husb_xref,
                        self._offset_to_line(sub_offset),
                        f"HUSB in {xref}",
                    )
                    self._ref_validator.collect_fam_spouse(xref, husb_xref)

            elif sub.tag == "WIFE" and sub.value:
                wife_xref = self._extract_xref(sub.value)
                if wife_xref:
                    self._ref_validator.collect_usage(
                        wife_xref,
                        self._offset_to_line(sub_offset),
                        f"WIFE in {xref}",
                    )
                    self._ref_validator.collect_fam_spouse(xref, wife_xref)

            elif sub.tag == "CHIL" and sub.value:
                chil_xref = self._extract_xref(sub.value)
                if chil_xref:
                    chil_xrefs.append(chil_xref)
                    self._ref_validator.collect_usage(
                        chil_xref,
                        self._offset_to_line(sub_offset),
                        f"CHIL in {xref}",
                    )
                    self._ref_validator.collect_fam_child(xref, chil_xref)

            # Check for direct pointer references (SOUR, NOTE, OBJE, REPO)
            elif sub.tag in ("SOUR", "NOTE", "OBJE", "REPO") and sub.value:
                ref_xref = self._extract_xref(sub.value)
                if ref_xref:
                    self._ref_validator.collect_usage(
                        ref_xref,
                        self._offset_to_line(sub_offset),
                        f"{sub.tag} reference in {xref}",
                    )

            # Check for nested pointer references
            self._collect_sub_xrefs_recursive(sub, xref, depth=1)

        # Store for semantic validation
        self._sem_validator.collect_family(
            FamilyInfo(
                xref=xref,
                line=line,
                husb_xref=husb_xref,
                wife_xref=wife_xref,
                chil_xrefs=chil_xrefs,
                marriage_year=marriage_year,
            )
        )

    def _process_generic(self, record: Record) -> None:
        """Process a generic record (NOTE, SOUR, REPO, OBJE, etc.)."""
        xref = record.xref_id
        if not xref:
            return

        # OBJE structural checks (W033, W034)
        if record.tag == "OBJE":
            offset = record.offset if record.offset else 0
            rec_line = self._offset_to_line(offset)
            has_file = False
            for sub in record.sub_records:
                if sub.tag == "FILE":
                    has_file = True
                    has_form = any(s.tag == "FORM" for s in sub.sub_records)
                    if not has_form:
                        sub_offset = sub.offset if sub.offset else 0
                        self._add_issue(
                            ErrorCode.W034_FILE_MISSING_FORM,
                            f"FILE in {xref} has no FORM subtag",
                            line=self._offset_to_line(sub_offset),
                            xref=xref,
                        )
            if not has_file:
                self._add_issue(
                    ErrorCode.W033_OBJE_MISSING_FILE,
                    f"OBJE {xref} has no FILE subtag",
                    line=rec_line,
                    xref=xref,
                )

        # Recursively collect xref usages
        self._collect_sub_xrefs_recursive(record, xref)

    def _collect_sub_xrefs_recursive(
        self, record: Record, parent_xref: str, depth: int = 0
    ) -> None:
        # GEDCOM allows levels 0-99; cap depth to avoid runaway recursion
        if depth >= MAX_NESTING_DEPTH:
            return

        for sub in record.sub_records:
            sub_offset = sub.offset if sub.offset else 0
            if sub.value:
                ref_xref = self._extract_xref(sub.value)
                if ref_xref:
                    self._ref_validator.collect_usage(
                        ref_xref,
                        self._offset_to_line(sub_offset),
                        f"{sub.tag} reference in {parent_xref}",
                    )
            self._collect_sub_xrefs_recursive(sub, parent_xref, depth + 1)

    def _check_custom_tags(self, record: Record, depth: int = 0) -> None:
        """Recursively check for custom tags in sub-records.

        Custom tags start with underscore (_) and are vendor extensions.
        Warnings are deduplicated to avoid flooding output.
        """
        if depth >= MAX_NESTING_DEPTH:
            return

        for sub in record.sub_records:
            tag = sub.tag
            if tag and tag.startswith("_"):
                if tag not in self._warned_custom_tags:
                    sub_offset = sub.offset if sub.offset else 0
                    if len(self._warned_custom_tags) < MAX_CUSTOM_TAG_WARNINGS:
                        self._add_issue(
                            ErrorCode.W004_CUSTOM_TAG,
                            f"Custom tag {tag} is non-standard",
                            line=self._offset_to_line(sub_offset),
                        )
                    elif len(self._warned_custom_tags) == MAX_CUSTOM_TAG_WARNINGS:
                        self._add_issue(
                            ErrorCode.W004_CUSTOM_TAG,
                            f"Additional custom tags suppressed "
                            f"(>{MAX_CUSTOM_TAG_WARNINGS} unique tags found)",
                            line=self._offset_to_line(sub_offset),
                        )
                    self._warned_custom_tags.add(tag)
            self._check_custom_tags(sub, depth + 1)

    @staticmethod
    def _extract_xref(value: Any) -> str | None:
        """Extract an xref pointer, ignoring reserved GEDCOM escapes.

        Values such as ``@#DGREGORIAN@`` (calendar escape) and ``@@`` (an
        escaped literal ``@``) are delimited like pointers but are not
        references, so treating them as one produces a spurious E001.
        Non-string values are passed through untouched — ged4py hands us
        tuples for NAME and None for event tags, and pointer objects still
        need their ``xref_id`` resolved.
        """
        if isinstance(value, str) and (len(value) < 3 or value[1] in "#@"):
            return None
        return extract_xref(value)

    def _extract_year(self, record: Record, path: str) -> int | None:
        """Extract year from a date at the given path."""
        date_rec = record.sub_tag(path)
        if date_rec is None or date_rec.value is None:
            return None
        return extract_year_from_date(date_rec.value)

    def _validate_version_compliance(self, header: Record) -> None:
        # --strict mode: enforce version-specific requirements
        if self.strict is None:
            return

        # Check GEDC record exists
        gedc = header.sub_tag("GEDC")
        if gedc is None:
            gedc_line = 1  # HEAD is at line 1
            self._add_issue(
                ErrorCode.E013_MISSING_GEDC,
                "HEAD record missing required GEDC sub-record",
                line=gedc_line,
            )
            if self.mode == "quick":
                raise StopValidation()
        else:
            # Check VERS exists under GEDC
            vers = gedc.sub_tag("VERS")
            if vers is None:
                gedc_offset = gedc.offset if gedc.offset else 0
                self._add_issue(
                    ErrorCode.E014_MISSING_GEDC_VERS,
                    "GEDC record missing required VERS sub-record",
                    line=self._offset_to_line(gedc_offset),
                )
                if self.mode == "quick":
                    raise StopValidation()
            else:
                # Check version mismatch
                declared_version = str(vers.value) if vers.value else None
                if declared_version and declared_version != self.strict:
                    vers_offset = vers.offset if vers.offset else 0
                    self._add_issue(
                        ErrorCode.W031_VERSION_MISMATCH,
                        f"File declares version {declared_version}, "
                        f"but --strict {self.strict} was specified",
                        line=self._offset_to_line(vers_offset),
                    )

        # Check SOUR exists
        sour = header.sub_tag("SOUR")
        if sour is None:
            self._add_issue(
                ErrorCode.E015_MISSING_SOUR,
                "HEAD record missing required SOUR sub-record",
                line=1,
            )
            if self.mode == "quick":
                raise StopValidation()

        # Check CHAR exists
        char = header.sub_tag("CHAR")
        if char is None:
            self._add_issue(
                ErrorCode.E016_MISSING_CHAR,
                "HEAD record missing required CHAR sub-record",
                line=1,
            )
            if self.mode == "quick":
                raise StopValidation()
        else:
            # Check ANSEL deprecation in 5.5.5
            if self.strict == "5.5.5":
                charset = str(char.value).upper() if char.value else ""
                if charset == "ANSEL":
                    char_offset = char.offset if char.offset else 0
                    self._add_issue(
                        ErrorCode.W030_ANSEL_DEPRECATED,
                        "ANSEL encoding is deprecated in GEDCOM 5.5.5; "
                        "UTF-8 is recommended",
                        line=self._offset_to_line(char_offset),
                    )

    def _add_issue(
        self,
        code: ErrorCode,
        message: str,
        line: int | None = None,
        xref: str | None = None,
        context: str | None = None,
    ) -> None:
        """Add a validation issue."""
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                line=line,
                xref=xref,
                context=context,
            )
        )
