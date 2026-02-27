"""Relationship classification and description building."""

from __future__ import annotations


def _ordinal(n: int) -> str:
    """Return ordinal string: 1->'1st', 2->'2nd', 3->'3rd', etc."""
    if n < 1:
        raise ValueError(f"Ordinal requires n >= 1, got {n}")
    # 11, 12, 13 always use "th"
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _removed_label(n: int) -> str:
    """Return removal label: 0->'', 1->'once removed', etc."""
    if n < 0:
        raise ValueError(f"Removed requires n >= 0, got {n}")
    if n == 0:
        return ""
    if n == 1:
        return "once removed"
    if n == 2:
        return "twice removed"
    return f"{n} times removed"


def _sex_term(male: str, female: str, neutral: str, target_sex: str) -> str:
    if target_sex == "M":
        return male
    if target_sex == "F":
        return female
    return neutral


def classify_relationship(gen_p: int, gen_t: int, target_sex: str) -> str:
    """Classify a (gen_p, gen_t) pair into a base relationship type.

    Returns the base type string (no half-prefix).
    Priority order matters — sibling must come before uncle/aunt.
    """
    # Priority 1: same individual
    if gen_p == 0 and gen_t == 0:
        return "same individual"

    # Priority 2: direct ancestor (target is ancestor of primary)
    if gen_t == 0:
        if gen_p == 1:
            return _sex_term("father", "mother", "parent", target_sex)
        if gen_p == 2:
            return _sex_term("grandfather", "grandmother", "grandparent", target_sex)
        # gen_p >= 3: great-grandparent with multiplier
        greats = gen_p - 2
        base = _sex_term(
            "great-grandfather",
            "great-grandmother",
            "great-grandparent",
            target_sex,
        )
        if greats == 1:
            return base
        return f"{greats}x {base}"

    # Priority 3: direct descendant (target is descendant of primary)
    if gen_p == 0:
        if gen_t == 1:
            return _sex_term("son", "daughter", "child", target_sex)
        if gen_t == 2:
            return _sex_term("grandson", "granddaughter", "grandchild", target_sex)
        greats = gen_t - 2
        base = _sex_term(
            "great-grandson",
            "great-granddaughter",
            "great-grandchild",
            target_sex,
        )
        if greats == 1:
            return base
        return f"{greats}x {base}"

    # Priority 4: sibling (MUST come before uncle/aunt check)
    if gen_p == 1 and gen_t == 1:
        return _sex_term("brother", "sister", "sibling", target_sex)

    # Priority 5: uncle/aunt (gen_t == 1, gen_p >= 2)
    if gen_t == 1:
        base = _sex_term("uncle", "aunt", "uncle/aunt", target_sex)
        if gen_p == 2:
            return base
        greats = gen_p - 2
        if greats == 1:
            return f"great-{base}"
        return f"{greats}x great-{base}"

    # Priority 6: nephew/niece (gen_p == 1, gen_t >= 2)
    if gen_p == 1:
        base = _sex_term("nephew", "niece", "nephew/niece", target_sex)
        if gen_t == 2:
            return base
        greats = gen_t - 2
        if greats == 1:
            return f"great-{base}"
        return f"{greats}x great-{base}"

    # Priority 7: cousin
    if gen_p < 2 or gen_t < 2:
        raise ValueError(
            f"Unexpected generation pair ({gen_p}, {gen_t}) " "reached cousin branch"
        )
    degree = min(gen_p, gen_t) - 1
    removed = abs(gen_p - gen_t)
    label = f"{_ordinal(degree)} cousin"
    if removed > 0:
        label = f"{label} {_removed_label(removed)}"
    return label


def build_description(
    target_name: str,
    primary_name: str,
    base_type: str,
    is_half: bool,
    show_half: bool,
) -> str:
    """Build the relationship sentence.

    show_half corresponds to --type all (True) vs --type blood (False).
    """
    if base_type == "same individual":
        return f"{target_name} and {primary_name} are the same individual."

    # Apply half-prefix if needed
    display_type = base_type
    if show_half and is_half:
        display_type = f"half-{base_type}"

    # Direct-line relationships use "the" (unique by definition)
    # Siblings, uncles, nephews, cousins use "a"/"an" (multiples possible)
    direct_line_keywords = (
        "father",
        "mother",
        "parent",
        "grandfather",
        "grandmother",
        "grandparent",
        "great-grandfather",
        "great-grandmother",
        "great-grandparent",
        "son",
        "daughter",
        "child",
        "grandson",
        "granddaughter",
        "grandchild",
        "great-grandson",
        "great-granddaughter",
        "great-grandchild",
    )

    # Check if the base type (without half-prefix) is a direct-line type
    is_direct = any(base_type.endswith(kw) for kw in direct_line_keywords)

    if is_direct:
        return f"{target_name} is the {display_type} of {primary_name}."

    # a/an: check first letter of final display_type string
    article = "an" if display_type[0].lower() in "aeiou" else "a"
    return f"{target_name} is {article} {display_type} of {primary_name}."
