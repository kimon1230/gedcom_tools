"""GEDCOM date parsing and precision classification."""

from __future__ import annotations

import re

# ged4py DateValueTypes - import once at module level for performance
try:
    from ged4py.date import DateValueTypes

    HAS_DATE_VALUE_TYPES = True
except ImportError:
    DateValueTypes = None  # type: ignore[misc, assignment]
    HAS_DATE_VALUE_TYPES = False


# Month name to number mapping
MONTH_TO_NUM: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

# Compiled regex for month extraction - faster than iterating dict
MONTH_PATTERN = re.compile(
    r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.IGNORECASE
)

# Prefixes indicating approximate dates
APPROX_PREFIXES = (
    "ABT",
    "EST",
    "CAL",
    "BEF",
    "AFT",
    "BET",
    "FROM",
    "TO",
    "INT",
    "CIRCA",
    "C.",  # Non-standard but common
)


def is_phrase_date(date_val: object) -> bool:
    # PHRASE dates have NO .date/.date1/.date2 — must check before accessing them
    if not HAS_DATE_VALUE_TYPES:
        return False
    return hasattr(date_val, "kind") and date_val.kind == DateValueTypes.PHRASE


def get_century(year: int) -> str:
    """Get century string from year (e.g., 1850 -> '1800')."""
    return str((year // 100) * 100)


def extract_year_from_date(date_val: object) -> int | None:
    """Extract year from a ged4py date value, with regex fallback."""
    if date_val is None:
        return None

    # PHRASE type has NO attributes - check first
    if is_phrase_date(date_val):
        return None

    # TODO: remove this once ged4py exposes .year directly on DateValue
    if hasattr(date_val, "year") and date_val.year:
        try:
            return int(date_val.year)
        except (ValueError, TypeError):
            pass

    # ged4py Simple, About, Before, After - year is at .date.year
    if hasattr(date_val, "date") and date_val.date:
        year = getattr(date_val.date, "year", None)
        if year is not None:
            try:
                return int(year)
            except (ValueError, TypeError):
                pass

    # ged4py Range, Period - year is at .date1.year (first date in range)
    if hasattr(date_val, "date1") and date_val.date1:
        year = getattr(date_val.date1, "year", None)
        if year is not None:
            try:
                return int(year)
            except (ValueError, TypeError):
                pass

    # Fallback to regex extraction from string representation
    date_str = str(date_val)
    match = re.search(r"\b(\d{4})\b", date_str)
    if match:
        return int(match.group(1))

    return None


def extract_month(date_val: object) -> int | None:
    # ged4py month values are STRING enums ("OCT", "JAN"), not ints
    if date_val is None:
        return None

    # PHRASE type has NO attributes - check first
    if is_phrase_date(date_val):
        return None

    # ged4py Simple/About/Before/After - month is at .date.month as a STRING
    if hasattr(date_val, "date") and date_val.date:
        month_str = getattr(date_val.date, "month", None)
        if month_str:
            return MONTH_TO_NUM.get(str(month_str).upper())

    # ged4py Range/Period - use .date1
    if hasattr(date_val, "date1") and date_val.date1:
        month_str = getattr(date_val.date1, "month", None)
        if month_str:
            return MONTH_TO_NUM.get(str(month_str).upper())

    # Fallback: use compiled regex (faster than iterating dict)
    date_str = str(date_val)
    match = MONTH_PATTERN.search(date_str)
    if match:
        return MONTH_TO_NUM[match.group(1).upper()]

    return None


def classify_date_precision(date_val: object) -> tuple[str, bool]:
    """Classify into (category, has_full_components).

    Category is "full", "partial", "approximate", or "missing".
    has_full_components is True when day+month+year are all present.
    """
    # ged4py date types: Simple/About/Before/After have .date,
    # Range/Period have .date1/.date2, Phrase has none of these.
    if date_val is None:
        return ("missing", False)

    # PHRASE type has NO attributes - check first
    if is_phrase_date(date_val):
        return ("missing", False)

    is_approximate = False
    has_day = False
    has_month = False
    has_year = False

    # Handle ged4py DateValue objects
    if HAS_DATE_VALUE_TYPES and hasattr(date_val, "kind"):
        kind = date_val.kind

        # Check if approximate/uncertain type
        if kind in (
            DateValueTypes.ABOUT,
            DateValueTypes.ESTIMATED,
            DateValueTypes.CALCULATED,
            DateValueTypes.BEFORE,
            DateValueTypes.AFTER,
            DateValueTypes.RANGE,
            DateValueTypes.PERIOD,
            DateValueTypes.INTERPRETED,
            DateValueTypes.FROM,
            DateValueTypes.TO,
        ):
            is_approximate = True

        # Get date components from .date or .date1
        cal_date = None
        if hasattr(date_val, "date") and date_val.date:
            cal_date = date_val.date
        elif hasattr(date_val, "date1") and date_val.date1:
            cal_date = date_val.date1

        if cal_date:
            has_year = cal_date.year is not None
            has_month = cal_date.month is not None
            has_day = getattr(cal_date, "day", None) is not None

    # Fallback/additional string parsing if we don't have year info yet
    if not has_year:
        date_str = str(date_val).strip().upper()
        if not date_str:
            return ("missing", False)

        # Check for approximate prefixes
        for prefix in APPROX_PREFIXES:
            if date_str.startswith(prefix):
                is_approximate = True
                break

        # Parse components
        parts = date_str.split()
        has_year = any(p.isdigit() and len(p) == 4 for p in parts)
        has_month = any(p[:3] in MONTH_TO_NUM for p in parts if len(p) >= 3)

        for p in parts:
            if p.isdigit() and len(p) <= 2:
                try:
                    day = int(p)
                    if 1 <= day <= 31:
                        has_day = True
                        break
                except ValueError:
                    pass

    if not has_year:
        return ("missing", False)

    has_full = has_day and has_month and has_year

    if is_approximate:
        return ("approximate", has_full)
    elif has_full:
        return ("full", True)
    else:
        return ("partial", False)
