# gedcom-tools

CLI utility for GEDCOM file validation, analysis, and search.

## Installation

```bash
pip install gedcom-tools
```

Or for development:

```bash
git clone https://github.com/kimon1230/gedcom-tools.git
cd gedcom-tools
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
gedcom-tools <command> [options] <file>
```

### Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `-v, --verbose` | Show detailed progress with timing |
| `-q, --quiet` | Suppress non-essential output |
| `--format {text,json}` | Output format (default: text) |

### Commands

#### validate

Check a GEDCOM file for structural errors and data issues.

```bash
# Quick validation (fail fast on first error)
gedcom-tools validate family.ged

# Full validation (collect all errors with IDs and line numbers)
gedcom-tools validate --full family.ged

# Verbose output (show detailed progress)
gedcom-tools -v validate --full family.ged

# Output as JSON (useful for piping to other tools)
gedcom-tools --format json validate --full family.ged

# Quiet mode (errors only, no progress indicators)
gedcom-tools -q validate --full family.ged

# Strict mode (version-specific validation)
gedcom-tools validate --strict 5.5.1 family.ged
gedcom-tools validate --strict 5.5.5 --full family.ged
```

**Options:**

| Option | Description |
|--------|-------------|
| `--quick` | Fail fast on first error (default) |
| `--full` | Collect all errors with IDs and line numbers |
| `--strict VERSION` | Enable strict validation for GEDCOM version (5.5.1 or 5.5.5) |

**Strict Mode Checks:**

When `--strict` is specified, additional validation is performed:
- Required HEAD sub-records: GEDC, GEDC/VERS, SOUR, CHAR
- Version mismatch warning if declared version differs from specified
- Line length limit (255 characters per GEDCOM spec)
- ANSEL encoding deprecation warning (5.5.5 only)

**Exit Codes:**

| Code | Meaning |
|------|---------|
| 0 | Validation passed (no errors, warnings allowed) |
| 1 | Validation failed (errors found) |
| 2 | Usage error (invalid arguments, file not found) |

#### stats (coming soon)

Display statistics about a GEDCOM file.

#### search (coming soon)

Search for individuals within a GEDCOM file.

## Requirements

- Python 3.11 or higher

## License

MIT License. See [LICENSE](LICENSE) for details.
