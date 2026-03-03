from __future__ import annotations

_CODES = {
    c: d
    for d, chars in enumerate(
        ["AEIOU", "BFPV", "CGJKQSXZ", "DT", "L", "MN", "R"], start=0
    )
    for c in chars
}


def soundex(name: str) -> str:
    """American Soundex encoding of a name."""
    alpha = [c for c in name.upper() if c.isalpha()]
    if not alpha:
        return ""
    first = alpha[0]
    digits: list[str] = []
    prev = _CODES.get(first, -1)
    for ch in alpha[1:]:
        code = _CODES.get(ch, -1)
        if code > 0 and code != prev:
            digits.append(str(code))
        if code > 0:
            prev = code
        elif code == 0:
            # vowels separate identical consonant codes
            prev = -1
        # H, W, Y (code == -1): transparent, don't change prev
    return (first + "".join(digits))[:4].ljust(4, "0")


def double_metaphone(name: str) -> tuple[str, str]:
    """Double Metaphone encoding. Returns (primary, secondary)."""
    import unicodedata

    nfd = unicodedata.normalize("NFD", name.upper())
    alpha = "".join(c for c in nfd if c.isascii() and c.isalpha())
    if not alpha:
        return ("", "")
    from doublemetaphone import doublemetaphone as _dm  # type: ignore[import-untyped]

    result = _dm(alpha)
    return (result[0] or "", result[1] or "")


def phonetic_encode(name: str, algorithm: str = "soundex") -> tuple[str, str]:
    """Dispatch to selected algorithm. Returns (primary, secondary).

    Secondary is always "" for soundex.
    """
    if algorithm == "metaphone":
        return double_metaphone(name)
    if algorithm == "soundex":
        return (soundex(name), "")
    raise ValueError(f"Unknown phonetic algorithm: {algorithm!r}")


def phonetic_codes_match(
    a_primary: str,
    a_alt: str,
    b_primary: str,
    b_alt: str,
) -> bool:
    """True if any non-empty code from a overlaps with any from b."""
    return (bool(a_primary) and (a_primary == b_primary or a_primary == b_alt)) or (
        bool(a_alt) and (a_alt == b_primary or a_alt == b_alt)
    )
