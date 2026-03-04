from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gedcom_tools.commands.search.models import (
        MatchDetail,
        SearchIndividual,
        SearchResult,
    )
    from gedcom_tools.progress import Colors


_MATCH_TEXT_TEMPLATES: dict[str, str] = {
    "contains": '{field} contains "{query}"',
    "exactly": '{field} exactly "{query}"',
    "pattern": '{field} matches pattern "{query}"',
    "sounds_like": '{field} "{value}" sounds like "{query}"',
    "regex": '{field} matches "{query}"',
    "range": "{field} in {query}",
}


def _format_match_detail(
    detail: MatchDetail, verbose: bool = False, phonetic_algo: str = "soundex"
) -> str:
    template = _MATCH_TEXT_TEMPLATES.get(detail.match_type, "")
    text = template.format(
        field=detail.field,
        value=detail.matched_value,
        query=detail.query_term,
    )
    if verbose and detail.match_type == "sounds_like":
        from gedcom_tools.phonetics import phonetic_encode
        from gedcom_tools.utils import normalize_compare

        primary, alt = phonetic_encode(
            normalize_compare(detail.query_term), phonetic_algo
        )
        codes = "/".join(c for c in (primary, alt) if c)
        text += f" ({codes})"
    return text


def _lifespan(ind: SearchIndividual) -> str:
    birth = str(ind.birth_year) if ind.birth_year is not None else "?"
    death = str(ind.death_year) if ind.death_year is not None else "?"
    return f"{birth}-{death}"


def _event_line(label: str, year: int | None, place: str) -> str | None:
    if year is None:
        return None
    parts = [str(year)]
    if place:
        parts.append(place)
    return f"    {label}: {', '.join(parts)}"


def _individual_to_dict(ind: SearchIndividual) -> dict[str, Any]:
    result: dict[str, Any] = {
        "xref": ind.xref,
        "given_name": ind.given_name,
        "surname": ind.surname,
        "sex": ind.sex,
        "birth_year": ind.birth_year,
        "birth_year_approximate": ind.birth_year_approximate,
        "birth_place": ind.birth_place,
        "death_year": ind.death_year,
        "death_year_approximate": ind.death_year_approximate,
        "death_place": ind.death_place,
        "alt_names": [{"given": g, "surname": s} for g, s in ind.alt_names],
    }
    return result


def _match_detail_to_dict(detail: MatchDetail) -> dict[str, str]:
    return {
        "field": detail.field,
        "value": detail.matched_value,
        "query": detail.query_term,
        "type": detail.match_type,
    }


def format_text(
    result: SearchResult,
    colors: Colors,
    quiet: bool = False,
    verbose: bool = False,
    phonetic_algo: str = "soundex",
) -> str:
    if result.total_individuals == 0:
        return "No individuals found in file."

    if quiet:
        lines: list[str] = []
        for match in result.matches:
            ind = match.individual
            lines.append(f"  {ind.full_name} ({_lifespan(ind)}) [{ind.xref}]")
        return "\n".join(lines)

    lines = []
    lines.append(f"File: {result.file_path}")
    lines.append(f"Query: {result.query_string}")
    lines.append("")

    match_count = len(result.matches)
    total = result.total_individuals

    if match_count == 0:
        lines.append("No matches found.")
        lines.append(
            "Tip: try fewer criteria, a wider date range, "
            "or phonetic matching (surname~Schmidt)."
        )
        return "\n".join(lines)

    header = f"=== Search Results ({match_count:,} of {total:,} individuals) ==="
    lines.append(f"{colors.cyan}{header}{colors.reset}")
    lines.append("")

    for match in result.matches:
        ind = match.individual
        lines.append(f"  {ind.full_name} ({_lifespan(ind)}) [{ind.xref}]")

        born_line = _event_line("Born", ind.birth_year, ind.birth_place)
        if born_line:
            lines.append(born_line)

        died_line = _event_line("Died", ind.death_year, ind.death_place)
        if died_line:
            lines.append(died_line)

        if match.details:
            detail_texts = [
                _format_match_detail(d, verbose, phonetic_algo) for d in match.details
            ]
            lines.append(f"    Matched: {', '.join(detail_texts)}")

        lines.append("")

    # Remove trailing blank line
    if lines and lines[-1] == "":
        lines.pop()

    if result.truncated:
        lines.append(f"  (results limited to {match_count} -- use --limit 0 for all)")

    return "\n".join(lines)


def format_json(result: SearchResult) -> str:
    data: dict[str, Any] = {
        "file": result.file_path,
        "filename": Path(result.file_path).name,
        "query": result.query_string,
        "encoding": {
            "detected": result.encoding.encoding,
            "has_bom": result.encoding.has_bom,
            "declared": result.encoding.declared_charset,
        },
        "total_individuals": result.total_individuals,
        "match_count": len(result.matches),
        "truncated": result.truncated,
        "matches": [],
    }

    for match in result.matches:
        entry = _individual_to_dict(match.individual)
        entry["match_details"] = [_match_detail_to_dict(d) for d in match.details]
        data["matches"].append(entry)

    return json.dumps(data, indent=2, ensure_ascii=False)


def format_count(result: SearchResult, json_mode: bool = False) -> str:
    count = len(result.matches)
    if json_mode:
        return json.dumps({"count": count})
    return str(count)
