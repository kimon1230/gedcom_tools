# Search Command

The `search` command finds individuals in a GEDCOM file using flexible query
syntax with substring, exact, phonetic, wildcard, and regex matching.

## Usage

```bash
gedcom-tools search <file> <query> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--regex` | Treat `:` operator values as regex patterns |
| `--fuzzy-dates N` | Expand approximate dates ±N years |
| `--limit N` | Maximum number of results (default: unlimited) |
| `--count` | Show match count only (ignores `--limit`) |
| `--format {text,json}` | Output format (default: text) |
| `-v, --verbose` | Show phase timing and Soundex codes |
| `-q, --quiet` | Minimal output (names and xrefs only) |
| `--no-color` | Disable colored output |

## How It Works

The command runs in 3-4 phases:

1. Collect individuals (names, dates, places, sex, alt names, pre-computed
   Soundex codes)
2. Build relationship graph (only when `ancestor:` or `descendant:` terms
   are present)
3. Match each individual against all query terms (AND logic)
4. Format results

All text matching is case-insensitive and Unicode-normalized (diacritics
removed). `café` matches `Cafe`, `smith` matches `SMITH`.

In verbose mode, each phase is shown with timing.

## Query Syntax

The query is a single string of space-separated terms. Quote the entire query
to prevent the shell from expanding `~` and `*`:

```bash
gedcom-tools search tree.ged 'surname~Schmidt born:1800-1850'
```

### Fields

| Field | Description |
|-------|-------------|
| `name` | Full name (given + surname), also the default for bare terms |
| `given` | Given (first) name only |
| `surname` | Surname (family name) only |
| `born` | Birth year or year range |
| `died` | Death year or year range |
| `place` | Birth or death place (searches both) |
| `sex` | Sex: M, F, U, or X (single character, case-insensitive) |
| `ancestor` | Relationship traversal (see [Relationship Queries](#relationship-queries)) |
| `descendant` | Relationship traversal (see [Relationship Queries](#relationship-queries)) |

Name fields (`name`, `given`, `surname`) also search alternative name records
(ROMN, FONE transliterations) attached to the individual.

Birth dates use a fallback chain: BIRT → CHR (christening) → BAPM (baptism).
Death dates fall back from DEAT → BURI (burial). Searching `born:1850` will
match an individual whose only recorded date is a christening in 1850.

### Operators

| Operator | Name | Description |
|----------|------|-------------|
| `:` | Substring | Value appears anywhere in the field (default) |
| `=` | Exact | Value matches the entire field |
| `~` | Phonetic | Soundex match (name fields only) |

The `~` operator is restricted to name fields (`name`, `given`, `surname`).
Using it on date or place fields produces an error.

The `=` operator does not support date ranges. Use `born:1800-1850` (with `:`),
not `born=1800-1850`.

### Bare Terms

A term without a field prefix searches the `name` field:

```bash
gedcom-tools search tree.ged 'Smith'        # same as name:Smith
gedcom-tools search tree.ged '~Schmidt'     # same as name~Schmidt
```

### Date Ranges

Date fields accept a single year or a year range (inclusive):

```bash
gedcom-tools search tree.ged 'born:1850'          # exact year
gedcom-tools search tree.ged 'born:1800-1850'     # inclusive range
gedcom-tools search tree.ged 'died:1920'
```

The start year must be before or equal to the end year. `born:1900-1800` is
rejected with a suggestion to swap the values.

### Wildcards

The `:` operator auto-detects `*` (any characters) and `?` (single character)
as wildcard patterns:

```bash
gedcom-tools search tree.ged 'surname:Sm*'        # starts with Sm
gedcom-tools search tree.ged 'surname:Sm?th'       # Sm_th (one char)
gedcom-tools search tree.ged 'place:*shire'        # ends with shire
```

Wildcard patterns require at least 3 non-wildcard characters to prevent overly
broad matches. Wildcards are disabled when `--regex` is active.

### Regex Patterns

The `--regex` flag treats `:` operator values as regular expressions:

```bash
gedcom-tools search tree.ged --regex 'surname:Sm[a-i]th'
gedcom-tools search tree.ged --regex 'surname:^Smith$'
gedcom-tools search tree.ged --regex 'given:\bJohn\b'
```

Regex mode only applies to the `:` operator. The `=` and `~` operators behave
normally regardless of `--regex`. Date and relationship fields are also
unaffected.

Patterns with nested quantifiers (e.g. `(a+)+`) are rejected to prevent
catastrophic backtracking. Invalid regex syntax produces an error with
a suggestion to use substring matching instead.

### Quoting

Use double quotes for values containing spaces:

```bash
gedcom-tools search tree.ged 'place:"New York"'
gedcom-tools search tree.ged 'place:"Los Angeles" sex:F'
```

Single quotes are not treated as value delimiters inside the query, so names
like O'Brien work without escaping:

```bash
gedcom-tools search tree.ged "surname:O'Brien"
```

### Multiple Terms

Multiple terms are separated by spaces. All terms must match (AND logic):

```bash
gedcom-tools search tree.ged 'surname:Smith born:1800-1850'
gedcom-tools search tree.ged 'surname:Smith sex:F place:London'
gedcom-tools search tree.ged 'given:John surname:Smith born:1800-1900'
```

## Relationship Queries

Relationship terms use BFS (breadth-first search) to traverse the family
graph:

| Term | Meaning |
|------|---------|
| `ancestor:@I1@` | Find everyone who **descends from** @I1@ |
| `descendant:@I5@` | Find everyone who is an **ancestor of** @I5@ |

The term name describes the role of the specified individual: `ancestor:@I1@`
means "@I1@ is an ancestor" and returns the descendants.

```bash
# All descendants of individual @I1@
gedcom-tools search tree.ged 'ancestor:@I1@'

# All ancestors of individual @I5@
gedcom-tools search tree.ged 'descendant:@I5@'

# Descendants of @I1@ who have surname Smith
gedcom-tools search tree.ged 'ancestor:@I1@ surname:Smith'

# People who descend from @I1@ AND are ancestors of @I5@
gedcom-tools search tree.ged 'ancestor:@I1@ descendant:@I5@'
```

The specified individual (root) is excluded from results -- a person is not
their own ancestor or descendant.

Traversal is capped at 50 generations. The xref must be the full GEDCOM
identifier including `@` delimiters (e.g. `@I1@`, not `I1`). If the xref is
not found in the file, an error is shown suggesting to search for the
individual first.

## Fuzzy Date Matching

The `--fuzzy-dates` flag widens date matching for approximate dates:

```bash
gedcom-tools search tree.ged 'born:1850' --fuzzy-dates 2
```

This expands the search window by ±N years, but **only for individuals whose
dates are marked as approximate** in GEDCOM (ABT, EST, CAL, BEF, AFT, BET
prefixes). Exact dates are matched exactly regardless of `--fuzzy-dates`.

For example, with `--fuzzy-dates 2` and query `born:1850`:
- "ABT 1852" matches (approximate, within ±2 of 1850)
- "1852" does not match (exact date, outside range)

## Output

### Text Output

```
File: /path/to/tree.ged
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

When `--limit` truncates results, a notice is shown:

```
  (results limited to 50 -- use --limit 0 for all)
```

Use `--limit 0` to disable truncation and show all results.

When no results match:

```
No matches found.
Tip: try fewer criteria, a wider date range, or phonetic matching (surname~Schmidt).
```

When the file contains no individuals:

```
No individuals found in file.
```

In verbose mode, phonetic match details include the Soundex code:

```
    Matched: surname "Smythe" sounds like "Smith" (S530)
```

Match detail labels vary by match type:

| Match Type | Example |
|------------|---------|
| Substring | `surname contains "Smith"` |
| Exact | `surname exactly "Smith"` |
| Wildcard | `surname matches pattern "Sm*th"` |
| Phonetic | `surname "Smythe" sounds like "Smith"` |
| Regex | `surname matches "^Sm.*th$"` |
| Date range | `born in 1800-1850` |

### Text Output (Quiet)

Names and xrefs only, no headers or match details:

```
  John Smith (1820-1895) [@I42@]
  Mary Smith (1835-1910) [@I67@]
  William Smith (1848-?) [@I103@]
```

### Text Output (Count)

Bare integer:

```
3
```

### JSON Output

```json
{
  "file": "/path/to/tree.ged",
  "query": "surname:Smith born:1800-1850",
  "encoding": {
    "detected": "UTF-8",
    "has_bom": false,
    "declared": "UTF-8"
  },
  "total_individuals": 1000,
  "match_count": 3,
  "truncated": false,
  "matches": [
    {
      "xref": "@I42@",
      "given_name": "John",
      "surname": "Smith",
      "sex": "M",
      "birth_year": 1820,
      "birth_year_approximate": false,
      "birth_place": "London, England",
      "death_year": 1895,
      "death_year_approximate": false,
      "death_place": "",
      "alt_names": [],
      "match_details": [
        {
          "field": "surname",
          "value": "Smith",
          "query": "Smith",
          "type": "contains"
        },
        {
          "field": "born",
          "value": "1820",
          "query": "1800-1850",
          "type": "range"
        }
      ]
    }
  ]
}
```

Match detail `type` values: `contains`, `exactly`, `pattern`, `sounds_like`,
`regex`, `range`.

### JSON Output (Count)

```json
{"count": 3}
```

## Common Pitfalls

**Shell tilde expansion:** If your shell expands `~` into a home directory
path, the phonetic operator won't work as expected. Always wrap the query in
single quotes:

```bash
# Wrong — shell expands ~ to /home/user
gedcom-tools search tree.ged surname~Schmidt

# Correct
gedcom-tools search tree.ged 'surname~Schmidt'
```

**Shell wildcard expansion:** Similarly, `*` and `?` can be expanded by the
shell. Quote the query to prevent this.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing |
| 2 | Usage error (file not found, invalid query syntax) |

## Known Limitations

- Soundex is designed for English names and may not work well for names from
  other languages
- Place matching is string-based; no geocoding or geographic lookup
- Wildcard patterns require at least 3 non-wildcard characters
- Relationship traversal is capped at 50 generations
- All results are returned by default; use `--limit` to cap output for large
  result sets

## Related Commands

- [`validate`](validate.md) -- check file structure and data issues
- [`stats`](stats.md) -- summary statistics for a GEDCOM file
- [`isolated`](isolated.md) -- find unconnected individuals using graph analysis
- [`languages`](languages.md) -- detect languages in notes and events
- [`compare`](compare.md) -- cross-file individual matching
