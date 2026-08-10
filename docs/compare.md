# Compare Command

The `compare` command compares two GEDCOM files to find matching individuals
using probabilistic record linkage (simplified Fellegi-Sunter).

## Usage

```bash
gedcom-tools compare <file_a> <file_b> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {text,json}` | Output format (default: text) |
| `-v, --verbose` | Show timing and per-field scores |
| `-q, --quiet` | One-line summary |
| `--certain-threshold F` | Minimum score for certain match (default: 0.85) |
| `--probable-threshold F` | Minimum score for probable match (default: 0.65) |
| `--show-matches {all,certain,probable}` | Which matches to show (default: all) |
| `--list-unique` | List individuals unique to each file |
| `--limit N` | Max items per output section (text default: 50, JSON default: unlimited) |
| `--reject-sex-mismatch` | Treat sex mismatches as hard reject (score 0.0) |
| `--phonetic {soundex,metaphone}` | Phonetic algorithm for blocking and scoring (default: soundex) |
| `--max-block-size N` | Max individuals sharing a blocking key before the group is skipped (default: 500) |
| `--no-color` | Disable colored output |
| `--ascii` | ASCII-only decorations in progress output and results |

## How It Works

The command runs in five phases:

1. Detect encodings of both files
2. Read individuals from file A (collector extracts name, dates, places, sex)
3. Read individuals from file B
4. Find matches: multi-pass blocking, weighted Jaro-Winkler scoring, greedy
   one-to-one deduplication
5. Format results

In verbose mode, each phase is shown with timing.

## Methodology

### Scoring Approach

Uses a simplified Fellegi-Sunter probabilistic model (Fellegi & Sunter, 1969).
Each individual is compared across 7 weighted fields:

| Field | Weight |
|-------|--------|
| Surname | 0.30 |
| Given Name | 0.20 |
| Birth Year | 0.20 |
| Death Year | 0.10 |
| Birth Place | 0.10 |
| Death Place | 0.05 |
| Sex | 0.05 |

Weights sum to 1.0. The total score is a weighted average of per-field
similarities.

### String Similarity

Jaro-Winkler similarity (Jaro, 1989; Winkler, 1990) via the `rapidfuzz`
library. Handles typos, transcription errors, and naming variants.

For names with multiple alternatives (e.g., NAME + ROMN + FONE), the best
score across the cartesian product of name pairs is used.

### Phonetic Bonus

When surname Jaro-Winkler is between 0.50 and 0.85, a +0.05 bonus is applied
if both surnames share a phonetic code. With the default Soundex algorithm
(Russell, 1918), this requires identical codes. With `--phonetic metaphone`,
both primary and secondary Double Metaphone codes are checked — a bonus is
applied if any code from one side matches any code from the other. This helps
bridge transliteration differences, especially for European name variants
(Schmidt/Smith, Müller/Miller).

### Year Proximity

Birth and death years use graduated proximity bands:

| Difference | Score |
|------------|-------|
| 0 years | 1.00 |
| +/-1 year | 0.85 |
| +/-2 years | 0.70 |
| +/-3 years | 0.50 |
| +/-5 years | 0.25 |
| +/-7 years | 0.10 |
| +/-10 years | 0.05 |
| >10 years | 0.00 |

### Place Comparison

Place strings are split by comma into components. A greedy best-match alignment
finds the highest-scoring component pairs (consumed greedily), and the average
is taken. This handles differing levels of specificity (e.g., "London, England"
vs "London, Middlesex, England").

### Sex Handling

Matching sex scores 1.0. When sex is missing on either side, the field is
skipped and its weight is redistributed among the remaining fields. Mismatched
sex applies a 0.7x penalty to the total score. With `--reject-sex-mismatch`,
mismatched sex gives 0.0 total.

In verbose mode, sex mismatch penalties are shown in the score breakdown.

### Multi-Pass Blocking

To avoid O(N*M) comparisons, 5 blocking passes generate candidate pairs
(Christen, 2012):

1. Surname phonetic + birth decade
2. Surname phonetic + death decade
3. Given name phonetic + birth decade
4. Exact birth year + exact death year
5. Surname phonetic + given name phonetic

Only pairs that share at least one blocking key are scored.

### Block Size Cap

Scoring a blocking group costs time proportional to the square of its size, so
groups larger than `--max-block-size` (default 500) are skipped entirely. On a
file where 600 people share `SMITH|1850s`, that group contributes no candidate
pairs at all and matches inside it are never found.

Skipped groups are reported. A run that dropped any prints to stderr:

```
Warning: 2 blocking groups exceeded --max-block-size 500 and were skipped, so some matches may be missing.
  Re-run with a larger --max-block-size to include them; scoring cost grows with the square of the group size.
```

and JSON output carries `oversized_blocks_skipped` with the same number. The
count is of distinct blocking keys -- one 600-member group is one skipped group,
however many individuals looked it up. The warning is printed in every output
mode, `--quiet` included, since it says the result is incomplete.

Raising the cap recovers the missed matches at the cost of a slower run.
Narrowing the input -- comparing subtrees rather than whole files -- avoids the
group instead.

With `--phonetic metaphone`, two additional multi-key passes run after the
standard passes. Each individual is indexed under both its primary and secondary
Double Metaphone codes, so cross-code matches (e.g., Smith's secondary code
matching Schmidt's primary code) become candidates that Soundex would miss.

### Three-Tier Classification

| Classification | Criteria |
|----------------|----------|
| Certain | Score >= certain_threshold AND >= 4 comparable fields |
| Probable | Score >= probable_threshold |
| Non-match | Score < probable_threshold |

A "comparable field" is one where both individuals have data. This prevents a
name-only match from being classified as "certain" without corroborating
evidence.

The `insufficient_data` flag is set when fewer than 3 comparable fields exist,
or when no corroborating fields (dates, places) were compared. The `name_only`
flag is set when no corroborating fields were compared.

A match can be classified as "probable" while also having `insufficient_data`
set -- this occurs when names (and possibly sex) match well but no dates or
places are available for corroboration. Consumers should treat these as
low-confidence matches.

### Greedy Deduplication

After scoring, a greedy one-to-one assignment ensures each individual appears
in at most one match (Papadakis et al., 2023). Pairs are sorted by descending
score; the first valid pair for each individual wins.

## Output

### Text Output

```
File A: tree_a.ged
File B: tree_b.ged
Encoding A: UTF-8
Encoding B: UTF-8

=== Comparison Summary ===
  Individuals in A:    100
  Individuals in B:    120
  Certain matches:      15
  Probable matches:       8
  Unique to A:          77
  Unique to B:          97

=== Certain Matches (15) ===
  1. John Smith (b. 1850, d. 1920)
     A: @I1@   B: @I10@   Score: 0.95
     Differences:
       Birth Place: "London, England" vs "London, Middlesex, England"

  2. Mary Jones (b. 1872, d. 1945)
     A: @I3@   B: @I22@   Score: 0.91

=== Probable Matches (8) ===
  ...
```

Probable matches are hidden when `--show-matches certain` is used. Certain
matches are hidden when `--show-matches probable` is used. Unique-to-A and
unique-to-B sections are shown when `--list-unique` is used. Verbose mode adds
a per-field score breakdown for each match.

### Text Output (Quiet)

Single line:

```
15 certain, 8 probable, 77 unique to tree_a.ged, 97 unique to tree_b.ged
```

### JSON Output

```json
{
  "file_a": "tree_a.ged",
  "file_b": "tree_b.ged",
  "filename_a": "tree_a.ged",
  "filename_b": "tree_b.ged",
  "encoding_a": { "detected": "UTF-8", "has_bom": false, "declared": "UTF-8" },
  "encoding_b": { "detected": "UTF-8", "has_bom": false, "declared": "UTF-8" },
  "total_a": 100,
  "total_b": 120,
  "certain_matches": [
    {
      "individual_a": { "xref": "@I1@", "name": "John Smith", "birth_year": 1850, "death_year": 1920 },
      "individual_b": { "xref": "@I10@", "name": "John Smith", "birth_year": 1850, "death_year": 1920 },
      "score": 0.95,
      "classification": "certain",
      "insufficient_data": false,
      "name_only": false,
      "sex_penalty": false,
      "comparable_field_count": 6,
      "field_scores": {
        "Surname": 1.0,
        "Given Name": 1.0,
        "Birth Year": 1.0,
        "Death Year": 1.0,
        "Birth Place": 0.85,
        "Death Place": 0.0,
        "Sex": 1.0
      },
      "differences": [
        { "field": "Birth Place", "value_a": "London, England", "value_b": "London, Middlesex, England" }
      ]
    }
  ],
  "certain_matches_total": 1,
  "probable_matches": [],
  "probable_matches_total": 0,
  "unique_to_a": [],
  "unique_to_a_total": 0,
  "unique_to_b": [],
  "unique_to_b_total": 0
}
```

`oversized_blocks_skipped` is added only when at least one blocking group was
dropped for exceeding `--max-block-size`; its absence means nothing was capped.
Treat a present key as "these results are incomplete" -- see
[Block Size Cap](#block-size-cap).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing |
| 2 | Usage error (file not found, invalid thresholds, `--max-block-size` below 1, same file) |

## Known Limitations

- Name-only matches (no dates, places, or sex) are flagged with
  `insufficient_data` and cannot reach "certain" classification
- Place comparison is string-based; no geocoding or gazetteer lookup
- No structural graph walking -- matches are field-level only, family
  relationships are not considered
- Blocking may miss pairs that share no blocking key at all (rare with 5
  passes)
- Blocking groups larger than `--max-block-size` are skipped; the run reports
  how many, but not which individuals were in them
- Greedy deduplication is not globally optimal (no Hungarian algorithm)

## References

Christen, P. (2012). A survey of indexing techniques for scalable record
    linkage and deduplication. *IEEE Transactions on Knowledge and Data
    Engineering*, *24*(9), 1537-1555.

Fellegi, I. P., & Sunter, A. B. (1969). A theory for record linkage.
    *Journal of the American Statistical Association*, *64*(328), 1183-1210.

Jaro, M. A. (1989). Advances in record-linkage methodology as applied to
    matching the 1985 census of Tampa, Florida. *Journal of the American
    Statistical Association*, *84*(406), 414-420.

Phillips, L. (2000). The Double Metaphone search algorithm. *C/C++ Users
    Journal*, *18*(6).

Papadakis, G., Efthymiou, V., Thanos, E., Hassanzadeh, O., & Christen, P.
    (2023). An analysis of one-to-one matching algorithms for entity
    resolution. *The VLDB Journal*, *32*(6), 1369-1400.

Russell, R. C. (1918). *Index* (U.S. Patent No. 1,261,167). U.S. Patent and
    Trademark Office.

Winkler, W. E. (1990). String comparator metrics and enhanced decision rules
    in the Fellegi-Sunter model of record linkage. In *Proceedings of the
    Section on Survey Research Methods* (pp. 354-359). American Statistical
    Association.

## Related Commands

- [`search`](search.md) -- find individuals using flexible query syntax
- [`stats`](stats.md) -- summary statistics for a single GEDCOM file
- [`isolated`](isolated.md) -- find unconnected individuals within a single file
