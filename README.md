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
| `-v, --verbose` | Enable verbose output |
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

# Output as JSON
gedcom-tools --format json validate --full family.ged
```

**Options:**

| Option | Description |
|--------|-------------|
| `--quick` | Fail fast on first error (default) |
| `--full` | Collect all errors with IDs and line numbers |

#### stats (coming soon)

Display statistics about a GEDCOM file.

#### search (coming soon)

Search for individuals within a GEDCOM file.

## Requirements

- Python 3.11 or higher

## License

MIT License. See [LICENSE](LICENSE) for details.
