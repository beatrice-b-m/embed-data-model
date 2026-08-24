"""Explicit clinical association records with source provenance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple

from embed_toolkit.clinical.procedures import ProcedureIdentity
from embed_toolkit.core.provenance import SourceLocator


class AttributionStatus(str, Enum):
    """Strength and origin of a source-to-domain association."""

    SOURCE_ASSERTED = "source_asserted"
    SOURCE_COLOCATED = "source_colocated"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


class ClinicalObjectKind(str, Enum):
    """Clinical grains that may receive pathology attribution."""

    PATIENT = "patient"
    EXAM = "exam"
    BREAST_SIDE = "breast_side"
    FINDING = "finding"
    PROCEDURE = "procedure"


@dataclass(frozen=True)
class ClinicalObjectReference:
    """Non-recursive reference to one governed clinical object."""

    kind: ClinicalObjectKind
    identity: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ClinicalObjectKind(self.kind))
        identity = tuple(self.identity)
        if not identity or any(
            not isinstance(value, str) or not value.strip() for value in identity
        ):
            raise ValueError("Clinical object identity components must be populated")
        object.__setattr__(self, "identity", identity)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind.value, "identity": list(self.identity)}


@dataclass(frozen=True)
class FindingProcedureLink:
    """Attributed edge from a represented finding to a resolved procedure."""

    accession_number: str
    finding_number: str
    procedure: ProcedureIdentity
    status: AttributionStatus
    source: SourceLocator

    def __post_init__(self) -> None:
        for attribute in ("accession_number", "finding_number"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        status = AttributionStatus(self.status)
        if status is AttributionStatus.UNRESOLVED:
            raise ValueError("A resolved procedure link cannot be unresolved")
        object.__setattr__(self, "status", status)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding": {
                "accession_number": self.accession_number,
                "finding_number": self.finding_number,
            },
            "procedure": self.procedure.to_dict(),
            "status": self.status.value,
            "source": self.source.to_dict(),
        }
