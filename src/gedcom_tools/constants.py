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

# Stats-specific thresholds
MIN_MARRIAGE_AGE = 12
MAX_MARRIAGE_AGE = 80
MAX_FIRST_CHILD_AGE = 70  # Exclude implausible ages from first-child stats
MAX_SPOUSAL_AGE_GAP = 50
