"""Persistent exam and breast-side aggregate objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from embed_toolkit.clinical.attributes import ExamAttributeObservation
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.procedures import _to_plain
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.imaging.images import MammogramImage


@dataclass
class BreastSide:
    """One persistent unilateral side owned within an exam accession."""

    accession_number: str
    laterality: Laterality
    findings: List[Finding] = field(default_factory=list)
    images: List[MammogramImage] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or not self.accession_number.strip()
        ):
            raise ValueError("BreastSide requires a populated accession_number")
        self.laterality = Laterality.coerce(self.laterality)
        if not self.laterality.is_unilateral:
            raise ValueError("BreastSide requires LEFT or RIGHT laterality")
        initial_findings = list(self.findings)
        initial_images = list(self.images)
        self.findings = []
        self.images = []
        for finding in initial_findings:
            self.add_finding(finding)
        for image in initial_images:
            self.add_image(image)

    @property
    def identity(self) -> Tuple[str, Laterality]:
        return self.accession_number, self.laterality

    def add_finding(self, finding: Finding) -> Finding:
        if finding.accession_number != self.accession_number:
            raise ValueError("Finding accession_number must match BreastSide")
        if self.laterality not in Laterality.coerce(finding.laterality).expand():
            raise ValueError("Finding laterality must match BreastSide laterality")
        for existing in self.findings:
            if existing.identity == finding.identity:
                return existing
        self.findings.append(finding)
        return finding

    def add_image(self, image: MammogramImage) -> MammogramImage:
        if image.accession_number != self.accession_number:
            raise ValueError("Image accession_number must match BreastSide")
        if image.laterality is not self.laterality:
            raise ValueError("Image laterality must match BreastSide laterality")
        for existing in self.images:
            if existing.image_id == image.image_id:
                return existing
        self.images.append(image)
        return image

    def to_dict(self) -> Dict[str, object]:
        """Serialize membership through references, not duplicated objects."""

        return {
            "accession_number": self.accession_number,
            "laterality": self.laterality.value,
            "finding_references": [
                {
                    "accession_number": finding.accession_number,
                    "finding_number": finding.finding_number,
                }
                for finding in self.findings
            ],
            "image_references": [image.image_id for image in self.images],
        }


@dataclass
class Exam:
    """A clinical breast-imaging exam keyed by accession."""

    accession_number: str
    patient_id: Optional[str] = None
    exam_date: Optional[str] = None
    description: Optional[str] = None
    attribute_observations: List[ExamAttributeObservation] = field(
        default_factory=list
    )
    findings: List[Finding] = field(default_factory=list)
    images: List[MammogramImage] = field(default_factory=list)
    breast_sides: Dict[Laterality, BreastSide] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or not self.accession_number.strip()
        ):
            raise ValueError("Exam requires a populated accession_number")
        initial_findings = list(self.findings)
        initial_images = list(self.images)
        initial_sides = tuple(self.breast_sides.values())
        initial_attribute_observations = list(self.attribute_observations)
        self.attribute_observations = []
        self.findings = []
        self.images = []
        self.breast_sides = {}
        for side in initial_sides:
            if side.accession_number != self.accession_number:
                raise ValueError("BreastSide accession_number must match Exam")
            self.ensure_side(side.laterality)
            for finding in side.findings:
                if side.laterality not in Laterality.coerce(
                    finding.laterality
                ).expand():
                    raise ValueError("Finding laterality must match supplied BreastSide")
                initial_findings.append(finding)
            for image in side.images:
                if image.laterality is not side.laterality:
                    raise ValueError("Image laterality must match supplied BreastSide")
                initial_images.append(image)
        self.extend_findings(initial_findings)
        for image in initial_images:
            self.add_image(image)
        for observation in initial_attribute_observations:
            self.add_attribute_observation(observation)

    @property
    def finding_index(self) -> Dict[Tuple[str, str], Finding]:
        return {finding.identity: finding for finding in self.findings}

    def ensure_side(self, laterality: Laterality) -> BreastSide:
        side = Laterality.coerce(laterality)
        if not side.is_unilateral:
            raise ValueError("Exam breast sides require LEFT or RIGHT laterality")
        existing = self.breast_sides.get(side)
        if existing is not None:
            return existing
        created = BreastSide(self.accession_number, side)
        self.breast_sides[side] = created
        return created

    def add_attribute_observation(
        self,
        observation: ExamAttributeObservation,
    ) -> ExamAttributeObservation:
        """Own one uniquely source-attributed invariant observation."""

        if not isinstance(observation, ExamAttributeObservation):
            raise TypeError("observation must be an ExamAttributeObservation")
        if observation.accession_number != self.accession_number:
            raise ValueError(
                "ExamAttributeObservation accession_number must match Exam"
            )
        for existing in self.attribute_observations:
            if existing.identity == observation.identity:
                if existing != observation:
                    raise ValueError(
                        "One exam attribute observation identity cannot "
                        "represent different values"
                    )
                return existing
        self.attribute_observations.append(observation)
        return observation

    def add_finding(self, finding: Finding) -> Finding:
        if finding.accession_number != self.accession_number:
            raise ValueError("Finding accession_number must match Exam accession_number")
        existing = self.finding_index.get(finding.identity)
        if existing is not None:
            existing.merge_observation(finding)
            owned = existing
        else:
            self.findings.append(finding)
            owned = finding
        for laterality in Laterality.coerce(owned.laterality).expand():
            self.ensure_side(laterality).add_finding(owned)
        return owned

    def extend_findings(self, findings: Iterable[Finding]) -> None:
        for finding in findings:
            self.add_finding(finding)

    def add_image(self, image: MammogramImage) -> MammogramImage:
        if image.accession_number != self.accession_number:
            raise ValueError("Image accession_number must match Exam accession_number")
        for existing in self.images:
            if existing.image_id == image.image_id:
                return existing
        self.images.append(image)
        if image.laterality.is_unilateral:
            self.ensure_side(image.laterality).add_image(image)
        return image

    def to_dict(self) -> Dict[str, object]:
        """Serialize owned objects once and side memberships by reference."""

        return {
            "accession_number": self.accession_number,
            "patient_id": self.patient_id,
            "exam_date": self.exam_date,
            "description": self.description,
            "attribute_observations": [
                observation.to_dict()
                for observation in self.attribute_observations
            ],
            "findings": [finding.to_dict() for finding in self.findings],
            "images": [image.to_dict() for image in self.images],
            "breast_sides": [
                self.breast_sides[side].to_dict()
                for side in (Laterality.LEFT, Laterality.RIGHT)
                if side in self.breast_sides
            ],
            "metadata": _to_plain(self.metadata),
        }
