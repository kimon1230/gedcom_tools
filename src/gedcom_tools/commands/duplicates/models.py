from __future__ import annotations

from dataclasses import dataclass, field

from gedcom_tools.commands.compare.models import MatchPair
from gedcom_tools.utils import EncodingInfo


@dataclass
class DuplicatesResult:
    """Result of scanning a single GEDCOM file for duplicate individuals."""

    file: str
    encoding: EncodingInfo
    total_individuals: int
    certain_matches: list[MatchPair] = field(default_factory=list)
    probable_matches: list[MatchPair] = field(default_factory=list)
