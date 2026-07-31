# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.2.1]

### Fixed
- `--ascii` (and `GEDCOM_TOOLS_ASCII`) now reaches every decoration, not just the validation output. Six modules drew their separators from hardcoded characters and ignored the flag entirely: the `languages` table rule (53 box-drawing characters, so the whole table collapsed into a row of boxes on a console whose font lacks them), the `↔` pair separator and `×` score multiplier in `compare` and `duplicates`, and the `→` conversion arrows in `convert --quiet` and `filter --quiet`. These were written as `\uXXXX` escapes rather than literal characters, which is why the 1.2.0 sweep missed them

### Changed
- Em-dashes in message prose are now written `--` in both Unicode and ASCII mode, for consistency with the `-- use --limit 0 for all` wording that `compare` already used. Affects the `--dry-run` notices in `convert` and `filter`, the truncation notice in `duplicates`, the "no HEAD record" error from `convert`, and two `search` query-validation errors. The `languages` event separator keeps its em-dash in Unicode mode — it is a field separator and now follows `--ascii` like the other decorations
- Added a regression test that walks `src/` and rejects new non-ASCII string literals outside a small allowlist, so the next hardcoded glyph fails in CI rather than shipping

## [1.2.0]

### Fixed
- `UnicodeEncodeError` when output is redirected on a legacy codepage — the CLI worked interactively and crashed under `> out.txt`, CI capture, or any build script. Affected non-ASCII names and places in every command, not just the tool's own `✓ ✗ →` decorations; `--format json` was affected too, since most formatters emit unescaped Unicode

### Added
- `--ascii` global flag and `GEDCOM_TOOLS_ASCII` environment variable — replaces `✓ ✗ →` and the spinner with `[OK]`, `[!]`, `->` for consoles whose fonts cannot draw them (Windows console fonts routinely lack braille)
- Continuous integration: lint/format/type checks, a test matrix across Linux and Windows on Python 3.11 and 3.13, and a regression job that captures CLI output on both platforms

### Changed
- Redirected output is now written as UTF-8 regardless of the system codepage; terminals keep their own encoding and gain a `backslashreplace` error handler. An explicit `PYTHONIOENCODING` is honoured and takes precedence
- `ged4py` requirement changed from `~=0.4.4` to `>=0.5.2,<0.6`. The 1.1.0 pin was never what development ran — the declared range excluded the version actually tested. The bounded range is retained, now aligned with what is exercised
- `DoubleMetaphone` requirement raised to `>=1.2`; 1.1 has no wheels and its Cython source fails to build on Python 3.13
- Development dependency floors raised to the versions CI and local development actually run

## [1.1.1]

### Added
- Optional `graph` extras group for GraphViz chart generation via `kimon-gedgraph` (`pip install kimon-gedcom-tools[graph]`)

## [1.1.0]

### Security
- Living person estimation redesigned: custom GEDCOM tags (`_LVG`, `_LIVING`, `_LVNG`, `_CONF_FLAG` for living; `_NLIV` for not living) take priority over date-based inference; individuals with no dates and no custom tag are no longer conservatively marked as living
- Cross-reference IDs cleared for redacted living individuals in export output (prevents correlation via family links)
- `filename` / `filename_a` / `filename_b` fields added to JSON output in export, compare, and stats commands (basename only, safe for sharing)
- Individual names removed from stats timeline JSON entries to prevent PII leakage
- Output files from export, filter, and convert commands are created with `0600` permissions (owner-only) on Unix systems
- Regex validation strengthened: pattern length limit (256 chars), nesting depth limit (3 levels), quantified inner group rejection, overlapping alternation rejection
- Search pattern cache replaced with bounded `@lru_cache(maxsize=256)` to prevent unbounded memory growth
- 500 MB file size limit for filter and convert commands to prevent unbounded memory allocation
- Recursive source counting converted to iterative to prevent stack overflow on deeply nested records
- Error messages sanitized to strip C0 control characters, ANSI escape sequences, and Unicode bidi overrides before printing to stderr
- `ged4py` dependency pinned to compatible release (`~=0.4.4`) to prevent unexpected breaking changes

## [1.0.1]

### Fixed
- Fix package name and repository URLs for PyPI publishing

## [1.0.0]

### Added
- `filter` command — transform GEDCOM files by stripping tags, removing records, or extracting subtrees centered on an individual
- Strip operations: `--strip-custom-tags`, `--strip-notes`, `--strip-sources`, `--strip-multimedia`, `--strip-tag TAG` (repeatable, both record-level and line-level)
- Subtree extraction: `--subtree @I1@` with `--ancestors N`, `--descendants N`, `--include-spouses` for extracting family branches
- Automatic cross-reference cleanup: dangling pointer removal and empty family cascade after filtering
- Line-level GEDCOM parser for lossless round-trip processing (preserves encoding, BOM, line endings)
- `--dry-run` for previewing filter results without writing output
- Shared byte-I/O utilities extracted from convert: `strip_bom()`, `resolve_source_codec()`, `check_output_safety()` moved to `utils.py` for reuse across filter and convert
- `convert` command — transcode GEDCOM files between character encodings (UTF-8, ANSEL, ASCII, UNICODE) with automatic CHAR header update
- Auto-detection of source encoding from CHAR header and BOM, with `--from` override for non-standard files (any Python codec: latin-1, cp1252, iso-8859-7, etc.)
- NFC normalization for ANSEL sources (ANSEL combining diacritics produce NFD; NFC composes to precomposed characters)
- `--bom` flag for adding byte order mark to UTF-8 or UTF-16 output
- `--dry-run` for previewing conversion without writing output
- `--no-normalize` to skip NFC normalization when preserving decomposed form is needed
- Line length warnings when transcoding causes lines to exceed the GEDCOM 255-byte limit
- Same-file protection via `os.path.samefile()` (detects symlinks and hardlinks)
- Overwrite protection (`--force` to override)
- `export` command — extract all individuals and families from a GEDCOM file into CSV or JSON format for spreadsheets, databases, and downstream tools
- CSV export with 17 individual columns and 10 family columns, UTF-8 BOM for Excel file output
- JSON export with `meta` section, `alt_names` objects, `notes` arrays, and `null` for missing years
- `--table {individuals,families}` for CSV table selection (JSON always includes both)
- `-o, --output` for file output with overwrite protection (`--force` to override)
- `--no-bom` to suppress UTF-8 BOM in CSV file output
- `--redact-living` privacy flag — replaces names and dates of estimated-living individuals with placeholders
- `--max-age N` to customize living estimation threshold (default: 110 years)
- Living estimation algorithm: requires birth year + no death record to classify as living (conservative — no birth year = not redacted)
- Family spouse name redaction when referenced individual is estimated living
- `--phonetic {soundex,metaphone}` option for `search`, `compare`, and `duplicates` commands — select between American Soundex and Double Metaphone phonetic algorithms
- Double Metaphone support via `DoubleMetaphone` library — handles European name variants (Schmidt/Smith, Müller/Miller) far better than Soundex
- `phonetic_encode()` and `phonetic_codes_match()` shared functions in `phonetics.py` for algorithm-agnostic phonetic operations
- Secondary-code blocking passes for `compare` and `duplicates` — when using metaphone, individuals are indexed under both primary and secondary codes for improved candidate recall
- 8 new validation warning codes:
  - W016/W017: Asymmetric family-individual link detection (FAM↔INDI bidirectional cross-reference integrity)
  - W026: Sibling spacing check — flags siblings born less than 9 months apart (twins excluded)
  - W027: Multiple SEX records on a single individual
  - W028: Invalid SEX value (not M, F, U, or X)
  - W029: Sex-role mismatch (HUSB with SEX F, or WIFE with SEX M)
  - W033: OBJE record missing FILE sub-record
  - W034: FILE sub-record missing FORM (media type)
- `MIN_SIBLING_SPACING_MONTHS` and `VALID_SEX_VALUES` constants
- `birth_month` field in validation `IndividualInfo` for sibling spacing checks
- Role-aware reference tracking (`indi_as_child`, `indi_as_spouse`, `fam_children`, `fam_spouses`) replacing generic connection dicts
- `duplicates` command — scan a single GEDCOM file for potential duplicate individuals using the same probabilistic scoring engine as `compare` (multi-pass blocking, weighted Jaro-Winkler, greedy one-to-one deduplication)
- `--show-matches {all,certain,probable}` filter for `duplicates` command
- `--limit N` for `duplicates` result truncation (text default: 50, JSON default: unlimited)
- `--reject-sex-mismatch` flag for `duplicates` command
- `relationship` command — determine the genealogical relationship between two individuals using Lowest Common Ancestor algorithm
- Half-relationship detection (full vs half siblings, uncles, cousins) via shared-parent counting and spouse-pairing heuristic
- Multi-key sort for relationship paths: shortest path, blood over half, male line preference
- `--paths N` option to show multiple relationship paths (default: 1)
- `--type {blood,all}` option to control half-relationship prefix display
- `--generations N` option to limit ancestor search depth (default: 30)
- Moved `ParentChildGraph`, `build_parent_child_graph`, `find_ancestors`, `find_descendants` from `commands/search/relationships.py` to shared `graph.py` module (backward-compatible re-export shim)
- `--show-text` option for `languages` command — displays the detected text for each match when using `--language`, useful for auditing language detection accuracy
- `search` command — find individuals in GEDCOM files using flexible query syntax
- Query operators: substring (`:`), exact (`=`), phonetic/Soundex (`~`), wildcard (`*`/`?`), regex (`--regex`)
- 9 query fields: `name`, `given`, `surname`, `born`, `died`, `place`, `sex`, `ancestor`, `descendant`
- Date range queries (`born:1800-1850`) with fuzzy matching for approximate dates (`--fuzzy-dates`)
- Relationship traversal via BFS (`ancestor:@I1@`, `descendant:@I5@`)
- Alternative name matching (ROMN/FONE transliterations)
- `--count` flag for match count only, `--limit` for result truncation
- Shared `phonetics.py` module — Soundex extracted from compare for reuse across commands

### Changed
- Internal field renames: `surname_soundex` → `surname_phonetic`, `given_name_soundex` → `given_phonetic` (no JSON API change — these fields are never exposed in output)
- `languages` JSON filter output: `notes` field changed from `["@N1@"]` (list of strings) to `[{"xref": "@N1@"}]` (list of objects) for consistency with `persons` and `events`

## [0.4.0]

### Added
- `compare` command — compare two GEDCOM files to find matching individuals using probabilistic record linkage (weighted Jaro-Winkler scoring, multi-pass blocking, greedy one-to-one deduplication)
- `languages` command — detects languages used in notes, stories, and event descriptions
- `--language` filter mode — lists persons, notes, and events written in a specific language (accepts name or ISO 639-1 code)
- `--min-length` option to set minimum text length threshold for language detection
- Full language model (126MB) auto-downloaded on first run
- New dependency: `fast-langdetect` for language detection
- JSON output includes `_total` fields for all array sections (enables truncation-aware consumers)
- Sex mismatch penalty visible in verbose text output and JSON (`sex_penalty` field)

### Fixed
- Year fallback logic: christening/baptism/burial dates no longer suppress year 0 via `or` short-circuit
- Stats collector: death year fallback no longer unconditionally overwrites previously extracted value
- Compare spec: corrected sex handling, blocking pass descriptions, and insufficient_data documentation

## [0.2.1]

### Added
- ANSEL encoding support — GEDCOM files with `CHAR ANSEL` are now validated and analyzed correctly

### Removed
- `E009_ANSEL_NOT_SUPPORTED` error code (ANSEL is supported via ged4py's ansel codec)

## [0.2.0]

### Added
- `isolated` command — detects singletons (component size 1) and isolated pairs (component size 2) using graph analysis
- Shared `graph.py` module with `UnionFind` and `find_connected_components` for reuse across commands

### Changed
- Consolidated age plausibility constants into shared `constants.py` module
- Improved exception handling in validation engine for malformed files
- **Breaking:** Stats JSON key `"orphans"` renamed to `"isolated"` in completeness section
- Stats text label `"Orphans:"` renamed to `"Isolated:"`
- Stats isolated count now uses graph analysis instead of FAMS/FAMC heuristic

### Fixed
- Stats isolated count now includes both singletons and pairs (aligned with isolated command)
- Pluralization fix in isolated command quiet mode ("1 pair" instead of "1 pairs")
- Documentation: Removed incorrect reference to chardet library
- Documentation: Fixed parent age threshold (< 12, not < 13)

### Removed
- Dead code: Removed unused `_has_source_citation()` method

## [0.1.1]

### Added
- Stats command with comprehensive genealogical statistics
- Life events analysis (marriage age, first child age, spousal gap)
- Research quality metrics (date precision, source depth)
- Birth pattern analysis by month
- Lifespan trends by century
- Family size distribution
- Given name frequency by gender

## [0.1.0]

### Added
- Initial release
- Validate command with 4-phase validation engine
- Quick and full validation modes
- Strict mode for GEDCOM version compliance (5.5.1, 5.5.5)
- 38 error/warning codes with descriptions
- Text and JSON output formats
- Progress indicators with timing
