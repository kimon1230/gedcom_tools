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

# File size limit for byte-level operations (filter, convert)
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
