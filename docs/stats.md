# Stats Command

The `stats` command analyzes a GEDCOM file and produces genealogical statistics.

## Usage

```bash
gedcom-tools stats <file> [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--format {text,json}` | Output format (default: text) |
| `--top N` | Number of items in top-N lists (default: 10) |
| `-v, --verbose` | Show timing information |
| `-q, --quiet` | One-line summary of record counts |

### Quiet Mode

With `-q`, outputs a single line:

```
100 individuals, 50 families, 10 sources, 25 locations
```

## Output Sections

### Record Counts

Basic counts of records in the file: individuals, families, sources, locations.

### Timeline

- Earliest/latest events with cross-reference IDs (xref) and dates
- Date span in years
- Distribution by century

Note: Timeline entries in JSON output include the xref but not the
individual's name. Names are excluded to prevent PII leakage when stats
output is shared or logged.

### Tree Structure

- Maximum generation depth
- Largest families

### Demographics

- Gender distribution
- Top surnames and lineages
- Top given names by gender

### Data Completeness

Coverage metrics showing how complete the data is:

| Metric | Description |
|--------|-------------|
| Birth Date | Individuals with a birth (or christening/baptism) date |
| Death Date | Individuals with a death (or burial) date |
| Marriage Date | Families with a marriage date |
| Source Citations | Individuals with at least one SOUR reference |
| Notes | Individuals with a NOTE record |
| Media | Individuals with an OBJE (media) record |
| Isolated | Individuals in components of size 1 (singletons) or 2 (pairs) — see [isolated command](isolated.md) |
| Estimated Living | Individuals estimated to be alive (born after threshold year, no death record) |

Each metric shows: count / total (percentage).

### Life Events

Statistics about life events, filtered for plausibility:

| Stat | Filter |
|------|--------|
| Age at first marriage | 12-80 years |
| Age at first child | 12-70 years |
| Spousal age gap | 0-50 years |

Marriage ages are broken down by gender and by birth century.

### Family Size

Distribution of children per family.

**Important:** Only includes families with at least one child. Childless
marriages are excluded from this statistic.

Buckets: 1, 2-3, 4-6, 7-9, 10+

### Birth Patterns

Monthly distribution of births.

**Important:** Only includes actual birth dates that are not approximate.
Dates marked with ABT, BEF, AFT, etc. are excluded because the month may
be uncertain. Christening/baptism dates are also excluded.

### Lifespan Trends

Average lifespan by birth century. Filtered to 0-120 years to exclude data
errors.

### Research Quality

Indicators of data completeness:

#### Birth Date Precision

How complete are birth dates?

| Category | Description |
|----------|-------------|
| Full | day + month + year (e.g., "2 Oct 1822") |
| Partial | month + year, or year only (e.g., "Oct 1850", "1850") |
| Approximate | dates with ABT, BEF, AFT, EST, CAL, CIRCA, etc. |
| Missing | no date recorded |

Approximate dates are sub-classified:
- **with full date**: ABT 15 JAN 1850 (approximate but has all components)
- **with partial date**: ABT 1850 (approximate and incomplete)

**Note:** Only birth dates are analyzed. Death dates and marriage dates are
not included in this metric.

#### Occupation Coverage

Percentage of individuals with at least one occupation recorded.

**Limitation:** Only the first occupation found is counted. Individuals with
multiple occupations over their lifetime are counted once.

#### Source Depth

Average number of source citations per person. Sources are counted
recursively through all sub-records (e.g., a source on `INDI/BIRT/SOUR`
counts the same as `INDI/SOUR`).

## JSON Output

Use `--format json` for machine-readable output.

### Schema

See [stats-schema.json](stats-schema.json) for the formal JSON Schema
(draft 2020-12).

## Notes

### Christening vs Birth Dates

When a birth date is missing, the tool falls back to christening (CHR) or
baptism (BAPM) dates for the birth **year** only.

The following are NOT extracted from christening dates:
- Birth **month** (the ceremony date differs from birth date)
- Birth date **precision** (the precision applies to the ceremony, not birth)

### Approximate Date Handling

Dates with prefixes like ABT, BEF, AFT, EST, CAL, CIRCA are treated as
approximate:
- They ARE included in age calculations (using the year component)
- They are NOT included in birth month statistics (month may be uncertain)
- They are classified separately in date precision statistics

### Plausibility Filtering

Extreme values are filtered to avoid data errors skewing statistics:

| Metric | Valid Range |
|--------|-------------|
| Marriage age | 12-80 years |
| Parent age at first child | 12-70 years |
| Spousal age gap | 0-50 years |
| Lifespan | 0-120 years |

Values outside these ranges are silently excluded from aggregates.
These thresholds are defined in `src/gedcom_tools/constants.py`.

## Related Commands

- [`search`](search.md) -- find individuals using flexible query syntax
- [`validate`](validate.md) -- check file structure and data issues
- [`isolated`](isolated.md) -- detect unconnected individuals
- [`languages`](languages.md) -- detect languages in notes and events
- [`compare`](compare.md) -- cross-file individual matching
