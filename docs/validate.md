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

### Structural Errors (E001-E009)

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
| E009 | **ANSEL not supported** - ANSEL encoding is not supported by this tool |

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
| W003 | **Line too long** - Line exceeds 255 characters (soft warning) |
| W004 | **Custom tag** - Non-standard tag starting with underscore |
| W005 | **Missing SUBM** - No submitter record found |

### Orphaned Records (W010-W015)

| Code | Description |
|------|-------------|
| W010 | **Orphaned NOTE** - NOTE record not referenced by any other record |
| W011 | **Orphaned OBJE** - OBJE (media) record not referenced |
| W012 | **Orphaned SOUR** - SOUR (source) record not referenced |
| W013 | **Orphaned REPO** - REPO (repository) record not referenced |
| W014 | **Isolated individual** - INDI with no family connections |
| W015 | **Empty family** - FAM with no HUSB, WIFE, or CHIL |

### Semantic Warnings (W020-W025)

| Code | Description | Threshold |
|------|-------------|-----------|
| W020 | **Parent too young** | Father < 12 or Mother < 12 at child's birth |
| W021 | **Mother too old** | Mother > 50 at child's birth |
| W022 | **Father too old** | Father > 80 at child's birth |
| W023 | **Implausible lifespan** | Age at death > 120 years |
| W024 | **Marriage before birth** | Marriage date before spouse's birth |
| W025 | **Child before marriage** | Child born before parents' marriage |

### Strict Mode Warnings (W030-W032)

Only checked when `--strict` is specified.

| Code | Description |
|------|-------------|
| W030 | **ANSEL deprecated** | ANSEL encoding deprecated in GEDCOM 5.5.5 |
| W031 | **Version mismatch** | Declared version differs from --strict version |
| W032 | **Line too long (strict)** | Line exceeds 255 characters (strict check) |

## Output Formats

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
  "errors": [
    {
      "code": "E001",
      "description": "Unresolved cross-reference",
      "line": 10,
      "xref": "@F99@",
      "message": "Reference to undefined @F99@",
      "context": "FAMC reference in @I1@"
    }
  ],
  "warnings": []
}
```

## Notes

### Encoding Detection

The validator auto-detects encoding:
1. Checks for BOM (UTF-8, UTF-16)
2. Reads CHAR declaration in header
3. Defaults to UTF-8 if no BOM or CHAR declaration found

### Strict Mode

Strict mode (`--strict 5.5.1` or `--strict 5.5.5`) enables:
- Required header checks (GEDC, VERS, SOUR, CHAR)
- Version mismatch warnings
- Strict line length enforcement (255 chars)
- ANSEL deprecation warning (5.5.5 only)
