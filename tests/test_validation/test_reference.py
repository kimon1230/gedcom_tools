from gedcom_tools.validation.issues import ErrorCode
from gedcom_tools.validation.reference import ReferenceValidator


class TestReferenceValidator:
    def test_no_issues_for_valid_refs(self):
        validator = ReferenceValidator()

        # Define records
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)

        # Use them properly
        validator.collect_usage("@I1@", 11, "HUSB in @F1@")
        validator.collect_usage("@F1@", 2, "FAMS in @I1@")

        # Mark connections (role-aware)
        validator.collect_indi_as_spouse("@I1@", "@F1@")
        validator.collect_fam_spouse("@F1@", "@I1@")

        issues = validator.validate()
        assert len(issues) == 0

    def test_unresolved_xref(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_usage("@F99@", 5, "FAMC in @I1@")
        # Connect the INDI so we don't get isolated warning
        validator.collect_indi_as_spouse("@I1@", "@F1@")
        validator.collect_fam_spouse("@F1@", "@I1@")

        issues = validator.validate()
        unresolved = [i for i in issues if i.code == ErrorCode.E001_UNRESOLVED_XREF]
        assert len(unresolved) == 1
        assert "@F99@" in unresolved[0].message

    def test_duplicate_xref(self):
        validator = ReferenceValidator()
        issue1 = validator.collect_definition("@I1@", "INDI", 1)
        issue2 = validator.collect_definition("@I1@", "INDI", 10)

        assert issue1 is None
        assert issue2 is not None
        assert issue2.code == ErrorCode.E002_DUPLICATE_XREF

    def test_orphaned_note(self):
        validator = ReferenceValidator()
        validator.collect_definition("@N1@", "NOTE", 5)

        issues = validator.validate()
        orphan_issues = [i for i in issues if i.code == ErrorCode.W010_ORPHANED_NOTE]
        assert len(orphan_issues) == 1

    def test_orphaned_sour(self):
        validator = ReferenceValidator()
        validator.collect_definition("@S1@", "SOUR", 5)

        issues = validator.validate()
        orphan_issues = [i for i in issues if i.code == ErrorCode.W012_ORPHANED_SOUR]
        assert len(orphan_issues) == 1

    def test_orphaned_repo(self):
        validator = ReferenceValidator()
        validator.collect_definition("@R1@", "REPO", 5)

        issues = validator.validate()
        orphan_issues = [i for i in issues if i.code == ErrorCode.W013_ORPHANED_REPO]
        assert len(orphan_issues) == 1

    def test_orphaned_obje(self):
        validator = ReferenceValidator()
        validator.collect_definition("@O1@", "OBJE", 5)

        issues = validator.validate()
        orphan_issues = [i for i in issues if i.code == ErrorCode.W011_ORPHANED_OBJE]
        assert len(orphan_issues) == 1

    def test_used_source_not_orphaned(self):
        validator = ReferenceValidator()
        validator.collect_definition("@S1@", "SOUR", 5)
        validator.collect_usage("@S1@", 10, "SOUR ref")

        issues = validator.validate()
        orphan_issues = [i for i in issues if i.code == ErrorCode.W012_ORPHANED_SOUR]
        assert len(orphan_issues) == 0

    def test_isolated_individual(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        # No family links

        issues = validator.validate()
        isolated = [i for i in issues if i.code == ErrorCode.W014_ISOLATED_INDI]
        assert len(isolated) == 1

    def test_connected_individual_via_child_not_isolated(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_indi_as_child("@I1@", "@F1@")

        issues = validator.validate()
        isolated = [i for i in issues if i.code == ErrorCode.W014_ISOLATED_INDI]
        assert len(isolated) == 0

    def test_connected_individual_via_spouse_not_isolated(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_indi_as_spouse("@I1@", "@F1@")

        issues = validator.validate()
        isolated = [i for i in issues if i.code == ErrorCode.W014_ISOLATED_INDI]
        assert len(isolated) == 0

    def test_empty_family(self):
        validator = ReferenceValidator()
        validator.collect_definition("@F1@", "FAM", 10)
        # No members

        issues = validator.validate()
        empty = [i for i in issues if i.code == ErrorCode.W015_EMPTY_FAM]
        assert len(empty) == 1

    def test_family_with_child_not_empty(self):
        validator = ReferenceValidator()
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_fam_child("@F1@", "@I1@")

        issues = validator.validate()
        empty = [i for i in issues if i.code == ErrorCode.W015_EMPTY_FAM]
        assert len(empty) == 0

    def test_family_with_spouse_not_empty(self):
        validator = ReferenceValidator()
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_fam_spouse("@F1@", "@I1@")

        issues = validator.validate()
        empty = [i for i in issues if i.code == ErrorCode.W015_EMPTY_FAM]
        assert len(empty) == 0


class TestRoleAwareDicts:
    def test_collect_indi_as_child_stores_correctly(self):
        validator = ReferenceValidator()
        validator.collect_indi_as_child("@I1@", "@F1@")
        validator.collect_indi_as_child("@I1@", "@F2@")
        assert validator.indi_as_child["@I1@"] == {"@F1@", "@F2@"}

    def test_collect_indi_as_spouse_stores_correctly(self):
        validator = ReferenceValidator()
        validator.collect_indi_as_spouse("@I1@", "@F1@")
        assert validator.indi_as_spouse["@I1@"] == {"@F1@"}

    def test_collect_fam_child_stores_correctly(self):
        validator = ReferenceValidator()
        validator.collect_fam_child("@F1@", "@I1@")
        validator.collect_fam_child("@F1@", "@I2@")
        assert validator.fam_children["@F1@"] == {"@I1@", "@I2@"}

    def test_collect_fam_spouse_stores_correctly(self):
        validator = ReferenceValidator()
        validator.collect_fam_spouse("@F1@", "@I1@")
        validator.collect_fam_spouse("@F1@", "@I2@")
        assert validator.fam_spouses["@F1@"] == {"@I1@", "@I2@"}

    def test_dicts_start_empty(self):
        validator = ReferenceValidator()
        assert validator.indi_as_child == {}
        assert validator.indi_as_spouse == {}
        assert validator.fam_children == {}
        assert validator.fam_spouses == {}

    def test_setdefault_does_not_create_empty_entries(self):
        validator = ReferenceValidator()
        validator.collect_indi_as_child("@I1@", "@F1@")
        # Only @I1@ should exist, not any other keys
        assert len(validator.indi_as_child) == 1


class TestAsymmetricLinks:
    def test_fam_chil_without_indi_famc_w016(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        # FAM lists CHIL but INDI has no FAMC
        validator.collect_fam_child("@F1@", "@I1@")

        issues = validator.validate()
        w016 = [i for i in issues if i.code == ErrorCode.W016_ASYMMETRIC_CHILD_LINK]
        assert len(w016) == 1
        assert "@I1@" in w016[0].message
        assert "@F1@" in w016[0].message

    def test_indi_famc_without_fam_chil_w016(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        # INDI references FAMC but FAM doesn't list as CHIL
        validator.collect_indi_as_child("@I1@", "@F1@")

        issues = validator.validate()
        w016 = [i for i in issues if i.code == ErrorCode.W016_ASYMMETRIC_CHILD_LINK]
        assert len(w016) == 1
        assert "@I1@" in w016[0].message

    def test_fam_spouse_without_indi_fams_w017(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        # FAM lists HUSB/WIFE but INDI has no FAMS
        validator.collect_fam_spouse("@F1@", "@I1@")

        issues = validator.validate()
        w017 = [i for i in issues if i.code == ErrorCode.W017_ASYMMETRIC_SPOUSE_LINK]
        assert len(w017) == 1
        assert "@I1@" in w017[0].message

    def test_indi_fams_without_fam_spouse_w017(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        # INDI references FAMS but FAM doesn't list as HUSB/WIFE
        validator.collect_indi_as_spouse("@I1@", "@F1@")

        issues = validator.validate()
        w017 = [i for i in issues if i.code == ErrorCode.W017_ASYMMETRIC_SPOUSE_LINK]
        assert len(w017) == 1
        assert "@I1@" in w017[0].message

    def test_both_sides_present_no_warning(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        # Bidirectional child link
        validator.collect_fam_child("@F1@", "@I1@")
        validator.collect_indi_as_child("@I1@", "@F1@")

        issues = validator.validate()
        w016 = [i for i in issues if i.code == ErrorCode.W016_ASYMMETRIC_CHILD_LINK]
        w017 = [i for i in issues if i.code == ErrorCode.W017_ASYMMETRIC_SPOUSE_LINK]
        assert len(w016) == 0
        assert len(w017) == 0

    def test_undefined_xref_no_asymmetric_warning(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        # @F99@ not defined — E001 covers this, not W016
        validator.collect_indi_as_child("@I1@", "@F99@")

        issues = validator.validate()
        w016 = [i for i in issues if i.code == ErrorCode.W016_ASYMMETRIC_CHILD_LINK]
        assert len(w016) == 0
