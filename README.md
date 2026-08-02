# gedcom-tools

CLI utility for GEDCOM file validation, analysis, and search.

## Installation

```bash
pip install kimon-gedcom-tools

# With optional GraphViz chart generation (pedigree, relationship, hourglass, bowtie)
pip install kimon-gedcom-tools[graph]
```

Or for development:

```bash
git clone https://github.com/kimon1230/gedcom_tools.git
cd gedcom_tools
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
| `--ascii` | Use ASCII-only decorations (`[OK]`, `[!]`, `->`, `<->`, `x`, `-`, `--`) instead of `✓ ✗ → ↔ × ─ —` |

Output is safe to redirect and to pipe. It is written as UTF-8 regardless of the
system codepage, so `gedcom-tools search tree.ged 'surname=Müller' > out.txt`
produces a UTF-8 file on Windows as well as on Unix; and piping into a consumer
that stops reading early — `gedcom-tools --format json stats tree.ged | head` —
exits 0 rather than reporting a broken pipe as a failure.

`--ascii` is for consoles whose fonts cannot draw the decorations; it can also
be set with `GEDCOM_TOOLS_ASCII=1`. Setting `PYTHONIOENCODING` yourself takes
precedence over the UTF-8 default.

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

# Show detected text for each match (audit what was classified)
gedcom-tools languages family.ged --language Spanish --show-text

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
    Theodora Zografou (@I12@)

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
| `--show-text` | Show detected text for each match (requires `--language`) |
| `--min-length N` | Minimum text length for detection (default: 10) |

**Categories:**

- **Notes**: Standalone top-level notes not referenced by any individual or family
- **Stories**: Biographical notes directly attached to individuals
- **Events**: Notes on births, deaths, marriages, and other life events

**Supported languages:** 26 languages via fast-langdetect, including Arabic, Chinese, English, French, German, Greek, and more. Also accepts "unknown" for unclassifiable texts.

#### search

Search for individuals matching flexible query criteria including name, dates, places, sex, and family relationships.

```bash
# Search by name (substring match)
gedcom-tools search family.ged 'Smith'

# Phonetic matching (Soundex by default)
gedcom-tools search family.ged 'surname~Schmidt'

# Double Metaphone (better for European name variants)
gedcom-tools search family.ged 'surname~Schmidt' --phonetic metaphone

# Multiple criteria (AND logic)
gedcom-tools search family.ged 'surname:Smith born:1800-1850 place:London'

# Exact match
gedcom-tools search family.ged 'surname=Smith sex=F'

# Wildcard patterns
gedcom-tools search family.ged 'surname:Sm*th'

# Regex patterns
gedcom-tools search --regex family.ged 'surname:Sm[a-i]th'

# Relationship traversal (find all descendants of @I1@)
gedcom-tools search family.ged 'ancestor:@I1@'

# Fuzzy date matching (approximate dates ±2 years)
gedcom-tools search family.ged 'born:1850' --fuzzy-dates 2

# Count matches only
gedcom-tools search family.ged 'surname:Smith' --count

# Limit results
gedcom-tools search family.ged 'Smith' --limit 10

# JSON output
gedcom-tools --format json search family.ged 'surname:Smith'

# Quiet mode (names and xrefs only)
gedcom-tools -q search family.ged 'Smith'
```

<details>
<summary><b>Sample: Search results</b></summary>

```
$ gedcom-tools search family.ged 'surname:Smith born:1800-1850'

File: family.ged
Query: surname:Smith born:1800-1850

=== Search Results (3 of 1,000 individuals) ===

  John Smith (1820-1895) [@I42@]
    Born: 1820, London, England
    Died: 1895
    Matched: surname contains "Smith", born in 1800-1850

  Mary Smith (1835-1910) [@I67@]
    Born: 1835, Manchester, England
    Died: 1910, London, England
    Matched: surname contains "Smith", born in 1800-1850

  William Smith (1848-?) [@I103@]
    Born: 1848
    Matched: surname contains "Smith", born in 1800-1850
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--regex` | Treat `:` operator values as regex patterns |
| `--phonetic {soundex,metaphone}` | Phonetic algorithm for `~` operator (default: soundex) |
| `--fuzzy-dates N` | Expand approximate dates ±N years |
| `--limit N` | Maximum number of results (default: unlimited) |
| `--count` | Show match count only |

**Query syntax:**

- **Fields**: `name`, `given`, `surname`, `born`, `died`, `place`, `sex`, `ancestor`, `descendant`
- **Operators**: `:` (substring), `=` (exact), `~` (phonetic — Soundex or Double Metaphone via `--phonetic`)
- Bare terms (no field prefix) search the `name` field
- Name fields also search alternative name records (ROMN/FONE transliterations)
- See [Search Command](docs/search.md) for full query syntax and examples

#### compare

Compare two GEDCOM files to find matching individuals using probabilistic record linkage.

```bash
# Compare two GEDCOM files
gedcom-tools compare tree_a.ged tree_b.ged

# Only show certain matches
gedcom-tools compare tree_a.ged tree_b.ged --show-matches certain

# List individuals unique to each file
gedcom-tools compare tree_a.ged tree_b.ged --list-unique

# Adjust thresholds
gedcom-tools compare tree_a.ged tree_b.ged --certain-threshold 0.90 --probable-threshold 0.70

# JSON output
gedcom-tools --format json compare tree_a.ged tree_b.ged

# Reject sex mismatches
gedcom-tools compare tree_a.ged tree_b.ged --reject-sex-mismatch

# Quiet mode
gedcom-tools -q compare tree_a.ged tree_b.ged

# Verbose mode (per-field scores)
gedcom-tools -v compare tree_a.ged tree_b.ged
```

<details>
<summary><b>Sample: Compare two files</b> (tree_a.ged vs tree_b.ged)</summary>

```
$ gedcom-tools compare tree_a.ged tree_b.ged

File A: tree_a.ged
File B: tree_b.ged
Encoding: UTF-8 / UTF-8

=== Summary ===
  Individuals in A:      100
  Individuals in B:      120
  Certain matches:        15
  Probable matches:        8
  Unique to A:            77
  Unique to B:            97

=== Certain Matches (15) ===
  John Smith (1850-1920) [A:@I1@] ↔ John Smith (1850-1920) [B:@I10@]  score: 0.95
    Birth Place: "London, England" (A) vs "London, Middlesex, England" (B)

=== Probable Matches (8) ===
  Mary Johnson (1872-1945) [A:@I2@] ↔ Maria Johnson (1873-1945) [B:@I11@]  score: 0.72
    Given Name: "Mary" (A) vs "Maria" (B)
    Birth Year: "1872" (A) vs "1873" (B)

  Tip: use --list-unique to see names of unmatched individuals.
```

</details>

<details>
<summary><b>Sample: Quiet mode</b> (tree_a.ged vs tree_b.ged)</summary>

```
$ gedcom-tools -q compare tree_a.ged tree_b.ged

15 certain, 8 probable, 77 unique to tree_a.ged, 97 unique to tree_b.ged
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--certain-threshold F` | Minimum score for certain match (default: 0.85) |
| `--probable-threshold F` | Minimum score for probable match (default: 0.65) |
| `--show-matches {all,certain,probable}` | Which matches to show (default: all) |
| `--list-unique` | List individuals unique to each file |
| `--limit N` | Max items per output section (text default: 50, JSON default: unlimited) |
| `--reject-sex-mismatch` | Treat sex mismatches as hard reject |
| `--phonetic {soundex,metaphone}` | Phonetic algorithm for blocking and scoring (default: soundex) |

**How it works:**

- Uses weighted Jaro-Winkler string similarity across 7 fields: surname, given name, birth year, death year, birth place, death place, and sex
- Multi-pass blocking for efficient comparison of large files
- Three-tier classification: certain, probable, non-match
- Greedy one-to-one deduplication ensures each individual appears in at most one match
- See [Compare Command](docs/compare.md) for full methodology details

#### duplicates

Scan a single GEDCOM file for potential duplicate individuals using the same scoring engine as compare.

```bash
# Find duplicates in a file
gedcom-tools duplicates family.ged

# Only show certain matches
gedcom-tools duplicates family.ged --show-matches certain

# Adjust thresholds
gedcom-tools duplicates family.ged --certain-threshold 0.90 --probable-threshold 0.70

# JSON output
gedcom-tools --format json duplicates family.ged

# Reject sex mismatches
gedcom-tools duplicates family.ged --reject-sex-mismatch

# Quiet mode
gedcom-tools -q duplicates family.ged

# Verbose mode (per-field scores)
gedcom-tools -v duplicates family.ged
```

<details>
<summary><b>Sample: Find duplicates</b> (family.ged)</summary>

```
$ gedcom-tools duplicates family.ged

File: family.ged

=== Duplicate Scan Summary ===
  Individuals scanned:   500
  Certain duplicates:      3
  Probable duplicates:     5

=== Certain Duplicates (3) ===
  John Smith (1850-1920) [@I1@] ↔ John Smith (1850-1920) [@I42@]  score: 0.95
    Birth Place: "London, England" vs "London, Middlesex, England"

  Mary Jones (1872-1945) [@I3@] ↔ Maria Jones (1873-1945) [@I88@]  score: 0.91
    Given Name: "Mary" vs "Maria"
    Birth Year: "1872" vs "1873"

=== Probable Duplicates (5) ===
  ...
```

</details>

<details>
<summary><b>Sample: Quiet mode</b> (family.ged)</summary>

```
$ gedcom-tools -q duplicates family.ged

3 certain, 5 probable
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--certain-threshold F` | Minimum score for certain duplicate (default: 0.85) |
| `--probable-threshold F` | Minimum score for probable duplicate (default: 0.65) |
| `--show-matches {all,certain,probable}` | Which matches to show (default: all) |
| `--limit N` | Max items per output section (text default: 50, JSON default: unlimited) |
| `--reject-sex-mismatch` | Treat sex mismatches as hard reject |
| `--phonetic {soundex,metaphone}` | Phonetic algorithm for blocking and scoring (default: soundex) |

**How it works:**

- Reuses the compare command's scoring engine (weighted Jaro-Winkler, multi-pass blocking, three-tier classification) on a single file
- Self-pairs and symmetric duplicates are filtered out before scoring
- Greedy one-to-one deduplication ensures each individual appears in at most one match
- See [Duplicates Command](docs/duplicates.md) for full details

#### relationship

Determine the genealogical relationship between two individuals using Lowest Common Ancestor analysis.

```bash
# Find relationship between two individuals
gedcom-tools relationship family.ged @I1@ @I2@

# Show half-relationship prefix
gedcom-tools relationship family.ged @I1@ @I2@ --type all

# Show multiple relationship paths
gedcom-tools relationship family.ged @I1@ @I2@ --paths 5

# JSON output
gedcom-tools --format json relationship family.ged @I1@ @I2@

# Quiet mode (description only)
gedcom-tools -q relationship family.ged @I1@ @I2@

# Limit search depth
gedcom-tools relationship family.ged @I1@ @I2@ --generations 50
```

<details>
<summary><b>Sample: Relationship query</b></summary>

```
$ gedcom-tools relationship family.ged @I1@ @I3@

File: family.ged

=== Relationship ===

  John Smith (1850-1920) [@I1@]
  James Smith (1880-1945) [@I3@]

  James Smith is the son of John Smith.
```

</details>

<details>
<summary><b>Sample: Multiple paths</b></summary>

```
$ gedcom-tools relationship family.ged @I1@ @I3@ --paths 3

File: family.ged

=== Relationships (2 found) ===

  John Smith (1850-1920) [@I1@]
  James Smith (1880-1945) [@I3@]

  1. James Smith is the son of John Smith.
  2. James Smith is a 1st cousin of John Smith.
```

</details>

<details>
<summary><b>Sample: Quiet mode</b></summary>

```
$ gedcom-tools -q relationship family.ged @I1@ @I3@

James Smith is the son of John Smith.
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--type {blood,all}` | Relationship display: `blood` (default) suppresses half-prefix; `all` shows it |
| `--paths N` | Number of relationship paths to show (default: 1) |
| `--generations N` | Maximum ancestor search depth (default: 30) |

**How it works:**

- BFS upward from both individuals to find common ancestors, then classifies each `(gen_primary, gen_target)` pair into a relationship type (parent, sibling, cousin, etc.)
- Detects half-relationships via shared-parent counting and spouse-pairing analysis
- Results sorted by shortest path, blood over half, male line preference
- See [Relationship Command](docs/relationship.md) for full algorithm details

#### export

Export all individuals and families from a GEDCOM file to CSV or JSON for use in
spreadsheets, databases, and downstream tools.

```bash
# Export individuals as CSV to stdout
gedcom-tools export family.ged

# Export families table
gedcom-tools export family.ged --table families

# Export as JSON (always includes both individuals and families)
gedcom-tools export family.ged --format json

# Write CSV to file (includes UTF-8 BOM for Excel compatibility)
gedcom-tools export family.ged -o individuals.csv

# Write CSV without BOM
gedcom-tools export family.ged -o individuals.csv --no-bom

# JSON to file
gedcom-tools export family.ged --format json -o tree.json

# Redact living individuals (names/dates replaced)
gedcom-tools export family.ged --redact-living

# Custom living threshold
gedcom-tools export family.ged --redact-living --max-age 90
```

<details>
<summary><b>Sample: CSV individuals</b></summary>

```
$ gedcom-tools export family.ged

xref,given_name,surname,suffix,sex,birth_date,birth_year,birth_place,death_date,death_year,death_place,burial_date,burial_place,occupations,source_count,famc_xref,fams_xrefs
@I1@,John,Smith,,M,15 JAN 1850,1850,"London, England",ABT 1920,1920,"New York, USA",,,,3,@F5@,@F1@;@F7@
```

</details>

<details>
<summary><b>Sample: JSON export</b></summary>

```json
$ gedcom-tools export family.ged --format json

{
  "meta": {
    "file": "family.ged",
    "encoding": "UTF-8",
    "gedcom_tools_version": "1.0.0",
    "individual_count": 150,
    "family_count": 45,
    "redacted_living": false,
    "redacted_count": 0
  },
  "individuals": [
    {
      "xref": "@I1@",
      "given_name": "John",
      "surname": "Smith",
      "birth_year": 1850,
      "death_year": 1920,
      "occupations": ["Blacksmith"],
      "alt_names": [{"given": "Johann", "surname": "Schmidt"}],
      "notes": ["Immigrated to New York circa 1880."]
    }
  ],
  "families": [...]
}
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--to {csv,json}` | Export format (default: csv) |
| `--format {csv,json}` | Deprecated alias for `--to`; still accepted |
| `--table {individuals,families}` | Table to export in CSV mode (default: individuals; ignored for JSON) |
| `--no-bom` | Omit UTF-8 BOM when writing CSV to a file |
| `-o, --output FILE` | Write to file instead of stdout |
| `--force` | Overwrite output file if it already exists |
| `--redact-living` | Replace names and dates of estimated-living individuals |
| `--max-age N` | Maximum plausible lifespan in years for living estimation (default: 110, minimum: 1) |

**Note on `--format`:** For most commands, `--format json` means "format
command results as JSON." For `export`, `--format json` means "export data as
JSON." This is intentional — export has no text result mode; it produces data
in a specific format. See [Export Command](docs/export.md) for full details.

**CSV output:**
- UTF-8 BOM included only when writing to a file (`-o`), for Excel compatibility. Use `--no-bom` to suppress.
- Multi-valued fields (family xrefs, children) are semicolon-delimited within cells.
- See [Export Command](docs/export.md) for full column reference.

**Living estimation:**
- Uses birth year, death records, and any custom living tags in the file to estimate whether someone is living
- Unknown means living: an individual with no usable birth date and no death record **is** redacted, so a file thin on dates loses more rows than a birth-year-only rule would take
- A living couple's `marriage_date`, `marriage_year` and `marriage_place` are cleared too — one living spouse is enough, since a wedding date and venue re-identify the pair
- `meta.redacted_count` in JSON reports how many individuals were actually redacted; `meta.redacted_living` only reports that the flag was set

#### convert

Convert a GEDCOM file between character encodings with automatic CHAR header
update, BOM handling, and NFC normalization.

```bash
# Convert ANSEL to UTF-8
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged

# Override source encoding for non-standard files
gedcom-tools convert weird.ged --from latin-1 --to utf-8 -o fixed.ged

# Preview without writing
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged --dry-run

# Add BOM for Windows tools
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged --bom

# Convert to UTF-16
gedcom-tools convert tree.ged --to unicode -o tree_utf16.ged
```

<details>
<summary><b>Sample: Convert ANSEL to UTF-8</b> (royal92.ged)</summary>

```
$ gedcom-tools convert royal92.ged --to utf-8 -o royal92_utf8.ged

✓ [1/2] Detecting encoding
✓ [2/2] Transcoding
File: royal92.ged

=== Conversion ===
  Source encoding: ANSEL
  Target encoding: UTF-8
  Lines:           30,682
  NFC normalized:  yes
  BOM:             none
  Output:          royal92_utf8.ged
```

</details>

<details>
<summary><b>Sample: Dry run</b></summary>

```
$ gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged --dry-run

✓ [1/2] Detecting encoding
✓ [2/2] Transcoding
File: old_tree.ged

=== Conversion ===
  Source encoding: ANSEL
  Target encoding: UTF-8
  Lines:           3,432
  NFC normalized:  yes
  BOM:             none
  Output:          tree_utf8.ged

  (dry run -- no file written)
```

</details>

<details>
<summary><b>Sample: Quiet mode</b></summary>

```
$ gedcom-tools -q convert old_tree.ged --to utf-8 -o tree_utf8.ged

Converted old_tree.ged (ANSEL → UTF-8) → tree_utf8.ged
```

</details>

**Options:**

| Option | Description |
|--------|-------------|
| `--to {utf-8,ansel,ascii,unicode}` | Target encoding (required) |
| `--from CODEC` | Override source encoding detection (any Python codec name) |
| `-o, --output FILE` | Output file path (required) |
| `--force` | Overwrite existing output file |
| `--bom` | Add byte order mark to output |
| `--no-normalize` | Skip NFC Unicode normalization |
| `--dry-run` | Preview conversion without writing output |

**How it works:**

- Reads the file as raw bytes, decodes using the detected (or overridden) source codec, applies NFC normalization for ANSEL sources, updates the CHAR header, re-encodes in the target codec, and writes the output
- Source encoding is auto-detected from the CHAR header. Use `--from` with any Python codec name for non-standard files (latin-1, cp1252, iso-8859-7, etc.)
- Target is restricted to the four GEDCOM-standard character sets to ensure a valid CHAR header
- Warns if any lines exceed the GEDCOM 255-byte limit in the target encoding
- See [Convert Command](docs/convert.md) for full details

#### filter

Filter and transform GEDCOM files by stripping tags, removing record types, or
extracting subtrees centered on a specific individual.

```bash
# Remove all custom (underscore-prefixed) tags
gedcom-tools filter tree.ged -o clean.ged --strip-custom-tags

# Remove notes and sources
gedcom-tools filter tree.ged -o minimal.ged --strip-notes --strip-sources

# Remove specific tags (repeatable)
gedcom-tools filter tree.ged -o clean.ged --strip-tag OCCU --strip-tag RESI

# Extract an individual with all ancestors
gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@

# Extract subtree with limited depth, descendants, and spouses
gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@ --ancestors 3 --descendants 2 --include-spouses
```

<details>
<summary><b>Sample: Strip custom tags</b></summary>

```
$ gedcom-tools filter tree.ged -o clean.ged --strip-custom-tags

✓ [1/4] Reading input
✓ [2/4] Parsing GEDCOM
✓ [3/4] Filtering
✓ [4/4] Writing output
File: tree.ged

=== Filter Results ===

  Record Type       Source   Output  Removed
  --------------- -------- -------- --------
  Individuals          500      500        0
  Families             200      200        0
  --------------- -------- -------- --------
  Total                703      703        0

  Output: clean.ged
```

Custom tag lines are removed from within records (line-level), so record counts
may not change — but the output file will be smaller.

</details>

<details>
<summary><b>Sample: Subtree extraction</b></summary>

```
$ gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@ --ancestors 3 --descendants 1 --include-spouses

✓ [1/4] Reading input
✓ [2/4] Parsing GEDCOM
✓ [3/4] Filtering
✓ [4/4] Writing output
File: tree.ged

=== Filter Results ===

  Record Type       Source   Output  Removed
  --------------- -------- -------- --------
  Individuals          500       18      482
  Families             200        8      192
  Sources               30        5       25
  --------------- -------- -------- --------
  Total                732       33      699

  Dangling references cleaned: 12

  Output: subtree.ged
```

</details>

<details>
<summary><b>Sample: Quiet mode</b></summary>

```
$ gedcom-tools -q filter tree.ged -o clean.ged --strip-notes

Filtered tree.ged (780 → 730 records) → clean.ged
```

</details>

**Strip options:**

| Option | Description |
|--------|-------------|
| `--strip-custom-tags` | Remove all custom (`_`-prefixed) tags |
| `--strip-notes` | Remove NOTE records and references |
| `--strip-sources` | Remove SOUR records and citations |
| `--strip-multimedia` | Remove OBJE records and references |
| `--strip-tag TAG` | Remove a specific tag (repeatable) |

**Subtree options:**

| Option | Description |
|--------|-------------|
| `--subtree XREF` | Extract subtree rooted at individual (e.g., `@I1@`) |
| `--ancestors N` | Max ancestor generations (default: unlimited) |
| `--descendants N` | Max descendant generations (default: 0) |
| `--include-spouses` | Include spouses of extracted individuals |

**How it works:**

- Parses GEDCOM at the line level (no ged4py reinterpretation) for lossless round-trip output
- Strip operations remove whole records and/or inline sub-lines, with automatic child-line cascading
- Subtree extraction uses BFS traversal on a directed parent-child graph, then transitively collects referenced SOUR/NOTE/OBJE/REPO records
- After filtering, dangling pointer references are cleaned and empty families are cascade-removed
- Encoding, BOM, and line endings are preserved from the input
- See [Filter Command](docs/filter.md) for full algorithm details

## Documentation

Detailed documentation for each command:

- [Validate Command](docs/validate.md) - Error/warning codes and strict mode
- [Stats Command](docs/stats.md) - Statistics output and JSON schema
- [Isolated Command](docs/isolated.md) - Detecting unconnected individuals
- [Languages Command](docs/languages.md) - Language detection and filtering
- [Search Command](docs/search.md) - Finding individuals with flexible query syntax
- [Compare Command](docs/compare.md) - Comparing individuals across files
- [Duplicates Command](docs/duplicates.md) - Finding duplicate individuals within a file
- [Relationship Command](docs/relationship.md) - Finding relationships between individuals
- [Export Command](docs/export.md) - Exporting individuals and families to CSV or JSON
- [Convert Command](docs/convert.md) - Converting between character encodings
- [Filter Command](docs/filter.md) - Filtering and transforming GEDCOM files

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
