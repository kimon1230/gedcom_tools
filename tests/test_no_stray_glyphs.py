from __future__ import annotations

import ast
from collections.abc import Container
from pathlib import Path
from typing import NamedTuple

# Anchored on the working tree rather than gedcom_tools.__file__ - under a
# non-editable install the latter points at site-packages, and the guard would
# silently validate a copy nobody is editing.
SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "gedcom_tools"

# Keys are posix paths relative to SRC_ROOT. Literals are written as escapes on
# purpose: several are invisible, and \u2500 vs \u2014 are indistinguishable
# when rendered.
ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        # The ASCII/Unicode toggle itself - these are the definition of the
        # thing this test protects, so they cannot route through glyphs().
        ("progress.py", "\u2713"),
        ("progress.py", "\u2717"),
        ("progress.py", "\u2192"),
        ("progress.py", "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"),
        ("progress.py", "\u2194"),
        ("progress.py", "\u2500"),
        ("progress.py", "\u00d7"),
        ("progress.py", "\u2014"),
        # Message content, rendered in both text and JSON. A display-only flag
        # must never change machine-readable output.
        ("validation/semantic.py", " \u2192 "),
        # BOM. Data, not decoration.
        ("commands/export/formatters.py", "\ufeff"),
        # Bidi control characters, stripped during sanitisation.
        (
            "utils.py",
            "\u200e\u200f\u061c\u202a\u202b\u202c\u202d\u202e"
            "\u2066\u2067\u2068\u2069\u2028\u2029",
        ),
    }
)


class Violation(NamedTuple):
    module: str
    line: int
    literal: str


def _docstring_nodes(tree: ast.AST) -> list[ast.Constant]:
    """Collect the Constant node of every docstring position in the tree."""
    found: list[ast.Constant] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.append(first.value)
    return found


def _scan_source(
    source: bytes, module_key: str, allow: Container[tuple[str, str]]
) -> list[Violation]:
    # Parsing bytes lets ast honour any encoding declaration in the file.
    # read_text() without an explicit encoding uses the locale codec, which
    # blows up on progress.py under the Windows CI legs.
    tree = ast.parse(source, filename=module_key)
    docstrings = _docstring_nodes(tree)

    violations: list[Violation] = []
    # ast.walk descends into JoinedStr, so f-string segments are covered here
    # without any special casing. Comments never reach the AST at all.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        # Constant also carries int/float/bytes/None/Ellipsis, none of which
        # have .isascii().
        if not isinstance(node.value, str) or node.value.isascii():
            continue
        if any(node is doc for doc in docstrings):
            continue
        if (module_key, node.value) in allow:
            continue
        violations.append(Violation(module_key, node.lineno, node.value))
    return violations


def test_no_stray_non_ascii_literals_in_src() -> None:
    assert SRC_ROOT.is_dir()

    violations: list[Violation] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        key = path.relative_to(SRC_ROOT).as_posix()
        violations.extend(_scan_source(path.read_bytes(), key, ALLOWED))

    detail = "\n".join(f"  {v.module}:{v.line}: {v.literal!r}" for v in violations)
    assert not violations, (
        "Non-ASCII literals must route through progress.glyphs() so --ascii "
        f"can switch them:\n{detail}"
    )


def test_bare_non_ascii_literal_is_flagged() -> None:
    found = _scan_source(b'SEP = "\\u2500"\n', "mod.py", frozenset())
    assert found == [Violation("mod.py", 1, "\u2500")]


def test_non_ascii_inside_fstring_is_flagged() -> None:
    found = _scan_source(b'x = f"{a}\\u2194{b}"\n', "mod.py", frozenset())
    assert [(v.line, v.literal) for v in found] == [(1, "\u2194")]


def test_docstring_glyph_is_exempt() -> None:
    assert (
        _scan_source(b'"""Convert \\u2014 in place."""\n', "mod.py", frozenset()) == []
    )


def test_allowlisted_pair_is_exempt() -> None:
    allow = {("mod.py", "\u2192")}
    assert _scan_source(b'ARROW = "\\u2192"\n', "mod.py", allow) == []
    # Same literal, different module: still a violation.
    assert _scan_source(b'ARROW = "\\u2192"\n', "other.py", allow)


def test_non_string_constants_are_ignored() -> None:
    source = b"COUNT = 3\nRATIO = 1.5\nBLOB = b'\\xff'\nNOTHING = None\nANY = ...\n"
    assert _scan_source(source, "mod.py", frozenset()) == []
