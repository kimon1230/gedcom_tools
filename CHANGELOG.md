# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
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
