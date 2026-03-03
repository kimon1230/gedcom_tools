# Export Command

The `export` command extracts all individuals and families from a GEDCOM file
into CSV or JSON format for use in spreadsheets, databases, and downstream
tools.

This is a **data extraction** command, distinct from the per-command
`--format json` which formats command results. The export command produces raw
tabular or structured data. For example, `gedcom-tools --format json stats`
formats stats output as JSON, while `gedcom-tools export --format json` exports
the raw individual and family records as a JSON document.

## Usage

```bash
gedcom-tools export <file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {csv,json}` | Export format (default: csv) |
| `--table {individuals,families}` | Table to export in CSV mode (default: individuals; ignored for JSON) |
| `--no-bom` | Omit UTF-8 BOM when writing CSV to a file |
| `-o, --output FILE` | Write to file instead of stdout |
| `--force` | Overwrite output file if it already exists |
| `--redact-living` | Replace names and dates of estimated-living individuals |
| `--max-age N` | Maximum age for living estimation (default: 110) |
| `-v, --verbose` | Show progress phases with timing |
| `-q, --quiet` | Errors only |
| `--no-color` | Disable colored progress output |

### Examples

```bash
# Export individuals as CSV to stdout
gedcom-tools export family.ged

# Export families table
gedcom-tools export family.ged --table families

# Export as JSON (includes both individuals and families)
gedcom-tools export family.ged --format json

# Write to file (CSV gets UTF-8 BOM for Excel compatibility)
gedcom-tools export family.ged -o individuals.csv

# Write to file without BOM
gedcom-tools export family.ged -o individuals.csv --no-bom

# JSON to file
gedcom-tools export family.ged --format json -o tree.json

# Redact living individuals
gedcom-tools export family.ged --redact-living

# Custom living threshold (90 years instead of default 110)
gedcom-tools export family.ged --redact-living --max-age 90

# Overwrite existing output file
gedcom-tools export family.ged -o individuals.csv --force
```

## CSV Format

### Individuals Table (default)

17 columns with a header row:

| Column | Description |
|--------|-------------|
| `xref` | GEDCOM cross-reference ID (e.g., `@I1@`) |
| `given_name` | Given name(s) from the primary NAME record |
| `surname` | Surname from the primary NAME record |
| `suffix` | Name suffix (Jr., Sr., III, etc.) |
| `sex` | Sex code: M, F, U, or X |
| `birth_date` | GEDCOM date string (e.g., `15 JAN 1850`, `ABT 1920`) |
| `birth_year` | Extracted numeric year (empty if unknown) |
| `birth_place` | Birth place string |
| `death_date` | GEDCOM date string |
| `death_year` | Extracted numeric year (empty if unknown) |
| `death_place` | Death place string |
| `burial_date` | Burial date string |
| `burial_place` | Burial place string |
| `occupations` | Occupations joined with `"; "` (see note below) |
| `source_count` | Number of SOUR citations (recursive) |
| `famc_xref` | Family-as-child cross-reference |
| `fams_xrefs` | Family-as-spouse cross-references, semicolon-delimited |

### Families Table (`--table families`)

10 columns with a header row:

| Column | Description |
|--------|-------------|
| `xref` | Family cross-reference ID (e.g., `@F1@`) |
| `husband_xref` | Husband individual cross-reference |
| `husband_name` | Husband display name (denormalized from INDI) |
| `wife_xref` | Wife individual cross-reference |
| `wife_name` | Wife display name (denormalized from INDI) |
| `marriage_date` | GEDCOM date string |
| `marriage_year` | Extracted numeric year (empty if unknown) |
| `marriage_place` | Marriage place string |
| `child_count` | Number of children in this family |
| `children_xrefs` | Child cross-references, semicolon-delimited |

### CSV Conventions

- **Encoding**: UTF-8. When writing to a file (`-o`), a UTF-8 BOM (U+FEFF)
  is prepended for Excel compatibility. Use `--no-bom` to suppress it. Stdout
  output never includes a BOM (it would break piping to `diff`, `grep`, etc.).
- **Multi-valued fields**: `fams_xrefs` and `children_xrefs` are
  semicolon-delimited within a single cell (e.g., `@F1@;@F7@`).
- **Occupations**: Multiple OCCU records are joined with `"; "` (semicolon
  followed by a space). This distinguishes the join delimiter from semicolons
  that may appear within a single occupation value. **This join is a display
  convention and is not guaranteed to be reversible.** Use JSON format if you
  need structured occupation data.
- **Empty fields**: Empty string (not "N/A" or "None").
- **Null years**: `birth_year` and `death_year` render as empty when unknown
  (not "None" or 0).
- **Quoting**: Standard CSV quoting via Python's `csv.writer` — commas and
  double quotes in values are handled automatically.

## JSON Format

JSON output always includes both individuals and families regardless of the
`--table` flag.

```json
{
  "meta": {
    "file": "family.ged",
    "encoding": "UTF-8",
    "gedcom_tools_version": "1.0.0",
    "individual_count": 150,
    "family_count": 45,
    "redacted_living": false
  },
  "individuals": [
    {
      "xref": "@I1@",
      "given_name": "John",
      "surname": "Smith",
      "suffix": "",
      "sex": "M",
      "birth_date": "15 JAN 1850",
      "birth_year": 1850,
      "birth_place": "London, England",
      "death_date": "ABT 1920",
      "death_year": 1920,
      "death_place": "New York, USA",
      "burial_date": "",
      "burial_place": "",
      "occupations": ["Blacksmith"],
      "source_count": 3,
      "famc_xref": "@F5@",
      "fams_xrefs": ["@F1@"],
      "alt_names": [
        {"given": "Johann", "surname": "Schmidt"}
      ],
      "notes": ["Immigrated to New York circa 1880."]
    }
  ],
  "families": [
    {
      "xref": "@F1@",
      "husband_xref": "@I1@",
      "husband_name": "John Smith",
      "wife_xref": "@I2@",
      "wife_name": "Mary Jones",
      "marriage_date": "3 JUN 1875",
      "marriage_year": 1875,
      "marriage_place": "St. Mary's Church, London",
      "child_count": 2,
      "children_xrefs": ["@I3@", "@I4@"]
    }
  ]
}
```

### JSON-Specific Fields

These fields appear in JSON but not in CSV:

- **`alt_names`**: Array of `{"given": ..., "surname": ...}` objects from
  alternate NAME records (ROMN, FONE, or additional NAME lines).
- **`notes`**: Array of inline note strings attached to the individual. Only
  inline NOTE text is included; pointer-referenced notes (`NOTE @N1@`) are
  skipped.

### JSON Conventions

- `birth_year`, `death_year`, `marriage_year`: `null` when unknown (not 0 or
  omitted).
- `occupations`: Native JSON array (not joined like CSV).
- `ensure_ascii=False`: Unicode characters are preserved directly (e.g.,
  `"Müller"` not `"M\\u00fcller"`).
- `meta.gedcom_tools_version`: Always reflects the running version (never
  hardcoded).
- `meta.redacted_living`: `true` when `--redact-living` was active, `false`
  otherwise.

## Living Person Estimation

The `--redact-living` flag replaces names, dates, and places of individuals
estimated to be living. The estimation algorithm:

1. **Has death year** → not living
2. **Has burial date** → not living
3. **No birth year** (and no death/burial) → unknown, **not redacted**
4. **Birth year > max_age years ago** → not living
5. **Birth year <= max_age years ago AND no death** → estimated living

The `--max-age` option controls the threshold (default: 110 years, inclusive).
A person born exactly `max_age` years ago is still considered possibly living.

### What Gets Redacted

**Individuals (CSV and JSON):**
- `given_name` → `"Living"`
- `surname`, `suffix`, dates, places, occupations → cleared (empty)
- `alt_names`, `notes` → cleared (JSON only)
- `xref`, `sex`, `source_count`, `famc_xref`, `fams_xrefs` → preserved

**Families:**
- When a spouse is estimated living, their denormalized `husband_name` or
  `wife_name` is replaced with `"Living"`. All other family fields (xrefs,
  dates, child links) are preserved.

### Design Note

Individuals with no birth year and no death record are **not** redacted. This
conservative approach avoids blanket-redacting poorly-sourced historical
individuals (the majority of records in many files). If you need stricter
privacy, filter by birth year in your downstream processing.

## Date String Format

Date strings (`birth_date`, `death_date`, etc.) contain ged4py's canonical
representation of the GEDCOM date value, not necessarily the verbatim original
text. For example, `ABOUT 1850` may appear as `ABT 1850`, and whitespace may be
normalized. The canonical form is valid GEDCOM and preserves all semantic
content.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing |
| 2 | Usage error (file not found, invalid arguments) |

## Known Limitations

- Date strings are ged4py's canonical form, not verbatim original GEDCOM text
- `--redact-living` requires a birth year to estimate living status; individuals
  with no birth year and no death year are not redacted
- Only inline NOTE text is exported; pointer-referenced notes (`NOTE @N1@`) are
  skipped
- `--table` is ignored for JSON format (always includes both individuals and
  families)
- The `occupations` CSV join with `"; "` is not guaranteed to be reversible;
  use JSON for structured data

## Related Commands

- [`search`](search.md) -- find individuals using flexible query syntax
- [`compare`](compare.md) -- match individuals across two different files
- [`duplicates`](duplicates.md) -- find duplicate individuals within a file
- [`stats`](stats.md) -- summary statistics for a single GEDCOM file
