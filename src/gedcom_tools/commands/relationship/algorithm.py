"""Relationship finding algorithm using Lowest Common Ancestor."""

from __future__ import annotations

from pathlib import Path

from ged4py.parser import GedcomReader

from gedcom_tools.commands.relationship.classifier import (
    build_description,
    classify_relationship,
)
from gedcom_tools.commands.relationship.models import (
    RelationshipPath,
    RelationshipResult,
    RelIndividual,
)
from gedcom_tools.dates import extract_year_from_date
from gedcom_tools.graph import ParentChildGraph, find_ancestors_with_depth
from gedcom_tools.utils import normalize_display, parse_name_record, xref_sort_key


def load_individuals(file_path: Path) -> dict[str, RelIndividual]:
    """Load all INDI records into RelIndividual dict. Single pass."""
    individuals: dict[str, RelIndividual] = {}
    with GedcomReader(str(file_path)) as reader:
        for rec in reader.records0("INDI"):
            xref = rec.xref_id
            if not xref:
                continue

            # Name: first NAME record only
            name_rec = next((sub for sub in rec.sub_records if sub.tag == "NAME"), None)
            given, surname = parse_name_record(name_rec)
            composed = normalize_display(f"{given} {surname}".strip()).strip()
            name = composed or f"[Unknown] ({xref})"

            # Sex
            sex = ""
            sex_rec = rec.sub_tag("SEX")
            if sex_rec and sex_rec.value:
                sex = str(sex_rec.value).upper().strip()

            # Birth/death years
            birth_year: int | None = None
            death_year: int | None = None
            birt = rec.sub_tag("BIRT")
            if birt:
                date_rec = birt.sub_tag("DATE")
                if date_rec and date_rec.value:
                    birth_year = extract_year_from_date(date_rec.value)
            deat = rec.sub_tag("DEAT")
            if deat:
                date_rec = deat.sub_tag("DATE")
                if date_rec and date_rec.value:
                    death_year = extract_year_from_date(date_rec.value)

            individuals[xref] = RelIndividual(
                xref=xref,
                name=name,
                sex=sex,
                birth_year=birth_year,
                death_year=death_year,
            )
    return individuals


def _compute_is_half(
    gen_p: int,
    gen_t: int,
    group_ancestors: list[str],
    all_common_ancestors: set[str],
    graph: ParentChildGraph,
    primary_xref: str,
    target_xref: str,
) -> bool:
    """Determine if a relationship is half (True) or full (False)."""
    # Direct lines are never half
    if gen_p == 0 or gen_t == 0:
        return False

    # Siblings: count shared parents
    if gen_p == 1 and gen_t == 1:
        p_parents = set(graph.parents_of.get(primary_xref, []))
        t_parents = set(graph.parents_of.get(target_xref, []))
        shared = len(p_parents & t_parents)
        # 0 shared = half (incomplete data), 1 = half, >= 2 = full
        return shared < 2

    # General case: spouse-pairing via graph.couples
    # If ANY ancestor in the group is paired (has a partner in the
    # full common ancestor set), the group is full-blood.
    for ancestor in group_ancestors:
        partners = graph.couples.get(ancestor, set())
        if partners & all_common_ancestors:
            return False
    return True


def _sort_key(
    path: RelationshipPath,
    individuals: dict[str, RelIndividual],
) -> tuple[int, bool, int]:
    """Multi-key sort: shortest path, blood over half, male line."""
    total_gens = path.gen_p + path.gen_t
    # False < True: full-blood sorts before half
    is_half = path.is_half
    # Negate for descending sort (more males = better)
    male_count = sum(
        1
        for xref in path.common_ancestors
        if individuals.get(xref) and individuals[xref].sex == "M"
    )
    return (total_gens, is_half, -male_count)


def find_relationship(
    graph: ParentChildGraph,
    individuals: dict[str, RelIndividual],
    primary: str,
    target: str,
    *,
    paths: int = 1,
    max_generations: int = 30,
    show_half: bool = False,
) -> tuple[RelationshipResult, bool]:
    """Find relationship between primary and target.

    Returns (result, truncated) where truncated indicates BFS
    was limited by max_generations.
    """
    primary_ind = individuals[primary]
    target_ind = individuals[target]

    # Short-circuit: same individual
    if primary == target:
        desc = build_description(
            target_ind.name,
            primary_ind.name,
            "same individual",
            is_half=False,
            show_half=False,
        )
        path = RelationshipPath(
            type="same individual",
            gen_p=0,
            gen_t=0,
            common_ancestors=[primary],
            is_half=False,
            description=desc,
        )
        result = RelationshipResult(
            file="",
            primary=primary_ind,
            target=target_ind,
            related=True,
            relationships=[path],
            total_paths=1,
        )
        return result, False

    # BFS upward from both
    ancestors_p, trunc_p = find_ancestors_with_depth(
        graph, primary, max_depth=max_generations
    )
    ancestors_t, trunc_t = find_ancestors_with_depth(
        graph, target, max_depth=max_generations
    )
    truncated = trunc_p or trunc_t

    # Common ancestors (intersection of xref sets)
    # Don't discard primary/target — they're valid direct-line ancestors
    # (same-individual case is already short-circuited above)
    common = set(ancestors_p.keys()) & set(ancestors_t.keys())

    if not common:
        result = RelationshipResult(
            file="",
            primary=primary_ind,
            target=target_ind,
            related=False,
        )
        return result, truncated

    # Group by (gen_p, gen_t)
    groups: dict[tuple[int, int], list[str]] = {}
    for xref in common:
        key = (ancestors_p[xref], ancestors_t[xref])
        groups.setdefault(key, []).append(xref)

    # Classify each group
    raw_paths: list[RelationshipPath] = []
    for (gen_p, gen_t), ancestor_list in groups.items():
        base_type = classify_relationship(gen_p, gen_t, target_ind.sex)
        is_half = _compute_is_half(
            gen_p,
            gen_t,
            ancestor_list,
            common,
            graph,
            primary,
            target,
        )
        sorted_ancestors = sorted(ancestor_list, key=xref_sort_key)
        desc = build_description(
            target_ind.name,
            primary_ind.name,
            base_type,
            is_half=is_half,
            show_half=show_half,
        )
        raw_paths.append(
            RelationshipPath(
                type=base_type,
                gen_p=gen_p,
                gen_t=gen_t,
                common_ancestors=sorted_ancestors,
                is_half=is_half,
                description=desc,
            )
        )

    # Deduplicate by (base_type, is_half)
    dedup: dict[tuple[str, bool], RelationshipPath] = {}
    for p in raw_paths:
        dedup_key = (p.type, p.is_half)
        if dedup_key not in dedup:
            dedup[dedup_key] = p
        else:
            existing = dedup[dedup_key]
            new_sum = p.gen_p + p.gen_t
            old_sum = existing.gen_p + existing.gen_t
            # Keep smallest sum; for equal sums, smaller gen_p wins
            if new_sum < old_sum or (new_sum == old_sum and p.gen_p < existing.gen_p):
                # Merge ancestors, keep new gen_p/gen_t
                merged_ancestors = sorted(
                    set(existing.common_ancestors) | set(p.common_ancestors),
                    key=xref_sort_key,
                )
                dedup[dedup_key] = RelationshipPath(
                    type=p.type,
                    gen_p=p.gen_p,
                    gen_t=p.gen_t,
                    common_ancestors=merged_ancestors,
                    is_half=p.is_half,
                    description=p.description,
                )
            else:
                # Keep existing gen_p/gen_t but merge ancestors
                merged_ancestors = sorted(
                    set(existing.common_ancestors) | set(p.common_ancestors),
                    key=xref_sort_key,
                )
                existing.common_ancestors = merged_ancestors

    # Sort and limit
    all_paths = sorted(dedup.values(), key=lambda p: _sort_key(p, individuals))
    selected = all_paths[:paths]

    result = RelationshipResult(
        file="",
        primary=primary_ind,
        target=target_ind,
        related=True,
        relationships=selected,
        total_paths=len(all_paths),
    )
    return result, truncated
