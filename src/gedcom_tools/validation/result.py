"""Validation result and formatters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gedcom_tools.progress import glyphs
from gedcom_tools.utils import EncodingInfo
from gedcom_tools.validation.issues import Severity, ValidationIssue

if TYPE_CHECKING:
    from gedcom_tools.progress import Colors


@dataclass
class ValidationResult:
    """Result of validating a GEDCOM file."""

    file_path: str
    issues: list[ValidationIssue] = field(default_factory=list)
    encoding_info: EncodingInfo | None = None
    record_counts: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return only error-level issues."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return only warning-level issues."""
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def success(self) -> bool:
        """Return True if no errors were found."""
        return len(self.errors) == 0

    def format_text(self, colors: Colors, quiet: bool = False) -> str:
        if quiet:
            return self._format_text_quiet(colors)
        return self._format_text_full(colors)

    def _format_text_quiet(self, colors: Colors) -> str:
        """Format for quiet mode: errors only, nothing else."""
        if not self.errors:
            return ""

        lines: list[str] = []
        for issue in self.errors:
            lines.append(self._format_issue(issue, colors))
        return "\n".join(lines)

    def _format_text_full(self, colors: Colors) -> str:
        """Format with full details: file info, all issues, summary."""
        lines: list[str] = []

        # Header with file info
        lines.append(f"File: {self.file_path}")
        if self.encoding_info:
            lines.append(f"Encoding: {self.encoding_info}")

        # Record counts summary
        if self.record_counts:
            counts = ", ".join(
                f"{count} {rtype}"
                for rtype, count in sorted(self.record_counts.items())
            )
            lines.append(f"Records: {counts}")

        lines.append("")

        # Issues grouped by severity
        if self.errors:
            lines.append(f"{colors.red}Errors ({len(self.errors)}):{colors.reset}")
            for issue in self.errors:
                lines.append(f"  {self._format_issue(issue, colors)}")
            lines.append("")

        if self.warnings:
            lines.append(
                f"{colors.yellow}Warnings ({len(self.warnings)}):{colors.reset}"
            )
            for issue in self.warnings:
                lines.append(f"  {self._format_issue(issue, colors)}")
            lines.append("")

        # Summary
        marks = glyphs()
        if self.success:
            if self.warnings:
                lines.append(
                    f"{colors.green}{marks.check} Valid{colors.reset} "
                    f"(with {len(self.warnings)} warning(s))"
                )
            else:
                lines.append(f"{colors.green}{marks.check} Valid{colors.reset}")
        else:
            lines.append(
                f"{colors.red}{marks.cross} Invalid{colors.reset} "
                f"({len(self.errors)} error(s), {len(self.warnings)} warning(s))"
            )

        return "\n".join(lines)

    def _format_issue(self, issue: ValidationIssue, colors: Colors) -> str:
        """Format a single issue for text output.

        Format:
          [CODE] Description
            Line N: @XREF@ Specific message
            → Context (if present)

        The description tells users what the code means.
        The message gives specific details about this instance.
        """
        code_color = colors.red if issue.severity == Severity.ERROR else colors.yellow

        # First line: code and description (what this error type means)
        header = (
            f"{code_color}[{issue.code.value}]{colors.reset} {issue.code.description}"
        )

        # Second line: specific details about this instance
        detail_parts = []
        if issue.line is not None:
            detail_parts.append(f"Line {issue.line}:")
        if issue.xref:
            detail_parts.append(f"{colors.cyan}{issue.xref}{colors.reset}")
        detail_parts.append(issue.message)

        detail = " ".join(detail_parts)
        result = f"{header}\n    {colors.dim}{detail}{colors.reset}"

        # Third line: context (if present)
        if issue.context:
            arrow = glyphs().arrow
            result += f"\n    {colors.dim}{arrow} {issue.context}{colors.reset}"

        return result

    def format_json(self) -> str:
        """Format the result as JSON."""
        encoding_data: dict[str, object] | None = None
        if self.encoding_info:
            encoding_data = {
                "detected": self.encoding_info.encoding,
                "has_bom": self.encoding_info.has_bom,
                "declared": self.encoding_info.declared_charset,
            }

        issues_list: list[dict[str, object]] = []
        for issue in self.issues:
            issue_data: dict[str, object] = {
                "code": issue.code.value,
                "description": issue.code.description,
                "severity": issue.severity.value,
                "message": issue.message,
            }
            if issue.line is not None:
                issue_data["line"] = issue.line
            if issue.xref:
                issue_data["xref"] = issue.xref
            if issue.context:
                issue_data["context"] = issue.context
            issues_list.append(issue_data)

        from pathlib import Path as _Path

        data: dict[str, object] = {
            "file": self.file_path,
            "filename": _Path(self.file_path).name,
            "valid": self.success,
            "encoding": encoding_data,
            "record_counts": self.record_counts,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "issues": issues_list,
        }

        return json.dumps(data, indent=2)
