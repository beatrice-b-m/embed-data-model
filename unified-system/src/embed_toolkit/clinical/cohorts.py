"""Cohort-level clinical aggregate objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.procedures import _to_plain


@dataclass
class Cohort:
    """A named collection of patients for analysis or export."""

    cohort_id: str
    patients: List[Patient] = field(default_factory=list)
    description: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def exams(self) -> Tuple[Exam, ...]:
        return tuple(exam for patient in self.patients for exam in patient.exams)

    @property
    def findings(self) -> Tuple[Finding, ...]:
        return tuple(finding for exam in self.exams for finding in exam.findings)

    def add_patient(self, patient: Patient) -> Patient:
        for existing in self.patients:
            if existing.patient_id == patient.patient_id:
                return existing
        self.patients.append(patient)
        return patient

    def to_dict(self) -> Dict[str, object]:
        return _to_plain(self)
