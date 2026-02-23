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
