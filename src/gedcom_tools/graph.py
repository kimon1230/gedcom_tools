"""Graph utilities for GEDCOM family connectivity analysis."""

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
    """Find connected components among individuals linked by families.

    Args:
        individual_xrefs: All known INDI xrefs.
        family_members: Maps each FAM xref to a list of its member INDI xrefs
            (HUSB + WIFE + CHIL, pre-filtered for None). Members not in
            individual_xrefs are silently skipped.

    Returns:
        Components grouped by root xref: ``{root: [member_xrefs]}``.
    """
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
    """Build family-members mapping from family objects.

    Each family object must have ``husb_xref``, ``wife_xref`` (str | None),
    and ``chil_xrefs`` (list[str]) attributes.

    Args:
        families: Iterable of (xref, family_object) pairs.

    Returns:
        Dict mapping FAM xref to list of member INDI xrefs.
    """
    result: dict[str, list[str]] = {}
    for fam_xref, fam in families:
        members = [
            m for m in [fam.husb_xref, fam.wife_xref, *fam.chil_xrefs] if m is not None
        ]
        result[fam_xref] = members
    return result


def count_isolated(components: dict[str, list[str]]) -> int:
    """Count individuals in components of size 1 or 2.

    Args:
        components: Result from :func:`find_connected_components`.

    Returns:
        Total number of individuals in singleton and pair components.
    """
    return sum(len(c) for c in components.values() if len(c) <= 2)
