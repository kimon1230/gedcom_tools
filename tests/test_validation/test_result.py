import json

from gedcom_tools.progress import Colors, set_ascii_mode
from gedcom_tools.utils import EncodingInfo
from gedcom_tools.validation.issues import (
    ErrorCode,
    ValidationIssue,
)
from gedcom_tools.validation.result import ValidationResult


class TestValidationResult:
    def test_empty_result_is_success(self):
        result = ValidationResult(file_path="/test/file.ged")
        assert result.success is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_warnings_still_success(self):
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.W014_ISOLATED_INDI,
                    message="Individual alone",
                )
            ],
        )
        assert result.success is True
        assert len(result.warnings) == 1

    def test_errors_not_success(self):
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.E001_UNRESOLVED_XREF,
                    message="Not found",
                )
            ],
        )
        assert result.success is False
        assert len(result.errors) == 1

    def test_format_text_success(self):
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            encoding_info=EncodingInfo(encoding="UTF-8"),
            record_counts={"INDI": 5, "FAM": 2},
        )
        text = result.format_text(colors)
        assert "/test/file.ged" in text
        assert "UTF-8" in text
        assert "Valid" in text
        assert "5 INDI" in text

    def test_format_text_with_errors(self):
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.E001_UNRESOLVED_XREF,
                    message="Reference @X@ not found",
                    line=42,
                )
            ],
        )
        text = result.format_text(colors)
        assert "Invalid" in text
        assert "[E001]" in text
        assert "Line 42" in text

    def test_format_text_with_warnings(self):
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.W014_ISOLATED_INDI,
                    message="No family",
                )
            ],
        )
        text = result.format_text(colors)
        assert "Valid" in text
        assert "1 warning" in text

    def test_format_text_with_context(self):
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.E001_UNRESOLVED_XREF,
                    message="Not found",
                    context="1 FAMC @F99@",
                )
            ],
        )
        text = result.format_text(colors)
        assert "1 FAMC @F99@" in text

    def test_format_json_valid(self):
        result = ValidationResult(
            file_path="/test/file.ged",
            encoding_info=EncodingInfo(encoding="UTF-8", has_bom=True),
            record_counts={"INDI": 3},
        )
        json_str = result.format_json()
        data = json.loads(json_str)

        assert data["file"] == "/test/file.ged"
        assert data["valid"] is True
        assert data["encoding"]["detected"] == "UTF-8"
        assert data["encoding"]["has_bom"] is True
        assert data["record_counts"]["INDI"] == 3
        assert data["summary"]["errors"] == 0
        assert data["summary"]["warnings"] == 0
        assert len(data["issues"]) == 0

    def test_format_json_with_issues(self):
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.E001_UNRESOLVED_XREF,
                    message="Not found",
                    line=10,
                    xref="@I99@",
                ),
                ValidationIssue(
                    code=ErrorCode.W014_ISOLATED_INDI,
                    message="No family",
                ),
            ],
        )
        json_str = result.format_json()
        data = json.loads(json_str)

        assert data["valid"] is False
        assert data["summary"]["errors"] == 1
        assert data["summary"]["warnings"] == 1
        assert len(data["issues"]) == 2

        error = data["issues"][0]
        assert error["code"] == "E001"
        assert error["severity"] == "error"
        assert error["line"] == 10
        assert error["xref"] == "@I99@"

    def test_format_json_no_encoding(self):
        result = ValidationResult(file_path="/test/file.ged")
        json_str = result.format_json()
        data = json.loads(json_str)

        assert data["encoding"] is None

    def test_format_text_quiet_valid_file(self):
        """Quiet mode on valid file returns empty string."""
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            encoding_info=EncodingInfo(encoding="UTF-8"),
            record_counts={"INDI": 5},
        )
        text = result.format_text(colors, quiet=True)
        assert text == ""

    def test_format_text_quiet_warnings_only(self):
        """Quiet mode with only warnings returns empty string."""
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.W014_ISOLATED_INDI,
                    message="No family",
                )
            ],
        )
        text = result.format_text(colors, quiet=True)
        assert text == ""

    def test_format_text_quiet_with_errors(self):
        """Quiet mode shows only errors, no file info or warnings."""
        colors = Colors(force_disable=True)
        result = ValidationResult(
            file_path="/test/file.ged",
            encoding_info=EncodingInfo(encoding="UTF-8"),
            issues=[
                ValidationIssue(
                    code=ErrorCode.E001_UNRESOLVED_XREF,
                    message="Not found",
                    line=10,
                ),
                ValidationIssue(
                    code=ErrorCode.W014_ISOLATED_INDI,
                    message="No family",
                ),
            ],
        )
        text = result.format_text(colors, quiet=True)

        # Should contain error info
        assert "[E001]" in text
        assert "Line 10" in text

        # Should NOT contain file info, warnings, or summary
        assert "/test/file.ged" not in text
        assert "UTF-8" not in text
        assert "[W014]" not in text
        assert "Invalid" not in text
        assert "Valid" not in text


class TestSuppressedCounts:
    """The JSON suppression tally, exercised without going through the engine."""

    def _result(self, suppressed):
        return ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(code=ErrorCode.W002_TRAILING_WHITESPACE, message="ws"),
                ValidationIssue(
                    code=ErrorCode.W002_TRAILING_WHITESPACE,
                    message="40 more lines with this issue were suppressed",
                ),
            ],
            suppressed_counts=suppressed,
        )

    def test_suppressed_absent_when_nothing_was_dropped(self):
        summary = json.loads(self._result({}).format_json())["summary"]
        assert "suppressed" not in summary
        assert summary["total_warnings"] == 2

    def test_total_warnings_present_without_suppression(self):
        result = ValidationResult(file_path="/test/file.ged")
        summary = json.loads(result.format_json())["summary"]
        # Always emitted, so a consumer reads one key rather than branching.
        assert summary["total_warnings"] == 0

    def test_suppressed_emitted_when_non_empty(self):
        summary = json.loads(self._result({"W002": 40}).format_json())["summary"]
        assert summary["suppressed"] == {"W002": 40}
        # 2 reported, 40 dropped, 1 of the reported is the stand-in summary.
        assert summary["warnings"] == 2
        assert summary["total_warnings"] == 41

    def test_two_capped_codes_each_lose_one_stand_in(self):
        result = ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(code=ErrorCode.W002_TRAILING_WHITESPACE, message="a"),
                ValidationIssue(code=ErrorCode.W003_LINE_TOO_LONG, message="b"),
            ],
            suppressed_counts={"W002": 5, "W003": 7},
        )
        summary = json.loads(result.format_json())["summary"]
        assert summary["total_warnings"] == 2 + 12 - 2


class TestAsciiDecorations:
    def _result_with_context(self):
        return ValidationResult(
            file_path="/test/file.ged",
            issues=[
                ValidationIssue(
                    code=ErrorCode.E001_UNRESOLVED_XREF,
                    message="Not found",
                    context="1 FAMC @F99@",
                )
            ],
        )

    def test_ascii_mode_replaces_marks_and_arrow(self):
        set_ascii_mode(True)
        text = self._result_with_context().format_text(Colors(force_disable=True))
        assert "[!] Invalid" in text
        assert "-> 1 FAMC @F99@" in text
        text.encode("ascii")

    def test_unicode_mode_is_unchanged(self):
        text = self._result_with_context().format_text(Colors(force_disable=True))
        assert "✗ Invalid" in text
        assert "→ 1 FAMC @F99@" in text
