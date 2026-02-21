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

        # Mark connections
        validator.collect_indi_family_link("@I1@", "@F1@")
        validator.collect_fam_member("@F1@", "@I1@")

        issues = validator.validate()
        assert len(issues) == 0

    def test_unresolved_xref(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_usage("@F99@", 5, "FAMC in @I1@")
        # Connect the INDI so we don't get isolated warning
        validator.collect_indi_family_link("@I1@", "@F1@")
        validator.collect_fam_member("@F1@", "@I1@")

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

    def test_connected_individual_not_isolated(self):
        validator = ReferenceValidator()
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_indi_family_link("@I1@", "@F1@")

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

    def test_family_with_members_not_empty(self):
        validator = ReferenceValidator()
        validator.collect_definition("@F1@", "FAM", 10)
        validator.collect_definition("@I1@", "INDI", 1)
        validator.collect_fam_member("@F1@", "@I1@")

        issues = validator.validate()
        empty = [i for i in issues if i.code == ErrorCode.W015_EMPTY_FAM]
        assert len(empty) == 0
