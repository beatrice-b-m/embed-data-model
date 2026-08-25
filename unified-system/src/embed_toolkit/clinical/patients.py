"""Patient-level clinical aggregate objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from embed_toolkit.clinical.attributes import PatientAttributeObservation
from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.histories import (
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_toolkit.clinical.procedures import _to_plain


@dataclass
class Patient:
    """A patient with clinical exams."""

    patient_id: str
    exams: List[Exam] = field(default_factory=list)
    attribute_observations: List[PatientAttributeObservation] = field(
        default_factory=list
    )
    metadata: Dict[str, object] = field(default_factory=dict)
    history_observations: List[PatientHistoryObservation] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        if not isinstance(self.patient_id, str) or not self.patient_id.strip():
            raise ValueError("patient_id must be a non-empty string")
        initial_exams = list(self.exams)
        initial_observations = list(self.attribute_observations)
        initial_history = list(self.history_observations)
        self.exams = []
        self.attribute_observations = []
        self.history_observations = []
        for exam in initial_exams:
            self.add_exam(exam)
        for observation in initial_observations:
            self.add_attribute_observation(observation)
        for observation in initial_history:
            self.add_history_observation(observation)

    @property
    def findings(self) -> Tuple[Finding, ...]:
        return tuple(finding for exam in self.exams for finding in exam.findings)

    @property
    def medication_history(self) -> Tuple[MedicationHistoryObservation, ...]:
        return tuple(
            item
            for item in self.history_observations
            if isinstance(item, MedicationHistoryObservation)
        )

    @property
    def procedure_history(self) -> Tuple[ProcedureHistoryObservation, ...]:
        return tuple(
            item
            for item in self.history_observations
            if isinstance(item, ProcedureHistoryObservation)
        )

    def add_exam(self, exam: Exam) -> Exam:
        if exam.patient_id is None:
            exam.patient_id = self.patient_id
        if exam.patient_id != self.patient_id:
            raise ValueError("Exam patient_id must match Patient patient_id")
        for existing in self.exams:
            if existing.accession_number == exam.accession_number:
                return existing
        self.exams.append(exam)
        return exam

    def add_attribute_observation(
        self,
        observation: PatientAttributeObservation,
    ) -> PatientAttributeObservation:
        """Own one uniquely source-attributed observation for this patient."""

        if not isinstance(observation, PatientAttributeObservation):
            raise TypeError(
                "observation must be a PatientAttributeObservation"
            )
        if observation.patient_id != self.patient_id:
            raise ValueError(
                "PatientAttributeObservation patient_id must match Patient"
            )
        for existing in self.attribute_observations:
            if existing.identity == observation.identity:
                if existing != observation:
                    raise ValueError(
                        "One patient attribute observation identity cannot "
                        "represent different values"
                    )
                return existing
        self.attribute_observations.append(observation)
        return observation

    def add_history_observation(
        self,
        observation: PatientHistoryObservation,
    ) -> PatientHistoryObservation:
        """Own one uniquely source-attributed reported history item."""

        if not isinstance(observation, PatientHistoryObservation):
            raise TypeError("observation must be a PatientHistoryObservation")
        if observation.patient_id != self.patient_id:
            raise ValueError("Patient history patient_id must match Patient")
        for existing in self.history_observations:
            if existing.identity == observation.identity:
                if existing != observation:
                    raise ValueError(
                        "One patient history source identity cannot represent "
                        "different observations"
                    )
                return existing
        self.history_observations.append(observation)
        return observation

    def to_dict(self) -> Dict[str, object]:
        return {
            "patient_id": self.patient_id,
            "exams": [exam.to_dict() for exam in self.exams],
            "attribute_observations": [
                observation.to_dict()
                for observation in self.attribute_observations
            ],
            "history_observations": [
                observation.to_dict()
                for observation in self.history_observations
            ],
            "metadata": _to_plain(self.metadata),
        }
