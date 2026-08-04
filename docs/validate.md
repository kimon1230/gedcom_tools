# Validate Command

The `validate` command checks GEDCOM files for structural errors and data issues.

## Usage

```bash
gedcom-tools validate <file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--quick` | Fail fast on first error (default) |
| `--full` | Collect all errors with IDs and line numbers |
| `--strict {5.5.1,5.5.5}` | Validate against a specific GEDCOM version |
| `--no-color` | Disable colored output |
| `--ascii` | ASCII-only decorations in progress output and results |

### Modes

- **Quick mode** (default): Stops at the first error. Fast for checking if a file is valid.
- **Full mode**: Collects all errors and warnings. Useful for fixing multiple issues.
- **Strict mode**: Enables version-specific validation checks.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Valid (no errors, warnings allowed) |
| 1 | Invalid (errors found) |
| 2 | Usage error (bad arguments, file not found) |

## Error Codes

Errors indicate problems that make the file invalid or unusable.

### Structural Errors (E001-E008)

| Code | Description |
|------|-------------|
| E001 | **Unresolved cross-reference** - Reference to undefined record (e.g., FAMC @F99@ where @F99@ doesn't exist) |
| E002 | **Duplicate cross-reference** - Same XREF ID used for multiple records |
| E003 | **Invalid level number** - Level must be 0-99 and increment by at most 1 |
| E004 | **Malformed GEDCOM line** - Line doesn't match GEDCOM format |
| E005 | **Missing HEAD record** - File must start with HEAD |
| E006 | **Missing TRLR record** - File must end with TRLR |
| E007 | **Content after TRLR** - No records allowed after TRLR |
| E008 | **Decode failure** - Cannot decode file with detected encoding |

### Semantic Errors (E010-E012)

| Code | Description |
|------|-------------|
| E010 | **Ancestry cycle** - Individual is their own ancestor (impossible genealogy) |
| E011 | **Death before birth** - Death date is earlier than birth date |
| E012 | **Birth before parent** - Individual born before their parent was born |

### Strict Mode Errors (E013-E016)

Only checked when `--strict` is specified.

| Code | Description |
|------|-------------|
| E013 | **Missing GEDC** - HEAD must contain GEDC sub-record |
| E014 | **Missing VERS** - GEDC must contain VERS sub-record |
| E015 | **Missing SOUR** - HEAD must contain SOUR sub-record |
| E016 | **Missing CHAR** - HEAD must contain CHAR sub-record |

## Warning Codes

Warnings indicate potential issues that don't make the file invalid.

### Formatting Warnings (W002-W005)

| Code | Description |
|------|-------------|
| W002 | **Trailing whitespace** - Line has spaces/tabs at end |
| W003 | **Line too long** - Line exceeds 255 bytes (soft warning) |
| W004 | **Custom tag** - Non-standard tag starting with underscore |
| W005 | **Missing SUBM** - No submitter record found |

Per-line warnings (W002, W003, and W032 under `--strict`) report the first 10
occurrences of each code, then one summary line giving the number suppressed.
A file with trailing whitespace on every line would otherwise produce one
warning per line — millions of them on a large file — burying everything else.

### Orphaned Records (W010-W015)

| Code | Description |
|------|-------------|
| W010 | **Orphaned NOTE** - NOTE record not referenced by any other record |
| W011 | **Orphaned OBJE** - OBJE (media) record not referenced |
| W012 | **Orphaned SOUR** - SOUR (source) record not referenced |
| W013 | **Orphaned REPO** - REPO (repository) record not referenced |
| W014 | **Isolated individual** - INDI with no family connections |
| W015 | **Empty family** - FAM with no HUSB, WIFE, or CHIL |

A record counts as referenced if a pointer to it appears anywhere inside another record, at any nesting depth — a NOTE cited under a SOUR under a BIRT event is not orphaned.

### Reference Warnings (W016-W017)

| Code | Description |
|------|-------------|
| W016 | **Asymmetric child link** - FAM lists individual as CHIL but individual has no matching FAMC, or individual has FAMC pointing to family but family doesn't list them as CHIL |
| W017 | **Asymmetric spouse link** - FAM lists individual as HUSB/WIFE but individual has no matching FAMS, or individual has FAMS pointing to family but family doesn't list them as HUSB/WIFE |

These checks detect broken bidirectional links between INDI and FAM records. In valid GEDCOM, every FAM.CHIL should have a corresponding INDI.FAMC and vice versa. The same applies to HUSB/WIFE and FAMS. Only flagged when both the INDI and FAM records exist — if either is missing, E001 (unresolved cross-reference) covers it instead.

### Semantic Warnings (W020-W029)

| Code | Description | Threshold |
|------|-------------|-----------|
| W020 | **Parent too young** | Father < 12 or Mother < 12 at child's birth |
| W021 | **Mother too old** | Mother > 80 at child's birth |
| W022 | **Father too old** | Father > 80 at child's birth |
| W023 | **Implausible lifespan** | Age at death > 120 years |
| W024 | **Marriage before birth** | Marriage date before spouse's birth |
| W025 | **Child before marriage** | Child born before parents' marriage |
| W026 | **Siblings born too close** | Siblings born < 9 months apart (excluding twins) |
| W027 | **Multiple SEX records** | Individual has more than one SEX sub-record |
| W028 | **Invalid SEX value** | SEX value is not M, F, U, or X |
| W029 | **Sex-role mismatch** | Individual recorded as HUSB but has SEX F, or recorded as WIFE but has SEX M |

Age and date thresholds are defined in `src/gedcom_tools/constants.py`.

**W026 known limitations:**
- Requires month-level precision on both birth dates — year-only dates are skipped
- Twins (same birth month) are excluded automatically
- Only checks siblings within the same FAM record
- Uses Gregorian calendar only (Julian dates are not converted)

### Strict Mode Warnings (W030-W032)

Only checked when `--strict` is specified.

| Code | Description |
|------|-------------|
| W030 | **ANSEL deprecated** | ANSEL encoding deprecated in GEDCOM 5.5.5 |
| W031 | **Version mismatch** | Declared version differs from --strict version |
| W032 | **Line too long (strict)** | Line exceeds 255 bytes (strict check) |

### Media Warnings (W033-W034)

| Code | Description |
|------|-------------|
| W033 | **OBJE missing FILE** - Top-level OBJE record has no FILE sub-record |
| W034 | **FILE missing FORM** - FILE sub-record within OBJE has no FORM (media type) |

These check structural integrity of multimedia object records. A valid OBJE should contain at least one FILE sub-record, and each FILE should specify its FORM (e.g., `jpeg`, `pdf`). Only top-level OBJE records are checked — inline OBJE references within INDI or FAM records are not validated.

## Output Formats

### Quiet Mode

With `-q`, only errors are shown (no file info, no warnings, no summary). If the file
is valid, there is no output.

```
[E001] Unresolved cross-reference
    Line 10: @F99@ Reference to undefined @F99@
    → FAMC reference in @I1@
```

### Text (default)

```
[E001] Unresolved cross-reference
    Line 10: @F99@ Reference to undefined @F99@
    → FAMC reference in @I1@
```

### JSON

```bash
gedcom-tools --format json validate --full file.ged
```

```json
{
  "file": "file.ged",
  "valid": false,
  "encoding": {
    "detected": "UTF-8",
    "has_bom": true,
    "declared": "UTF-8"
  },
  "record_counts": {
    "HEAD": 1,
    "INDI": 3,
    "FAM": 2,
    "TRLR": 1
  },
  "summary": {
    "errors": 1,
    "warnings": 0
  },
  "issues": [
    {
      "code": "E001",
      "severity": "error",
      "description": "Unresolved cross-reference",
      "message": "Reference to undefined @F99@",
      "line": 10,
      "xref": "@I1@"
    }
  ]
}
```

## Notes

### Encoding Detection

The validator auto-detects encoding:
1. Checks for BOM (UTF-8, UTF-16)
2. Reads CHAR declaration in header
3. Defaults to UTF-8 if no BOM or CHAR declaration found
4. Supports ANSEL encoding (common in older GEDCOM files)

### Strict Mode

Strict mode (`--strict 5.5.1` or `--strict 5.5.5`) enables:
- Required header checks (GEDC, VERS, SOUR, CHAR)
- Version mismatch warnings
- Strict line length enforcement (255 bytes)
- ANSEL deprecation warning (5.5.5 only)

## Related Commands

- [`search`](search.md) -- find individuals using flexible query syntax
- [`stats`](stats.md) -- summary statistics for a GEDCOM file
- [`isolated`](isolated.md) -- detect unconnected individuals
- [`languages`](languages.md) -- detect languages in notes and events
- [`compare`](compare.md) -- cross-file individual matching
- [`duplicates`](duplicates.md) -- find duplicate individuals within a file
- [`relationship`](relationship.md) -- determine genealogical relationships
