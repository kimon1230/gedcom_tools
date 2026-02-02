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
MAX_MOTHER_AGE = 50
MAX_FATHER_AGE = 80

# Stats-specific thresholds
MIN_MARRIAGE_AGE = 12
MAX_MARRIAGE_AGE = 80
MAX_PARENT_AGE = 70  # For first-child age filtering
MAX_SPOUSAL_AGE_GAP = 50
