"""Shared utility functions and data models."""

from __future__ import annotations

import errno
import io
import os
import re
import stat
import sys
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

# BinaryFileCR is absent from ged4py.parser.__all__ but is what GedcomReader
# itself wraps every file in -- see _declared_charset for why we need it too.
from ged4py.parser import (  # type: ignore[attr-defined]
    BinaryFileCR,
    GedcomReader,
    guess_codec,
)

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


def _lookup_text_codec(name: str) -> str | None:
    """Canonical codec name for `name`, or None if it is not a text codec.

    ``codecs.lookup`` also resolves the byte-to-byte transforms -- base64, hex,
    zlib, rot13 and friends. Those sail straight through a bare lookup and then
    detonate hundreds of lines later inside the decode with "'base64' is not a
    text encoding", which tells a user who typed ``--from base64`` nothing they
    can act on. Rejecting them here routes them into the caller's own "unknown
    encoding" message instead.

    Probing ``info.decode(b"", ...)`` does not work as a test: base64 and hex
    decode empty input happily (returning bytes, not str), while zlib and
    rot13 raise things that are not LookupError. ``_is_text_encoding`` is the
    private flag CPython itself consults to raise that LookupError, so it is
    the exact predicate we want. The ``True`` default keeps an exotic
    ``CodecInfo`` that lacks the attribute working rather than rejecting a
    perfectly good codec -- notably ``gedcom``, the ANSEL codec everything
    here depends on.
    """
    import codecs

    try:
        info = codecs.lookup(name)
    except LookupError:
        return None
    if not getattr(info, "_is_text_encoding", True):
        return None
    return info.name


def resolve_source_codec(encoding_info: EncodingInfo, from_override: str | None) -> str:
    """Resolve the source codec name from encoding info or user override."""
    if from_override is not None:
        key = from_override.lower()
        if key in GEDCOM_CHARSETS:
            return GEDCOM_CHARSETS[key]
        resolved = _lookup_text_codec(from_override)
        if resolved is not None:
            return resolved
        msg = f"Unknown source encoding: {from_override}"
        raise ValueError(msg)

    enc = encoding_info.encoding
    if enc in SOURCE_ENCODING_MAP:
        return SOURCE_ENCODING_MAP[enc]
    key = enc.lower()
    if key in GEDCOM_CHARSETS:
        return GEDCOM_CHARSETS[key]
    resolved = _lookup_text_codec(enc)
    if resolved is not None:
        return resolved
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

    This runs before any work starts so a doomed run fails fast with a useful
    message. It is not the security boundary: the path can change underneath
    us between here and the write. `write_output_securely` is what actually
    decides whether the bytes land.
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


SYMLINK_OUTPUT_ERROR = "Output path is a symlink; refusing to follow it."


def write_output_securely(
    path: Path,
    data: str | bytes,
    *,
    force: bool,
    encoding: str = "utf-8",
) -> str | None:
    """Write `data` to `path` through a single create-or-fail open.

    Returns an error message for the caller to print, or None on success.
    `encoding` applies to str data only; bytes go out untouched.

    One `os.open` does the work that a `write_bytes` + `chmod` pair used to:
    the file is created 0600 (never briefly world-readable), symlinks are
    refused instead of followed, and there is no window between deciding the
    path is safe and writing to it.

    Platform split: O_NOFOLLOW and the creation mode are POSIX-only. On
    Windows both flags are absent, so the open is still atomically
    create-or-fail but symlinks are followed and the mode is ignored — the
    same concession the `sys.platform != "win32"` chmod guard already made.
    """
    target_mode: int | None
    try:
        target_mode = os.lstat(path).st_mode
    except OSError:
        # Nothing there yet (or the parent is unreadable): let the atomic open
        # below decide. A propagating FileNotFoundError here would break every
        # ordinary "create a new file" write.
        target_mode = None

    if target_mode is not None and (
        stat.S_ISCHR(target_mode) or stat.S_ISFIFO(target_mode)
    ):
        # /dev/null and named pipes: nothing to create, nothing to truncate,
        # and no mode worth setting. Write them the plain way.
        #
        # lstat, not stat: stat() follows symlinks, so a link aimed at a FIFO
        # or a device would look identical to the real thing and get written
        # through — exactly what the symlink guard below exists to stop.
        # Anything else, links included, falls through to O_NOFOLLOW.
        if isinstance(data, str):
            path.write_text(data, encoding=encoding, newline="")
        else:
            path.write_bytes(data)
        return None

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)  # POSIX only; absent on Windows
        | getattr(os, "O_BINARY", 0)  # Windows only; keeps the CRT out of it
        | (os.O_TRUNC if force else os.O_EXCL)
    )

    try:
        fd = os.open(path, flags, 0o600)
    except OSError as e:
        # O_NOFOLLOW gives ELOOP on a live symlink; O_EXCL gives EEXIST on a
        # dangling one, which is why islink is checked too. Either way the
        # answer is not "use --force" — that path is refused as well.
        if e.errno == errno.ELOOP or path.is_symlink():
            return f"Error: {SYMLINK_OUTPUT_ERROR}"
        if path.is_dir():
            # Checked before FileExistsError: a directory also raises EEXIST
            # under O_EXCL, and "use --force" would be false advice — with
            # --force the open raises EISDIR instead.
            return f"Error: {path} is a directory. Give a file path instead."
        if isinstance(e, FileExistsError):
            return f"Error: {path} already exists. Use --force to overwrite."
        raise

    if force:
        # O_TRUNC reuses the existing file's mode, so an overwrite of a
        # world-readable file would stay world-readable. fchmod acts on the
        # open descriptor, so no path lookup and nothing to race.
        with suppress(OSError, AttributeError):
            os.fchmod(fd, 0o600)

    if isinstance(data, str):
        # newline="" is load-bearing: the default rewrites every \n as
        # os.linesep, which on Windows turns csv.writer's own \r\n into \r\r\n.
        # O_BINARY only silences the CRT; Python's translation is its own layer.
        with os.fdopen(fd, "w", encoding=encoding, newline="") as text_out:
            text_out.write(data)
    else:
        with os.fdopen(fd, "wb") as byte_out:
            byte_out.write(data)

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


# Real GEDCOM headers are a few hundred bytes. The window only needs to be big
# enough that _declared_charset's reconciliation fallback stays a rarity.
_CHAR_SCAN_WINDOW = 65536


def _scan_declared_charset(
    stream: io.BufferedReader, bom_size: int
) -> tuple[str | None, bool]:
    """Find the raw `1 CHAR` value by scanning bytes, never decoding the body.

    Returns the charset and whether the caller must reconcile against the
    unbounded reader because the CHAR line may lie past the window.
    """
    stream.seek(bom_size)
    chunk = stream.read(_CHAR_SCAN_WINDOW)
    lines = re.split(b"\r\n|\r|\n", chunk)

    window_full = len(chunk) == _CHAR_SCAN_WINDOW
    if window_full:
        # The last element is a partial line. Keeping it matches a straddling
        # "1 CHAR ANSEL" as "ANS" and hands back a silently wrong encoding.
        lines.pop()

    declared: str | None = None
    found_head_end = False
    for raw in lines:
        parts = raw.strip().split()
        if len(parts) >= 2 and parts[0] == b"0" and parts[1] != b"HEAD":
            found_head_end = True
            break
        if len(parts) >= 3 and parts[0] == b"1" and parts[1] == b"CHAR":
            # Charset names are ASCII, so decode only the value. Decoding the
            # whole buffer raises UnicodeDecodeError on a multi-byte character
            # straddling the cut, and on `1 CHAR ASCII` with a latin-1 body byte.
            declared = b" ".join(parts[2:]).decode("ascii", errors="replace")
            break

    return declared, declared is None and window_full and not found_head_end


def _declared_charset_via_reader(file_path: Path) -> str | None:
    """Fallback: let ged4py lex the file. Slow, but it reads without a bound."""
    with GedcomReader(str(file_path)) as reader:
        if reader.header:
            char_rec = reader.header.sub_tag("CHAR")
            if char_rec and char_rec.value:
                return str(char_rec.value)
    return None


def _declared_charset(file_path: Path) -> str | None:
    """Read the `1 CHAR` value, preferring a bounded read over a full lex.

    `guess_codec` is the same function GedcomReader uses, so every alias table,
    tokenisation rule and raise path is preserved by construction -- but it stops
    at the end of the header instead of indexing the whole file.

    BinaryFileCR is load-bearing: a plain file handle makes guess_codec raise
    OSError on CR-only files, which would send every one of them to the fallback.
    """
    try:
        with BinaryFileCR(io.FileIO(str(file_path))) as stream:
            _codec, bom_size = guess_codec(stream, require_char=False, warn=False)
            declared, needs_reconcile = _scan_declared_charset(stream, bom_size)
    except (OSError, UnicodeDecodeError):
        # Truncated or otherwise malformed header. UnicodeDecodeError is a
        # ValueError, not an OSError -- guess_codec documents it as a raise path.
        return _declared_charset_via_reader(file_path)

    if needs_reconcile:
        # The window ran out mid-header. Returning None here would downgrade an
        # ANSEL file to the UTF-8 default; the reader is the only thing that can
        # still find the CHAR line.
        return _declared_charset_via_reader(file_path)
    return declared


def detect_encoding(file_path: Path) -> EncodingInfo:
    """Detect GEDCOM file encoding from BOM and CHAR header."""
    has_bom = False

    with open(file_path, "rb") as f:
        bom = f.read(3)
        if bom.startswith(b"\xef\xbb\xbf"):
            has_bom = True
        elif bom[:2] in (b"\xff\xfe", b"\xfe\xff"):
            has_bom = True

    declared_charset = _declared_charset(file_path)

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
