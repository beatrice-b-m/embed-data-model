"""Explicit clinical association records with source provenance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple, Union

from embed_data_model.clinical.procedures import ProcedureIdentity
from embed_data_model.core.provenance import SourceLocator
from embed_data_model.core.source import SourceRef


SourceValue = Union[SourceLocator, SourceRef]


class AttributionStatus(str, Enum):
    """Strength and origin of a source-to-domain association.

    Members
    -------
    SOURCE_ASSERTED='source_asserted', SOURCE_COLOCATED='source_colocated',
    INFERRED='inferred', CANDIDATE='candidate', UNRESOLVED='unresolved'.
    """

    SOURCE_ASSERTED = "source_asserted"
    SOURCE_COLOCATED = "source_colocated"
    INFERRED = "inferred"
    CANDIDATE = "candidate"
    UNRESOLVED = "unresolved"

    @property
    def is_resolved_attribution(self) -> bool:
        """True for SOURCE_ASSERTED, SOURCE_COLOCATED or INFERRED; False for
        unresolved/ambiguous statuses.
        """

        return self in {
            self.SOURCE_ASSERTED,
            self.SOURCE_COLOCATED,
            self.INFERRED,
        }


class ClinicalObjectKind(str, Enum):
    """Clinical grains that may receive pathology attribution.

    Members
    -------
    PATIENT='patient', EXAM='exam', BREAST_SIDE='breast_side',
    FINDING='finding', PROCEDURE='procedure'.
    """

    PATIENT = "patient"
    EXAM = "exam"
    BREAST_SIDE = "breast_side"
    FINDING = "finding"
    PROCEDURE = "procedure"


@dataclass(frozen=True)
class ClinicalObjectReference:
    """Non-recursive reference to one governed clinical object.

    Attributes
    ----------
    kind : ClinicalObjectKind
        Governed kind of referenced object; identity shape depends on the kind.
    identity : Tuple[str, ...]
        Semantic identity used for graph membership; use rekey for a registered
        entity.
    """

    kind: ClinicalObjectKind
    """Governed kind of referenced object; identity shape depends on the kind."""
    identity: Tuple[str, ...]
    """Semantic identity used for graph membership; use rekey for a registered entity."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ClinicalObjectKind(self.kind))
        identity = tuple(self.identity)
        if not identity or any(
            not isinstance(value, str) or not value.strip() for value in identity
        ):
            raise ValueError("Clinical object identity components must be populated")
        object.__setattr__(self, "identity", identity)

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {"kind": self.kind.value, "identity": list(self.identity)}


@dataclass(frozen=True)
class FindingProcedureLink:
    """Attributed edge from a represented finding to a resolved procedure.

    Attributes
    ----------
    accession_number : str
        Non-empty exam accession identifying the clinical examination.
    finding_number : str
        Non-empty finding identifier scoped to its accession; not a row ordinal.
    procedure : ProcedureIdentity
        Complete resolved ProcedureIdentity for the attribution target.
    status : AttributionStatus
        Attribution strength/origin; unresolved statuses cannot establish
        resolved links.
    source : SourceValue
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events.
    """

    accession_number: str
    """Non-empty exam accession identifying the clinical examination."""
    finding_number: str
    """Non-empty finding identifier scoped to its accession; not a row ordinal."""
    procedure: ProcedureIdentity
    """Complete resolved ProcedureIdentity for the attribution target."""
    status: AttributionStatus
    """Attribution strength/origin; unresolved statuses cannot establish resolved links."""
    source: SourceValue
    """Optional provenance. SourceRef and SourceLocator identify evidence, not clinical events."""

    def __post_init__(self) -> None:
        for attribute in ("accession_number", "finding_number"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        status = AttributionStatus(self.status)
        if not status.is_resolved_attribution:
            raise ValueError("A resolved procedure link requires attribution status")
        object.__setattr__(self, "status", status)

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "finding": {
                "accession_number": self.accession_number,
                "finding_number": self.finding_number,
            },
            "procedure": self.procedure.to_dict(),
            "status": self.status.value,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class AssociationLink:
    """Source-attributed edge between two canonical graph records.

    Attributes
    ----------
    source_kind : str
        Registry kind of the source endpoint.
    source_identity : Tuple[str, ...]
        Tuple of source identity components in their semantic order.
    target_kind : str
        Registry kind of the target endpoint.
    target_identity : Tuple[str, ...]
        Tuple of target identity components in their semantic order.
    status : AttributionStatus
        Attribution strength/origin; unresolved statuses cannot establish
        resolved links.
    source : SourceValue
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events.
    """

    source_kind: str
    """Registry kind of the source endpoint."""
    source_identity: Tuple[str, ...]
    """Tuple of source identity components in their semantic order."""
    target_kind: str
    """Registry kind of the target endpoint."""
    target_identity: Tuple[str, ...]
    """Tuple of target identity components in their semantic order."""
    status: AttributionStatus
    """Attribution strength/origin; unresolved statuses cannot establish resolved links."""
    source: SourceValue
    """Optional provenance. SourceRef and SourceLocator identify evidence, not clinical events."""

    def __post_init__(self) -> None:
        for attribute in ("source_kind", "target_kind"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        for attribute in ("source_identity", "target_identity"):
            values = tuple(getattr(self, attribute))
            if not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{attribute} components must be populated")
            object.__setattr__(self, attribute, values)
        object.__setattr__(self, "status", AttributionStatus(self.status))
        if not isinstance(self.source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "source_kind": self.source_kind,
            "source_identity": list(self.source_identity),
            "target_kind": self.target_kind,
            "target_identity": list(self.target_identity),
            "status": self.status.value,
            "source": self.source.to_dict(),
        }
