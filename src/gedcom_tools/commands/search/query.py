from __future__ import annotations

import re
import shlex

from gedcom_tools.commands.search.models import SearchQuery, SearchTerm

VALID_FIELDS = frozenset(
    {
        "name",
        "given",
        "surname",
        "born",
        "died",
        "place",
        "sex",
        "ancestor",
        "descendant",
    }
)
NAME_FIELDS = frozenset({"name", "given", "surname"})
DATE_FIELDS = frozenset({"born", "died"})
XREF_FIELDS = frozenset({"ancestor", "descendant"})
OPERATORS = frozenset({":", "=", "~"})

_SINGLE_YEAR_RE = re.compile(r"^\d{1,4}$")
_DATE_RANGE_RE = re.compile(r"^\d{1,4}-\d{1,4}$")
_NESTED_QUANTIFIER_RE = re.compile(r"([+*?}])\s*\)\s*[+*?{]")
_QUANTIFIED_INNER_RE = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*?{]")
_OVERLAPPING_ALT_RE = re.compile(r"\(([^)]*\|[^)]*)\)\s*[+*?{]")
_MAX_REGEX_LENGTH = 256
_MAX_NESTING_DEPTH = 3
_XREF_RE = re.compile(r"^@[A-Za-z0-9_]+@$")


def _tokenize(query_string: str) -> list[str]:
    lexer = shlex.shlex(query_string, posix=True)
    lexer.whitespace_split = True
    lexer.quotes = '"'
    # Don't treat backslash as escape inside unquoted tokens — users type
    # literal backslashes in regex patterns like \bSmith\b
    lexer.escape = ""
    return list(lexer)


def _split_field_operator_value(token: str) -> tuple[str, str, str]:
    """Split a token into (field, operator, value).

    Operator at position 0 means field defaults to "name".
    First operator character found left-to-right wins.
    """
    if not token:
        raise ValueError("Empty token")

    # Operator at position 0: ~Schmidt, :value, =value
    if token[0] in OPERATORS:
        return ("name", token[0], token[1:])

    # Scan for first operator
    for i, ch in enumerate(token):
        if ch in OPERATORS:
            return (token[:i].lower(), ch, token[i + 1 :])

    # No operator found — bare value defaults to name:
    return ("name", ":", token)


def _validate_field(field: str) -> None:
    if field not in VALID_FIELDS:
        valid = ", ".join(sorted(VALID_FIELDS))
        raise ValueError(f"Unknown field '{field}'. Valid fields: {valid}")


def _validate_operator_field(field: str, operator: str) -> None:
    if operator != "~":
        return
    if field in DATE_FIELDS:
        raise ValueError(
            f"Phonetic matching (~) is not supported for date fields. "
            f"Use {field}:YYYY or {field}:YYYY-YYYY"
        )
    if field not in NAME_FIELDS:
        raise ValueError(
            "Phonetic matching (~) is only supported for name fields "
            "(name, given, surname)"
        )


def _parse_date_range(value: str, field: str, operator: str) -> tuple[int, int] | None:
    """Parse date value into a (start, end) range, or None for non-date fields."""
    if field not in DATE_FIELDS:
        return None

    if _DATE_RANGE_RE.match(value):
        if operator == "=":
            raise ValueError(f"Date ranges require the : operator. Use {field}:{value}")
        parts = value.split("-", 1)
        start, end = int(parts[0]), int(parts[1])
        if start > end:
            raise ValueError(
                f"Invalid date range '{value}': start year ({start}) is after "
                f"end year ({end}). Swap them: {field}:{end}-{start}"
            )
        return (start, end)

    if _SINGLE_YEAR_RE.match(value):
        year = int(value)
        return (year, year)

    raise ValueError(
        f"Invalid date format '{value}'. Use {field}:YYYY for a single year "
        f"or {field}:YYYY-YYYY for a range"
    )


def _validate_sex(value: str) -> None:
    if len(value) > 1:
        raise ValueError(
            f"Sex values in GEDCOM are single characters (M, F, U, X). "
            f"Use sex:{value[0].upper()} instead of sex:{value}"
        )


def _validate_xref(value: str, field: str) -> None:
    if not _XREF_RE.match(value):
        raise ValueError(
            f"Invalid identifier format '{value}'. "
            f"Use the full GEDCOM identifier: {field}:@{value.strip('@')}@"
        )


def _detect_wildcard(value: str, regex_mode: bool, operator: str) -> bool:
    if regex_mode or operator != ":":
        return False
    return "*" in value or "?" in value


def _validate_wildcard(value: str) -> None:
    non_wild = value.replace("*", "").replace("?", "")
    if len(non_wild) < 3:
        raise ValueError(
            f"Wildcard pattern '{value}' is too broad "
            f"\N{EM DASH} add more characters, e.g. 'Sm*th'"
        )


def _count_nesting_depth(value: str) -> int:
    """Count maximum parenthesis nesting depth, ignoring escaped parens."""
    depth = 0
    max_depth = 0
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            i += 2
            continue
        if value[i] == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif value[i] == ")":
            depth = max(0, depth - 1)
        i += 1
    return max_depth


def _validate_regex(value: str) -> None:
    if len(value) > _MAX_REGEX_LENGTH:
        raise ValueError(
            f"Regex pattern is too long ({len(value)} chars, max {_MAX_REGEX_LENGTH}). "
            f"Simplify the pattern"
        )
    if _count_nesting_depth(value) > _MAX_NESTING_DEPTH:
        raise ValueError(
            f"Regex pattern has too many nested groups "
            f"(max {_MAX_NESTING_DEPTH} levels). Simplify the pattern"
        )
    if _NESTED_QUANTIFIER_RE.search(value):
        raise ValueError(
            f"Regex pattern '{value}' contains nested quantifiers which could "
            f"cause slow matching. Simplify the pattern"
        )
    if _QUANTIFIED_INNER_RE.search(value):
        raise ValueError(
            f"Regex pattern '{value}' contains a quantified group with "
            f"quantified subexpressions. Simplify the pattern"
        )
    if _OVERLAPPING_ALT_RE.search(value):
        raise ValueError(
            f"Regex pattern '{value}' contains alternation inside a "
            f"quantified group which could cause slow matching. "
            f"Simplify the pattern"
        )
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(
            f"Invalid regex pattern '{value}': {exc}. "
            f"Check your regex syntax or remove --regex for substring matching"
        ) from None


def _check_tilde_expansion(value: str, operator: str) -> None:
    """Warn if shell expanded ~ into a home directory path."""
    if operator != "~":
        return
    if "/home/" in value or "/Users/" in value:
        raise ValueError(
            f"Value '{value}' looks like a home directory path \N{EM DASH} "
            f"the shell likely expanded ~. Wrap the query in single quotes: "
            f"gedcom-tools search tree.ged 'surname~Schmidt'"
        )


def parse_query(
    query_string: str,
    regex_mode: bool = False,
    fuzzy_dates: int | None = None,
    limit: int | None = None,
    count_only: bool = False,
    phonetic_algo: str = "soundex",
) -> SearchQuery:
    stripped = query_string.strip() if query_string else ""
    if not stripped:
        raise ValueError(
            "No search query provided.\n"
            "Usage: gedcom-tools search <file> '<query>'\n"
            "Examples: 'Smith', 'surname:Schmidt born:1850', 'place:\"New York\"'"
        )

    tokens = _tokenize(stripped)
    terms: list[SearchTerm] = []

    for token in tokens:
        field, operator, value = _split_field_operator_value(token)

        if not value:
            raise ValueError(f"Missing value for field '{field}'")

        _validate_field(field)
        _validate_operator_field(field, operator)
        _check_tilde_expansion(value, operator)

        date_range = _parse_date_range(value, field, operator)

        if field == "sex":
            _validate_sex(value)

        if field in XREF_FIELDS:
            _validate_xref(value, field)

        is_wildcard = _detect_wildcard(value, regex_mode, operator)

        if is_wildcard:
            _validate_wildcard(value)

        if (
            regex_mode
            and operator == ":"
            and field not in DATE_FIELDS
            and field not in XREF_FIELDS
        ):
            _validate_regex(value)

        terms.append(
            SearchTerm(
                field=field,
                operator=operator,
                value=value,
                is_wildcard=is_wildcard,
                date_range=date_range,
            )
        )

    return SearchQuery(
        terms=terms,
        regex_mode=regex_mode,
        fuzzy_dates=fuzzy_dates,
        limit=limit,
        count_only=count_only,
        phonetic_algo=phonetic_algo,
    )
