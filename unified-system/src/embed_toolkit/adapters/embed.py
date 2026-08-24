"""EMBED table builders for clinical rows and image metadata rows.

The public EMBED tables have two different meanings: MagView clinical rows
describe clinical grains and source-colocated associations, while image
metadata rows describe files and optional image-local ROIs. This adapter keeps
those sources separate, assembles exam-to-image ownership explicitly, and only
projects finding-image candidate sets from that owned hierarchy.
"""

from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from embed_toolkit.clinical.exams import BreastSide, Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.associations import (
    AttributionStatus,
    ClinicalObjectKind,
    ClinicalObjectReference,
    FindingProcedureLink,
)
from embed_toolkit.clinical.pathology import (
    PathologyAttributionLink,
    PathologyDiagnosis,
    PathologyObservation,
    PathologyRecordKind,
    PathologyReference,
    PathologySeverity,
)
from embed_toolkit.clinical.procedures import (
    Procedure,
    ProcedureIdentity,
    UnresolvedProcedureOccurrence,
)
from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.core.build_policy import BuildPolicy
from embed_toolkit.core.primitives import (
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewPosition,
)
from embed_toolkit.core.provenance import (
    BuildIssue,
    IssueSeverity,
    ResolutionState,
    SourceLocator,
    SourceOccurrence,
    SourceScopeKind,
)
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.rois import RegionOfInterest


Row = Mapping[str, Any]


@dataclass(frozen=True)
class EmbedClinicalTables:
    """Clinical objects built from MagView-derived rows."""

    patients: Tuple[Patient, ...]
    exams: Tuple[Exam, ...]
    findings: Tuple[Finding, ...]
    breast_sides: Tuple[BreastSide, ...]
    procedures: Tuple[Procedure, ...]
    finding_procedure_links: Tuple[FindingProcedureLink, ...]
    unresolved_procedure_occurrences: Tuple[UnresolvedProcedureOccurrence, ...]
    pathology_observations: Tuple[PathologyObservation, ...]
    pathology_diagnoses: Tuple[PathologyDiagnosis, ...]
    pathology_attribution_links: Tuple[PathologyAttributionLink, ...]
    unresolved_occurrences: Tuple[SourceOccurrence, ...]
    build_issues: Tuple[BuildIssue, ...]


@dataclass(frozen=True)
class EmbedImageTables:
    """Image objects built from image metadata rows."""

    images: Tuple[MammogramImage, ...]
    rois: Tuple[RegionOfInterest, ...]


@dataclass(frozen=True)
class EmbedClinicalImageGraph:
    """Cross-table exam/image containment and reconciliation result."""

    exams: Tuple[Exam, ...]
    images: Tuple[MammogramImage, ...]
    unmatched_images: Tuple[MammogramImage, ...]
    unmatched_exams: Tuple[Exam, ...]
    build_issues: Tuple[BuildIssue, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize images once and containment through image references."""

        return {
            "exams": [
                {
                    "accession_number": exam.accession_number,
                    "patient_id": exam.patient_id,
                    "image_references": [image.image_id for image in exam.images],
                    "breast_sides": [
                        {
                            "accession_number": side.accession_number,
                            "laterality": side.laterality.value,
                            "image_references": [
                                image.image_id for image in side.images
                            ],
                        }
                        for laterality in (Laterality.LEFT, Laterality.RIGHT)
                        if (side := exam.breast_sides.get(laterality)) is not None
                    ],
                }
                for exam in self.exams
            ],
            "images": [image.to_dict() for image in self.images],
            "unmatched_image_references": [
                image.image_id for image in self.unmatched_images
            ],
            "unmatched_exam_references": [
                exam.accession_number for exam in self.unmatched_exams
            ],
            "build_issues": [issue.to_dict() for issue in self.build_issues],
        }


@dataclass(frozen=True)
class FindingImageCandidateProjection:
    """Candidate images selected without asserting clinical attribution."""

    finding: Finding
    candidate_images: Tuple[MammogramImage, ...]
    selection_basis: str = field(
        default="assembled_exam_unilateral_side_membership",
        init=False,
    )
    status: AttributionStatus = field(
        default=AttributionStatus.CANDIDATE,
        init=False,
    )

    def to_dict(self) -> dict[str, object]:
        """Serialize finding and candidate membership through references."""

        return {
            "finding_reference": {
                "accession_number": self.finding.accession_number,
                "finding_number": self.finding.finding_number,
            },
            "candidate_image_references": [
                image.image_id for image in self.candidate_images
            ],
            "selection_basis": self.selection_basis,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class _ColumnAliases:
    patient_id: Tuple[str, ...]
    birth_year: Tuple[str, ...] = ("birth_year", "PatientBirthYear")
    sex: Tuple[str, ...] = ("sex", "PatientSex")
    accession: Tuple[str, ...] = ()
    exam_date: Tuple[str, ...] = ()
    exam_description: Tuple[str, ...] = ("exam_description", "StudyDescription")
    finding_number: Tuple[str, ...] = ()
    clinical_side: Tuple[str, ...] = ()
    finding_type: Tuple[str, ...] = ("finding_type", "massshape", "finding")
    assessment: Tuple[str, ...] = ()
    procedure_id: Tuple[str, ...] = ("procedure_id", "proc_id")
    procedure_type: Tuple[str, ...] = ()
    procedure_date: Tuple[str, ...] = ()
    procedure_laterality: Tuple[str, ...] = ()
    pathology_id: Tuple[str, ...] = ("pathology_id", "path_id")
    pathology_diagnosis: Tuple[str, ...] = ("pathology_diagnosis", "path_diag")
    pathology_severity: Tuple[str, ...] = ()
    pathology_result_category: Tuple[str, ...] = (
        "pathology_category",
        "path_result",
    )
    pathology_report_date: Tuple[str, ...] = ()
    pathology_malignant: Tuple[str, ...] = ("pathology_malignant", "malignant")
    pathology_descriptor_prefix: str = "path"
    image_id: Tuple[str, ...] = ()
    image_side: Tuple[str, ...] = ()
    view_position: Tuple[str, ...] = ()
    modality: Tuple[str, ...] = ()
    height: Tuple[str, ...] = ()
    width: Tuple[str, ...] = ()
    frame_count: Tuple[str, ...] = ()
    study_uid: Tuple[str, ...] = ("StudyInstanceUID", "study_instance_uid")
    series_uid: Tuple[str, ...] = ()
    sop_uid: Tuple[str, ...] = ()
    patient_orientation: Tuple[str, ...] = ()
    coordinate_frame_id: Tuple[str, ...] = ()
    roi_id: Tuple[str, ...] = ("roi_id", "ROI_ID")
    roi_source: Tuple[str, ...] = ()
    roi_confidence: Tuple[str, ...] = ("roi_confidence", "ROI_confidence")
    roi_coordinates: Tuple[str, ...] = ()
    roi_frames: Tuple[str, ...] = ()
    y_min: Tuple[str, ...] = ("y_min", "YMin")
    x_min: Tuple[str, ...] = ("x_min", "XMin")
    y_max: Tuple[str, ...] = ("y_max", "YMax")
    x_max: Tuple[str, ...] = ("x_max", "XMax")


_MISSING = object()


def _column_aliases(config: Optional[EmbedColumnConfig]) -> _ColumnAliases:
    columns = config or default_embed_columns()
    return _ColumnAliases(
        patient_id=_aliases(columns.patient_id, "patient_id", "PatientID"),
        accession=_aliases(columns.accession, "accession_number", "AccessionNumber"),
        exam_date=_aliases(columns.study_date, "exam_date", "StudyDate"),
        finding_number=_aliases(columns.finding_number, "finding_number"),
        clinical_side=_aliases(columns.finding_laterality, "laterality"),
        assessment=_aliases(columns.finding_assessment, "assessment", "birads"),
        procedure_type=_aliases(columns.procedure_type, "procedure_type", "proc_type"),
        procedure_date=_aliases(columns.procedure_date, "procedure_date", "proc_date"),
        procedure_laterality=_aliases(
            columns.procedure_laterality,
            "bside",
            "procedure_laterality",
        ),
        pathology_severity=_aliases(
            columns.pathology_severity,
        ),
        pathology_report_date=_aliases(
            columns.pathology_report_date,
            "pathology_report_date",
        ),
        pathology_descriptor_prefix=columns.pathology_diagnosis_prefix,
        image_id=_aliases(columns.image_id, "image_id", "ImageID", columns.image_path),
        image_side=_aliases(columns.image_laterality, "image_laterality"),
        view_position=_aliases(columns.image_view, "view_position"),
        modality=_aliases(columns.image_modality, "ImageType", "modality"),
        height=_aliases(columns.image_height, "height", "image_height"),
        width=_aliases(columns.image_width, "width", "image_width"),
        frame_count=_aliases(columns.image_frames, "NumberOfFrames", "frame_count"),
        series_uid=_aliases(columns.series_id, "SeriesInstanceUID", "series_instance_uid"),
        sop_uid=_aliases(columns.sop_instance_uid, "SOPInstanceUID", "sop_instance_uid"),
        patient_orientation=_aliases(columns.image_orientation, "patient_orientation"),
        coordinate_frame_id=_aliases(
            columns.acquisition_group_id,
            "coordinate_frame_id",
        ),
        roi_source=_aliases(columns.roi_source, "roi_source", "ROI_source"),
        roi_coordinates=_aliases(columns.roi_coords, "roi_coordinates"),
        roi_frames=_aliases(columns.roi_frames, "ROI_frames", "roi_frames"),
    )


def _aliases(*names: str) -> Tuple[str, ...]:
    ordered = []
    for name in names:
        if name and name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def build_clinical_tables(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
    build_policy: Optional[BuildPolicy] = None,
    source_scope: Optional[str] = None,
    source_scope_kind: SourceScopeKind = SourceScopeKind.MATERIALIZATION,
    source_profile: str = "embed_context_internal",
    source_table: str = "magview",
) -> EmbedClinicalTables:
    """Build clinical objects under an explicit source-evidence policy.

    ``source_scope`` should name the caller's dataset release or
    materialization. When omitted, the builder creates an explicitly ephemeral
    in-memory materialization scope; that scope is provenance, not clinical or
    durable source identity. Row ordinals are zero-based within this call.
    """

    policy = build_policy or BuildPolicy()
    if not isinstance(policy, BuildPolicy):
        raise TypeError("build_policy must be a BuildPolicy")
    scope_kind = SourceScopeKind(source_scope_kind)
    if source_scope is None:
        if scope_kind is not SourceScopeKind.MATERIALIZATION:
            raise ValueError("Dataset source scopes must be supplied explicitly")
        resolved_source_scope = f"in-memory:{uuid.uuid4()}"
    elif not isinstance(source_scope, str) or not source_scope.strip():
        raise ValueError("source_scope must be a non-empty string")
    else:
        resolved_source_scope = source_scope
    for name, value in (
        ("source_profile", source_profile),
        ("source_table", source_table),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    column_aliases = _column_aliases(columns)
    patients: dict[str, Patient] = {}
    exams: dict[str, Exam] = {}
    procedure_registry: dict[ProcedureIdentity, Procedure] = {}
    finding_procedure_links: list[FindingProcedureLink] = []
    unresolved_procedure_occurrences: list[UnresolvedProcedureOccurrence] = []
    pathology_observations: list[PathologyObservation] = []
    pathology_diagnoses: list[PathologyDiagnosis] = []
    pathology_attribution_links: list[PathologyAttributionLink] = []
    unresolved_occurrences: dict[SourceLocator, SourceOccurrence] = {}
    build_issues: list[BuildIssue] = []

    for row_ordinal, row in enumerate(rows):
        locator = SourceLocator(
            scope=resolved_source_scope,
            scope_kind=scope_kind,
            source_profile=source_profile,
            source_table=source_table,
            row_ordinal=row_ordinal,
        )
        row_observations, row_diagnosis, pathology_issues = _pathology_from_row(
            row,
            column_aliases,
            locator,
        )
        if pathology_issues:
            pathology_occurrence = SourceOccurrence(
                locator=locator,
                raw_values=dict(row),
                resolution_state=ResolutionState.UNRESOLVED,
                issues=pathology_issues,
            )
            policy.review(pathology_occurrence)
            _retain_unresolved_occurrence(
                unresolved_occurrences,
                pathology_occurrence,
            )
            build_issues.extend(pathology_issues)
        pathology_observations.extend(row_observations)
        if row_diagnosis is not None:
            pathology_diagnoses.append(row_diagnosis)
        patient_id = _string_value(_get(row, column_aliases.patient_id))
        accession = _string_value(_get(row, column_aliases.accession))
        finding_number = _string_value(_get(row, column_aliases.finding_number))
        identity_issues = _clinical_identity_issues(
            patient_id=patient_id,
            accession=accession,
            finding_number=finding_number,
            locator=locator,
            columns=column_aliases,
        )
        parent_identity_issues = tuple(
            issue
            for issue in identity_issues
            if issue.code != "missing_finding_identity"
        )
        if parent_identity_issues:
            occurrence = SourceOccurrence(
                locator=locator,
                raw_values=dict(row),
                resolution_state=ResolutionState.UNRESOLVED,
                issues=identity_issues,
            )
            policy.review(occurrence)
            _retain_unresolved_occurrence(unresolved_occurrences, occurrence)
            build_issues.extend(identity_issues)
            continue

        assert patient_id is not None
        assert accession is not None
        existing_exam = exams.get(accession)
        if existing_exam is not None and existing_exam.patient_id != patient_id:
            conflict_issue = BuildIssue(
                code="conflicting_accession_patient_identity",
                message="An accession cannot resolve to multiple patient identities.",
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "accession_number": accession,
                    "retained_patient_id": existing_exam.patient_id,
                    "observed_patient_id": patient_id,
                },
            )
            conflict_issues = (conflict_issue,) + tuple(
                issue
                for issue in identity_issues
                if issue.code == "missing_finding_identity"
            )
            occurrence = SourceOccurrence(
                locator=locator,
                raw_values=dict(row),
                resolution_state=ResolutionState.UNRESOLVED,
                issues=conflict_issues,
            )
            policy.review(occurrence)
            _retain_unresolved_occurrence(unresolved_occurrences, occurrence)
            build_issues.extend(conflict_issues)
            continue

        finding_occurrence = None
        if finding_number is None:
            finding_occurrence = SourceOccurrence(
                locator=locator,
                raw_values=dict(row),
                resolution_state=ResolutionState.UNRESOLVED,
                issues=tuple(
                    issue
                    for issue in identity_issues
                    if issue.code == "missing_finding_identity"
                ),
            )
            policy.review(finding_occurrence)

        patient = patients.setdefault(
            patient_id,
            Patient(
                patient_id=patient_id,
                sex=_string_value(_get(row, column_aliases.sex)),
                birth_year=_optional_int(_get(row, column_aliases.birth_year)),
            ),
        )
        exam = existing_exam
        if exam is None:
            exam = Exam(
                accession_number=accession,
                patient_id=patient_id,
                exam_date=_string_value(_get(row, column_aliases.exam_date)),
                description=_string_value(_get(row, column_aliases.exam_description)),
            )
            exams[accession] = patient.add_exam(exam)
        else:
            patient.add_exam(exam)

        if finding_occurrence is not None:
            pathology_attribution_links.extend(
                _pathology_attribution_links(
                    observations=row_observations,
                    diagnosis=row_diagnosis,
                    targets=(
                        ClinicalObjectReference(
                            ClinicalObjectKind.PATIENT,
                            (patient_id,),
                        ),
                        ClinicalObjectReference(
                            ClinicalObjectKind.EXAM,
                            (accession,),
                        ),
                    ),
                    locator=locator,
                )
            )
            _retain_unresolved_occurrence(
                unresolved_occurrences,
                finding_occurrence,
            )
            build_issues.extend(finding_occurrence.issues)
            continue

        assert finding_number is not None
        side = _clinical_laterality(_get(row, column_aliases.clinical_side))
        finding = Finding(
            accession_number=accession,
            laterality=side,
            finding_number=finding_number,
            finding_type=_string_value(_get(row, column_aliases.finding_type)),
            assessment=_string_value(_get(row, column_aliases.assessment)),
            raw_source_fields=dict(row),
        )
        finding = exam.add_finding(finding)
        resolved_procedure, link, unresolved_procedure = _procedure_from_row(
            row,
            column_aliases,
            patient_id,
            accession,
            finding.finding_number,
            locator,
            procedure_registry,
            policy,
        )
        if link is not None:
            finding_procedure_links.append(link)
        if unresolved_procedure is not None:
            unresolved_procedure_occurrences.append(unresolved_procedure)
            _retain_unresolved_occurrence(
                unresolved_occurrences,
                unresolved_procedure.occurrence,
            )
            build_issues.extend(unresolved_procedure.occurrence.issues)
        targets = [
            ClinicalObjectReference(ClinicalObjectKind.PATIENT, (patient_id,)),
            ClinicalObjectReference(ClinicalObjectKind.EXAM, (accession,)),
            ClinicalObjectReference(
                ClinicalObjectKind.FINDING,
                (accession, finding.finding_number),
            ),
        ]
        targets.extend(
            ClinicalObjectReference(
                ClinicalObjectKind.BREAST_SIDE,
                (accession, laterality.value),
            )
            for laterality in Laterality.coerce(finding.laterality).expand()
        )
        if resolved_procedure is not None:
            procedure_identity = resolved_procedure.identity
            targets.append(
                ClinicalObjectReference(
                    ClinicalObjectKind.PROCEDURE,
                    (
                        procedure_identity.patient_id,
                        procedure_identity.performed_date,
                        procedure_identity.procedure_type,
                        procedure_identity.laterality.value,
                    ),
                )
            )
        pathology_attribution_links.extend(
            _pathology_attribution_links(
                observations=row_observations,
                diagnosis=row_diagnosis,
                targets=tuple(targets),
                locator=locator,
            )
        )

    ordered_patients = tuple(patients.values())
    ordered_exams = tuple(exams.values())
    ordered_findings = tuple(finding for exam in ordered_exams for finding in exam.findings)
    ordered_sides = tuple(
        side for exam in ordered_exams for side in exam.breast_sides.values()
    )
    return EmbedClinicalTables(
        patients=ordered_patients,
        exams=ordered_exams,
        findings=ordered_findings,
        breast_sides=ordered_sides,
        procedures=tuple(procedure_registry.values()),
        finding_procedure_links=tuple(finding_procedure_links),
        unresolved_procedure_occurrences=tuple(unresolved_procedure_occurrences),
        pathology_observations=tuple(pathology_observations),
        pathology_diagnoses=tuple(pathology_diagnoses),
        pathology_attribution_links=tuple(pathology_attribution_links),
        unresolved_occurrences=tuple(unresolved_occurrences.values()),
        build_issues=tuple(build_issues),
    )


def build_image_tables(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> EmbedImageTables:
    """Build images and image-local ROIs from image metadata rows."""

    column_aliases = _column_aliases(columns)
    images: list[MammogramImage] = []
    rois: list[RegionOfInterest] = []
    image_by_id: dict[str, MammogramImage] = {}

    for row in rows:
        image_id = _required_string(row, column_aliases.image_id, "image_id")
        coordinate_frame_id = _string_value(_get(row, column_aliases.coordinate_frame_id))
        image = image_by_id.get(image_id)
        if image is None:
            modality = ImageModality.coerce(_get(row, column_aliases.modality))
            image = MammogramImage(
                    image_id=image_id,
                    laterality=Laterality.coerce(_get(row, column_aliases.image_side)),
                    view_position=ViewPosition.coerce(
                        _get(row, column_aliases.view_position)
                    ),
                    modality=modality,
                    height=_optional_int(_get(row, column_aliases.height)),
                    width=_optional_int(_get(row, column_aliases.width)),
                    # ImagesInAcquisition is a frame count only for DBT. The
                    # NumberOfFrames alias remains a compatibility input.
                    frame_count=_optional_int(_get(row, column_aliases.frame_count))
                    if modality is ImageModality.DBT
                    else None,
                    accession_number=_string_value(_get(row, column_aliases.accession)),
                    patient_id=_string_value(_get(row, column_aliases.patient_id)),
                    study_instance_uid=_string_value(
                        _get(row, column_aliases.study_uid)
                    ),
                    series_instance_uid=_string_value(
                        _get(row, column_aliases.series_uid)
                    ),
                    sop_instance_uid=_string_value(_get(row, column_aliases.sop_uid)),
                    patient_orientation=_patient_orientation(row, column_aliases),
                    coordinate_frame_id=coordinate_frame_id,
                )
            images.append(image)
            image_by_id[image_id] = image
        rois.extend(_rois_from_row(row, column_aliases, image, coordinate_frame_id))

    return EmbedImageTables(images=tuple(images), rois=tuple(rois))


def assemble_clinical_image_graph(
    clinical: EmbedClinicalTables,
    image_tables: EmbedImageTables,
    *,
    build_policy: Optional[BuildPolicy] = None,
    source_scope: Optional[str] = None,
    source_scope_kind: SourceScopeKind = SourceScopeKind.MATERIALIZATION,
    source_profile: str = "internal-v1c",
    source_table: str = "image_metadata",
) -> EmbedClinicalImageGraph:
    """Attach images to matching exams after cross-table identity checks.

    An omitted scope creates explicitly ephemeral assembly provenance. Dataset
    scopes must be supplied by the caller. Validation is completed before any
    attachment so strict failures do not leave a partially assembled graph.
    """

    if not isinstance(clinical, EmbedClinicalTables):
        raise TypeError("clinical must be an EmbedClinicalTables")
    if not isinstance(image_tables, EmbedImageTables):
        raise TypeError("image_tables must be an EmbedImageTables")
    policy = build_policy or BuildPolicy()
    if not isinstance(policy, BuildPolicy):
        raise TypeError("build_policy must be a BuildPolicy")
    scope_kind = SourceScopeKind(source_scope_kind)
    if source_scope is None:
        if scope_kind is not SourceScopeKind.MATERIALIZATION:
            raise ValueError("Dataset source scopes must be supplied explicitly")
        resolved_source_scope = f"in-memory-assembly:{uuid.uuid4()}"
    elif not isinstance(source_scope, str) or not source_scope.strip():
        raise ValueError("source_scope must be a non-empty string")
    else:
        resolved_source_scope = source_scope
    for name, value in (
        ("source_profile", source_profile),
        ("source_table", source_table),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    exam_by_accession = {exam.accession_number: exam for exam in clinical.exams}
    attachments = []
    unmatched_images = []
    issues = []
    matched_accessions = set()

    for image in image_tables.images:
        accession = image.accession_number
        exam = exam_by_accession.get(accession) if accession is not None else None
        if exam is None:
            unmatched_images.append(image)
            continue
        if (
            image.patient_id is not None
            and exam.patient_id is not None
            and image.patient_id != exam.patient_id
        ):
            issue = BuildIssue(
                code="conflicting_clinical_image_patient_identity",
                message=(
                    "Clinical and image patient identities conflict for one "
                    "accession."
                ),
                severity=IssueSeverity.ERROR,
                source=SourceLocator(
                    scope=resolved_source_scope,
                    scope_kind=scope_kind,
                    source_profile=source_profile,
                    source_table=source_table,
                    source_key=image.image_id,
                ),
                context={
                    "accession_number": accession,
                    "clinical_patient_id": exam.patient_id,
                    "image_patient_id": image.patient_id,
                    "image_id": image.image_id,
                },
            )
            policy.handle_issue(issue)
            issues.append(issue)
            unmatched_images.append(image)
            continue
        attachments.append((exam, image))
        matched_accessions.add(exam.accession_number)

    for exam, image in attachments:
        exam.add_image(image)

    unmatched_exams = tuple(
        exam
        for exam in clinical.exams
        if exam.accession_number not in matched_accessions
    )
    return EmbedClinicalImageGraph(
        exams=clinical.exams,
        images=image_tables.images,
        unmatched_images=tuple(unmatched_images),
        unmatched_exams=unmatched_exams,
        build_issues=tuple(issues),
    )


def project_finding_image_candidates(
    graph: EmbedClinicalImageGraph,
) -> Tuple[FindingImageCandidateProjection, ...]:
    """Project side-compatible candidates from assembled exam containment.

    Candidate membership is a search-space projection only. It is not an
    inferred or confirmed clinical finding-to-image attribution.
    """

    if not isinstance(graph, EmbedClinicalImageGraph):
        raise TypeError("graph must be an EmbedClinicalImageGraph")

    projections = []
    for exam in graph.exams:
        for finding in exam.findings:
            candidates = []
            seen_image_ids = set()
            for laterality in finding.laterality.expand():
                side = exam.breast_sides.get(laterality)
                if side is None:
                    continue
                for image in side.images:
                    if image.laterality is not laterality:
                        continue
                    if image.image_id in seen_image_ids:
                        continue
                    candidates.append(image)
                    seen_image_ids.add(image.image_id)
            projections.append(
                FindingImageCandidateProjection(
                    finding=finding,
                    candidate_images=tuple(candidates),
                )
            )
    return tuple(projections)


def build_patients(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[Patient, ...]:
    """Convenience wrapper returning only patient aggregates."""

    return build_clinical_tables(rows, columns=columns).patients


def build_exams(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[Exam, ...]:
    """Convenience wrapper returning only exam aggregates."""

    return build_clinical_tables(rows, columns=columns).exams


def build_images(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[MammogramImage, ...]:
    """Convenience wrapper returning only image objects."""

    return build_image_tables(rows, columns=columns).images


def build_rois(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[RegionOfInterest, ...]:
    """Convenience wrapper returning only ROI objects."""

    return build_image_tables(rows, columns=columns).rois


def _clinical_laterality(value: Any) -> Laterality:
    if value is _MISSING or _is_blank(value):
        return Laterality.BILATERAL
    side = Laterality.coerce(value)
    return side


def _procedure_from_row(
    row: Row,
    columns: _ColumnAliases,
    patient_id: str,
    accession: str,
    finding_number: str,
    locator: SourceLocator,
    registry: dict[ProcedureIdentity, Procedure],
    policy: BuildPolicy,
) -> Tuple[
    Optional[Procedure],
    Optional[FindingProcedureLink],
    Optional[UnresolvedProcedureOccurrence],
]:
    procedure_id = _string_value(_get(row, columns.procedure_id))
    procedure_type = _string_value(_get(row, columns.procedure_type))
    procedure_date = _string_value(_get(row, columns.procedure_date))
    raw_laterality = _string_value(_get(row, columns.procedure_laterality))
    procedure_laterality = Laterality.coerce(raw_laterality)
    if not any((procedure_id, procedure_type, procedure_date, raw_laterality)):
        return None, None, None

    missing_identity_fields = tuple(
        field_name
        for field_name, missing in (
            ("patient_id", not patient_id.strip()),
            ("performed_date", procedure_date is None),
            ("procedure_type", procedure_type is None),
            ("laterality", procedure_laterality is Laterality.UNKNOWN),
        )
        if missing
    )
    if missing_identity_fields:
        issue = BuildIssue(
            code="incomplete_procedure_identity",
            message=(
                "A populated procedure surface requires patient, performed date, "
                "type, and known biopsy laterality."
            ),
            severity=IssueSeverity.ERROR,
            source=locator,
            context={
                "missing_identity_fields": list(missing_identity_fields),
                "source_procedure_id": procedure_id,
            },
        )
        occurrence = SourceOccurrence(
            locator=locator,
            raw_values=dict(row),
            resolution_state=ResolutionState.UNRESOLVED,
            issues=(issue,),
        )
        policy.review(occurrence)
        return (
            None,
            None,
            UnresolvedProcedureOccurrence(
                occurrence=occurrence,
                missing_identity_fields=missing_identity_fields,
                patient_id=patient_id,
                performed_date=procedure_date,
                procedure_type=procedure_type,
                laterality=procedure_laterality,
            ),
        )

    identity = ProcedureIdentity(
        patient_id=patient_id,
        performed_date=procedure_date,
        procedure_type=procedure_type,
        laterality=procedure_laterality,
    )
    occurrence = SourceOccurrence(
        locator=locator,
        raw_values=dict(row),
        resolution_state=ResolutionState.RESOLVED,
    )
    procedure = registry.setdefault(identity, Procedure(identity=identity))
    procedure.add_source_occurrence(occurrence)
    return (
        procedure,
        FindingProcedureLink(
            accession_number=accession,
            finding_number=finding_number,
            procedure=identity,
            status=AttributionStatus.SOURCE_COLOCATED,
            source=locator,
        ),
        None,
    )


def _pathology_from_row(
    row: Row,
    columns: _ColumnAliases,
    locator: SourceLocator,
) -> Tuple[
    Tuple[PathologyObservation, ...],
    Optional[PathologyDiagnosis],
    Tuple[BuildIssue, ...],
]:
    diagnosis = _string_value(_get(row, columns.pathology_diagnosis))
    category = _string_value(_get(row, columns.pathology_result_category))
    report_documented_date = _string_value(
        _get(row, columns.pathology_report_date)
    )
    malignant = _optional_bool(_get(row, columns.pathology_malignant))
    raw_severity = _get(row, columns.pathology_severity)
    if raw_severity is _MISSING or _is_blank(raw_severity):
        raw_severity = None
    observations = tuple(
        PathologyObservation(
            descriptor=descriptor,
            source_slot=f"{columns.pathology_descriptor_prefix}{index}",
            source_ordinal=index,
            source=locator,
        )
        for index in range(1, 11)
        if (
            descriptor := _string_value(
                row.get(f"{columns.pathology_descriptor_prefix}{index}", _MISSING)
            )
        )
        is not None
    )
    severity, issues = _govern_pathology_severity(
        raw_severity,
        observations,
        locator,
    )
    if not any(
        (
            diagnosis,
            category,
            report_documented_date,
            malignant is not None,
            raw_severity is not None,
            observations,
        )
    ):
        return (), None, ()
    row_diagnosis = PathologyDiagnosis(
        source=locator,
        diagnosis=diagnosis,
        result_category=category,
        malignant=malignant,
        severity=severity,
        raw_severity=raw_severity,
        report_documented_date=report_documented_date,
        validation_issues=issues,
    )
    return observations, row_diagnosis, issues


def _govern_pathology_severity(
    raw_severity: Any,
    observations: Tuple[PathologyObservation, ...],
    locator: SourceLocator,
) -> Tuple[Optional[PathologySeverity], Tuple[BuildIssue, ...]]:
    issues = []
    if raw_severity is None:
        if observations:
            issues.append(
                BuildIssue(
                    code="descriptors_without_severity",
                    message="Pathology descriptors require a populated severity.",
                    severity=IssueSeverity.ERROR,
                    source=locator,
                    context={"raw_severity": None},
                )
            )
        return None, tuple(issues)
    try:
        if isinstance(raw_severity, bool):
            raise ValueError
        numeric = int(raw_severity)
        if float(raw_severity) != numeric:
            raise ValueError
        severity = PathologySeverity(numeric)
    except (TypeError, ValueError):
        issues.append(
            BuildIssue(
                code="invalid_pathology_severity",
                message=(
                    "Pathology severity must be an integer from 0 through 5, "
                    f"got {raw_severity!r}."
                ),
                severity=IssueSeverity.ERROR,
                source=locator,
                context={"raw_severity": raw_severity},
            )
        )
        return None, tuple(issues)
    return severity, tuple(issues)


def _retain_unresolved_occurrence(
    occurrences: dict[SourceLocator, SourceOccurrence],
    occurrence: SourceOccurrence,
) -> None:
    """Retain one unresolved occurrence per physical source locator."""

    existing = occurrences.get(occurrence.locator)
    if existing is None:
        occurrences[occurrence.locator] = occurrence
        return
    if existing.raw_values != occurrence.raw_values:
        raise ValueError("One source locator cannot represent different raw rows")
    additional_issues = tuple(
        issue for issue in occurrence.issues if issue not in existing.issues
    )
    occurrences[occurrence.locator] = SourceOccurrence(
        locator=existing.locator,
        raw_values=existing.raw_values,
        resolution_state=ResolutionState.UNRESOLVED,
        issues=existing.issues + additional_issues,
    )


def _pathology_attribution_links(
    *,
    observations: Tuple[PathologyObservation, ...],
    diagnosis: Optional[PathologyDiagnosis],
    targets: Tuple[ClinicalObjectReference, ...],
    locator: SourceLocator,
) -> Tuple[PathologyAttributionLink, ...]:
    references = [
        PathologyReference(
            kind=PathologyRecordKind.OBSERVATION,
            source=observation.source,
            source_slot=observation.source_slot,
        )
        for observation in observations
    ]
    if diagnosis is not None:
        references.append(
            PathologyReference(
                kind=PathologyRecordKind.DIAGNOSIS,
                source=diagnosis.source,
            )
        )
    return tuple(
        PathologyAttributionLink(
            pathology=reference,
            target=target,
            status=AttributionStatus.SOURCE_COLOCATED,
            source=locator,
        )
        for reference in references
        for target in targets
    )


def _rois_from_row(
    row: Row,
    columns: _ColumnAliases,
    image: MammogramImage,
    coordinate_frame_id: Optional[str],
) -> Tuple[RegionOfInterest, ...]:
    coordinate_sets = _coordinate_sets(row, columns)
    if not coordinate_sets:
        return ()

    frames = _sequence_value(_get(row, columns.roi_frames)) if image.is_dbt else ()
    if frames and len(frames) != len(coordinate_sets):
        raise ValueError("Nonempty ROI_frames must align positionally with ROI_coords")
    roi_ids = _sequence_value(_get(row, columns.roi_id))
    source = _string_value(_get(row, columns.roi_source))
    confidence = _optional_float(_get(row, columns.roi_confidence))
    rois = []
    for index, coordinates in enumerate(coordinate_sets):
        rois.append(
            RegionOfInterest.from_embed_coordinates(
                coordinates=coordinates,
                roi_id=_string_value(_indexed_value(roi_ids, index))
                or _string_value(_get(row, columns.roi_id))
                or f"{image.image_id}:roi:{index + 1}",
                image_id=image.image_id,
                frame_indices=_frame_indices(_indexed_value(frames, index)),
                source=source,
                confidence=confidence,
                coordinate_frame_id=coordinate_frame_id,
            )
        )
        if image.frame_count is not None and any(
            frame >= image.frame_count for frame in rois[-1].frame_indices
        ):
            raise ValueError(
                f"ROI frame index must be below DBT frame count {image.frame_count}"
            )
    return tuple(rois)


def _coordinate_sets(
    row: Row,
    columns: _ColumnAliases,
) -> Tuple[Tuple[float, float, float, float], ...]:
    raw_coordinates = _get(row, columns.roi_coordinates)
    if raw_coordinates is not _MISSING:
        parsed = _sequence_value(raw_coordinates)
        if len(parsed) == 4 and not any(isinstance(item, (list, tuple)) for item in parsed):
            return (_coordinate_box(parsed),)
        return tuple(_coordinate_box(_sequence_value(item)) for item in parsed)

    values = (
        _get(row, columns.y_min),
        _get(row, columns.x_min),
        _get(row, columns.y_max),
        _get(row, columns.x_max),
    )
    if any(value is _MISSING or _is_blank(value) for value in values):
        return ()
    return (_coordinate_box(values),)


def _coordinate_box(values: Sequence[Any]) -> Tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError("ROI coordinates must have four values")
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _frame_indices(value: Any) -> Tuple[int, ...]:
    """Return one ROI's complete DBT frame collection."""

    if value is _MISSING or _is_blank(value):
        return ()
    return tuple(_required_frame_index(item) for item in _sequence_value(value))


def _required_frame_index(value: Any) -> int:
    frame = _optional_int(value)
    if frame is None:
        raise ValueError("ROI frame indices must be populated integers")
    return frame


def _patient_orientation(
    row: Row,
    columns: _ColumnAliases,
) -> Optional[PatientOrientation]:
    value = _get(row, columns.patient_orientation)
    if value is _MISSING or _is_blank(value):
        return None
    return PatientOrientation.coerce(value)


def _clinical_identity_issues(
    *,
    patient_id: Optional[str],
    accession: Optional[str],
    finding_number: Optional[str],
    locator: SourceLocator,
    columns: _ColumnAliases,
) -> Tuple[BuildIssue, ...]:
    issues = []
    for value, code, message, logical_field, aliases in (
        (
            patient_id,
            "missing_patient_identity",
            "Patient identity is required to construct clinical objects.",
            "patient_id",
            columns.patient_id,
        ),
        (
            accession,
            "missing_accession_identity",
            "Accession identity is required to construct clinical objects.",
            "accession_number",
            columns.accession,
        ),
        (
            finding_number,
            "missing_finding_identity",
            "Finding identity is required to construct clinical objects.",
            "finding_number",
            columns.finding_number,
        ),
    ):
        if value is None:
            issues.append(
                BuildIssue(
                    code=code,
                    message=message,
                    severity=IssueSeverity.ERROR,
                    source=locator,
                    context={
                        "logical_field": logical_field,
                        "source_columns": list(aliases),
                    },
                )
            )
    return tuple(issues)


def _required_string(row: Row, names: Tuple[str, ...], logical_name: str) -> str:
    value = _get(row, names)
    text = _string_value(value)
    if text is None:
        raise ValueError(f"Missing required EMBED column: {logical_name}")
    return text


def _get(row: Row, names: Tuple[str, ...]) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return _MISSING


def _sequence_value(value: Any) -> Tuple[Any, ...]:
    if value is _MISSING or _is_blank(value):
        return ()
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return (value,)
        return _sequence_value(parsed)
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _indexed_value(values: Tuple[Any, ...], index: int) -> Any:
    if not values:
        return _MISSING
    if index < len(values):
        return values[index]
    return _MISSING


def _string_value(value: Any) -> Optional[str]:
    if value is _MISSING or _is_blank(value):
        return None
    return str(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is _MISSING or _is_blank(value):
        return None
    return int(value)


def _optional_float(value: Any) -> Optional[float]:
    if value is _MISSING or _is_blank(value):
        return None
    return float(value)


def _optional_bool(value: Any) -> Optional[bool]:
    if value is _MISSING or _is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in {"1", "Y", "YES", "TRUE", "MALIGNANT"}:
        return True
    if text in {"0", "N", "NO", "FALSE", "BENIGN"}:
        return False
    return None


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}
