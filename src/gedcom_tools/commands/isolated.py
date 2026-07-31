"""Isolated command — find individuals with no effective family connections."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ged4py.parser import GedcomReader

from gedcom_tools.constants import EXIT_ERROR, EXIT_SUCCESS
from gedcom_tools.dates import extract_year_from_date
from gedcom_tools.graph import find_connected_components
from gedcom_tools.progress import Colors, PhaseTracker
from gedcom_tools.utils import extract_xref, validate_input_file

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction


@dataclass
class IsolatedIndividual:

    xref: str
    name: str = ""
    sex: str = ""
    birth_year: int | None = None


@dataclass
class IsolatedResult:

    file_path: str
    total_individuals: int
    singletons: list[IsolatedIndividual] = field(default_factory=list)
    pairs: list[list[IsolatedIndividual]] = field(default_factory=list)

    @property
    def isolated_count(self) -> int:
        return len(self.singletons) + 2 * len(self.pairs)

    def format_text(self, colors: Colors, quiet: bool = False) -> str:
        if quiet:
            if self.isolated_count == 0:
                return ""
            s_label = "singleton" if len(self.singletons) == 1 else "singletons"
            p_label = "pair" if len(self.pairs) == 1 else "pairs"
            return (
                f"{self.isolated_count} isolated "
                f"({len(self.singletons)} {s_label}, "
                f"{len(self.pairs)} {p_label})"
            )

        lines: list[str] = [f"File: {self.file_path}", ""]

        lines.append(_header(colors, "Isolated Analysis"))
        lines.append(f"  Total individuals:    {self.total_individuals:>5}")
        if self.total_individuals > 0:
            pct = self.isolated_count / self.total_individuals * 100
            lines.append(
                f"  Isolated individuals: {self.isolated_count:>5} ({pct:.1f}%)"
            )
        else:
            lines.append(f"  Isolated individuals: {self.isolated_count:>5}")
        lines.append(f"    Singletons:         {len(self.singletons):>5}")
        lines.append(
            f"    Isolated pairs:     {len(self.pairs):>5}"
            + (f" ({len(self.pairs) * 2} individuals)" if self.pairs else "")
        )

        if self.singletons:
            lines.append("")
            lines.append(_header(colors, "Singletons"))
            lines.append("  These individuals have no effective family connections.")
            lines.append(
                "  They may need to be linked to a family or removed if added in error."
            )
            lines.append("")
            for i, ind in enumerate(self.singletons, 1):
                lines.append(f"  {i}. {_format_individual(ind)}")

        if self.pairs:
            lines.append("")
            lines.append(_header(colors, "Isolated Pairs"))
            lines.append(
                "  These pairs are connected only to each other,"
                " with no link to anyone else."
            )
            lines.append("")
            for i, pair in enumerate(self.pairs, 1):
                lines.append(f"  {i}. {_format_individual(pair[0])}")
                if len(pair) > 1:
                    lines.append(f"     {_format_individual(pair[1])}")

        return "\n".join(lines)

    def format_json(self) -> str:
        from pathlib import Path as _Path

        data = {
            "file": self.file_path,
            "filename": _Path(self.file_path).name,
            "summary": {
                "total_individuals": self.total_individuals,
                "isolated_count": self.isolated_count,
                "singleton_count": len(self.singletons),
                "pair_count": len(self.pairs),
            },
            "singletons": [_individual_to_dict(s) for s in self.singletons],
            "pairs": [[_individual_to_dict(p) for p in pair] for pair in self.pairs],
        }
        return json.dumps(data, indent=2)


def _header(colors: Colors, title: str) -> str:
    return f"{colors.cyan}=== {title} ==={colors.reset}"


def _format_individual(ind: IsolatedIndividual) -> str:
    parts = [f"{ind.name} ({ind.xref})"]
    if ind.sex:
        parts.append(ind.sex)
    if ind.birth_year is not None:
        parts.append(f"b. {ind.birth_year}")
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {', '.join(parts[1:])}"


def _individual_to_dict(ind: IsolatedIndividual) -> dict[str, str | int | None]:
    return {
        "xref": ind.xref,
        "name": ind.name,
        "sex": ind.sex,
        "birth_year": ind.birth_year,
    }


_extract_xref = extract_xref


def _collect_data(
    file_path: Path,
    *,
    quiet: bool,
    verbose: bool,
    no_color: bool,
) -> IsolatedResult:
    """Collect individuals and families, then find isolated."""
    tracker = PhaseTracker(
        total_phases=2,
        stream=sys.stderr,
        no_color=no_color,
        quiet=quiet,
        verbose=verbose,
    )

    individuals: dict[str, IsolatedIndividual] = {}
    family_members: dict[str, list[str]] = {}

    # Phase 1: Collect data
    with tracker.phase("Collecting data"):
        with GedcomReader(str(file_path)) as reader:
            for rec in reader.records0("INDI"):
                xref = rec.xref_id
                if not xref:
                    continue

                name = ""
                name_rec = rec.sub_tag("NAME")
                if name_rec and name_rec.value:
                    val = name_rec.value
                    if isinstance(val, tuple):
                        # ged4py returns (given, surname, suffix)
                        name = " ".join(p for p in val if p).strip()
                    else:
                        name = str(val).replace("/", "").strip()

                sex = ""
                sex_rec = rec.sub_tag("SEX")
                if sex_rec and sex_rec.value:
                    sex = str(sex_rec.value).strip()

                birth_year = None
                birt_rec = rec.sub_tag("BIRT")
                if birt_rec:
                    date_rec = birt_rec.sub_tag("DATE")
                    if date_rec and date_rec.value:
                        birth_year = extract_year_from_date(date_rec.value)

                individuals[xref] = IsolatedIndividual(
                    xref=xref, name=name, sex=sex, birth_year=birth_year
                )

            for rec in reader.records0("FAM"):
                xref = rec.xref_id
                if not xref:
                    continue

                members: list[str] = []
                for sub in rec.sub_records:
                    if sub.tag in ("HUSB", "WIFE", "CHIL") and sub.value:
                        m = _extract_xref(sub.value)
                        if m:
                            members.append(m)

                family_members[xref] = members

    # Phase 2: Find isolated
    with tracker.phase("Analyzing connections"):
        components = find_connected_components(set(individuals.keys()), family_members)

        singletons: list[IsolatedIndividual] = []
        pairs: list[list[IsolatedIndividual]] = []

        for members in components.values():
            if len(members) == 1:
                singletons.append(individuals[members[0]])
            elif len(members) == 2:
                pairs.append([individuals[members[0]], individuals[members[1]]])

    return IsolatedResult(
        file_path=str(file_path),
        total_individuals=len(individuals),
        singletons=singletons,
        pairs=pairs,
    )


def register_subcommand(
    subparsers: _SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "isolated",
        help="Find isolated individuals with no family connections",
        description=(
            "Detect individuals in connected components of size 1 (singletons)"
            " or size 2 (isolated pairs) using graph analysis."
        ),
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the GEDCOM file to analyze",
    )


def run(args: Namespace) -> int:
    file_path: Path = args.file

    if err := validate_input_file(file_path):
        return err

    output_format = getattr(args, "format", "text")
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    no_color = getattr(args, "no_color", False)

    try:
        result = _collect_data(
            file_path, quiet=quiet, verbose=verbose, no_color=no_color
        )

        if output_format == "json":
            print(result.format_json())
        else:
            colors = Colors(sys.stdout, force_disable=no_color)
            output = result.format_text(colors, quiet=quiet)
            if output:
                print(output)

        return EXIT_SUCCESS

    except BrokenPipeError:
        # cli._run_command turns this into a clean exit; catching it in the
        # generic handler below would report a closed pipe as a failure.
        raise
    except Exception as e:
        if verbose:
            raise
        from gedcom_tools.utils import sanitize_error

        print(f"Error: {sanitize_error(str(e))}", file=sys.stderr)
        return EXIT_ERROR
