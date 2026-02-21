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

<details>
<summary><b>Sample: Quick validation</b> (royal92.ged)</summary>

```
$ gedcom-tools validate royal92.ged

✓ [1/4] Detecting encoding
✓ [2/4] Parsing structure
✓ [3/4] Validating references
✓ [4/4] Checking semantics
File: royal92.ged
Encoding: ANSEL
Records: 1422 FAM, 1 HEAD, 3010 INDI, 1 SUBM, 1 TRLR

Errors (5):
  [E012] Birth date before parent's birth
    Line 1813: @I169@ Born (1931) before parent @I812@ (1980)
  ...

✗ Invalid (5 error(s), 33 warning(s))
```

Quick mode fails fast on the first error. Use `--full` to see everything.

</details>

<details>
<summary><b>Sample: Full validation</b> (royal92.ged)</summary>

```
$ gedcom-tools validate --full royal92.ged

✓ [1/4] Detecting encoding
✓ [2/4] Parsing structure
✓ [3/4] Validating references
✓ [4/4] Checking semantics
File: royal92.ged
Encoding: ANSEL
Records: 1422 FAM, 1 HEAD, 3010 INDI, 1 SUBM, 1 TRLR

Errors (5):
  [E012] Birth date before parent's birth
    Line 1813: @I169@ Born (1931) before parent @I812@ (1980)
  [E012] Birth date before parent's birth
    Line 12853: @I1476@ Born (1477) before parent @I1474@ (1479)
  [E012] Birth date before parent's birth
    Line 12899: @I1484@ Born (1484) before parent @I2865@ (1512)
  [E012] Birth date before parent's birth
    Line 22895: @I2947@ Born (1873) before parent @I2948@ (1941)
  [E011] Death date before birth date
    Line 22905: @I2948@ Death (1906) before birth (1941)

Warnings (33):
  [W005] Missing SUBM record
    Line 1: No SUBM (submitter) record referenced in HEAD
  [W014] Individual with no family connections
    Line 1391: @I128@ Individual has no family connections
  [W014] Individual with no family connections
    Line 3543: @I359@ Individual has no family connections
  [W014] Individual with no family connections
    Line 8497: @I970@ Individual has no family connections
  [W025] Child born before parents' marriage
    Line 24039: @F101@ Child @I315@ born (1964) before marriage (1967)
  ...
  [W020] Parent too young at child's birth
    Line 1813: @I169@ Mother @I812@ was -49 at birth
  [W022] Father too old at child's birth
    Line 7294: @I812@ Father @I2946@ was 108 at birth
  ...

✗ Invalid (5 error(s), 33 warning(s))
```

Every issue includes a code, description, line number, and actionable message.

</details>

<details>
<summary><b>Sample: JSON validation output</b> (royal92.ged)</summary>

```json
$ gedcom-tools --format json validate --full royal92.ged

{
  "file": "royal92.ged",
  "valid": false,
  "encoding": {
    "detected": "ANSEL",
    "has_bom": false,
    "declared": "ANSEL"
  },
  "record_counts": {
    "HEAD": 1,
    "SUBM": 1,
    "INDI": 3010,
    "FAM": 1422,
    "TRLR": 1
  },
  "summary": {
    "errors": 5,
    "warnings": 33
  },
  "issues": [
    {
      "code": "W005",
      "description": "Missing SUBM record",
      "severity": "warning",
      "message": "No SUBM (submitter) record referenced in HEAD",
      "line": 1
    },
    {
      "code": "E012",
      "description": "Birth date before parent's birth",
      "severity": "error",
      "message": "Born (1931) before parent @I812@ (1980)",
      "line": 1813,
      "xref": "@I169@"
    },
    ...
  ]
}
```

</details>

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

<details>
<summary><b>Sample: Full stats output</b> (royal92.ged — 3,010 individuals)</summary>

```
$ gedcom-tools stats royal92.ged

File: royal92.ged
Encoding: ANSEL

=== Record Counts ===
  Individuals:         3,010
  Families:            1,422
  Sources:                 0
  Locations:             715

=== Timeline ===
  Date Span:        686 - 1991 (1305 years)
  Earliest (year):  Charles Martel (b. 686)
  Earliest (gen):   Peter of_Yugoslavia (generation 80)
  Avg Lifespan:     50.9 years (n=1,285, range 0-99)

  By Century:
    1000s:            27 (0.9%)
    1100s:            36 (1.2%)
    1200s:            58 (1.9%)
    1300s:            57 (1.9%)
    1400s:            77 (2.6%)
    1500s:            65 (2.2%)
    1600s:           129 (4.3%)
    1700s:           235 (7.8%)
    1800s:           521 (17.3%)
    1900s:           493 (16.4%)
    600s:              1 (0.0%)
    700s:              8 (0.3%)
    800s:             14 (0.5%)
    900s:             13 (0.4%)

=== Tree Structure ===
  Generation Depth: 80 generations
  Avg Children/Fam: 1.4 (across 1,422 families)

  Largest Families:
    1. Hanover/Charlotte (@F39@)     15 children
    2. (Longshanks)/of_Castile (@F464@)     15 children
    3. William_I/Hanover (@F435@)     13 children

=== Demographics ===
  Gender:
    Male:            1686 (56.0%)
    Female:          1311 (43.6%)
    Unknown:           13 (0.4%)

  Top Surnames:
     1. Hanover                 70 (2.3%)
     2. Romanov                 66 (2.2%)
     3. Stuart                  34 (1.1%)
     4. Windsor                 29 (1.0%)
     5. Howard                  29 (1.0%)
     6. Tudor                   21 (0.7%)
     7. Seymour                 20 (0.7%)
     8. Oldenburg               18 (0.6%)
     9. Hohenzollern            18 (0.6%)
    10. Wurttemberg             18 (0.6%)

  Top Given Names (Male):
     1. John                    70 (4.2%)
     2. William                 64 (3.8%)
     3. Henry                   62 (3.7%)
     4. Charles                 62 (3.7%)
     5. Thomas                  42 (2.5%)
     6. Frederick               39 (2.3%)
     7. George                  37 (2.2%)
     8. Edward                  36 (2.1%)
     9. Alexander               30 (1.8%)
    10. James                   27 (1.6%)

  Top Given Names (Female):
     1. Elizabeth               57 (4.3%)
     2. Anne                    56 (4.3%)
     3. Mary                    54 (4.1%)
     4. Margaret                51 (3.9%)
     5. Marie                   40 (3.1%)
     6. Louise                  35 (2.7%)
     7. Maria                   35 (2.7%)
     8. Catherine               31 (2.4%)
     9. Charlotte               25 (1.9%)
    10. Victoria                23 (1.8%)

=== Locations ===
  Top Places:
     1. Westminster,Abbey,London,England          36 (2.7%)
     2. St. Denis,France                          27 (2.0%)
     3. Paris,France                              26 (1.9%)
     4. St. James Palace,London,England           26 (1.9%)
     5. Stockholm,Sweden                          25 (1.9%)
     6. Windsor Castle,Berkshire,England          20 (1.5%)
     7. London,England                            17 (1.3%)
     8. Copenhagen,Denmark                        17 (1.3%)
     9. Buckingham,Palace,London,England          15 (1.1%)
    10. Athens,Greece                             12 (0.9%)

=== Data Completeness ===
  Birth/Baptism Date:    1734 / 3,010 (57.6%)
  Death/Burial Date:     1692 / 3,010 (56.2%)
  Marriage Date:          555 / 1,422 (39.0%)
  Has Sources:              0 / 3,010 (0.0%)
  Has Notes:                0 / 3,010 (0.0%)
  Has Media:                0 / 3,010 (0.0%)
  Isolated:                 3 / 3,010 (0.1%)
  Estimated Living:       352 / 3,010 (11.7%)

=== Life Events ===
  Age at First Marriage:
    Male:    27.0 years (n=394, range 12-71)
    Female:  22.6 years (n=433, range 12-65)
    By Century:
      1100s:  M 19.8, F 17.0 (n=19)
      1200s:  M 19.6, F 17.4 (n=30)
      1300s:  M 24.8, F 20.1 (n=32)
      1400s:  M 22.2, F 17.1 (n=51)
      1500s:  M 21.2, F 20.5 (n=38)
      1600s:  M 23.5, F 20.7 (n=53)
      1700s:  M 27.0, F 21.1 (n=109)
      1800s:  M 29.2, F 22.8 (n=241)
      1900s:  M 29.0, F 26.9 (n=230)
  Age at First Child:
    Male:    30.3 years (n=420, range 16-68)
    Female:  24.6 years (n=361, range 16-56)
  Spousal Age Gap: 7.7 years avg (n=571, range 0-49)

=== Family Size ===
  Average: 2.1 children per family (n=971)
  Distribution:
    1 child:          584 (60%)
    2-3 children:     239 (25%)
    4-6 children:     106 (11%)
    7-9 children:      31 (3%)
    10+ children:      11 (1%)
  Largest: 15 children

=== Birth Patterns ===
  By Month:
    Jan:    37 (   8%)   Feb:    21 (   4%)   Mar:    36 (   7%)
    Apr:    48 (  10%)   May:    36 (   7%)   Jun:    56 (  12%)
    Jul:    42 (   9%)   Aug:    47 (  10%)   Sep:    42 (   9%)
    Oct:    40 (   8%)   Nov:    51 (  10%)   Dec:    30 (   6%)
  Peak: Jun (12%)

=== Lifespan Trends ===
  By Century:
    1000s:  47.1 years (n=27)
    1100s:  41.5 years (n=36)
    1200s:  34.2 years (n=57)
    1300s:  37.1 years (n=56)
    1400s:  39.4 years (n=74)
    1500s:  38.2 years (n=63)
    1600s:  38.9 years (n=127)
    1700s:  53.8 years (n=232)
    1800s:  61.7 years (n=502)
    1900s:  45.2 years (n=77)

=== Research Quality ===
  Birth Date Precision:
    Full (day/month/year):      464 (15%)
    Partial (month/year):      1174 (39%)
    Approximate:                 96 (3%)
    Missing:                   1276 (42%)
  Occupation recorded: 0 / 3,010 (0.0%)
  Source citations:    None found
```

</details>

<details>
<summary><b>Sample: Quiet mode</b> (royal92.ged)</summary>

```
$ gedcom-tools -q stats royal92.ged

3,010 individuals, 1,422 families, 0 sources, 715 locations
```

</details>

<details>
<summary><b>Sample: Verbose mode</b> (royal92.ged)</summary>

```
$ gedcom-tools -v stats royal92.ged

✓ [1/3] Detecting encoding (1.16s)
✓ [2/3] Collecting data (3.39s)
✓ [3/3] Calculating statistics (40ms)
File: royal92.ged
Encoding: ANSEL
...
```

Verbose mode adds per-step timing to help identify performance bottlenecks on large files.

</details>

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
- **Data Completeness**: Birth/death date coverage, marriage date coverage, source citations, notes, media, isolated, estimated living
- **Life Events**: Age at first marriage (by gender and century), age at first child (by gender), spousal age gap
- **Family Size**: Children per family distribution with buckets (1, 2-3, 4-6, 7-9, 10+)
- **Birth Patterns**: Monthly distribution showing seasonal trends
- **Lifespan Trends**: Average lifespan by century (1700s, 1800s, 1900s, etc.)
- **Research Quality**: Birth date precision breakdown (full/partial/approximate/missing), occupation coverage, source depth (avg sources per person)

**Date Extraction:**
- Birth year: Uses BIRT/DATE, falls back to CHR/DATE (christening), then BAPM/DATE (baptism)
- Death year: Uses DEAT/DATE, falls back to BURI/DATE (burial)

**Surname Handling:**
- "Top Surnames" shows individual surname components (e.g., "Garcia" and "Lopez" separately)
- "Top Lineages" shows full SURN values (e.g., "Garcia Lopez" as one entry)

**Given Name Handling:**
- Extracts first given name from NAME tuple (e.g., "John William" -> "John")
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

#### isolated

Find individuals with no effective family connections using graph analysis.

```bash
# Find isolated individuals
gedcom-tools isolated family.ged

# JSON output
gedcom-tools --format json isolated family.ged

# Quiet mode (one-line summary)
gedcom-tools -q isolated family.ged
```

<details>
<summary><b>Sample: Isolated analysis</b> (royal92.ged)</summary>

```
$ gedcom-tools isolated royal92.ged

File: royal92.ged

=== Isolated Analysis ===
  Total individuals:     3010
  Isolated individuals:     3 (0.1%)
    Singletons:             3
    Isolated pairs:         0

=== Singletons ===
  These individuals have no effective family connections.
  They may need to be linked to a family or removed if added in error.

  1. Charles William Frederick Cavendish-Bentwi (@I359@) M
  2. Issue_Unknown (@I128@) M
  3. Anne of_Bourbon-Parma (@I970@) F
```

</details>

**What it detects:**

- **Singletons**: Individuals in no family record at all (component size 1)
- **Isolated pairs**: Two individuals connected only to each other (component size 2)

Uses graph analysis to identify connected components in the family tree.

#### languages

Detect languages used in GEDCOM text content (notes, stories, events) using fast-langdetect.

```bash
# Detect languages in a GEDCOM file
gedcom-tools languages family.ged

# Filter for a specific language
gedcom-tools languages family.ged --language Greek

# Filter using ISO code + JSON output
gedcom-tools --format json languages family.ged --language el

# Set minimum text length for detection
gedcom-tools languages family.ged --min-length 30

# Quiet mode
gedcom-tools -q languages family.ged
```

<details>
<summary><b>Sample: Aggregate language detection</b> (family.ged)</summary>

```
$ gedcom-tools languages family.ged

File: family.ged
Encoding: UTF-8

=== Language Detection ===
  Texts analyzed: 42 (5 skipped, too short)

  Language             Notes  Stories  Events   Total
  ─────────────────────────────────────────────────────
  English                 10       15       8      33
  Greek                    2        4       3       9
  ─────────────────────────────────────────────────────
  Total                   12       19      11      42

  Distinct languages: 2 (excluding unknown)

  Notes   = standalone top-level notes
  Stories = biographical notes on individuals
  Events  = notes on births, deaths, marriages, and other events
  Tip: use --language <name> to list individual records in that language.
```

</details>

<details>
<summary><b>Sample: Filter by language</b> (family.ged)</summary>

```
$ gedcom-tools languages family.ged --language Greek

File: family.ged
Encoding: UTF-8

=== Greek (el) ===
  Texts analyzed: 42 (5 skipped, too short)

  Persons with biographical notes (2):
    Eleni Papadopoulos (@I5@)
    Nikolaos Andreou (@I12@)

  Standalone notes (1):
    @N7@

  Events with notes (2):
    @I5@  BIRT  — Eleni Papadopoulos
    @F3@  MARR
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--language LANG` | Filter for a specific language (name or ISO 639-1 code) |
| `--min-length N` | Minimum text length for detection (default: 10) |

**Categories:**

- **Notes**: Standalone top-level notes not referenced by any individual or family
- **Stories**: Biographical notes directly attached to individuals
- **Events**: Notes on births, deaths, marriages, and other life events

**Supported languages:** 26 languages via fast-langdetect, including Arabic, Chinese, English, French, German, Greek, and more. Also accepts "unknown" for unclassifiable texts.

## Documentation

Detailed documentation for each command:

- [Validate Command](docs/validate.md) - Error/warning codes and strict mode
- [Stats Command](docs/stats.md) - Statistics output and JSON schema
- [Isolated Command](docs/isolated.md) - Detecting unconnected individuals
- [Languages Command](docs/languages.md) - Language detection and filtering

## Sample Data

The sample outputs in this README use **royal92.ged**, a classic GEDCOM test file
containing 3,010 individuals across 80 generations of European royal genealogy
(dating from 686 AD to 1991). Created by Denis R. Reid in 1992, it remains one
of the most widely used GEDCOM files for testing and benchmarking genealogy
software.

## Requirements

- Python 3.11 or higher

## License

MIT License. See [LICENSE](LICENSE) for details.
