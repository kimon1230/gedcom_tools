"""Shared utility functions and data models."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ged4py.parser import GedcomReader

from gedcom_tools.constants import EXIT_ERROR, EXIT_USAGE_ERROR

if TYPE_CHECKING:
    from ged4py.model import Record

# --- Shared byte-I/O constants ---

GEDCOM_CHARSETS: dict[str, str] = {
    "utf-8": "utf-8",
    "ansel": "gedcom",
    "ascii": "ascii",
    "unicode": "utf-16-le",
}

SOURCE_ENCODING_MAP: dict[str, str] = {
    "UTF-8": "utf-8",
    "ANSEL": "gedcom",
    "ASCII": "ascii",
    "UNICODE": "utf-16-le",
    "UTF-16-LE": "utf-16-le",
    "UTF-16-BE": "utf-16-be",
}

BOMS: dict[str, bytes] = {
    "utf-8": b"\xef\xbb\xbf",
    "utf-16-le": b"\xff\xfe",
    "utf-16-be": b"\xfe\xff",
}

BOM_ENCODINGS: set[str] = {"utf-8", "utf-16-le", "utf-16-be"}


def strip_bom(data: bytes) -> tuple[bytes, str | None]:
    """Strip BOM from raw bytes, returning data and BOM encoding label."""
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:], "utf-8"
    if data[:2] == b"\xff\xfe":
        return data[2:], "utf-16-le"
    if data[:2] == b"\xfe\xff":
        return data[2:], "utf-16-be"
    return data, None


def resolve_source_codec(encoding_info: EncodingInfo, from_override: str | None) -> str:
    """Resolve the source codec name from encoding info or user override."""
    import codecs

    if from_override is not None:
        key = from_override.lower()
        if key in GEDCOM_CHARSETS:
            return GEDCOM_CHARSETS[key]
        try:
            return codecs.lookup(from_override).name
        except LookupError:
            pass
        msg = f"Unknown source encoding: {from_override}"
        raise ValueError(msg)

    enc = encoding_info.encoding
    if enc in SOURCE_ENCODING_MAP:
        return SOURCE_ENCODING_MAP[enc]
    key = enc.lower()
    if key in GEDCOM_CHARSETS:
        return GEDCOM_CHARSETS[key]
    try:
        return codecs.lookup(enc).name
    except LookupError:
        pass
    msg = f"Cannot determine source encoding from '{enc}'. Use --from to specify."
    raise ValueError(msg)


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_C0_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")
_BIDI_CHARS = frozenset(
    "\u200e\u200f\u061c"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069"
    "\u2028\u2029"
)


def sanitize_error(msg: str) -> str:
    """Strip control characters, ANSI escapes, and bidi overrides from error text."""
    result = _ANSI_ESCAPE_RE.sub("", msg)
    result = _C0_CONTROL_RE.sub("", result)
    return "".join(c for c in result if c not in _BIDI_CHARS)


def report_error(e: Exception) -> None:
    """Print an unexpected exception to stderr in the one house format.

    Every generic ``except Exception`` handler routes through here so the same
    failure reads the same way whichever command hit it. The type name matters:
    a bare ``Error: 'foo'`` from a KeyError tells the user nothing.
    """
    print(f"Error: {type(e).__name__}: {sanitize_error(str(e))}", file=sys.stderr)
    print("Re-run with --verbose for a full traceback.", file=sys.stderr)


def check_output_safety(
    input_path: Path,
    output_path: Path,
    *,
    force: bool,
    dry_run: bool,
    command: str,
) -> str | None:
    """Return error message if output path is unsafe, or None if OK.

    `command` names the caller ("Convert", "Filter") for the error text.

    Note: TOCTOU race between this check and the caller's write.
    Acceptable for a local CLI tool — not practically exploitable.
    """
    parent = output_path.parent
    if not parent.exists():
        return f"Error: Directory {parent} does not exist"

    same_file_error = (
        "Error: Output path resolves to the input file. "
        f"{command} always produces a new file."
    )
    try:
        if os.path.samefile(input_path, output_path):
            return same_file_error
    except OSError:
        # samefile stats both paths, so a missing file lands here too.
        if output_path.resolve() == input_path.resolve():
            return same_file_error

    if not dry_run and output_path.exists() and not force:
        return f"Error: {output_path} already exists. Use --force to overwrite."

    return None


def normalize_display(text: str) -> str:
    """NFC normalization for consistent display across encodings."""
    return unicodedata.normalize("NFC", text) if text else ""


def normalize_compare(text: str) -> str:
    """Full normalization for matching: NFC, strip diacritics, lowercase."""
    if not text:
        return ""
    nfc = unicodedata.normalize("NFC", text)
    nfd = unicodedata.normalize("NFD", nfc)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return stripped.lower()


@dataclass
class EncodingInfo:
    """BOM + CHAR header detection result."""

    encoding: str
    has_bom: bool = False
    declared_charset: str | None = None

    def __str__(self) -> str:
        parts = [self.encoding]
        if self.has_bom:
            parts.append("(with BOM)")
        if (
            self.declared_charset
            and self.declared_charset.lower() != self.encoding.lower()
        ):
            parts.append(f"(declared: {self.declared_charset})")
        return " ".join(parts)


def detect_encoding(file_path: Path) -> EncodingInfo:
    """Detect GEDCOM file encoding from BOM and CHAR header."""
    has_bom = False
    declared_charset = None

    with open(file_path, "rb") as f:
        bom = f.read(3)
        if bom.startswith(b"\xef\xbb\xbf"):
            has_bom = True
        elif bom[:2] in (b"\xff\xfe", b"\xfe\xff"):
            has_bom = True

    with GedcomReader(str(file_path)) as reader:
        if reader.header:
            char_rec = reader.header.sub_tag("CHAR")
            if char_rec and char_rec.value:
                declared_charset = str(char_rec.value)

    detected = "UTF-8"
    if has_bom:
        if bom.startswith(b"\xef\xbb\xbf"):
            detected = "UTF-8"
        elif bom[:2] == b"\xff\xfe":
            detected = "UTF-16-LE"
        elif bom[:2] == b"\xfe\xff":
            detected = "UTF-16-BE"
    elif declared_charset:
        detected = declared_charset.upper()

    return EncodingInfo(
        encoding=detected,
        has_bom=has_bom,
        declared_charset=declared_charset,
    )


def extract_xref(value: Any) -> str | None:
    # HACK: ged4py's pointer type is inconsistent — handle both forms
    if value is None:
        return None

    val_str = str(value)
    if val_str.startswith("@") and val_str.endswith("@"):
        return val_str

    if hasattr(value, "xref_id"):
        xref_id: str | None = value.xref_id
        return xref_id

    return None


_XREF_RE = re.compile(r"@([A-Za-z]*)(\d+)@")


def xref_sort_key(xref: str) -> tuple[str, int, str]:
    """Sort key for GEDCOM XREFs that orders numerically within each prefix.

    "@I2@" < "@I10@" and "@F1@" < "@I1@".
    """
    m = _XREF_RE.match(xref)
    if m:
        return (m.group(1), int(m.group(2)), "")
    return ("", 0, xref)


def validate_input_file(file_path: Path) -> int | None:
    """Validate input file exists and is readable. Returns error code or None."""
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not file_path.is_file():
        print(f"Error: Not a file: {file_path}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not os.access(file_path, os.R_OK):
        print(
            f"Error: Cannot read file (permission denied): {file_path}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    return None


def count_sources_recursive(record: Record) -> int:
    """Count SOUR sub-records iteratively to avoid stack overflow."""
    visited: set[int] = set()
    count = 0
    stack = [record]
    while stack:
        current = stack.pop()
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)
        for sub in current.sub_records:
            if sub.tag == "SOUR":
                count += 1
            stack.append(sub)
    return count


def parse_name_record(name_record: Record | None) -> tuple[str, str]:
    """Parse given name and surname from a ged4py NAME sub-record.

    Handles NAME tuple extraction and GIVN/SURN sub-record overrides.
    Returns (given_name, surname). Callers compose full_name or
    extract first-token as needed.
    """
    if name_record is None:
        return ("", "")

    given = ""
    surname = ""

    val = name_record.value
    if val is not None:
        if isinstance(val, tuple) and len(val) >= 2:
            given = val[0] or ""
            surname = val[1] or ""
        else:
            given = str(val)

    # GIVN/SURN sub-records override tuple values when present
    for sub in name_record.sub_records:
        if sub.tag == "GIVN" and sub.value:
            given = str(sub.value)
        elif sub.tag == "SURN" and sub.value:
            surname = str(sub.value)

    return (given, surname)
