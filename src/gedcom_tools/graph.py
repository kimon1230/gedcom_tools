"""Graph algorithms for GEDCOM family tree connectivity."""

from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

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


class SubLineLike(Protocol):
    """A GEDCOM line below level 0, as seen by the graph builder."""

    @property
    def level(self) -> int: ...

    @property
    def tag(self) -> str: ...

    @property
    def value(self) -> str | None: ...


class RecordLike(Protocol):
    """A parsed level-0 record with its sub-lines flattened into one list.

    Structural match for ``filter.models.GedcomRecord``, declared here so
    the graph builder does not have to import a command package.
    """

    @property
    def xref(self) -> str | None: ...

    @property
    def tag(self) -> str: ...

    @property
    def children(self) -> Sequence[SubLineLike]: ...


# Family membership as the graph builder consumes it: (fam xref, parents, children)
_FamilyTriple = tuple[str | None, list[str], list[str]]


def _sort_pointer(
    tag: str | None, value: Any, parents: list[str], children: list[str]
) -> None:
    """Append a FAM sub-line's pointer to the parent or child list.

    Sub-lines that are not HUSB/WIFE/CHIL, carry no value, or whose value
    is not a resolvable xref are ignored -- a dangling pointer is still an
    xref and is kept, but ``1 CHIL`` with nothing after it is not.
    """
    if tag in ("HUSB", "WIFE"):
        target = parents
    elif tag == "CHIL":
        target = children
    else:
        return
    if not value:
        return
    xref = extract_xref(value)
    if xref:
        target.append(xref)


def _families_from_file(file_path: Path) -> Iterator[_FamilyTriple]:
    """Yield family membership by re-parsing the file with ged4py."""
    with GedcomReader(str(file_path)) as reader:
        for fam_rec in reader.records0("FAM"):
            parents: list[str] = []
            children: list[str] = []
            for sub in fam_rec.sub_records:
                _sort_pointer(sub.tag, sub.value, parents, children)
            yield fam_rec.xref_id, parents, children


def _families_from_records(records: Iterable[RecordLike]) -> Iterator[_FamilyTriple]:
    """Yield family membership from already-parsed records."""
    for rec in records:
        if rec.tag != "FAM":
            continue
        parents: list[str] = []
        children: list[str] = []
        for line in rec.children:
            # ged4py exposes only immediate subordinates; this child list is
            # flat and spans every level, so anything deeper than 1 would add
            # edges the file-path route never sees.
            if line.level == 1:
                _sort_pointer(line.tag, line.value, parents, children)
        yield rec.xref, parents, children


def _add_family(
    graph: ParentChildGraph,
    fam_xref: str | None,
    parents: list[str],
    children: list[str],
) -> None:
    """Add one family's parent-child and couple edges to the graph."""
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
            fam_xref,
            len(parents),
        )
    couple_parents = parents[:2]
    for i, p1 in enumerate(couple_parents):
        for p2 in couple_parents[i + 1 :]:
            graph.couples.setdefault(p1, set()).add(p2)
            graph.couples.setdefault(p2, set()).add(p1)


def build_parent_child_graph(
    source: Path | str | os.PathLike[str] | Iterable[RecordLike],
) -> ParentChildGraph:
    """Build directed parent-child graph from FAM records.

    ``source`` is either a path to a GEDCOM file, which is parsed with
    ged4py, or an iterable of level-0 records that has already been parsed.
    Both forms feed the same edge-building code and produce equal graphs;
    callers that already hold the records should pass them rather than pay
    for a second parse of the file.

    A path may be a ``Path``, a ``str`` or any other ``os.PathLike``. A bare
    ``str`` is always a path and never a sequence of records -- it is
    iterable, so the records branch would walk it one character at a time.

    Processes HUSB/WIFE as parents and CHIL as children.
    Builds edges per-parent (not per-couple) to handle single-parent families.
    """
    graph = ParentChildGraph()

    families = (
        _families_from_file(Path(source))
        if isinstance(source, (str, os.PathLike))
        else _families_from_records(source)
    )
    for fam_xref, parents, children in families:
        _add_family(graph, fam_xref, parents, children)

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
