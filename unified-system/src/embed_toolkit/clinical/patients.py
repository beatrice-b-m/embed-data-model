"""Patient-level clinical aggregate objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.procedures import _to_plain


@dataclass
class Patient:
    """A patient with clinical exams."""

    patient_id: str
    exams: List[Exam] = field(default_factory=list)
    sex: Optional[str] = None
    birth_year: Optional[int] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def findings(self) -> Tuple[Finding, ...]:
        return tuple(finding for exam in self.exams for finding in exam.findings)

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

    def to_dict(self) -> Dict[str, object]:
        return {
            "patient_id": self.patient_id,
            "sex": self.sex,
            "birth_year": self.birth_year,
            "exams": [exam.to_dict() for exam in self.exams],
            "metadata": _to_plain(self.metadata),
        }
