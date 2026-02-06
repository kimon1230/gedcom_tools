"""Tests for the validation engine."""

from pathlib import Path

from gedcom_tools.validation import validate_file
from gedcom_tools.validation.issues import ErrorCode

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestValidateFile:
    def test_valid_file(self):
        result = validate_file(FIXTURES / "555sample.ged", quiet=True)
        assert result.success is True
        assert len(result.errors) == 0

    def test_valid_file_has_encoding_info(self):
        result = validate_file(FIXTURES / "555sample.ged", quiet=True)
        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "UTF-8"

    def test_valid_file_has_record_counts(self):
        result = validate_file(FIXTURES / "555sample.ged", quiet=True)
        assert "INDI" in result.record_counts
        assert result.record_counts["INDI"] == 3

    def test_missing_head(self):
        result = validate_file(FIXTURES / "missing_head.ged", mode="full", quiet=True)
        head_errors = [
            i for i in result.issues if i.code == ErrorCode.E005_MISSING_HEAD
        ]
        assert len(head_errors) == 1

    def test_missing_trlr(self):
        result = validate_file(FIXTURES / "missing_trlr.ged", mode="full", quiet=True)
        trlr_errors = [
            i for i in result.issues if i.code == ErrorCode.E006_MISSING_TRLR
        ]
        assert len(trlr_errors) == 1

    def test_unresolved_xref(self):
        result = validate_file(
            FIXTURES / "unresolved_xref.ged", mode="full", quiet=True
        )
        xref_errors = [
            i for i in result.issues if i.code == ErrorCode.E001_UNRESOLVED_XREF
        ]
        assert len(xref_errors) == 1
        assert "@F99@" in xref_errors[0].message

    def test_duplicate_xref(self):
        result = validate_file(FIXTURES / "duplicate_xref.ged", mode="full", quiet=True)
        dup_errors = [
            i for i in result.issues if i.code == ErrorCode.E002_DUPLICATE_XREF
        ]
        assert len(dup_errors) == 1

    def test_ancestry_cycle(self):
        result = validate_file(FIXTURES / "ancestry_cycle.ged", mode="full", quiet=True)
        cycle_errors = [
            i for i in result.issues if i.code == ErrorCode.E010_ANCESTRY_CYCLE
        ]
        assert len(cycle_errors) >= 1

    def test_death_before_birth(self):
        result = validate_file(
            FIXTURES / "death_before_birth.ged", mode="full", quiet=True
        )
        date_errors = [
            i for i in result.issues if i.code == ErrorCode.E011_DEATH_BEFORE_BIRTH
        ]
        assert len(date_errors) == 1

    def test_orphaned_source(self):
        result = validate_file(
            FIXTURES / "orphaned_source.ged", mode="full", quiet=True
        )
        orphan_warnings = [
            i for i in result.issues if i.code == ErrorCode.W012_ORPHANED_SOUR
        ]
        assert len(orphan_warnings) == 1

    def test_isolated_individual(self):
        result = validate_file(
            FIXTURES / "isolated_individual.ged", mode="full", quiet=True
        )
        isolated_warnings = [
            i for i in result.issues if i.code == ErrorCode.W014_ISOLATED_INDI
        ]
        assert len(isolated_warnings) == 1

    def test_empty_family(self):
        result = validate_file(FIXTURES / "empty_family.ged", mode="full", quiet=True)
        empty_warnings = [
            i for i in result.issues if i.code == ErrorCode.W015_EMPTY_FAM
        ]
        assert len(empty_warnings) == 1

    def test_parent_too_young(self):
        result = validate_file(
            FIXTURES / "parent_too_young.ged", mode="full", quiet=True
        )
        age_warnings = [
            i for i in result.issues if i.code == ErrorCode.W020_PARENT_TOO_YOUNG
        ]
        assert len(age_warnings) == 1

    def test_direct_note_reference_not_orphaned(self):
        result = validate_file(FIXTURES / "note_reference.ged", mode="full", quiet=True)
        orphan_warnings = [
            i for i in result.issues if i.code == ErrorCode.W010_ORPHANED_NOTE
        ]
        # NOTE @N1@ is referenced directly by INDI, should not be orphaned
        assert len(orphan_warnings) == 0


class TestQuickMode:
    def test_quick_mode_stops_on_first_error(self):
        result = validate_file(
            FIXTURES / "duplicate_xref.ged", mode="quick", quiet=True
        )
        # Should have the duplicate error but may not continue to find all issues
        assert not result.success
        assert len(result.errors) >= 1

    def test_full_mode_collects_all(self):
        result = validate_file(FIXTURES / "duplicate_xref.ged", mode="full", quiet=True)
        # Full mode should find all issues
        assert not result.success


class TestValidateFileInterface:
    def test_accepts_string_path(self):
        result = validate_file(str(FIXTURES / "555sample.ged"), quiet=True)
        assert result.success is True

    def test_accepts_path_object(self):
        result = validate_file(FIXTURES / "555sample.ged", quiet=True)
        assert result.success is True


class TestLineChecks:
    """Tests for line-level validation checks."""

    def test_trailing_whitespace(self):
        result = validate_file(
            FIXTURES / "trailing_whitespace.ged", mode="full", quiet=True
        )
        whitespace_warnings = [
            i for i in result.issues if i.code == ErrorCode.W002_TRAILING_WHITESPACE
        ]
        assert len(whitespace_warnings) >= 1
        assert "whitespace" in whitespace_warnings[0].message.lower()

    def test_content_after_trlr(self):
        result = validate_file(
            FIXTURES / "content_after_trlr.ged", mode="full", quiet=True
        )
        after_trlr_errors = [
            i for i in result.issues if i.code == ErrorCode.E007_CONTENT_AFTER_TRLR
        ]
        assert len(after_trlr_errors) >= 1
        assert "TRLR" in after_trlr_errors[0].message

    def test_custom_tag_at_level_0(self):
        result = validate_file(
            FIXTURES / "custom_level0_tag.ged", mode="full", quiet=True
        )
        custom_warnings = [
            i for i in result.issues if i.code == ErrorCode.W004_CUSTOM_TAG
        ]
        assert len(custom_warnings) >= 1
        assert "_CUSTOM" in custom_warnings[0].message


class TestStrictModeChecks:
    """Tests for strict mode validation checks."""

    def test_missing_gedc_vers(self):
        result = validate_file(
            FIXTURES / "missing_gedc_vers.ged", mode="full", strict="5.5.1", quiet=True
        )
        vers_errors = [
            i for i in result.issues if i.code == ErrorCode.E014_MISSING_GEDC_VERS
        ]
        assert len(vers_errors) == 1
        assert "VERS" in vers_errors[0].message

    def test_missing_char(self):
        result = validate_file(
            FIXTURES / "missing_char.ged", mode="full", strict="5.5.1", quiet=True
        )
        char_errors = [
            i for i in result.issues if i.code == ErrorCode.E016_MISSING_CHAR
        ]
        assert len(char_errors) == 1
        assert "CHAR" in char_errors[0].message

    def test_strict_quick_mode_stops_on_missing_gedc(self):
        result = validate_file(
            FIXTURES / "missing_gedc.ged", mode="quick", strict="5.5.1", quiet=True
        )
        assert not result.success
        gedc_errors = [
            i for i in result.issues if i.code == ErrorCode.E013_MISSING_GEDC
        ]
        assert len(gedc_errors) >= 1

    def test_strict_quick_mode_stops_on_missing_sour(self):
        result = validate_file(
            FIXTURES / "missing_sour.ged", mode="quick", strict="5.5.1", quiet=True
        )
        assert not result.success
        sour_errors = [
            i for i in result.issues if i.code == ErrorCode.E015_MISSING_SOUR
        ]
        assert len(sour_errors) >= 1


class TestVerboseMode:
    """Tests for verbose mode."""

    def test_verbose_mode_accepted(self):
        result = validate_file(
            FIXTURES / "555sample.ged", mode="full", verbose=True, quiet=False
        )
        assert result.success is True


class TestExceptionPaths:
    """Tests for parser exception handling paths."""

    def test_invalid_level_integrity_error(self):
        result = validate_file(FIXTURES / "invalid_level.ged", mode="full", quiet=True)
        level_errors = [
            i for i in result.issues if i.code == ErrorCode.E003_INVALID_LEVEL
        ]
        assert len(level_errors) >= 1
        assert not result.success

    def test_invalid_level_quick_mode(self):
        result = validate_file(FIXTURES / "invalid_level.ged", mode="quick", quiet=True)
        assert not result.success
        assert len(result.errors) >= 1

    def test_malformed_line_parser_error(self):
        result = validate_file(FIXTURES / "malformed_line.ged", mode="full", quiet=True)
        parse_errors = [
            i for i in result.issues if i.code == ErrorCode.E004_MALFORMED_LINE
        ]
        assert len(parse_errors) >= 1
        assert not result.success

    def test_malformed_line_quick_mode(self):
        result = validate_file(
            FIXTURES / "malformed_line.ged", mode="quick", quiet=True
        )
        assert not result.success
        assert len(result.errors) >= 1


class TestOffsetToLine:
    def test_empty_line_offsets_returns_zero(self):
        from gedcom_tools.validation.engine import ValidationEngine

        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = []
        assert engine._offset_to_line(100) == 0

    def test_offset_at_exact_boundary(self):
        from gedcom_tools.validation.engine import ValidationEngine

        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = [0, 10, 20, 30]
        assert engine._offset_to_line(10) == 2  # Line 2 starts at offset 10

    def test_offset_beyond_file(self):
        from gedcom_tools.validation.engine import ValidationEngine

        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = [0, 10, 20, 30]
        result = engine._offset_to_line(1000)
        assert result == 4  # Last line

    def test_offset_in_middle_of_line(self):
        from gedcom_tools.validation.engine import ValidationEngine

        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = [0, 10, 20, 30]
        assert engine._offset_to_line(15) == 2  # Between line 2 (10) and line 3 (20)

    def test_offset_zero(self):
        from gedcom_tools.validation.engine import ValidationEngine

        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = [0, 10, 20, 30]
        assert engine._offset_to_line(0) == 1


class TestEncodingErrors:
    def test_invalid_encoding_reports_error(self):
        result = validate_file(
            FIXTURES / "invalid_encoding.ged",
            mode="full",
            quiet=True,
        )
        # File should either be invalid or have encoding-related issues
        assert not result.success or any(
            "encoding" in str(i.message).lower() for i in result.issues
        )
