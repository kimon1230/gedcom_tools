from __future__ import annotations

from dataclasses import dataclass, field

from gedcom_tools.graph import (
    UnionFind,
    build_family_members,
    count_isolated,
    find_connected_components,
)


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
