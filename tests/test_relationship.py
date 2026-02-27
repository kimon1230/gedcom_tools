"""Tests for the relationship command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from gedcom_tools.cli import main
from gedcom_tools.commands.relationship import _validate_xref
from gedcom_tools.commands.relationship.algorithm import (
    _sort_key,
    find_relationship,
    load_individuals,
)
from gedcom_tools.commands.relationship.classifier import (
    _ordinal,
    _removed_label,
    build_description,
    classify_relationship,
)
from gedcom_tools.commands.relationship.formatter import format_json, format_text
from gedcom_tools.commands.relationship.models import (
    RelationshipPath,
    RelationshipResult,
    RelIndividual,
)
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.graph import build_parent_child_graph
from gedcom_tools.progress import Colors


def _write_ged(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.ged"
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n")
    return p


# -- GEDCOM test data --

_SIMPLE_FAMILY = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n"
    "1 BIRT\n2 DATE 1 JAN 1850\n"
    "1 DEAT\n2 DATE 15 MAR 1920\n"
    "0 @I2@ INDI\n1 NAME Mary /Jones/\n1 SEX F\n"
    "0 @I3@ INDI\n1 NAME James /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
)

_THREE_GEN = (
    "0 @I1@ INDI\n1 NAME Grandpa /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Grandma /Jones/\n1 SEX F\n"
    "0 @I3@ INDI\n1 NAME Dad /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Uncle /Smith/\n1 SEX M\n"
    "0 @I5@ INDI\n1 NAME Mom /Brown/\n1 SEX F\n"
    "0 @I6@ INDI\n1 NAME Kid /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
    "1 CHIL @I3@\n1 CHIL @I4@\n"
    "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I5@\n1 CHIL @I6@\n"
)

_COUSIN_TREE = (
    "0 @I1@ INDI\n1 NAME Grandpa /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Grandma /Jones/\n1 SEX F\n"
    "0 @I3@ INDI\n1 NAME Dad /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Uncle /Smith/\n1 SEX M\n"
    "0 @I5@ INDI\n1 NAME Mom /Brown/\n1 SEX F\n"
    "0 @I6@ INDI\n1 NAME Aunt /White/\n1 SEX F\n"
    "0 @I7@ INDI\n1 NAME Cousin1 /Smith/\n1 SEX M\n"
    "0 @I8@ INDI\n1 NAME Cousin2 /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
    "1 CHIL @I3@\n1 CHIL @I4@\n"
    "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I5@\n1 CHIL @I7@\n"
    "0 @F3@ FAM\n1 HUSB @I4@\n1 WIFE @I6@\n1 CHIL @I8@\n"
)

_HALF_SIBLINGS = (
    "0 @I1@ INDI\n1 NAME Dad /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Mom1 /Jones/\n1 SEX F\n"
    "0 @I3@ INDI\n1 NAME Kid1 /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Mom2 /Brown/\n1 SEX F\n"
    "0 @I5@ INDI\n1 NAME Kid2 /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
    "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I4@\n1 CHIL @I5@\n"
)

_FULL_SIBLINGS = (
    "0 @I1@ INDI\n1 NAME Dad /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Mom /Jones/\n1 SEX F\n"
    "0 @I3@ INDI\n1 NAME Kid1 /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Kid2 /Smith/\n1 SEX F\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
    "1 CHIL @I3@\n1 CHIL @I4@\n"
)

# Single grandparent → half uncle, half cousin, direct line
_HALF_GP = (
    "0 @I1@ INDI\n1 NAME GP /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Dad /Smith/\n1 SEX M\n"
    "0 @I3@ INDI\n1 NAME Uncle /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Kid /Smith/\n1 SEX M\n"
    "0 @I5@ INDI\n1 NAME Cousin /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n1 CHIL @I3@\n"
    "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I4@\n"
    "0 @F3@ FAM\n1 HUSB @I3@\n1 CHIL @I5@\n"
)

_DISCONNECTED = (
    "0 @I1@ INDI\n1 NAME Alice /Smith/\n1 SEX F\n"
    "0 @I2@ INDI\n1 NAME Bob /Jones/\n1 SEX M\n"
)

_SPARSE = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n1 SEX M\n"
    "1 BIRT\n2 DATE 1 JAN 1850\n"
    "1 DEAT\n2 DATE 15 MAR 1920\n"
    "0 @I2@ INDI\n"
    "0 @I3@ INDI\n1 NAME Jane /Doe/\n"
    "0 @I4@ INDI\n1 NAME Bob /Brown/\n1 SEX M\n"
)

# Pedigree collapse: GG reachable at depth 2 (via P2) and 3 (via P1→G1)
_PEDIGREE_COLLAPSE = (
    "0 @I1@ INDI\n1 NAME GG /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME G1 /Smith/\n1 SEX M\n"
    "0 @I3@ INDI\n1 NAME P1 /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME P2 /Smith/\n1 SEX F\n"
    "0 @I5@ INDI\n1 NAME Child /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n1 CHIL @I4@\n"
    "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I3@\n"
    "0 @F3@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n1 CHIL @I5@\n"
)

# Directional merge: X at (3,2) and Y at (2,3) → both "1st cousin once removed"
# X → A, B;  Y → D, E2;  A → C;  E2 → E;  C+D → P;  B+E → T
_DIRECTIONAL = (
    "0 @I1@ INDI\n1 NAME X /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Y /Jones/\n1 SEX M\n"
    "0 @I3@ INDI\n1 NAME A /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME B /Smith/\n1 SEX M\n"
    "0 @I5@ INDI\n1 NAME C /Smith/\n1 SEX M\n"
    "0 @I6@ INDI\n1 NAME D /Jones/\n1 SEX F\n"
    "0 @I7@ INDI\n1 NAME E2 /Jones/\n1 SEX M\n"
    "0 @I8@ INDI\n1 NAME E /Jones/\n1 SEX F\n"
    "0 @I9@ INDI\n1 NAME P /Smith/\n1 SEX M\n"
    "0 @I10@ INDI\n1 NAME T /Jones/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I3@\n1 CHIL @I4@\n"
    "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I6@\n1 CHIL @I7@\n"
    "0 @F3@ FAM\n1 HUSB @I3@\n1 CHIL @I5@\n"
    "0 @F4@ FAM\n1 HUSB @I7@\n1 CHIL @I8@\n"
    "0 @F5@ FAM\n1 HUSB @I5@\n1 WIFE @I6@\n1 CHIL @I9@\n"
    "0 @F6@ FAM\n1 HUSB @I4@\n1 WIFE @I8@\n1 CHIL @I10@\n"
)

# Anti-dedup: like _DIRECTIONAL but X+XS are a couple → (3,2) full, (2,3) half
_ANTI_DEDUP = (
    "0 @I1@ INDI\n1 NAME X /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME Y /Jones/\n1 SEX M\n"
    "0 @I3@ INDI\n1 NAME A /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME B /Smith/\n1 SEX M\n"
    "0 @I5@ INDI\n1 NAME C /Smith/\n1 SEX M\n"
    "0 @I6@ INDI\n1 NAME D /Jones/\n1 SEX F\n"
    "0 @I7@ INDI\n1 NAME E2 /Jones/\n1 SEX M\n"
    "0 @I8@ INDI\n1 NAME E /Jones/\n1 SEX F\n"
    "0 @I9@ INDI\n1 NAME P /Smith/\n1 SEX M\n"
    "0 @I10@ INDI\n1 NAME T /Jones/\n1 SEX M\n"
    "0 @I11@ INDI\n1 NAME XS /White/\n1 SEX F\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I11@\n"
    "1 CHIL @I3@\n1 CHIL @I4@\n"
    "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I6@\n1 CHIL @I7@\n"
    "0 @F3@ FAM\n1 HUSB @I3@\n1 CHIL @I5@\n"
    "0 @F4@ FAM\n1 HUSB @I7@\n1 CHIL @I8@\n"
    "0 @F5@ FAM\n1 HUSB @I5@\n1 WIFE @I6@\n1 CHIL @I9@\n"
    "0 @F6@ FAM\n1 HUSB @I4@\n1 WIFE @I8@\n1 CHIL @I10@\n"
)

# Two distinct relationship types: A(@I7@) and B(@I8@) share
# X(@I3@) at (3,2) and GGP(@I1@) at (3,3)
_MULTI_TYPE = (
    "0 @I1@ INDI\n1 NAME GGP /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME GP /Smith/\n1 SEX M\n"
    "0 @I3@ INDI\n1 NAME X /Smith/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Z /Smith/\n1 SEX F\n"
    "0 @I5@ INDI\n1 NAME Y /Smith/\n1 SEX M\n"
    "0 @I6@ INDI\n1 NAME P /Smith/\n1 SEX M\n"
    "0 @I7@ INDI\n1 NAME A /Smith/\n1 SEX M\n"
    "0 @I8@ INDI\n1 NAME B /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n1 CHIL @I3@\n"
    "0 @F2@ FAM\n1 HUSB @I3@\n1 CHIL @I4@\n1 CHIL @I5@\n"
    "0 @F3@ FAM\n1 HUSB @I2@\n1 WIFE @I4@\n1 CHIL @I6@\n"
    "0 @F4@ FAM\n1 HUSB @I6@\n1 CHIL @I7@\n"
    "0 @F5@ FAM\n1 HUSB @I5@\n1 CHIL @I8@\n"
)

# Mixed aggregation: GP1+GM1 couple + GP2 alone → all at (2,1)
_MIXED_AGG = (
    "0 @I1@ INDI\n1 NAME GP1 /Smith/\n1 SEX M\n"
    "0 @I2@ INDI\n1 NAME GM1 /Jones/\n1 SEX F\n"
    "0 @I3@ INDI\n1 NAME GP2 /Brown/\n1 SEX M\n"
    "0 @I4@ INDI\n1 NAME Dad /Smith/\n1 SEX M\n"
    "0 @I5@ INDI\n1 NAME Uncle /Smith/\n1 SEX M\n"
    "0 @I6@ INDI\n1 NAME Kid /Smith/\n1 SEX M\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
    "1 CHIL @I4@\n1 CHIL @I5@\n"
    "0 @F2@ FAM\n1 HUSB @I3@\n1 CHIL @I4@\n1 CHIL @I5@\n"
    "0 @F3@ FAM\n1 HUSB @I4@\n1 CHIL @I6@\n"
)


# =====================================================================
# Batch 2 tests: classifier pure helpers
# =====================================================================


class TestOrdinal:
    def test_first(self):
        assert _ordinal(1) == "1st"

    def test_second(self):
        assert _ordinal(2) == "2nd"

    def test_third(self):
        assert _ordinal(3) == "3rd"

    def test_fourth(self):
        assert _ordinal(4) == "4th"

    def test_eleventh(self):
        assert _ordinal(11) == "11th"

    def test_twelfth(self):
        assert _ordinal(12) == "12th"

    def test_thirteenth(self):
        assert _ordinal(13) == "13th"

    def test_twenty_first(self):
        assert _ordinal(21) == "21st"

    def test_twenty_second(self):
        assert _ordinal(22) == "22nd"

    def test_twenty_third(self):
        assert _ordinal(23) == "23rd"

    def test_hundredth(self):
        assert _ordinal(100) == "100th"

    def test_hundred_and_first(self):
        assert _ordinal(101) == "101st"

    def test_hundred_and_eleventh(self):
        assert _ordinal(111) == "111th"

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="n >= 1"):
            _ordinal(0)


class TestRemovedLabel:
    def test_zero(self):
        assert _removed_label(0) == ""

    def test_once(self):
        assert _removed_label(1) == "once removed"

    def test_twice(self):
        assert _removed_label(2) == "twice removed"

    def test_three(self):
        assert _removed_label(3) == "3 times removed"

    def test_five(self):
        assert _removed_label(5) == "5 times removed"

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="n >= 0"):
            _removed_label(-1)


class TestClassifyRelationship:
    def test_same_individual(self):
        assert classify_relationship(0, 0, "M") == "same individual"

    def test_father(self):
        assert classify_relationship(1, 0, "M") == "father"

    def test_mother(self):
        assert classify_relationship(1, 0, "F") == "mother"

    def test_parent_unknown(self):
        assert classify_relationship(1, 0, "") == "parent"

    def test_grandfather(self):
        assert classify_relationship(2, 0, "M") == "grandfather"

    def test_grandmother(self):
        assert classify_relationship(2, 0, "F") == "grandmother"

    def test_great_grandfather(self):
        assert classify_relationship(3, 0, "M") == "great-grandfather"

    def test_2x_great_grandfather(self):
        assert classify_relationship(4, 0, "M") == "2x great-grandfather"

    def test_son(self):
        assert classify_relationship(0, 1, "M") == "son"

    def test_daughter(self):
        assert classify_relationship(0, 1, "F") == "daughter"

    def test_child_unknown(self):
        assert classify_relationship(0, 1, "") == "child"

    def test_grandson(self):
        assert classify_relationship(0, 2, "M") == "grandson"

    def test_granddaughter(self):
        assert classify_relationship(0, 2, "F") == "granddaughter"

    def test_great_grandson(self):
        assert classify_relationship(0, 3, "M") == "great-grandson"

    def test_2x_great_grandson(self):
        assert classify_relationship(0, 4, "M") == "2x great-grandson"

    def test_brother(self):
        assert classify_relationship(1, 1, "M") == "brother"

    def test_sister(self):
        assert classify_relationship(1, 1, "F") == "sister"

    def test_sibling_unknown(self):
        assert classify_relationship(1, 1, "") == "sibling"

    def test_uncle(self):
        assert classify_relationship(2, 1, "M") == "uncle"

    def test_aunt(self):
        assert classify_relationship(2, 1, "F") == "aunt"

    def test_great_uncle(self):
        assert classify_relationship(3, 1, "M") == "great-uncle"

    def test_great_aunt(self):
        assert classify_relationship(3, 1, "F") == "great-aunt"

    def test_2x_great_uncle(self):
        assert classify_relationship(4, 1, "M") == "2x great-uncle"

    def test_nephew(self):
        assert classify_relationship(1, 2, "M") == "nephew"

    def test_niece(self):
        assert classify_relationship(1, 2, "F") == "niece"

    def test_great_nephew(self):
        assert classify_relationship(1, 3, "M") == "great-nephew"

    def test_great_niece(self):
        assert classify_relationship(1, 3, "F") == "great-niece"

    def test_2x_great_nephew(self):
        assert classify_relationship(1, 4, "M") == "2x great-nephew"

    def test_first_cousin(self):
        assert classify_relationship(2, 2, "M") == "1st cousin"

    def test_first_cousin_once_removed(self):
        assert classify_relationship(3, 2, "M") == "1st cousin once removed"

    def test_second_cousin(self):
        assert classify_relationship(3, 3, "M") == "2nd cousin"

    def test_first_cousin_twice_removed(self):
        assert classify_relationship(4, 2, "M") == "1st cousin twice removed"

    def test_second_cousin_twice_removed(self):
        assert classify_relationship(5, 3, "M") == "2nd cousin twice removed"

    def test_sibling_not_uncle(self):
        """(1,1) must dispatch to sibling, not uncle/aunt."""
        result = classify_relationship(1, 1, "M")
        assert result == "brother"
        assert "uncle" not in result

    def test_uncle_not_cousin(self):
        """(2,1) must dispatch to uncle, not cousin."""
        result = classify_relationship(2, 1, "M")
        assert result == "uncle"
        assert "cousin" not in result


class TestBuildDescription:
    def test_cousin_no_removal(self):
        result = build_description(
            "Alice", "Bob", "1st cousin", is_half=False, show_half=False
        )
        assert result == "Alice is a 1st cousin of Bob."

    def test_cousin_with_removal(self):
        result = build_description(
            "Alice",
            "Bob",
            "2nd cousin once removed",
            is_half=False,
            show_half=False,
        )
        assert result == "Alice is a 2nd cousin once removed of Bob."

    def test_half_cousin(self):
        result = build_description(
            "Alice", "Bob", "1st cousin", is_half=True, show_half=True
        )
        assert result == "Alice is a half-1st cousin of Bob."

    def test_half_brother(self):
        result = build_description(
            "Alice", "Bob", "brother", is_half=True, show_half=True
        )
        assert result == "Alice is a half-brother of Bob."

    def test_same_individual(self):
        result = build_description(
            "Alice",
            "Bob",
            "same individual",
            is_half=False,
            show_half=False,
        )
        assert result == "Alice and Bob are the same individual."

    def test_uncle_uses_an(self):
        result = build_description(
            "James", "John", "uncle", is_half=False, show_half=False
        )
        assert result == "James is an uncle of John."

    def test_aunt_uses_an(self):
        result = build_description(
            "Mary", "John", "aunt", is_half=False, show_half=False
        )
        assert result == "Mary is an aunt of John."

    def test_brother_uses_a(self):
        result = build_description(
            "James", "John", "brother", is_half=False, show_half=False
        )
        assert result == "James is a brother of John."

    def test_half_uncle_uses_a(self):
        """'half-uncle' starts with 'h', so article is 'a' not 'an'."""
        result = build_description(
            "James", "John", "uncle", is_half=True, show_half=True
        )
        assert result == "James is a half-uncle of John."

    def test_direct_line_uses_the(self):
        result = build_description(
            "James",
            "John",
            "grandfather",
            is_half=False,
            show_half=False,
        )
        assert result == "James is the grandfather of John."

    def test_great_grandfather_uses_the(self):
        result = build_description(
            "James",
            "John",
            "2x great-grandfather",
            is_half=False,
            show_half=False,
        )
        assert result == "James is the 2x great-grandfather of John."

    def test_son_uses_the(self):
        result = build_description(
            "James", "John", "son", is_half=False, show_half=False
        )
        assert result == "James is the son of John."

    def test_half_suppressed_when_show_half_false(self):
        result = build_description(
            "Alice", "Bob", "brother", is_half=True, show_half=False
        )
        assert result == "Alice is a brother of Bob."


# =====================================================================
# Batch 3 tests: algorithm, half-detection, sort, edge cases
# =====================================================================


class TestLoadIndividuals:
    def test_standard_individual(self, tmp_path):
        ged = _write_ged(tmp_path, _SPARSE)
        inds = load_individuals(ged)
        ind = inds["@I1@"]
        assert ind.name == "John Smith"
        assert ind.sex == "M"
        assert ind.birth_year == 1850
        assert ind.death_year == 1920

    def test_no_name(self, tmp_path):
        ged = _write_ged(tmp_path, _SPARSE)
        inds = load_individuals(ged)
        assert inds["@I2@"].name == "[Unknown] (@I2@)"

    def test_no_sex(self, tmp_path):
        ged = _write_ged(tmp_path, _SPARSE)
        inds = load_individuals(ged)
        assert inds["@I3@"].sex == ""

    def test_no_dates(self, tmp_path):
        ged = _write_ged(tmp_path, _SPARSE)
        inds = load_individuals(ged)
        ind = inds["@I4@"]
        assert ind.birth_year is None
        assert ind.death_year is None


class TestFindRelationship:
    def test_parent_child_forward(self, tmp_path):
        """Primary=parent, target=child → son."""
        ged = _write_ged(tmp_path, _SIMPLE_FAMILY)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I1@", "@I3@")
        assert result.related is True
        rel = result.relationships[0]
        assert rel.type == "son"
        assert rel.gen_p == 0
        assert rel.gen_t == 1

    def test_parent_child_reverse(self, tmp_path):
        """Primary=child, target=parent → father."""
        ged = _write_ged(tmp_path, _SIMPLE_FAMILY)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I3@", "@I1@")
        rel = result.relationships[0]
        assert rel.type == "father"
        assert rel.gen_p == 1
        assert rel.gen_t == 0

    def test_grandparent(self, tmp_path):
        ged = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I6@", "@I1@")
        rel = result.relationships[0]
        assert rel.type == "grandfather"
        assert rel.gen_p == 2

    def test_siblings(self, tmp_path):
        ged = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I3@", "@I4@")
        rel = result.relationships[0]
        assert rel.type == "brother"
        assert rel.gen_p == 1
        assert rel.gen_t == 1

    def test_uncle_nephew(self, tmp_path):
        ged = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I6@", "@I4@")
        rel = result.relationships[0]
        assert rel.type == "uncle"
        assert rel.gen_p == 2
        assert rel.gen_t == 1

    def test_cousins(self, tmp_path):
        ged = _write_ged(tmp_path, _COUSIN_TREE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I7@", "@I8@")
        rel = result.relationships[0]
        assert rel.type == "1st cousin"

    def test_pedigree_collapse_min_depth(self, tmp_path):
        """GG reachable at depth 2 (short) and 3 (long) → uses min."""
        ged = _write_ged(tmp_path, _PEDIGREE_COLLAPSE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I5@", "@I1@")
        rel = result.relationships[0]
        assert rel.type == "grandfather"
        assert rel.gen_p == 2

    def test_multi_paths_two_types(self, tmp_path):
        """paths=10 returns two distinct types sorted by path length."""
        ged = _write_ged(tmp_path, _MULTI_TYPE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I7@", "@I8@", paths=10)
        types = [r.type for r in result.relationships]
        assert len(types) == 2
        # Shorter path first: sum 5 before sum 6
        assert "1st cousin once removed" in types
        assert "2nd cousin" in types
        assert types[0] == "1st cousin once removed"

    def test_directional_merge(self, tmp_path):
        """(3,2) and (2,3) both → '1st cousin once removed', merged."""
        ged = _write_ged(tmp_path, _DIRECTIONAL)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I9@", "@I10@", paths=10)
        cousin_paths = [
            r for r in result.relationships if r.type == "1st cousin once removed"
        ]
        assert len(cousin_paths) == 1
        merged = cousin_paths[0]
        # Both X(@I1@) and Y(@I2@) in common ancestors
        assert "@I1@" in merged.common_ancestors
        assert "@I2@" in merged.common_ancestors
        # Smaller gen_p wins tiebreaker (both sum=5)
        assert merged.gen_p == 2
        assert merged.gen_t == 3

    def test_anti_dedup(self, tmp_path):
        """Same type but different is_half → kept separate."""
        ged = _write_ged(tmp_path, _ANTI_DEDUP)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I9@", "@I10@", paths=10)
        cousin_paths = [
            r for r in result.relationships if r.type == "1st cousin once removed"
        ]
        assert len(cousin_paths) == 2
        half_values = {r.is_half for r in cousin_paths}
        assert half_values == {True, False}

    def test_total_paths_set(self, tmp_path):
        """total_paths reflects deduplicated count before paths limit."""
        ged = _write_ged(tmp_path, _MULTI_TYPE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I7@", "@I8@", paths=1)
        assert result.total_paths == 2
        assert len(result.relationships) == 1


class TestSortOrder:
    def test_shorter_path_first(self):
        short = RelationshipPath(type="uncle", gen_p=2, gen_t=1)
        long = RelationshipPath(type="1st cousin", gen_p=2, gen_t=2)
        assert _sort_key(short, {}) < _sort_key(long, {})

    def test_full_blood_before_half(self):
        full = RelationshipPath(type="uncle", gen_p=2, gen_t=1, is_half=False)
        half = RelationshipPath(type="uncle", gen_p=2, gen_t=1, is_half=True)
        assert _sort_key(full, {}) < _sort_key(half, {})

    def test_male_line_before_female_line(self):
        inds = {
            "@I1@": RelIndividual(xref="@I1@", name="M", sex="M"),
            "@I2@": RelIndividual(xref="@I2@", name="F", sex="F"),
        }
        male = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            is_half=True,
            common_ancestors=["@I1@"],
        )
        female = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            is_half=True,
            common_ancestors=["@I2@"],
        )
        assert _sort_key(male, inds) < _sort_key(female, inds)

    def test_unknown_sex_sorts_after_male(self):
        inds = {
            "@I1@": RelIndividual(xref="@I1@", name="M", sex="M"),
            "@I2@": RelIndividual(xref="@I2@", name="U", sex=""),
        }
        male = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            is_half=True,
            common_ancestors=["@I1@"],
        )
        unknown = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            is_half=True,
            common_ancestors=["@I2@"],
        )
        assert _sort_key(male, inds) < _sort_key(unknown, inds)

    def test_paths_1_returns_best(self, tmp_path):
        ged = _write_ged(tmp_path, _MULTI_TYPE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I7@", "@I8@", paths=1)
        assert len(result.relationships) == 1

    def test_paths_exceeding_available(self, tmp_path):
        ged = _write_ged(tmp_path, _MULTI_TYPE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I7@", "@I8@", paths=99)
        assert len(result.relationships) == 2


class TestHalfRelationships:
    def test_half_siblings(self, tmp_path):
        ged = _write_ged(tmp_path, _HALF_SIBLINGS)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I3@", "@I5@")
        assert result.relationships[0].is_half is True

    def test_full_siblings(self, tmp_path):
        ged = _write_ged(tmp_path, _FULL_SIBLINGS)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I3@", "@I4@")
        assert result.relationships[0].is_half is False

    def test_half_uncle(self, tmp_path):
        """Single grandparent → uncle is half."""
        ged = _write_ged(tmp_path, _HALF_GP)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I4@", "@I3@")
        rel = result.relationships[0]
        assert rel.type == "uncle"
        assert rel.is_half is True

    def test_half_cousin(self, tmp_path):
        """Single grandparent → cousins are half."""
        ged = _write_ged(tmp_path, _HALF_GP)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I4@", "@I5@")
        rel = result.relationships[0]
        assert rel.type == "1st cousin"
        assert rel.is_half is True

    def test_full_cousin(self, tmp_path):
        """Grandparent couple → cousins are full."""
        ged = _write_ged(tmp_path, _COUSIN_TREE)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I7@", "@I8@")
        assert result.relationships[0].is_half is False

    def test_direct_line_never_half(self, tmp_path):
        ged = _write_ged(tmp_path, _HALF_GP)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I4@", "@I1@")
        rel = result.relationships[0]
        assert rel.type == "grandfather"
        assert rel.is_half is False

    def test_mixed_paired_unpaired(self, tmp_path):
        """One paired + one unpaired ancestor → full (any-paired rule)."""
        ged = _write_ged(tmp_path, _MIXED_AGG)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I6@", "@I5@")
        rel = result.relationships[0]
        assert rel.type == "uncle"
        assert rel.is_half is False

    def test_remarried_ancestor(self, tmp_path):
        """Remarried ancestor may misclassify due to v1 simplification.

        The spouse-pairing check finds a partner from a different marriage
        in the common set, incorrectly marking as paired. This is a known
        limitation documented in the plan.
        """
        # Just verify the code runs without error on a remarriage tree
        ged_data = (
            "0 @I1@ INDI\n1 NAME GP /Smith/\n1 SEX M\n"
            "0 @I2@ INDI\n1 NAME Wife1 /Jones/\n1 SEX F\n"
            "0 @I3@ INDI\n1 NAME Wife2 /Brown/\n1 SEX F\n"
            "0 @I4@ INDI\n1 NAME Child1 /Smith/\n1 SEX M\n"
            "0 @I5@ INDI\n1 NAME Child2 /Smith/\n1 SEX M\n"
            "0 @I6@ INDI\n1 NAME GC1 /Smith/\n1 SEX M\n"
            "0 @I7@ INDI\n1 NAME GC2 /Smith/\n1 SEX M\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I4@\n"
            "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I3@\n1 CHIL @I5@\n"
            "0 @F3@ FAM\n1 HUSB @I4@\n1 CHIL @I6@\n"
            "0 @F4@ FAM\n1 HUSB @I5@\n1 CHIL @I7@\n"
        )
        ged = _write_ged(tmp_path, ged_data)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I6@", "@I7@")
        assert result.related is True
        assert result.relationships[0].type == "1st cousin"


class TestEdgeCases:
    def test_same_person(self, tmp_path):
        ged = _write_ged(tmp_path, _SIMPLE_FAMILY)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I1@", "@I1@")
        assert result.related is True
        rel = result.relationships[0]
        assert rel.type == "same individual"
        assert rel.gen_p == 0
        assert rel.gen_t == 0
        assert rel.is_half is False
        assert rel.common_ancestors == ["@I1@"]

    def test_same_person_isolated(self, tmp_path):
        ged_data = "0 @I1@ INDI\n1 NAME Solo /Person/\n1 SEX M\n"
        ged = _write_ged(tmp_path, ged_data)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I1@", "@I1@")
        assert result.related is True
        assert result.relationships[0].common_ancestors == ["@I1@"]

    def test_no_relationship(self, tmp_path):
        ged = _write_ged(tmp_path, _DISCONNECTED)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I1@", "@I2@")
        assert result.related is False
        assert result.relationships == []

    def test_generations_truncation(self, tmp_path):
        ged = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        # Grandparent at depth 2 — limit to 1 → not found
        result, trunc = find_relationship(
            graph, inds, "@I6@", "@I1@", max_generations=1
        )
        assert result.related is False
        assert trunc is True
        # Limit to 2 → found
        result2, trunc2 = find_relationship(
            graph, inds, "@I6@", "@I1@", max_generations=2
        )
        assert result2.related is True
        assert result2.relationships[0].type == "grandfather"

    def test_no_sex_gender_neutral(self, tmp_path):
        ged_data = (
            "0 @I1@ INDI\n1 NAME Parent /Smith/\n"
            "0 @I2@ INDI\n1 NAME Child /Smith/\n1 SEX M\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
        )
        ged = _write_ged(tmp_path, ged_data)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I2@", "@I1@")
        assert result.relationships[0].type == "parent"

    def test_no_name_in_description(self, tmp_path):
        ged_data = (
            "0 @I1@ INDI\n1 NAME Known /Person/\n1 SEX M\n"
            "0 @I2@ INDI\n1 SEX M\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
        )
        ged = _write_ged(tmp_path, ged_data)
        graph = build_parent_child_graph(ged)
        inds = load_individuals(ged)
        result, _ = find_relationship(graph, inds, "@I1@", "@I2@")
        rel = result.relationships[0]
        assert "[Unknown] (@I2@)" in rel.description


# =====================================================================
# Batch 4 tests: formatter, xref validation, CLI integration
# =====================================================================


def _make_ind(
    xref: str = "@I1@",
    name: str = "Alice",
    sex: str = "F",
    birth: int | None = 1900,
    death: int | None = 1970,
) -> RelIndividual:
    return RelIndividual(
        xref=xref, name=name, sex=sex, birth_year=birth, death_year=death
    )


def _no_color() -> Colors:
    return Colors(force_disable=True)


class TestValidateXref:
    def test_simple(self):
        assert _validate_xref("@I1@") == "@I1@"

    def test_numeric(self):
        assert _validate_xref("@I123@") == "@I123@"

    def test_hyphen(self):
        assert _validate_xref("@I1-1@") == "@I1-1@"

    def test_dot(self):
        assert _validate_xref("@I.1@") == "@I.1@"

    def test_colon(self):
        assert _validate_xref("@I1:2@") == "@I1:2@"

    def test_no_at_signs(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_xref("I1")

    def test_embedded_at(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_xref("@I@1@")

    def test_non_ascii(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_xref("@Ié1@")

    def test_space(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_xref("@I 1@")

    def test_empty_between_ats(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_xref("@@")


class TestFormatText:
    def test_single_relationship_header(self):
        p = _make_ind(xref="@I1@", name="John Smith", sex="M", birth=1850, death=1920)
        t = _make_ind(xref="@I3@", name="James Smith", sex="M", birth=None, death=None)
        path = RelationshipPath(
            type="son",
            gen_p=0,
            gen_t=1,
            description="James Smith is the son of John Smith.",
        )
        result = RelationshipResult(
            file="tree.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "=== Relationship ===" in text
        assert "Relationships" not in text

    def test_quiet_mode(self):
        p = _make_ind(xref="@I1@", name="John")
        t = _make_ind(xref="@I2@", name="James", sex="M")
        path = RelationshipPath(
            type="son",
            gen_p=0,
            gen_t=1,
            description="James is the son of John.",
        )
        result = RelationshipResult(
            file="tree.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color(), quiet=True)
        assert text == "James is the son of John."
        assert "File:" not in text

    def test_quiet_mode_not_related(self):
        p = _make_ind(xref="@I1@", name="Alice")
        t = _make_ind(xref="@I2@", name="Bob", sex="M")
        result = RelationshipResult(file="f.ged", primary=p, target=t, related=False)
        text = format_text(result, _no_color(), quiet=True)
        assert "not related" in text

    def test_multiple_relationships_header(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        paths = [
            RelationshipPath(
                type="uncle", gen_p=2, gen_t=1, description="B is an uncle of A."
            ),
            RelationshipPath(
                type="1st cousin",
                gen_p=2,
                gen_t=2,
                description="B is a 1st cousin of A.",
            ),
            RelationshipPath(
                type="2nd cousin",
                gen_p=3,
                gen_t=3,
                description="B is a 2nd cousin of A.",
            ),
        ]
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=paths,
            total_paths=3,
        )
        text = format_text(result, _no_color())
        assert "=== Relationships (3 found) ===" in text
        assert "1. B is an uncle of A." in text
        assert "2. B is a 1st cousin of A." in text
        assert "3. B is a 2nd cousin of A." in text

    def test_half_prefix_in_description(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="brother",
            gen_p=1,
            gen_t=1,
            is_half=True,
            description="B is a half-brother of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "half-brother" in text

    def test_blood_mode_no_half_prefix(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="brother",
            gen_p=1,
            gen_t=1,
            is_half=True,
            description="B is a brother of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "half-brother" not in text
        assert "brother" in text

    def test_cousin_article_a(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="1st cousin",
            gen_p=2,
            gen_t=2,
            description="B is a 1st cousin of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "is a 1st cousin of" in text

    def test_uncle_article_an(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            description="B is an uncle of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "is an uncle of" in text

    def test_direct_line_article_the(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="grandfather",
            gen_p=2,
            gen_t=0,
            description="B is the grandfather of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "is the grandfather of" in text

    def test_same_individual_uses_are(self):
        p = _make_ind(xref="@I1@", name="A")
        path = RelationshipPath(
            type="same individual",
            gen_p=0,
            gen_t=0,
            description="A and A are the same individual.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=p,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "are the same individual" in text

    def test_paths_hint(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            description="B is an uncle of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=3,
        )
        text = format_text(result, _no_color())
        assert "(1 of 3 relationships shown. Use --paths 3 to see all.)" in text

    def test_not_related(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        result = RelationshipResult(file="f.ged", primary=p, target=t, related=False)
        text = format_text(result, _no_color())
        assert "No relationship found." in text

    def test_verbose_truncation_warning(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        result = RelationshipResult(file="f.ged", primary=p, target=t, related=False)
        text = format_text(result, _no_color(), verbose=True, truncated=True)
        assert "Warning:" in text
        assert "--generations" in text

    def test_verbose_no_truncation_no_warning(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            description="B is an uncle of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color(), verbose=True, truncated=False)
        assert "Warning:" not in text

    def test_verbose_truncation_warning_related(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="uncle",
            gen_p=2,
            gen_t=1,
            description="B is an uncle of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color(), verbose=True, truncated=True)
        assert "Warning:" in text
        assert "--generations" in text

    def test_lifespan_display(self):
        p = _make_ind(xref="@I1@", name="John", sex="M", birth=1850, death=1920)
        t = _make_ind(xref="@I2@", name="James", sex="M", birth=None, death=None)
        path = RelationshipPath(
            type="son", gen_p=0, gen_t=1, description="James is the son of John."
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        text = format_text(result, _no_color())
        assert "1850-1920" in text
        assert "?-?" in text


class TestFormatJson:
    def test_standard_output(self):
        p = _make_ind(xref="@I1@", name="John", sex="M", birth=1850, death=1920)
        t = _make_ind(xref="@I3@", name="James", sex="M", birth=1880, death=1950)
        path = RelationshipPath(
            type="son",
            gen_p=0,
            gen_t=1,
            common_ancestors=["@I1@"],
            is_half=False,
            description="James is the son of John.",
        )
        result = RelationshipResult(
            file="tree.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        data = json.loads(format_json(result))
        assert data["file"] == "tree.ged"
        assert data["primary"]["xref"] == "@I1@"
        assert data["primary"]["birth_year"] == 1850
        assert data["target"]["name"] == "James"
        assert data["related"] is True
        rel = data["relationships"][0]
        assert rel["type"] == "son"
        assert rel["gen_from_primary"] == 0
        assert rel["gen_from_target"] == 1
        assert rel["common_ancestors"] == ["@I1@"]
        assert rel["is_half"] is False

    def test_null_years(self):
        p = _make_ind(birth=None, death=None)
        t = _make_ind(xref="@I2@", birth=None, death=None)
        result = RelationshipResult(file="f.ged", primary=p, target=t, related=False)
        data = json.loads(format_json(result))
        assert data["primary"]["birth_year"] is None
        assert data["primary"]["death_year"] is None

    def test_is_half_with_type_all(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="brother",
            gen_p=1,
            gen_t=1,
            common_ancestors=["@I3@"],
            is_half=True,
            description="B is a half-brother of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        data = json.loads(format_json(result))
        assert data["relationships"][0]["is_half"] is True
        assert "half-" in data["relationships"][0]["description"]

    def test_is_half_with_type_blood(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="brother",
            gen_p=1,
            gen_t=1,
            common_ancestors=["@I3@"],
            is_half=True,
            description="B is a brother of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        data = json.loads(format_json(result))
        assert data["relationships"][0]["is_half"] is True
        assert "half-" not in data["relationships"][0]["description"]
        assert data["relationships"][0]["type"] == "brother"

    def test_not_related(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        result = RelationshipResult(file="f.ged", primary=p, target=t, related=False)
        data = json.loads(format_json(result))
        assert data["related"] is False
        assert data["relationships"] == []

    def test_common_ancestors_sorted(self):
        p = _make_ind(xref="@I1@", name="A")
        t = _make_ind(xref="@I2@", name="B", sex="M")
        path = RelationshipPath(
            type="1st cousin",
            gen_p=2,
            gen_t=2,
            common_ancestors=["@I3@", "@I4@"],
            is_half=False,
            description="B is a 1st cousin of A.",
        )
        result = RelationshipResult(
            file="f.ged",
            primary=p,
            target=t,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        data = json.loads(format_json(result))
        assert data["relationships"][0]["common_ancestors"] == ["@I3@", "@I4@"]


class TestRelationshipCLI:
    def test_basic_invocation(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _SIMPLE_FAMILY))
        result = main(["--no-color", "relationship", ged, "@I1@", "@I3@"])
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "son" in out

    def test_json_format(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _SIMPLE_FAMILY))
        result = main(["--format", "json", "relationship", ged, "@I1@", "@I3@"])
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert data["related"] is True
        assert data["relationships"][0]["type"] == "son"

    def test_type_all(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _HALF_SIBLINGS))
        result = main(
            ["--no-color", "relationship", ged, "@I3@", "@I5@", "--type", "all"]
        )
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "half-" in out

    def test_paths_multiple(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _MULTI_TYPE))
        result = main(
            ["--no-color", "relationship", ged, "@I7@", "@I8@", "--paths", "3"]
        )
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Relationships" in out

    def test_paths_single_default(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _MULTI_TYPE))
        result = main(["--no-color", "relationship", ged, "@I7@", "@I8@"])
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "=== Relationship ===" in out

    def test_generations_flag(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _THREE_GEN))
        result = main(
            [
                "--no-color",
                "relationship",
                ged,
                "@I6@",
                "@I1@",
                "--generations",
                "1",
            ]
        )
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "No relationship found." in out

    def test_verbose_truncation_warning(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _THREE_GEN))
        result = main(
            [
                "--verbose",
                "--no-color",
                "relationship",
                ged,
                "@I6@",
                "@I1@",
                "--generations",
                "1",
            ]
        )
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Warning:" in out
        assert "--generations" in out

    def test_verbose_no_truncation_no_warning(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _THREE_GEN))
        result = main(["--verbose", "--no-color", "relationship", ged, "@I6@", "@I1@"])
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "Warning:" not in out

    def test_invalid_xref_format(self, tmp_path):
        ged = str(_write_ged(tmp_path, _SIMPLE_FAMILY))
        with pytest.raises(SystemExit) as exc:
            main(["relationship", ged, "I1", "@I3@"])
        assert exc.value.code == 2

    def test_nonexistent_xref(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _SIMPLE_FAMILY))
        result = main(["relationship", ged, "@I999@", "@I1@"])
        assert result == EXIT_USAGE_ERROR
        err = capsys.readouterr().err
        assert "@I999@" in err
        assert "not found" in err

    def test_unrelated_individuals(self, tmp_path, capsys):
        ged = str(_write_ged(tmp_path, _DISCONNECTED))
        result = main(["--no-color", "relationship", ged, "@I1@", "@I2@"])
        assert result == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "No relationship found." in out
