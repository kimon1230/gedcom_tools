from gedcom_tools.validation.issues import (
    ErrorCode,
    FamilyInfo,
    IndividualInfo,
)
from gedcom_tools.validation.semantic import SemanticValidator


class TestSemanticValidator:
    def test_no_issues_for_valid_data(self):
        validator = SemanticValidator()

        # Normal family
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1950,
                death_year=2020,
                famc_xrefs=[],
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                birth_year=1955,
                death_year=2021,
                famc_xrefs=[],
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I3@",
                line=20,
                birth_year=1980,
                famc_xrefs=["@F1@"],
                fams_xrefs=[],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=30,
                husb_xref="@I1@",
                wife_xref="@I2@",
                chil_xrefs=["@I3@"],
                marriage_year=1975,
            )
        )

        issues = validator.validate()
        assert len(issues) == 0

    def test_death_before_birth(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1950,
                death_year=1940,
            )
        )

        issues = validator.validate()
        death_issues = [
            i for i in issues if i.code == ErrorCode.E011_DEATH_BEFORE_BIRTH
        ]
        assert len(death_issues) == 1
        assert "1940" in death_issues[0].message
        assert "1950" in death_issues[0].message

    def test_birth_before_parent(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1950,
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                birth_year=1940,  # Born before parent
                famc_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                husb_xref="@I1@",
                chil_xrefs=["@I2@"],
            )
        )

        issues = validator.validate()
        birth_issues = [
            i for i in issues if i.code == ErrorCode.E012_BIRTH_BEFORE_PARENT
        ]
        assert len(birth_issues) == 1

    def test_ancestry_cycle(self):
        validator = SemanticValidator()

        # I1 is parent of I2, I2 is parent of I1
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                famc_xrefs=["@F1@"],
                fams_xrefs=["@F2@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                famc_xrefs=["@F2@"],
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                husb_xref="@I2@",
                chil_xrefs=["@I1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F2@",
                line=30,
                husb_xref="@I1@",
                chil_xrefs=["@I2@"],
            )
        )

        issues = validator.validate()
        cycle_issues = [i for i in issues if i.code == ErrorCode.E010_ANCESTRY_CYCLE]
        assert len(cycle_issues) >= 1

    def test_parent_too_young(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1990,
                sex="M",
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                birth_year=2000,  # Parent was 10
                famc_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                husb_xref="@I1@",
                chil_xrefs=["@I2@"],
            )
        )

        issues = validator.validate()
        age_issues = [i for i in issues if i.code == ErrorCode.W020_PARENT_TOO_YOUNG]
        assert len(age_issues) == 1

    def test_mother_too_old(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1900,
                sex="F",
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                birth_year=1985,  # Mother was 85
                famc_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                wife_xref="@I1@",
                chil_xrefs=["@I2@"],
            )
        )

        issues = validator.validate()
        age_issues = [i for i in issues if i.code == ErrorCode.W021_MOTHER_TOO_OLD]
        assert len(age_issues) == 1

    def test_father_too_old(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1900,
                sex="M",
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                birth_year=1990,  # Father was 90
                famc_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                husb_xref="@I1@",
                chil_xrefs=["@I2@"],
            )
        )

        issues = validator.validate()
        age_issues = [i for i in issues if i.code == ErrorCode.W022_FATHER_TOO_OLD]
        assert len(age_issues) == 1

    def test_age_at_death_implausible(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1800,
                death_year=1950,  # 150 years old
            )
        )

        issues = validator.validate()
        age_issues = [
            i for i in issues if i.code == ErrorCode.W023_AGE_AT_DEATH_IMPLAUSIBLE
        ]
        assert len(age_issues) == 1

    def test_marriage_before_birth(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1950,
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                husb_xref="@I1@",
                marriage_year=1940,  # Before birth
            )
        )

        issues = validator.validate()
        marriage_issues = [
            i for i in issues if i.code == ErrorCode.W024_MARRIAGE_BEFORE_BIRTH
        ]
        assert len(marriage_issues) == 1

    def test_child_before_marriage(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=1950,
                fams_xrefs=["@F1@"],
            )
        )
        validator.collect_individual(
            IndividualInfo(
                xref="@I2@",
                line=10,
                birth_year=1970,  # Before marriage
                famc_xrefs=["@F1@"],
            )
        )
        validator.collect_family(
            FamilyInfo(
                xref="@F1@",
                line=20,
                husb_xref="@I1@",
                chil_xrefs=["@I2@"],
                marriage_year=1980,
            )
        )

        issues = validator.validate()
        child_issues = [
            i for i in issues if i.code == ErrorCode.W025_CHILD_BEFORE_MARRIAGE
        ]
        assert len(child_issues) == 1

    def test_missing_dates_no_issues(self):
        """Ensure missing dates don't cause false positives."""
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(
                xref="@I1@",
                line=1,
                birth_year=None,
                death_year=None,
            )
        )

        issues = validator.validate()
        assert len(issues) == 0


class TestAncestryEdgeCases:
    def test_diamond_ancestry_no_false_positive(self):
        """Diamond pattern (shared ancestor) should not be flagged as cycle."""
        individuals = {
            "@I1@": IndividualInfo(xref="@I1@", line=1, famc_xrefs=["@F1@"]),
            "@I2@": IndividualInfo(xref="@I2@", line=2, famc_xrefs=["@F1@"]),
            "@I3@": IndividualInfo(xref="@I3@", line=3),
        }
        families = {
            "@F1@": FamilyInfo(
                xref="@F1@", line=10, husb_xref="@I3@", chil_xrefs=["@I1@", "@I2@"]
            ),
        }
        validator = SemanticValidator(individuals=individuals, families=families)
        issues = validator.validate()
        cycle_issues = [i for i in issues if i.code == ErrorCode.E010_ANCESTRY_CYCLE]
        assert len(cycle_issues) == 0, "Diamond ancestry should not be a cycle"

    def test_multi_generation_cycle_detected(self):
        """A -> B -> C -> A cycle should be detected."""
        individuals = {
            "@I1@": IndividualInfo(xref="@I1@", line=1, famc_xrefs=["@F1@"]),
            "@I2@": IndividualInfo(xref="@I2@", line=2, famc_xrefs=["@F2@"]),
            "@I3@": IndividualInfo(xref="@I3@", line=3, famc_xrefs=["@F3@"]),
        }
        families = {
            "@F1@": FamilyInfo(
                xref="@F1@", line=10, husb_xref="@I3@", chil_xrefs=["@I1@"]
            ),
            "@F2@": FamilyInfo(
                xref="@F2@", line=20, husb_xref="@I1@", chil_xrefs=["@I2@"]
            ),
            "@F3@": FamilyInfo(
                xref="@F3@", line=30, husb_xref="@I2@", chil_xrefs=["@I3@"]
            ),
        }
        validator = SemanticValidator(individuals=individuals, families=families)
        issues = validator.validate()
        cycle_issues = [i for i in issues if i.code == ErrorCode.E010_ANCESTRY_CYCLE]
        assert len(cycle_issues) >= 1, "Multi-generation cycle should be detected"


class TestSiblingSpacing:
    def test_siblings_5_months_apart_w026(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1980, birth_month=3)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=8)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, chil_xrefs=["@I1@", "@I2@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 1
        assert "5 months" in w026[0].message

    def test_siblings_9_months_apart_no_warning(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1980, birth_month=1)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=10)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, chil_xrefs=["@I1@", "@I2@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 0

    def test_twins_no_warning(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1980, birth_month=6)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=6)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, chil_xrefs=["@I1@", "@I2@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 0

    def test_year_only_dates_no_warning(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1980, birth_month=None)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=None)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, chil_xrefs=["@I1@", "@I2@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 0

    def test_reverse_chronological_order_still_fires(self):
        validator = SemanticValidator()
        # I2 is older but listed second in GEDCOM
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1980, birth_month=8)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=3)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, chil_xrefs=["@I1@", "@I2@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 1

    def test_three_siblings_one_pair_violating(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1978, birth_month=1)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=3)
        )
        # I3 is only 4 months after I2
        validator.collect_individual(
            IndividualInfo(xref="@I3@", line=20, birth_year=1980, birth_month=7)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=30, chil_xrefs=["@I1@", "@I2@", "@I3@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 1

    def test_cross_year_boundary(self):
        validator = SemanticValidator()
        validator.collect_individual(
            IndividualInfo(xref="@I1@", line=1, birth_year=1979, birth_month=10)
        )
        validator.collect_individual(
            IndividualInfo(xref="@I2@", line=10, birth_year=1980, birth_month=3)
        )
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, chil_xrefs=["@I1@", "@I2@"])
        )

        issues = validator.validate()
        w026 = [i for i in issues if i.code == ErrorCode.W026_SIBLING_TOO_CLOSE]
        assert len(w026) == 1
        assert "5 months" in w026[0].message


class TestSexRoleMismatch:
    def test_husb_with_sex_f_w029(self):
        validator = SemanticValidator()
        validator.collect_individual(IndividualInfo(xref="@I1@", line=1, sex="F"))
        validator.collect_family(FamilyInfo(xref="@F1@", line=10, husb_xref="@I1@"))

        issues = validator.validate()
        w029 = [i for i in issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 1
        assert "HUSB" in w029[0].message
        assert "SEX=F" in w029[0].message

    def test_wife_with_sex_m_w029(self):
        validator = SemanticValidator()
        validator.collect_individual(IndividualInfo(xref="@I1@", line=1, sex="M"))
        validator.collect_family(FamilyInfo(xref="@F1@", line=10, wife_xref="@I1@"))

        issues = validator.validate()
        w029 = [i for i in issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 1
        assert "WIFE" in w029[0].message
        assert "SEX=M" in w029[0].message

    def test_both_mismatched_in_same_fam(self):
        validator = SemanticValidator()
        validator.collect_individual(IndividualInfo(xref="@I1@", line=1, sex="F"))
        validator.collect_individual(IndividualInfo(xref="@I2@", line=10, sex="M"))
        validator.collect_family(
            FamilyInfo(xref="@F1@", line=20, husb_xref="@I1@", wife_xref="@I2@")
        )

        issues = validator.validate()
        w029 = [i for i in issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 2

    def test_husb_with_sex_m_no_warning(self):
        validator = SemanticValidator()
        validator.collect_individual(IndividualInfo(xref="@I1@", line=1, sex="M"))
        validator.collect_family(FamilyInfo(xref="@F1@", line=10, husb_xref="@I1@"))

        issues = validator.validate()
        w029 = [i for i in issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 0

    def test_sex_u_no_warning(self):
        validator = SemanticValidator()
        validator.collect_individual(IndividualInfo(xref="@I1@", line=1, sex="U"))
        validator.collect_family(FamilyInfo(xref="@F1@", line=10, husb_xref="@I1@"))

        issues = validator.validate()
        w029 = [i for i in issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 0

    def test_missing_sex_no_warning(self):
        validator = SemanticValidator()
        validator.collect_individual(IndividualInfo(xref="@I1@", line=1, sex=None))
        validator.collect_family(FamilyInfo(xref="@F1@", line=10, husb_xref="@I1@"))

        issues = validator.validate()
        w029 = [i for i in issues if i.code == ErrorCode.W029_SEX_ROLE_MISMATCH]
        assert len(w029) == 0
