"""Shared utility functions and data models."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ged4py.parser import GedcomReader

from gedcom_tools.constants import EXIT_ERROR, EXIT_USAGE_ERROR

if TYPE_CHECKING:
    from ged4py.model import Record


@dataclass
class EncodingInfo:
    """Information about the detected encoding of a GEDCOM file."""

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
    """Detect GEDCOM file encoding from BOM and CHAR header.

    Checks for UTF-8, UTF-16-LE, and UTF-16-BE byte-order marks,
    then reads the CHAR header via GedcomReader.

    Raises:
        CodecError: If the file cannot be decoded.
        ParserError: If the file contains malformed GEDCOM lines.
        IntegrityError: If the file has structural issues.
    """
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
    """Extract xref ID from a value (string or ged4py pointer)."""
    if value is None:
        return None

    val_str = str(value)
    if val_str.startswith("@") and val_str.endswith("@"):
        return val_str

    if hasattr(value, "xref_id"):
        xref_id: str | None = value.xref_id
        return xref_id

    return None


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
    """Count all SOUR references in a record and all sub-records recursively.

    Uses visited-set tracking to protect against circular references in
    malformed GEDCOM data.
    """
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
