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
│       └── commands/
│           ├── __init__.py      # Commands package init
│           └── validate.py      # Validation command
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   ├── fixtures/
│   │   └── 555sample.ged        # Test GEDCOM from gedcom.org
│   └── test_cli.py              # CLI tests
├── pyproject.toml               # Project metadata and tool config
├── README.md                    # User documentation
└── DEVELOPER.md                 # This file
```

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

Coverage requirement: **90%+**

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
