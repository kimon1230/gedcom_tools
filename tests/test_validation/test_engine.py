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
            "0 TRLR\n"
        )
        result = validate_file(ged, mode="full", quiet=True)
        assert result.success is True
        assert result.encoding_info is not None
        assert result.encoding_info.encoding == "ANSEL"
        error_values = {i.code.value for i in result.issues}
        assert "E009" not in error_values

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
        """royal92.ged (ANSEL file) should not produce E009."""
        royal92 = FIXTURES / "royal92.ged"
        result = validate_file(royal92, mode="full", quiet=True)

        error_values = {i.code.value for i in result.issues}
        assert "E009" not in error_values
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
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
            "0 TRLR\n"
        )
        result = validate_file(ged, mode="full", quiet=True)
        w029 = [i for i in result.issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 1
        assert "HUSB" in w029[0].message
        assert "SEX=F" in w029[0].message


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
