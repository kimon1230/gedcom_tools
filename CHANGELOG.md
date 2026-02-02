# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed
- Consolidated age plausibility constants into shared `constants.py` module
- Improved exception handling in validation engine for malformed files

### Fixed
- Documentation: Removed incorrect reference to chardet library
- Documentation: Fixed parent age threshold (< 12, not < 13)

### Removed
- Dead code: Removed unused `_has_source_citation()` method

## [0.0.2]

### Added
- Stats command with comprehensive genealogical statistics
- Life events analysis (marriage age, first child age, spousal gap)
- Research quality metrics (date precision, source depth)
- Birth pattern analysis by month
- Lifespan trends by century
- Family size distribution
- Given name frequency by gender

## [0.0.1]

### Added
- Initial release
- Validate command with 4-phase validation engine
- Quick and full validation modes
- Strict mode for GEDCOM version compliance (5.5.1, 5.5.5)
- 38 error/warning codes with descriptions
- Text and JSON output formats
- Progress indicators with timing
