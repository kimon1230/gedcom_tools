# Relationship Command

The `relationship` command determines the genealogical relationship between
two individuals in a GEDCOM file using Lowest Common Ancestor (LCA) analysis.

## Usage

```bash
gedcom-tools relationship <file> <primary> <target> [options]
```

Where `<primary>` and `<target>` are individual xrefs (e.g., `@I1@`, `@I2@`).
The relationship is expressed as target-to-primary: "Target is the X of Primary."

### Options

| Option | Description |
|--------|-------------|
| `--type {blood,all}` | Relationship display: `blood` (default) suppresses half-prefix in text; `all` shows half-prefix. JSON `is_half` is always accurate regardless of this flag. |
| `--paths N` | Number of relationship paths to show, sorted best-first (default: 1) |
| `--generations N` | Maximum ancestor search depth (default: 30) |
| `--format {text,json}` | Output format (default: text) |
| `-v, --verbose` | Show timing and depth-limit warnings |
| `-q, --quiet` | Description sentence(s) only |
| `--no-color` | Disable colored output |
| `--ascii` | ASCII-only decorations (`[OK]`, `[!]`, `->`) |

### Xref Format

Both `primary` and `target` must be valid GEDCOM xref IDs:
- Start and end with `@`
- Contain only ASCII letters, digits, periods, hyphens, underscores, or colons
- Examples: `@I1@`, `@I123@`, `@I1-1@`, `@I1.2@`, `@I1:3@`

Invalid xrefs are rejected at parse time with an actionable error message.

## How It Works

The command runs in four phases:

1. **Load individuals** — single pass over INDI records to extract names, sex,
   and birth/death years
2. **Validate xrefs** — confirm both primary and target exist in the file
3. **Build relationship graph** — construct a directed parent-child graph from
   FAM records, tracking parent-child edges and spouse pairings
4. **Find relationship** — BFS upward from both individuals to find common
   ancestors, classify the relationship type, detect half-relationships, and
   format the result

In verbose mode, each phase is shown with timing.

### Algorithm

1. BFS upward from both primary and target, recording each ancestor's minimum
   generational distance (limited by `--generations`)
2. Intersect the two ancestor sets to find common ancestors
3. For each common ancestor, compute `(gen_p, gen_t)` — the generational
   distance from primary and target respectively
4. Group common ancestors by `(gen_p, gen_t)` and classify each group
5. Detect half-relationships via shared-parent counting (siblings) or
   spouse-pairing analysis (general case)
6. Deduplicate by `(base_type, is_half)`, merging common ancestor lists
7. Sort results by shortest path, blood over half, male line preference
8. Return top N paths per `--paths`

### Relationship Classification

`gen_p` is generations from primary to common ancestor. `gen_t` is generations
from target to common ancestor. Classification uses the target's sex for
gendered terms; unknown sex produces gender-neutral terms.

| gen_p | gen_t | Relationship |
|-------|-------|-------------|
| 0 | 0 | same individual |
| 1 | 0 | father / mother / parent |
| 0 | 1 | son / daughter / child |
| 1 | 1 | brother / sister / sibling |
| 2 | 0 | grandfather / grandmother |
| 0 | 2 | grandson / granddaughter |
| n>=3 | 0 | (n-2)x great-grandfather / great-grandmother |
| 0 | n>=3 | (n-2)x great-grandson / great-granddaughter |
| 2 | 1 | uncle / aunt |
| 1 | 2 | nephew / niece |
| 3 | 1 | great-uncle / great-aunt |
| 1 | 3 | great-nephew / great-niece |
| n>=4 | 1 | (n-2)x great-uncle / great-aunt |
| 1 | n>=4 | (n-2)x great-nephew / great-niece |
| n>=2 | m>=2 | cousin: degree=min(n,m)-1, removed=\|n-m\| |

**"Great" prefix:** 1 great = "great-grandfather", 2+ = "2x great-grandfather",
"3x great-grandfather", etc.

**Cousin ordinals:** "1st cousin", "2nd cousin", "3rd cousin", etc. Removal
uses "once removed", "twice removed", "3 times removed", etc.

### Half-Relationship Detection

Half-relationships are always computed regardless of `--type`. The `--type`
flag controls display only:

- `--type blood` (default): text labels omit "half-" prefix
- `--type all`: text labels include "half-" prefix when applicable

JSON output always includes the accurate `is_half` field.

**How it works:**

- **Direct lines** (parent, grandparent, child, etc.) are never half — the
  concept doesn't apply to direct-line relationships
- **Siblings**: count shared parents. Two shared parents = full sibling; one or
  zero shared parents = half-sibling
- **General case** (uncles, cousins, etc.): spouse-pairing analysis via the
  graph's couples data. If any common ancestor in the group has a partner who
  is also a common ancestor, the relationship is full-blood. Only when all
  common ancestors in the group are unpaired is it half-blood.

### Sort Order

When `--paths` shows multiple results, they are sorted best-first:

1. **Shortest path first** — `gen_p + gen_t` ascending
2. **Blood over half** — full-blood relationships before half-blood
3. **Male line preference** — paths with more male common ancestors sort first

## Output

### Text Output

```
File: family.ged

=== Relationship ===

  John Smith (1850-1920) [@I1@]
  James Smith (1880-1945) [@I3@]

  James Smith is the son of John Smith.
```

### Text Output (Quiet)

```
James Smith is the son of John Smith.
```

### Text Output (Multiple Paths)

```
File: family.ged

=== Relationships (2 found) ===

  John Smith (1850-1920) [@I1@]
  James Smith (1880-1945) [@I3@]

  1. James Smith is the son of John Smith.
  2. James Smith is a 1st cousin of John Smith.
```

When paths are limited, a hint is shown:

```
  (1 of 3 relationships shown. Use --paths 3 to see all.)
```

### JSON Output

```json
{
  "file": "family.ged",
  "primary": {
    "xref": "@I1@",
    "name": "John Smith",
    "sex": "M",
    "birth_year": 1850,
    "death_year": 1920
  },
  "target": {
    "xref": "@I3@",
    "name": "James Smith",
    "sex": "M",
    "birth_year": 1880,
    "death_year": null
  },
  "related": true,
  "relationships": [
    {
      "type": "son",
      "gen_from_primary": 0,
      "gen_from_target": 1,
      "common_ancestors": ["@I1@"],
      "is_half": false,
      "description": "James Smith is the son of John Smith."
    }
  ]
}
```

**JSON field notes:**

- `birth_year`, `death_year`: integer or `null` when no date is available
- `is_half`: always computed accurately, regardless of `--type`
- `type`: base relationship type (no half-prefix). The `description` field
  includes the half-prefix when `--type all` and `is_half` is true.
- `gen_from_primary`, `gen_from_target`: generational distances from the
  shortest path after dedup merge. These do not necessarily correspond to all
  entries in `common_ancestors`, which is the union of ancestors from all
  merged groups.
- `common_ancestors`: sorted deterministically by xref for stable output

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (related or not related) |
| 1 | Error during processing |
| 2 | Usage error (invalid xref format, xref not found, file not found) |

## Known Limitations

- **Remarried ancestor**: The spouse-pairing heuristic can misclassify when a
  remarried ancestor appears as a common ancestor across different marriages —
  the check finds a partner from a different marriage and may wrongly mark as
  full-blood
- **Two-pass file read**: Individuals are loaded in one pass, the parent-child
  graph in another. Both are O(N) and I/O-dominated, so the cost is acceptable
  for v1
- **BFS depth limit**: The default 30-generation search depth covers virtually
  all real-world genealogies, but exceptionally deep trees may need
  `--generations` increased
- **Step/adoptive parents**: GEDCOM FAM records don't distinguish biological vs.
  step/adoptive parent-child relationships unless ADOP/PEDI tags are present.
  All FAM-linked parent-child edges are treated as biological

## Related Commands

- [`search`](search.md) — find individuals using flexible query syntax
- [`compare`](compare.md) — compare individuals across two files
- [`stats`](stats.md) — summary statistics for a single GEDCOM file
- [`isolated`](isolated.md) — find unconnected individuals within a single file
