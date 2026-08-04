from array import array
from pathlib import Path

import pytest

from gedcom_tools.constants import MAX_FILE_SIZE_BYTES
from gedcom_tools.validation import validate_file
from gedcom_tools.validation.engine import MAX_ISSUES_PER_CODE, ValidationEngine
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

    def test_deeply_nested_note_reference_not_orphaned(self, tmp_path):
        ged = tmp_path / "nested_note.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 BIRT\n"
            "2 SOUR @S1@\n"
            "3 NOTE @N1@\n"
            "0 @S1@ SOUR\n"
            "1 TITL Parish register\n"
            "0 @N1@ NOTE Cited in the baptism entry.\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        # @N1@ is cited at level 3 under BIRT/SOUR, so it is not orphaned
        orphan_warnings = [
            i for i in result.issues if i.code == ErrorCode.W010_ORPHANED_NOTE
        ]
        assert orphan_warnings == []


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


class TestSubmitterReference:
    """W005 keys off the SUBM pointer in HEAD, not on a SUBM record existing."""

    HEADER = (
        "0 HEAD\n"
        "1 SOUR Test\n"
        "1 GEDC\n"
        "2 VERS 5.5.1\n"
        "2 FORM LINEAGE-LINKED\n"
        "1 CHAR UTF-8\n"
    )
    BODY = "0 @I1@ INDI\n1 NAME John /Doe/\n0 TRLR\n"

    def test_head_without_subm_warns(self, tmp_path):
        ged = tmp_path / "no_subm.ged"
        ged.write_text(self.HEADER + self.BODY, encoding="utf-8")

        result = validate_file(ged, mode="full", quiet=True)
        subm_warnings = [
            i for i in result.issues if i.code == ErrorCode.W005_MISSING_SUBM
        ]
        assert len(subm_warnings) == 1
        assert "SUBM" in subm_warnings[0].message
        assert subm_warnings[0].line == 1
        assert result.success is True  # a warning must not fail the file

    def test_head_with_subm_is_quiet(self, tmp_path):
        ged = tmp_path / "with_subm.ged"
        ged.write_text(
            self.HEADER
            + "1 SUBM @U1@\n"
            + "0 @U1@ SUBM\n"
            + "1 NAME Test Submitter\n"
            + self.BODY,
            encoding="utf-8",
        )

        result = validate_file(ged, mode="full", quiet=True)
        assert not any(i.code == ErrorCode.W005_MISSING_SUBM for i in result.issues)


class TestStrictModeChecks:

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

    def test_verbose_mode_accepted(self):
        result = validate_file(
            FIXTURES / "555sample.ged", mode="full", verbose=True, quiet=False
        )
        assert result.success is True


class TestExceptionPaths:

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

    def test_bom_conflicting_with_char_reports_decode_failure(self, tmp_path):
        ged = tmp_path / "conflict.ged"
        ged.write_bytes(b"\xef\xbb\xbf0 HEAD\n1 CHAR ASCII\n0 TRLR\n")
        result = validate_file(ged, mode="full", quiet=True)
        decode_errors = [
            i for i in result.issues if i.code == ErrorCode.E008_DECODE_FAILURE
        ]
        assert len(decode_errors) == 1
        assert "BOM codec" in decode_errors[0].message
        assert not result.success

    def test_truncated_header_reports_a_read_failure(self, tmp_path):
        # The header runs off the end of the file, so encoding detection cannot
        # complete. Without a handler this surfaced as a bare OSError traceback.
        ged = tmp_path / "truncated.ged"
        ged.write_bytes(b"0 HEAD\n1 CHAR")
        result = validate_file(ged, mode="quick", quiet=True)
        assert not result.success
        assert [i.code for i in result.errors] == [ErrorCode.E004_MALFORMED_LINE]
        assert "Could not read file header" in result.errors[0].message


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


class TestAnselSupport:

    def test_ansel_file_validates_successfully(self, tmp_path):
        """ANSEL-declared file with ASCII content validates cleanly."""
        ged = tmp_path / "ansel.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "2 FORM LINEAGE-LINKED\n"
            "1 CHAR ANSEL\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        assert result.success is True
        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "ANSEL"

    def test_ansel_file_with_diacritics(self, tmp_path):
        """ANSEL file with combining diacritics parses without errors."""
        ged = tmp_path / "ansel_diacritics.ged"
        # ANSEL combining acute (0xE2) precedes the base character
        lines = [
            b"0 HEAD\n",
            b"1 SOUR Test\n",
            b"1 GEDC\n",
            b"2 VERS 5.5.1\n",
            b"2 FORM LINEAGE-LINKED\n",
            b"1 CHAR ANSEL\n",
            b"0 @I1@ INDI\n",
            b"1 NAME Jos\xe2e /Garc\xe2ia/\n",
            b"0 TRLR\n",
        ]
        ged.write_bytes(b"".join(lines))

        result = validate_file(ged, mode="full", quiet=True)
        assert result.success is True
        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "ANSEL"

    def test_royal92_validates_without_ansel_error(self):
        """royal92.ged is recognised as ANSEL rather than rejected as unreadable."""
        royal92 = FIXTURES / "royal92.ged"
        result = validate_file(royal92, mode="full", quiet=True)

        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "ANSEL"

    def test_malformed_ansel_gets_decode_error(self, tmp_path):
        """Invalid ANSEL byte triggers E008 decode failure."""
        ged = tmp_path / "bad_ansel.ged"
        lines = [
            b"0 HEAD\n",
            b"1 SOUR Test\n",
            b"1 GEDC\n",
            b"2 VERS 5.5.1\n",
            b"2 FORM LINEAGE-LINKED\n",
            b"1 CHAR ANSEL\n",
            b"0 @I1@ INDI\n",
            b"1 NAME \xff /Bad/\n",
            b"0 TRLR\n",
        ]
        ged.write_bytes(b"".join(lines))

        result = validate_file(ged, mode="full", quiet=True)
        assert result.success is False
        error_codes = {i.code for i in result.errors}
        assert ErrorCode.E008_DECODE_FAILURE in error_codes


class TestSexValidation:
    def test_multiple_sex_records_w027(self, tmp_path):
        ged = tmp_path / "multi_sex.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "1 SEX M\n"
            "1 SEX F\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w027 = [i for i in result.issues if i.code == ErrorCode.W027_MULTIPLE_SEX]
        assert len(w027) == 1
        assert "2 SEX records" in w027[0].message

    def test_invalid_sex_value_w028(self, tmp_path):
        ged = tmp_path / "bad_sex.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "1 SEX Z\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w028 = [i for i in result.issues if i.code == ErrorCode.W028_INVALID_SEX]
        assert len(w028) == 1
        assert "Z" in w028[0].message

    def test_valid_sex_no_warning(self, tmp_path):
        ged = tmp_path / "valid_sex.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME Jane /Smith/\n"
            "1 SEX F\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w027 = [i for i in result.issues if i.code == ErrorCode.W027_MULTIPLE_SEX]
        w028 = [i for i in result.issues if i.code == ErrorCode.W028_INVALID_SEX]
        assert len(w027) == 0
        assert len(w028) == 0

    def test_sex_u_and_x_are_valid(self, tmp_path):
        ged = tmp_path / "sex_u.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME Pat /Smith/\n"
            "1 SEX U\n"
            "0 @I2@ INDI\n"
            "1 NAME Alex /Jones/\n"
            "1 SEX X\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w028 = [i for i in result.issues if i.code == ErrorCode.W028_INVALID_SEX]
        assert len(w028) == 0


class TestObjeValidation:
    def test_obje_missing_file_w033(self, tmp_path):
        ged = tmp_path / "obje_no_file.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @O1@ OBJE\n"
            "1 TITL Photo\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w033 = [i for i in result.issues if i.code == ErrorCode.W033_OBJE_MISSING_FILE]
        assert len(w033) == 1
        assert "@O1@" in w033[0].message

    def test_file_missing_form_w034(self, tmp_path):
        ged = tmp_path / "file_no_form.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @O1@ OBJE\n"
            "1 FILE photo.jpg\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w034 = [i for i in result.issues if i.code == ErrorCode.W034_FILE_MISSING_FORM]
        assert len(w034) == 1
        assert "@O1@" in w034[0].message

    def test_obje_with_file_and_form_no_warning(self, tmp_path):
        ged = tmp_path / "obje_ok.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @O1@ OBJE\n"
            "1 FILE photo.jpg\n"
            "2 FORM JPEG\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w033 = [i for i in result.issues if i.code == ErrorCode.W033_OBJE_MISSING_FILE]
        w034 = [i for i in result.issues if i.code == ErrorCode.W034_FILE_MISSING_FORM]
        assert len(w033) == 0
        assert len(w034) == 0

    def test_two_files_one_without_form(self, tmp_path):
        ged = tmp_path / "two_files.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @O1@ OBJE\n"
            "1 FILE photo.jpg\n"
            "2 FORM JPEG\n"
            "1 FILE doc.pdf\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w034 = [i for i in result.issues if i.code == ErrorCode.W034_FILE_MISSING_FORM]
        assert len(w034) == 1

    def test_two_files_both_missing_form(self, tmp_path):
        ged = tmp_path / "two_no_form.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @O1@ OBJE\n"
            "1 FILE photo.jpg\n"
            "1 FILE doc.pdf\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w034 = [i for i in result.issues if i.code == ErrorCode.W034_FILE_MISSING_FORM]
        assert len(w034) == 2


class TestAsymmetricLinkIntegration:
    def test_one_sided_chil_link_w016(self, tmp_path):
        ged = tmp_path / "asym_child.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "0 @F1@ FAM\n"
            "1 CHIL @I1@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w016 = [
            i for i in result.issues if i.code == ErrorCode.W016_ASYMMETRIC_CHILD_LINK
        ]
        assert len(w016) == 1
        assert "@I1@" in w016[0].message

    def test_one_sided_fams_link_w017(self, tmp_path):
        ged = tmp_path / "asym_spouse.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "1 FAMS @F1@\n"
            "0 @F1@ FAM\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w017 = [
            i for i in result.issues if i.code == ErrorCode.W017_ASYMMETRIC_SPOUSE_LINK
        ]
        assert len(w017) == 1
        assert "@I1@" in w017[0].message


class TestSiblingSpacingIntegration:
    def test_siblings_4_months_apart_w026(self, tmp_path):
        ged = tmp_path / "close_siblings.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME Child1 /Smith/\n"
            "1 BIRT\n"
            "2 DATE 15 JAN 1980\n"
            "1 FAMC @F1@\n"
            "0 @I2@ INDI\n"
            "1 NAME Child2 /Smith/\n"
            "1 BIRT\n"
            "2 DATE 20 MAY 1980\n"
            "1 FAMC @F1@\n"
            "0 @F1@ FAM\n"
            "1 CHIL @I1@\n"
            "1 CHIL @I2@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w026 = [i for i in result.issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 1
        assert "4 months" in w026[0].message


class TestSexRoleMismatchIntegration:
    def test_husb_with_sex_f_w029(self, tmp_path):
        ged = tmp_path / "sex_role.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME Jane /Smith/\n"
            "1 SEX F\n"
            "1 FAMS @F1@\n"
            "0 @F1@ FAM\n"
            "1 HUSB @I1@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        w029 = [i for i in result.issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 1
        assert "HUSB" in w029[0].message
        assert "SEX=F" in w029[0].message


class TestReservedEscapes:
    """@#DGREGORIAN@ and @@ are escapes, not pointers — see GEDCOM 5.5.1 escape."""

    def test_fixture_has_no_unresolved_xref_errors(self):
        result = validate_file(
            FIXTURES / "reserved_escape.ged", mode="full", quiet=True
        )
        xref_errors = [
            i for i in result.issues if i.code == ErrorCode.E001_UNRESOLVED_XREF
        ]
        assert xref_errors == []

    def test_fixture_validates_clean(self):
        result = validate_file(
            FIXTURES / "reserved_escape.ged", mode="full", quiet=True
        )
        assert result.success is True

    def test_calendar_escape_nested_under_event(self, tmp_path):
        ged = tmp_path / "cal_escape.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME T /P/\n"
            "1 EVEN\n"
            "2 TYPE @#DGREGORIAN@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        assert [
            i for i in result.issues if i.code == ErrorCode.E001_UNRESOLVED_XREF
        ] == []

    def test_escaped_at_sign_directly_under_indi(self, tmp_path):
        # Level 1 NOTE takes the dedicated branch, not the recursive collector
        ged = tmp_path / "at_escape.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME T /P/\n"
            "1 NOTE @@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        assert [
            i for i in result.issues if i.code == ErrorCode.E001_UNRESOLVED_XREF
        ] == []

    def test_escaped_at_sign_directly_under_fam(self, tmp_path):
        ged = tmp_path / "fam_at_escape.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME T /P/\n"
            "1 FAMS @F1@\n"
            "0 @F1@ FAM\n"
            "1 HUSB @I1@\n"
            "1 NOTE @@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        assert [
            i for i in result.issues if i.code == ErrorCode.E001_UNRESOLVED_XREF
        ] == []

    def test_real_xrefs_alongside_escapes_still_resolve(self):
        # No W014 means the FAMS/HUSB/WIFE pointers were collected as usages
        result = validate_file(
            FIXTURES / "reserved_escape.ged", mode="full", quiet=True
        )
        assert [
            i for i in result.issues if i.code == ErrorCode.W014_ISOLATED_INDI
        ] == []

    def test_genuinely_unresolved_reference_still_errors(self, tmp_path):
        ged = tmp_path / "mixed.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 SOUR Test\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME T /P/\n"
            "1 NOTE @@\n"
            "1 NOTE @N9@\n"
            "1 EVEN\n"
            "2 TYPE @#DGREGORIAN@\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        result = validate_file(ged, mode="full", quiet=True)
        xref_errors = [
            i for i in result.issues if i.code == ErrorCode.E001_UNRESOLVED_XREF
        ]
        assert len(xref_errors) == 1
        assert "@N9@" in xref_errors[0].message


class TestExtractXrefGuard:
    def test_calendar_escape_rejected(self):
        assert ValidationEngine._extract_xref("@#DGREGORIAN@") is None

    def test_alternate_calendar_escapes_rejected(self):
        for escape in ("@#DJULIAN@", "@#DHEBREW@", "@#DFRENCH R@", "@#DROMAN@"):
            assert ValidationEngine._extract_xref(escape) is None

    def test_double_at_rejected(self):
        assert ValidationEngine._extract_xref("@@") is None

    def test_bare_at_rejected(self):
        assert ValidationEngine._extract_xref("@") is None

    def test_empty_string_rejected(self):
        assert ValidationEngine._extract_xref("") is None

    def test_individual_pointer_passes(self):
        assert ValidationEngine._extract_xref("@I1@") == "@I1@"

    def test_family_pointer_passes(self):
        assert ValidationEngine._extract_xref("@F1@") == "@F1@"

    def test_single_character_pointer_passes(self):
        assert ValidationEngine._extract_xref("@N@") == "@N@"

    def test_none_passes_through(self):
        # ged4py yields None for BIRT/DEAT/BURI values
        assert ValidationEngine._extract_xref(None) is None

    def test_name_tuple_passes_through(self):
        # ged4py yields (given, surname, suffix) for NAME
        assert ValidationEngine._extract_xref(("Robert Eugene", "Williams", "")) is None

    def test_plain_text_value_passes_through(self):
        assert ValidationEngine._extract_xref("Cited in the baptism entry.") is None

    def test_object_with_xref_id_still_resolved(self):
        class Pointer:
            xref_id = "@S1@"

        assert ValidationEngine._extract_xref(Pointer()) == "@S1@"


def _write_ged(path, body_lines):
    """Write a minimal valid 5.5.1 file wrapped around the given body lines."""
    header = [
        "0 HEAD",
        "1 SOUR Test",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
    ]
    path.write_text(
        "\n".join(header + list(body_lines) + ["0 TRLR", ""]),
        encoding="utf-8",
    )
    return path


class TestLineIssueCap:
    def test_trailing_whitespace_capped(self, tmp_path):
        body = []
        for i in range(25):
            body.extend([f"0 @I{i}@ INDI", f"1 NAME Person{i} /Test/ "])
        ged = _write_ged(tmp_path / "ws.ged", body)

        result = validate_file(ged, mode="full", quiet=True)
        warnings = [
            i for i in result.issues if i.code == ErrorCode.W002_TRAILING_WHITESPACE
        ]
        per_line = [i for i in warnings if i.line is not None]
        summaries = [i for i in warnings if i.line is None]

        assert len(per_line) == MAX_ISSUES_PER_CODE
        assert len(summaries) == 1
        assert "15 more" in summaries[0].message
        assert "suppressed" in summaries[0].message

    def test_below_cap_has_no_summary(self, tmp_path):
        body = []
        for i in range(3):
            body.extend([f"0 @I{i}@ INDI", f"1 NAME Person{i} /Test/ "])
        ged = _write_ged(tmp_path / "few_ws.ged", body)

        result = validate_file(ged, mode="full", quiet=True)
        warnings = [
            i for i in result.issues if i.code == ErrorCode.W002_TRAILING_WHITESPACE
        ]
        assert len(warnings) == 3
        assert all(i.line is not None for i in warnings)

    def test_exactly_at_cap_has_no_summary(self, tmp_path):
        body = []
        for i in range(MAX_ISSUES_PER_CODE):
            body.extend([f"0 @I{i}@ INDI", f"1 NAME Person{i} /Test/ "])
        ged = _write_ged(tmp_path / "cap_ws.ged", body)

        result = validate_file(ged, mode="full", quiet=True)
        warnings = [
            i for i in result.issues if i.code == ErrorCode.W002_TRAILING_WHITESPACE
        ]
        assert len(warnings) == MAX_ISSUES_PER_CODE
        assert all(i.line is not None for i in warnings)

    def test_one_over_cap_reports_single_remainder(self, tmp_path):
        body = []
        for i in range(MAX_ISSUES_PER_CODE + 1):
            body.extend([f"0 @I{i}@ INDI", f"1 NAME Person{i} /Test/ "])
        ged = _write_ged(tmp_path / "over_ws.ged", body)

        result = validate_file(ged, mode="full", quiet=True)
        summaries = [
            i
            for i in result.issues
            if i.code == ErrorCode.W002_TRAILING_WHITESPACE and i.line is None
        ]
        assert len(summaries) == 1
        assert "1 more" in summaries[0].message

    def test_line_too_long_capped(self, tmp_path):
        filler = "x" * 300
        body = []
        for i in range(14):
            body.extend([f"0 @N{i}@ NOTE {filler}"])
        ged = _write_ged(tmp_path / "long.ged", body)

        result = validate_file(ged, mode="full", quiet=True)
        warnings = [i for i in result.issues if i.code == ErrorCode.W003_LINE_TOO_LONG]
        assert len([i for i in warnings if i.line is not None]) == (MAX_ISSUES_PER_CODE)
        summaries = [i for i in warnings if i.line is None]
        assert len(summaries) == 1
        assert "4 more" in summaries[0].message

    def test_strict_line_too_long_capped(self, tmp_path):
        filler = "x" * 300
        body = [f"0 @N{i}@ NOTE {filler}" for i in range(14)]
        ged = _write_ged(tmp_path / "long_strict.ged", body)

        result = validate_file(ged, mode="full", strict="5.5.1", quiet=True)
        warnings = [
            i for i in result.issues if i.code == ErrorCode.W032_LINE_TOO_LONG_STRICT
        ]
        assert len([i for i in warnings if i.line is not None]) == (MAX_ISSUES_PER_CODE)
        assert len([i for i in warnings if i.line is None]) == 1
        assert not any(i.code == ErrorCode.W003_LINE_TOO_LONG for i in result.issues)

    def test_codes_are_capped_independently(self, tmp_path):
        filler = "x" * 300
        body = []
        for i in range(12):
            body.extend([f"0 @I{i}@ INDI", f"1 NAME Person{i} /Test/ "])
        for i in range(12):
            body.append(f"0 @N{i}@ NOTE {filler}")
        ged = _write_ged(tmp_path / "both.ged", body)

        result = validate_file(ged, mode="full", quiet=True)
        for code in (
            ErrorCode.W002_TRAILING_WHITESPACE,
            ErrorCode.W003_LINE_TOO_LONG,
        ):
            matching = [i for i in result.issues if i.code == code]
            assert len([i for i in matching if i.line is not None]) == (
                MAX_ISSUES_PER_CODE
            )
            assert len([i for i in matching if i.line is None]) == 1


class TestLineOffsetStorage:
    def test_offsets_use_compact_array(self, tmp_path):
        ged = _write_ged(tmp_path / "offsets.ged", ["0 @I1@ INDI", "1 NAME A /B/"])
        engine = ValidationEngine(ged, mode="full", quiet=True)
        engine.validate()

        assert isinstance(engine._line_offsets, array)
        assert engine._line_offsets.typecode == "Q"
        assert engine._line_offsets[0] == 0
        assert list(engine._line_offsets) == sorted(engine._line_offsets)

    def test_offsets_match_byte_positions(self, tmp_path):
        ged = _write_ged(tmp_path / "positions.ged", ["0 @I1@ INDI", "1 NAME A /B/"])
        engine = ValidationEngine(ged, mode="full", quiet=True)
        engine.validate()

        raw = ged.read_bytes()
        expected = [0]
        for line in raw.splitlines(keepends=True):
            expected.append(expected[-1] + len(line))
        assert list(engine._line_offsets) == expected

    def test_reported_line_numbers_still_correct(self, tmp_path):
        # Trailing whitespace sits on the 8th line of the assembled file
        ged = _write_ged(
            tmp_path / "lines.ged", ["0 @I1@ INDI", "1 NAME John /Smith/ "]
        )
        result = validate_file(ged, mode="full", quiet=True)
        warnings = [
            i for i in result.issues if i.code == ErrorCode.W002_TRAILING_WHITESPACE
        ]
        assert len(warnings) == 1
        assert warnings[0].line == 8

    def test_offset_to_line_works_with_array(self):
        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = array("Q", [0, 10, 20, 30])
        assert engine._offset_to_line(0) == 1
        assert engine._offset_to_line(10) == 2
        assert engine._offset_to_line(25) == 3
        assert engine._offset_to_line(1000) == 4

    def test_empty_array_returns_zero(self):
        engine = ValidationEngine.__new__(ValidationEngine)
        engine._line_offsets = array("Q")
        assert engine._offset_to_line(100) == 0


class TestFileSizeLimit:
    def test_oversized_file_rejected(self, tmp_path):
        big = tmp_path / "big.ged"
        with open(big, "wb") as f:
            f.seek(MAX_FILE_SIZE_BYTES + 1)
            f.write(b"\x00")

        with pytest.raises(ValueError, match="too large"):
            validate_file(big, mode="full", quiet=True)

    def test_error_includes_size_and_limit(self, tmp_path):
        big = tmp_path / "big.ged"
        with open(big, "wb") as f:
            f.seek(MAX_FILE_SIZE_BYTES + 1)
            f.write(b"\x00")

        with pytest.raises(ValueError, match="Maximum supported size is 500 MB"):
            validate_file(big, mode="full", quiet=True)

    def test_file_at_limit_is_accepted(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gedcom_tools.validation.engine.MAX_FILE_SIZE_BYTES", 4096)
        ged = _write_ged(tmp_path / "small.ged", ["0 @I1@ INDI", "1 NAME A /B/"])
        result = validate_file(ged, mode="full", quiet=True)
        assert result.success is True


class TestEncodingErrors:
    def test_invalid_encoding_reports_error(self):
        result = validate_file(
            FIXTURES / "invalid_encoding.ged",
            mode="full",
            quiet=True,
        )
        assert result.success is False
        decode_failures = [
            i for i in result.issues if i.code == ErrorCode.E008_DECODE_FAILURE
        ]
        assert len(decode_failures) == 1
        assert "0xff" in decode_failures[0].message
