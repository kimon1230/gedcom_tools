"""Stats data collection from GEDCOM files."""

from __future__ import annotations

import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ged4py.model import Pointer
from ged4py.parser import CodecError, GedcomReader, IntegrityError, ParserError

from gedcom_tools.commands.stats.formatters import StatsResult
from gedcom_tools.commands.stats.models import (
    AggregateStats,
    CoverageStats,
    DatePrecisionStats,
    FamilyData,
    FamilyEntry,
    GenderedAggregateStats,
    GenerationEntry,
    IndividualData,
    LifespanStats,
    MarriageStats,
    RankedItem,
    TimelineEntry,
)
from gedcom_tools.constants import (
    FAM_NON_EVENT_TAGS,
    INDI_NON_EVENT_TAGS,
    MAX_FIRST_CHILD_AGE,
    MAX_LIFESPAN,
    MAX_MARRIAGE_AGE,
    MAX_NOTE_BUFFER_BYTES,
    MAX_SPOUSAL_AGE_GAP,
    MIN_MARRIAGE_AGE,
    MIN_PARENT_AGE,
)
from gedcom_tools.dates import (
    classify_date_precision,
    extract_month,
    extract_year_from_date,
    get_century,
)
from gedcom_tools.graph import (
    build_family_members,
    count_isolated,
    find_connected_components,
)
from gedcom_tools.language_detect import GedcomLanguageDetector
from gedcom_tools.progress import PhaseTracker
from gedcom_tools.utils import (
    EncodingInfo,
    count_sources_recursive,
    detect_encoding,
    extract_xref,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ged4py.model import Record

# More conservative than MAX_LIFESPAN (120) used in validation.
# For stats "estimated living" calculation, we assume anyone born
# over 110 years ago is deceased unless we have death records.
MAX_LIFESPAN_YEARS = 110

# Practical limit for place hierarchy traversal
MAX_LOCATION_DEPTH = 10


class StatsCollector:

    # Bound on the buffered note text, as an attribute so a test can shrink it
    # far enough to exercise the fallback without a 64 MB fixture.
    max_note_buffer_bytes: int = MAX_NOTE_BUFFER_BYTES

    def __init__(
        self,
        file_path: Path,
        quiet: bool = False,
        verbose: bool = False,
        no_color: bool = False,
        top_n: int = 10,
    ):
        self.file_path = file_path
        self.quiet = quiet
        self.verbose = verbose
        self.no_color = no_color
        self.top_n = max(1, top_n)

        self.individuals: dict[str, IndividualData] = {}
        self.families: dict[str, FamilyData] = {}
        self.locations: Counter[str] = Counter()
        self.record_counts: dict[str, int] = {}
        self.encoding_info: EncodingInfo | None = None

        # Language detection state
        self.note_lookup: dict[str, str] = {}
        self.detected_languages: set[str] = set()
        self.lang_detector: GedcomLanguageDetector | None = None

        # Note text gathered during collection, detected on in phase 3 once
        # the model is loaded. Reading it here saves a second pass over the
        # file; `_note_buffer_overflow` records that the budget blew and the
        # second pass is needed after all.
        self._note_texts: list[str] = []
        self._note_bytes = 0
        self._note_buffer_overflow = False

        # Calculate living threshold dynamically
        self.living_threshold_year = date.today().year - MAX_LIFESPAN_YEARS

    def collect(self) -> StatsResult:
        """Run collection and return statistics result."""
        tracker = PhaseTracker(
            total_phases=4,
            stream=sys.stderr,
            no_color=self.no_color,
            quiet=self.quiet,
            verbose=self.verbose,
        )

        # Phase 1: Detect encoding
        with tracker.phase("Detecting encoding"):
            self._detect_encoding()

        # Phase 2: Collect data (also builds note_lookup)
        with tracker.phase("Collecting data") as spinner:
            self._collect_data(spinner)

        # Phase 3: Load language models (if the file has INDI/FAM records)
        with tracker.phase("Loading language models"):
            if self.individuals or self.families:
                self.lang_detector = GedcomLanguageDetector()
                self._detect_languages()

        # Phase 4: Calculate statistics
        with tracker.phase("Calculating statistics"):
            return self._calculate_stats()

    def _detect_encoding(self) -> None:
        try:
            self.encoding_info = detect_encoding(self.file_path)
        except (CodecError, ParserError, IntegrityError, OSError) as e:
            if not self.quiet:
                print(f"Warning: Could not detect encoding: {e}", file=sys.stderr)
            self.encoding_info = EncodingInfo(encoding="Unknown")

    def _collect_data(self, spinner: object) -> None:
        """Collect all data in a single pass through the file."""
        with GedcomReader(str(self.file_path)) as reader:
            # Pre-pass: build note lookup for language detection
            for rec in reader.records0("NOTE"):
                if rec.xref_id and rec.value:
                    self.note_lookup[rec.xref_id] = str(rec.value)

            count = 0
            for record in reader.records0():
                count += 1
                if hasattr(spinner, "update") and count % 100 == 0:
                    spinner.update(f" ({count:,} records)")

                tag = record.tag
                if not tag:
                    continue

                self.record_counts[tag] = self.record_counts.get(tag, 0) + 1

                if tag == "INDI":
                    self._collect_individual(record)
                    self._buffer_notes(record, INDI_NON_EVENT_TAGS)
                elif tag == "FAM":
                    self._collect_family(record)
                    self._buffer_notes(record, FAM_NON_EVENT_TAGS)

    @staticmethod
    def _iter_note_subs(
        record: Record, non_event_tags: frozenset[str]
    ) -> Iterator[Any]:
        """Yield an INDI/FAM record's NOTE sub-records, event notes included."""
        for sub in record.sub_records:
            if sub.tag == "NOTE":
                yield sub
            elif sub.tag not in non_event_tags:
                for subsub in sub.sub_records:
                    if subsub.tag == "NOTE":
                        yield subsub

    def _note_text(self, sub: Any) -> str | None:
        """Return an inline NOTE sub-record's text, or None if it is blank.

        Pointers are not resolved here. Every caller must skip them first -
        handed a `Pointer` this returns the xref string as if it were note
        text. Pointer targets reach detection through `note_lookup` instead,
        once each, in `_detect_languages`.
        """
        if sub.value is None:
            return None
        text = str(sub.value)
        return text if text.strip() else None

    def _buffer_notes(self, record: Record, non_event_tags: frozenset[str]) -> None:
        """Stash a record's inline note text for the language detection phase.

        Detection needs the model that phase 3 loads, but the notes are only
        cheap to reach while the record is already parsed. Buffering the text
        keeps stats to one read of the file.

        Pointer notes are skipped: their text is already resident in
        `note_lookup`, so buffering it again would charge one shared note
        once per reference and detect on it once per reference too. A file
        where thousands of records point at one research note used to blow
        the budget on a single note's worth of text.

        Consequence, deliberate: the budget bounds *inline* note text only.
        `note_lookup` holds every top-level NOTE, fully resident and never
        counted, so a file with tens of MB of top-level notes exceeds the
        intended ceiling without ever setting `_note_buffer_overflow`. That
        predates the pointer skip - the lookup was never counted - and is
        left alone here.
        """
        for sub in self._iter_note_subs(record, non_event_tags):
            if isinstance(sub, Pointer):
                continue

            text = self._note_text(sub)
            if text is None or self._note_buffer_overflow:
                continue

            self._note_bytes += len(text.encode("utf-8", "replace"))
            if self._note_bytes > self.max_note_buffer_bytes:
                # Drop the whole buffer, not just the overflowing note: phase
                # 3 rereads the file, and detecting over a partial buffer as
                # well would only duplicate the work.
                self._note_buffer_overflow = True
                self._note_texts.clear()
                continue

            self._note_texts.append(text)

    def _detect_note_language(self, sub: Any) -> None:
        """Detect the language of an inline NOTE sub-record and track it."""
        if isinstance(sub, Pointer):
            return
        self._detect_note_language_text(self._note_text(sub))

    def _detect_languages(self) -> None:
        """Run language detection across all collected INDI/FAM note text."""
        if self._note_buffer_overflow:
            self._detect_languages_rereading()
        else:
            for text in self._note_texts:
                self._detect_note_language_text(text)

        # Post-pass over every top-level note, referenced or not. Neither the
        # buffer nor the reread looks at pointers, so this is where a shared
        # note gets detected - exactly once, however many records point at it.
        for text in self.note_lookup.values():
            self._detect_note_language_text(text)

    def _detect_languages_rereading(self) -> None:
        """Detect straight off the file when the note buffer blew its budget.

        Slower, but only one note is resident at a time. The walk covers the
        whole file rather than the tail: the notes already dropped from the
        buffer would otherwise never be looked at. Pointer notes are skipped
        here as they are in the buffer - `_detect_languages`' post-pass over
        `note_lookup` covers them, once each.
        """
        with GedcomReader(str(self.file_path)) as reader:
            for rec in reader.records0("INDI"):
                for sub in self._iter_note_subs(rec, INDI_NON_EVENT_TAGS):
                    self._detect_note_language(sub)

            for rec in reader.records0("FAM"):
                for sub in self._iter_note_subs(rec, FAM_NON_EVENT_TAGS):
                    self._detect_note_language(sub)

    def _detect_note_language_text(self, text: str | None) -> None:
        if self.lang_detector is None or text is None:
            return
        text = unicodedata.normalize("NFC", text).strip()
        if len(text) < self.lang_detector.min_length:
            return
        lang, was_skipped = self.lang_detector.detect(text)
        if not was_skipped and lang != "unknown":
            self.detected_languages.add(lang)

    def _collect_individual(self, record: Record) -> None:
        xref = record.xref_id
        if not xref:
            return

        data = IndividualData(xref=xref)

        name_rec = record.sub_tag("NAME")
        if name_rec and name_rec.value:
            name_val = name_rec.value
            # ged4py returns (given, surname, trailing), where `trailing` is
            # whatever followed the surname in the NAME value. That is a
            # suffix in "John /Smith/ Jr." but further pieces of the given
            # name in the patronymic form "/Ivanov/ Ivan Ivanovich".
            if isinstance(name_val, tuple) and len(name_val) >= 2:
                given = name_val[0] or ""
                surname = name_val[1] or ""
                trailing = name_val[2] if len(name_val) > 2 else ""
                # Store full name including the trailing piece
                name_parts = [given, surname]
                if trailing:
                    name_parts.append(trailing)
                data.name = " ".join(p for p in name_parts if p)
                # Extract first given name (handle "John William" -> "John").
                # With nothing before the surname, fall back to the trailing
                # piece so "/Ivanov/ Ivan Ivanovich" ranks as "Ivan" instead
                # of dropping out of the given-name rankings entirely.
                # GEDCOM cannot tell a trailing given-name piece from a
                # suffix here, so "/Smith/ Jr." does rank "Jr." as a given
                # name. No rule gets both right; the patronymic form is the
                # commoner one, and losing the person is worse either way.
                parts = (given or trailing).split()
                data.given_name = parts[0] if parts else ""
                if not data.surname:
                    data.surname = surname
                    data.surname_parts = surname.split() if surname else []
            else:
                data.name = self._format_name(str(name_val))

            # Given name via GIVN sub-record (overrides if present)
            for sub in name_rec.sub_records:
                if sub.tag == "GIVN" and sub.value:
                    givn = str(sub.value)
                    givn_parts = givn.split() if givn else []
                    data.given_name = givn_parts[0] if givn_parts else ""
                elif sub.tag == "SURN" and sub.value:
                    data.surname = str(sub.value)
                    data.surname_parts = data.surname.split()

        sex_rec = record.sub_tag("SEX")
        if sex_rec and sex_rec.value:
            data.sex = str(sex_rec.value).upper()

        # FIXME: ged4py date parsing is flaky with non-English months
        birth_rec = record.sub_tag("BIRT")
        if birth_rec:
            date_rec = birth_rec.sub_tag("DATE")
            if date_rec and date_rec.value:
                data.birth_year = extract_year_from_date(date_rec.value)
                precision, has_full = classify_date_precision(date_rec.value)
                data.birth_date_precision = precision
                data.birth_date_has_full = has_full

                # Only extract month from non-approximate dates for accuracy
                if precision != "approximate":
                    data.birth_month = extract_month(date_rec.value)

        # Fallback to CHR/BAPM for birth year only (not month/precision)
        if data.birth_year is None:
            data.birth_year = self._extract_year(record, "CHR/DATE")
            if data.birth_year is None:
                data.birth_year = self._extract_year(record, "BAPM/DATE")

        # Death year with fallback: DEAT/DATE -> BURI/DATE
        if data.death_year is None:
            data.death_year = self._extract_year(record, "DEAT/DATE")
            if data.death_year is None:
                data.death_year = self._extract_year(record, "BURI/DATE")

        # Occupation (first one found)
        occu_rec = record.sub_tag("OCCU")
        if occu_rec and occu_rec.value:
            data.occupation = str(occu_rec.value)

        # Source count (recursive)
        data.source_count = count_sources_recursive(record)
        data.has_source = data.source_count > 0

        # Family links and other data
        for sub in record.sub_records:
            if sub.tag == "FAMC" and sub.value:
                fam_xref = extract_xref(sub.value)
                if fam_xref and not data.famc_xref:
                    data.famc_xref = fam_xref
            elif sub.tag == "FAMS" and sub.value:
                fam_xref = extract_xref(sub.value)
                if fam_xref:
                    data.fams_xrefs.append(fam_xref)
            elif sub.tag == "NOTE":
                data.has_note = True
            elif sub.tag == "OBJE":
                data.has_media = True
            # NOTE: SOUR handled by count_sources_recursive above

        # Collect locations from BIRT, DEAT, BURI, etc.
        self._collect_locations(record)

        self.individuals[xref] = data

    def _collect_family(self, record: Record) -> None:
        xref = record.xref_id
        if not xref:
            return

        data = FamilyData(xref=xref)

        # Extract marriage year
        data.marriage_year = self._extract_year(record, "MARR/DATE")

        for sub in record.sub_records:
            if sub.tag == "HUSB" and sub.value:
                data.husb_xref = extract_xref(sub.value)
            elif sub.tag == "WIFE" and sub.value:
                data.wife_xref = extract_xref(sub.value)
            elif sub.tag == "CHIL" and sub.value:
                chil_xref = extract_xref(sub.value)
                if chil_xref:
                    data.chil_xrefs.append(chil_xref)

        # Collect locations from MARR, etc.
        self._collect_locations(record)

        self.families[xref] = data

    def _collect_locations(self, record: Record) -> None:
        self._collect_locations_recursive(record)

    def _collect_locations_recursive(self, record: Record, depth: int = 0) -> None:
        if depth > MAX_LOCATION_DEPTH:
            return

        for sub in record.sub_records:
            if sub.tag == "PLAC" and sub.value:
                self.locations[str(sub.value)] += 1
            self._collect_locations_recursive(sub, depth + 1)

    def _extract_year(self, record: Record, path: str) -> int | None:
        date_rec = record.sub_tag(path)
        if date_rec is None or date_rec.value is None:
            return None
        return extract_year_from_date(date_rec.value)

    def _format_name(self, raw_name: str) -> str:
        """Format a GEDCOM name (remove slashes around surname)."""
        return raw_name.replace("/", "").strip()

    def _get_surname_safe(self, indi: IndividualData) -> str:
        if indi.surname:
            return indi.surname
        if indi.name:
            parts = indi.name.split()
            if parts:
                return parts[-1]
        return "?"

    def _calculate_stats(self) -> StatsResult:
        result = StatsResult(
            file_path=str(self.file_path),
            encoding_info=self.encoding_info,
            individuals=len(self.individuals),
            families=len(self.families),
            sources=self.record_counts.get("SOUR", 0),
            locations=len(self.locations),
            distinct_languages=len(self.detected_languages),
        )

        if not self.individuals:
            return result

        # Demographics (includes given names now)
        self._calculate_demographics(result)

        # Timeline (includes lifespan now)
        self._calculate_timeline(result)

        # Tree structure (includes marriage stats now)
        self._calculate_tree_structure(result)

        # Completeness (includes source coverage now)
        self._calculate_completeness(result)

        # Locations
        self._calculate_locations(result)

        # Life event calculations (must run after families collected)
        self._calculate_marriage_ages()  # Populates individual fields
        self._calculate_first_child_ages()  # Populates individual fields
        self._calculate_life_events(result)  # Aggregates into result
        self._calculate_spousal_age_gap(result)  # Iterates families directly

        # Family and demographic patterns
        self._calculate_family_size(result)
        self._calculate_birth_patterns(result)
        self._calculate_lifespan_by_century(result)

        # Research quality
        self._calculate_date_precision(result)
        self._calculate_occupation_coverage(result)
        self._calculate_source_depth(result)

        return result

    def _calculate_demographics(self, result: StatsResult) -> None:
        """Calculate gender distribution, surname rankings, and given name rankings."""
        total = len(self.individuals)

        # Gender counts and given name tracking
        male_given: Counter[str] = Counter()
        female_given: Counter[str] = Counter()

        for indi in self.individuals.values():
            if indi.sex == "M":
                result.gender_male += 1
                if indi.given_name:
                    male_given[indi.given_name] += 1
            elif indi.sex == "F":
                result.gender_female += 1
                if indi.given_name:
                    female_given[indi.given_name] += 1
            else:
                result.gender_unknown += 1

        # Surname frequency (individual parts)
        surname_counter: Counter[str] = Counter()
        for indi in self.individuals.values():
            for part in indi.surname_parts:
                surname_counter[part] += 1

        result.top_surnames = [
            RankedItem(name=name, count=count, percent=count / total * 100)
            for name, count in surname_counter.most_common(self.top_n)
        ]

        # Lineage frequency (full surname)
        lineage_counter: Counter[str] = Counter()
        for indi in self.individuals.values():
            surname = indi.surname if indi.surname else "Unknown"
            lineage_counter[surname] += 1

        result.top_lineages = [
            RankedItem(name=name, count=count, percent=count / total * 100)
            for name, count in lineage_counter.most_common(self.top_n)
        ]

        # Top given names by gender
        if result.gender_male > 0:
            result.top_given_names_male = [
                RankedItem(
                    name=name, count=count, percent=count / result.gender_male * 100
                )
                for name, count in male_given.most_common(self.top_n)
            ]

        if result.gender_female > 0:
            result.top_given_names_female = [
                RankedItem(
                    name=name, count=count, percent=count / result.gender_female * 100
                )
                for name, count in female_given.most_common(self.top_n)
            ]

    def _calculate_timeline(self, result: StatsResult) -> None:
        """Calculate timeline statistics including lifespan."""
        # Find earliest and latest birth years
        earliest: IndividualData | None = None
        latest: IndividualData | None = None
        century_counts: Counter[str] = Counter()
        lifespans: list[int] = []

        for indi in self.individuals.values():
            year = indi.birth_year
            if year is not None:
                # Track earliest/latest
                if earliest is None or (
                    earliest.birth_year is not None and year < earliest.birth_year
                ):
                    earliest = indi
                if latest is None or (
                    latest.birth_year is not None and year > latest.birth_year
                ):
                    latest = indi

                # Century distribution
                century_counts[get_century(year)] += 1

            # Calculate lifespan for those with both dates
            if indi.birth_year is not None and indi.death_year is not None:
                lifespan = indi.death_year - indi.birth_year
                # Filter out obviously wrong data (negative or implausible)
                if 0 <= lifespan <= MAX_LIFESPAN:
                    lifespans.append(lifespan)

        if earliest and earliest.birth_year:
            result.earliest_year = TimelineEntry(
                year=earliest.birth_year, xref=earliest.xref, name=earliest.name
            )

        if latest and latest.birth_year:
            result.latest_year = TimelineEntry(
                year=latest.birth_year, xref=latest.xref, name=latest.name
            )

        if earliest and latest and earliest.birth_year and latest.birth_year:
            result.date_span_years = latest.birth_year - earliest.birth_year

        result.by_century = dict(century_counts)

        # Lifespan statistics
        if lifespans:
            result.lifespan = LifespanStats(
                average=sum(lifespans) / len(lifespans),
                min_value=min(lifespans),
                max_value=max(lifespans),
                sample_size=len(lifespans),
            )

    def _calculate_tree_structure(self, result: StatsResult) -> None:
        """Calculate generation depth, largest families, and marriage stats."""
        # Generation depth using DFS with memoization
        memo: dict[str, int] = {}
        max_depth = 0
        deepest_indi: IndividualData | None = None

        for xref in self.individuals:
            depth = self._compute_generation_depth(xref, memo)
            if depth > max_depth:
                max_depth = depth
                deepest_indi = self.individuals[xref]

        result.generation_depth = max_depth

        if deepest_indi:
            result.earliest_generation = GenerationEntry(
                generation=max_depth, xref=deepest_indi.xref, name=deepest_indi.name
            )

        # Largest families by child count and marriage stats
        family_sizes: list[tuple[str, int]] = []
        marriages_with_date = 0
        total_children = 0

        for fam in self.families.values():
            child_count = len(fam.chil_xrefs)
            total_children += child_count
            if child_count > 0:
                family_sizes.append((fam.xref, child_count))
            if fam.marriage_year is not None:
                marriages_with_date += 1

        family_sizes.sort(key=lambda x: x[1], reverse=True)

        for xref, child_count in family_sizes[: min(3, len(family_sizes))]:
            fam = self.families[xref]
            parents = self._format_family_parents(fam)
            result.largest_families.append(
                FamilyEntry(xref=xref, parents=parents, children=child_count)
            )

        # Marriage statistics
        total_families = len(self.families)
        if total_families > 0:
            result.marriage = MarriageStats(
                total_marriages=total_families,
                with_date=marriages_with_date,
                without_date=total_families - marriages_with_date,
                avg_children=total_children / total_families,
            )

    def _parent_xrefs(self, xref: str) -> list[str]:
        """Return the xrefs of an individual's recorded parents."""
        indi = self.individuals.get(xref)
        if not indi or not indi.famc_xref:
            return []

        fam = self.families.get(indi.famc_xref)
        if not fam:
            return []

        return [parent for parent in (fam.husb_xref, fam.wife_xref) if parent]

    def _compute_generation_depth(self, xref: str, memo: dict[str, int]) -> int:
        """Compute max ancestor depth for an individual.

        Iterative post-order DFS over an explicit stack, so pedigrees with
        very long parent chains cannot blow the interpreter stack. Results
        are cached in ``memo`` and stay valid across calls: the depth of a
        node is ``1 + max(parent depths)``, which never depends on the path
        used to reach it. Ancestors currently on the traversal path are
        skipped, contributing nothing to the max, which terminates cycles.
        """
        if xref in memo:
            return memo[xref]

        # Each entry is (xref, parents_expanded). A node is pushed once to
        # queue its parents and a second time to fold their depths together.
        stack: list[tuple[str, bool]] = [(xref, False)]
        on_path: set[str] = set()

        while stack:
            current, expanded = stack.pop()

            if expanded:
                on_path.discard(current)
                depths = [
                    memo[parent]
                    for parent in self._parent_xrefs(current)
                    if parent in memo
                ]
                memo[current] = 1 + max(depths, default=0)
                continue

            # A node is never queued while it sits on the path, so any
            # duplicate entry is resolved by the time it surfaces here.
            if current in memo:
                continue

            parents = self._parent_xrefs(current)
            if not parents:
                memo[current] = 1
                continue

            on_path.add(current)
            stack.append((current, True))
            # Reversed, so parents pop in declaration order. A stack visits
            # them backwards otherwise, and in a pedigree with a parent cycle
            # the visit order decides which ancestor is still on the path when
            # the other folds - so the two orders disagree on ~1% of cyclic
            # inputs. Reversed matches the recursive version this replaced.
            for parent in reversed(parents):
                if parent not in memo and parent not in on_path:
                    stack.append((parent, False))

        return memo[xref]

    def _format_family_parents(self, fam: FamilyData) -> str:
        """Format family parents as 'Surname/Surname'."""
        husb_surname = "?"
        wife_surname = "?"

        if fam.husb_xref and fam.husb_xref in self.individuals:
            husb = self.individuals[fam.husb_xref]
            husb_surname = self._get_surname_safe(husb)

        if fam.wife_xref and fam.wife_xref in self.individuals:
            wife = self.individuals[fam.wife_xref]
            wife_surname = self._get_surname_safe(wife)

        return f"{husb_surname}/{wife_surname}"

    def _calculate_completeness(self, result: StatsResult) -> None:
        total = len(self.individuals)
        if total == 0:
            return

        birth_with = 0
        death_with = 0
        notes_with = 0
        media_with = 0
        source_with = 0
        estimated_living = 0

        for indi in self.individuals.values():
            if indi.birth_year is not None:
                birth_with += 1
            if indi.death_year is not None:
                death_with += 1
            if indi.has_note:
                notes_with += 1
            if indi.has_media:
                media_with += 1
            if indi.has_source:
                source_with += 1

            # Estimated living: born after threshold, no death/burial
            if (
                indi.birth_year
                and indi.birth_year > self.living_threshold_year
                and indi.death_year is None
            ):
                estimated_living += 1

        result.birth_date = CoverageStats(
            with_count=birth_with,
            without_count=total - birth_with,
            percent=birth_with / total * 100,
        )
        result.death_date = CoverageStats(
            with_count=death_with,
            without_count=total - death_with,
            percent=death_with / total * 100,
        )
        result.source_citations = CoverageStats(
            with_count=source_with,
            without_count=total - source_with,
            percent=source_with / total * 100,
        )
        result.notes = CoverageStats(
            with_count=notes_with,
            without_count=total - notes_with,
            percent=notes_with / total * 100,
        )
        result.media = CoverageStats(
            with_count=media_with,
            without_count=total - media_with,
            percent=media_with / total * 100,
        )
        # Isolated: components of size 1 (singletons) or 2 (pairs)
        family_members = build_family_members(
            (fam.xref, fam) for fam in self.families.values()
        )
        components = find_connected_components(
            set(self.individuals.keys()), family_members
        )
        isolated = count_isolated(components)
        result.isolated = CoverageStats(
            with_count=isolated,
            without_count=total - isolated,
            percent=isolated / total * 100,
        )
        result.estimated_living = CoverageStats(
            with_count=estimated_living,
            without_count=total - estimated_living,
            percent=estimated_living / total * 100,
        )

    def _calculate_locations(self, result: StatsResult) -> None:
        total_loc_refs = sum(self.locations.values())
        if total_loc_refs == 0:
            return

        result.top_locations = [
            RankedItem(name=place, count=count, percent=count / total_loc_refs * 100)
            for place, count in self.locations.most_common(self.top_n)
        ]

    # -------------------------------------------------------------------------
    # Life event and pattern calculation methods
    # -------------------------------------------------------------------------

    def _build_aggregate_stats(self, values: list[int]) -> AggregateStats | None:
        if not values:
            return None

        return AggregateStats(
            average=sum(values) / len(values),
            min_value=min(values),
            max_value=max(values),
            sample_size=len(values),
        )

    def _calculate_marriage_ages(self) -> None:
        for xref, indi in self.individuals.items():
            if not indi.fams_xrefs or indi.birth_year is None:
                continue

            earliest_marriage: int | None = None
            earliest_fam_xref: str | None = None

            for fam_xref in indi.fams_xrefs:
                fam = self.families.get(fam_xref)
                if fam and fam.marriage_year is not None:
                    if (
                        earliest_marriage is None
                        or fam.marriage_year < earliest_marriage
                    ):
                        earliest_marriage = fam.marriage_year
                        earliest_fam_xref = fam_xref

            if earliest_marriage is not None and earliest_fam_xref:
                indi.first_marriage_year = earliest_marriage
                indi.first_marriage_age = earliest_marriage - indi.birth_year
                indi.first_marriage_fam_xref = earliest_fam_xref

                # Get spouse birth year - verify individual is actually HUSB or WIFE
                fam = self.families.get(earliest_fam_xref)
                if not fam:
                    continue
                spouse_xref: str | None = None
                if fam.husb_xref == xref:
                    spouse_xref = fam.wife_xref
                elif fam.wife_xref == xref:
                    spouse_xref = fam.husb_xref

                if spouse_xref and spouse_xref in self.individuals:
                    indi.spouse_birth_year = self.individuals[spouse_xref].birth_year

    def _calculate_first_child_ages(self) -> None:
        for indi in self.individuals.values():
            if not indi.fams_xrefs or indi.birth_year is None:
                continue

            earliest_child_year: int | None = None

            for fam_xref in indi.fams_xrefs:
                fam = self.families.get(fam_xref)
                if not fam:
                    continue

                for child_xref in fam.chil_xrefs:
                    child = self.individuals.get(child_xref)
                    if child and child.birth_year is not None:
                        if (
                            earliest_child_year is None
                            or child.birth_year < earliest_child_year
                        ):
                            earliest_child_year = child.birth_year

            # Only set field if age is plausible
            if earliest_child_year is not None:
                age = earliest_child_year - indi.birth_year
                if MIN_PARENT_AGE <= age <= MAX_FIRST_CHILD_AGE:
                    indi.first_child_year = earliest_child_year
                    indi.first_child_age = age

    def _calculate_life_events(self, result: StatsResult) -> None:
        # Marriage age by gender and century
        male_ages: list[int] = []
        female_ages: list[int] = []
        male_by_century: dict[str, list[int]] = {}
        female_by_century: dict[str, list[int]] = {}

        # First child age by gender
        male_child_ages: list[int] = []
        female_child_ages: list[int] = []

        for indi in self.individuals.values():
            # Marriage age
            if indi.first_marriage_age is not None:
                if MIN_MARRIAGE_AGE <= indi.first_marriage_age <= MAX_MARRIAGE_AGE:
                    century = get_century(indi.birth_year) if indi.birth_year else None

                    if indi.sex == "M":
                        male_ages.append(indi.first_marriage_age)
                        if century:
                            male_by_century.setdefault(century, []).append(
                                indi.first_marriage_age
                            )
                    elif indi.sex == "F":
                        female_ages.append(indi.first_marriage_age)
                        if century:
                            female_by_century.setdefault(century, []).append(
                                indi.first_marriage_age
                            )

            # First child age
            if indi.first_child_age is not None:
                if MIN_PARENT_AGE <= indi.first_child_age <= MAX_FIRST_CHILD_AGE:
                    if indi.sex == "M":
                        male_child_ages.append(indi.first_child_age)
                    elif indi.sex == "F":
                        female_child_ages.append(indi.first_child_age)

        # Build marriage age stats with century breakdown
        if male_ages or female_ages:
            by_century: dict[str, dict[str, AggregateStats | None]] = {}
            all_centuries = set(male_by_century.keys()) | set(female_by_century.keys())
            for century in sorted(all_centuries):
                male_stats = self._build_aggregate_stats(
                    male_by_century.get(century, [])
                )
                female_stats = self._build_aggregate_stats(
                    female_by_century.get(century, [])
                )
                if male_stats or female_stats:
                    by_century[century] = {
                        "male": male_stats,
                        "female": female_stats,
                    }

            result.age_at_first_marriage = GenderedAggregateStats(
                male=self._build_aggregate_stats(male_ages),
                female=self._build_aggregate_stats(female_ages),
                by_century=by_century,
            )

        # Build first child age stats
        if male_child_ages or female_child_ages:
            result.age_at_first_child = GenderedAggregateStats(
                male=self._build_aggregate_stats(male_child_ages),
                female=self._build_aggregate_stats(female_child_ages),
            )

    def _calculate_spousal_age_gap(self, result: StatsResult) -> None:
        age_gaps: list[int] = []

        for fam in self.families.values():
            # Need both spouses with birth years
            if not fam.husb_xref or not fam.wife_xref:
                continue

            husb = self.individuals.get(fam.husb_xref)
            wife = self.individuals.get(fam.wife_xref)

            if not husb or not wife:
                continue
            if husb.birth_year is None or wife.birth_year is None:
                continue

            gap = abs(husb.birth_year - wife.birth_year)
            if gap <= MAX_SPOUSAL_AGE_GAP:
                age_gaps.append(gap)

        result.spousal_age_gap = self._build_aggregate_stats(age_gaps)

    def _calculate_family_size(self, result: StatsResult) -> None:
        sizes: list[int] = []
        for fam in self.families.values():
            child_count = len(fam.chil_xrefs)
            if child_count > 0:  # Only include families with children
                sizes.append(child_count)

        if not sizes:
            return

        # Distribution buckets
        distribution: dict[str, int] = {
            "1": 0,
            "2-3": 0,
            "4-6": 0,
            "7-9": 0,
            "10+": 0,
        }
        for size in sizes:
            if size == 1:
                distribution["1"] += 1
            elif size <= 3:
                distribution["2-3"] += 1
            elif size <= 6:
                distribution["4-6"] += 1
            elif size <= 9:
                distribution["7-9"] += 1
            else:
                distribution["10+"] += 1

        result.family_size = AggregateStats(
            average=sum(sizes) / len(sizes),
            min_value=min(sizes),
            max_value=max(sizes),
            sample_size=len(sizes),
            distribution=distribution,
        )

    def _calculate_birth_patterns(self, result: StatsResult) -> None:
        month_counts: dict[int, int] = {}

        for indi in self.individuals.values():
            if indi.birth_month:
                month_counts[indi.birth_month] = (
                    month_counts.get(indi.birth_month, 0) + 1
                )

        if month_counts:
            result.birth_by_month = month_counts

    def _calculate_lifespan_by_century(self, result: StatsResult) -> None:
        century_lifespans: dict[str, list[int]] = {}

        for indi in self.individuals.values():
            if indi.birth_year is None or indi.death_year is None:
                continue

            lifespan = indi.death_year - indi.birth_year
            if not (0 <= lifespan <= MAX_LIFESPAN):
                continue

            century = get_century(indi.birth_year)
            century_lifespans.setdefault(century, []).append(lifespan)

        for century, lifespans in sorted(century_lifespans.items()):
            stats = self._build_aggregate_stats(lifespans)
            if stats:
                result.lifespan_by_century[century] = stats

    def _calculate_date_precision(self, result: StatsResult) -> None:
        if not self.individuals:
            return

        stats = DatePrecisionStats()

        for indi in self.individuals.values():
            precision = indi.birth_date_precision
            has_full = indi.birth_date_has_full

            if precision == "full":
                stats.full += 1
            elif precision == "partial":
                stats.partial += 1
            elif precision == "approximate":
                if has_full:
                    stats.approximate_full += 1
                else:
                    stats.approximate_partial += 1
            else:  # "missing"
                stats.missing += 1

        if stats.total > 0:
            result.date_precision = stats

    def _calculate_occupation_coverage(self, result: StatsResult) -> None:
        if not self.individuals:
            return

        with_occupation = sum(
            1 for indi in self.individuals.values() if indi.occupation.strip()
        )
        total = len(self.individuals)

        result.occupation_coverage = CoverageStats(
            with_count=with_occupation,
            without_count=total - with_occupation,
            percent=with_occupation / total * 100 if total else 0.0,
        )

    def _calculate_source_depth(self, result: StatsResult) -> None:
        if not self.individuals:
            return

        counts = [indi.source_count for indi in self.individuals.values()]
        result.source_depth = self._build_aggregate_stats(counts)
