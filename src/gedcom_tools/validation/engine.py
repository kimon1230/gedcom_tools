"""Validation engine orchestrator."""

from __future__ import annotations

import re
from array import array
from bisect import bisect_left
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal

from ged4py.parser import CodecError, GedcomReader, IntegrityError, ParserError

from gedcom_tools.constants import MAX_FILE_SIZE_BYTES, VALID_SEX_VALUES
from gedcom_tools.dates import (
    MONTH_PATTERN,
    classify_date_precision,
    extract_month,
    extract_year_for_validation,
    has_unreadable_structure,
    is_phrase_date,
    phrase_text,
)
from gedcom_tools.progress import PhaseTracker
from gedcom_tools.utils import (
    EncodingInfo,
    detect_encoding,
    extract_xref,
    sanitize_error,
)
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


class FileTooLargeError(ValueError):
    """Raised when the input exceeds the supported file size.

    A ``ValueError`` subclass so existing callers catching ``ValueError``
    keep working. The distinct type is what lets ``commands/validate.py``
    report an anticipated policy rejection as a plain one-line message
    instead of routing it through the unexpected-exception handler, which
    would name the exception type and offer a traceback.
    """


# Maximum recommended line length per GEDCOM spec
MAX_LINE_LENGTH = 255

# Maximum nesting depth per GEDCOM spec (level numbers 0-99)
MAX_NESTING_DEPTH = 99

# How many issues of any one code get reported before the rest are collapsed
# into a single "N more suppressed" line. Applies to the unique-custom-tag
# warning and to the per-line formatting warnings (W002/W003/W032), which are
# otherwise unbounded: one issue object per offending line, on a file that can
# be 500 MB of them.
MAX_ISSUES_PER_CODE = 10

# "2 DATE (during the war)" - GEDCOM 5.5.1 permits a parenthesised DATE_PHRASE,
# and it is conformant, so W035 must not fire on it. [^)] not .* : the greedy
# form spans two phrases, exempting "(1850) and later (see note)", which is
# not a DATE_PHRASE and whose year really was guessed at.
_PAREN_DATE_RE = re.compile(rb"^\s*\d+\s+DATE\s+\([^)]*\)\s*$")

# Enough of the offending value to recognise it without pasting a whole note
_MAX_ECHOED_DATE = 60


# W035 walks these tags rather than calling sub_tag once per path: sub_tag
# returns the FIRST match, so a record carrying two BIRT events - the normal
# shape when two sources are merged - had its second date checked by nothing.
_INDI_DATED_EVENT_TAGS = ("BIRT", "CHR", "BAPM", "DEAT", "BURI")
_FAM_DATED_EVENT_TAGS = ("MARR",)


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
        self._line_offsets: array[int] = array("Q")
        self._warned_custom_tags: set[str] = set()
        # code.value -> issues of that code dropped by MAX_ISSUES_PER_CODE.
        # Keyed by the string, not the ErrorCode member: this reaches
        # json.dumps, which rejects enum keys.
        self._suppressed_counts: dict[str, int] = {}
        # Line numbers whose DATE value is a spec-legal parenthesised phrase.
        # ged4py strips the parens before exposing .phrase, so the parsed object
        # cannot tell "(during the war)" from "30 November 1989" - only the raw
        # bytes can, and _build_line_map is the one place that has them.
        self._paren_date_lines: array[int] = array("Q")
        self._nonstandard_date_count = 0

    def validate(self) -> ValidationResult:
        """Run all validation phases and return results.

        Raises
        ------
        FileTooLargeError
            If the file is larger than the supported maximum. ``filter`` and
            ``convert`` reject oversized input the same way; validation applies
            the same limit so one command does not silently accept a file the
            rest of the tool refuses.
        """
        file_size = self.file_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            msg = (
                f"File is too large ({actual_mb:.1f} MB). "
                f"Maximum supported size is {limit_mb} MB."
            )
            raise FileTooLargeError(msg)

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
            suppressed_counts=self._suppressed_counts,
        )

    def _build_line_map(self) -> None:
        """Build offset-to-line mapping and check line-level issues.

        Checks:
        - W002: Trailing whitespace
        - W003: Line too long (soft warning, always checked)
        - W032: Line too long strict (only in --strict mode)

        These are per-line checks, so a file that trips one of them on every
        line would otherwise produce one issue object per line. Each code is
        capped and the remainder reported as a single summary.
        """
        # "Q" (unsigned long long) keeps the map at 8 bytes per line instead of
        # a full Python int object per line.
        self._line_offsets = array("Q", [0])
        self._paren_date_lines = array("Q")
        seen: dict[ErrorCode, int] = {}
        with open(self.file_path, "rb") as f:
            offset = 0
            line_num = 0
            for line in f:
                line_num += 1
                line_content = line.rstrip(b"\r\n")

                # W002: Trailing whitespace
                if line_content != line_content.rstrip():
                    self._add_line_issue(
                        seen,
                        ErrorCode.W002_TRAILING_WHITESPACE,
                        "Line has trailing whitespace",
                        line_num,
                    )

                # W003/W032: Line length checks
                if len(line_content) > MAX_LINE_LENGTH:
                    if self.strict is not None:
                        self._add_line_issue(
                            seen,
                            ErrorCode.W032_LINE_TOO_LONG_STRICT,
                            f"Line exceeds {MAX_LINE_LENGTH} bytes "
                            f"({len(line_content)} bytes)",
                            line_num,
                        )
                    else:
                        self._add_line_issue(
                            seen,
                            ErrorCode.W003_LINE_TOO_LONG,
                            f"Line exceeds recommended {MAX_LINE_LENGTH} bytes "
                            f"({len(line_content)} bytes)",
                            line_num,
                        )

                # No endswith(b")") fast path here: the pattern ends \)\s*$,
                # so a conformant "(DATE_PHRASE)" with a trailing space would
                # skip the check and get a false W035. The guard measured 4.6x
                # on this line but only 0.6% of a validate run - not a trade
                # worth a false positive on spec-legal input.
                if _PAREN_DATE_RE.match(line_content):
                    # array("Q") rather than a set: one boxed int per matching
                    # line costs ~65 bytes against 8 here, and a file of
                    # parenthesised dates at the 500 MB cap measured ~3 GB.
                    # line_num only increases, so the array stays sorted and
                    # _is_paren_date_line can bisect it.
                    self._paren_date_lines.append(line_num)

                offset += len(line)
                self._line_offsets.append(offset)

        for code, count in seen.items():
            if count > MAX_ISSUES_PER_CODE:
                suppressed = count - MAX_ISSUES_PER_CODE
                self._suppressed_counts[code.value] = suppressed
                self._add_issue(
                    code,
                    f"{suppressed:,} more lines with this issue were "
                    f"suppressed (first {MAX_ISSUES_PER_CODE} shown)",
                )

    def _add_line_issue(
        self,
        seen: dict[ErrorCode, int],
        code: ErrorCode,
        message: str,
        line: int,
    ) -> None:
        """Record a per-line issue, up to the per-code reporting limit.

        ``seen`` keeps counting past the limit so the caller can report how
        many occurrences were left out.
        """
        count = seen.get(code, 0) + 1
        seen[code] = count
        if count <= MAX_ISSUES_PER_CODE:
            self._add_issue(code, message, line=line)

    def _raw_date_value(self, line: int) -> str:
        """The DATE value exactly as the file writes it.

        A structured mis-parse has no phrase text to echo, and str(date_val) is
        ged4py's NORMALISED rendering - "3/1990" comes back as "3/90" - which
        the user cannot find in their own file. Read the source line instead.

        Called at most MAX_ISSUES_PER_CODE times per run, so the re-read is
        cheaper than holding every DATE line in memory.
        """
        if not 1 <= line <= len(self._line_offsets):
            return ""
        try:
            with open(self.file_path, "rb") as f:
                f.seek(self._line_offsets[line - 1])
                raw = f.readline()
        except OSError:
            return ""

        encoding = "utf-8"
        if self.encoding_info is not None and self.encoding_info.encoding:
            encoding = self.encoding_info.encoding
        text = raw.decode(encoding, errors="replace").rstrip("\r\n")

        # Strip the "N DATE " prefix; keep everything after it verbatim.
        parts = text.strip().split(None, 2)
        return parts[2] if len(parts) > 2 else ""

    def _is_paren_date_line(self, line: int) -> bool:
        """Whether this line is a conformant parenthesised DATE_PHRASE.

        GEDCOM 5.5.1 permits "2 DATE (during the war)" and ged4py strips the
        parens, so only the byte-level pre-pass can tell it from a bare phrase.
        """
        lines = self._paren_date_lines
        idx = bisect_left(lines, line)
        return idx < len(lines) and lines[idx] == line

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
        except OSError as e:
            # A truncated header never reaches a CHAR record, so ged4py runs off
            # the end of the file. Report it rather than letting it escape as an
            # unhandled traceback from a phase the user cannot see into.
            self._add_issue(
                ErrorCode.E004_MALFORMED_LINE,
                f"Could not read file header: {e}",
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
        self._check_all_event_dates(record, _INDI_DATED_EVENT_TAGS)

        if birt_date_rec and birt_date_rec.value:
            # Age and chronology checks act on the year, so a year scraped
            # from free text must not reach them: "Reg. 1823 vol II" is an
            # archive reference, and reading it as a birth year invents a
            # 127-year lifespan the file never claimed.
            birth_year = extract_year_for_validation(birt_date_rec.value)
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
        self._check_all_event_dates(record, _FAM_DATED_EVENT_TAGS)

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
                    if len(self._warned_custom_tags) < MAX_ISSUES_PER_CODE:
                        self._add_issue(
                            ErrorCode.W004_CUSTOM_TAG,
                            f"Custom tag {tag} is non-standard",
                            line=self._offset_to_line(sub_offset),
                        )
                    elif len(self._warned_custom_tags) == MAX_ISSUES_PER_CODE:
                        self._add_issue(
                            ErrorCode.W004_CUSTOM_TAG,
                            f"Additional custom tags suppressed "
                            f"(>{MAX_ISSUES_PER_CODE} unique tags found)",
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

    def _check_all_event_dates(self, record: Record, tags: tuple[str, ...]) -> None:
        """Run W035 over every DATE under every matching event.

        One walk of sub_records rather than a sub_tag per path: sub_tag stops
        at the first match, so the second of two BIRT events was never checked.
        Each DATE is visited exactly once, which matters because the per-code
        cap counts emissions - a double visit would halve the reporting budget.
        """
        for sub in record.sub_records:
            if str(sub.tag).upper() not in tags:
                continue
            for child in sub.sub_records:
                if str(child.tag).upper() == "DATE" and child.value is not None:
                    self._check_nonstandard_date(child)

    def _check_nonstandard_date(self, date_rec: Record) -> None:
        """Warn when a DATE value is not in GEDCOM form.

        ged4py parses only three of the twelve month names in full, so
        "30 November 1989" is free text to it and its year is recovered
        heuristically. The user needs to know which dates were guessed at.
        """
        value = date_rec.value
        if value is None:
            return

        # Two routes in, and they must stay a union. The phrase route is the
        # original rule and covers everything ged4py could not parse at all.
        # The structural route covers what it parsed WRONG - "Reg 1823" as a
        # month "REG", "3/1990" as the dual year 3 - which looks structured and
        # is not a date. Keying the whole check on the trust gate instead would
        # SWAP the two sets rather than widen them: every clean phrase would go
        # silent. A merely implausible year is excluded on purpose; "25 DEC
        # 9999" is in GEDCOM form and its problem is the year, not the form.
        structural = False
        if is_phrase_date(value):
            text = phrase_text(value)
            if not text:
                return
        elif has_unreadable_structure(value):
            structural = True
            text = ""
        else:
            return

        offset = date_rec.offset if date_rec.offset else 0
        line = self._offset_to_line(offset)
        if self._is_paren_date_line(line):
            return

        if structural:
            text = self._raw_date_value(line)
            if not text:
                return

        count = self._nonstandard_date_count
        self._nonstandard_date_count += 1
        if count < MAX_ISSUES_PER_CODE:
            # Only suggest the abbreviation when the month is actually
            # spelled out - "10 JAN" is already abbreviated and its real
            # problem is the missing year, not the month form.
            # Scrub before truncating so the echo budget counts visible
            # characters, not stripped escape bytes - and so the cut cannot
            # land mid-escape. Both are inside the cap branch because the
            # result is only ever read here.
            shown = sanitize_error(text)
            if len(shown) > _MAX_ECHOED_DATE:
                shown = shown[:_MAX_ECHOED_DATE] + "..."

            # The month must be spelled out AND inside the echoed window -
            # pointing at an abbreviation for text we truncated away is not
            # an actionable message.
            month = MONTH_PATTERN.search(text)
            if (
                month is not None
                and len(month.group(1)) > 3
                and month.start() < _MAX_ECHOED_DATE
            ):
                hint = f' - use the 3-letter form "{month.group(1).upper()[:3]}"'
            else:
                hint = " - use the DD MMM YYYY form"
            self._add_issue(
                ErrorCode.W035_NONSTANDARD_DATE,
                f'Date not in GEDCOM format: "{shown}"{hint}',
                line=line,
            )
        elif count == MAX_ISSUES_PER_CODE:
            self._add_issue(
                ErrorCode.W035_NONSTANDARD_DATE,
                "More non-standard dates were suppressed "
                f"(first {MAX_ISSUES_PER_CODE} shown)",
                line=line,
            )
        # Only record a dropped count once the cap is actually exceeded.
        # ValidationResult subtracts one per entry, for the synthetic summary
        # issue each truncated code leaves behind - so writing a zero here
        # makes total_warnings report one FEWER than the file contains.
        if self._nonstandard_date_count > MAX_ISSUES_PER_CODE:
            self._suppressed_counts[ErrorCode.W035_NONSTANDARD_DATE.value] = (
                self._nonstandard_date_count - MAX_ISSUES_PER_CODE
            )

    def _extract_year(self, record: Record, path: str) -> int | None:
        """Extract year from a date at the given path."""
        date_rec = record.sub_tag(path)
        if date_rec is None or date_rec.value is None:
            return None
        return extract_year_for_validation(date_rec.value)

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
        """Add a validation issue.

        Text scrubbing happens in ValidationIssue itself, since the reference
        and semantic validators build issues without passing through here.
        """
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                line=line,
                xref=xref,
                context=context,
            )
        )
