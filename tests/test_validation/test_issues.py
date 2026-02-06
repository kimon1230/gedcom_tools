"""Tests for validation issues module."""

from gedcom_tools.utils import EncodingInfo
from gedcom_tools.validation.issues import (
    ErrorCode,
    FamilyInfo,
    IndividualInfo,
    RecordInfo,
    Severity,
    UsageInfo,
    ValidationIssue,
)


class TestSeverity:
    def test_error_value(self):
        assert Severity.ERROR.value == "error"

    def test_warning_value(self):
        assert Severity.WARNING.value == "warning"


class TestErrorCode:
    def test_error_codes_start_with_e(self):
        error_codes = [c for c in ErrorCode if c.value.startswith("E")]
        assert len(error_codes) > 0
        for code in error_codes:
            assert code.severity == Severity.ERROR

    def test_warning_codes_start_with_w(self):
        warning_codes = [c for c in ErrorCode if c.value.startswith("W")]
        assert len(warning_codes) > 0
        for code in warning_codes:
            assert code.severity == Severity.WARNING

    def test_description_exists(self):
        """Every ErrorCode has a meaningful description that's not a fallback."""
        for code in ErrorCode:
            desc = code.description
            assert desc is not None
            assert desc != "Unknown issue", f"{code} missing description"
            assert len(desc) > 10, f"{code} description too short: {desc}"

    def test_specific_codes(self):
        assert ErrorCode.E001_UNRESOLVED_XREF.value == "E001"
        assert ErrorCode.E005_MISSING_HEAD.value == "E005"
        assert ErrorCode.W014_ISOLATED_INDI.value == "W014"


class TestValidationIssue:
    def test_basic_issue(self):
        issue = ValidationIssue(
            code=ErrorCode.E001_UNRESOLVED_XREF,
            message="Reference not found",
        )
        assert issue.severity == Severity.ERROR
        assert issue.line is None
        assert issue.xref is None

    def test_issue_with_all_fields(self):
        issue = ValidationIssue(
            code=ErrorCode.E001_UNRESOLVED_XREF,
            message="Reference not found",
            line=42,
            xref="@I99@",
            context="1 FAMC @I99@",
        )
        assert issue.line == 42
        assert issue.xref == "@I99@"
        assert issue.context == "1 FAMC @I99@"

    def test_str_representation(self):
        issue = ValidationIssue(
            code=ErrorCode.E001_UNRESOLVED_XREF,
            message="Reference not found",
            line=42,
            xref="@I99@",
        )
        s = str(issue)
        assert "[E001]" in s
        assert "Line 42" in s
        assert "@I99@" in s
        assert "Reference not found" in s

    def test_str_without_line(self):
        issue = ValidationIssue(
            code=ErrorCode.E001_UNRESOLVED_XREF,
            message="Reference not found",
        )
        s = str(issue)
        assert "[E001]" in s
        assert "Line" not in s


class TestEncodingInfo:
    def test_basic(self):
        info = EncodingInfo(encoding="UTF-8")
        assert str(info) == "UTF-8"

    def test_with_bom(self):
        info = EncodingInfo(encoding="UTF-8", has_bom=True)
        assert "with BOM" in str(info)

    def test_with_different_declared(self):
        info = EncodingInfo(
            encoding="UTF-8",
            declared_charset="ASCII",
        )
        assert "declared: ASCII" in str(info)

    def test_same_declared_not_shown(self):
        info = EncodingInfo(
            encoding="UTF-8",
            declared_charset="utf-8",
        )
        assert "declared" not in str(info)


class TestIndividualInfo:
    def test_basic(self):
        info = IndividualInfo(xref="@I1@", line=10)
        assert info.xref == "@I1@"
        assert info.line == 10
        assert info.birth_year is None
        assert info.famc_xrefs == []
        assert info.fams_xrefs == []

    def test_with_dates(self):
        info = IndividualInfo(
            xref="@I1@",
            line=10,
            birth_year=1900,
            death_year=1980,
        )
        assert info.birth_year == 1900
        assert info.death_year == 1980


class TestFamilyInfo:
    def test_basic(self):
        info = FamilyInfo(xref="@F1@", line=20)
        assert info.xref == "@F1@"
        assert info.husb_xref is None
        assert info.chil_xrefs == []

    def test_with_members(self):
        info = FamilyInfo(
            xref="@F1@",
            line=20,
            husb_xref="@I1@",
            wife_xref="@I2@",
            chil_xrefs=["@I3@", "@I4@"],
        )
        assert info.husb_xref == "@I1@"
        assert len(info.chil_xrefs) == 2


class TestRecordInfo:
    def test_basic(self):
        info = RecordInfo(xref="@N1@", record_type="NOTE", line=5)
        assert info.xref == "@N1@"
        assert info.record_type == "NOTE"
        assert info.line == 5


class TestUsageInfo:
    def test_basic(self):
        info = UsageInfo(line=15, context="1 SOUR @S1@")
        assert info.line == 15
        assert info.context == "1 SOUR @S1@"
