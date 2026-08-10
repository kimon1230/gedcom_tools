# Filter Command

The `filter` command transforms GEDCOM files by removing unwanted records,
stripping specific tags, or extracting subtrees centered on an individual. It
operates on raw GEDCOM lines — no data is reinterpreted or reformatted — so the
output is a valid GEDCOM file that preserves encoding, line endings, BOM, and all
content that was not explicitly removed.

## Usage

```bash
gedcom-tools filter <file> -o <output> [options]
```

### Options

**Output options:**

| Option | Description |
|--------|-------------|
| `-o, --output FILE` | Output file path (required) |
| `--from CODEC` | Override source encoding detection (any Python codec name) |
| `--force` | Overwrite existing output file |
| `--dry-run` | Preview changes without writing output |
| `-v, --verbose` | Show progress phases with timing |
| `-q, --quiet` | Errors only |
| `--no-color` | Disable colored progress output |
| `--ascii` | ASCII-only progress decorations (`[OK]`, `[!]`) |

**Strip options:**

| Option | Description |
|--------|-------------|
| `--strip-custom-tags` | Remove all custom (`_`-prefixed) tags at any level |
| `--strip-notes` | Remove NOTE records and inline NOTE references |
| `--strip-sources` | Remove SOUR records and inline citations |
| `--strip-multimedia` | Remove OBJE records and inline references |
| `--strip-tag TAG` | Remove a specific tag (repeatable) |

**Subtree options:**

| Option | Description |
|--------|-------------|
| `--subtree XREF` | Extract subtree rooted at individual (e.g., `@I1@`) |
| `--ancestors N` | Max ancestor generations (default: unlimited) |
| `--descendants N` | Max descendant generations (default: 0) |
| `--include-spouses` | Include spouses of extracted individuals |

At least one strip or subtree option is required.

### Examples

```bash
# Remove all custom (underscore-prefixed) tags
gedcom-tools filter tree.ged -o clean.ged --strip-custom-tags

# Remove notes and sources
gedcom-tools filter tree.ged -o minimal.ged --strip-notes --strip-sources

# Remove a specific tag (repeatable)
gedcom-tools filter tree.ged -o clean.ged --strip-tag OCCU --strip-tag RESI

# Extract an individual with all ancestors
gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@

# Extract with limited ancestor depth and descendants
gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@ --ancestors 3 --descendants 2

# Extract subtree including spouses
gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@ --include-spouses

# Combine subtree extraction with stripping
gedcom-tools filter tree.ged -o subtree.ged --subtree @I1@ --ancestors 5 --strip-notes

# Preview without writing
gedcom-tools filter tree.ged -o clean.ged --strip-custom-tags --dry-run

# Overwrite existing output file
gedcom-tools filter tree.ged -o clean.ged --strip-notes --force

# Override the source encoding when the CHAR header is wrong or unreadable
gedcom-tools filter weird.ged -o clean.ged --strip-notes --from latin-1
```

## Source Encoding

The source encoding is read from the GEDCOM `1 CHAR` header, and the output is
written back in the same codec. `--from CODEC` overrides that, skipping header
detection entirely — which is what makes a file with a mangled or missing CHAR
value filterable at all. It accepts any Python codec name (`latin-1`, `cp1252`,
`iso-8859-7`) as well as the GEDCOM charset names `ansel`, `unicode`, `utf-8`
and `ascii`.

Auto-detection is deliberately narrower than `--from`. `filter` decodes the
whole file and splits it into lines afterwards, so the codec named in the header
decides where the line boundaries fall — and a codec such as UTF-7 spells a line
break in plain ASCII (`+AAo-`), which turns a NOTE value into level-0 records
that were never in the file. Only encodings that cannot do this are honoured
from the header; anything else is refused with:

```
Error: Cannot determine source encoding from 'UTF-7'. Use --from to specify.
```

Passing `--from utf-7` processes the file anyway. The restriction is about a
file choosing its own decoder, not about the codec being forbidden.

Note that `validate` and `stats` read the same file through ged4py, which splits
on bytes before decoding, so they are unaffected and will still report on it.

## How It Works

Encoding is resolved first, before any phase begins — from the `1 CHAR` header,
or straight from `--from` when it is given — so a file whose encoding cannot be
determined is refused before the read starts. The pipeline itself has four
phases:

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 1: Reading Input                                      │
│  - Read raw bytes, strip BOM                                 │
│  - Decode using the resolved source codec                    │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Phase 2: Parsing GEDCOM                                     │
│  - Detect line ending (CRLF or LF)                           │
│  - Parse lines into (level, xref, tag, value, raw) tuples    │
│  - Group by level-0 boundaries into records                  │
│  - Verify HEAD and TRLR exist                                │
│  - Count source records by type                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Phase 3: Filtering                                          │
│  - Subtree extraction (if --subtree)                         │
│  - Strip transforms (record-level, then line-level)          │
│  - Dangling pointer cleanup                                  │
│  - Empty family cascade removal                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Phase 4: Writing Output                                     │
│  - Serialize records back to text using original line ending  │
│  - Re-encode using original codec                            │
│  - Prepend BOM if the source had one                         │
│  - Write to output file (unless --dry-run)                   │
└──────────────────────────────────────────────────────────────┘
```

## Strip Operations

### `--strip-custom-tags`

Removes all lines whose tag starts with `_` at any level. Custom tags are
vendor-specific extensions (e.g., `_APID`, `_UID`, `_FSFTID`) that many GEDCOM
programs add for internal use. When a custom tag is removed, all its child lines
(deeper levels) are also removed.

### `--strip-notes`

Removes NOTE records at the top level (entire `0 @N1@ NOTE ...` blocks) and
inline NOTE references at any sub-level (e.g., `1 NOTE text` or `2 NOTE @N3@`
within an INDI or FAM record). Child lines under removed NOTE references are
also removed.

### `--strip-sources`

Removes SOUR records at the top level and inline SOUR citations at any
sub-level. This strips all source documentation from the file.

### `--strip-multimedia`

Removes OBJE records at the top level and inline OBJE references at any
sub-level. This strips all multimedia links from the file.

### `--strip-tag TAG`

Removes records and sub-lines matching a specific tag. Can be repeated to strip
multiple tags. Tags are case-insensitive (automatically uppercased). Works at
both record level (removes entire top-level records with that tag) and line level
(removes sub-lines and their children).

```bash
# Strip occupation and residence records/lines
gedcom-tools filter tree.ged -o clean.ged --strip-tag OCCU --strip-tag RESI
```

### Order of Operations

Strip transforms are applied in this order:

1. **Record-level strips** — Remove entire top-level records (NOTE, SOUR, OBJE,
   or user-specified tags)
2. **Custom tag strips** — Remove `_`-prefixed lines at any level
3. **Line-level strips** — Remove inline sub-lines by tag (NOTE, SOUR, OBJE, or
   user-specified tags)
4. **User-specified tag strips** — `--strip-tag` applies at both record and line
   levels

## Subtree Extraction

The `--subtree` option extracts a family subtree centered on a specific
individual. The algorithm:

1. Build a directed parent-child graph from the GEDCOM FAM records
2. Validate the root xref exists in the file
3. BFS upward to collect ancestors (up to `--ancestors N` generations; unlimited
   by default)
4. BFS downward to collect descendants (up to `--descendants N` generations; 0 by
   default, meaning no descendants)
5. If `--include-spouses`, add spouses of all kept individuals via FAM
   HUSB/WIFE pairings
6. Keep any FAM record where at least one HUSB, WIFE, or CHIL is in the keep set
7. Transitively collect dependent records (SOUR, NOTE, OBJE, REPO) referenced by
   kept INDI and FAM records, following chains (e.g., SOUR → REPO)
8. Filter: keep records whose xref is in the keep set, plus structural records
   (HEAD, TRLR, SUBM) and non-xref records

### Combining Subtree with Strip

When both subtree and strip options are specified, subtree extraction runs first,
then strip transforms are applied to the reduced set of records. This lets you
extract a subtree and clean it up in a single pass:

```bash
# Extract grandparent subtree, remove notes and custom tags
gedcom-tools filter tree.ged -o clean_subtree.ged \
    --subtree @I1@ --ancestors 2 --descendants 1 --include-spouses \
    --strip-notes --strip-custom-tags
```

## Cross-Reference Cleanup

After filtering, two cleanup passes run automatically:

### Dangling Pointer Removal

When records are removed, other records may still reference them (e.g., a CHIL
line pointing to a removed individual). These dangling references are detected
and removed. When a dangling pointer line is removed, its child lines at deeper
levels are also removed.

### Empty Family Cascade

After dangling pointer removal, some FAM records may lose all their HUSB, WIFE,
and CHIL references. These empty families are automatically removed. If removing
a FAM creates new dangling pointers (e.g., an INDI's FAMS reference to the
removed FAM), a second dangling pointer cleanup pass runs.

## Output Format

### Text (default)

```
File: tree.ged

=== Filter Results ===

  Record Type       Source   Output  Removed
  --------------- -------- -------- --------
  Individuals          500      150      350
  Families             200       60      140
  Notes                 50        0       50
  Sources               30       15       15
  --------------- -------- -------- --------
  Total                780      225      555

  Dangling references cleaned: 42
  Empty families removed: 3

  Output: subtree.ged
```

### Quiet mode (`-q`)

```
Filtered tree.ged (780 → 225 records) → subtree.ged
```

### Dry run

Appends `(dry run -- no file written)` to the output. No file is created.

### JSON (`--format json`)

```json
{
  "source_file": "tree.ged",
  "output_file": "subtree.ged",
  "source": {
    "individuals": 500,
    "families": 200,
    "notes": 50,
    "sources": 30,
    "multimedia": 0,
    "repositories": 0,
    "submitters": 1,
    "other": 2,
    "total": 783
  },
  "output": {
    "individuals": 150,
    "families": 60,
    "notes": 0,
    "sources": 15,
    "multimedia": 0,
    "repositories": 0,
    "submitters": 1,
    "other": 2,
    "total": 228
  },
  "removed": {
    "individuals": 350,
    "families": 140,
    "notes": 50,
    "sources": 15,
    "multimedia": 0,
    "repositories": 0,
    "submitters": 0,
    "other": 0,
    "total": 555
  },
  "dangling_lines_removed": 42,
  "empty_families_removed": 3,
  "dry_run": false,
  "gedcom_tools_version": "1.0.0"
}
```

## Safety

- **File size limit** — input files larger than 500 MB are rejected with an
  actionable error message showing the actual size and the limit. That figure is
  a backstop against absurd input, not a supported size: `filter` builds an
  in-memory representation around 25 times the file size, so the practical
  ceiling on an ordinary machine is nearer **50-80 MB**. Beyond that the command
  will exhaust memory rather than reach the limit.
- **Output file required** — `-o` is mandatory. The original file is never
  modified.
- **Overwrite protection** — refuses to overwrite an existing file unless
  `--force` is specified.
- **Symlink refusal** — a symlink at the output path is refused, even with
  `--force`. Writing through a link would let a pre-planted link redirect the
  output somewhere the user did not name. Write to the real path instead.
- **Same-file protection** — detects when input and output are the same file
  (including via symlinks and hardlinks) and refuses. In-place filtering is not
  supported.
- **Dry run** — `--dry-run` previews the filtering results without writing any
  file.
- **Output permissions** — output files are created with `0600` permissions
  (owner read/write only) on Unix systems. Skipped on Windows.
- **Encoding preservation** — the output is encoded using the same codec as the
  input. If the input had a BOM, the output will too.
- **Line ending preservation** — CRLF or LF line endings are preserved from the
  input.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing (invalid GEDCOM structure, xref not found) |
| 2 | Usage error (file not found, invalid arguments, no filter options) |

## Known Limitations

- **Whole-file memory load** — the entire file is read into memory as decoded
  text, then parsed into Python objects. Files under 100 MB (the vast majority of
  GEDCOM files) are fine.
- **Subtree double-read** — when using `--subtree`, the file is read twice: once
  as raw bytes (for line-level processing) and once via ged4py (for graph
  construction). This is unavoidable given ged4py's read-only design.
- **Orphaned dependent records** — after empty family cascade, SOUR/NOTE/OBJE/
  REPO records that were only referenced by removed FAMs become orphaned. Run
  `gedcom-tools validate` on the output to identify them.
- **No CONC/CONT rewrapping** — transforms that change line content do not
  re-check the 255-byte line length limit or split long lines using CONC/CONT
  continuation tags.
- **`--strip-custom-tags` is all-or-nothing** — no way to exclude specific
  custom tags from removal. Use `--strip-tag _TAG1 --strip-tag _TAG2` for
  selective removal.
- **Record boundaries follow ged4py's line grammar** — so that `filter` and
  `validate` cannot disagree about where a record starts. Two line shapes some
  writers emit are therefore not record boundaries: an xref whose first
  character is not alphanumeric (`0 @.X@ INDI`) and a line using tabs as its
  internal delimiters. Both attach to the preceding record as child lines, which
  means `--subtree` on that preceding xref carries them along, and
  `--subtree @.X@` finds nothing.

## Related Commands

- [`validate`](validate.md) — check the output file for structural and semantic errors
- [`export`](export.md) — extract individuals and families to CSV or JSON
- [`convert`](convert.md) — convert between character encodings
- [`stats`](stats.md) — summary statistics for a GEDCOM file
