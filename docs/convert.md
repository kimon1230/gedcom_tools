# Convert Command

The `convert` command transcodes a GEDCOM file from one character encoding to
another (e.g., ANSEL to UTF-8). It performs raw byte-level conversion with
automatic CHAR header update, BOM handling, and NFC normalization for ANSEL
sources.

This is a **transcoding** command, not a GEDCOM writer. The file structure is
preserved byte-for-byte; only the character encoding and the `1 CHAR` header
line change.

## Usage

```bash
gedcom-tools convert <file> --to <encoding> -o <output> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--to {utf-8,ansel,ascii,unicode}` | Target encoding (required) |
| `--from CODEC` | Override source encoding detection (any Python codec name) |
| `-o, --output FILE` | Output file path (required) |
| `--force` | Overwrite existing output file |
| `--bom` | Add byte order mark to output |
| `--no-normalize` | Skip NFC Unicode normalization |
| `--dry-run` | Preview conversion without writing output |
| `-v, --verbose` | Show progress phases with timing |
| `-q, --quiet` | Errors only |
| `--no-color` | Disable colored progress output |
| `--ascii` | ASCII-only progress decorations (`[OK]`, `[!]`) |

### Examples

```bash
# Convert ANSEL to UTF-8
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged

# Convert with BOM (for Windows tools that expect it)
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged --bom

# Preview without writing
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged --dry-run

# Override source encoding for non-standard files
gedcom-tools convert weird.ged --from latin-1 --to utf-8 -o fixed.ged

# Convert to UTF-16 (GEDCOM "UNICODE")
gedcom-tools convert tree.ged --to unicode -o tree_utf16.ged

# Overwrite existing output
gedcom-tools convert old_tree.ged --to utf-8 -o tree_utf8.ged --force
```

## How It Works

The conversion pipeline:

1. **Detect encoding** — auto-detects the source encoding from the CHAR header
   and BOM, or uses the `--from` override.
2. **Read and decode** — reads the entire file as raw bytes, strips any BOM,
   and decodes using the resolved source codec.
3. **Normalize** — applies NFC normalization when the source is ANSEL (which
   produces NFD decomposed Unicode). Skipped with `--no-normalize`.
4. **Update CHAR header** — replaces `1 CHAR <old>` with `1 CHAR <new>` in
   the decoded text to reflect the target encoding.
5. **Encode and write** — encodes the text in the target codec, optionally
   prepends a BOM, and writes to the output file.

## Encoding Support

### Target Encodings (`--to`)

Only the four GEDCOM-standard character sets are allowed as targets:

| `--to` value | GEDCOM CHAR | Python codec | Notes |
|-------------|-------------|--------------|-------|
| `utf-8` | `UTF-8` | `utf-8` | Recommended for modern tools |
| `ansel` | `ANSEL` | `gedcom` | Legacy encoding via ansel package |
| `ascii` | `ASCII` | `ascii` | 7-bit only, fails on non-ASCII characters |
| `unicode` | `UNICODE` | `utf-16-le` | UTF-16 little-endian (Windows convention) |

### Source Encodings

Source encoding is auto-detected from the GEDCOM CHAR header. For non-standard
files, `--from` accepts any Python codec name:

```bash
# Standard GEDCOM files — auto-detected
gedcom-tools convert tree.ged --to utf-8 -o out.ged

# Non-standard encoding — override with any Python codec
gedcom-tools convert tree.ged --from latin-1 --to utf-8 -o out.ged
gedcom-tools convert tree.ged --from cp1252 --to utf-8 -o out.ged
gedcom-tools convert tree.ged --from iso-8859-7 --to utf-8 -o out.ged
```

`--from` also accepts GEDCOM charset names (`ansel`, `unicode`, `utf-8`,
`ascii`), which are mapped to their Python codec equivalents.

## CHAR Header Update

The `1 CHAR` line under `0 HEAD` is automatically updated to reflect the target
encoding. For example, converting to UTF-8 changes:

```
1 CHAR ANSEL
```

to:

```
1 CHAR UTF-8
```

If no `1 CHAR` line exists, one is inserted after `0 HEAD`. Only the first
occurrence is modified (in case of non-standard files with multiple CHAR lines).

## NFC Normalization

ANSEL uses combining diacritics that precede their base characters (opposite of
Unicode convention). The `ansel` codec produces NFD (decomposed) Unicode where
diacritics follow the base character but remain as separate code points. NFC
normalization composes these into single precomposed characters:

- NFD: `e` + `\u0301` (combining acute) = two code points
- NFC: `\u00e9` (é) = one code point

NFC normalization is applied automatically when the source codec is ANSEL. Use
`--no-normalize` to skip this step if you need to preserve the decomposed form.

For non-ANSEL sources, normalization is not applied (most codecs already produce
NFC-compatible output).

## Line Length Warnings

The GEDCOM specification limits lines to 255 bytes (content only, excluding
line terminators). When converting between encodings, character byte widths may
change:

- ASCII → UTF-8: No change for ASCII characters; non-ASCII not possible
- ANSEL → UTF-8: Accented characters may grow from 1-2 bytes to 2-3 bytes
- Any → UTF-16: Most characters double in size (2 bytes each)

If any lines exceed 255 bytes in the target encoding, a warning is printed to
stderr with the count. The file is still written — the warning is informational.
Splitting long lines with CONC/CONT tags would require GEDCOM structure
awareness and is not performed.

## BOM Handling

### Input BOM

Any BOM (byte order mark) in the source file is always stripped during
conversion. BOMs are metadata, not content, and are handled separately from
the encoding.

### Output BOM (`--bom`)

The `--bom` flag adds a BOM to the output file:

| Target | BOM bytes |
|--------|-----------|
| `utf-8` | `EF BB BF` |
| `unicode` | `FF FE` (UTF-16-LE) |
| `ascii` | (silently ignored) |
| `ansel` | (silently ignored) |

`--bom` is silently ignored for ASCII and ANSEL targets where BOM is
meaningless, rather than producing an error (convenient for batch scripts).

## Output Format

### Text (default)

```
File: old_tree.ged

=== Conversion ===
  Source encoding: ANSEL
  Target encoding: UTF-8
  Lines:           3,432
  NFC normalized:  yes
  BOM:             none
  Output:          tree_utf8.ged
```

### Quiet mode (`-q`)

```
Converted old_tree.ged (ANSEL → UTF-8) → tree_utf8.ged
```

### Dry run

Appends `(dry run — no file written)` to the output. No file is created.

### JSON (`--format json`)

```json
{
  "source_file": "old_tree.ged",
  "output_file": "tree_utf8.ged",
  "source_encoding": "ANSEL",
  "target_encoding": "UTF-8",
  "lines_total": 3432,
  "lines_over_limit": 0,
  "normalized": true,
  "bom_added": false,
  "bom_stripped": null,
  "dry_run": false,
  "gedcom_tools_version": "1.0.0"
}
```

## Safety

- **File size limit** — input files larger than 500 MB are rejected with an
  actionable error message showing the actual size and the limit.
- **Output file required** — `-o` is mandatory. No stdout output for UTF-16
  targets (which are binary).
- **Overwrite protection** — refuses to overwrite an existing file unless
  `--force` is specified.
- **Same-file protection** — detects when input and output are the same file
  (including via symlinks and hardlinks) and refuses. In-place conversion is
  not supported.
- **Output permissions** — output files are created with `0600` permissions
  (owner read/write only) on Unix systems. Skipped on Windows.
- **Dry run** — `--dry-run` previews the conversion without writing any file.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error during processing (decode/encode failure, empty file) |
| 2 | Usage error (file not found, unknown encoding) |

## Known Limitations

- **Whole-file memory load** — the entire file is read into memory. This works
  for typical GEDCOM files (< 50 MB) but is not suitable for 100 MB+ files.
- **No CONC/CONT splitting** — lines exceeding 255 bytes are warned about but
  not split. Splitting would require GEDCOM structure awareness.
- **Non-BOM UTF-16 assumed little-endian** — a file with `CHAR UNICODE` and no
  BOM is decoded as UTF-16-LE (Windows default). Use `--from utf-16-be` to
  override if the file is actually big-endian.
- **Auto-detection trusts CHAR header** — if a file declares `CHAR UTF-8` but
  is actually Latin-1, auto-detection returns UTF-8 and decoding fails. The
  error message suggests `--from` as the fix.
- **Non-standard CHAR values** — values like `ANSI` or `IBM WINDOWS` are not
  in the auto-detection map. Use `--from` to specify the actual codec.

## Related Commands

- [`validate`](validate.md) — check a GEDCOM file for structural and semantic errors
- [`export`](export.md) — extract individuals and families to CSV or JSON
- [`stats`](stats.md) — summary statistics for a GEDCOM file
