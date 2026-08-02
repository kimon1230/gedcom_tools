# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE_ERROR = 2

# Age plausibility thresholds for VALIDATION (used for warnings)
# Note: Stats uses MAX_LIFESPAN_YEARS = 110 in collector.py for "estimated living"
# calculation. This is intentionally lower (more conservative) for determining
# if someone born N years ago might still be alive.
MAX_LIFESPAN = 120  # W023: Age at death implausible if > 120
MIN_PARENT_AGE = 12
MAX_PARENT_AGE_AT_BIRTH = 80
MIN_SIBLING_SPACING_MONTHS = 9
VALID_SEX_VALUES = frozenset({"M", "F", "U", "X"})

# Stats-specific thresholds
MIN_MARRIAGE_AGE = 12
MAX_MARRIAGE_AGE = 80
MAX_FIRST_CHILD_AGE = 70  # Exclude implausible ages from first-child stats
MAX_SPOUSAL_AGE_GAP = 50

# Reject threshold for byte-level operations (filter, convert). This is a
# backstop against absurd input, NOT a statement that files near it will work:
# filter holds the raw bytes, the decoded text, one object per line and one per
# record all at once, which measures at roughly 25x the file size (more on files
# with very short lines). A file at this cap would need something like 12 GB of
# RAM and would die of memory exhaustion long before the check mattered.
#
# The practical ceiling on an ordinary machine is nearer 50-80 MB. Lowering the
# constant to match was considered and rejected: it would reject files that
# process fine today to guard against a user exhausting their own memory with
# their own file. The real fix is to stream the filter parse - see the note in
# ~/.claude/plans/gedcom_tools/ on why that is not a small change.
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB

# Tags on INDI sub-records that are NOT events/attributes.
# Shared by the languages command and the stats collector so both agree on
# what counts as an event when attributing notes.
INDI_NON_EVENT_TAGS = frozenset(
    {
        "NAME",
        "SEX",
        "NOTE",
        "FAMC",
        "FAMS",
        "SOUR",
        "OBJE",
        "CHAN",
        "RFN",
        "AFN",
        "REFN",
        "RIN",
        "ALIA",
        "ANCI",
        "DESI",
        "SUBM",
        "ASSO",
        "RESN",
    }
)

# Tags on FAM sub-records that are NOT events
FAM_NON_EVENT_TAGS = frozenset(
    {
        "HUSB",
        "WIFE",
        "CHIL",
        "NCHI",
        "NOTE",
        "SOUR",
        "OBJE",
        "CHAN",
        "REFN",
        "RIN",
        "SUBM",
    }
)
