from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gedcom_tools.progress import glyphs

if TYPE_CHECKING:
    from gedcom_tools.commands.compare.models import (
        CompareIndividual,
        CompareResult,
        MatchPair,
    )
    from gedcom_tools.progress import Colors


def _format_individual(ind: CompareIndividual) -> str:
    name = ind.full_name or "Unknown"
    birth = str(ind.birth_year) if ind.birth_year is not None else "?"
    death = str(ind.death_year) if ind.death_year is not None else "?"
    return f"{name} ({birth}-{death}) [{ind.source_file}:{ind.xref}]"


def _format_unique_individual(ind: CompareIndividual) -> str:
    name = ind.full_name or "Unknown"
    birth = str(ind.birth_year) if ind.birth_year is not None else "?"
    death = str(ind.death_year) if ind.death_year is not None else "?"
    return f"{name} ({birth}-{death}) [{ind.xref}]"


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
        header = f"=== {section_title} ({total:,} total, showing first {limit}) ==="
        display = pairs[:limit]
    else:
        header = f"=== {section_title} ({total:,}) ==="
        display = pairs

    lines.append(f"{colors.cyan}{header}{colors.reset}")

    for pair in display:
        ind_a = _format_individual(pair.individual_a)
        ind_b = _format_individual(pair.individual_b)
        lines.append(f"  {ind_a} {g.pair} {ind_b}  score: {pair.score.total:.2f}")

        if pair.field_diffs:
            for diff in pair.field_diffs:
                lines.append(
                    f'    {diff.field}: "{diff.value_a}" (A)'
                    f' vs "{diff.value_b}" (B)'
                )
        else:
            lines.append("    (no differences)")

        if verbose:
            score_parts = [
                f"{field} {value:.2f}"
                for field, value in pair.score.field_scores.items()
            ]
            if pair.score.sex_penalty:
                score_parts.append(f"Sex mismatch {g.times}0.70")
            lines.append(f"    Scores: {', '.join(score_parts)}")

    if limit > 0 and total > limit:
        remaining = total - limit
        lines.append(f"  ({remaining:,} more -- use --limit 0 for all)")

    return lines


def _format_unique_section(
    individuals: list[CompareIndividual],
    section_title: str,
    colors: Colors,
    limit: int,
) -> list[str]:
    total = len(individuals)
    if total == 0:
        return []

    lines: list[str] = []

    if limit > 0 and total > limit:
        header = f"=== {section_title} ({total:,} total, showing first {limit}) ==="
        display = individuals[:limit]
    else:
        header = f"=== {section_title} ({total:,}) ==="
        display = individuals

    lines.append(f"{colors.cyan}{header}{colors.reset}")

    for ind in display:
        lines.append(f"  {_format_unique_individual(ind)}")

    if limit > 0 and total > limit:
        remaining = total - limit
        lines.append(f"  ({remaining:,} more -- use --limit 0 for all)")

    return lines


def _match_pair_to_dict(pair: MatchPair) -> dict[str, Any]:
    return {
        "individual_a": _individual_summary(pair.individual_a),
        "individual_b": _individual_summary(pair.individual_b),
        "score": pair.score.total,
        "classification": pair.score.classification,
        "insufficient_data": pair.score.insufficient_data,
        "name_only": pair.score.name_only,
        "comparable_field_count": pair.score.comparable_field_count,
        "sex_penalty": pair.score.sex_penalty,
        "field_scores": pair.score.field_scores,
        "differences": [
            {
                "field": diff.field,
                "value_a": diff.value_a,
                "value_b": diff.value_b,
            }
            for diff in pair.field_diffs
        ],
    }


def _individual_summary(ind: CompareIndividual) -> dict[str, Any]:
    return {
        "xref": ind.xref,
        "name": ind.full_name or "Unknown",
        "birth_year": ind.birth_year,
        "death_year": ind.death_year,
    }


def format_text(
    result: CompareResult,
    colors: Colors,
    quiet: bool = False,
    verbose: bool = False,
    show_matches: str = "all",
    list_unique: bool = False,
    limit: int = 0,
) -> str:
    """Format comparison results as human-readable text."""
    if quiet:
        file_a = Path(result.file_a).name
        file_b = Path(result.file_b).name
        return (
            f"{len(result.certain_matches):,} certain, "
            f"{len(result.probable_matches):,} probable, "
            f"{len(result.unique_to_a):,} unique to {file_a}, "
            f"{len(result.unique_to_b):,} unique to {file_b}"
        )

    lines: list[str] = []

    # Header
    lines.append(f"File A: {result.file_a}")
    lines.append(f"File B: {result.file_b}")
    lines.append(f"Encoding A: {result.encoding_a}")
    lines.append(f"Encoding B: {result.encoding_b}")
    lines.append("")

    # Summary
    lines.append(f"{colors.cyan}=== Comparison Summary ==={colors.reset}")
    lines.append(f"  Individuals in A: {result.total_a:>8,}")
    lines.append(f"  Individuals in B: {result.total_b:>8,}")
    lines.append(f"  Certain matches:  {len(result.certain_matches):>8,}")
    lines.append(f"  Probable matches: {len(result.probable_matches):>8,}")
    lines.append(f"  Unique to A:      {len(result.unique_to_a):>8,}")
    lines.append(f"  Unique to B:      {len(result.unique_to_b):>8,}")

    # Certain Matches
    if show_matches in ("all", "certain"):
        certain_lines = _format_match_section(
            result.certain_matches, "Certain Matches", colors, verbose, limit
        )
        if certain_lines:
            lines.append("")
            lines.extend(certain_lines)

    # Probable Matches
    if show_matches in ("all", "probable"):
        probable_lines = _format_match_section(
            result.probable_matches, "Probable Matches", colors, verbose, limit
        )
        if probable_lines:
            lines.append("")
            lines.extend(probable_lines)

    # Unique sections
    if list_unique:
        unique_a_lines = _format_unique_section(
            result.unique_to_a, "Unique to A", colors, limit
        )
        if unique_a_lines:
            lines.append("")
            lines.extend(unique_a_lines)

        unique_b_lines = _format_unique_section(
            result.unique_to_b, "Unique to B", colors, limit
        )
        if unique_b_lines:
            lines.append("")
            lines.extend(unique_b_lines)
    elif result.unique_to_a or result.unique_to_b:
        lines.append("")
        lines.append("  Tip: use --list-unique to see names of unmatched individuals.")

    return "\n".join(lines)


def format_json(
    result: CompareResult,
    show_matches: str = "all",
    list_unique: bool = False,
    limit: int = 0,
) -> str:
    """Format comparison results as JSON."""
    certain = result.certain_matches if show_matches in ("all", "certain") else []
    probable = result.probable_matches if show_matches in ("all", "probable") else []
    unique_a = result.unique_to_a if list_unique else []
    unique_b = result.unique_to_b if list_unique else []

    certain_total = len(certain)
    probable_total = len(probable)
    unique_a_total = len(unique_a)
    unique_b_total = len(unique_b)

    if limit > 0:
        certain = certain[:limit]
        probable = probable[:limit]
        unique_a = unique_a[:limit]
        unique_b = unique_b[:limit]

    data: dict[str, Any] = {
        "file_a": result.file_a,
        "filename_a": Path(result.file_a).name,
        "file_b": result.file_b,
        "filename_b": Path(result.file_b).name,
        "encoding_a": {
            "detected": result.encoding_a.encoding,
            "has_bom": result.encoding_a.has_bom,
            "declared": result.encoding_a.declared_charset,
        },
        "encoding_b": {
            "detected": result.encoding_b.encoding,
            "has_bom": result.encoding_b.has_bom,
            "declared": result.encoding_b.declared_charset,
        },
        "total_a": result.total_a,
        "total_b": result.total_b,
        "certain_matches": [_match_pair_to_dict(p) for p in certain],
        "certain_matches_total": certain_total,
        "probable_matches": [_match_pair_to_dict(p) for p in probable],
        "probable_matches_total": probable_total,
        "unique_to_a": [_individual_summary(ind) for ind in unique_a],
        "unique_to_a_total": unique_a_total,
        "unique_to_b": [_individual_summary(ind) for ind in unique_b],
        "unique_to_b_total": unique_b_total,
    }

    # Only present when recall was actually capped -- a stderr warning does
    # not reach a consumer reading JSON off stdout.
    if result.oversized_blocks_skipped:
        data["oversized_blocks_skipped"] = result.oversized_blocks_skipped

    return json.dumps(data, indent=2, ensure_ascii=False)
