from __future__ import annotations

import ast
import inspect
from collections.abc import Container, Mapping
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from gedcom_tools import cli

# Commands whose run() has no `except Exception` at all, so a BrokenPipeError
# already travels untouched up to cli._run_command.
#
# Neither has any `except` in run() at all now - the write-then-chmod pairs that
# used to carry an `except OSError` were replaced by utils.write_output_securely,
# which returns a message instead of swallowing. So the exemption rests on the
# simplest possible ground: nothing in either run() catches anything.
EXEMPT = frozenset({"convert", "filter"})

# Known limit: this rule reasons about `except Exception` handlers only. An
# `except OSError` swallows BrokenPipeError just as effectively. The three
# chmod-guarding ones this comment used to list are gone, absorbed into
# utils.write_output_securely; what remains in the command modules is
# languages.py:515 (a tuple catch around detect_encoding, downgrading to a
# warning) and two in compare/__init__.py. compare:122 narrows a samefile()
# probe, and compare:134 deliberately swallows a failed write to stderr - the
# verdict there is returned either way, which is the point: an earlier version
# wrapped the `return` in that same try, so a dead stderr silently skipped it
# and compare went on to compare a file with itself. Deciding this
# automatically would mean reasoning about what each try body encloses, which
# is not worth the machinery; reviewing a new `except OSError` by hand is.


class RunAnalysis(NamedTuple):
    # Line numbers rather than counts: a failure message that points at the
    # offending try is worth more than one that says "3 problems".
    generic_tries: list[int]
    unguarded: list[int]
    unreported: list[int]


class Audit(NamedTuple):
    # "<command>:<line>" entries, so a failure names both the command and the
    # try that broke the rule.
    missing_generic: list[str]
    unguarded: list[str]
    unreported: list[str]


def _is_generic(handler: ast.ExceptHandler) -> bool:
    """Does this handler catch bare Exception, alone or inside a tuple?"""
    node = handler.type
    if isinstance(node, ast.Name):
        return node.id == "Exception"
    if isinstance(node, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id == "Exception" for elt in node.elts
        )
    return False


def _is_broken_pipe_reraise(handler: ast.ExceptHandler) -> bool:
    if not isinstance(handler.type, ast.Name) or handler.type.id != "BrokenPipeError":
        return False
    # A bare `raise` and nothing else. `except BrokenPipeError: pass` reads the
    # same from a distance and does the opposite.
    return (
        len(handler.body) == 1
        and isinstance(handler.body[0], ast.Raise)
        and handler.body[0].exc is None
    )


def _calls_report_error(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "report_error":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "report_error":
            return True
    return False


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no top-level {name}() in the parsed module")


def _generic_tries(func: ast.FunctionDef) -> list[ast.Try]:
    """Every try in func - nested ones included - that catches bare Exception."""
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Try) and any(_is_generic(h) for h in node.handlers)
    ]


def analyse(func: ast.FunctionDef) -> RunAnalysis:
    """Locate every generic handler in func and judge how it is guarded."""
    generic_tries: list[int] = []
    unguarded: list[int] = []
    unreported: list[int] = []

    for node in _generic_tries(func):
        first_generic = next(i for i, h in enumerate(node.handlers) if _is_generic(h))

        generic_tries.append(node.lineno)
        # Precedes, not immediately precedes: inserting a typed handler between
        # the two is legitimate and must not fail this.
        if not any(_is_broken_pipe_reraise(h) for h in node.handlers[:first_generic]):
            unguarded.append(node.lineno)
        if not _calls_report_error(node.handlers[first_generic]):
            unreported.append(node.handlers[first_generic].lineno)

    return RunAnalysis(generic_tries, unguarded, unreported)


def _parse(module: ModuleType) -> ast.Module:
    source = inspect.getsourcefile(module)
    assert source is not None, f"{module.__name__} has no source file"
    return ast.parse(Path(source).read_bytes(), filename=source)


def _analyse_run(module: ModuleType) -> RunAnalysis:
    return analyse(_find_function(_parse(module), "run"))


def test_the_handler_map_covers_every_registered_subcommand() -> None:
    # The rule is only as broad as _HANDLERS, so a command that registers a
    # subparser but never lands in the map would go unchecked forever.
    # Read off create_parser() rather than argparse's private action list.
    registered = {
        call.func.value.id
        for call in ast.walk(_find_function(_parse(cli), "create_parser"))
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "register_subcommand"
        and isinstance(call.func.value, ast.Name)
    }
    assert registered == {
        mod.__name__.rpartition(".")[2] for mod in cli._HANDLERS.values()
    }


def audit(handlers: Mapping[str, ModuleType], exempt: Container[str]) -> Audit:
    """Apply the contract to a whole command map."""
    verdict = Audit([], [], [])
    for name, module in sorted(handlers.items()):
        if name in exempt:
            continue
        found = _analyse_run(module)
        if not found.generic_tries:
            # Not a pass. A command with no generic handler belongs in the
            # exempt set with a written reason, so the next reader can see it
            # was a decision rather than an oversight.
            verdict.missing_generic.append(name)
        verdict.unguarded.extend(f"{name}:{line}" for line in found.unguarded)
        verdict.unreported.extend(f"{name}:{line}" for line in found.unreported)
    return verdict


def test_every_command_either_reraises_broken_pipe_or_is_exempt() -> None:
    missing_generic, unguarded, _ = audit(cli._HANDLERS, EXEMPT)

    assert not missing_generic, (
        "run() has no `except Exception`, so it neither needs nor documents the "
        f"BrokenPipeError guard - add it to EXEMPT with a reason: {missing_generic}"
    )
    assert not unguarded, (
        "every `except Exception` in a command's run() must be preceded by "
        "`except BrokenPipeError: raise`, or `... | head` reports a closed pipe "
        f"as a failure: {unguarded}"
    )


def test_exempt_commands_still_have_no_generic_handler() -> None:
    # Self-invalidating exemption. Let convert or filter grow an
    # `except Exception` and the checks above would skip it forever.
    grown = [
        name
        for name in sorted(EXEMPT)
        if _analyse_run(cli._HANDLERS[name]).generic_tries
    ]
    assert not grown, (
        "these commands gained an `except Exception` and are no longer exempt - "
        f"guard them and drop them from EXEMPT: {grown}"
    )


def test_exempt_set_names_real_commands() -> None:
    assert EXEMPT <= set(cli._HANDLERS)


def test_generic_handlers_report_through_report_error() -> None:
    unreported = list(audit(cli._HANDLERS, EXEMPT).unreported)

    # cli._run_command is the tenth site and is not reachable through
    # _HANDLERS, so it gets named explicitly.
    dispatch = analyse(_find_function(_parse(cli), "_run_command"))
    assert dispatch.generic_tries
    unreported.extend(f"cli._run_command:{line}" for line in dispatch.unreported)

    assert not unreported, (
        "unexpected exceptions must go through utils.report_error so every "
        f"command fails in the same format: {unreported}"
    )


def test_cli_dispatch_catches_broken_pipe_before_its_generic_handler() -> None:
    # _run_command is the end of the chain, not a link in it: it turns the
    # commands' re-raise into a clean exit instead of passing it on. So the
    # ordering is what matters here, not the re-raise the rule looks for.
    #
    # The arms catch OSError, not BrokenPipeError: a closed pipe on Windows
    # arrives as OSError(EINVAL), which BrokenPipeError misses entirely - that
    # was CI run 30835357508, exit 120 on both Windows legs.
    #
    # They are nested inside the generic try rather than siblings of it. As
    # siblings, the `raise` that rejects a non-pipe errno would skip the
    # generic handler and escape as an unhandled traceback; nesting is what
    # routes it to report_error. So the ordering this asserts is containment.
    fn = _find_function(_parse(cli), "_run_command")
    generic = _generic_tries(fn)
    assert len(generic) == 1
    pipe_arms = [
        h
        for node in ast.walk(generic[0])
        for h in (node.handlers if isinstance(node, ast.Try) else [])
        if isinstance(h.type, ast.Name) and h.type.id == "OSError"
    ]
    assert pipe_arms, "the pipe-shaped handlers must sit inside the generic try"


def test_cli_dispatch_pipe_arms_are_errno_gated() -> None:
    """Every `except OSError` in _run_command must consult `_reader_gone`.

    A bare `except OSError` here is the failure mode this guards. The outer
    arm returns EXIT_SUCCESS, so unguarded it reports a PermissionError as a
    clean run; the inner one would swallow ENOSPC and call a truncated file a
    successful write. Both were caught in review before they shipped.
    """
    fn = _find_function(_parse(cli), "_run_command")
    arms = [
        h
        for node in ast.walk(fn)
        if isinstance(node, ast.Try)
        for h in node.handlers
        if isinstance(h.type, ast.Name) and h.type.id == "OSError"
    ]
    assert arms, "expected the pipe-shaped handlers to catch OSError"
    for arm in arms:
        called = {
            n.func.id
            for n in ast.walk(arm)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_reader_gone" in called, (
            "an `except OSError` in _run_command that does not consult "
            "_reader_gone swallows every I/O failure, not just a closed pipe"
        )


# --- the rule, checked against sources written to break it -----------------


def _analyse_source(source: str) -> RunAnalysis:
    return analyse(_find_function(ast.parse(source), "run"))


def _fake_command(tmp_path: Path, name: str, source: str) -> ModuleType:
    """Import `source` as a throwaway command module, off sys.modules."""
    import importlib.util

    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_flags_a_command_with_no_generic_handler(tmp_path: Path) -> None:
    # The clause that mutation-testing proves: dropping both guards must not
    # buy a command a silent pass.
    module = _fake_command(
        tmp_path,
        "naked",
        "def run(args):\n    try:\n        return 0\n    finally:\n        pass\n",
    )
    assert audit({"naked": module}, frozenset()) == Audit(["naked"], [], [])


def test_audit_skips_exempted_commands(tmp_path: Path) -> None:
    module = _fake_command(tmp_path, "spared", "def run(args):\n    return 0\n")
    assert audit({"spared": module}, {"spared"}) == Audit([], [], [])


def test_audit_names_the_command_and_the_line(tmp_path: Path) -> None:
    module = _fake_command(
        tmp_path, "leaky", GUARDED.replace("BrokenPipeError", "OSError")
    )
    found = audit({"leaky": module}, frozenset())
    assert found.missing_generic == []
    assert found.unguarded == ["leaky:3"]
    assert found.unreported == []


GUARDED = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        raise
    except Exception as e:
        report_error(e)
        return 1
"""


def test_guarded_run_is_clean() -> None:
    found = _analyse_source(GUARDED)
    assert found.generic_tries and not found.unguarded and not found.unreported


def test_guard_after_the_generic_handler_is_flagged() -> None:
    source = """
def run(args):
    try:
        return work()
    except Exception as e:
        report_error(e)
        return 1
    except BrokenPipeError:
        raise
"""
    assert _analyse_source(source).unguarded == [3]


def test_a_typed_handler_may_come_first() -> None:
    # Ordering among the typed handlers is the author's business; the guard
    # only has to land somewhere ahead of the generic one.
    source = """
def run(args):
    try:
        return work()
    except ValueError:
        return 2
    except BrokenPipeError:
        raise
    except Exception as e:
        report_error(e)
        return 1
"""
    assert _analyse_source(source).unguarded == []


def test_a_typed_handler_may_sit_between_the_guard_and_the_generic_one() -> None:
    source = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        raise
    except ValueError as e:
        return 2
    except Exception as e:
        report_error(e)
        return 1
"""
    assert _analyse_source(source).unguarded == []


def test_a_second_generic_try_must_be_guarded_too() -> None:
    source = """
def run(args):
    try:
        setup()
    except BrokenPipeError:
        raise
    except Exception as e:
        report_error(e)
    try:
        return work()
    except Exception as e:
        report_error(e)
        return 1
"""
    found = _analyse_source(source)
    assert found.generic_tries == [3, 9]
    assert found.unguarded == [9]


def test_a_nested_generic_try_is_seen() -> None:
    source = """
def run(args):
    try:
        with open(args.file) as fh:
            try:
                return work(fh)
            except Exception:
                return 1
    except BrokenPipeError:
        raise
    except Exception as e:
        report_error(e)
        return 1
"""
    found = _analyse_source(source)
    assert found.unguarded == [5]


def test_no_generic_handler_reports_nothing_to_check() -> None:
    source = """
def run(args):
    try:
        return work()
    except OSError:
        return 1
"""
    assert _analyse_source(source) == RunAnalysis([], [], [])


def test_exception_inside_a_tuple_counts_as_generic() -> None:
    source = """
def run(args):
    try:
        return work()
    except (KeyboardInterrupt, Exception) as e:
        report_error(e)
        return 1
"""
    assert _analyse_source(source).unguarded == [3]


def test_a_non_name_handler_type_is_not_generic() -> None:
    source = """
def run(args):
    try:
        return work()
    except errors.Anything:
        return 1
"""
    assert _analyse_source(source).generic_tries == []


def test_a_bare_except_is_not_treated_as_generic() -> None:
    # `except:` also catches BrokenPipeError, but it is banned by ruff (E722)
    # and no command has one; the rule deliberately does not model it.
    source = """
def run(args):
    try:
        return work()
    except:
        return 1
"""
    assert _analyse_source(source).generic_tries == []


def test_swallowing_broken_pipe_does_not_count_as_a_guard() -> None:
    source = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        pass
    except Exception as e:
        report_error(e)
        return 1
"""
    assert _analyse_source(source).unguarded == [3]


def test_reraising_a_different_error_does_not_count_as_a_guard() -> None:
    source = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        raise SystemExit(1)
    except Exception as e:
        report_error(e)
        return 1
"""
    assert _analyse_source(source).unguarded == [3]


def test_a_guard_with_extra_statements_does_not_count() -> None:
    source = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        cleanup()
        raise
    except Exception as e:
        report_error(e)
        return 1
"""
    assert _analyse_source(source).unguarded == [3]


def test_a_generic_handler_that_never_reports_is_flagged() -> None:
    source = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        raise
    except Exception:
        print("oops")
        return 1
"""
    found = _analyse_source(source)
    assert found.unguarded == []
    assert found.unreported == [7]


def test_a_qualified_report_error_call_counts() -> None:
    source = """
def run(args):
    try:
        return work()
    except BrokenPipeError:
        raise
    except Exception as e:
        utils.report_error(e)
        return 1
"""
    assert _analyse_source(source).unreported == []


def test_a_missing_run_is_an_assertion_not_a_silent_skip() -> None:
    with pytest.raises(AssertionError, match="no top-level run"):
        _analyse_source("def main(args):\n    pass\n")


def test_a_run_nested_inside_a_class_does_not_satisfy_the_lookup() -> None:
    source = "class Command:\n    def run(self, args):\n        pass\n"
    with pytest.raises(AssertionError):
        _analyse_source(source)


def test_parse_reads_the_module_on_disk() -> None:
    tree = _parse(cli)
    assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} >= {
        "main",
        "_run_command",
    }
