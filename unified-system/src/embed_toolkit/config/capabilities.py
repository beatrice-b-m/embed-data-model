"""Profile-level declarations for governed clinical capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Tuple, Union

from embed_toolkit.core.provenance import AvailabilityState, ResolutionState


ProfileDeclarationState = Union[AvailabilityState, ResolutionState]


class GovernedConcept(str, Enum):
    """Source-neutral clinical and imaging concepts governed by a profile."""

    PATIENT = "patient"
    IMAGING_EPISODE = "imaging_episode"
    IMAGING_EXAM = "imaging_exam"
    BREAST_SIDE = "breast_side"
    IMAGING_FINDING = "imaging_finding"
    IMAGING_INTERPRETATION = "imaging_interpretation"
    RADIOLOGY_REPORT = "radiology_report"
    IMAGE = "image"
    REGION_OF_INTEREST = "region_of_interest"
    PROCEDURE = "procedure"
    PATHOLOGY_SPECIMEN = "pathology_specimen"
    PATHOLOGY_OBSERVATION = "pathology_observation"
    PATHOLOGY_DIAGNOSIS = "pathology_diagnosis"
    RISK_ASSESSMENT = "risk_assessment"


def normalize_declaration_state(value: Any) -> ProfileDeclarationState:
    """Normalize one profile classification using the shared state vocabulary."""

    if isinstance(value, AvailabilityState):
        return value
    if isinstance(value, ResolutionState):
        if value is ResolutionState.UNRESOLVED:
            return value
        raise ValueError("Profile declarations cannot use the resolved state")
    try:
        return AvailabilityState(value)
    except (TypeError, ValueError):
        try:
            resolution = ResolutionState(value)
        except (TypeError, ValueError):
            allowed = tuple(
                state.value for state in AvailabilityState
            ) + (ResolutionState.UNRESOLVED.value,)
            raise ValueError(
                f"Profile declaration state must be one of {allowed}, got {value!r}"
            )
        if resolution is ResolutionState.UNRESOLVED:
            return resolution
        raise ValueError("Profile declarations cannot use the resolved state")


@dataclass(frozen=True)
class CapabilityDeclaration:
    """Declare whether and why one governed concept is available in a profile."""

    concept: GovernedConcept
    state: ProfileDeclarationState
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept", GovernedConcept(self.concept))
        object.__setattr__(self, "state", normalize_declaration_state(self.state))
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Capability reason must be a non-empty string")

    def to_dict(self) -> Dict[str, str]:
        """Return a deterministic JSON-ready declaration."""

        return {
            "concept": self.concept.value,
            "state": self.state.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProfileCapabilities:
    """Exhaustive declarations for a supplied governed-concept boundary."""

    source_profile: str
    governed_concepts: Tuple[GovernedConcept, ...]
    declarations: Tuple[CapabilityDeclaration, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_profile, str) or not self.source_profile.strip():
            raise ValueError("source_profile must be a non-empty string")

        governed_concepts = tuple(
            GovernedConcept(concept) for concept in self.governed_concepts
        )
        duplicate_governed = _duplicates(governed_concepts)
        if duplicate_governed:
            duplicate_values = tuple(
                concept.value for concept in duplicate_governed
            )
            raise ValueError(f"Duplicate governed concepts: {duplicate_values}")

        declarations = tuple(self.declarations)
        concepts = tuple(declaration.concept for declaration in declarations)
        duplicates = _duplicates(concepts)
        if duplicates:
            duplicate_values = tuple(concept.value for concept in duplicates)
            raise ValueError(
                f"Duplicate capability declarations: {duplicate_values}"
            )

        governed_set = set(governed_concepts)
        declaration_set = set(concepts)
        missing = tuple(
            concept.value
            for concept in sorted(
                governed_set - declaration_set,
                key=lambda item: item.value,
            )
        )
        unexpected = tuple(
            concept.value
            for concept in sorted(
                declaration_set - governed_set,
                key=lambda item: item.value,
            )
        )
        if missing:
            raise ValueError(f"Missing capability declarations: {missing}")
        if unexpected:
            raise ValueError(f"Unexpected capability declarations: {unexpected}")

        object.__setattr__(
            self,
            "governed_concepts",
            tuple(sorted(governed_concepts, key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "declarations",
            tuple(sorted(declarations, key=lambda item: item.concept.value)),
        )

    def declaration_for(self, concept: GovernedConcept) -> CapabilityDeclaration:
        """Return the declaration for a governed concept or raise clearly."""

        normalized = GovernedConcept(concept)
        for declaration in self.declarations:
            if declaration.concept is normalized:
                return declaration
        raise KeyError(normalized.value)

    def to_dict(self) -> Dict[str, Any]:
        """Return declarations in stable concept order."""

        return {
            "source_profile": self.source_profile,
            "governed_concepts": [
                concept.value for concept in self.governed_concepts
            ],
            "declarations": [
                declaration.to_dict() for declaration in self.declarations
            ],
        }


def _duplicates(values: Iterable[GovernedConcept]) -> Tuple[GovernedConcept, ...]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates, key=lambda item: item.value))
