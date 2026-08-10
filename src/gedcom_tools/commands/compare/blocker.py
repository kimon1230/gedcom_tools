from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gedcom_tools.commands.compare.models import CompareIndividual


DEFAULT_MAX_BLOCK_SIZE = 500


def describe_oversized_blocks(count: int, max_block_size: int) -> str:
    """Warning text for blocking groups dropped by the block-size cap.

    Shared by `compare` and `duplicates` so both report the same thing.
    """
    groups = "group" if count == 1 else "groups"
    was = "was" if count == 1 else "were"
    return (
        f"Warning: {count:,} blocking {groups} exceeded --max-block-size "
        f"{max_block_size} and {was} skipped, so some matches may be missing.\n"
        "  Re-run with a larger --max-block-size to include them; scoring cost "
        "grows with the square of the group size."
    )


def _key_surname_birth(ind: CompareIndividual) -> str | None:
    if ind.surname_phonetic and ind.birth_decade:
        return f"{ind.surname_phonetic}|{ind.birth_decade}"
    return None


def _key_surname_death(ind: CompareIndividual) -> str | None:
    if ind.surname_phonetic and ind.death_decade:
        return f"{ind.surname_phonetic}|{ind.death_decade}"
    return None


def _key_given_birth(ind: CompareIndividual) -> str | None:
    if ind.given_phonetic and ind.birth_decade:
        return f"{ind.given_phonetic}|{ind.birth_decade}"
    return None


def _key_exact_years(ind: CompareIndividual) -> str | None:
    if ind.birth_year is not None and ind.death_year is not None:
        return f"{ind.birth_year}|{ind.death_year}"
    return None


def _key_surname_given(ind: CompareIndividual) -> str | None:
    if ind.surname_phonetic and ind.given_phonetic:
        return f"{ind.surname_phonetic}|{ind.given_phonetic}"
    return None


_PASS_KEY_FNS: list[Callable[[CompareIndividual], str | None]] = [
    _key_surname_birth,
    _key_surname_death,
    _key_given_birth,
    _key_exact_years,
    _key_surname_given,
]


def _multi_key_surname_birth(ind: CompareIndividual) -> list[str]:
    """Keys for both primary and alt surname codes paired with birth decade."""
    keys: list[str] = []
    if ind.surname_phonetic and ind.birth_decade:
        keys.append(f"{ind.surname_phonetic}|{ind.birth_decade}")
    if (
        ind.surname_phonetic_alt
        and ind.birth_decade
        and ind.surname_phonetic_alt != ind.surname_phonetic
    ):
        keys.append(f"{ind.surname_phonetic_alt}|{ind.birth_decade}")
    return keys


def _multi_key_surname_given(ind: CompareIndividual) -> list[str]:
    """Keys for both primary and alt surname codes paired with given phonetic."""
    keys: list[str] = []
    if ind.surname_phonetic and ind.given_phonetic:
        keys.append(f"{ind.surname_phonetic}|{ind.given_phonetic}")
    if (
        ind.surname_phonetic_alt
        and ind.given_phonetic
        and ind.surname_phonetic_alt != ind.surname_phonetic
    ):
        keys.append(f"{ind.surname_phonetic_alt}|{ind.given_phonetic}")
    return keys


_METAPHONE_MULTI_KEY_FNS: list[Callable[[CompareIndividual], list[str]]] = [
    _multi_key_surname_birth,
    _multi_key_surname_given,
]


def _run_pass(
    individuals_a: list[CompareIndividual],
    individuals_b: list[CompareIndividual],
    key_fn: Callable[[CompareIndividual], str | None],
    max_block_size: int,
    candidates: set[tuple[str, str]],
    oversized_keys: set[str],
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
        if block is None:
            continue
        if len(block) > max_block_size:
            # Record the key, not a counter: this branch runs once per
            # individual on side A, so a single fat block would otherwise
            # be reported as hundreds of skipped groups.
            oversized_keys.add(key)
            continue
        xref_a = ind.xref
        for xref_b in block:
            candidates.add((xref_a, xref_b))


def _run_multi_key_pass(
    individuals_a: list[CompareIndividual],
    individuals_b: list[CompareIndividual],
    key_fn: Callable[[CompareIndividual], list[str]],
    max_block_size: int,
    candidates: set[tuple[str, str]],
    oversized_keys: set[str],
) -> None:
    blocks: dict[str, list[str]] = defaultdict(list)
    for ind in individuals_b:
        for key in key_fn(ind):
            blocks[key].append(ind.xref)

    for ind in individuals_a:
        xref_a = ind.xref
        for key in key_fn(ind):
            block = blocks.get(key)
            if block is None:
                continue
            if len(block) > max_block_size:
                oversized_keys.add(key)
                continue
            for xref_b in block:
                candidates.add((xref_a, xref_b))


def generate_candidates(
    individuals_a: list[CompareIndividual],
    individuals_b: list[CompareIndividual],
    max_block_size: int = DEFAULT_MAX_BLOCK_SIZE,
    algorithm: str = "soundex",
    oversized_keys: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Return set of (xref_a, xref_b) candidate pairs.

    Blocks larger than ``max_block_size`` are skipped, which silently costs
    recall.  Pass a set as ``oversized_keys`` to find out: every blocking key
    that was skipped lands in it, so ``len(oversized_keys)`` is the number of
    distinct groups dropped.  Keys are deduplicated across passes, so two
    passes that happen to produce the same key string count once.
    """
    candidates: set[tuple[str, str]] = set()
    skipped = oversized_keys if oversized_keys is not None else set()
    for key_fn in _PASS_KEY_FNS:
        _run_pass(
            individuals_a, individuals_b, key_fn, max_block_size, candidates, skipped
        )
    if algorithm == "metaphone":
        for mk_fn in _METAPHONE_MULTI_KEY_FNS:
            _run_multi_key_pass(
                individuals_a,
                individuals_b,
                mk_fn,
                max_block_size,
                candidates,
                skipped,
            )
    return candidates
