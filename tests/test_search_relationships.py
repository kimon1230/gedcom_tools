from __future__ import annotations

from pathlib import Path

from gedcom_tools.commands.search.relationships import (
    ParentChildGraph,
    build_parent_child_graph,
    find_ancestors,
    find_descendants,
)


def _write_ged(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    p = tmp_path / filename
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n")
    return p


THREE_GEN = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n1 FAMS @F1@\n"
    "0 @I2@ INDI\n1 NAME Mary /Jones/\n1 FAMS @F1@\n"
    "0 @I3@ INDI\n1 NAME James /Smith/\n1 FAMC @F1@\n1 FAMS @F2@\n"
    "0 @I4@ INDI\n1 NAME Alice /Brown/\n1 FAMS @F2@\n"
    "0 @I5@ INDI\n1 NAME Robert /Smith/\n1 FAMC @F2@\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
    "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n1 CHIL @I5@\n"
)


# ---------------------------------------------------------------------------
# Graph building
# ---------------------------------------------------------------------------


class TestBuildGraph:
    def test_basic_family(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @I3@ INDI\n1 NAME E /F/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n",
        )
        graph = build_parent_child_graph(ged)
        assert set(graph.parents_of["@I3@"]) == {"@I1@", "@I2@"}
        assert "@I3@" in graph.children_of["@I1@"]
        assert "@I3@" in graph.children_of["@I2@"]

    def test_single_parent(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n",
        )
        graph = build_parent_child_graph(ged)
        assert graph.parents_of["@I2@"] == ["@I1@"]
        assert graph.children_of["@I1@"] == ["@I2@"]

    def test_multiple_children(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @I3@ INDI\n1 NAME E /F/\n"
            "0 @I4@ INDI\n1 NAME G /H/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
            "1 CHIL @I3@\n1 CHIL @I4@\n",
        )
        graph = build_parent_child_graph(ged)
        assert set(graph.children_of["@I1@"]) == {"@I3@", "@I4@"}
        assert set(graph.children_of["@I2@"]) == {"@I3@", "@I4@"}
        assert set(graph.parents_of["@I3@"]) == {"@I1@", "@I2@"}
        assert set(graph.parents_of["@I4@"]) == {"@I1@", "@I2@"}

    def test_no_families(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        graph = build_parent_child_graph(ged)
        assert graph.parents_of == {}
        assert graph.children_of == {}

    def test_empty_family_no_children(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n",
        )
        graph = build_parent_child_graph(ged)
        assert graph.children_of == {}
        assert graph.parents_of == {}


# ---------------------------------------------------------------------------
# find_ancestors
# ---------------------------------------------------------------------------


class TestFindAncestors:
    def test_direct_parents(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        ancestors = find_ancestors(graph, "@I5@")
        assert "@I3@" in ancestors
        assert "@I4@" in ancestors

    def test_grandparents(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        ancestors = find_ancestors(graph, "@I5@")
        assert ancestors == {"@I1@", "@I2@", "@I3@", "@I4@"}

    def test_root_excluded(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        ancestors = find_ancestors(graph, "@I5@")
        assert "@I5@" not in ancestors

    def test_no_parents(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        ancestors = find_ancestors(graph, "@I1@")
        assert ancestors == set()

    def test_xref_not_in_graph(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        ancestors = find_ancestors(graph, "@I999@")
        assert ancestors == set()


# ---------------------------------------------------------------------------
# find_descendants
# ---------------------------------------------------------------------------


class TestFindDescendants:
    def test_direct_children(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        desc = find_descendants(graph, "@I3@")
        assert "@I5@" in desc

    def test_grandchildren(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        desc = find_descendants(graph, "@I1@")
        assert desc == {"@I3@", "@I5@"}

    def test_root_excluded(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        desc = find_descendants(graph, "@I1@")
        assert "@I1@" not in desc

    def test_no_children(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        desc = find_descendants(graph, "@I5@")
        assert desc == set()

    def test_xref_not_in_graph(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        desc = find_descendants(graph, "@I999@")
        assert desc == set()

    def test_both_parents_share_descendants(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, THREE_GEN)
        graph = build_parent_child_graph(ged)
        desc_father = find_descendants(graph, "@I1@")
        desc_mother = find_descendants(graph, "@I2@")
        assert desc_father == desc_mother


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_cycle_detection(self, tmp_path: Path) -> None:
        # I1 is parent of I2, I2 is parent of I1 (invalid but shouldn't crash)
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
            "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I1@\n",
        )
        graph = build_parent_child_graph(ged)
        # Should terminate without infinite loop
        ancestors = find_ancestors(graph, "@I1@")
        assert "@I2@" in ancestors
        desc = find_descendants(graph, "@I1@")
        assert "@I2@" in desc

    def test_self_referential(self, tmp_path: Path) -> None:
        # Individual is own parent (malformed GEDCOM)
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n" "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I1@\n",
        )
        graph = build_parent_child_graph(ged)
        # Root is in visited set, so self-reference doesn't cause loop
        ancestors = find_ancestors(graph, "@I1@")
        assert ancestors == set()
        desc = find_descendants(graph, "@I1@")
        assert desc == set()

    def test_pedigree_collapse(self, tmp_path: Path) -> None:
        # I3 and I4 are siblings who have child I5
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @I3@ INDI\n1 NAME E /F/\n"
            "0 @I4@ INDI\n1 NAME G /H/\n"
            "0 @I5@ INDI\n1 NAME J /K/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
            "1 CHIL @I3@\n1 CHIL @I4@\n"
            "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n1 CHIL @I5@\n",
        )
        graph = build_parent_child_graph(ged)
        ancestors = find_ancestors(graph, "@I5@")
        # I1 and I2 are grandparents through both I3 and I4 — deduplicated
        assert ancestors == {"@I1@", "@I2@", "@I3@", "@I4@"}

    def test_depth_limit(self, tmp_path: Path) -> None:
        # Build a chain: I1→I2→I3→I4 with depth limit 2
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @I3@ INDI\n1 NAME E /F/\n"
            "0 @I4@ INDI\n1 NAME G /H/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
            "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I3@\n"
            "0 @F3@ FAM\n1 HUSB @I3@\n1 CHIL @I4@\n",
        )
        graph = build_parent_child_graph(ged)
        # max_depth=2: I4→I3 (depth 1), I3→I2 (depth 2), stops before I1
        ancestors = find_ancestors(graph, "@I4@", max_depth=2)
        assert "@I3@" in ancestors
        assert "@I2@" in ancestors
        assert "@I1@" not in ancestors

    def test_depth_limit_descendants(self, tmp_path: Path) -> None:
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @I3@ INDI\n1 NAME E /F/\n"
            "0 @I4@ INDI\n1 NAME G /H/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
            "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I3@\n"
            "0 @F3@ FAM\n1 HUSB @I3@\n1 CHIL @I4@\n",
        )
        graph = build_parent_child_graph(ged)
        # max_depth=1: only direct children
        desc = find_descendants(graph, "@I1@", max_depth=1)
        assert desc == {"@I2@"}

    def test_adoptive_family(self, tmp_path: Path) -> None:
        # I3 is child in two families (biological + adoptive)
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @I3@ INDI\n1 NAME E /F/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I3@\n"
            "0 @F2@ FAM\n1 HUSB @I2@\n1 CHIL @I3@\n",
        )
        graph = build_parent_child_graph(ged)
        parents = set(graph.parents_of["@I3@"])
        assert parents == {"@I1@", "@I2@"}

    def test_isolated_individual(self, tmp_path: Path) -> None:
        ged = _write_ged(tmp_path, "0 @I1@ INDI\n1 NAME A /B/\n")
        graph = build_parent_child_graph(ged)
        assert find_ancestors(graph, "@I1@") == set()
        assert find_descendants(graph, "@I1@") == set()

    def test_no_duplicate_edges(self, tmp_path: Path) -> None:
        # Same child-parent pair referenced in two families
        ged = _write_ged(
            tmp_path,
            "0 @I1@ INDI\n1 NAME A /B/\n"
            "0 @I2@ INDI\n1 NAME C /D/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
            "0 @F2@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n",
        )
        graph = build_parent_child_graph(ged)
        assert graph.parents_of["@I2@"].count("@I1@") == 1
        assert graph.children_of["@I1@"].count("@I2@") == 1


# ---------------------------------------------------------------------------
# Graph dataclass
# ---------------------------------------------------------------------------


class TestParentChildGraph:
    def test_empty_graph(self) -> None:
        graph = ParentChildGraph()
        assert graph.parents_of == {}
        assert graph.children_of == {}

    def test_get_nonexistent_key(self) -> None:
        graph = ParentChildGraph()
        assert graph.parents_of.get("@I1@", []) == []
        assert graph.children_of.get("@I1@", []) == []
