"""Tests for validation result formatting."""

import json

from gedcom_tools.progress import Colors
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
