"""Graph algorithms for GEDCOM family tree connectivity."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ged4py.parser import GedcomReader

from gedcom_tools.utils import extract_xref

logger = logging.getLogger(__name__)

__all__ = [
    "UnionFind",
    "find_connected_components",
    "build_family_members",
    "count_isolated",
    "ParentChildGraph",
    "build_parent_child_graph",
    "find_ancestors",
    "find_descendants",
    "find_ancestors_with_depth",
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


@dataclass
class ParentChildGraph:
    """Directed parent-child relationship graph."""

    parents_of: dict[str, list[str]] = field(default_factory=dict)
    children_of: dict[str, list[str]] = field(default_factory=dict)
    couples: dict[str, set[str]] = field(default_factory=dict)


def build_parent_child_graph(file_path: Path) -> ParentChildGraph:
    """Build directed parent-child graph from FAM records.

    Processes HUSB/WIFE as parents and CHIL as children.
    Builds edges per-parent (not per-couple) to handle single-parent families.
    """
    graph = ParentChildGraph()

    with GedcomReader(str(file_path)) as reader:
        for fam_rec in reader.records0("FAM"):
            parents: list[str] = []
            children: list[str] = []

            for sub in fam_rec.sub_records:
                if sub.tag in ("HUSB", "WIFE") and sub.value:
                    xref = extract_xref(sub.value)
                    if xref:
                        parents.append(xref)
                elif sub.tag == "CHIL" and sub.value:
                    xref = extract_xref(sub.value)
                    if xref:
                        children.append(xref)

            for child in children:
                for parent in parents:
                    child_parents = graph.parents_of.setdefault(child, [])
                    if parent not in child_parents:
                        child_parents.append(parent)
                    parent_children = graph.children_of.setdefault(parent, [])
                    if child not in parent_children:
                        parent_children.append(child)

            # Cap to 2 parents for couples ONLY — child-parent edges use full list
            if len(parents) > 2:
                logger.warning(
                    "FAM %s has %d parents; using first 2 for couples",
                    fam_rec.xref_id,
                    len(parents),
                )
            couple_parents = parents[:2]
            for i, p1 in enumerate(couple_parents):
                for p2 in couple_parents[i + 1 :]:
                    graph.couples.setdefault(p1, set()).add(p2)
                    graph.couples.setdefault(p2, set()).add(p1)

    return graph


def find_ancestors(graph: ParentChildGraph, xref: str, max_depth: int = 50) -> set[str]:
    """Find all ancestors via BFS. Root xref is excluded from results."""
    result: set[str] = set()
    visited: set[str] = {xref}
    queue: deque[tuple[str, int]] = deque()

    for parent in graph.parents_of.get(xref, []):
        if parent not in visited:
            visited.add(parent)
            queue.append((parent, 1))
            result.add(parent)

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for parent in graph.parents_of.get(current, []):
            if parent not in visited:
                visited.add(parent)
                queue.append((parent, depth + 1))
                result.add(parent)

    return result


def find_descendants(
    graph: ParentChildGraph, xref: str, max_depth: int = 50
) -> set[str]:
    """Find all descendants via BFS. Root xref is excluded from results."""
    result: set[str] = set()
    visited: set[str] = {xref}
    queue: deque[tuple[str, int]] = deque()

    for child in graph.children_of.get(xref, []):
        if child not in visited:
            visited.add(child)
            queue.append((child, 1))
            result.add(child)

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for child in graph.children_of.get(current, []):
            if child not in visited:
                visited.add(child)
                queue.append((child, depth + 1))
                result.add(child)

    return result


def find_ancestors_with_depth(
    graph: ParentChildGraph, xref: str, max_depth: int = 30
) -> tuple[dict[str, int], bool]:
    """Find all ancestors with their minimum depth via BFS.

    Returns (dict mapping xref to min depth, truncated flag).
    Self is included at depth 0. Truncated is True when ancestors
    beyond max_depth were left unexplored.
    """
    ancestors: dict[str, int] = {xref: 0}
    visited: set[str] = {xref}
    queue: deque[tuple[str, int]] = deque()
    truncated = False

    for parent in graph.parents_of.get(xref, []):
        if parent not in visited:
            visited.add(parent)
            ancestors[parent] = 1
            queue.append((parent, 1))

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            # At max_depth: node is in result but parents are not explored
            if graph.parents_of.get(current, []):
                truncated = True
            continue
        for parent in graph.parents_of.get(current, []):
            if parent not in visited:
                visited.add(parent)
                ancestors[parent] = depth + 1
                queue.append((parent, depth + 1))

    return ancestors, truncated
