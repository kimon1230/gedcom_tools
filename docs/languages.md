# Languages Command

The `languages` command detects languages used in the text content of a GEDCOM
file -- notes, biographical stories, and event descriptions.

## Usage

```bash
gedcom-tools languages <file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {text,json}` | Output format (default: text) |
| `-v, --verbose` | Show timing with processing phases |
| `-q, --quiet` | One-line summary |
| `--min-length N` | Minimum text length for detection (default: 10). Shorter texts are skipped as unreliable |
| `--language LANG` | Show records in a specific language (name or ISO 639-1 code) |

## Modes

### Aggregate Mode (default)

Without `--language`, the command scans all text content and shows a breakdown
table of languages by category.

### Filter Mode (`--language`)

With `--language`, the command lists the specific persons, notes, and events
that contain text in that language. Accepts language names ("English", "Greek"),
ISO 639-1 codes ("en", "el"), or the special value "unknown" for unclassifiable
texts. Matching is case-insensitive.

## Categories

Text content is classified into three categories:

- **Notes** -- standalone top-level NOTE records not referenced by any individual or family
- **Stories** -- biographical notes attached directly to individuals
- **Events** -- notes on births, deaths, marriages, and other life events (on both INDI and FAM records)

Source citation notes (under SOUR records) are excluded from analysis.

## How It Works

1. Encoding is detected and the language detection models are loaded
2. A note index is built so pointer notes (`NOTE @N1@`) can be resolved and
   analyzed once (cached)
3. INDI and FAM records are walked, classifying each note into its category
4. Unreferenced top-level notes are classified last
5. Results are sorted by total count (aggregate) or by xref (filter)

In verbose mode, each of these five phases is shown with timing.

### Supported Languages

Arabic, Chinese, Czech, Danish, Dutch, English, Finnish, French, German, Greek,
Hebrew, Hungarian, Italian, Japanese, Korean, Latin, Norwegian Bokmal, Norwegian
Nynorsk, Polish, Portuguese, Romanian, Russian, Spanish, Swedish, Turkish,
Ukrainian.

## Output

### Text Output (Aggregate)

```
File: tree.ged
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

### Text Output (Filter)

```
File: tree.ged
Encoding: UTF-8

=== Greek (el) ===
  Texts analyzed: 42 (5 skipped, too short)

  Persons with biographical notes (3):
    Eleni Papadopoulos (@I5@)
    Nikolaos Andreou (@I12@)
    Maria Konstantinou (@I44@)

  Standalone notes (1):
    @N7@

  Events with notes (3):
    @I5@  BIRT  — Eleni Papadopoulos
    @F3@  MARR
    @F3@  (family note)
```

FAM-level notes that aren't under an event sub-record show as "(family note)"
with a null event tag.

### JSON Output (Aggregate)

```json
{
  "file": "tree.ged",
  "mode": "aggregate",
  "encoding": { "detected": "UTF-8", "has_bom": false, "declared": "UTF-8" },
  "languages": [
    { "language": "English", "code": "en", "notes": 10, "stories": 15, "events": 8, "total": 33 },
    { "language": "Greek", "code": "el", "notes": 2, "stories": 4, "events": 3, "total": 9 }
  ],
  "summary": { "total_texts": 42, "skipped_short": 5, "distinct_languages": 2, "min_length": 20 },
  "categories": {
    "notes": "Standalone top-level notes",
    "stories": "Biographical notes on individuals",
    "events": "Notes on births, deaths, marriages, and other events"
  }
}
```

### JSON Output (Filter)

```json
{
  "file": "tree.ged",
  "mode": "filter",
  "encoding": { "detected": "UTF-8", "has_bom": false, "declared": "UTF-8" },
  "language": "Greek",
  "code": "el",
  "persons": [
    { "xref": "@I5@", "name": "Eleni Papadopoulos" },
    { "xref": "@I12@", "name": "Nikolaos Andreou" },
    { "xref": "@I44@", "name": "Maria Konstantinou" }
  ],
  "notes": ["@N7@"],
  "events": [
    { "parent_xref": "@I5@", "event_tag": "BIRT", "name": "Eleni Papadopoulos" },
    { "parent_xref": "@F3@", "event_tag": "MARR", "name": null },
    { "parent_xref": "@F3@", "event_tag": null, "name": null }
  ],
  "summary": {
    "person_count": 3,
    "note_count": 1,
    "event_count": 3,
    "total_matches": 7,
    "total_texts": 42,
    "skipped_short": 5,
    "min_length": 20
  }
}
```

### Quiet Mode

Aggregate: `2 language(s) detected across 42 text(s)`

Filter: `Greek: 3 persons, 1 note, 3 events`

Returns empty output when there are no results.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing |
| 2 | Usage error (file not found, invalid language) |

## Notes

- A person with multiple notes in the target language appears only once in
  filter results (deduplicated by xref)
- `event_tag` is null for FAM direct notes -- these are family-level notes not
  attached to a specific event
- Pointer notes are resolved and their text is analyzed once; the result is
  cached to avoid duplicate detection
- `--min-length` and `--language` can be combined
- Passing an unrecognized language name prints supported languages to stderr
  and exits with code 2
