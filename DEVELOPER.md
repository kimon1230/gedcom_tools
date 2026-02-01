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
│       ├── progress.py          # Terminal UI (spinners, progress)
│       ├── commands/
│       │   ├── __init__.py      # Commands package init
│       │   └── validate.py      # Validation command handler
│       └── validation/
│           ├── __init__.py      # Public API: validate_file()
│           ├── engine.py        # 4-phase validation orchestrator
│           ├── issues.py        # Error/warning codes and data classes
│           ├── reference.py     # Cross-reference validation
│           ├── result.py        # Result formatting (text/JSON)
│           └── semantic.py      # Semantic validation (dates, cycles)
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── fixtures/                # Test GEDCOM files
│   ├── test_cli.py              # CLI integration tests
│   ├── test_progress.py         # Progress UI tests
│   └── test_validation/         # Validation engine tests
├── pyproject.toml               # Project metadata and tool config
├── README.md                    # User documentation
└── DEVELOPER.md                 # This file
```

## Architecture

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
│  - Reject ANSEL (not supported)                                 │
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

The test suite uses `555sample.ged` from [gedcom.org](https://www.gedcom.org/samples/555SAMPLE.GED) as the primary test fixture. This is a standard GEDCOM sample file used for testing GEDCOM parsers and tools.

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

### Development
- `pytest` - Testing framework
- `pytest-cov` - Coverage reporting
- `ruff` - Linting
- `black` - Code formatting
- `mypy` - Type checking
- `pip-audit` - Security vulnerability scanning
