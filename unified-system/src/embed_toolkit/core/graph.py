"""Canonical graph registry and staged ingestion transactions."""

from __future__ import annotations

from collections import defaultdict
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from typing import Any, DefaultDict, Dict, Mapping, Optional, Tuple
from uuid import uuid4

from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.interpretations import ImagingInterpretation
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.source import (
    Issue,
    IssueSeverity,
    SourceRef,
    UnresolvedReference,
)
from embed_toolkit.imaging.images import MammogramImage


class LoadError(ValueError):
    """Raised when strict loading encounters an error-severity issue."""

    def __init__(self, issue: Issue) -> None:
        self.issue = issue
        super().__init__(f"{issue.code}: {issue.message}")


@dataclass(frozen=True)
class _Contribution:
    source: SourceRef
    concept: str
    slot: str
    entity_id: str
    payload: Tuple[Any, ...]
    metadata: Mapping[str, Any]

    @property
    def address(self) -> Tuple[SourceRef, str, str]:
        return self.source, self.concept, self.slot


class DatasetGraph:
    """One identity registry shared by every source-table load."""

    def __init__(
        self,
        identity_namespace: Optional[str] = None,
        source_scope: Optional[str] = None,
    ) -> None:
        self._identity_namespace = _nonempty_or_default(
            identity_namespace, "default", "identity_namespace"
        )
        self._source_scope = _nonempty_or_default(
            source_scope, f"in-memory:{uuid4()}", "source_scope"
        )
        self._patients: Dict[str, Patient] = {}
        self._exams: Dict[str, Exam] = {}
        self._findings: Dict[Tuple[str, str], Finding] = {}
        self._images: Dict[str, MammogramImage] = {}
        self._contributions: Dict[Tuple[SourceRef, str, str], _Contribution] = {}
        self._issues: list[Issue] = []
        self._issue_fingerprints: set[Tuple[Any, ...]] = set()
        self._exam_observations: DefaultDict[
            str, DefaultDict[str, Dict[SourceRef, Any]]
        ] = defaultdict(lambda: defaultdict(dict))
        self._finding_observations: DefaultDict[
            Tuple[str, str], DefaultDict[str, Dict[SourceRef, Any]]
        ] = defaultdict(lambda: defaultdict(dict))
        self._image_observations: DefaultDict[
            str, DefaultDict[str, Dict[SourceRef, Any]]
        ] = defaultdict(lambda: defaultdict(dict))
        self._unresolved_references: Tuple[UnresolvedReference, ...] = ()

    @property
    def identity_namespace(self) -> str:
        return self._identity_namespace

    @property
    def source_scope(self) -> str:
        return self._source_scope

    @property
    def patients(self) -> Tuple[Patient, ...]:
        """Return a deterministic, read-only view of canonical patients."""

        return tuple(self._patients[key] for key in sorted(self._patients))

    @property
    def exams(self) -> Tuple[Exam, ...]:
        """Return a deterministic, read-only view of canonical exams."""

        return tuple(self._exams[key] for key in sorted(self._exams))

    @property
    def issues(self) -> Tuple[Issue, ...]:
        """Return cumulative issues, deduplicated across invocation replay."""

        return tuple(self._issues)

    @property
    def findings(self) -> Tuple[Finding, ...]:
        """Return findings ordered by accession and finding number."""

        return tuple(self._findings[key] for key in sorted(self._findings))

    @property
    def images(self) -> Tuple[MammogramImage, ...]:
        """Return images ordered by their governed image key."""

        return tuple(self._images[key] for key in sorted(self._images))

    @property
    def unresolved_references(self) -> Tuple[UnresolvedReference, ...]:
        return self._unresolved_references

    def patient(self, patient_id: str) -> Optional[Patient]:
        return self._patients.get(patient_id)

    def exam(self, accession: str) -> Optional[Exam]:
        return self._exams.get(accession)

    def finding(self, accession: str, finding_number: str) -> Optional[Finding]:
        return self._findings.get((accession, str(finding_number)))

    def image(self, image_id: str) -> Optional[MammogramImage]:
        return self._images.get(image_id)

    def transaction(self, mode: str = "audit") -> "GraphTransaction":
        """Open the only supported mutation surface for this graph."""

        return GraphTransaction(self, mode=mode)

    def _record_issue(self, issue: Issue) -> None:
        if issue.fingerprint not in self._issue_fingerprints:
            self._issues.append(issue)
            self._issue_fingerprints.add(issue.fingerprint)

    def _resolve_exam(self, accession: str) -> None:
        exam = self._exams[accession]
        observations = self._exam_observations[accession]
        exam.patient_id = _one_value_or_none(observations["patient_id"].values())
        exam.exam_date = _one_value_or_none(observations["exam_date"].values())
        exam.description = _one_value_or_none(observations["description"].values())

        for patient in self._patients.values():
            patient.exams[:] = [
                owned for owned in patient.exams if owned.accession_number != accession
            ]
        if exam.patient_id is not None:
            patient = self._patients.get(exam.patient_id)
            if patient is not None:
                patient.add_exam(exam)

    def _resolve_finding(self, identity: Tuple[str, str]) -> None:
        finding = self._findings[identity]
        observations = self._finding_observations[identity]
        laterality = _one_value_or_none(
            value
            for value in observations["laterality"].values()
            if value is not Laterality.UNKNOWN
        )
        finding.laterality = laterality or Laterality.UNKNOWN
        finding.finding_type = _one_value_or_none(
            observations["finding_type"].values()
        )
        assessment = _one_value_or_none(observations["assessment"].values())
        recommendation = _one_value_or_none(
            observations["recommendation"].values()
        )
        evidence = tuple(
            sorted(
                set(observations["laterality"]) | set(observations["assessment"])
                | set(observations["recommendation"]),
                key=lambda source: repr(source.to_dict()),
            )
        )
        finding.interpretation = (
            ImagingInterpretation(
                accession_number=identity[0],
                finding_number=identity[1],
                sources=evidence,
                assessment=assessment,
                recommendation=recommendation,
            )
            if evidence and (assessment is not None or recommendation is not None)
            else None
        )

        exam = self._exams[identity[0]]
        exam.findings[:] = [item for item in exam.findings if item.identity != identity]
        for side in exam.breast_sides.values():
            side.findings[:] = [item for item in side.findings if item.identity != identity]
        exam.findings.append(finding)
        for side_value in finding.laterality.expand():
            exam.ensure_side(side_value).add_finding(finding)
        exam.breast_sides = {
            side: owned
            for side, owned in exam.breast_sides.items()
            if owned.findings or owned.images
        }

    def _resolve_images(self) -> None:
        unresolved: set[UnresolvedReference] = set()
        for exam in self._exams.values():
            exam.images.clear()
            for side in exam.breast_sides.values():
                side.images.clear()

        for image_id in sorted(self._images):
            image = self._images[image_id]
            observations = self._image_observations[image_id]
            image.sources = sorted(
                set().union(*(set(values) for values in observations.values())),
                key=lambda source: repr(source.to_dict()),
            )
            image.patient_id = _one_value_or_none(observations["patient_id"].values())
            image.accession_number = _one_value_or_none(
                observations["accession"].values()
            )
            image.laterality = _one_enum_or_unknown(
                observations["laterality"].values(), Laterality.UNKNOWN
            )
            image.view_position = _one_enum_or_unknown(
                observations["view_position"].values(), ViewPosition.UNKNOWN
            )
            image.modality = _one_enum_or_unknown(
                observations["modality"].values(), ImageModality.UNKNOWN
            )
            for field in (
                "source_modality",
                "derived_image_type",
                "height",
                "width",
                "frame_count",
                "study_instance_uid",
                "series_instance_uid",
                "sop_instance_uid",
                "coordinate_frame_id",
            ):
                setattr(image, field, _one_value_or_none(observations[field].values()))

            if image.patient_id is not None and image.patient_id not in self._patients:
                unresolved.add(
                    UnresolvedReference(
                        "image", image_id, "patient", image.patient_id, "missing_target"
                    )
                )
            if image.accession_number is None:
                continue
            exam = self._exams.get(image.accession_number)
            if exam is None:
                unresolved.add(
                    UnresolvedReference(
                        "image",
                        image_id,
                        "exam",
                        image.accession_number,
                        "missing_target",
                    )
                )
                continue
            if (
                image.patient_id is not None
                and exam.patient_id is not None
                and image.patient_id != exam.patient_id
            ):
                unresolved.add(
                    UnresolvedReference(
                        "image",
                        image_id,
                        "exam",
                        image.accession_number,
                        "conflicting_patient",
                    )
                )
                continue
            exam.add_image(image)

        for exam in self._exams.values():
            exam.images.sort(key=lambda image: image.image_id)
            exam.breast_sides = {
                side: owned
                for side, owned in exam.breast_sides.items()
                if owned.findings or owned.images
            }
        self._unresolved_references = tuple(
            sorted(
                unresolved,
                key=lambda item: (
                    item.source_kind,
                    item.source_id,
                    item.target_kind,
                    item.target_id,
                    item.reason,
                ),
            )
        )


class GraphTransaction(AbstractContextManager["GraphTransaction"]):
    """Invocation-scoped staging area with strict rollback semantics."""

    def __init__(self, graph: DatasetGraph, *, mode: str = "audit") -> None:
        if mode not in {"audit", "strict"}:
            raise ValueError("mode must be 'audit' or 'strict'")
        self.graph = graph
        self.mode = mode
        self.issues: list[Issue] = []
        self._issue_fingerprints: set[Tuple[Any, ...]] = set()
        self._pending: Dict[Tuple[SourceRef, str, str], _Contribution] = {}
        self._patient_nodes: Dict[str, Patient] = {}
        self._exam_nodes: Dict[str, Exam] = {}
        self._finding_nodes: Dict[Tuple[str, str], Finding] = {}
        self._image_nodes: Dict[str, MammogramImage] = {}
        self._closed = False

    def __enter__(self) -> "GraphTransaction":
        if self._closed:
            raise RuntimeError("a graph transaction cannot be reused")
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        self._closed = True
        if exc_type is not None:
            return False
        first_error = next(
            (issue for issue in self.issues if issue.severity is IssueSeverity.ERROR),
            None,
        )
        if self.mode == "strict" and first_error is not None:
            raise LoadError(first_error)
        self._commit()
        return False

    def add_issue(self, issue: Issue) -> Issue:
        if not isinstance(issue, Issue):
            raise TypeError("issue must be an Issue")
        if issue.fingerprint not in self._issue_fingerprints:
            self.issues.append(issue)
            self._issue_fingerprints.add(issue.fingerprint)
        return issue

    def upsert_patient(
        self,
        patient_id: str,
        source: SourceRef,
        *,
        values: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Patient:
        _require_open(self)
        _require_identifier(patient_id, "patient_id")
        contribution = _Contribution(
            source=source,
            concept="patient",
            slot="",
            entity_id=patient_id,
            payload=_freeze(values or {"patient_id": patient_id}),
            metadata=dict(metadata or {}),
        )
        if not self._stage(contribution):
            return self.graph.patient(patient_id) or Patient(patient_id)
        patient = self.graph.patient(patient_id)
        if patient is None:
            patient = self._patient_nodes.setdefault(patient_id, Patient(patient_id))
        return patient

    def upsert_exam(
        self,
        accession: str,
        source: SourceRef,
        *,
        patient_id: Optional[str] = None,
        exam_date: Optional[str] = None,
        description: Optional[str] = None,
        values: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Exam:
        _require_open(self)
        _require_identifier(accession, "accession")
        if patient_id is not None:
            _require_identifier(patient_id, "patient_id")
        normalized = values or {
            "accession": accession,
            "patient_id": patient_id,
            "exam_date": exam_date,
            "exam_description": description,
        }
        contribution = _Contribution(
            source=source,
            concept="exam",
            slot="",
            entity_id=accession,
            payload=_freeze(normalized),
            metadata=dict(metadata or {}),
        )
        if not self._stage(contribution):
            return self.graph.exam(accession) or Exam(accession)

        observed_patient_ids = self._observed_exam_values(accession, "patient_id")
        if patient_id is not None and observed_patient_ids - {patient_id}:
            self.add_issue(
                Issue(
                    code="conflicting_exam_patient",
                    message="one accession has conflicting patient identities",
                    source=source,
                    context={
                        "accession": accession,
                        "observed_patient_ids": sorted(
                            observed_patient_ids | {patient_id}
                        ),
                    },
                )
            )
        for field, value in (
            ("exam_date", exam_date),
            ("description", description),
        ):
            observed_values = self._observed_exam_values(accession, field)
            if value is not None and observed_values - {value}:
                self.add_issue(
                    Issue(
                        code="conflicting_exam_field",
                        message=(
                            "one accession has conflicting populated values "
                            f"for {field}"
                        ),
                        source=source,
                        context={
                            "accession": accession,
                            "field": field,
                            "observed_values": sorted(
                                str(item) for item in observed_values
                            ),
                        },
                    )
                )

        exam = self.graph.exam(accession)
        if exam is None:
            exam = self._exam_nodes.setdefault(accession, Exam(accession))
        return exam

    def upsert_finding(
        self,
        accession: str,
        finding_number: str,
        source: SourceRef,
        *,
        laterality: Laterality = Laterality.UNKNOWN,
        finding_type: Optional[str] = None,
        assessment: Optional[str] = None,
        recommendation: Optional[str] = None,
        values: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Finding:
        """Stage one finding observation and its accession-owned identity."""

        _require_open(self)
        _require_identifier(accession, "accession")
        _require_identifier(finding_number, "finding_number")
        side = Laterality.coerce(laterality)
        identity = (accession, finding_number)
        normalized = values or {
            "accession": accession,
            "finding_number": finding_number,
            "laterality": side.value,
            "finding_type": finding_type,
            "assessment": assessment,
            "recommendation": recommendation,
        }
        contribution = _Contribution(
            source=source,
            concept="finding",
            slot="",
            entity_id="\x1f".join(identity),
            payload=_freeze(normalized),
            metadata=dict(metadata or {}),
        )
        if not self._stage(contribution):
            return self.graph.finding(*identity) or Finding(accession, side, finding_number)

        for field, value in (
            ("laterality", side if side is not Laterality.UNKNOWN else None),
            ("finding_type", finding_type),
            ("assessment", assessment),
            ("recommendation", recommendation),
        ):
            observed = self._observed_finding_values(identity, field)
            if value is not None and observed - {value}:
                self.add_issue(
                    Issue(
                        code="conflicting_finding_field",
                        message=f"one finding has conflicting populated values for {field}",
                        source=source,
                        context={
                            "accession": accession,
                            "finding_number": finding_number,
                            "field": field,
                            "observed_values": sorted(str(item) for item in observed | {value}),
                        },
                    )
                )

        self._exam_nodes.setdefault(accession, self.graph.exam(accession) or Exam(accession))
        finding = self.graph.finding(*identity)
        if finding is None:
            finding = self._finding_nodes.setdefault(
                identity, Finding(accession, side, finding_number)
            )
        return finding

    def _observed_finding_values(
        self, identity: Tuple[str, str], field: str
    ) -> set[Any]:
        values = {
            value
            for value in self.graph._finding_observations[identity][field].values()
            if value is not None and value is not Laterality.UNKNOWN
        }
        for contribution in self._pending.values():
            if contribution.concept != "finding":
                continue
            if tuple(contribution.entity_id.split("\x1f", 1)) != identity:
                continue
            payload = dict(_thaw_mapping(contribution.payload))
            value = payload.get(field)
            if field == "laterality" and value is not None:
                value = Laterality.coerce(value)
            if value is not None and value is not Laterality.UNKNOWN:
                values.add(value)
        return values

    def upsert_image(
        self,
        image_id: str,
        source: SourceRef,
        *,
        patient_id: Optional[str] = None,
        accession: Optional[str] = None,
        laterality: Laterality = Laterality.UNKNOWN,
        view_position: ViewPosition = ViewPosition.UNKNOWN,
        modality: ImageModality = ImageModality.UNKNOWN,
        source_modality: Optional[str] = None,
        derived_image_type: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        frame_count: Optional[int] = None,
        study_instance_uid: Optional[str] = None,
        series_instance_uid: Optional[str] = None,
        sop_instance_uid: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
        values: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> MammogramImage:
        """Stage one image without manufacturing referenced clinical nodes."""

        _require_open(self)
        _require_identifier(image_id, "image_id")
        side = Laterality.coerce(laterality)
        view = ViewPosition.coerce(view_position)
        image_modality = ImageModality.coerce(modality)
        normalized = values or {
            "image_id": image_id,
            "patient_id": patient_id,
            "accession": accession,
            "laterality": side.value,
            "view_position": view.value,
            "modality": image_modality.value,
            "source_modality": source_modality,
            "derived_image_type": derived_image_type,
            "height": height,
            "width": width,
            "frame_count": frame_count,
            "study_instance_uid": study_instance_uid,
            "series_instance_uid": series_instance_uid,
            "sop_instance_uid": sop_instance_uid,
            "coordinate_frame_id": coordinate_frame_id,
        }
        contribution = _Contribution(
            source=source,
            concept="image",
            slot="",
            entity_id=image_id,
            payload=_freeze(normalized),
            metadata=dict(metadata or {}),
        )
        if not self._stage(contribution):
            return self.graph.image(image_id) or MammogramImage(
                image_id, side, view, sources=[source]
            )
        for field, value in normalized.items():
            if field == "image_id" or value is None or value == "UNKNOWN":
                continue
            observed = self._observed_image_values(image_id, field)
            comparison = (
                Laterality.coerce(value)
                if field == "laterality"
                else ViewPosition.coerce(value)
                if field == "view_position"
                else ImageModality.coerce(value)
                if field == "modality"
                else value
            )
            if observed - {comparison}:
                self.add_issue(
                    Issue(
                        code="conflicting_image_field",
                        message=f"one image has conflicting populated values for {field}",
                        source=source,
                        context={
                            "image_id": image_id,
                            "field": field,
                            "observed_values": sorted(
                                str(item) for item in observed | {comparison}
                            ),
                        },
                    )
                )
        image = self.graph.image(image_id)
        if image is None:
            image = self._image_nodes.setdefault(
                image_id, MammogramImage(image_id, side, view, sources=[source])
            )
        return image

    def _observed_image_values(self, image_id: str, field: str) -> set[Any]:
        values = {
            value
            for value in self.graph._image_observations[image_id][field].values()
            if value is not None and getattr(value, "value", value) != "UNKNOWN"
        }
        for contribution in self._pending.values():
            if contribution.concept != "image" or contribution.entity_id != image_id:
                continue
            value = dict(_thaw_mapping(contribution.payload)).get(field)
            if field == "laterality":
                value = Laterality.coerce(value)
            elif field == "view_position":
                value = ViewPosition.coerce(value)
            elif field == "modality":
                value = ImageModality.coerce(value)
            if value is not None and getattr(value, "value", value) != "UNKNOWN":
                values.add(value)
        return values

    def _observed_exam_values(self, accession: str, field: str) -> set[Any]:
        values = {
            value
            for value in self.graph._exam_observations[accession][field].values()
            if value is not None
        }
        for contribution in self._pending.values():
            if contribution.concept != "exam" or contribution.entity_id != accession:
                continue
            payload = dict(_thaw_mapping(contribution.payload))
            key = "exam_description" if field == "description" else field
            value = payload.get(key)
            if value is not None:
                values.add(value)
        return values

    def _stage(self, contribution: _Contribution) -> bool:
        if not isinstance(contribution.source, SourceRef):
            raise TypeError("source must be a SourceRef")
        existing = self._pending.get(contribution.address)
        if existing is None:
            existing = self.graph._contributions.get(contribution.address)
        if existing is None:
            self._pending[contribution.address] = contribution
            return True
        if existing.payload == contribution.payload:
            return False
        self.add_issue(
            Issue(
                code="source_contribution_conflict",
                message="one source contribution address has changed content",
                source=contribution.source,
                context={
                    "concept": contribution.concept,
                    "slot": contribution.slot,
                },
            )
        )
        return False

    def _commit(self) -> None:
        graph = self.graph
        for patient_id, patient in self._patient_nodes.items():
            graph._patients.setdefault(patient_id, patient)
        for accession, exam in self._exam_nodes.items():
            graph._exams.setdefault(accession, exam)
        for identity, finding in self._finding_nodes.items():
            graph._findings.setdefault(identity, finding)
        for image_id, image in self._image_nodes.items():
            graph._images.setdefault(image_id, image)

        touched_exams: set[str] = set()
        touched_findings: set[Tuple[str, str]] = set()
        for address, contribution in self._pending.items():
            graph._contributions[address] = contribution
            if contribution.concept == "finding":
                identity = tuple(contribution.entity_id.split("\x1f", 1))
                values = dict(_thaw_mapping(contribution.payload))
                observations = graph._finding_observations[identity]
                observations["laterality"][contribution.source] = Laterality.coerce(
                    values.get("laterality")
                )
                for field in ("finding_type", "assessment", "recommendation"):
                    observations[field][contribution.source] = values.get(field)
                touched_findings.add(identity)
                continue
            if contribution.concept == "image":
                values = dict(_thaw_mapping(contribution.payload))
                observations = graph._image_observations[contribution.entity_id]
                for field, value in values.items():
                    if field == "image_id":
                        continue
                    if field == "laterality":
                        value = Laterality.coerce(value)
                    elif field == "view_position":
                        value = ViewPosition.coerce(value)
                    elif field == "modality":
                        value = ImageModality.coerce(value)
                    observations[field][contribution.source] = value
                continue
            if contribution.concept != "exam":
                continue
            values = dict(_thaw_mapping(contribution.payload))
            observations = graph._exam_observations[contribution.entity_id]
            observations["patient_id"][contribution.source] = values.get("patient_id")
            observations["exam_date"][contribution.source] = values.get("exam_date")
            observations["description"][contribution.source] = values.get(
                "exam_description"
            )
            touched_exams.add(contribution.entity_id)

        # A newly loaded patient may resolve an existing exam reference.
        touched_exams.update(
            accession
            for accession, exam in graph._exams.items()
            if exam.patient_id in self._patient_nodes
        )
        for accession in touched_exams:
            graph._resolve_exam(accession)
        for identity in touched_findings:
            graph._resolve_finding(identity)
        for accession in {identity[0] for identity in touched_findings}:
            exam = graph._exams[accession]
            exam.findings.sort(key=lambda finding: finding.identity)
            for side in exam.breast_sides.values():
                side.findings.sort(key=lambda finding: finding.identity)
        graph._resolve_images()
        for issue in self.issues:
            graph._record_issue(issue)


def _nonempty_or_default(value: Optional[str], default: str, attribute: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{attribute} must be a non-empty string or None")
    return value


def _require_identifier(value: str, attribute: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{attribute} must be a non-empty string")


def _require_open(transaction: GraphTransaction) -> None:
    if transaction._closed:
        raise RuntimeError("graph transaction is closed")


def _one_value_or_none(values: Any) -> Any:
    populated = {value for value in values if value is not None}
    return next(iter(populated)) if len(populated) == 1 else None


def _one_enum_or_unknown(values: Any, unknown: Any) -> Any:
    populated = {value for value in values if value is not unknown}
    return next(iter(populated)) if len(populated) == 1 else unknown


def _freeze(value: Any) -> Tuple[Any, ...]:
    if isinstance(value, Mapping):
        return (
            "mapping",
            tuple(sorted((str(key), _freeze(item)) for key, item in value.items())),
        )
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_freeze(item) for item in value))
    if isinstance(value, Enum):
        return ("enum", type(value).__qualname__, _freeze(value.value))
    if value is None or type(value) in {bool, int, float, str}:
        return (type(value).__name__, value)
    if hasattr(value, "isoformat"):
        return (type(value).__name__, value.isoformat())
    return ("repr", type(value).__qualname__, repr(value))


def _thaw_mapping(value: Tuple[Any, ...]) -> Tuple[Tuple[str, Any], ...]:
    if not value or value[0] != "mapping":
        raise TypeError("contribution payload must be a mapping")
    return tuple((key, _thaw(item)) for key, item in value[1])


def _thaw(value: Tuple[Any, ...]) -> Any:
    tag, payload = value
    if tag == "mapping":
        return {key: _thaw(item) for key, item in payload}
    if tag == "sequence":
        return tuple(_thaw(item) for item in payload)
    if tag == "NoneType":
        return None
    if tag in {"bool", "int", "float", "str"}:
        return payload
    return payload


__all__ = ["DatasetGraph", "GraphTransaction", "LoadError"]
