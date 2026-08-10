"""Languages command."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from ged4py.model import Pointer
from ged4py.parser import CodecError, GedcomReader, IntegrityError, ParserError

from gedcom_tools.constants import (
    EXIT_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    FAM_NON_EVENT_TAGS,
    INDI_NON_EVENT_TAGS,
)
from gedcom_tools.language_detect import (
    LANGUAGE_NAMES,
    MIN_TEXT_LENGTH_DEFAULT,
    GedcomLanguageDetector,
)
from gedcom_tools.progress import Colors, PhaseTracker, glyphs
from gedcom_tools.utils import (
    EncodingInfo,
    detect_encoding,
    sanitize_error,
    validate_input_file,
    xref_sort_key,
)

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


class EventMatch(NamedTuple):
    parent_xref: str
    event_tag: str | None
    name: str | None


def _resolve_language(value: str) -> tuple[str, str] | None:
    """Match a language name or ISO code to (display_name, code)."""
    lower = value.lower()
    if lower == "unknown":
        return "Unknown", "unknown"
    if lower in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[lower], lower
    for code, name in LANGUAGE_NAMES.items():
        if name.lower() == lower:
            return name, code
    return None


@dataclass
class LanguageRow:

    language: str
    code: str
    notes: int
    stories: int
    events: int

    @property
    def total(self) -> int:
        return self.notes + self.stories + self.events


@dataclass
class LanguagesResult:

    file_path: str
    encoding_info: EncodingInfo | None
    rows: list[LanguageRow] = field(default_factory=list)
    total_texts: int = 0
    skipped_short: int = 0
    min_length: int = MIN_TEXT_LENGTH_DEFAULT

    # Filter mode fields (empty/None when not filtering)
    language_filter: str | None = None
    language_filter_name: str | None = None
    person_xrefs: list[tuple[str, str]] = field(default_factory=list)
    note_xrefs: list[str] = field(default_factory=list)
    event_matches: list[EventMatch] = field(default_factory=list)

    # Text content for --show-text (populated only when show_text=True)
    person_texts: dict[str, list[str]] = field(default_factory=dict)
    note_texts: dict[str, list[str]] = field(default_factory=dict)
    event_texts: dict[str, list[str]] = field(default_factory=dict)

    @property
    def distinct_languages(self) -> int:
        return sum(1 for r in self.rows if r.code != "unknown")

    def format_text(
        self, colors: Colors, quiet: bool = False, show_text: bool = False
    ) -> str:
        if self.language_filter:
            return self._format_filter_text(colors, quiet, show_text)

        g = glyphs()

        if quiet:
            if self.total_texts == 0 and self.skipped_short == 0:
                return ""
            return (
                f"{self.distinct_languages} language(s) detected "
                f"across {self.total_texts} text(s)"
            )

        lines: list[str] = [f"File: {self.file_path}"]
        if self.encoding_info:
            lines.append(f"Encoding: {self.encoding_info}")
        lines.append("")

        lines.append(f"{colors.cyan}=== Language Detection ==={colors.reset}")

        # Summary line
        if self.skipped_short > 0:
            lines.append(
                f"  Texts analyzed: {self.total_texts}"
                f" ({self.skipped_short} skipped, too short)"
            )
        else:
            lines.append(f"  Texts analyzed: {self.total_texts}")

        # Empty cases
        if self.total_texts == 0:
            if self.skipped_short > 0:
                lines.append("")
                lines.append(
                    f"  All {self.skipped_short} text(s) were below"
                    f" the minimum length ({self.min_length} characters)."
                )
            else:
                lines.append("")
                lines.append("  No text content found in this file.")
            return "\n".join(lines)

        # Table
        lines.append("")
        lines.append("  Language             Notes  Stories  Events   Total")
        lines.append("  " + g.rule * 53)
        for row in self.rows:
            lines.append(
                f"  {row.language:<20} {row.notes:>5}"
                f"  {row.stories:>7}  {row.events:>6}  {row.total:>6}"
            )
        lines.append("  " + g.rule * 53)

        # Totals row
        t_notes = sum(r.notes for r in self.rows)
        t_stories = sum(r.stories for r in self.rows)
        t_events = sum(r.events for r in self.rows)
        lines.append(
            f"  {'Total':<20} {t_notes:>5}"
            f"  {t_stories:>7}  {t_events:>6}  {self.total_texts:>6}"
        )

        lines.append("")
        lines.append(
            f"  Distinct languages: {self.distinct_languages}" " (excluding unknown)"
        )

        lines.append("")
        lines.append(
            f"  {colors.dim}Notes   = standalone top-level notes{colors.reset}"
        )
        lines.append(
            f"  {colors.dim}Stories = biographical notes on individuals{colors.reset}"
        )
        lines.append(
            f"  {colors.dim}Events  = notes on births, deaths,"
            f" marriages, and other events{colors.reset}"
        )
        lines.append(
            f"  {colors.dim}Tip: use --language <name> to list"
            f" individual records in that language.{colors.reset}"
        )

        has_unknown = any(r.code == "unknown" for r in self.rows)
        if has_unknown:
            lines.append("")
            lines.append(
                f"  {colors.dim}Note: short or ambiguous texts may be"
                f" classified as Unknown.{colors.reset}"
            )

        return "\n".join(lines)

    def _format_filter_text(self, colors: Colors, quiet: bool, show_text: bool) -> str:
        g = glyphs()
        display = f"{self.language_filter_name} ({self.language_filter})"
        n_persons = len(self.person_xrefs)
        n_notes = len(self.note_xrefs)
        n_events = len(self.event_matches)
        total = n_persons + n_notes + n_events

        if quiet:
            if total == 0:
                return ""
            parts = []
            parts.append(f"{'1 person' if n_persons == 1 else f'{n_persons} persons'}")
            parts.append(f"{'1 note' if n_notes == 1 else f'{n_notes} notes'}")
            parts.append(f"{'1 event' if n_events == 1 else f'{n_events} events'}")
            return f"{self.language_filter_name}: {', '.join(parts)}"

        lines: list[str] = [f"File: {self.file_path}"]
        if self.encoding_info:
            lines.append(f"Encoding: {self.encoding_info}")
        lines.append("")

        lines.append(f"{colors.cyan}=== {display} ==={colors.reset}")

        # Texts analyzed context line
        if self.skipped_short > 0:
            lines.append(
                f"  Texts analyzed: {self.total_texts}"
                f" ({self.skipped_short} skipped, too short)"
            )
        else:
            lines.append(f"  Texts analyzed: {self.total_texts}")

        # Empty states
        if self.total_texts == 0:
            if self.skipped_short > 0:
                lines.append("")
                lines.append(
                    f"  All {self.skipped_short} text(s) were below"
                    f" the minimum length ({self.min_length} characters)."
                )
            else:
                lines.append("")
                lines.append("  No text content found in this file.")
            return "\n".join(lines)

        if total == 0:
            lines.append("")
            lines.append(f"  No matches found for {display}.")
            return "\n".join(lines)

        # Person matches
        if n_persons > 0:
            lines.append("")
            lines.append(f"  Persons with biographical notes ({n_persons}):")
            for xref, name in self.person_xrefs:
                if name:
                    lines.append(f"    {name} ({xref})")
                else:
                    lines.append(f"    ({xref})")
                if show_text:
                    for txt in self.person_texts.get(xref, []):
                        collapsed = " ".join(txt.split())
                        lines.append(f"      {collapsed}")

        # Note matches
        if n_notes > 0:
            lines.append("")
            lines.append(f"  Standalone notes ({n_notes}):")
            for xref in self.note_xrefs:
                lines.append(f"    {xref}")
                if show_text:
                    for txt in self.note_texts.get(xref, []):
                        collapsed = " ".join(txt.split())
                        lines.append(f"      {collapsed}")

        # Event matches
        if n_events > 0:
            lines.append("")
            lines.append(f"  Events with notes ({n_events}):")
            for em in self.event_matches:
                if em.event_tag is None:
                    label = f"    {em.parent_xref}  (family note)"
                elif em.name:
                    label = f"    {em.parent_xref}  {em.event_tag}  {g.dash} {em.name}"
                else:
                    label = f"    {em.parent_xref}  {em.event_tag}"
                lines.append(label)
                if show_text:
                    key = f"{em.parent_xref}:{em.event_tag or ''}"
                    for txt in self.event_texts.get(key, []):
                        collapsed = " ".join(txt.split())
                        lines.append(f"      {collapsed}")

        lines.append("")
        return "\n".join(lines)

    def format_json(self, show_text: bool = False) -> str:
        if self.language_filter:
            return self._format_filter_json(show_text)

        from pathlib import Path as _Path

        data: dict[str, Any] = {
            "file": self.file_path,
            "filename": _Path(self.file_path).name,
            "mode": "aggregate",
            "encoding": None,
            "languages": [
                {
                    "language": r.language,
                    "code": r.code,
                    "notes": r.notes,
                    "stories": r.stories,
                    "events": r.events,
                    "total": r.total,
                }
                for r in self.rows
            ],
            "summary": {
                "total_texts": self.total_texts,
                "skipped_short": self.skipped_short,
                "distinct_languages": self.distinct_languages,
                "min_length": self.min_length,
            },
            "categories": {
                "notes": "Standalone top-level notes",
                "stories": "Biographical notes on individuals",
                "events": "Notes on births, deaths, marriages, and other events",
            },
            "disclaimer": (
                "Short or ambiguous texts may be classified as Unknown."
                " Language detection is less reliable on texts shorter"
                " than ~30 characters."
            ),
        }

        if self.encoding_info:
            data["encoding"] = {
                "detected": self.encoding_info.encoding,
                "has_bom": self.encoding_info.has_bom,
                "declared": self.encoding_info.declared_charset,
            }

        return json.dumps(data, indent=2)

    def _format_filter_json(self, show_text: bool) -> str:
        n_persons = len(self.person_xrefs)
        n_notes = len(self.note_xrefs)
        n_events = len(self.event_matches)

        persons = []
        for x, n in self.person_xrefs:
            obj: dict[str, Any] = {"xref": x, "name": n}
            if show_text:
                obj["texts"] = self.person_texts.get(x, [])
            persons.append(obj)

        notes = []
        for x in self.note_xrefs:
            obj = {"xref": x}
            if show_text:
                obj["texts"] = self.note_texts.get(x, [])
            notes.append(obj)

        events = []
        for e in self.event_matches:
            obj = {
                "parent_xref": e.parent_xref,
                "event_tag": e.event_tag,
                "name": e.name,
            }
            if show_text:
                key = f"{e.parent_xref}:{e.event_tag or ''}"
                obj["texts"] = self.event_texts.get(key, [])
            events.append(obj)

        from pathlib import Path as _Path

        data: dict[str, Any] = {
            "file": self.file_path,
            "filename": _Path(self.file_path).name,
            "mode": "filter",
            "encoding": None,
            "language": self.language_filter_name,
            "code": self.language_filter,
            "persons": persons,
            "notes": notes,
            "events": events,
            "summary": {
                "person_count": n_persons,
                "note_count": n_notes,
                "event_count": n_events,
                "total_matches": n_persons + n_notes + n_events,
                "total_texts": self.total_texts,
                "skipped_short": self.skipped_short,
                "min_length": self.min_length,
            },
        }

        if self.encoding_info:
            data["encoding"] = {
                "detected": self.encoding_info.encoding,
                "has_bom": self.encoding_info.has_bom,
                "declared": self.encoding_info.declared_charset,
            }

        return json.dumps(data, indent=2)


class LanguagesCollector:

    def __init__(
        self,
        file_path: Path,
        min_length: int = MIN_TEXT_LENGTH_DEFAULT,
        quiet: bool = False,
        verbose: bool = False,
        no_color: bool = False,
        language_filter: str | None = None,
        show_text: bool = False,
    ) -> None:
        self.file_path = file_path
        self.min_length = min_length
        self.quiet = quiet
        self.verbose = verbose
        self.no_color = no_color
        self.detector: GedcomLanguageDetector | None = None
        self.lang_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"notes": 0, "stories": 0, "events": 0}
        )
        self.total_texts = 0
        self.skipped_short = 0
        self._detection_cache: dict[str, tuple[str, bool]] = {}

        # Filter mode tracking
        self._language_filter: str | None = language_filter
        self._person_xrefs: set[str] = set()
        self._indi_names: dict[str, str] = {}
        self._note_xrefs: set[str] = set()
        self._event_matches: set[tuple[str, str | None]] = set()

        # Text tracking (only when --show-text is active)
        self._show_text = show_text
        self._person_texts: dict[str, list[str]] = defaultdict(list)
        self._note_texts: dict[str, list[str]] = defaultdict(list)
        self._event_texts: dict[str, list[str]] = defaultdict(list)

    def _detect_and_count(
        self,
        text: str | None,
        category: str,
        xref: str | None = None,
        *,
        parent_xref: str | None = None,
        event_tag: str | None = None,
    ) -> None:
        # Detect language and bump the counter for the given category
        if not text or not text.strip():
            return
        # A mypy narrowing guard, not a runtime check. Converting it to a raise
        # would change behaviour to satisfy a linter.
        assert (  # noqa: S101
            self.detector is not None
        ), "_detect_and_count called before collect()"

        if xref and xref in self._detection_cache:
            lang, was_skipped = self._detection_cache[xref]
        else:
            lang, was_skipped = self.detector.detect(text)
            if xref:
                self._detection_cache[xref] = (lang, was_skipped)

        if was_skipped:
            self.skipped_short += 1
            return
        self.total_texts += 1
        self.lang_counts[lang][category] += 1

        # Track matches for filter mode
        if self._language_filter and lang == self._language_filter:
            if category == "stories" and parent_xref:
                self._person_xrefs.add(parent_xref)
                if self._show_text:
                    self._person_texts[parent_xref].append(text)
            elif category == "events" and parent_xref:
                self._event_matches.add((parent_xref, event_tag))
                if self._show_text:
                    key = f"{parent_xref}:{event_tag or ''}"
                    self._event_texts[key].append(text)
            elif category == "notes" and xref:
                self._note_xrefs.add(xref)
                if self._show_text:
                    self._note_texts[xref].append(text)

    def _get_note_text(
        self, sub: Any, note_lookup: dict[str, str]
    ) -> tuple[str | None, str | None]:
        """Extract text and optional xref from a NOTE sub-record.

        Returns (text, xref) — xref is set only for pointer notes.
        """
        if isinstance(sub, Pointer):
            xref = str(sub.value)
            return note_lookup.get(xref), xref
        if sub.value is None:
            return None, None
        val = str(sub.value)
        return (val if val.strip() else None), None

    def collect(self) -> LanguagesResult:
        tracker = PhaseTracker(
            total_phases=5,
            stream=sys.stderr,
            no_color=self.no_color,
            quiet=self.quiet,
            verbose=self.verbose,
        )

        encoding_info: EncodingInfo | None = None

        with tracker.phase("Detecting encoding"):
            try:
                encoding_info = detect_encoding(self.file_path)
            except (CodecError, ParserError, IntegrityError, OSError) as e:
                if not self.quiet:
                    # Byte-identical to the stats site; sanitized for the same
                    # reason -- the exception text is attacker-influenced.
                    print(
                        "Warning: Could not detect encoding: "
                        f"{sanitize_error(str(e))}",
                        file=sys.stderr,
                    )
                encoding_info = EncodingInfo(encoding="Unknown")

        with tracker.phase("Loading language model"):
            self.detector = GedcomLanguageDetector(
                min_length=self.min_length, stream=sys.stderr
            )

        # Pre-pass: build NOTE xref lookup
        note_lookup: dict[str, str] = {}
        referenced_xrefs: set[str] = set()

        # One reader serves both passes — ged4py's index is lazy and seekable,
        # so repeated records0() calls reuse it instead of re-scanning the file.
        with GedcomReader(str(self.file_path)) as reader:
            with tracker.phase("Building note index"):
                for rec in reader.records0("NOTE"):
                    if rec.xref_id and rec.value:
                        note_lookup[rec.xref_id] = str(rec.value)

            # Main pass: iterate INDI and FAM records
            with tracker.phase("Analyzing text content"):
                for rec in reader.records0("INDI"):
                    # Extract person name for filter mode
                    if self._language_filter and rec.xref_id:
                        indi_name = ""
                        name_rec = rec.sub_tag("NAME")
                        if name_rec and name_rec.value:
                            val = name_rec.value
                            if isinstance(val, tuple):
                                indi_name = " ".join(p for p in val if p).strip()
                            else:
                                indi_name = str(val).replace("/", "").strip()
                        self._indi_names[rec.xref_id] = indi_name

                    for sub in rec.sub_records:
                        if sub.tag == "NOTE":
                            text, ptr_xref = self._get_note_text(sub, note_lookup)
                            if ptr_xref:
                                referenced_xrefs.add(ptr_xref)
                            self._detect_and_count(
                                text,
                                "stories",
                                xref=ptr_xref,
                                parent_xref=rec.xref_id,
                            )
                        elif sub.tag not in INDI_NON_EVENT_TAGS:
                            for subsub in sub.sub_records:
                                if subsub.tag == "NOTE":
                                    text, ptr_xref = self._get_note_text(
                                        subsub, note_lookup
                                    )
                                    if ptr_xref:
                                        referenced_xrefs.add(ptr_xref)
                                    self._detect_and_count(
                                        text,
                                        "events",
                                        xref=ptr_xref,
                                        parent_xref=rec.xref_id,
                                        event_tag=sub.tag,
                                    )

                for rec in reader.records0("FAM"):
                    for sub in rec.sub_records:
                        if sub.tag == "NOTE":
                            text, ptr_xref = self._get_note_text(sub, note_lookup)
                            if ptr_xref:
                                referenced_xrefs.add(ptr_xref)
                            self._detect_and_count(
                                text,
                                "events",
                                xref=ptr_xref,
                                parent_xref=rec.xref_id,
                            )
                        elif sub.tag not in FAM_NON_EVENT_TAGS:
                            for subsub in sub.sub_records:
                                if subsub.tag == "NOTE":
                                    text, ptr_xref = self._get_note_text(
                                        subsub, note_lookup
                                    )
                                    if ptr_xref:
                                        referenced_xrefs.add(ptr_xref)
                                    self._detect_and_count(
                                        text,
                                        "events",
                                        xref=ptr_xref,
                                        parent_xref=rec.xref_id,
                                        event_tag=sub.tag,
                                    )

        # Post-pass: classify unreferenced top-level notes
        with tracker.phase("Classifying unreferenced notes"):
            for xref, text in note_lookup.items():
                if xref not in referenced_xrefs:
                    self._detect_and_count(text, "notes", xref=xref)

        return self._build_result(encoding_info)

    def _build_result(self, encoding_info: EncodingInfo | None) -> LanguagesResult:
        result = LanguagesResult(
            file_path=str(self.file_path),
            encoding_info=encoding_info,
            total_texts=self.total_texts,
            skipped_short=self.skipped_short,
            min_length=self.min_length,
        )

        if self._language_filter:
            result.language_filter = self._language_filter
            result.language_filter_name = LANGUAGE_NAMES.get(
                self._language_filter, "Unknown"
            )
            result.person_xrefs = sorted(
                [(x, self._indi_names.get(x, "")) for x in self._person_xrefs],
                key=lambda t: xref_sort_key(t[0]),
            )
            result.note_xrefs = sorted(self._note_xrefs, key=xref_sort_key)
            result.event_matches = sorted(
                [
                    EventMatch(px, et, self._indi_names.get(px))
                    for px, et in self._event_matches
                ],
                key=lambda t: (xref_sort_key(t[0]), t[1] or ""),
            )
            if self._show_text:
                result.person_texts = dict(self._person_texts)
                result.note_texts = dict(self._note_texts)
                result.event_texts = dict(self._event_texts)
        else:
            rows: list[LanguageRow] = []
            for code, counts in self.lang_counts.items():
                name = LANGUAGE_NAMES.get(
                    code, code.title() if code != "unknown" else "Unknown"
                )
                rows.append(
                    LanguageRow(
                        language=name,
                        code=code,
                        notes=counts["notes"],
                        stories=counts["stories"],
                        events=counts["events"],
                    )
                )
            rows.sort(key=lambda r: r.total, reverse=True)
            result.rows = rows

        return result


def register_subcommand(
    subparsers: _SubParsersAction[argparse.ArgumentParser],
) -> None:
    # FIXME: --min-length should probably be a global option shared with stats
    parser = subparsers.add_parser(
        "languages",
        help="Detect languages used in notes and event descriptions",
        description=(
            "Scan all text content (notes, stories, event descriptions)"
            " in a GEDCOM file and report a breakdown by language."
            " Analyzes notes and event descriptions;"
            " citation notes under SOUR records are excluded."
        ),
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the GEDCOM file to analyze",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=MIN_TEXT_LENGTH_DEFAULT,
        help=(
            f"Minimum text length for detection (default: {MIN_TEXT_LENGTH_DEFAULT})."
            " Shorter texts are skipped as unreliable."
        ),
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help=(
            "Show records in a specific language (name or ISO 639-1 code)."
            ' Use "--language unknown" for unclassifiable texts.'
        ),
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        default=False,
        help=(
            "Show the detected text for each match (requires --language)."
            " Useful for auditing language detection accuracy."
        ),
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file
    output_format = getattr(args, "format", "text")
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    no_color = getattr(args, "no_color", False)
    min_length = getattr(args, "min_length", MIN_TEXT_LENGTH_DEFAULT)
    language_arg = getattr(args, "language", None)
    show_text = getattr(args, "show_text", False)

    # Argument validation before file validation
    if show_text and not language_arg:
        print("--show-text requires --language", file=sys.stderr)
        return EXIT_USAGE_ERROR

    language_filter = None
    if language_arg:
        resolved = _resolve_language(language_arg)
        if not resolved:
            supported = sorted(LANGUAGE_NAMES.values())
            print(f"Unknown language: {language_arg!r}", file=sys.stderr)
            print("Supported languages:", file=sys.stderr)
            for i in range(0, len(supported), 5):
                chunk = ", ".join(supported[i : i + 5])
                print(f"  {chunk}", file=sys.stderr)
            print(
                'Also accepts ISO 639-1 codes (en, el, de, ...) or "unknown"',
                file=sys.stderr,
            )
            return EXIT_USAGE_ERROR
        language_filter = resolved[1]

    if err := validate_input_file(file_path):
        return err

    try:
        collector = LanguagesCollector(
            file_path,
            language_filter=language_filter,
            show_text=show_text,
            min_length=min_length,
            quiet=quiet,
            verbose=verbose,
            no_color=no_color,
        )
        result = collector.collect()

        if output_format == "json":
            print(result.format_json(show_text=show_text))
        else:
            colors = Colors(sys.stdout, force_disable=no_color)
            output = result.format_text(colors, quiet=quiet, show_text=show_text)
            if output:
                print(output)

        return EXIT_SUCCESS

    except BrokenPipeError:
        # cli._run_command turns this into a clean exit; catching it in the
        # generic handler below would report a closed pipe as a failure.
        raise
    except Exception as e:
        if verbose:
            raise
        from gedcom_tools.utils import report_error

        report_error(e)
        return EXIT_ERROR
