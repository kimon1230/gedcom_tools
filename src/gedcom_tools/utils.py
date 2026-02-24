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


def count_sources_recursive(record: Record, _visited: set[int] | None = None) -> int:
    # visited-set guards against circular refs in malformed GEDCOM
    if _visited is None:
        _visited = set()

    record_id = id(record)
    if record_id in _visited:
        return 0
    _visited.add(record_id)

    count = 0
    for sub in record.sub_records:
        if sub.tag == "SOUR":
            count += 1
        count += count_sources_recursive(sub, _visited)
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
