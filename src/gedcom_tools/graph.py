"""Graph algorithms for GEDCOM family tree connectivity."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

__all__ = [
    "UnionFind",
    "find_connected_components",
    "build_family_members",
    "count_isolated",
]


class UnionFind:
    """Disjoint-set data structure with path compression and union by rank."""

    def __init__(self, elements: Iterable[str]) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}
        for e in elements:
            self._parent[e] = e
            self._rank[e] = 0

    def find(self, x: str) -> str:
        """Find root of element with path compression."""
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        """Merge sets containing x and y using union by rank."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1


def find_connected_components(
    individual_xrefs: set[str],
    family_members: dict[str, list[str]],
) -> dict[str, list[str]]:
    # TODO: consider returning frozensets instead of lists for immutability
    uf = UnionFind(individual_xrefs)

    for members in family_members.values():
        valid = [m for m in members if m in individual_xrefs]
        for i in range(1, len(valid)):
            uf.union(valid[0], valid[i])

    components: dict[str, list[str]] = defaultdict(list)
    for xref in individual_xrefs:
        components[uf.find(xref)].append(xref)
    return dict(components)


def build_family_members(
    families: Iterable[tuple[str, Any]],
) -> dict[str, list[str]]:
    # Expects objects with husb_xref, wife_xref, chil_xrefs attrs
    result: dict[str, list[str]] = {}
    for fam_xref, fam in families:
        members = [
            m for m in [fam.husb_xref, fam.wife_xref, *fam.chil_xrefs] if m is not None
        ]
        result[fam_xref] = members
    return result


def count_isolated(components: dict[str, list[str]]) -> int:
    return sum(len(c) for c in components.values() if len(c) <= 2)
