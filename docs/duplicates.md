# Duplicates Command

The `duplicates` command scans a single GEDCOM file for potential duplicate
individuals using the same probabilistic record linkage engine as the
[`compare`](compare.md) command.

## Usage

```bash
gedcom-tools duplicates <file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {text,json}` | Output format (default: text) |
| `-v, --verbose` | Show timing and per-field scores |
| `-q, --quiet` | One-line summary |
| `--certain-threshold F` | Minimum score for certain duplicate (default: 0.85) |
| `--probable-threshold F` | Minimum score for probable duplicate (default: 0.65) |
| `--show-matches {all,certain,probable}` | Which matches to show (default: all) |
| `--limit N` | Max items per output section (text default: 50, JSON default: unlimited) |
| `--reject-sex-mismatch` | Treat sex mismatches as hard reject (score 0.0) |
| `--phonetic {soundex,metaphone}` | Phonetic algorithm for blocking and scoring (default: soundex) |
| `--max-block-size N` | Max individuals sharing a blocking key before the group is skipped (default: 500) |
| `--no-color` | Disable colored output |
| `--ascii` | ASCII-only decorations in progress output and results |

## How It Works

The command runs in three phases:

1. Read the file and extract individuals (name, dates, places, sex)
2. Find duplicates: multi-pass blocking, weighted Jaro-Winkler scoring, greedy
   one-to-one deduplication
3. Format results

### Differences from Compare

The `compare` command matches individuals *across* two different files. The
`duplicates` command matches individuals *within* a single file:

| Aspect | Compare | Duplicates |
|--------|---------|------------|
| Files | Two input files (A, B) | Single input file |
| Self-pairs | Not possible (different files) | Filtered out (`@I1@` vs `@I1@`) |
| Symmetric pairs | Not possible (A→B direction) | Collapsed (`(@I1@, @I2@)` = `(@I2@, @I1@)`) |
| Deduplication | Separate `used_a`/`used_b` sets | Single `used` set (each individual in at most one pair) |
| Unique listing | `--list-unique` shows unmatched | Not applicable |

All other aspects — scoring, blocking, classification, thresholds — are
identical.

### Scoring

Uses the same weighted Jaro-Winkler scoring as `compare` across 7 fields.
See [Compare: Scoring Approach](compare.md#scoring-approach) for field weights,
string similarity, phonetic bonus, year proximity bands, and place comparison
details.

The `--phonetic metaphone` option uses Double Metaphone for blocking and scoring,
improving recall for European name variants. See
[Compare: Multi-Pass Blocking](compare.md#multi-pass-blocking) for details.

### Block Size Cap

Groups larger than `--max-block-size` (default 500) are skipped, because scoring
a group costs time proportional to the square of its size. A file where 600
people share `SMITH|1850s` finds no duplicates inside that group.

The run says so rather than quietly reporting fewer duplicates. Any skipped
group produces a stderr warning:

```
Warning: 2 blocking groups exceeded --max-block-size 500 and were skipped, so some matches may be missing.
  Re-run with a larger --max-block-size to include them; scoring cost grows with the square of the group size.
```

and JSON output carries `oversized_blocks_skipped` with the same number, since a
stderr warning never reaches a consumer piping JSON. The count is of distinct
blocking keys, so one 600-member group counts once. The warning is printed in
every output mode, `--quiet` included.

Raise the cap to include the group at the cost of a slower run, or narrow the
input to avoid it. See [Compare: Block Size Cap](compare.md#block-size-cap).

### Classification

| Classification | Criteria |
|----------------|----------|
| Certain | Score >= certain_threshold AND >= 4 comparable fields |
| Probable | Score >= probable_threshold |
| Non-match | Score < probable_threshold (not shown) |

The `insufficient_data` flag is set when fewer than 3 comparable fields exist or
when no corroborating fields (dates, places) were compared. These matches are
annotated with `(low confidence)` in text output.

### Greedy Deduplication

Pairs are sorted by descending score. Each individual can appear in at most one
matched pair. Once an individual is claimed by a higher-scoring pair, it is
excluded from lower-scoring pairs.

Note: this means transitive duplicates are not fully reported. If I1↔I2 (score
0.92) and I1↔I3 (score 0.88), only I1↔I2 is shown. I3 remains unmatched. Use
`--limit 0` and inspect the probable section for additional leads.

## Output

### Text Output

```
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

  William Brown (1900-?) [@I10@] ↔ Wm Brown (1900-1965) [@I55@]  score: 0.88
    Given Name: "William" vs "Wm"
    Death Year: "None" vs "1965"

=== Probable Duplicates (5) ===
  ...
```

When `--show-matches certain` is used, the probable section is hidden (summary
counts still reflect the full scan). When `--show-matches probable` is used, the
certain section is hidden. Verbose mode adds a per-field score breakdown below
each match.

### Text Output (Quiet)

Single line:

```
3 certain, 5 probable
```

### Text Output (Verbose)

Verbose mode shows per-field scores and sex penalty (if applicable):

```
  John Smith (1850-1920) [@I1@] ↔ John Smith (1850-1920) [@I42@]  score: 0.95
    Birth Place: "London, England" vs "London, Middlesex, England"
    [Scores: Surname 1.00, Given Name 1.00, Birth Year 1.00, Death Year 1.00, Birth Place 0.85, Sex 1.00]
```

When a sex mismatch penalty is applied:

```
    [Scores: Surname 1.00, Given Name 0.90, Birth Year 1.00, Sex mismatch ×0.70]
```

### JSON Output

```json
{
  "file": "family.ged",
  "encoding": {
    "detected": "UTF-8",
    "has_bom": false,
    "declared": "UTF-8"
  },
  "total_individuals": 500,
  "certain_duplicates": [
    {
      "individual_a": {
        "xref": "@I1@",
        "name": "John Smith",
        "given_name": "John",
        "surname": "Smith",
        "sex": "M",
        "birth_year": 1850,
        "birth_place": "London, England",
        "death_year": 1920,
        "death_place": null
      },
      "individual_b": {
        "xref": "@I42@",
        "name": "John Smith",
        "given_name": "John",
        "surname": "Smith",
        "sex": "M",
        "birth_year": 1850,
        "birth_place": "London, Middlesex, England",
        "death_year": 1920,
        "death_place": null
      },
      "score": 0.95,
      "classification": "certain",
      "field_scores": {
        "Surname": 1.0,
        "Given Name": 1.0,
        "Birth Year": 1.0,
        "Death Year": 1.0,
        "Birth Place": 0.85,
        "Sex": 1.0
      },
      "differences": [
        {
          "field": "Birth Place",
          "value_a": "London, England",
          "value_b": "London, Middlesex, England"
        }
      ]
    }
  ],
  "certain_duplicates_total": 3,
  "probable_duplicates": [],
  "probable_duplicates_total": 5
}
```

The `*_total` fields reflect the full count before any `--limit` truncation or
`--show-matches` filtering, so consumers always know the complete picture.

The `oversized_blocks_skipped` key is added only when at least one blocking
group was dropped for exceeding `--max-block-size`; its absence means nothing
was capped:

```json
{
  "total_individuals": 5000,
  "certain_duplicates_total": 3,
  "probable_duplicates_total": 5,
  "oversized_blocks_skipped": 2
}
```

The `insufficient_data` key is only present when `true`:

```json
{
  "score": 0.72,
  "classification": "probable",
  "insufficient_data": true,
  ...
}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing |
| 2 | Usage error (file not found, invalid thresholds, `--max-block-size` below 1) |

## Known Limitations

- Greedy deduplication is one-to-one: transitive chains (I1↔I2, I2↔I3) only
  report the highest-scoring pair; the third individual remains unmatched
- No cluster mode: related duplicates are not grouped into transitive sets
- No family context: matches are field-level only; shared parents/children are
  not considered as corroborating evidence
- Blocking may miss pairs with no shared blocking key (rare with 5 passes)
- Large blocks (more than `--max-block-size` individuals sharing a blocking key)
  are skipped to avoid quadratic blowup; the run reports how many groups were
  dropped, but not which individuals were in them

## Related Commands

- [`compare`](compare.md) — match individuals across two different files
- [`search`](search.md) — find individuals using flexible query syntax
- [`isolated`](isolated.md) — find unconnected individuals within a single file
