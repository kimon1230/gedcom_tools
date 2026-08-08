# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.2.1]

### Security
- `export` wrote GEDCOM values into CSV cells verbatim, so a name, place or occupation beginning `=`, `+`, `-`, `@`, TAB or CR became a live spreadsheet formula. Opening an exported file from an untrusted tree in Excel could execute a DDE payload as the user — and the export writes a BOM, so Excel opens it as a sheet without prompting. Such values are now prefixed with a single quote. Note this is literal CSV data: a value that is legitimately just `-` or `@` now reads back with the prefix
- Names and places from the file were printed to the terminal unfiltered, so a crafted GEDCOM could emit window-title escapes, clear the screen, or use bidi overrides to reorder what the user saw — enough to fake a `✓ Valid` verdict. Terminal output is now stripped of control sequences other than the tool's own colours. Redirected and `-o` output is deliberately left untouched, since a file has nothing to interpret them
- `filter` could be made to write records that were never in its input. Line splitting used `str.splitlines()`, which breaks on eight separators GEDCOM does not recognise — U+2028, U+2029, NEL and five C0 controls — so a value containing one was a value to `validate` and structure to `filter`. A crafted note could smuggle a whole individual past `--strip-notes` into a "sanitized" export
- `export`, `filter` and `convert` created their output file at the process umask and narrowed it to `0600` only afterwards, leaving a window in which exported PII was world-readable. They also followed symlinks: a dangling link at the output path defeated the overwrite guard entirely — no `--force` needed — and `os.chmod` then rewrote the *target's* permissions. All three now create the file atomically with `O_CREAT|O_EXCL|O_NOFOLLOW` at `0600` (POSIX; on Windows the open is still atomic but cannot enforce either)
- The 126 MB language-detection model was cached in `/tmp/fasttext-langdetect`, which on a shared machine or CI runner any user can write to — and it is accepted on a filename check with no checksum, then handed to fasttext's native loader. Pre-planting a file there permanently suppressed the download and fed arbitrary bytes to that parser. The cache now lives under `$XDG_CACHE_HOME` or `~/.cache/gedcom-tools/`, created `0700`. Anyone who already has the model in `/tmp` downloads it once more; the old copy is deliberately not migrated, being exactly the untrusted artifact
- The regex guard for `--regex` searches inspected the pattern as typed while the matcher compiled a diacritic-folded copy, so inserting a combining mark between a quantifier and its group slipped a catastrophic pattern past the check. Validation now runs on the string that is actually compiled
- **`export --redact-living` now redacts substantially more people, and files that previously exported cleanly will look different.** It treated an unknown birth date as evidence of death: an individual with no birth year, no death record and no burial was published in full. Genealogy files are thin on dates for exactly the recent, private individuals the flag exists to protect. Unknown now means living. A range birth date is judged on its latest bound rather than its earliest, since that is the reading under which the person may still be alive, and a `_NLIV` "not living" tag — which comes from a file the tool did not write — is honoured only when the record carries independent death evidence, instead of being a switch for turning redaction off wholesale. On the 3,010-person `royal92.ged` reference file this takes redaction from 357 individuals to 1,227. If you were relying on the old output, export without `--redact-living` and apply your own policy downstream
- `export --redact-living` published a living couple's wedding date and named venue. Both spouse names were replaced with `Living` and both xrefs cleared, but `marriage_date`, `marriage_year` and `marriage_place` were copied through untouched in the same row — and a date plus a church, next to any unredacted child's `famc_xref` and surname, hands the redacted parents straight back. All three are now cleared when *either* spouse is estimated living, in both the CSV and the JSON emitter
- `export --max-age` accepted any integer, and `--max-age 0` silently disabled redaction entirely: every dated individual lands past a zero-year lifespan, so nobody is estimated living — while the JSON metadata still reported `"redacted_living": true`. Verified against a file containing an 11-year-old, exported in full under a `true` claim. Values below 1 are now refused with a usage error

### Fixed
- `convert --from base64` passed validation and then died in the transcoding phase with `LookupError: 'base64' is not a text encoding; use codecs.decode() to handle arbitrary codecs`. `codecs.lookup()` accepts non-text codecs, so the guard meant to catch a bad `--from` value waved them through — the same for `hex`, `zlib`, `rot13`, `bz2`, `uu` and `quopri`. They are now refused up front with `Error: Unknown source encoding: base64`, and the exit code moves from 1 to 2, which is what a bad flag value should give. The auto-detected path had the identical hole, so a file declaring `1 CHAR zlib` now reports `Cannot determine source encoding from 'ZLIB'. Use --from to specify.` rather than the same crash. ANSEL is unaffected — the `gedcom` codec is a text codec and still resolves, from `--from ansel` and from the CHAR header alike
- `validate --quick` on a file whose header runs off the end reported `Error: OSError: Unexpected EOF while reading GEDCOM header` and nothing else. It now reports `[E004] Malformed GEDCOM line -- Could not read file header`, in the same shape as every other structural error. `stats` gained the same handling, warning about the unreadable header rather than aborting on it
- `export -o <input> --force` destroyed the file it was reading. The command hand-rolled a two-line overwrite check instead of the shared safety check `convert` and `filter` use, so it had no same-file guard: a 2 KB genealogy file came back as 700 bytes of CSV, exit 0, no warning. It now routes through the shared check, which also refuses a missing output directory before parsing the file rather than after
- A command's exit code was discarded when its output was piped. The stdout flush sat inside the same `try` as the command itself, so a reader that stopped early — `| head` — turned a failed run into exit 0. A CI gate of the form `gedcom-tools validate tree.ged | head` reported success on an invalid file. The flush is now separated, and an interrupted-mid-write command still exits 0 as intended, since it never reached a verdict
- `search` was the one command that still failed on a closed pipe, printing `Error: [Errno 32] Broken pipe` and exiting non-zero where the other eight exited cleanly. It was skipped when the guard was added to the rest
- Unexpected errors rendered in two different formats depending on which subcommand was typed: `filter` named the exception type and pointed at `--verbose`, while `stats` printed the bare message. All ten sites now render through one function
- `compare`'s same-file guard could be bypassed, comparing a file against itself. The guard's `try` enclosed its own `return` alongside the `os.path.samefile()` probe, and `BrokenPipeError` is an `OSError` — so under `-q` with a stderr that could not be written to, the verdict was skipped along with the message it failed to print. The probe is now the only thing in that `try`, and the verdict no longer depends on the message getting out
- `--regex` could not match accented patterns. The pattern was compiled raw while the text it matched against had already been stripped of diacritics, so `surname:Müller` found Hans Müller but `surname:Müller --regex` found nothing. Both sides now go through the same diacritic folding — case is untouched, since the pattern already compiles with `IGNORECASE` and lowercasing it would invert `\S`, `\W` and `\D`. A pattern that will not compile after folding falls back to its raw form
- Validation reported `[E001] Unresolved cross-reference` for GEDCOM's reserved escapes. `@#DGREGORIAN@` (calendar escape) and `@@` (a literal `@`) are not pointers, but reference collection accepted any `@...@` value, so an ordinary `2 TYPE @#DGREGORIAN@` failed a file that was valid
- `export --format text` died with `invalid choice: 'text'`, naming an option `--help` does not show. The hidden alias now accepts the same vocabulary as the global flag and folds it to CSV, as it already did for every other unrecognised value
- `languages` built the GEDCOM index twice, once for the note pre-pass and once for the individual/family pass. They now share a reader — about a second off a 5,000-person file
- `convert` could silently corrupt the file it wrote. On a file whose line endings were mixed, inserting a missing `1 CHAR` header sliced the first character off the following line; and a valueless `1 CHAR` line was not recognised on CRLF or CR input, so a second one was appended next to it. The header regexes are now line-ending agnostic and reuse the terminator the HEAD record actually carries
- `convert --from` could not rescue the broken-header files it exists for. Encoding detection ran before the override was consulted and raised an error the command did not catch, so `--from ascii` on a file declaring an unknown charset still failed. Detection is now skipped entirely when `--from` is given, and the failure without it names `--from` as the remedy
- Piping any command into a consumer that stops reading — `| head`, for instance — exited **120** instead of 0. `BrokenPipeError` reached the generic error handler, and the interpreter then failed to flush stdout at shutdown
- Records referenced only by a pointer nested three or more levels deep inside an individual or family were reported as orphaned. Reference collection stopped one level below the level-1 tag while the generic path recursed fully, so a note cited under a source under a birth event looked unused
- `filter` and `convert` wrote ANSI colour codes into redirected output. Both selected colours based on whether *stderr* was a terminal while printing their results to *stdout* — the only two of ten commands to do so
- `convert` reported the wrong command name when its output path matched its input, telling the user "Filter always produces a new file"
- `export` accepted `--format` in a way that meant three different things depending on where it appeared: before the subcommand it silently produced CSV when `text` was requested and rejected `csv` outright, while after the subcommand `csv` worked. A `--to {csv,json}` flag now selects the format, `--format` remains as an alias so existing scripts keep working, and `--to` wins when both are given
- `languages` silently continued when it could not detect a file's encoding, where `stats` warned about the same input. It now catches the same specific errors and prints the same warning
- Error messages from nine commands were printed without the escape-sequence stripping the tool already applies elsewhere, so control characters embedded in a filename or in GEDCOM content could reach the terminal unfiltered
- Unexpected errors printed only the message, with no exception type and no indication that `--verbose` shows a traceback
- `--ascii` (and `GEDCOM_TOOLS_ASCII`) now reaches every decoration, not just the validation output. Six modules drew their separators from hardcoded characters and ignored the flag entirely: the `languages` table rule (53 box-drawing characters, so the whole table collapsed into a row of boxes on a console whose font lacks them), the `↔` pair separator and `×` score multiplier in `compare` and `duplicates`, and the `→` conversion arrows in `convert --quiet` and `filter --quiet`. These were written as `\uXXXX` escapes rather than literal characters, which is why the 1.2.0 sweep missed them

- `compare` and `duplicates` dropped oversized blocking groups without saying so. Any group of more than 500 individuals sharing a blocking key -- 600 people matching `SMITH|1850s`, say -- was skipped to avoid quadratic scoring, and the only symptom was a shorter list of matches. The cap itself is a deliberate trade-off and still applies; the silence was not. Both commands now warn on stderr with the number of groups skipped, and JSON output carries `oversized_blocks_skipped`, since a stderr warning does not reach a consumer reading JSON off stdout. The count is of distinct blocking keys, so one 600-member group reports as one skipped group rather than once per individual that looked it up. The warning prints under `--quiet` too, on the grounds that "these results are incomplete" is exactly what a one-line summary needs to say

### Changed
- Encoding detection no longer reads the whole file. To look at the `1 CHAR` line in a file's first few lines it opened a full GEDCOM reader, which indexes every record in the file before the header can be touched -- 1,122 ms on a 469 KB reference file, growing linearly with file size, and paid by every one of the seventeen places that ask for it (`compare` asks twice). It now calls the same codec-guessing routine the reader uses internally, against a bounded read of the header, and drops back to the old path only when the header is malformed or the `1 CHAR` line lies beyond the first 64 KB. On that same file: 1,122 ms to 2.1 ms
- **Four header shapes that previously failed or reported a mangled charset now resolve.** `1  CHAR  ANSEL` with doubled spaces reported the charset as `" ANSEL"`, leading space and all, which flowed through into `--format json` output; `1 CHAR ANSEL   ` reported `"ANSEL   "`. Both now report `ANSEL`. A tab-separated `1<TAB>CHAR<TAB>ANSEL`, a leading blank line, a junk line ahead of `0 HEAD`, or NUL bytes inside the header each made detection fail outright; all now resolve normally. For `stats` this means such a file reports its real encoding instead of `Unknown` behind a `Warning: Could not detect encoding`. For `validate` it means a file whose *structure* is broken below the header -- `tests/fixtures/malformed_line.ged`, say -- now reports its encoding as `UTF-8` where the encoding field was previously empty; the structural error itself is unchanged in both code and message, but it is now raised by the parsing phase rather than the encoding phase
- `compare` and `duplicates` gained `--max-block-size N` (default 500), which sets the point at which a blocking group is skipped as too large. It exists so the new oversized-group warning can name a remedy: raising the cap recovers the missed matches at the cost of a slower run, since scoring a group costs time proportional to the square of its size. Values below 1 are refused with a usage error
- `compare --format json` and `duplicates --format json` may now include `oversized_blocks_skipped`. It is present only when at least one blocking group was dropped, so existing consumers see no change on files that were never capped
- **A symlink at the output path is now refused, even with `--force`.** Previously `-o link.ged --force` wrote through to the link's target. If you relied on writing through a symlink, write to the real path instead
- `export --to json` metadata gained `meta.redacted_count`, the number of individuals actually replaced with `Living` placeholders (`0` without `--redact-living`). The existing `meta.redacted_living` boolean is unchanged and still reports only whether the flag was set — the two differ on a file where nothing was estimated living, which is precisely the case worth noticing before publishing an export
- Em-dashes in message prose are now written `--` in both Unicode and ASCII mode, for consistency with the `-- use --limit 0 for all` wording that `compare` already used. Affects the `--dry-run` notices in `convert` and `filter`, the truncation notice in `duplicates`, the "no HEAD record" error from `convert`, and two `search` query-validation errors. The `languages` event separator keeps its em-dash in Unicode mode — it is a field separator and now follows `--ascii` like the other decorations
- Added a regression test that walks `src/` and rejects new non-ASCII string literals outside a small allowlist, so the next hardcoded glyph fails in CI rather than shipping
- `ansel` is now a declared dependency. It was imported directly by the conversion code but reached the install only because `ged4py` happened to require it, so a future `ged4py` release dropping that edge would have broken `gedcom-tools convert` at import time
- Startup is roughly twice as fast — `gedcom-tools --version` drops from about 0.6 s to 0.3 s. The language-detection model loader was imported at module scope and pulled an HTTP stack in on every invocation; it is now loaded on first use
- Reference documentation for `--ascii` and `--no-color` was missing from six command pages and is now present on all of them
- `validate` now refuses input files larger than 500 MB, the same limit `filter` and `convert` already applied, so one command no longer silently accepts a file the rest of the tool rejects. The refusal reports the actual size and the limit on stderr and exits 1
- **`validate --format json` gained `summary.total_warnings` and `summary.suppressed`, because `summary.warnings` had quietly changed meaning.** Per-line warnings are capped at 10 per code and the remainder collapsed into one summary line — so on a file with 119 warnings, `summary.warnings` reports 71 where it previously reported 119, and the 48 that went missing existed only as English inside a message string. A CI gate thresholding on that number gets a different verdict for an unchanged file with nothing in the output to explain it. `summary.warnings` keeps its current meaning, so it stays verifiable against the length of the `issues` array; `total_warnings` carries the uncapped count and is always present, equal to `warnings` when nothing was suppressed; `suppressed` is `{code: count}` and appears only when a code was actually capped. Gates should read `total_warnings`. The W004 custom-tag cap is a separate, pre-existing site and is not tallied, so `total_warnings` is low by the dropped-tag count on a file with more than ten distinct custom tags
- `search` now rejects a term whose value looks like a home directory path on **every** field, not only on phonetic (`~`) terms. The guard exists to catch a query the shell expanded before the tool saw it — `search tree.ged ~kimon` arriving as `/home/kimon` — and that is precisely the shape the old gate could not see, since an unquoted `~` never reaches argv as a `~` term. The cost is that a value legitimately containing `/home/` is no longer searchable on any field; no `VALID_FIELDS` entry holds a filesystem path, and the message names the fix (wrap the query in single quotes)

### Internal
- The `compare`, `duplicates` and `convert` test suites went through hand-built `argparse.Namespace` objects rather than the real parser, re-declaring every default and `dest` name by hand — so renaming a flag left all of them green while the CLI raised `AttributeError`. Demonstrated: renaming `convert`'s `--to` dest fails 23 of the rewritten tests and **none** of the old ones. They now build their arguments through `create_parser().parse_args()`, and each command gained end-to-end tests that go through `main()`
- The `--redact-living` family masking is duplicated verbatim between the CSV and JSON writers. Rather than extract it — a refactor whose own acceptance criterion would have been byte-identical output — there is now a test asserting the two paths produce the same redaction over their shared fields, so a rule added to one side only fails. It also pins that the two JSON-only individual keys (`alt_names`, `notes`) are the *only* asymmetry, since the individual writers genuinely differ in shape
- Deleted verified dead code: `commands/compare/phonetics.py` (a re-export shim with zero importers; the real module is the top-level `phonetics.py`), `Spinner.FRAMES`, and two one-line `_extract_xref` pass-throughs. `validation/engine.py`'s same-named method is untouched — despite the name it carries the reserved-escape logic that stops `@#DGREGORIAN@` being reported as an unresolved pointer
- Five assertions checked that error code `E009` was absent. `E009` was removed from the enum in an earlier release, so all five were vacuously true and advertised a contract that no longer existed. `W005_MISSING_SUBM` had no assertion anywhere despite being documented and appearing in the README example; it does now
- The five dataclasses `filter` allocates per line and per record now declare `slots=True`, cutting about 1.2 MB off a 5,000-person file. Modest, but the two bulk-allocated types account for essentially all of a `filter` run's live objects
- The closed-pipe contract is now enforced structurally rather than by convention. Eight of the nine command handlers had no coverage for it at all — deleting both guards from `validate` left the suite green — which is how `search` came to be missed. A test walks the command modules and requires each to either carry a `BrokenPipeError` re-raise ahead of its generic handler, or be named in an exemption set that is itself checked for still being true. It caught the `search` omission on the first run
- A test covering error propagation could never fail: its only assertion sat inside a `try`/`except Exception`, which swallowed the `AssertionError`. The ruff rules that catch this pattern (`S110`, `BLE001`) are now enabled
- Two regression tests against the reference sample file had never executed — the fixture path was wrong, so they skipped on every run since they were written. Both pass now, and the suite has no skipped tests on Linux
- Three statistics tests asserted only inside truthiness guards, so they stayed green if the statistic disappeared entirely; two of their fixtures were also missing the family links needed to reach the code under test at all
- The GEDCOM tag sets shared by `stats` and `languages` were duplicated verbatim in both modules and have been hoisted to a single definition
- CI caches the 126 MB language-detection model on the Linux jobs, so a third-party CDN outage no longer turns into a failed build

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
