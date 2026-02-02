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
| `--no-color` | Disable colored output |

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

#### stats

Display statistics about a GEDCOM file including record counts, demographics, timeline, and data quality metrics.

```bash
# Basic statistics
gedcom-tools stats family.ged

# Limit top-N lists (surnames, locations, etc.)
gedcom-tools stats family.ged --top 5

# JSON output (for programmatic use)
gedcom-tools --format json stats family.ged

# Quiet mode (one-line summary)
gedcom-tools -q stats family.ged

# Verbose mode (with timing)
gedcom-tools -v stats family.ged
```

**Options:**

| Option | Description |
|--------|-------------|
| `--top N` | Number of items in top-N lists (default: 10) |

**Statistics Provided:**

- **Record Counts**: Individuals, families, sources, unique locations
- **Timeline**: Date span, earliest/latest births, century distribution, average lifespan
- **Tree Structure**: Generation depth, largest families by child count, average children per family
- **Demographics**: Gender distribution, top surnames, top lineages, top given names (male/female)
- **Marriage Stats**: Total marriages, percentage with dates
- **Locations**: Most common places in the tree
- **Data Completeness**: Birth/death date coverage, marriage date coverage, source citations, notes, media, orphans, estimated living
- **Life Events**: Age at first marriage (by gender and century), age at first child (by gender), spousal age gap
- **Family Size**: Children per family distribution with buckets (1, 2-3, 4-6, 7-9, 10+)
- **Birth Patterns**: Monthly distribution showing seasonal trends
- **Lifespan Trends**: Average lifespan by century (1700s, 1800s, 1900s, etc.)
- **Research Quality**: Birth date precision breakdown (full/partial/approximate/missing), occupation coverage, source depth (avg sources per person)

**Date Extraction:**
- Birth year: Uses BIRT/DATE, falls back to CHR/DATE (christening), then BAPM/DATE (baptism)
- Death year: Uses DEAT/DATE, falls back to BURI/DATE (burial)

**Surname Handling:**
- "Top Surnames" shows individual surname components (e.g., "García" and "López" separately)
- "Top Lineages" shows full SURN values (e.g., "García López" as one entry)

**Given Name Handling:**
- Extracts first given name from NAME tuple (e.g., "John William" → "John")
- GIVN sub-record overrides tuple extraction if present
- Reported separately for male and female individuals

**Lifespan Calculation:**
- Computed from individuals with both birth and death dates
- Filters out implausible values (negative or >120 years)
- Reports average, min, max, and sample size

**Source Coverage:**
- Counts individuals with at least one SOUR citation
- Checks both direct citations (INDI/SOUR) and event citations (BIRT/SOUR, DEAT/SOUR, etc.)

**Life Events:**
- Age at first marriage calculated from birth year and earliest marriage date
- Requires FAMS links between individuals and families
- Filters implausible ages (marriage age 12-80, parent age 12-70)
- Shows breakdown by gender and century for historical trends

**Birth Patterns:**
- Extracts month from full birth dates (e.g., "2 OCT 1850")
- Excludes approximate dates (ABT, BEF, etc.) for accuracy
- Shows 12-month distribution with peak month

**Research Quality:**
- Date precision categorizes birth dates as:
  - Full: day/month/year (e.g., "2 OCT 1850")
  - Partial: month/year or year only (e.g., "1850")
  - Approximate: prefixed dates (ABT, BEF, AFT, etc.)
  - Missing: no birth date recorded
- Occupation coverage: percentage with OCCU records
- Source depth: average SOUR citations per person (recursive count)

#### search (coming soon)

Search for individuals within a GEDCOM file.

## Documentation

Detailed documentation for each command:

- [Validate Command](docs/validate.md) - Error/warning codes and strict mode
- [Stats Command](docs/stats.md) - Statistics output and JSON schema

## Requirements

- Python 3.11 or higher

## License

MIT License. See [LICENSE](LICENSE) for details.
