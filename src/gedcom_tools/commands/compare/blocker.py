from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gedcom_tools.commands.compare.models import CompareIndividual


def _key_surname_birth(ind: CompareIndividual) -> str | None:
    if ind.surname_soundex and ind.birth_decade:
        return f"{ind.surname_soundex}|{ind.birth_decade}"
    return None


def _key_surname_death(ind: CompareIndividual) -> str | None:
    if ind.surname_soundex and ind.death_decade:
        return f"{ind.surname_soundex}|{ind.death_decade}"
    return None


def _key_given_birth(ind: CompareIndividual) -> str | None:
    if ind.given_name_soundex and ind.birth_decade:
        return f"{ind.given_name_soundex}|{ind.birth_decade}"
    return None


def _key_exact_years(ind: CompareIndividual) -> str | None:
    if ind.birth_year is not None and ind.death_year is not None:
        return f"{ind.birth_year}|{ind.death_year}"
    return None


def _key_surname_given(ind: CompareIndividual) -> str | None:
    if ind.surname_soundex and ind.given_name_soundex:
        return f"{ind.surname_soundex}|{ind.given_name_soundex}"
    return None


_PASS_KEY_FNS: list[Callable[[CompareIndividual], str | None]] = [
    _key_surname_birth,
    _key_surname_death,
    _key_given_birth,
    _key_exact_years,
    _key_surname_given,
]


def _run_pass(
    individuals_a: list[CompareIndividual],
    individuals_b: list[CompareIndividual],
    key_fn: Callable[[CompareIndividual], str | None],
    max_block_size: int,
    candidates: set[tuple[str, str]],
) -> None:
    # Index side B
    blocks: dict[str, list[str]] = defaultdict(list)
    for ind in individuals_b:
        key = key_fn(ind)
        if key is not None:
            blocks[key].append(ind.xref)

    # Look up side A against B's blocks
    for ind in individuals_a:
        key = key_fn(ind)
        if key is None:
            continue
        block = blocks.get(key)
        if block is None or len(block) > max_block_size:
            continue
        xref_a = ind.xref
        for xref_b in block:
            candidates.add((xref_a, xref_b))


def generate_candidates(
    individuals_a: list[CompareIndividual],
    individuals_b: list[CompareIndividual],
    max_block_size: int = 500,
) -> set[tuple[str, str]]:
    """Return set of (xref_a, xref_b) candidate pairs."""
    candidates: set[tuple[str, str]] = set()
    for key_fn in _PASS_KEY_FNS:
        _run_pass(individuals_a, individuals_b, key_fn, max_block_size, candidates)
    return candidates
