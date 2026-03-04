"""Text and JSON formatters for the relationship command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gedcom_tools.commands.relationship.models import (
        RelationshipResult,
        RelIndividual,
    )
    from gedcom_tools.progress import Colors


def _lifespan(ind: RelIndividual) -> str:
    birth = str(ind.birth_year) if ind.birth_year is not None else "?"
    death = str(ind.death_year) if ind.death_year is not None else "?"
    return f"{birth}-{death}"


def _individual_to_dict(ind: RelIndividual) -> dict[str, Any]:
    return {
        "xref": ind.xref,
        "name": ind.name,
        "sex": ind.sex,
        "birth_year": ind.birth_year,
        "death_year": ind.death_year,
    }


def format_text(
    result: RelationshipResult,
    colors: Colors,
    quiet: bool = False,
    verbose: bool = False,
    truncated: bool = False,
) -> str:
    p = result.primary
    t = result.target

    if quiet:
        if not result.related:
            return f"{t.name} and {p.name} are not related."
        return "\n".join(r.description for r in result.relationships)

    lines: list[str] = []
    lines.append(f"File: {result.file}")
    lines.append("")

    if not result.related:
        lines.append(f"  {p.name} ({_lifespan(p)}) [{p.xref}]")
        lines.append(f"  {t.name} ({_lifespan(t)}) [{t.xref}]")
        lines.append("")
        lines.append("  No relationship found.")
        if verbose and truncated:
            lines.append("")
            lines.append(
                f"  {colors.yellow}Warning: Search was limited by --generations. "
                f"There may be additional relationships beyond this "
                f"depth.{colors.reset}"
            )
        return "\n".join(lines)

    count = len(result.relationships)
    if count == 1:
        header = "=== Relationship ==="
    else:
        header = f"=== Relationships ({count} found) ==="

    lines.append(f"{colors.cyan}{header}{colors.reset}")
    lines.append("")
    lines.append(f"  {p.name} ({_lifespan(p)}) [{p.xref}]")
    lines.append(f"  {t.name} ({_lifespan(t)}) [{t.xref}]")
    lines.append("")

    if count == 1:
        lines.append(f"  {result.relationships[0].description}")
    else:
        for i, rel in enumerate(result.relationships, 1):
            lines.append(f"  {i}. {rel.description}")

    total = result.total_paths
    if total > count:
        lines.append("")
        lines.append(
            f"  ({count} of {total} relationships shown. "
            f"Use --paths {total} to see all.)"
        )

    if verbose and truncated:
        lines.append("")
        lines.append(
            f"  {colors.yellow}Warning: Search was limited by --generations. "
            f"There may be additional relationships beyond this "
            f"depth.{colors.reset}"
        )

    return "\n".join(lines)


def format_json(result: RelationshipResult) -> str:
    data: dict[str, Any] = {
        "file": result.file,
        "filename": Path(result.file).name,
        "primary": _individual_to_dict(result.primary),
        "target": _individual_to_dict(result.target),
        "related": result.related,
        "relationships": [
            {
                "type": r.type,
                "gen_from_primary": r.gen_p,
                "gen_from_target": r.gen_t,
                "common_ancestors": r.common_ancestors,
                "is_half": r.is_half,
                "description": r.description,
            }
            for r in result.relationships
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
