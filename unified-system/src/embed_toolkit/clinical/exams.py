"""Exam and breast-side aggregate clinical objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.procedures import _to_plain
from embed_toolkit.core.primitives import Laterality


@dataclass
class BreastSide:
    """Clinical findings for one breast side within an exam."""

    laterality: Laterality
    findings: List[Finding] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        if not self.laterality.is_unilateral:
            raise ValueError("BreastSide requires LEFT or RIGHT laterality")

    def add_finding(self, finding: Finding) -> Finding:
        if self.laterality not in Laterality.coerce(finding.laterality).expand():
            raise ValueError("Finding laterality must match BreastSide laterality")
        self.findings.append(finding)
        return finding


@dataclass
class Exam:
    """A clinical breast imaging exam keyed by accession."""

    accession_number: str
    patient_id: Optional[str] = None
    exam_date: Optional[str] = None
    description: Optional[str] = None
    findings: List[Finding] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def finding_index(self) -> Dict[Tuple[str, str], Finding]:
        return {finding.identity: finding for finding in self.findings}

    @property
    def breast_sides(self) -> Dict[Laterality, BreastSide]:
        sides = {
            Laterality.LEFT: BreastSide(Laterality.LEFT),
            Laterality.RIGHT: BreastSide(Laterality.RIGHT),
        }
        for finding in self.findings:
            for side in Laterality.coerce(finding.laterality).expand():
                sides[side].findings.append(finding)
        return {side: breast_side for side, breast_side in sides.items() if breast_side.findings}

    def add_finding(self, finding: Finding) -> Finding:
        if finding.accession_number != self.accession_number:
            raise ValueError("Finding accession_number must match Exam accession_number")
        existing = self.finding_index.get(finding.identity)
        if existing is not None:
            existing.merge_observation(finding)
            return existing
        self.findings.append(finding)
        return finding

    def extend_findings(self, findings: Iterable[Finding]) -> None:
        for finding in findings:
            self.add_finding(finding)

    def to_dict(self) -> Dict[str, object]:
        return _to_plain(self)
