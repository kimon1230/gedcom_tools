from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gedcom_tools.graph import (
    ParentChildGraph,
    UnionFind,
    build_family_members,
    build_parent_child_graph,
    count_isolated,
    find_ancestors_with_depth,
    find_connected_components,
)


def _write_ged(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    p = tmp_path / filename
    p.write_text(f"0 HEAD\n1 CHAR UTF-8\n{content}0 TRLR\n", encoding="utf-8")
    return p


# Inline GEDCOM for couples/depth tests
_TWO_PARENT_FAM = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n"
    "0 @I2@ INDI\n1 NAME Mary /Jones/\n"
    "0 @I3@ INDI\n1 NAME James /Smith/\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
)

_SINGLE_PARENT_FAM = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n"
    "0 @I3@ INDI\n1 NAME James /Smith/\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I3@\n"
)

_TWO_MARRIAGES = (
    "0 @I1@ INDI\n1 NAME John /Smith/\n"
    "0 @I2@ INDI\n1 NAME Mary /Jones/\n"
    "0 @I3@ INDI\n1 NAME Alice /Brown/\n"
    "0 @I4@ INDI\n1 NAME Child1 /Smith/\n"
    "0 @I5@ INDI\n1 NAME Child2 /Smith/\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I4@\n"
    "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I3@\n1 CHIL @I5@\n"
)

# Three generations: grandparent -> parent -> child
_THREE_GEN = (
    "0 @I1@ INDI\n1 NAME Grandpa /Smith/\n"
    "0 @I2@ INDI\n1 NAME Grandma /Jones/\n"
    "0 @I3@ INDI\n1 NAME Dad /Smith/\n"
    "0 @I4@ INDI\n1 NAME Mom /Brown/\n"
    "0 @I5@ INDI\n1 NAME Kid /Smith/\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
    "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n1 CHIL @I5@\n"
)

# Pedigree collapse: child has same grandparent via both parents
_PEDIGREE_COLLAPSE = (
    "0 @I1@ INDI\n1 NAME Ancestor /X/\n"
    "0 @I2@ INDI\n1 NAME Parent1 /X/\n"
    "0 @I3@ INDI\n1 NAME Parent2 /X/\n"
    "0 @I4@ INDI\n1 NAME Child /X/\n"
    "0 @I5@ INDI\n1 NAME Spouse1 /Y/\n"
    "0 @I6@ INDI\n1 NAME Spouse2 /Z/\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I5@\n1 CHIL @I2@\n"
    "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I6@\n1 CHIL @I3@\n"
    "0 @F3@ FAM\n1 HUSB @I2@\n1 WIFE @I3@\n1 CHIL @I4@\n"
)

# Malformed: 3 parents in one FAM
_THREE_PARENTS = (
    "0 @I1@ INDI\n1 NAME A /X/\n"
    "0 @I2@ INDI\n1 NAME B /Y/\n"
    "0 @I3@ INDI\n1 NAME C /Z/\n"
    "0 @I4@ INDI\n1 NAME Child /W/\n"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 WIFE @I3@\n1 CHIL @I4@\n"
)


class TestBuildParentChildGraphCouples:

    def test_husb_wife_symmetric_couples(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _TWO_PARENT_FAM)
        graph = build_parent_child_graph(p)
        assert "@I2@" in graph.couples.get("@I1@", set())
        assert "@I1@" in graph.couples.get("@I2@", set())

    def test_single_parent_no_couples(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _SINGLE_PARENT_FAM)
        graph = build_parent_child_graph(p)
        assert graph.couples.get("@I1@") is None

    def test_two_marriages_both_partners(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _TWO_MARRIAGES)
        graph = build_parent_child_graph(p)
        partners = graph.couples.get("@I1@", set())
        assert "@I2@" in partners
        assert "@I3@" in partners

    def test_malformed_three_parents_all_get_child_edges(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _THREE_PARENTS)
        graph = build_parent_child_graph(p)
        # All three parents get child-parent edges
        assert "@I1@" in graph.parents_of.get("@I4@", [])
        assert "@I2@" in graph.parents_of.get("@I4@", [])
        assert "@I3@" in graph.parents_of.get("@I4@", [])
        # Only first two used for couples
        i1_partners = graph.couples.get("@I1@", set())
        i2_partners = graph.couples.get("@I2@", set())
        assert "@I2@" in i1_partners
        assert "@I1@" in i2_partners
        # Third parent not in couples with first two
        assert "@I3@" not in i1_partners
        assert "@I3@" not in i2_partners
        assert graph.couples.get("@I3@") is None


class TestFindAncestorsWithDepth:

    def test_self_at_depth_zero_no_parents(self) -> None:
        graph = ParentChildGraph()
        result, truncated = find_ancestors_with_depth(graph, "@I1@")
        assert result == {"@I1@": 0}
        assert truncated is False

    def test_parent_at_depth_1_grandparent_at_depth_2(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(p)
        result, truncated = find_ancestors_with_depth(graph, "@I5@")
        assert result["@I5@"] == 0
        assert result["@I3@"] == 1
        assert result["@I4@"] == 1
        assert result["@I1@"] == 2
        assert result["@I2@"] == 2
        assert truncated is False

    def test_pedigree_collapse_min_depth(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _PEDIGREE_COLLAPSE)
        graph = build_parent_child_graph(p)
        # @I1@ reachable via @I2@ (depth 2) and @I3@ (depth 2) — both same
        result, truncated = find_ancestors_with_depth(graph, "@I4@")
        assert result["@I1@"] == 2
        assert truncated is False

    def test_max_depth_truncation(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(p)
        # max_depth=1: parents found, grandparents NOT
        result, truncated = find_ancestors_with_depth(graph, "@I5@", max_depth=1)
        assert "@I3@" in result
        assert "@I4@" in result
        assert "@I1@" not in result
        assert "@I2@" not in result
        assert truncated is True

    def test_max_depth_no_truncation_leaf_at_boundary(self, tmp_path: Path) -> None:
        p = _write_ged(tmp_path, _THREE_GEN)
        graph = build_parent_child_graph(p)
        # max_depth=2: grandparents found, no further parents → not truncated
        result, truncated = find_ancestors_with_depth(graph, "@I5@", max_depth=2)
        assert "@I1@" in result
        assert "@I2@" in result
        assert truncated is False

    def test_isolated_individual(self) -> None:
        graph = ParentChildGraph()
        result, truncated = find_ancestors_with_depth(graph, "@I99@")
        assert result == {"@I99@": 0}
        assert truncated is False

    def test_duplicate_edges_no_incorrect_depths(self, tmp_path: Path) -> None:
        # Two FAM records pointing same parent to same child
        ged = (
            "0 @I1@ INDI\n1 NAME A /X/\n"
            "0 @I2@ INDI\n1 NAME B /Y/\n"
            "0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
            "0 @F2@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n"
        )
        p = _write_ged(tmp_path, ged)
        graph = build_parent_child_graph(p)
        result, truncated = find_ancestors_with_depth(graph, "@I2@")
        assert result["@I1@"] == 1
        assert truncated is False


class TestUnionFind:

    def test_singleton_element(self) -> None:
        uf = UnionFind(["a"])
        assert uf.find("a") == "a"

    def test_two_element_union(self) -> None:
        uf = UnionFind(["a", "b"])
        uf.union("a", "b")
        assert uf.find("a") == uf.find("b")

    def test_disjoint_sets(self) -> None:
        uf = UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")
        uf.union("c", "d")
        assert uf.find("a") == uf.find("b")
        assert uf.find("c") == uf.find("d")
        assert uf.find("a") != uf.find("c")

    def test_transitive_union(self) -> None:
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.find("a") == uf.find("c")

    def test_redundant_union(self) -> None:
        uf = UnionFind(["a", "b"])
        uf.union("a", "b")
        uf.union("a", "b")
        assert uf.find("a") == uf.find("b")

    def test_path_compression(self) -> None:
        uf = UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")
        uf.union("b", "c")
        uf.union("c", "d")
        root = uf.find("d")
        # After find with path compression, parent should point closer to root
        assert uf.find("d") == root
        assert uf.find("c") == root
        assert uf.find("b") == root


class TestFindConnectedComponents:

    def test_empty_inputs(self) -> None:
        result = find_connected_components(set(), {})
        assert result == {}

    def test_all_singletons_no_families(self) -> None:
        xrefs = {"@I1@", "@I2@", "@I3@"}
        result = find_connected_components(xrefs, {})
        assert len(result) == 3
        for members in result.values():
            assert len(members) == 1

    def test_single_family_connects_members(self) -> None:
        xrefs = {"@I1@", "@I2@", "@I3@"}
        families = {"@F1@": ["@I1@", "@I2@", "@I3@"]}
        result = find_connected_components(xrefs, families)
        assert len(result) == 1
        component = next(iter(result.values()))
        assert set(component) == xrefs

    def test_two_disjoint_families(self) -> None:
        xrefs = {"@I1@", "@I2@", "@I3@", "@I4@"}
        families = {
            "@F1@": ["@I1@", "@I2@"],
            "@F2@": ["@I3@", "@I4@"],
        }
        result = find_connected_components(xrefs, families)
        assert len(result) == 2
        sizes = sorted(len(v) for v in result.values())
        assert sizes == [2, 2]

    def test_families_bridged_by_shared_member(self) -> None:
        xrefs = {"@I1@", "@I2@", "@I3@"}
        families = {
            "@F1@": ["@I1@", "@I2@"],
            "@F2@": ["@I2@", "@I3@"],
        }
        result = find_connected_components(xrefs, families)
        assert len(result) == 1
        assert set(next(iter(result.values()))) == xrefs

    def test_family_with_nonexistent_member_skipped(self) -> None:
        xrefs = {"@I1@", "@I2@"}
        families = {"@F1@": ["@I1@", "@I2@", "@I999@"]}
        result = find_connected_components(xrefs, families)
        assert len(result) == 1
        assert set(next(iter(result.values()))) == {"@I1@", "@I2@"}

    def test_family_with_only_nonexistent_members(self) -> None:
        xrefs = {"@I1@"}
        families = {"@F1@": ["@I999@", "@I998@"]}
        result = find_connected_components(xrefs, families)
        assert len(result) == 1
        assert next(iter(result.values())) == ["@I1@"]

    def test_empty_family(self) -> None:
        xrefs = {"@I1@", "@I2@"}
        families = {"@F1@": []}
        result = find_connected_components(xrefs, families)
        assert len(result) == 2

    def test_single_member_family(self) -> None:
        xrefs = {"@I1@", "@I2@"}
        families = {"@F1@": ["@I1@"]}
        result = find_connected_components(xrefs, families)
        assert len(result) == 2

    def test_mixed_singletons_and_components(self) -> None:
        xrefs = {"@I1@", "@I2@", "@I3@", "@I4@", "@I5@"}
        families = {"@F1@": ["@I1@", "@I2@", "@I3@"]}
        result = find_connected_components(xrefs, families)
        assert len(result) == 3  # one component of 3, two singletons
        sizes = sorted(len(v) for v in result.values())
        assert sizes == [1, 1, 3]


@dataclass
class _FakeFamily:
    """Minimal family object for testing build_family_members."""

    husb_xref: str | None = None
    wife_xref: str | None = None
    chil_xrefs: list[str] = field(default_factory=list)


class TestBuildFamilyMembers:

    def test_basic_family(self) -> None:
        fam = _FakeFamily(husb_xref="@I1@", wife_xref="@I2@", chil_xrefs=["@I3@"])
        result = build_family_members([("@F1@", fam)])
        assert result == {"@F1@": ["@I1@", "@I2@", "@I3@"]}

    def test_none_members_filtered(self) -> None:
        fam = _FakeFamily(husb_xref="@I1@", wife_xref=None, chil_xrefs=[])
        result = build_family_members([("@F1@", fam)])
        assert result == {"@F1@": ["@I1@"]}

    def test_empty_family(self) -> None:
        fam = _FakeFamily()
        result = build_family_members([("@F1@", fam)])
        assert result == {"@F1@": []}

    def test_multiple_families(self) -> None:
        f1 = _FakeFamily(husb_xref="@I1@", wife_xref="@I2@")
        f2 = _FakeFamily(husb_xref="@I3@", wife_xref="@I4@", chil_xrefs=["@I5@"])
        result = build_family_members([("@F1@", f1), ("@F2@", f2)])
        assert len(result) == 2
        assert result["@F1@"] == ["@I1@", "@I2@"]
        assert result["@F2@"] == ["@I3@", "@I4@", "@I5@"]

    def test_empty_input(self) -> None:
        result = build_family_members([])
        assert result == {}


class TestCountIsolated:

    def test_all_singletons(self) -> None:
        components = {"@I1@": ["@I1@"], "@I2@": ["@I2@"]}
        assert count_isolated(components) == 2

    def test_all_pairs(self) -> None:
        components = {"@I1@": ["@I1@", "@I2@"], "@I3@": ["@I3@", "@I4@"]}
        assert count_isolated(components) == 4

    def test_mixed(self) -> None:
        components = {
            "@I1@": ["@I1@"],
            "@I2@": ["@I2@", "@I3@"],
            "@I4@": ["@I4@", "@I5@", "@I6@"],
        }
        assert count_isolated(components) == 3  # 1 singleton + 2 in pair

    def test_no_isolated(self) -> None:
        components = {"@I1@": ["@I1@", "@I2@", "@I3@"]}
        assert count_isolated(components) == 0

    def test_empty(self) -> None:
        assert count_isolated({}) == 0


class TestSearchRegressionAfterRefactor:
    """Verify search command still works after moving graph code to graph.py."""

    def test_search_name_via_shim(self, tmp_path: Path) -> None:
        from gedcom_tools.cli import main

        ged = _write_ged(tmp_path, _TWO_PARENT_FAM)
        rc = main(["--no-color", "search", str(ged), "name:Smith"])
        assert rc == 0
