from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RelIndividual:
    """Individual record for relationship queries."""

    xref: str
    name: str
    sex: str  # "M", "F", or ""
    birth_year: int | None = None
    death_year: int | None = None


@dataclass
class RelationshipPath:
    """Single relationship path via a common ancestor."""

    type: str  # base type (no half-prefix)
    gen_p: int  # generations from primary to common ancestor
    gen_t: int  # generations from target to common ancestor
    common_ancestors: list[str] = field(default_factory=list)
    is_half: bool = False
    description: str = ""


@dataclass
class RelationshipResult:
    """Full result of a relationship query."""

    file: str
    primary: RelIndividual
    target: RelIndividual
    related: bool
    relationships: list[RelationshipPath] = field(default_factory=list)
    total_paths: int = 0
