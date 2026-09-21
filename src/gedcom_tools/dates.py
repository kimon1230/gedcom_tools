"""GEDCOM date parsing and precision classification."""

from __future__ import annotations

import datetime
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
    r"\b(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?"
    r"|AUG(?:UST)?|SEP(?:T|TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)\b",
    re.IGNORECASE,
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


def phrase_text(date_val: object) -> str:
    # A bare "2 DATE" line parses to a DateValuePhrase whose .phrase is None,
    # and it still passes the callers' `value is None` guard.
    phrase = getattr(date_val, "phrase", None)
    return str(phrase) if phrase else ""


# Four-digit runs below this are reference numbers, not years
MIN_PLAUSIBLE_YEAR = 1000

# A GEDCOM line caps at 255 bytes; anything longer is a CONC-padded blob
MAX_DATE_TEXT = 255

_DATE_TOKEN_RE = re.compile(r"[^\s/\-.,]+")
_YEAR_TOKEN_RE = re.compile(r"\d{4}")
# Matches a day or a numeric month - "12/2/1882" has both
_SMALL_NUMBER_RE = re.compile(r"\d{1,2}")


def is_clean_date_phrase(text: str, current_year: int | None = None) -> bool:
    """True when every token is a date component and the years look usable.

    "30 November 1989", "12/2/1882" and the range "1801-1875" qualify;
    "Census 1900 record" does not. Two years are allowed because a bare range
    is the commonest phrase shape in real files, and with no free text around
    them the upper bound is a real one. Three or more is a list, not a range.

    This is not date validation - "32 JAN 1900" passes. It decides whether a
    year recovered from free text is trustworthy enough to make a decision on,
    since the first four digits of a note are as often an archive reference as
    a birth year.
    """
    # ged4py concatenates CONC continuations into one value with no cap, so
    # this text is unbounded. Tokenizing it allocates ~12x its length, and
    # nothing longer than a GEDCOM line is a date anyway.
    if not text or len(text) > MAX_DATE_TEXT:
        return False

    tokens = _DATE_TOKEN_RE.findall(text)
    if not tokens:
        return False

    # One year of slack absorbs clock skew and timezone-edge files
    base = datetime.date.today().year if current_year is None else current_year
    max_year = base + 1
    year_count = 0
    small_count = 0
    for token in tokens:
        if _YEAR_TOKEN_RE.fullmatch(token):
            if not MIN_PLAUSIBLE_YEAR <= int(token) <= max_year:
                return False
            year_count += 1
        elif _SMALL_NUMBER_RE.fullmatch(token):
            small_count += 1
        elif not MONTH_PATTERN.fullmatch(token):
            return False
    if not 1 <= year_count <= 2:
        return False
    # At most a day and a numeric month per year, which rejects digit runs like
    # "1 1 1 1 1850". It does NOT reject a citation shaped exactly like a date -
    # "12.1823.4" has the same token profile as "12/2/1882" and is accepted.
    # Closing that needs positional rules the real-date forms cannot satisfy.
    return small_count <= 2 * year_count


def plausible_years(text: str, current_year: int | None = None) -> list[int]:
    """Four-digit runs in free text that could plausibly be a year, in text order.

    The first run in a note is as often an archive reference, a regiment or a
    page number as a year. Filtering the candidates - rather than bounding
    whichever one was picked - keeps "ref 6789 b. 1850" reporting 1850 instead
    of discarding the record entirely.

    Free text only. A structured date's year is whatever the file says, and
    bounding it here would null legitimate pre-1000 years that ged4py parsed
    correctly.
    """
    base = datetime.date.today().year if current_year is None else current_year
    max_year = base + 1
    return [
        int(run)
        for run in re.findall(r"\b\d{4}\b", text)
        if MIN_PLAUSIBLE_YEAR <= int(run) <= max_year
    ]


# Only these calendars use years in the range MIN_PLAUSIBLE_YEAR..now. Hebrew
# years run ~5786 and French Republican ~230, so bounding those would reject
# every legitimate non-Gregorian date.
_BOUNDED_CALENDARS = ("GregorianDate", "JulianDate")


def _is_trustworthy(
    date_val: object,
    current_year: int | None = None,
    *,
    allow_phrase: bool,
    year_floor: int,
) -> bool:
    """Whether this date value's year is safe to make a decision on.

    The two callers need different answers, so the policy is a parameter:

    - liveness (export redaction) rejects free text outright and keeps
      MIN_PLAUSIBLE_YEAR. A citation shaped exactly like a date - "12.1823.4"
      has the same token profile as "12/2/1882" - would otherwise read as a
      birth year and publish someone the file never said was dead.
    - validation (chronology checks) accepts a clean phrase, because
      "12/2/1882" is a date a human reads without difficulty and it produces a
      correct E011 today; and it drops the 1000 floor, which was written for
      free text and has no business rejecting a spec-conformant "1 JAN 0950".
    """
    if is_phrase_date(date_val):
        if not allow_phrase:
            return False
        return is_clean_date_phrase(phrase_text(date_val), current_year)

    base = datetime.date.today().year if current_year is None else current_year
    max_year = base + 1

    # A structured kind is NOT proof of a date. ged4py validates neither the
    # month token nor the year, so "Reg 1823" parses as a SIMPLE date whose
    # month is "REG", and "3/1990" is read as the dual year 3 - which ages the
    # person past any lifespan and silently un-redacts them.
    # date2 is included because it is the bound the liveness reader consumes.
    for attr in ("date", "date1", "date2"):
        cal_date = getattr(date_val, attr, None)
        if cal_date is None:
            continue

        month = getattr(cal_date, "month", None)
        if month and getattr(cal_date, "month_num", None) is None:
            # month_num is set for Hebrew/French-Republican months too, so this
            # only reaches junk; MONTH_TO_NUM still admits ged4py's "JUNE".
            if MONTH_TO_NUM.get(str(month).upper()[:3]) is None:
                return False

        year = getattr(cal_date, "year", None)

        # "3/1990" is a dual-year mis-parse: ged4py reads year 3, dual 1990.
        # A real dual date spans one year boundary ("1750/51" -> 1750/1751),
        # so the gap is the discriminator. The floor used to catch this by
        # accident; validation drops the floor, so it has to be explicit.
        dual_year = getattr(cal_date, "dual_year", None)
        if year is not None and dual_year is not None:
            if int(dual_year) - int(year) != 1:
                return False

        if year is not None and type(cal_date).__name__ in _BOUNDED_CALENDARS:
            if not year_floor <= int(year) <= max_year:
                return False
    return True


def extract_year_for_validation(
    date_val: object, current_year: int | None = None
) -> int | None:
    """Year for the chronology checks (E011/E012/W020-W023).

    Accepts a clean phrase - "12/2/1882" is a readable date that yields a
    correct E011 - and applies no MIN_PLAUSIBLE_YEAR floor, so a 10th-century
    record is still checked.
    """
    if not _is_trustworthy(date_val, current_year, allow_phrase=True, year_floor=1):
        return None
    return extract_year_from_date(date_val)


def extract_year_latest_for_liveness(
    date_val: object, current_year: int | None = None
) -> int | None:
    """Upper bound of the birth year, for the --redact-living decision.

    Rejects free text: a year recovered from a note cannot be told apart from
    an archive citation, and acting on a wrong one publishes a living person.
    Unknown means living, so returning None here redacts.
    """
    if not _is_trustworthy(
        date_val, current_year, allow_phrase=False, year_floor=MIN_PLAUSIBLE_YEAR
    ):
        return None
    return extract_year_latest_from_date(date_val)


def get_century(year: int) -> str:
    """Get century string from year (e.g., 1850 -> '1800')."""
    return str((year // 100) * 100)


def extract_year_from_date(date_val: object) -> int | None:
    """Extract year from a ged4py date value, with regex fallback."""
    if date_val is None:
        return None

    # PHRASE has no .date/.date1/.year - recover the year from its free text.
    # First plausible candidate, not the first run: "ref 6789 b. 1850" is 1850.
    if is_phrase_date(date_val):
        years = plausible_years(phrase_text(date_val))
        return years[0] if years else None

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


def extract_year_latest_from_date(date_val: object) -> int | None:
    """Extract the latest year a date value can refer to.

    Ranges and periods ("BET 1900 AND 1995") carry two bounds and
    extract_year_from_date deliberately returns the lower one, since that is
    what gets reported as the birth year. For a phrase it returns the first
    year in the text rather than the lowest; this function returns the largest
    in either case. Liveness estimation needs the upper
    bound instead — assuming the earliest bound would age people into the grave.
    Anything with a single date resolves identically in both functions.
    """
    if date_val is None:
        return None

    # Word order in free text is not chronological, so take the largest year
    # rather than the last one. default= keeps a year-less phrase from raising.
    if is_phrase_date(date_val):
        return max(plausible_years(phrase_text(date_val)), default=None)

    # Raw strings never reach the structured branches below, and the shared
    # regex fallback takes the FIRST year it finds, so handle them here.
    if isinstance(date_val, str):
        years = re.findall(r"\b\d{4}\b", date_val)
        return int(years[-1]) if years else None

    # ged4py Range, Period - the upper bound is the LARGER of the two, not
    # whichever ged4py stored second. "BET 2010 AND 1823" is reversed in the
    # file, and reading 1823 as the upper bound ages a living person out.
    bounds = []
    for attr in ("date1", "date2"):
        year = getattr(getattr(date_val, attr, None), "year", None)
        if year is not None:
            try:
                bounds.append(int(year))
            except (ValueError, TypeError):
                pass
    if bounds:
        return max(bounds)

    return extract_year_from_date(date_val)


def extract_month(date_val: object) -> int | None:
    # ged4py month values are STRING enums ("OCT", "JAN"), not ints
    if date_val is None:
        return None

    if is_phrase_date(date_val):
        match = MONTH_PATTERN.search(phrase_text(date_val))
        return MONTH_TO_NUM[match.group(1).upper()[:3]] if match else None

    # ged4py Simple/About/Before/After - month is at .date.month as a STRING
    if hasattr(date_val, "date") and date_val.date:
        month_str = getattr(date_val.date, "month", None)
        if month_str:
            return MONTH_TO_NUM.get(str(month_str).upper()[:3])

    # ged4py Range/Period - use .date1
    if hasattr(date_val, "date1") and date_val.date1:
        month_str = getattr(date_val.date1, "month", None)
        if month_str:
            return MONTH_TO_NUM.get(str(month_str).upper()[:3])

    # Fallback: use compiled regex (faster than iterating dict)
    date_str = str(date_val)
    match = MONTH_PATTERN.search(date_str)
    if match:
        return MONTH_TO_NUM[match.group(1).upper()[:3]]

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
        raw = phrase_text(date_val) if is_phrase_date(date_val) else str(date_val)
        if len(raw) > MAX_DATE_TEXT:
            return ("missing", False)
        date_str = raw.strip().upper()
        if not date_str:
            return ("missing", False)

        parts = date_str.split()

        # Anchor on the first token: free text like "Tombstone erected 1901"
        # otherwise reads as approximate via the "TO" prefix.
        if parts and parts[0] in APPROX_PREFIXES:
            is_approximate = True

        # Regex, not a token scan - "12/2/1882" is a single non-isdigit token,
        # and a bare prefix test matches MAYBE, MARried, DECeased.
        # Same bound as the extractors: otherwise "vol 6789 p. 4" reports a
        # null year while the precision beside it claims "partial".
        has_year = bool(plausible_years(date_str))
        has_month = bool(MONTH_PATTERN.search(date_str))

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
