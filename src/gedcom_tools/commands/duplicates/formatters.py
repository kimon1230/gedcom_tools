from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gedcom_tools.progress import glyphs

if TYPE_CHECKING:
    from gedcom_tools.commands.compare.models import (
        CompareIndividual,
        MatchPair,
    )
    from gedcom_tools.commands.duplicates.models import DuplicatesResult
    from gedcom_tools.progress import Colors


def _year_range(birth: int | None, death: int | None) -> str:
    b = str(birth) if birth is not None else "?"
    d = str(death) if death is not None else "?"
    return f"{b}-{d}"


def _format_match_section(
    pairs: list[MatchPair],
    section_title: str,
    colors: Colors,
    verbose: bool,
    limit: int,
) -> list[str]:
    g = glyphs()
    total = len(pairs)
    if total == 0:
        return []

    lines: list[str] = []

    if limit > 0 and total > limit:
        header = f"=== {section_title} ({total} total, showing first {limit}) ==="
        display = pairs[:limit]
    else:
        header = f"=== {section_title} ({total}) ==="
        display = pairs

    lines.append(f"{colors.cyan}{header}{colors.reset}")

    for pair in display:
        a = pair.individual_a
        b = pair.individual_b
        a_years = _year_range(a.birth_year, a.death_year)
        b_years = _year_range(b.birth_year, b.death_year)
        a_name = a.full_name or "Unknown"
        b_name = b.full_name or "Unknown"
        suffix = ""
        if pair.score.insufficient_data:
            suffix = " (low confidence)"
        lines.append(
            f"  {a_name} ({a_years}) [{a.xref}] "
            f"{g.pair} {b_name} ({b_years}) [{b.xref}]  "
            f"score: {pair.score.total:.2f}{suffix}"
        )

        if pair.field_diffs:
            for diff in pair.field_diffs:
                lines.append(f'    {diff.field}: "{diff.value_a}" vs "{diff.value_b}"')
        else:
            lines.append("    (no differences)")

        if verbose and pair.score.field_scores:
            parts = [f"{k} {v:.2f}" for k, v in pair.score.field_scores.items()]
            if pair.score.sex_penalty:
                parts.append(f"Sex mismatch {g.times}0.70")
            lines.append(f"    [Scores: {', '.join(parts)}]")

    if limit > 0 and total > limit:
        remaining = total - limit
        lines.append(f"  ({remaining} more -- use --limit 0 for all)")

    return lines


def format_text(
    result: DuplicatesResult,
    colors: Colors,
    quiet: bool = False,
    verbose: bool = False,
    show_matches: str = "all",
    limit: int = 0,
) -> str:
    if quiet:
        return (
            f"{len(result.certain_matches)} certain, "
            f"{len(result.probable_matches)} probable"
        )

    lines: list[str] = [f"File: {result.file}"]
    lines.append("")
    lines.append(f"{colors.cyan}=== Duplicate Scan Summary ==={colors.reset}")
    lines.append(f"  Individuals scanned: {result.total_individuals:>5}")
    lines.append(f"  Certain duplicates:  {len(result.certain_matches):>5}")
    lines.append(f"  Probable duplicates: {len(result.probable_matches):>5}")

    if show_matches in ("all", "certain"):
        certain_lines = _format_match_section(
            result.certain_matches, "Certain Duplicates", colors, verbose, limit
        )
        if certain_lines:
            lines.append("")
            lines.extend(certain_lines)

    if show_matches in ("all", "probable"):
        probable_lines = _format_match_section(
            result.probable_matches, "Probable Duplicates", colors, verbose, limit
        )
        if probable_lines:
            lines.append("")
            lines.extend(probable_lines)

    return "\n".join(lines)


def _individual_to_dict(ind: CompareIndividual) -> dict[str, Any]:
    return {
        "xref": ind.xref,
        "name": ind.full_name or "Unknown",
        "given_name": ind.given_name,
        "surname": ind.surname,
        "sex": ind.sex,
        "birth_year": ind.birth_year,
        "birth_place": ind.birth_place,
        "death_year": ind.death_year,
        "death_place": ind.death_place,
    }


def _pair_to_dict(pair: MatchPair) -> dict[str, Any]:
    d: dict[str, Any] = {
        "individual_a": _individual_to_dict(pair.individual_a),
        "individual_b": _individual_to_dict(pair.individual_b),
        "score": round(pair.score.total, 4),
        "classification": pair.score.classification,
        "field_scores": {k: round(v, 4) for k, v in pair.score.field_scores.items()},
        "differences": [
            {
                "field": fd.field,
                "value_a": fd.value_a,
                "value_b": fd.value_b,
            }
            for fd in pair.field_diffs
        ],
    }
    if pair.score.insufficient_data:
        d["insufficient_data"] = True
    return d


def format_json(
    result: DuplicatesResult,
    show_matches: str = "all",
    limit: int = 0,
) -> str:
    certain = result.certain_matches if show_matches in ("all", "certain") else []
    probable = result.probable_matches if show_matches in ("all", "probable") else []

    certain_total = len(certain)
    probable_total = len(probable)

    certain_display = certain[:limit] if limit > 0 else certain
    probable_display = probable[:limit] if limit > 0 else probable

    output: dict[str, Any] = {
        "file": result.file,
        "filename": Path(result.file).name,
        "encoding": {
            "detected": result.encoding.encoding,
            "has_bom": result.encoding.has_bom,
            "declared": result.encoding.declared_charset,
        },
        "total_individuals": result.total_individuals,
        "certain_duplicates": [_pair_to_dict(p) for p in certain_display],
        "certain_duplicates_total": certain_total,
        "probable_duplicates": [_pair_to_dict(p) for p in probable_display],
        "probable_duplicates_total": probable_total,
    }

    return json.dumps(output, indent=2, ensure_ascii=False)
