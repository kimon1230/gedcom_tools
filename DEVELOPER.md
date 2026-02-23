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
│       ├── graph.py             # Graph algorithms (UnionFind, components)
│       ├── progress.py          # Terminal UI (Colors, PhaseTracker)
│       ├── utils.py             # Shared utilities (encoding, xref, validation)
│       ├── commands/
│       │   ├── __init__.py      # Commands package init
│       │   ├── isolated.py      # Isolated individuals command
│       │   ├── validate.py      # Validation command handler
│       │   ├── stats/           # Stats command package
│       │   │   ├── __init__.py  # CLI registration, public API
│       │   │   ├── models.py    # Data classes (IndividualData, etc.)
│       │   │   ├── collector.py # StatsCollector class
│       │   │   └── formatters.py# StatsResult with format methods
│       │   └── compare/         # Compare command package
│       │       ├── __init__.py  # CLI registration, orchestration
│       │       ├── models.py    # Data classes (CompareIndividual, etc.)
│       │       ├── collector.py # Individual extraction/normalization
│       │       ├── phonetics.py # American Soundex encoding
│       │       ├── blocker.py   # Multi-pass blocking
│       │       ├── scorer.py    # Weighted Jaro-Winkler scoring
│       │       ├── dedup.py     # Greedy one-to-one deduplication
│       │       └── formatters.py# Text and JSON output formatting
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
│   ├── test_progress.py         # Progress UI tests
│   ├── test_stats.py            # Stats command tests
│   ├── test_stats_schema.py     # JSON schema validation tests
│   ├── test_compare_*.py        # Compare command tests (scorer, dedup, formatters, integration)
│   ├── test_utils.py            # Shared utility tests
│   └── test_validation/         # Validation engine tests
├── docs/
│   ├── isolated.md              # Isolated command documentation
│   ├── validate.md              # Validation error/warning codes
│   ├── stats.md                 # Stats command documentation
│   ├── stats-schema.json        # JSON schema for stats output
│   └── compare.md               # Compare command documentation
├── pyproject.toml               # Project metadata and tool config
├── README.md                    # User documentation
├── DEVELOPER.md                 # This file
└── CHANGELOG.md                 # Version history
```

## Architecture

### Shared Modules

**`utils.py`** — Common utilities used across all commands:
- `EncodingInfo` dataclass — encoding detection results (detected, declared, BOM)
- `detect_encoding()` — BOM detection + declared CHAR header parsing
- `extract_xref()` — extract xref string from ged4py records
- `validate_input_file()` — shared file existence/readability check
- `count_sources_recursive()` — count SOUR citations at all nesting levels

**`dates.py`** — Date parsing and classification:
- `extract_year_from_date()` — year extraction from GEDCOM date strings
- `extract_month()` — month extraction for birth pattern analysis
- `classify_date_precision()` — categorize dates as full/partial/approximate/missing

**`graph.py`** — Graph algorithms for family connectivity:
- `UnionFind` — union-find data structure with path compression and union by rank
- `find_connected_components()` — identify connected components from family member sets

### Command Architecture

Each command follows the same pattern: `register_subcommand(subparsers)` to wire up argparse, `run(args)` as the entry point. Results are dataclasses with `format_text()` and `format_json()` methods.

- **validate** — 4-phase validation engine (see below)
- **stats** — Collector/Models/Formatters pattern: `StatsCollector` gathers raw data into `IndividualData`/`FamilyData` models, then `StatsResult` computes aggregates and formats output
- **isolated** — Builds family member sets from GEDCOM FAM records, runs `find_connected_components()` via UnionFind, reports singletons (size 1) and isolated pairs (size 2)
- **compare** — Collector/Models/Phonetics/Blocker/Scorer/Dedup/Formatters pipeline: extracts individuals from two files, generates candidate pairs via multi-pass blocking, scores with weighted Jaro-Winkler, deduplicates greedily, and formats results

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
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: Semantic Validation                                   │
│  - Ancestry cycles (person is their own ancestor)               │
│  - Date logic (death before birth, etc.)                        │
│  - Age plausibility (parent too young/old, lifespan > 120)      │
│  - Marriage before birth                                        │
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
```

Coverage requirement: **95%+**

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
       # Implementation...
       return 0  # Exit code
   ```

2. Register it in `src/gedcom_tools/cli.py`:
   ```python
   from gedcom_tools.commands import mycommand

   # In create_parser():
   mycommand.register_subcommand(subparsers)

   # In _dispatch_command():
   handlers = {
       "validate": validate.run,
       "stats": stats.run,
       "isolated": isolated.run,
       "mycommand": mycommand.run,
   }
   ```

3. Add tests in `tests/test_mycommand.py`

4. Update README.md with usage documentation

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (runtime error, validation failure, etc.) |
| 2 | Usage error (invalid arguments, missing command) |

## Dependencies

### Runtime
- `ged4py` - GEDCOM file parsing
- `rapidfuzz` - Jaro-Winkler string similarity (used by compare command)

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
