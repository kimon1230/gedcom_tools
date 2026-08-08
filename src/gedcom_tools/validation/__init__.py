"""Validation module for GEDCOM files.

This module provides the main validation functionality:
- validate_file(): Main entry point for validating a GEDCOM file
- ValidationResult: Result container with issues and metadata
- ValidationIssue: Individual validation issue
- ErrorCode: Enumeration of all error/warning codes
- Severity: ERROR or WARNING
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Literal

from gedcom_tools.validation.engine import FileTooLargeError, ValidationEngine
from gedcom_tools.validation.issues import ErrorCode, Severity, ValidationIssue
from gedcom_tools.validation.result import ValidationResult

__all__ = [
    "validate_file",
    "ValidationResult",
    "ValidationIssue",
    "ErrorCode",
    "Severity",
    "FileTooLargeError",
]


def validate_file(
    file_path: Path | str,
    mode: Literal["quick", "full"] = "quick",
    strict: str | None = None,
    quiet: bool = False,
    verbose: bool = False,
    no_color: bool = False,
    stream: IO[str] | None = None,
) -> ValidationResult:
    """Validate a GEDCOM file.

    Parameters
    ----------
    file_path
        Path to the GEDCOM file to validate.
    mode
        Validation mode: "quick" stops on first error, "full" collects all.
    strict
        GEDCOM version for strict validation (e.g., "5.5.1", "5.5.5").
        If None, allows any valid GEDCOM.
    quiet
        If True, suppress progress output.
    verbose
        If True, show detailed progress with timing information.
    no_color
        If True, disable colored output.
    stream
        Output stream for progress messages. Defaults to stderr.

    Returns
    -------
    ValidationResult
        Result containing all issues found and file metadata.
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path

    engine = ValidationEngine(
        file_path=path,
        mode=mode,
        strict=strict,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
        stream=stream,
    )

    return engine.validate()
