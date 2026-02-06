# Isolated Command

The `isolated` command detects individuals with no effective family connections
in a GEDCOM file using graph analysis.

## Usage

```bash
gedcom-tools isolated <file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {text,json}` | Output format (default: text) |
| `-v, --verbose` | Show timing information |
| `-q, --quiet` | One-line summary |

## What It Detects

### Singletons (Component Size 1)

Individuals who appear in no family record — they have no spouse link (FAMS)
and no child link (FAMC) connecting them to any other individual.

**Common causes:**
- Records added by mistake
- Individuals not yet linked to their family
- Imported records missing family connections

### Isolated Pairs (Component Size 2)

Two individuals connected only to each other, with no link to anyone else
in the tree. Typically a married couple with no children and no parents recorded.

**Common causes:**
- Incomplete research — children or parents not yet added
- Stub records for distant relatives

## How It Works

The command uses Union-Find (disjoint set) graph analysis:

1. Every individual starts in their own component
2. Family records merge components: all members of a FAM record (HUSB, WIFE,
   CHIL) are joined into the same component
3. After processing all families, any component of size 1 is a singleton and
   any component of size 2 is an isolated pair

This is the same algorithm used by the `stats` command for its isolated count
in the completeness section.

## Output

### Text Output

```
File: family.ged

=== Isolated Analysis ===
  Total individuals:       100
  Isolated individuals:      5 (5.0%)
    Singletons:              3
    Isolated pairs:          1 (2 individuals)

=== Singletons ===
  These individuals have no effective family connections.
  They may need to be linked to a family or removed if added in error.

  1. John Doe (@I45@) M, b. 1850
  2. Jane Smith (@I67@) F
  3. Unknown (@I99@)

=== Isolated Pairs ===
  These pairs are connected only to each other, with no link to anyone else.

  1. Robert Brown (@I12@) M, b. 1800
     Mary Brown (@I13@) F, b. 1805
```

### JSON Output

```json
{
  "file": "family.ged",
  "summary": {
    "total_individuals": 100,
    "isolated_count": 5,
    "singleton_count": 3,
    "pair_count": 1
  },
  "singletons": [
    {"xref": "@I45@", "name": "John Doe", "sex": "M", "birth_year": 1850},
    {"xref": "@I67@", "name": "Jane Smith", "sex": "F", "birth_year": null},
    {"xref": "@I99@", "name": "Unknown", "sex": "", "birth_year": null}
  ],
  "pairs": [
    [
      {"xref": "@I12@", "name": "Robert Brown", "sex": "M", "birth_year": 1800},
      {"xref": "@I13@", "name": "Mary Brown", "sex": "F", "birth_year": 1805}
    ]
  ]
}
```

### Quiet Mode

Returns a single line when isolated individuals exist, or nothing if none found:

```
5 isolated (3 singletons, 1 pair)
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing or permission denied |
| 2 | Usage error (file not found, not a file) |

## Relationship to Stats Command

The `stats` command includes an "Isolated" count in its Data Completeness section.
This uses the same algorithm and counts individuals in components of size 1
(singletons) and size 2 (pairs).

The `isolated` command provides detailed output (names, xrefs, birth years) while
the `stats` command only shows the count and percentage.
