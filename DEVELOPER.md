# Developer Guide

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/kimon1230/gedcom-tools.git
   cd gedcom-tools
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install in development mode with dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Project Structure

```
gedcom_tools/
├── src/
│   └── gedcom_tools/
│       ├── __init__.py          # Package init, version
│       ├── cli.py               # Main entry point, argument parsing
│       ├── constants.py         # Shared constants (exit codes, thresholds)
│       ├── dates.py             # Shared date parsing utilities
│       ├── graph.py             # Graph algorithms (UnionFind, components, ParentChildGraph, BFS traversal)
│       ├── language_detect.py   # fastText language detection wrapper (lazy model load, cache dir)
│       ├── progress.py          # Terminal UI (Colors, PhaseTracker, GlyphSet/--ascii)
│       ├── phonetics.py         # Shared phonetics (American Soundex and Double Metaphone)
│       ├── utils.py             # Shared utilities (encoding, xref, validation, secure output)
│       ├── commands/
│       │   ├── __init__.py      # Commands package init
│       │   ├── isolated.py      # Isolated individuals command
│       │   ├── languages.py     # Languages command (note/name language breakdown)
│       │   ├── validate.py      # Validation command handler
│       │   ├── stats/           # Stats command package
│       │   │   ├── __init__.py  # CLI registration, public API
│       │   │   ├── models.py    # Data classes (IndividualData, etc.)
│       │   │   ├── collector.py # StatsCollector class
│       │   │   └── formatters.py# StatsResult with format methods
│       │   ├── search/          # Search command package
│       │   │   ├── __init__.py  # CLI registration, orchestration
│       │   │   ├── models.py    # Data classes (SearchIndividual, etc.)
│       │   │   ├── query.py     # Query parsing and validation
│       │   │   ├── collector.py # Individual extraction/normalization
│       │   │   ├── matcher.py   # Term matching (text, phonetic, wildcard, regex)
│       │   │   ├── relationships.py # BFS ancestor/descendant traversal
│       │   │   └── formatter.py # Text and JSON output formatting
│       │   ├── compare/         # Compare command package
│       │   │   ├── __init__.py  # CLI registration, orchestration
│       │   │   ├── models.py    # Data classes (CompareIndividual, etc.)
│       │   │   ├── collector.py # Individual extraction/normalization
│       │   │   ├── blocker.py   # Multi-pass blocking
│       │   │   ├── scorer.py    # Weighted Jaro-Winkler scoring
│       │   │   ├── dedup.py     # Greedy one-to-one deduplication
│       │   │   └── formatters.py# Text and JSON output formatting
│       │   ├── duplicates/      # Duplicates command package
│       │   │   ├── __init__.py  # CLI registration, orchestration
│       │   │   ├── models.py    # Data classes (DuplicatesResult)
│       │   │   └── formatters.py# Text and JSON output formatting
│       │   ├── relationship/    # Relationship command package
│       │   │   ├── __init__.py  # CLI registration, xref validation, orchestration
│       │   │   ├── models.py    # Data classes (RelIndividual, RelationshipPath, RelationshipResult)
│       │   │   ├── classifier.py# Relationship classification and description building
│       │   │   ├── algorithm.py # LCA algorithm, half-detection, sorting
│       │   │   └── formatter.py # Text and JSON output formatting
│       │   ├── export/          # Export command package
│       │   │   ├── __init__.py  # CLI registration, format resolution, orchestration
│       │   │   ├── models.py    # Data classes (ExportIndividual, ExportFamily, ExportResult, estimate_living)
│       │   │   ├── collector.py # Individual/family extraction from GEDCOM
│       │   │   └── formatters.py# CSV and JSON output formatting
│       │   ├── convert/         # Convert command package
│       │   │   ├── __init__.py  # CLI registration, orchestration
│       │   │   └── transcoder.py# Encoding transcoder (codec resolution, BOM, CHAR header, NFC)
│       │   └── filter/          # Filter command package
│       │       ├── __init__.py  # CLI registration, validation, pipeline orchestration
│       │       ├── models.py    # Data classes (GedcomLine, GedcomRecord, FilterSpec, FilterResult, RecordCounts)
│       │       ├── parser.py    # Line-level GEDCOM parser (lossless round-trip)
│       │       ├── transforms.py# Strip transforms and subtree extraction
│       │       └── writer.py    # Dangling pointer cleanup, empty family cascade, serialization
│       └── validation/
│           ├── __init__.py      # Public API: validate_file()
│           ├── engine.py        # 4-phase validation orchestrator
│           ├── issues.py        # Error/warning codes and data classes
│           ├── reference.py     # Cross-reference validation
│           ├── result.py        # Result formatting (text/JSON)
│           └── semantic.py      # Semantic validation (dates, cycles)
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── fixtures/                # Test GEDCOM files (555sample.ged, etc.)
│   ├── test_cli.py              # CLI integration tests
│   ├── test_dates.py            # Date parsing utility tests
│   ├── test_graph.py            # Graph algorithm tests
│   ├── test_isolated.py         # Isolated command tests
│   ├── test_languages.py        # Languages command and language_detect tests
│   ├── test_progress.py         # Progress UI tests
│   ├── test_stats.py            # Stats command tests
│   ├── test_stats_schema.py     # JSON schema validation tests
│   ├── test_search_*.py         # Search command tests (query, collector, matcher, relationships, formatter, integration)
│   ├── test_compare_*.py        # Compare command tests (scorer, dedup, formatters, integration)
│   ├── test_duplicates_*.py    # Duplicates command tests (formatters, integration)
│   ├── test_export_*.py        # Export command tests (collector, formatters, integration)
│   ├── test_convert.py         # Convert command tests
│   ├── test_filter_*.py       # Filter command tests (parser, writer, transforms, integration)
│   ├── test_relationship.py    # Relationship command tests
│   ├── test_utils.py            # Shared utility tests
│   └── test_validation/         # Validation engine tests
├── docs/
│   ├── isolated.md              # Isolated command documentation
│   ├── languages.md             # Languages command documentation
│   ├── validate.md              # Validation error/warning codes
│   ├── stats.md                 # Stats command documentation
│   ├── stats-schema.json        # JSON schema for stats output
│   ├── search.md                # Search command documentation
│   ├── compare.md               # Compare command documentation
│   ├── duplicates.md            # Duplicates command documentation
│   ├── relationship.md          # Relationship command documentation
│   ├── export.md                # Export command documentation
│   ├── convert.md              # Convert command documentation
│   └── filter.md              # Filter command documentation
├── pyproject.toml               # Project metadata and tool config
├── README.md                    # User documentation
├── DEVELOPER.md                 # This file
└── CHANGELOG.md                 # Version history
```

## Architecture

### Shared Modules

**`constants.py`** — Shared constants used across validation and stats:
- Exit codes (`EXIT_SUCCESS`, `EXIT_ERROR`, `EXIT_USAGE_ERROR`)
- Validation thresholds (`MAX_LIFESPAN`, `MIN_PARENT_AGE`, `MAX_PARENT_AGE_AT_BIRTH`)
- Sibling spacing (`MIN_SIBLING_SPACING_MONTHS`)
- SEX validation (`VALID_SEX_VALUES`: M, F, U, X)
- Stats thresholds (`MIN_MARRIAGE_AGE`, `MAX_MARRIAGE_AGE`, `MAX_FIRST_CHILD_AGE`, `MAX_SPOUSAL_AGE_GAP`)

**`utils.py`** — Common utilities used across all commands:
- `EncodingInfo` dataclass — encoding detection results. The fields are `encoding`, `has_bom` and `declared_charset` — not `detected`/`declared`, which is a recurring mis-guess
- `detect_encoding()` — BOM detection + declared CHAR header parsing, over a bounded read of the header. Falls back to a full `GedcomReader` pass only for a malformed header or a `1 CHAR` line beyond the first 64 KB
- `extract_xref()` — extract xref string from ged4py records
- `validate_input_file()` — shared file existence/readability check
- `count_sources_recursive()` — count SOUR citations at all nesting levels
- `strip_bom()` — strip byte order mark from raw bytes, returning stripped bytes and BOM type
- `resolve_source_codec()` — resolve encoding info to a Python codec name
- `check_output_safety()` — validate output path (overwrite, same-file, directory existence)
- `write_output_securely()` — the only sanctioned way to write an output file. Creates it `O_CREAT|O_EXCL|O_NOFOLLOW` at `0600`, so exported PII is never briefly world-readable and a symlink at the target is refused
- `report_error()` / `sanitize_error()` — the shared error epilogue every command's generic handler calls, so all eleven print the same two-line shape with escape sequences stripped

**`dates.py`** — Date parsing and classification:
- `extract_year_from_date()` — year extraction from GEDCOM date strings
- `extract_month()` — month extraction for birth pattern analysis
- `classify_date_precision()` — categorize dates as full/partial/approximate/missing

**`graph.py`** — Graph algorithms for family connectivity:
- `UnionFind` — union-find data structure with path compression and union by rank
- `find_connected_components()` — identify connected components from family member sets
- `ParentChildGraph` — directed parent-child graph with spouse pairings
- `build_parent_child_graph()` — construct graph from GEDCOM FAM records
- `find_ancestors()`, `find_descendants()` — BFS traversal with depth limit
- `find_ancestors_with_depth()` — BFS returning ancestor-to-depth map with truncation flag

### Command Architecture

Each command follows the same pattern: `register_subcommand(subparsers)` to wire up argparse, `run(args)` as the entry point. Results are dataclasses with `format_text()` and `format_json()` methods.

- **validate** — 4-phase validation engine (see below)
- **stats** — Collector/Models/Formatters pattern: `StatsCollector` gathers raw data into `IndividualData`/`FamilyData` models, then `StatsResult` computes aggregates and formats output
- **isolated** — Builds family member sets from GEDCOM FAM records, runs `find_connected_components()` via UnionFind, reports singletons (size 1) and isolated pairs (size 2)
- **search** — Query/Collector/Matcher/Relationships/Formatter pipeline: parses query syntax into terms, collects individuals with pre-computed Soundex codes, matches via substring/exact/phonetic/wildcard/regex, optionally traverses parent-child graph for ancestor/descendant queries
- **compare** — Collector/Models/Phonetics/Blocker/Scorer/Dedup/Formatters pipeline: extracts individuals from two files, generates candidate pairs via multi-pass blocking, scores with weighted Jaro-Winkler, deduplicates greedily, and formats results
- **duplicates** — Single-file duplicate detection reusing the compare scoring engine: self-join blocking with self-pair/symmetric filtering, single `used` set for greedy dedup, own formatters for single-file output
- **relationship** — LCA-based relationship classification with half-detection and multi-key sort: loads individuals and parent-child graph, BFS from both endpoints, classifies via generation-pair table, detects half-blood via spouse pairing
- **export** — Data extraction to CSV or JSON: collector builds ExportIndividual/ExportFamily from GEDCOM, formatters produce CSV (with optional BOM) or JSON (with meta section, alt_names, notes). Living estimation + privacy redaction via `--redact-living`
- **convert** — Raw byte-level encoding transcoder: reads file as bytes, strips BOM, decodes with source codec, NFC-normalizes ANSEL sources, updates CHAR header, re-encodes in target codec. Supports auto-detection and `--from` override for non-standard codecs
- **filter** — Line-level GEDCOM transformer: parses raw lines into records, applies strip transforms (record-level and line-level) and/or subtree extraction (BFS via ParentChildGraph), cleans dangling pointers, cascades empty families, serializes back preserving encoding/BOM/line endings

### Validation Engine (4-Phase Design)

The validation engine (`src/gedcom_tools/validation/engine.py`) processes GEDCOM files in four sequential phases:

```
┌─────────────────────────────────────────────────────────────────┐
│                     GEDCOM File Input                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Encoding Detection                                    │
│  - Check BOM (Byte Order Mark)                                  │
│  - Read declared CHAR encoding from header                      │
│  - Detect ANSEL encoding (supported via ansel codec)                                 │
│  - Report encoding mismatches                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: Structure Parsing                                     │
│  - Verify HEAD/TRLR records exist                               │
│  - Collect all xref definitions (@I1@, @F1@, etc.)              │
│  - Collect all xref usages (references)                         │
│  - Extract individual/family data for semantic checks           │
│  - Build line number map for error reporting                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: Reference Validation                                  │
│  - Unresolved references (xref used but never defined)          │
│  - Duplicate definitions (same xref defined twice)              │
│  - Orphaned records (defined but never referenced)              │
│  - Isolated individuals (no family connections)                 │
│  - Empty families (no members)                                  │
│  - Asymmetric links (one-sided FAM↔INDI cross-references)      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: Semantic Validation                                   │
│  - Ancestry cycles (person is their own ancestor)               │
│  - Date logic (death before birth, etc.)                        │
│  - Age plausibility (parent too young/old, lifespan > 120)      │
│  - Marriage before birth                                        │
│  - Sibling spacing (< 9 months, excluding twins)                │
│  - Sex-role mismatch (HUSB with SEX F, WIFE with SEX M)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ValidationResult                            │
│  - List of issues (errors + warnings)                           │
│  - Encoding info                                                │
│  - Record counts                                                │
│  - Format as text or JSON                                       │
└─────────────────────────────────────────────────────────────────┘
```

**Design Rationale:**

1. **Sequential phases** - Each phase depends on data collected by previous phases. Encoding must be detected before parsing; parsing must complete before reference checking.

2. **Separation of concerns** - Reference validation (`reference.py`) and semantic validation (`semantic.py`) are independent modules that don't know about each other.

3. **Quick vs Full modes** - In quick mode, validation stops at the first error. In full mode, all phases run to completion, collecting all issues.

4. **Line number tracking** - A byte-offset-to-line-number map is built during phase 2 to provide accurate line numbers in error messages.

### Error Codes

Error codes follow a consistent scheme in `issues.py`:

- `E0xx` - Errors (fatal issues that indicate invalid GEDCOM)
- `W0xx` - Warnings (issues that may indicate problems but aren't fatal)

The severity is automatically derived from the code prefix.

## Test Data

- **`tests/fixtures/555sample.ged`** — from [gedcom.org](https://www.gedcom.org/samples/555SAMPLE.GED), used as the primary regression test fixture.
- **`tests/fixtures/royal92.ged`** — 3,010 individuals of European royalty, created by Denis R. Reid (1992). Used for README sample output and manual testing.
- Most unit tests use inline GEDCOM strings via `tmp_path` for isolation and readability.

## Running Tests

```bash
# Run all tests with coverage
pytest

# Run tests without coverage requirement (useful during development)
pytest --no-cov

# Run specific test file
pytest tests/test_cli.py -v

# Run tests matching a pattern
pytest -k "validate" -v

# Skip the tests that need the language-detection model
pytest -m "not network"
```

Coverage requirement: **95%+**

### The `network` marker

Language detection fetches a ~126 MB fastText model from a CDN on first use,
into `$XDG_CACHE_HOME/gedcom-tools/` (or `~/.cache/gedcom-tools/`). The 35 tests
that genuinely need the real model carry `@pytest.mark.network`:

```bash
pytest -m "not network"
```

Verified against an empty `XDG_CACHE_HOME`: 2607 passed, 35 deselected, **zero
bytes** fetched. It costs about 0.5 percentage points of coverage, all of it in
`src/gedcom_tools/language_detect.py`, so the run still clears the 95 % gate.

Everything else is kept offline by the `_fast_lingua` stub in
`tests/conftest.py`, which patches `GedcomLanguageDetector` at both import sites
(`commands/languages.py` and `commands/stats/collector.py`). That stub is
deliberately **not** autouse — a test that means to exercise the real detector
should have to say so. If you add a test that runs the `stats` pipeline, opt in
with `@pytest.mark.usefixtures("_fast_lingua")`, because `StatsCollector` builds
a detector unconditionally for any file with INDI or FAM records. Marking the
fixture itself with `network` is a hard collection error on pytest 9 — the marked
tests instead call `_detector_or_skip()`, which turns a download failure into a
skip, so a CDN outage does not read as a broken build.

`-m "not network"` is an escape hatch for a fresh clone, an offline laptop or a
CDN outage. CI should keep running the full suite, or the real-model assertions
stop being exercised.

## Code Quality

### Formatting

```bash
# Check formatting
black --check .

# Apply formatting
black .
```

### Linting

```bash
# Check for issues
ruff check .

# Auto-fix where possible
ruff check . --fix
```

### Type Checking

```bash
mypy src/
```

### Security Audit

```bash
pip-audit
```

## Adding a New Command

1. Create a new module in `src/gedcom_tools/commands/`:
   ```python
   # src/gedcom_tools/commands/mycommand.py

   def register_subcommand(subparsers):
       parser = subparsers.add_parser(
           "mycommand",
           help="Description of the command",
       )
       # Add arguments...

   def run(args):
       try:
           ...  # Implementation
           return EXIT_SUCCESS
       except BrokenPipeError:
           # Must come first, and must re-raise. cli._run_command turns this
           # into a clean exit; catching it below would report a crash when the
           # user simply piped into `head`.
           raise
       except Exception as e:
           report_error(e, verbose=args.verbose)
           return EXIT_ERROR
   ```

2. Register it in `src/gedcom_tools/cli.py` — in `create_parser()` and in the
   module-level `_HANDLERS` mapping:
   ```python
   from gedcom_tools.commands import mycommand

   # In create_parser():
   mycommand.register_subcommand(subparsers)

   # At module level:
   _HANDLERS: dict[str, ModuleType] = {
       ...,
       "mycommand": mycommand,
   }
   ```

   `_HANDLERS` maps a name to the **module**, not to the bound `run` function.
   That is deliberate and load-bearing: `{"mycommand": mycommand.run}` binds the
   function object at import time, which silently defeats the
   `monkeypatch.setattr(<module>, "run", ...)` that several CLI tests rely on.
   `_run_command()` does the lookup and calls `.run(args)` at dispatch time.

3. Add tests in `tests/test_mycommand.py`. Build the args through
   `create_parser().parse_args([...])` rather than hand-writing an
   `argparse.Namespace` — a hand-built namespace re-declares every default and
   `dest` name, so a later flag rename leaves the tests green while the real CLI
   raises `AttributeError`.

4. `tests/test_broken_pipe_contract.py` walks the modules in `_HANDLERS` and will
   fail unless the new command carries the `BrokenPipeError` re-raise shown
   above, ahead of its generic handler. Do not weaken that rule to go green; the
   only alternative is the exemption set, which is itself checked for still
   being true.

5. Update README.md with usage documentation, and add `docs/mycommand.md`.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (runtime error, validation failure, etc.) |
| 2 | Usage error (invalid arguments, missing command) |

## Dependencies

### Runtime
- `ged4py` - GEDCOM file parsing
- `ansel` - ANSEL codec, imported directly by `commands/convert/transcoder.py`. `ged4py` also depends on it, but the declaration is deliberate: relying on that transitive edge breaks `convert` at import time the day `ged4py` drops it
- `fast-langdetect` - fastText language detection, used by the `languages` command and by `stats`. Imported lazily — it pulls in an HTTP stack, which cost about 32 ms on every invocation when it was imported at module scope
- `rapidfuzz` - Jaro-Winkler string similarity (used by compare command). Also imported lazily, for the same reason
- `DoubleMetaphone` - Double Metaphone phonetic encoding for European name matching (used by search, compare, and duplicates commands via `--phonetic metaphone`)

### Development
- `pytest` - Testing framework
- `pytest-cov` - Coverage reporting
- `jsonschema` - JSON schema validation (used in tests)
- `ruff` - Linting
- `black` - Code formatting
- `mypy` - Type checking
- `pip-audit` - Security vulnerability scanning

## Versioning

This project follows [Semantic Versioning](https://semver.org/).

See [CHANGELOG.md](CHANGELOG.md) for release history and notable changes.

When making changes:
1. Update version in `pyproject.toml` and `src/gedcom_tools/__init__.py`
2. Add entry to CHANGELOG.md under "Unreleased" section
3. On release, move "Unreleased" items to new version section with date
