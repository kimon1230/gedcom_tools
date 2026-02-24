from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ged4py.parser import GedcomReader

from gedcom_tools.utils import extract_xref


@dataclass
class ParentChildGraph:
    """Directed parent-child relationship graph."""

    parents_of: dict[str, list[str]] = field(default_factory=dict)
    children_of: dict[str, list[str]] = field(default_factory=dict)


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
