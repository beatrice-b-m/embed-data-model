"""EMBED table builders for clinical rows and image metadata rows.

The public EMBED tables have two different meanings: MagView clinical rows
describe clinical grains and source-colocated associations, while image
metadata rows describe files and optional image-local ROIs. This adapter keeps
those sources separate, assembles exam-to-image ownership explicitly, and only
projects finding-image candidate sets from that owned hierarchy.
"""

from __future__ import annotations

import ast
import math
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from numbers import Integral, Real
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from embed_toolkit.clinical.attributes import (
    ExamAttributeName,
    ExamAttributeObservation,
    PatientAttributeName,
    PatientAttributeObservation,
    PatientObservationTimeBasis,
)
from embed_toolkit.clinical.exams import BreastSide, Exam
from embed_toolkit.adapters.magview import normalize_magview_location
from embed_toolkit.adapters.reconciliation import (
    ExamImageContainmentLink,
    FindingImageCandidate,
    PatientIdentityCheckStatus,
    UnmatchedImage,
    UnmatchedImageReason,
)
from embed_toolkit.clinical.findings import (
    Finding,
    FindingNormalizationEvidence,
    FindingNormalizationWarning,
)
from embed_toolkit.clinical.interpretations import ImagingInterpretation
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
    _to_plain,
)
from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.config.profile_contracts import (
    INTERNAL_V2_PROFILE,
    ProfileContract,
    ProfileKind,
    profile_source_field_candidates,
    profile_contract_for,
    validate_contract_source_fields,
)
from embed_toolkit.core.build_policy import BuildPolicy
from embed_toolkit.core.anatomy import (
    AnatomicalPosition,
    DepthThird,
    MedialLateralAxis,
    Quadrant,
    SuperiorInferiorAxis,
)
from embed_toolkit.core.primitives import (
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewPosition,
)
from embed_toolkit.core.provenance import (
    AvailabilityState,
    BuildIssue,
    IssueSeverity,
    ResolutionState,
    SourceLocator,
    SourceOccurrence,
    SourceScopeKind,
)
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import RegionOfInterest


Row = Mapping[str, Any]


@dataclass
class _ImageRowState:
    raw_values: dict[str, Any]
    locator: SourceLocator
    image_id: Optional[str]
    issues: list[BuildIssue]
    roi_eligible: bool

_IMAGE_INVARIANT_ATTRIBUTES = (
    "accession_number",
    "patient_id",
    "laterality",
    "view_position",
    "modality",
    "source_modality",
    "derived_image_type",
    "height",
    "width",
    "frame_count",
    "study_instance_uid",
    "series_instance_uid",
    "sop_instance_uid",
    "patient_orientation",
    "coordinate_frame_id",
)


def _has_populated_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_instances(values: Iterable[Any], expected: type, name: str) -> None:
    if any(not isinstance(value, expected) for value in values):
        raise TypeError(f"{name} must contain only {expected.__name__} values")


def _unique_by_key(
    values: Iterable[Any],
    key: Any,
    name: str,
) -> dict[Any, Any]:
    indexed = {}
    for value in values:
        identity = key(value)
        if identity in indexed:
            raise ValueError(f"{name} values must be unique")
        indexed[identity] = value
    return indexed


def _same_objects(left: Iterable[Any], right: Iterable[Any]) -> bool:
    left_items = tuple(left)
    right_items = tuple(right)
    return len(left_items) == len(right_items) and all(
        observed is expected
        for observed, expected in zip(left_items, right_items)
    )


def _require_profile_sources(
    sources: Iterable[SourceLocator],
    expected_profile: str,
    label: str,
) -> None:
    for source in sources:
        if not isinstance(source, SourceLocator):
            raise TypeError(f"{label} must contain only SourceLocator evidence")
        if source.source_profile != expected_profile:
            raise ValueError(
                f"{label} source profile {source.source_profile!r} must match "
                f"{expected_profile!r}"
            )


def _finding_sources(findings: Iterable[Finding]) -> Iterable[SourceLocator]:
    for finding in findings:
        if finding.interpretation is not None:
            yield from finding.interpretation.sources
        yield from (item.source for item in finding.normalization_evidence)
        yield from (item.source for item in finding.normalization_warnings)


def _exam_clinical_sources(exams: Iterable[Exam]) -> Iterable[SourceLocator]:
    for exam in exams:
        yield from (item.source for item in exam.attribute_observations)
        yield from _finding_sources(exam.findings)
        for side in exam.breast_sides.values():
            yield from _finding_sources(side.findings)


def _exam_images(exams: Iterable[Exam]) -> Iterable[MammogramImage]:
    for exam in exams:
        yield from exam.images
        for side in exam.breast_sides.values():
            yield from side.images


def _clone_clinical_exams(exams: Iterable[Exam]) -> Tuple[Exam, ...]:
    """Rebuild an independent graph hierarchy with coherent clinical references."""

    cloned = []
    for exam in exams:
        findings = deepcopy(exam.findings)
        cloned_exam = Exam(
            accession_number=exam.accession_number,
            patient_id=exam.patient_id,
            exam_date=exam.exam_date,
            description=exam.description,
            attribute_observations=deepcopy(exam.attribute_observations),
            findings=findings,
            metadata=deepcopy(exam.metadata),
        )
        for laterality in exam.breast_sides:
            cloned_exam.ensure_side(laterality)
        cloned.append(cloned_exam)
    return tuple(cloned)


def _image_sources(images: Iterable[MammogramImage]) -> Iterable[SourceLocator]:
    for image in images:
        yield from image.sources
        yield from image.attribute_sources.values()


@dataclass(frozen=True)
class EmbedClinicalTables:
    """Clinical objects built from MagView-derived rows."""

    patients: Tuple[Patient, ...]
    patient_attribute_observations: Tuple[PatientAttributeObservation, ...]
    exams: Tuple[Exam, ...]
    exam_attribute_observations: Tuple[ExamAttributeObservation, ...]
    findings: Tuple[Finding, ...]
    interpretations: Tuple[ImagingInterpretation, ...]
    breast_sides: Tuple[BreastSide, ...]
    procedures: Tuple[Procedure, ...]
    finding_procedure_links: Tuple[FindingProcedureLink, ...]
    unresolved_procedure_occurrences: Tuple[UnresolvedProcedureOccurrence, ...]
    pathology_observations: Tuple[PathologyObservation, ...]
    pathology_diagnoses: Tuple[PathologyDiagnosis, ...]
    pathology_attribution_links: Tuple[PathologyAttributionLink, ...]
    source_occurrences: Tuple[SourceOccurrence, ...]
    build_issues: Tuple[BuildIssue, ...]
    profile_contract: ProfileContract

    def __post_init__(self) -> None:
        if not isinstance(self.profile_contract, ProfileContract):
            raise TypeError("profile_contract must be a ProfileContract")
        if self.profile_contract.kind is not ProfileKind.CLINICAL:
            raise ValueError("Clinical tables require a clinical profile contract")
        nested_exams = tuple(
            exam for patient in self.patients for exam in patient.exams
        )
        if tuple(_exam_images((*self.exams, *nested_exams))) or any(
            side.images for side in self.breast_sides
        ):
            raise ValueError(
                "Clinical tables cannot own image evidence without an image contract"
            )
        sources: list[SourceLocator] = []
        sources.extend(item.source for item in self.patient_attribute_observations)
        for patient in self.patients:
            sources.extend(item.source for item in patient.attribute_observations)
        sources.extend(item.source for item in self.exam_attribute_observations)
        sources.extend(_exam_clinical_sources((*self.exams, *nested_exams)))
        sources.extend(_finding_sources(self.findings))
        for side in self.breast_sides:
            sources.extend(_finding_sources(side.findings))
        sources.extend(
            source
            for interpretation in self.interpretations
            for source in interpretation.sources
        )
        sources.extend(
            source for procedure in self.procedures for source in procedure.sources
        )
        sources.extend(link.source for link in self.finding_procedure_links)
        sources.extend(item.source for item in self.unresolved_procedure_occurrences)
        sources.extend(item.source for item in self.pathology_observations)
        for diagnosis in self.pathology_diagnoses:
            sources.append(diagnosis.source)
            sources.extend(issue.source for issue in diagnosis.validation_issues)
        for link in self.pathology_attribution_links:
            sources.extend((link.source, link.pathology.source))
        for occurrence in self.source_occurrences:
            sources.append(occurrence.locator)
            sources.extend(issue.source for issue in occurrence.issues)
        sources.extend(issue.source for issue in self.build_issues)
        _require_profile_sources(
            sources,
            self.profile_contract.source_profile,
            "Clinical tables",
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the clinical graph once, with governed identity references."""

        return {
            "patients": [
                {
                    "patient_id": patient.patient_id,
                    "exam_references": [
                        exam.accession_number for exam in patient.exams
                    ],
                    "patient_attribute_observation_references": [
                        observation.reference_dict()
                        for observation in patient.attribute_observations
                    ],
                    "metadata": _to_plain(patient.metadata),
                }
                for patient in self.patients
            ],
            "patient_attribute_observations": [
                observation.to_dict()
                for observation in self.patient_attribute_observations
            ],
            "exams": [
                {
                    "accession_number": exam.accession_number,
                    "patient_id": exam.patient_id,
                    "exam_date": exam.exam_date,
                    "description": exam.description,
                    "exam_attribute_observation_references": [
                        observation.reference_dict()
                        for observation in exam.attribute_observations
                    ],
                    "finding_references": [
                        {
                            "accession_number": finding.accession_number,
                            "finding_number": finding.finding_number,
                        }
                        for finding in exam.findings
                    ],
                    "breast_side_references": [
                        {
                            "accession_number": side.accession_number,
                            "laterality": side.laterality.value,
                        }
                        for laterality in (Laterality.LEFT, Laterality.RIGHT)
                        if (side := exam.breast_sides.get(laterality)) is not None
                    ],
                    "image_references": [image.image_id for image in exam.images],
                    "metadata": _to_plain(exam.metadata),
                }
                for exam in self.exams
            ],
            "exam_attribute_observations": [
                observation.to_dict()
                for observation in self.exam_attribute_observations
            ],
            "findings": [finding.to_dict() for finding in self.findings],
            "interpretations": [
                interpretation.to_dict() for interpretation in self.interpretations
            ],
            "breast_sides": [side.to_dict() for side in self.breast_sides],
            "procedures": [procedure.to_dict() for procedure in self.procedures],
            "finding_procedure_links": [
                link.to_dict() for link in self.finding_procedure_links
            ],
            "unresolved_procedure_occurrences": [
                occurrence.to_dict()
                for occurrence in self.unresolved_procedure_occurrences
            ],
            "pathology_observations": [
                observation.to_dict() for observation in self.pathology_observations
            ],
            "pathology_diagnoses": [
                diagnosis.to_dict() for diagnosis in self.pathology_diagnoses
            ],
            "pathology_attribution_links": [
                link.to_dict() for link in self.pathology_attribution_links
            ],
            "source_occurrences": [
                occurrence.to_dict() for occurrence in self.source_occurrences
            ],
            "build_issues": [issue.to_dict() for issue in self.build_issues],
            "profile_contract": self.profile_contract.to_dict(),
        }


@dataclass(frozen=True)
class EmbedImageTables:
    """Image objects built from image metadata rows."""

    images: Tuple[MammogramImage, ...]
    rois: Tuple[RegionOfInterest, ...]
    source_occurrences: Tuple[SourceOccurrence, ...]
    build_issues: Tuple[BuildIssue, ...]
    profile_contract: ProfileContract

    def __post_init__(self) -> None:
        for attribute in ("images", "rois", "source_occurrences", "build_issues"):
            object.__setattr__(self, attribute, tuple(getattr(self, attribute)))
        _require_instances(self.images, MammogramImage, "images")
        _require_instances(self.rois, RegionOfInterest, "rois")
        _require_instances(
            self.source_occurrences,
            SourceOccurrence,
            "source_occurrences",
        )
        _require_instances(self.build_issues, BuildIssue, "build_issues")
        if not isinstance(self.profile_contract, ProfileContract):
            raise TypeError("profile_contract must be a ProfileContract")
        if self.profile_contract.kind is not ProfileKind.IMAGE:
            raise ValueError("Image tables require an image profile contract")
        sources = list(_image_sources(self.images))
        for roi in self.rois:
            sources.extend(roi.sources)
            sources.append(roi.locator.image_locator)
        for occurrence in self.source_occurrences:
            sources.append(occurrence.locator)
            sources.extend(issue.source for issue in occurrence.issues)
        sources.extend(issue.source for issue in self.build_issues)
        _require_profile_sources(
            sources,
            self.profile_contract.source_profile,
            "Image tables",
        )
        if len({roi.locator for roi in self.rois}) != len(self.rois):
            raise ValueError("EmbedImageTables ROI locators must be unique")
        images_by_id = _unique_by_key(
            self.images,
            lambda image: image.image_id,
            "image_id",
        )
        for roi in self.rois:
            image = images_by_id.get(roi.image_id)
            if image is None:
                raise ValueError("Every ROI image_id must resolve to a table image")
            if roi.locator.image_locator != image.canonical_source:
                raise ValueError(
                    "ROI locator image scope must match image canonical_source"
                )
            if any(source not in image.sources for source in roi.sources):
                raise ValueError("ROI sources must occur in its image source ledger")
            if roi.source_provenance.modality is not image.modality:
                raise ValueError("ROI source modality must match its image modality")
            if image.modality is ImageModality.DBT and image.frame_count is not None:
                if any(frame >= image.frame_count for frame in roi.frame_indices):
                    raise ValueError("ROI frame indices must be within image frame_count")

    def to_dict(self) -> dict[str, object]:
        """Serialize images, ROIs, and canonical source evidence once."""

        return {
            "images": [image.to_dict() for image in self.images],
            "rois": [roi.to_dict() for roi in self.rois],
            "source_occurrences": [
                occurrence.to_dict() for occurrence in self.source_occurrences
            ],
            "build_issues": [issue.to_dict() for issue in self.build_issues],
            "profile_contract": self.profile_contract.to_dict(),
        }


@dataclass(frozen=True)
class EmbedClinicalImageGraph:
    """Cross-table exam/image containment and reconciliation result."""

    exams: Tuple[Exam, ...]
    images: Tuple[MammogramImage, ...]
    containment_links: Tuple[ExamImageContainmentLink, ...]
    unmatched_images: Tuple[UnmatchedImage, ...]
    unmatched_exams: Tuple[Exam, ...]
    build_issues: Tuple[BuildIssue, ...]
    clinical_profile_contract: ProfileContract
    image_profile_contract: ProfileContract

    def __post_init__(self) -> None:
        for attribute in (
            "exams",
            "images",
            "containment_links",
            "unmatched_images",
            "unmatched_exams",
            "build_issues",
        ):
            object.__setattr__(self, attribute, tuple(getattr(self, attribute)))
        _require_instances(self.exams, Exam, "exams")
        _require_instances(self.images, MammogramImage, "images")
        _require_instances(
            self.containment_links,
            ExamImageContainmentLink,
            "containment_links",
        )
        _require_instances(self.unmatched_images, UnmatchedImage, "unmatched_images")
        _require_instances(self.unmatched_exams, Exam, "unmatched_exams")
        _require_instances(self.build_issues, BuildIssue, "build_issues")
        if not isinstance(self.clinical_profile_contract, ProfileContract):
            raise TypeError("clinical_profile_contract must be a ProfileContract")
        if not isinstance(self.image_profile_contract, ProfileContract):
            raise TypeError("image_profile_contract must be a ProfileContract")
        if self.clinical_profile_contract.kind is not ProfileKind.CLINICAL:
            raise ValueError("Graph clinical contract must have clinical kind")
        if self.image_profile_contract.kind is not ProfileKind.IMAGE:
            raise ValueError("Graph image contract must have image kind")
        graph_exams = (*self.exams, *self.unmatched_exams)
        clinical_sources = list(_exam_clinical_sources(graph_exams))
        _require_profile_sources(
            clinical_sources,
            self.clinical_profile_contract.source_profile,
            "Graph clinical evidence",
        )
        image_sources = list(_image_sources(self.images))
        image_sources.extend(_image_sources(_exam_images(graph_exams)))
        for link in self.containment_links:
            image_sources.extend(link.sources)
            image_sources.extend(_image_sources((link.image,)))
        for unmatched in self.unmatched_images:
            image_sources.extend(unmatched.sources)
            image_sources.extend(_image_sources((unmatched.image,)))
        image_sources.extend(issue.source for issue in self.build_issues)
        _require_profile_sources(
            image_sources,
            self.image_profile_contract.source_profile,
            "Graph image and reconciliation evidence",
        )

        exam_by_accession = _unique_by_key(
            self.exams,
            lambda exam: exam.accession_number,
            "exam accession_number",
        )
        image_by_id = _unique_by_key(
            self.images,
            lambda image: image.image_id,
            "image_id",
        )
        link_by_key = _unique_by_key(
            self.containment_links,
            lambda link: (link.accession_number, link.image.image_id),
            "containment link",
        )
        unmatched_by_id = _unique_by_key(
            self.unmatched_images,
            lambda unmatched: unmatched.image.image_id,
            "unmatched image",
        )

        linked_image_ids = set()
        links_by_accession: dict[str, list[ExamImageContainmentLink]] = {
            accession: [] for accession in exam_by_accession
        }
        for link in link_by_key.values():
            if link.image.image_id in linked_image_ids:
                raise ValueError("each graph image may have only one containment link")
            graph_image = image_by_id.get(link.image.image_id)
            if graph_image is not link.image:
                raise ValueError(
                    "containment link image must be the exact graph-owned image"
                )
            exam = exam_by_accession.get(link.accession_number)
            if exam is None:
                raise ValueError("containment link accession must resolve to an exam")
            image_has_id = _has_populated_text(link.image.patient_id)
            exam_has_id = _has_populated_text(exam.patient_id)
            if image_has_id and exam_has_id:
                if link.image.patient_id != exam.patient_id:
                    raise ValueError("populated patient identity mismatch cannot link")
                expected_status = PatientIdentityCheckStatus.VERIFIED
            else:
                expected_status = PatientIdentityCheckStatus.UNVERIFIED
            if link.patient_identity_status is not expected_status:
                raise ValueError("containment patient identity status is inconsistent")
            linked_image_ids.add(link.image.image_id)
            links_by_accession[link.accession_number].append(link)

        for unmatched in unmatched_by_id.values():
            graph_image = image_by_id.get(unmatched.image.image_id)
            if graph_image is not unmatched.image:
                raise ValueError(
                    "unmatched image must be the exact graph-owned image"
                )
        unmatched_image_ids = set(unmatched_by_id)
        if linked_image_ids & unmatched_image_ids:
            raise ValueError("matched and unmatched image classifications must be disjoint")
        if linked_image_ids | unmatched_image_ids != set(image_by_id):
            raise ValueError("every graph image must be classified exactly once")

        for unmatched in unmatched_by_id.values():
            accession = unmatched.image.accession_number
            has_accession = _has_populated_text(accession)
            if unmatched.reason is UnmatchedImageReason.MISSING_ACCESSION:
                if has_accession:
                    raise ValueError(
                        "MISSING_ACCESSION requires an absent image accession"
                    )
            elif (
                unmatched.reason
                is UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH
            ):
                if not has_accession or accession in exam_by_accession:
                    raise ValueError(
                        "ACCESSION_NOT_IN_CLINICAL_GRAPH requires a populated "
                        "accession absent from graph exams"
                    )
            else:
                exam = exam_by_accession.get(accession) if has_accession else None
                if (
                    exam is None
                    or not _has_populated_text(unmatched.image.patient_id)
                    or not _has_populated_text(exam.patient_id)
                    or unmatched.image.patient_id == exam.patient_id
                ):
                    raise ValueError(
                        "PATIENT_IDENTITY_CONFLICT requires a resolved accession "
                        "and different populated patient identities"
                    )

        for exam in self.exams:
            links = links_by_accession[exam.accession_number]
            expected_images = [link.image for link in links]
            if not _same_objects(exam.images, expected_images):
                raise ValueError("exam image hierarchy must exactly match containment links")
            for laterality, side in exam.breast_sides.items():
                if (
                    laterality not in (Laterality.LEFT, Laterality.RIGHT)
                    or not isinstance(side, BreastSide)
                    or side.accession_number != exam.accession_number
                    or side.laterality is not laterality
                ):
                    raise ValueError("exam breast-side hierarchy is inconsistent")
            for laterality in (Laterality.LEFT, Laterality.RIGHT):
                side = exam.breast_sides.get(laterality)
                actual = [] if side is None else side.images
                expected = [
                    link.image for link in links if link.image.laterality is laterality
                ]
                if not _same_objects(actual, expected):
                    raise ValueError(
                        "breast-side image hierarchy must exactly match containment links"
                    )

        expected_unmatched_exams = [
            exam
            for exam in self.exams
            if not links_by_accession[exam.accession_number]
        ]
        if not _same_objects(self.unmatched_exams, expected_unmatched_exams):
            raise ValueError("unmatched_exams must exactly match exams without links")

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
            "containment_links": [
                link.to_dict() for link in self.containment_links
            ],
            "unmatched_images": [
                unmatched.to_dict() for unmatched in self.unmatched_images
            ],
            "unmatched_exam_references": [
                exam.accession_number for exam in self.unmatched_exams
            ],
            "build_issues": [issue.to_dict() for issue in self.build_issues],
            "clinical_profile_contract": self.clinical_profile_contract.to_dict(),
            "image_profile_contract": self.image_profile_contract.to_dict(),
        }


@dataclass(frozen=True)
class FindingImageCandidateProjection:
    """Candidate images selected without asserting clinical attribution."""

    finding: Finding
    candidates: Tuple[FindingImageCandidate, ...]
    selection_basis: str = field(
        default="assembled_exam_unilateral_side_membership",
        init=False,
    )
    status: AttributionStatus = field(
        default=AttributionStatus.CANDIDATE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.finding, Finding):
            raise TypeError("finding must be a Finding")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        _require_instances(self.candidates, FindingImageCandidate, "candidates")
        seen_image_ids = set()
        compatible_lateralities = set(self.finding.laterality.expand())
        for candidate in self.candidates:
            image = candidate.image
            if image.image_id in seen_image_ids:
                raise ValueError("candidates must contain unique image IDs")
            seen_image_ids.add(image.image_id)
            if image.accession_number != self.finding.accession_number:
                raise ValueError("candidate accession must match finding accession")
            if (
                not image.laterality.is_unilateral
                or image.laterality not in compatible_lateralities
            ):
                raise ValueError(
                    "candidate image laterality must be unilateral and compatible"
                )

    def to_dict(self) -> dict[str, object]:
        """Serialize finding and candidate membership through references."""

        return {
            "finding_reference": {
                "accession_number": self.finding.accession_number,
                "finding_number": self.finding.finding_number,
            },
            "candidates": [candidate.to_dict() for candidate in self.candidates],
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
    finding_location: Tuple[str, ...] = ()
    finding_depth: Tuple[str, ...] = ()
    finding_distance: Tuple[str, ...] = ()
    assessment: Tuple[str, ...] = ()
    recommendation: Tuple[str, ...] = ()
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
    derived_image_type: Tuple[str, ...] = ()
    height: Tuple[str, ...] = ()
    width: Tuple[str, ...] = ()
    frame_count: Tuple[str, ...] = ()
    study_uid: Tuple[str, ...] = ("StudyInstanceUID", "study_instance_uid")
    series_uid: Tuple[str, ...] = ()
    sop_uid: Tuple[str, ...] = ()
    patient_orientation: Tuple[str, ...] = ()
    coordinate_frame_id: Tuple[str, ...] = ()
    roi_source: Tuple[str, ...] = ()
    roi_confidence: Tuple[str, ...] = ("roi_confidence", "ROI_confidence")
    roi_coordinates: Tuple[str, ...] = ()
    roi_frames: Tuple[str, ...] = ()
    roi_depth_derived: Tuple[str, ...] = ()
    y_min: Tuple[str, ...] = ("y_min", "YMin")
    x_min: Tuple[str, ...] = ("x_min", "XMin")
    y_max: Tuple[str, ...] = ("y_max", "YMax")
    x_max: Tuple[str, ...] = ("x_max", "XMax")


@dataclass(frozen=True)
class _FindingAnatomyObservation:
    position: Optional[AnatomicalPosition]
    location_codes: dict[str, Any]
    depth_codes: dict[str, Any]
    distance_codes: dict[str, Any]
    evidence: Tuple[FindingNormalizationEvidence, ...]
    warnings: Tuple[FindingNormalizationWarning, ...]
    issues: Tuple[BuildIssue, ...]


@dataclass
class _ClinicalBuildState:
    patients: dict[str, Patient]
    patient_attribute_observations: list[PatientAttributeObservation]
    exams: dict[str, Exam]
    exam_attribute_observations: list[ExamAttributeObservation]
    procedure_registry: dict[ProcedureIdentity, Procedure]
    finding_procedure_links: list[FindingProcedureLink]
    unresolved_procedure_occurrences: list[UnresolvedProcedureOccurrence]
    pathology_observations: list[PathologyObservation]
    pathology_diagnoses: list[PathologyDiagnosis]
    pathology_attribution_links: list[PathologyAttributionLink]


_MISSING = object()
_INVALID_EXACT_INTEGER = object()
_INTERNAL_V2_ROI_DEPTH_DERIVATION_METHOD = "internal-v2-roi-depth-derivation"


def _column_aliases(config: Optional[EmbedColumnConfig]) -> _ColumnAliases:
    columns = config or default_embed_columns()
    clinical = profile_source_field_candidates(columns, ProfileKind.CLINICAL)
    image = profile_source_field_candidates(columns, ProfileKind.IMAGE)
    return _ColumnAliases(
        patient_id=clinical["patient_id"],
        birth_year=clinical["birth_year"],
        sex=clinical["sex"],
        accession=clinical["accession"],
        exam_date=clinical["study_date"],
        exam_description=clinical["exam_description"],
        finding_number=clinical["finding_number"],
        clinical_side=clinical["finding_laterality"],
        finding_location=clinical["finding_location"],
        finding_depth=clinical["finding_depth"],
        finding_distance=clinical["finding_distance"],
        assessment=clinical["finding_assessment"],
        recommendation=clinical["finding_recommendation"],
        procedure_type=clinical["procedure_type"],
        procedure_date=clinical["procedure_date"],
        procedure_laterality=clinical["procedure_laterality"],
        pathology_severity=clinical["pathology_severity"],
        pathology_report_date=clinical["pathology_report_date"],
        pathology_descriptor_prefix=columns.pathology_diagnosis_prefix,
        image_id=image["image_id"],
        image_side=image["image_laterality"],
        view_position=image["image_view"],
        modality=image["image_modality"],
        derived_image_type=image["derived_image_type"],
        height=image["image_height"],
        width=image["image_width"],
        frame_count=image["image_frames"],
        series_uid=image["series_id"],
        sop_uid=image["sop_instance_uid"],
        patient_orientation=image["image_orientation"],
        coordinate_frame_id=image["acquisition_group_id"],
        roi_source=image["roi_source"],
        roi_coordinates=_aliases(columns.roi_coords, "roi_coordinates"),
        roi_frames=image["roi_frames"],
        roi_depth_derived=image["roi_depth_derived"],
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
    source_profile: str = INTERNAL_V2_PROFILE,
    source_table: str = "magview",
    profile_contract: Optional[ProfileContract] = None,
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
    resolved_profile_contract = profile_contract_for(
        source_profile,
        profile_contract,
        expected_kind=ProfileKind.CLINICAL,
    )
    resolved_columns = columns or default_embed_columns()
    validate_contract_source_fields(resolved_profile_contract, resolved_columns)
    column_aliases = _column_aliases(resolved_columns)
    patients: dict[str, Patient] = {}
    patient_attribute_observations: list[PatientAttributeObservation] = []
    exams: dict[str, Exam] = {}
    exam_attribute_observations: list[ExamAttributeObservation] = []
    procedure_registry: dict[ProcedureIdentity, Procedure] = {}
    finding_procedure_links: list[FindingProcedureLink] = []
    unresolved_procedure_occurrences: list[UnresolvedProcedureOccurrence] = []
    pathology_observations: list[PathologyObservation] = []
    pathology_diagnoses: list[PathologyDiagnosis] = []
    pathology_attribution_links: list[PathologyAttributionLink] = []
    source_occurrences: list[SourceOccurrence] = []
    build_issues: list[BuildIssue] = []
    state = _ClinicalBuildState(
        patients=patients,
        patient_attribute_observations=patient_attribute_observations,
        exams=exams,
        exam_attribute_observations=exam_attribute_observations,
        procedure_registry=procedure_registry,
        finding_procedure_links=finding_procedure_links,
        unresolved_procedure_occurrences=unresolved_procedure_occurrences,
        pathology_observations=pathology_observations,
        pathology_diagnoses=pathology_diagnoses,
        pathology_attribution_links=pathology_attribution_links,
    )

    for row_ordinal, row in enumerate(rows):
        locator = SourceLocator(
            scope=resolved_source_scope,
            scope_kind=scope_kind,
            source_profile=source_profile,
            source_table=source_table,
            row_ordinal=row_ordinal,
        )
        row_issues = _build_clinical_row(
            row,
            locator,
            column_aliases,
            policy,
            state,
        )
        resolution_state = (
            ResolutionState.UNRESOLVED
            if any(issue.severity is IssueSeverity.ERROR for issue in row_issues)
            else ResolutionState.RESOLVED
        )
        source_occurrences.append(
            SourceOccurrence(
                locator=locator,
                raw_values=dict(row),
                resolution_state=resolution_state,
                issues=row_issues,
            )
        )
        build_issues.extend(row_issues)

    ordered_patients = tuple(patients.values())
    ordered_exams = tuple(exams.values())
    ordered_findings = tuple(finding for exam in ordered_exams for finding in exam.findings)
    ordered_interpretations = tuple(
        finding.interpretation
        for finding in ordered_findings
        if finding.interpretation is not None
    )
    ordered_sides = tuple(
        side for exam in ordered_exams for side in exam.breast_sides.values()
    )
    return EmbedClinicalTables(
        patients=ordered_patients,
        patient_attribute_observations=tuple(patient_attribute_observations),
        exams=ordered_exams,
        exam_attribute_observations=tuple(exam_attribute_observations),
        findings=ordered_findings,
        interpretations=ordered_interpretations,
        breast_sides=ordered_sides,
        procedures=tuple(procedure_registry.values()),
        finding_procedure_links=tuple(finding_procedure_links),
        unresolved_procedure_occurrences=tuple(unresolved_procedure_occurrences),
        pathology_observations=tuple(pathology_observations),
        pathology_diagnoses=tuple(pathology_diagnoses),
        pathology_attribution_links=tuple(pathology_attribution_links),
        source_occurrences=tuple(source_occurrences),
        build_issues=tuple(build_issues),
        profile_contract=resolved_profile_contract,
    )


def _build_clinical_row(
    row: Row,
    locator: SourceLocator,
    columns: _ColumnAliases,
    policy: BuildPolicy,
    state: _ClinicalBuildState,
) -> Tuple[BuildIssue, ...]:
    """Project one row while accumulating all issues for one ledger entry."""

    issues: list[BuildIssue] = []
    row_observations, row_diagnosis, pathology_issues = _pathology_from_row(
        row,
        columns,
        locator,
    )
    _review_row_issues(policy, pathology_issues)
    issues.extend(pathology_issues)
    state.pathology_observations.extend(row_observations)
    if row_diagnosis is not None:
        state.pathology_diagnoses.append(row_diagnosis)

    patient_id = _string_value(_get(row, columns.patient_id))
    accession = _string_value(_get(row, columns.accession))
    finding_number = _string_value(_get(row, columns.finding_number))
    identity_issues = _clinical_identity_issues(
        patient_id=patient_id,
        accession=accession,
        finding_number=finding_number,
        locator=locator,
        columns=columns,
    )
    parent_identity_issues = tuple(
        issue
        for issue in identity_issues
        if issue.code != "missing_finding_identity"
    )
    if parent_identity_issues:
        _review_row_issues(policy, identity_issues)
        issues.extend(identity_issues)
        return tuple(issues)

    assert patient_id is not None
    assert accession is not None
    existing_exam = state.exams.get(accession)
    if existing_exam is not None and existing_exam.patient_id != patient_id:
        conflict_issues = (
            BuildIssue(
                code="conflicting_accession_patient_identity",
                message="An accession cannot resolve to multiple patient identities.",
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "accession_number": accession,
                    "retained_patient_id": existing_exam.patient_id,
                    "observed_patient_id": patient_id,
                },
            ),
        ) + tuple(
            issue
            for issue in identity_issues
            if issue.code == "missing_finding_identity"
        )
        _review_row_issues(policy, conflict_issues)
        issues.extend(conflict_issues)
        return tuple(issues)

    missing_finding_issues = tuple(
        issue
        for issue in identity_issues
        if issue.code == "missing_finding_identity"
    )
    _review_row_issues(policy, missing_finding_issues)
    issues.extend(missing_finding_issues)

    attribute_observations, attribute_issues = _patient_attributes_from_row(
        row,
        columns,
        patient_id,
        locator,
    )
    _review_row_issues(policy, attribute_issues)
    issues.extend(attribute_issues)

    exam_observations = _exam_attributes_from_row(
        row,
        columns,
        accession,
        locator,
    )
    exam_attribute_issues, exam_attribute_fills = _reconcile_exam_attributes(
        existing_exam,
        exam_observations,
        locator,
    )
    _review_row_issues(policy, exam_attribute_issues)
    issues.extend(exam_attribute_issues)

    patient = state.patients.setdefault(patient_id, Patient(patient_id=patient_id))
    for observation in attribute_observations:
        owned_observation = patient.add_attribute_observation(observation)
        state.patient_attribute_observations.append(owned_observation)
    exam = existing_exam
    if exam is None:
        exam = Exam(
            accession_number=accession,
            patient_id=patient_id,
        )
        state.exams[accession] = patient.add_exam(exam)
    else:
        patient.add_exam(exam)
    for attribute, value in exam_attribute_fills:
        setattr(exam, attribute.value, value)
    for observation in exam_observations:
        owned_observation = exam.add_attribute_observation(observation)
        state.exam_attribute_observations.append(owned_observation)

    if finding_number is None:
        (
            resolved_procedure,
            _,
            unresolved_procedure,
            procedure_issues,
        ) = _procedure_from_row(
            row,
            columns,
            patient_id,
            accession,
            None,
            locator,
            state.procedure_registry,
            policy,
        )
        issues.extend(procedure_issues)
        if unresolved_procedure is not None:
            state.unresolved_procedure_occurrences.append(unresolved_procedure)
        targets = [
            ClinicalObjectReference(ClinicalObjectKind.PATIENT, (patient_id,)),
            ClinicalObjectReference(ClinicalObjectKind.EXAM, (accession,)),
        ]
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
        state.pathology_attribution_links.extend(
            _pathology_attribution_links(
                observations=row_observations,
                diagnosis=row_diagnosis,
                targets=tuple(targets),
                locator=locator,
            )
        )
        return tuple(issues)

    side = _clinical_laterality(_get(row, columns.clinical_side))
    anatomy = _finding_anatomy_from_row(
        row,
        columns,
        side,
        locator,
        policy,
    )
    issues.extend(anatomy.issues)
    row_interpretation = _interpretation_from_row(
        row,
        columns,
        accession,
        finding_number,
        locator,
    )
    existing_finding = exam.finding_index.get((accession, finding_number))
    finding = Finding(
        accession_number=accession,
        laterality=side,
        finding_number=finding_number,
        finding_type=_string_value(_get(row, columns.finding_type)),
        interpretation=row_interpretation,
        anatomical_position=anatomy.position,
        source_location_codes=anatomy.location_codes,
        source_depth_codes=anatomy.depth_codes,
        source_distance_codes=anatomy.distance_codes,
        normalization_evidence=list(anatomy.evidence),
        normalization_warnings=list(anatomy.warnings),
    )
    if existing_finding is not None:
        finding_attribute_issues = _finding_attribute_issues(
            existing_finding,
            finding,
            locator,
        )
        _review_row_issues(policy, finding_attribute_issues)
        issues.extend(finding_attribute_issues)
        for issue in finding_attribute_issues:
            attribute = issue.context["attribute"]
            setattr(finding, attribute, getattr(existing_finding, attribute))
    finding = exam.add_finding(finding)
    if existing_finding is not None:
        anatomy_issues = _merge_finding_anatomy(
            existing_finding,
            anatomy,
            locator,
            policy,
        )
        issues.extend(anatomy_issues)
        merged_interpretation, interpretation_issues = _merge_interpretations(
            existing_finding.interpretation,
            row_interpretation,
            locator,
            policy,
        )
        finding.interpretation = merged_interpretation
        issues.extend(interpretation_issues)

    (
        resolved_procedure,
        link,
        unresolved_procedure,
        procedure_issues,
    ) = _procedure_from_row(
        row,
        columns,
        patient_id,
        accession,
        finding.finding_number,
        locator,
        state.procedure_registry,
        policy,
    )
    issues.extend(procedure_issues)
    if link is not None:
        state.finding_procedure_links.append(link)
    if unresolved_procedure is not None:
        state.unresolved_procedure_occurrences.append(unresolved_procedure)

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
    state.pathology_attribution_links.extend(
        _pathology_attribution_links(
            observations=row_observations,
            diagnosis=row_diagnosis,
            targets=tuple(targets),
            locator=locator,
        )
    )
    return tuple(issues)


def _review_row_issues(
    policy: BuildPolicy,
    issues: Iterable[BuildIssue],
) -> None:
    for issue in issues:
        policy.handle_issue(issue)


def _patient_attributes_from_row(
    row: Row,
    columns: _ColumnAliases,
    patient_id: str,
    locator: SourceLocator,
) -> Tuple[Tuple[PatientAttributeObservation, ...], Tuple[BuildIssue, ...]]:
    """Project physically present patient attributes with exam-date context."""

    matched_attributes = []
    for attribute, aliases in (
        (PatientAttributeName.SEX, columns.sex),
        (PatientAttributeName.BIRTH_YEAR, columns.birth_year),
    ):
        source_field, raw_value = _matched_value(row, aliases)
        if source_field is not None:
            matched_attributes.append((attribute, source_field, raw_value))
    if not matched_attributes:
        return (), ()

    context_date, context_issue = _patient_attribute_context_date(
        row,
        columns.exam_date,
        patient_id,
        tuple(attribute for attribute, _, _ in matched_attributes),
        locator,
    )
    issues = [context_issue] if context_issue is not None else []
    observations = []
    for attribute, source_field, raw_value in matched_attributes:
        if attribute is PatientAttributeName.SEX:
            value = (
                None
                if _is_attributed_value_blank(raw_value)
                else str(raw_value).strip()
            )
        elif _is_explicit_patient_attribute_null(raw_value):
            value = None
        else:
            value = _normalize_exact_integer_source_value(raw_value)
            if value is _INVALID_EXACT_INTEGER:
                issues.append(
                    BuildIssue(
                        code="invalid_patient_attribute_value",
                        message=(
                            "Populated birth_year patient observation must "
                            "represent an exact finite integer."
                        ),
                        severity=IssueSeverity.ERROR,
                        source=locator,
                        context={
                            "patient_id": patient_id,
                            "attribute": attribute.value,
                            "source_field": source_field,
                            "raw_value": raw_value,
                        },
                    )
                )
                continue
        observations.append(
            PatientAttributeObservation(
                patient_id=patient_id,
                attribute=attribute,
                value=value,
                source=locator,
                context_date=context_date,
                time_basis=PatientObservationTimeBasis.EXAM_DATE_CONTEXT,
            )
        )
    return tuple(observations), tuple(issues)


def _exam_attributes_from_row(
    row: Row,
    columns: _ColumnAliases,
    accession_number: str,
    locator: SourceLocator,
) -> Tuple[ExamAttributeObservation, ...]:
    observations = []
    for attribute, aliases in (
        (ExamAttributeName.EXAM_DATE, columns.exam_date),
        (ExamAttributeName.DESCRIPTION, columns.exam_description),
    ):
        source_field, raw_value = _matched_value(row, aliases)
        if source_field is None:
            continue
        value = (
            None
            if _is_attributed_value_blank(raw_value)
            else str(raw_value).strip()
        )
        observations.append(
            ExamAttributeObservation(
                accession_number=accession_number,
                attribute=attribute,
                value=value,
                source=locator,
            )
        )
    return tuple(observations)


def _reconcile_exam_attributes(
    retained_exam: Optional[Exam],
    observations: Tuple[ExamAttributeObservation, ...],
    locator: SourceLocator,
) -> Tuple[
    Tuple[BuildIssue, ...],
    Tuple[Tuple[ExamAttributeName, str], ...],
]:
    issues = []
    fills = []
    for observation in observations:
        retained_value = (
            getattr(retained_exam, observation.attribute.value)
            if retained_exam is not None
            else None
        )
        if retained_value is None:
            if observation.value is not None:
                fills.append((observation.attribute, observation.value))
            continue
        if observation.value is None or retained_value == observation.value:
            continue
        supporting_sources = tuple(
            item.source
            for item in retained_exam.attribute_observations
            if item.attribute is observation.attribute
            and item.value == retained_value
        )
        issues.append(
            BuildIssue(
                code="conflicting_exam_attribute",
                message=(
                    "Repeated rows contain conflicting populated invariant "
                    f"Exam {observation.attribute.value} values."
                ),
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "accession_number": retained_exam.accession_number,
                    "attribute": observation.attribute.value,
                    "retained": retained_value,
                    "observed": observation.value,
                    "retained_supporting_sources": [
                        source.to_dict() for source in supporting_sources
                    ],
                },
            )
        )
    return tuple(issues), tuple(fills)


def _patient_attribute_context_date(
    row: Row,
    aliases: Tuple[str, ...],
    patient_id: str,
    attributes: Tuple[PatientAttributeName, ...],
    locator: SourceLocator,
) -> Tuple[Optional[date], Optional[BuildIssue]]:
    source_field, raw_value = _matched_value(row, aliases)
    if source_field is None or _is_attributed_value_blank(raw_value):
        return None, None
    parsed = _parse_patient_context_date(raw_value)
    if parsed is not None:
        return parsed, None
    return (
        None,
        BuildIssue(
            code="invalid_patient_attribute_context_date",
            message=(
                "Patient attribute exam-date context is populated but cannot "
                "be parsed as an ISO or compact calendar date."
            ),
            severity=IssueSeverity.ERROR,
            source=locator,
            context={
                "patient_id": patient_id,
                "attributes": [attribute.value for attribute in attributes],
                "source_field": source_field,
                "raw_value": raw_value,
            },
        ),
    )


def _parse_patient_context_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    text = str(value).strip()
    try:
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        return date.fromisoformat(text)
    except ValueError:
        return None


def _is_attributed_value_blank(value: Any) -> bool:
    if _is_blank(value):
        return True
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        return False


def _is_explicit_patient_attribute_null(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in {
        "",
        "none",
        "null",
    }


def _normalize_exact_integer_source_value(value: Any) -> Any:
    if isinstance(value, bool):
        return _INVALID_EXACT_INTEGER
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        if math.isfinite(numeric) and numeric.is_integer():
            return int(numeric)
        return _INVALID_EXACT_INTEGER
    if isinstance(value, str):
        try:
            numeric_text = Decimal(value.strip())
        except InvalidOperation:
            return _INVALID_EXACT_INTEGER
        if numeric_text.is_finite() and numeric_text == numeric_text.to_integral():
            return int(numeric_text)
    return _INVALID_EXACT_INTEGER


def _finding_attribute_issues(
    retained: Finding,
    observed: Finding,
    locator: SourceLocator,
) -> Tuple[BuildIssue, ...]:
    issues = []
    for attribute in ("laterality", "finding_type"):
        retained_value = getattr(retained, attribute)
        observed_value = getattr(observed, attribute)
        if (
            retained_value is None
            or observed_value is None
            or retained_value == observed_value
        ):
            continue
        issues.append(
            BuildIssue(
                code="conflicting_finding_attribute",
                message=(
                    "Repeated rows contain conflicting populated Finding "
                    f"{attribute} values."
                ),
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "accession_number": retained.accession_number,
                    "finding_number": retained.finding_number,
                    "attribute": attribute,
                    "retained": getattr(retained_value, "value", retained_value),
                    "observed": getattr(observed_value, "value", observed_value),
                },
            )
        )
    return tuple(issues)


def _interpretation_from_row(
    row: Row,
    columns: _ColumnAliases,
    accession_number: str,
    finding_number: str,
    locator: SourceLocator,
) -> Optional[ImagingInterpretation]:
    assessment = _get(row, columns.assessment)
    recommendation = _get(row, columns.recommendation)
    if assessment is _MISSING and recommendation is _MISSING:
        return None
    return ImagingInterpretation(
        accession_number=accession_number,
        finding_number=finding_number,
        sources=(locator,),
        assessment=_assessment_value(assessment, locator.source_profile),
        assessment_availability=(
            AvailabilityState.UNAVAILABLE
            if assessment is _MISSING
            else AvailabilityState.BOUND
        ),
        recommendation=_string_value(recommendation),
        recommendation_availability=(
            AvailabilityState.UNAVAILABLE
            if recommendation is _MISSING
            else AvailabilityState.BOUND
        ),
    )


def _assessment_value(value: Any, source_profile: str) -> Optional[str]:
    """Normalize governed Internal V2 assessment codes for semantic comparison."""

    text = _string_value(value)
    if text is None or source_profile != INTERNAL_V2_PROFILE:
        return text
    return text.strip().upper()


def _finding_anatomy_from_row(
    row: Row,
    columns: _ColumnAliases,
    laterality: Laterality,
    locator: SourceLocator,
    policy: BuildPolicy,
) -> _FindingAnatomyObservation:
    side_field, side_value = _matched_value(row, columns.clinical_side)
    location_field, location_value = _matched_value(row, columns.finding_location)
    depth_field, depth_value = _matched_value(row, columns.finding_depth)
    distance_field, distance_value = _matched_value(row, columns.finding_distance)
    location_codes = (
        {location_field: location_value} if location_field is not None else {}
    )
    depth_codes = {depth_field: depth_value} if depth_field is not None else {}
    distance_codes = (
        {distance_field: distance_value} if distance_field is not None else {}
    )
    evidence = []
    warnings = []
    issues = []
    position = None

    has_location = location_field is not None and not _is_blank(location_value)
    has_depth = depth_field is not None and not _is_blank(depth_value)
    if has_location or has_depth:
        normalized = normalize_magview_location(
            laterality=laterality,
            location_code=location_value if has_location else None,
            depth_code=depth_value if has_depth else None,
        )
        source_fields = {
            "location_code": (location_field, location_value),
            "depth_code": (depth_field, depth_value),
            "laterality": (side_field, side_value),
        }
        for item in normalized.evidence:
            source_field, raw_value = source_fields[item.field]
            if source_field is None:
                continue
            translated = FindingNormalizationEvidence(
                source=locator,
                source_field=source_field,
                raw_value=raw_value,
                normalized_kind=item.normalized_kind,
                normalized_value=(
                    item.normalized_value if laterality.is_unilateral else None
                ),
            )
            if translated not in evidence:
                evidence.append(translated)
        for item in normalized.warnings:
            source_field, raw_value = source_fields.get(
                item.field,
                (None, item.raw_value),
            )
            translated = FindingNormalizationWarning(
                source=locator,
                source_field=source_field,
                raw_value=raw_value,
                code=item.code,
                message=item.message,
            )
            if translated not in warnings:
                warnings.append(translated)
        if laterality.is_unilateral:
            position = normalized.position
        else:
            position = AnatomicalPosition(
                laterality=laterality,
                quadrant=Quadrant(laterality=laterality),
            )

    distance = None
    if distance_field is not None and not _is_blank(distance_value):
        try:
            if isinstance(distance_value, bool):
                raise ValueError
            distance = float(distance_value)
            if not math.isfinite(distance) or distance < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            distance = None
            issue = BuildIssue(
                code="invalid_finding_distance",
                message=(
                    "Finding distance must be a finite, nonnegative value in "
                    "centimeters."
                ),
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "source_field": distance_field,
                    "raw_value": distance_value,
                },
            )
            policy.handle_issue(issue)
            issues.append(issue)
        evidence.append(
            FindingNormalizationEvidence(
                source=locator,
                source_field=distance_field,
                raw_value=distance_value,
                normalized_kind="distance_from_nipple_cm",
                normalized_value=distance,
            )
        )
        if position is None and distance is not None and laterality.is_unilateral:
            position = AnatomicalPosition(
                laterality=laterality,
                quadrant=Quadrant(laterality=laterality),
            )
        if position is not None and distance is not None:
            position = replace(position, distance_from_nipple_cm=distance)

    has_anatomy_input = has_location or has_depth or (
        distance_field is not None and not _is_blank(distance_value)
    )
    if (
        has_anatomy_input
        and not laterality.is_unilateral
        and not any(warning.code == "unsupported_laterality" for warning in warnings)
    ):
        warnings.append(
            FindingNormalizationWarning(
                source=locator,
                source_field=side_field,
                raw_value=side_value if side_field is not None else None,
                code="unsupported_laterality",
                message=(
                    "Finding anatomy normalization requires left or right "
                    "laterality."
                ),
            )
        )

    return _FindingAnatomyObservation(
        position=position,
        location_codes=location_codes,
        depth_codes=depth_codes,
        distance_codes=distance_codes,
        evidence=tuple(evidence),
        warnings=tuple(warnings),
        issues=tuple(issues),
    )


def _merge_finding_anatomy(
    finding: Finding,
    observed: _FindingAnatomyObservation,
    locator: SourceLocator,
    policy: BuildPolicy,
) -> Tuple[BuildIssue, ...]:
    merged_position, issues = _merge_anatomical_positions(
        finding.anatomical_position,
        observed.position,
        finding,
        locator,
    )
    for issue in issues:
        policy.handle_issue(issue)
    finding.anatomical_position = merged_position
    for retained, additions in (
        (finding.source_location_codes, observed.location_codes),
        (finding.source_depth_codes, observed.depth_codes),
        (finding.source_distance_codes, observed.distance_codes),
    ):
        for source_field, raw_value in additions.items():
            retained.setdefault(source_field, raw_value)
    for item in observed.evidence:
        if item not in finding.normalization_evidence:
            finding.normalization_evidence.append(item)
    for warning in observed.warnings:
        if warning not in finding.normalization_warnings:
            finding.normalization_warnings.append(warning)
    return issues


def _merge_anatomical_positions(
    retained: Optional[AnatomicalPosition],
    observed: Optional[AnatomicalPosition],
    finding: Finding,
    locator: SourceLocator,
) -> Tuple[Optional[AnatomicalPosition], Tuple[BuildIssue, ...]]:
    if observed is None:
        return retained, ()
    if retained is None:
        return observed, ()
    issues = []
    if retained.laterality is not observed.laterality:
        issues.append(
            _anatomy_conflict_issue(
                finding,
                locator,
                "laterality",
                retained.laterality.value,
                observed.laterality.value,
            )
        )
        return retained, tuple(issues)

    def merge_value(
        attribute: str,
        current: Any,
        candidate: Any,
        missing: Any,
    ) -> Any:
        if candidate is missing:
            return current
        if current is missing:
            return candidate
        if current != candidate:
            issues.append(
                _anatomy_conflict_issue(
                    finding,
                    locator,
                    attribute,
                    getattr(current, "value", current),
                    getattr(candidate, "value", candidate),
                )
            )
        return current

    quadrant = Quadrant(
        laterality=retained.laterality,
        ml=merge_value(
            "quadrant.ml",
            retained.quadrant.ml,
            observed.quadrant.ml,
            MedialLateralAxis.UNKNOWN,
        ),
        si=merge_value(
            "quadrant.si",
            retained.quadrant.si,
            observed.quadrant.si,
            SuperiorInferiorAxis.UNKNOWN,
        ),
        depth=merge_value(
            "quadrant.depth",
            retained.quadrant.depth,
            observed.quadrant.depth,
            DepthThird.UNKNOWN,
        ),
    )
    return (
        AnatomicalPosition(
            laterality=retained.laterality,
            quadrant=quadrant,
            clock_position=merge_value(
                "clock_position",
                retained.clock_position,
                observed.clock_position,
                None,
            ),
            location_category=merge_value(
                "location_category",
                retained.location_category,
                observed.location_category,
                None,
            ),
            distance_from_nipple_cm=merge_value(
                "distance_from_nipple_cm",
                retained.distance_from_nipple_cm,
                observed.distance_from_nipple_cm,
                None,
            ),
        ),
        tuple(issues),
    )


def _anatomy_conflict_issue(
    finding: Finding,
    locator: SourceLocator,
    attribute: str,
    retained: Any,
    observed: Any,
) -> BuildIssue:
    return BuildIssue(
        code="conflicting_finding_anatomical_value",
        message="Repeated rows contain conflicting normalized finding anatomy.",
        severity=IssueSeverity.ERROR,
        source=locator,
        context={
            "accession_number": finding.accession_number,
            "finding_number": finding.finding_number,
            "attribute": attribute,
            "retained": retained,
            "observed": observed,
        },
    )


def _merge_interpretations(
    retained: Optional[ImagingInterpretation],
    observed: Optional[ImagingInterpretation],
    locator: SourceLocator,
    policy: BuildPolicy,
) -> Tuple[Optional[ImagingInterpretation], Tuple[BuildIssue, ...]]:
    if observed is None:
        return retained, ()
    if retained is None:
        return observed, ()
    if (
        retained.accession_number,
        retained.finding_number,
    ) != (
        observed.accession_number,
        observed.finding_number,
    ):
        raise ValueError("Interpretation identities must match before merge")

    values = {
        "assessment": retained.assessment,
        "assessment_availability": retained.assessment_availability,
        "recommendation": retained.recommendation,
        "recommendation_availability": retained.recommendation_availability,
    }
    issues = []
    for attribute in ("assessment", "recommendation"):
        availability_attribute = f"{attribute}_availability"
        retained_value = values[attribute]
        retained_availability = values[availability_attribute]
        observed_value = getattr(observed, attribute)
        observed_availability = getattr(observed, availability_attribute)
        if (
            retained_availability is AvailabilityState.UNAVAILABLE
            and observed_availability is AvailabilityState.BOUND
        ):
            values[attribute] = observed_value
            values[availability_attribute] = AvailabilityState.BOUND
            continue
        if (
            retained_availability is AvailabilityState.BOUND
            and observed_availability is AvailabilityState.BOUND
        ):
            if retained_value is None and observed_value is not None:
                values[attribute] = observed_value
            elif (
                retained_value is not None
                and observed_value is not None
                and retained_value != observed_value
            ):
                issues.append(
                    BuildIssue(
                        code="conflicting_interpretation_attribute",
                        message=(
                            "Repeated rows contain conflicting non-null "
                            f"{attribute} values for one finding."
                        ),
                        severity=IssueSeverity.ERROR,
                        source=locator,
                        context={
                            "accession_number": retained.accession_number,
                            "finding_number": retained.finding_number,
                            "attribute": attribute,
                            "retained": retained_value,
                            "observed": observed_value,
                        },
                    )
                )

    for issue in issues:
        policy.handle_issue(issue)
    sources = tuple(dict.fromkeys((*retained.sources, *observed.sources)))
    return (
        ImagingInterpretation(
            accession_number=retained.accession_number,
            finding_number=retained.finding_number,
            sources=sources,
            assessment=values["assessment"],
            assessment_availability=values["assessment_availability"],
            recommendation=values["recommendation"],
            recommendation_availability=values["recommendation_availability"],
        ),
        tuple(issues),
    )


def build_image_tables(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
    build_policy: Optional[BuildPolicy] = None,
    source_scope: Optional[str] = None,
    source_scope_kind: SourceScopeKind = SourceScopeKind.MATERIALIZATION,
    source_profile: str = INTERNAL_V2_PROFILE,
    source_table: str = "image_metadata",
    profile_contract: Optional[ProfileContract] = None,
) -> EmbedImageTables:
    """Build reconciled images and one canonical ledger entry per input row."""

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
    resolved_profile_contract = profile_contract_for(
        source_profile,
        profile_contract,
        expected_kind=ProfileKind.IMAGE,
    )
    resolved_columns = columns or default_embed_columns()
    validate_contract_source_fields(resolved_profile_contract, resolved_columns)
    column_aliases = _column_aliases(resolved_columns)
    images: list[MammogramImage] = []
    rois: list[RegionOfInterest] = []
    roi_index_by_locator: dict[RoiLocator, int] = {}
    image_by_id: dict[str, MammogramImage] = {}
    row_states: list[_ImageRowState] = []

    for row_ordinal, row in enumerate(rows):
        raw_values = dict(row)
        locator = SourceLocator(
            scope=resolved_source_scope,
            scope_kind=scope_kind,
            source_profile=source_profile,
            source_table=source_table,
            row_ordinal=row_ordinal,
        )
        row_issues: list[BuildIssue] = []
        roi_eligible = False
        image_id, derived_sop_instance_uid = _image_identity_from_row(
            raw_values,
            column_aliases.image_id,
            resolved_columns.image_path,
        )
        if image_id is None:
            issue = BuildIssue(
                code="missing_image_identity",
                message="Image identity is required to construct image objects.",
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "logical_field": "image_id",
                    "source_columns": list(column_aliases.image_id),
                },
            )
            policy.handle_issue(issue)
            row_issues.append(issue)
        else:
            observed, metadata_issues = _image_from_row(
                raw_values,
                column_aliases,
                image_id,
                locator,
                derived_sop_instance_uid=derived_sop_instance_uid,
            )
            for issue in metadata_issues:
                policy.handle_issue(issue)
            row_issues.extend(metadata_issues)
            if observed is not None:
                retained = image_by_id.get(image_id)
                if retained is None:
                    images.append(observed)
                    image_by_id[image_id] = observed
                    roi_eligible = True
                else:
                    conflict_issues, fills = _reconcile_image_attributes(
                        retained,
                        observed,
                        locator,
                    )
                    for issue in conflict_issues:
                        policy.handle_issue(issue)
                    row_issues.extend(conflict_issues)
                    retained.add_source(locator)
                    for attribute, value, source in fills:
                        setattr(retained, attribute, value)
                        retained.attribute_sources[attribute] = source
                    roi_eligible = not conflict_issues
        row_states.append(
            _ImageRowState(
                raw_values=raw_values,
                locator=locator,
                image_id=image_id,
                issues=row_issues,
                roi_eligible=roi_eligible,
            )
        )

    # ROI semantics depend on the fully reconciled image modality and frame
    # count, so projection is deliberately deferred until all image rows have
    # contributed safe fills. Original row order remains the evidence order.
    for state in row_states:
        if not state.roi_eligible or state.image_id is None:
            continue
        image = image_by_id[state.image_id]
        row_rois, roi_issues = _rois_from_row(
            state.raw_values,
            column_aliases,
            image,
            image.coordinate_frame_id,
            state.locator,
        )
        for issue in roi_issues:
            policy.handle_issue(issue)
        state.issues.extend(roi_issues)
        duplicate_issues = _merge_row_rois(
            row_rois,
            rois,
            roi_index_by_locator,
            state.locator,
        )
        for issue in duplicate_issues:
            policy.handle_issue(issue)
        state.issues.extend(duplicate_issues)

    source_occurrences: list[SourceOccurrence] = []
    build_issues: list[BuildIssue] = []
    for state in row_states:
        resolution_state = (
            ResolutionState.UNRESOLVED
            if any(issue.severity is IssueSeverity.ERROR for issue in state.issues)
            else ResolutionState.RESOLVED
        )
        source_occurrences.append(
            SourceOccurrence(
                locator=state.locator,
                raw_values=state.raw_values,
                resolution_state=resolution_state,
                issues=tuple(state.issues),
            )
        )
        build_issues.extend(state.issues)

    return EmbedImageTables(
        images=tuple(images),
        rois=tuple(rois),
        source_occurrences=tuple(source_occurrences),
        build_issues=tuple(build_issues),
        profile_contract=resolved_profile_contract,
    )


def _image_from_row(
    row: Row,
    columns: _ColumnAliases,
    image_id: str,
    locator: SourceLocator,
    *,
    derived_sop_instance_uid: Optional[str] = None,
) -> Tuple[Optional[MammogramImage], Tuple[BuildIssue, ...]]:
    source_modality = _string_value(_get(row, columns.modality))
    derived_image_type = _string_value(_get(row, columns.derived_image_type))
    modality = ImageModality.coerce(derived_image_type)
    if modality is ImageModality.UNKNOWN:
        modality = ImageModality.coerce(source_modality)
    issues = []
    parsed_integers = {}
    for attribute, aliases in (
        ("height", columns.height),
        ("width", columns.width),
        ("frame_count", columns.frame_count),
    ):
        if attribute == "frame_count" and modality is not ImageModality.DBT:
            parsed_integers[attribute] = None
            continue
        raw_value = _get(row, aliases)
        parsed_value = _positive_image_integer(raw_value)
        if parsed_value is _INVALID_EXACT_INTEGER:
            issues.append(
                _invalid_image_attribute_issue(
                    locator,
                    image_id,
                    attribute,
                    raw_value,
                    "Image dimensions and frame counts must be positive integers.",
                )
            )
            parsed_integers[attribute] = None
        else:
            parsed_integers[attribute] = parsed_value

    raw_orientation = _get(row, columns.patient_orientation)
    try:
        patient_orientation = _patient_orientation(row, columns)
    except (TypeError, ValueError) as exc:
        issues.append(
            _invalid_image_attribute_issue(
                locator,
                image_id,
                "patient_orientation",
                raw_orientation,
                str(exc),
            )
        )
        patient_orientation = None
    if issues:
        return None, tuple(issues)

    values = {
        "image_id": image_id,
        "sources": [locator],
        "accession_number": _string_value(_get(row, columns.accession)),
        "patient_id": _string_value(_get(row, columns.patient_id)),
        "laterality": Laterality.coerce(_get(row, columns.image_side)),
        "view_position": ViewPosition.coerce(_get(row, columns.view_position)),
        "modality": modality,
        "source_modality": source_modality,
        "derived_image_type": derived_image_type,
        "height": parsed_integers["height"],
        "width": parsed_integers["width"],
        "frame_count": parsed_integers["frame_count"],
        "study_instance_uid": _string_value(_get(row, columns.study_uid)),
        "series_instance_uid": _string_value(_get(row, columns.series_uid)),
        "sop_instance_uid": (
            derived_sop_instance_uid
            or _string_value(_get(row, columns.sop_uid))
        ),
        "patient_orientation": patient_orientation,
        "coordinate_frame_id": _string_value(
            _get(row, columns.coordinate_frame_id)
        ),
    }
    values["attribute_sources"] = {
        attribute: locator
        for attribute in ("image_id", *_IMAGE_INVARIANT_ATTRIBUTES)
        if attribute == "image_id"
        or _known_image_attribute(attribute, values[attribute])
    }
    try:
        return MammogramImage(**values), ()
    except (TypeError, ValueError, OverflowError) as exc:
        return (
            None,
            (
                _invalid_image_attribute_issue(
                    locator,
                    image_id,
                    "image",
                    dict(row),
                    str(exc),
                ),
            ),
        )


def _image_identity_from_row(
    row: Row,
    image_id_columns: Tuple[str, ...],
    image_path_column: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve image identity, deriving the SOP UID from the V1c file path."""

    source_field, raw_value = _matched_value(row, image_id_columns)
    value = _string_value(raw_value)
    if value is None or source_field != image_path_column:
        return value, None
    filename = re.split(r"[\\/]", value.strip())[-1]
    sop_instance_uid = (
        filename[:-4] if filename.lower().endswith(".dcm") else filename
    )
    return sop_instance_uid or None, sop_instance_uid or None


def _positive_image_integer(value: Any) -> Any:
    if value is _MISSING or _is_blank(value):
        return None
    normalized = _normalize_exact_integer_source_value(value)
    if (
        normalized is _INVALID_EXACT_INTEGER
        or normalized <= 0
    ):
        return _INVALID_EXACT_INTEGER
    return normalized


def _invalid_image_attribute_issue(
    locator: SourceLocator,
    image_id: str,
    attribute: str,
    raw_value: Any,
    detail: str,
) -> BuildIssue:
    return BuildIssue(
        code="invalid_image_attribute",
        message=detail,
        severity=IssueSeverity.ERROR,
        source=locator,
        context={
            "image_id": image_id,
            "attribute": attribute,
            "raw_value": raw_value,
        },
    )


def _reconcile_image_attributes(
    retained: MammogramImage,
    observed: MammogramImage,
    locator: SourceLocator,
) -> Tuple[
    Tuple[BuildIssue, ...],
    Tuple[Tuple[str, Any, SourceLocator], ...],
]:
    issues = []
    fills = []
    resulting_modality = retained.modality
    if (
        resulting_modality is ImageModality.UNKNOWN
        and observed.modality is not ImageModality.UNKNOWN
    ):
        resulting_modality = observed.modality
    for attribute in _IMAGE_INVARIANT_ATTRIBUTES:
        if (
            attribute == "frame_count"
            and resulting_modality is not ImageModality.DBT
        ):
            continue
        retained_value = getattr(retained, attribute)
        observed_value = getattr(observed, attribute)
        retained_known = _known_image_attribute(attribute, retained_value)
        observed_known = _known_image_attribute(attribute, observed_value)
        if not retained_known:
            if observed_known:
                fills.append(
                    (
                        attribute,
                        observed_value,
                        observed.source_for(attribute),
                    )
                )
            continue
        if not observed_known or retained_value == observed_value:
            continue
        issues.append(
            BuildIssue(
                code="conflicting_image_attribute",
                message=(
                    "Repeated rows contain conflicting populated invariant "
                    f"image {attribute} values."
                ),
                severity=IssueSeverity.ERROR,
                source=locator,
                context={
                    "image_id": retained.image_id,
                    "attribute": attribute,
                    "retained": _serialized_image_attribute(retained_value),
                    "observed": _serialized_image_attribute(observed_value),
                    "retained_sources": [
                        source.to_dict() for source in retained.sources
                    ],
                },
            )
        )
    return tuple(issues), tuple(fills)


def _known_image_attribute(attribute: str, value: Any) -> bool:
    if value is None:
        return False
    if attribute == "laterality":
        return value is not Laterality.UNKNOWN
    if attribute == "view_position":
        return value is not ViewPosition.UNKNOWN
    if attribute == "modality":
        return value is not ImageModality.UNKNOWN
    if attribute == "derived_image_type":
        return value.strip().upper() not in {"UNKNOWN", "UNK", "N/A", "NA"}
    if attribute == "patient_orientation":
        return value.exact
    return True


def _serialized_image_attribute(value: Any) -> Any:
    if isinstance(value, (Laterality, ViewPosition, ImageModality)):
        return value.value
    if isinstance(value, PatientOrientation):
        return list(value.as_tuple())
    return value


def assemble_clinical_image_graph(
    clinical: EmbedClinicalTables,
    image_tables: EmbedImageTables,
    *,
    build_policy: Optional[BuildPolicy] = None,
) -> EmbedClinicalImageGraph:
    """Attach images to matching exams after cross-table identity checks.

    Validation is completed before any attachment so strict failures do not
    leave a partially assembled graph. Reconciliation evidence always retains
    the original image source ledger.
    """

    if not isinstance(clinical, EmbedClinicalTables):
        raise TypeError("clinical must be an EmbedClinicalTables")
    if not isinstance(image_tables, EmbedImageTables):
        raise TypeError("image_tables must be an EmbedImageTables")
    policy = build_policy or BuildPolicy()
    if not isinstance(policy, BuildPolicy):
        raise TypeError("build_policy must be a BuildPolicy")

    graph_exams = _clone_clinical_exams(clinical.exams)
    exam_by_accession = {exam.accession_number: exam for exam in graph_exams}
    attachments = []
    containment_links = []
    unmatched_images = []
    issues = []
    matched_accessions = set()

    for image in image_tables.images:
        accession = image.accession_number
        sources = tuple(image.sources)
        if not isinstance(accession, str) or not accession.strip():
            issue = BuildIssue(
                code="missing_image_accession_for_assembly",
                message="Image has no accession for clinical graph assembly.",
                severity=IssueSeverity.WARNING,
                source=image.source_for("accession_number"),
                context={"image_id": image.image_id},
            )
            policy.handle_issue(issue)
            issues.append(issue)
            unmatched_images.append(
                UnmatchedImage(
                    image=image,
                    reason=UnmatchedImageReason.MISSING_ACCESSION,
                    sources=sources,
                )
            )
            continue

        exam = exam_by_accession.get(accession)
        if exam is None:
            unmatched_images.append(
                UnmatchedImage(
                    image=image,
                    reason=UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH,
                    sources=sources,
                )
            )
            continue
        image_has_patient_id = _has_populated_text(image.patient_id)
        exam_has_patient_id = _has_populated_text(exam.patient_id)
        if (
            image_has_patient_id
            and exam_has_patient_id
            and image.patient_id != exam.patient_id
        ):
            issue = BuildIssue(
                code="conflicting_clinical_image_patient_identity",
                message=(
                    "Clinical and image patient identities conflict for one "
                    "accession."
                ),
                severity=IssueSeverity.ERROR,
                source=image.source_for("patient_id"),
                context={
                    "accession_number": accession,
                    "clinical_patient_id": exam.patient_id,
                    "image_patient_id": image.patient_id,
                    "image_id": image.image_id,
                },
            )
            policy.handle_issue(issue)
            issues.append(issue)
            unmatched_images.append(
                UnmatchedImage(
                    image=image,
                    reason=UnmatchedImageReason.PATIENT_IDENTITY_CONFLICT,
                    sources=sources,
                )
            )
            continue

        if image_has_patient_id and exam_has_patient_id:
            identity_status = PatientIdentityCheckStatus.VERIFIED
        else:
            identity_status = PatientIdentityCheckStatus.UNVERIFIED
            issue = BuildIssue(
                code="missing_patient_identity_for_reconciliation",
                message=(
                    "Clinical/image patient identity could not be verified "
                    "because one identity is missing."
                ),
                severity=IssueSeverity.WARNING,
                source=image.source_for("patient_id"),
                context={
                    "accession_number": accession,
                    "clinical_patient_id": exam.patient_id,
                    "image_patient_id": image.patient_id,
                    "image_id": image.image_id,
                },
            )
            policy.handle_issue(issue)
            issues.append(issue)

        if not image.laterality.is_unilateral:
            issue = BuildIssue(
                code="unresolved_image_laterality_for_side_containment",
                message=(
                    "Image laterality is not unilateral; image was attached "
                    "to the exam but not to a breast side."
                ),
                severity=IssueSeverity.WARNING,
                source=image.source_for("laterality"),
                context={
                    "accession_number": accession,
                    "image_id": image.image_id,
                    "image_laterality": image.laterality.value,
                },
            )
            policy.handle_issue(issue)
            issues.append(issue)

        link = ExamImageContainmentLink(
            accession_number=accession,
            image=image,
            patient_identity_status=identity_status,
            sources=sources,
        )
        attachments.append((exam, image))
        containment_links.append(link)
        matched_accessions.add(exam.accession_number)

    for exam, image in attachments:
        exam.add_image(image)

    unmatched_exams = tuple(
        exam
        for exam in graph_exams
        if exam.accession_number not in matched_accessions
    )
    return EmbedClinicalImageGraph(
        exams=graph_exams,
        images=image_tables.images,
        containment_links=tuple(containment_links),
        unmatched_images=tuple(unmatched_images),
        unmatched_exams=unmatched_exams,
        build_issues=tuple(issues),
        clinical_profile_contract=clinical.profile_contract,
        image_profile_contract=image_tables.profile_contract,
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

    link_by_image_id = {
        (link.accession_number, link.image.image_id): link
        for link in graph.containment_links
    }
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
                    link = link_by_image_id.get(
                        (exam.accession_number, image.image_id)
                    )
                    if link is None:
                        continue
                    candidates.append(
                        FindingImageCandidate(
                            image=image,
                            patient_identity_status=link.patient_identity_status,
                            sources=link.sources,
                        )
                    )
                    seen_image_ids.add(image.image_id)
            projections.append(
                FindingImageCandidateProjection(
                    finding=finding,
                    candidates=tuple(candidates),
                )
            )
    return tuple(projections)


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
    finding_number: Optional[str],
    locator: SourceLocator,
    registry: dict[ProcedureIdentity, Procedure],
    policy: BuildPolicy,
) -> Tuple[
    Optional[Procedure],
    Optional[FindingProcedureLink],
    Optional[UnresolvedProcedureOccurrence],
    Tuple[BuildIssue, ...],
]:
    procedure_id = _string_value(_get(row, columns.procedure_id))
    procedure_type = _string_value(_get(row, columns.procedure_type))
    procedure_date = _string_value(_get(row, columns.procedure_date))
    raw_laterality = _string_value(_get(row, columns.procedure_laterality))
    procedure_laterality = Laterality.coerce(raw_laterality)
    if not any((procedure_id, procedure_type, procedure_date, raw_laterality)):
        return None, None, None, ()

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
        policy.handle_issue(issue)
        return (
            None,
            None,
            UnresolvedProcedureOccurrence(
                source=locator,
                missing_identity_fields=missing_identity_fields,
                patient_id=patient_id,
                performed_date=procedure_date,
                procedure_type=procedure_type,
                laterality=procedure_laterality,
            ),
            (issue,),
        )

    identity = ProcedureIdentity(
        patient_id=patient_id,
        performed_date=procedure_date,
        procedure_type=procedure_type,
        laterality=procedure_laterality,
    )
    procedure = registry.setdefault(identity, Procedure(identity=identity))
    procedure.add_source(locator)
    return (
        procedure,
        (
            FindingProcedureLink(
                accession_number=accession,
                finding_number=finding_number,
                procedure=identity,
                status=AttributionStatus.SOURCE_COLOCATED,
                source=locator,
            )
            if finding_number is not None
            else None
        ),
        None,
        (),
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
    row_locator: SourceLocator,
) -> Tuple[Tuple[RegionOfInterest, ...], Tuple[BuildIssue, ...]]:
    try:
        coordinate_sets, count_basis = _coordinate_sets(row, columns)
    except (TypeError, ValueError, OverflowError) as exc:
        return (), (
            _roi_build_issue(
                row_locator,
                image.image_id,
                "invalid_roi_coordinates",
                "ROI coordinates must be finite, complete, and geometrically valid.",
                {"detail": str(exc)},
            ),
        )
    if not coordinate_sets:
        return (), ()

    issues: list[BuildIssue] = []
    count = RoiSourceCount(len(coordinate_sets), count_basis)
    if image.modality is ImageModality.UNKNOWN:
        return (), (
            _roi_build_issue(
                row_locator,
                image.image_id,
                "unknown_roi_image_modality",
                "ROI depth/frame provenance requires a known 2D or DBT modality.",
            ),
        )

    frame_sets, frame_issue, recover_frames = _roi_frame_sets(
        row,
        columns,
        image,
        len(coordinate_sets),
        row_locator,
    )
    if frame_issue is not None:
        issues.append(frame_issue)
        if not recover_frames:
            return (), tuple(issues)

    derivation_flags, derivation_issue = _roi_depth_derivation_flags(
        row,
        columns,
        len(coordinate_sets),
        image,
        row_locator,
    )
    if derivation_issue is not None:
        issues.append(derivation_issue)
        return (), tuple(issues)
    unsupported_derived_indices = tuple(
        index
        for index, flag in enumerate(derivation_flags)
        if flag is True and (not image.is_dbt or not frame_sets[index])
    )
    if unsupported_derived_indices:
        issues.append(
            _roi_build_issue(
                row_locator,
                image.image_id,
                "derived_roi_depth_without_interpretable_frames",
                "Derived ROI depth requires DBT modality and usable frame evidence.",
                {"roi_indices": list(unsupported_derived_indices)},
            )
        )

    raw_confidence = _get(row, columns.roi_confidence)
    confidence = None
    if raw_confidence is not _MISSING and not _is_blank(raw_confidence):
        try:
            if isinstance(raw_confidence, bool):
                raise ValueError("boolean confidence is not numeric evidence")
            confidence = float(raw_confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be finite and in [0, 1]")
        except (TypeError, ValueError, OverflowError) as exc:
            issues.append(
                _roi_build_issue(
                    row_locator,
                    image.image_id,
                    "invalid_roi_confidence",
                    "ROI confidence must be finite and in [0, 1].",
                    {"raw_value": raw_confidence, "detail": str(exc)},
                )
            )
            confidence = None

    annotation_source = _string_value(_get(row, columns.roi_source))
    rois = []
    for index, coordinates in enumerate(coordinate_sets):
        locator = RoiLocator.synthetic(
            image_locator=image.canonical_source,
            source_ordinal=index,
        )
        frame_indices = frame_sets[index]
        depth_was_derived = derivation_flags[index] is True
        depth_frame_provenance = (
            RoiDepthFrameProvenance.DERIVED
            if image.is_dbt and frame_indices and depth_was_derived
            else RoiDepthFrameProvenance.SOURCE_SUPPLIED
            if image.is_dbt and frame_indices
            else RoiDepthFrameProvenance.UNAVAILABLE_DBT
            if image.is_dbt
            else RoiDepthFrameProvenance.NOT_APPLICABLE_2D
        )
        source_provenance = RoiSourceProvenance(
            modality=image.modality,
            source_count=count,
            depth_frame_provenance=depth_frame_provenance,
            frame_indices=frame_indices,
            derivation_method=(
                _INTERNAL_V2_ROI_DEPTH_DERIVATION_METHOD
                if depth_frame_provenance is RoiDepthFrameProvenance.DERIVED
                else None
            ),
        )
        source_provenance.validate_locator(locator)
        rois.append(
            RegionOfInterest.from_embed_coordinates(
                coordinates=coordinates,
                locator=locator,
                image_id=image.image_id,
                source_provenance=source_provenance,
                sources=tuple(
                    dict.fromkeys((image.canonical_source, row_locator))
                ),
                annotation_source=annotation_source,
                confidence=confidence,
                coordinate_frame_id=coordinate_frame_id,
            )
        )
    return tuple(rois), tuple(issues)


def _merge_row_rois(
    proposed: Tuple[RegionOfInterest, ...],
    retained: list[RegionOfInterest],
    index_by_locator: dict[RoiLocator, int],
    row_locator: SourceLocator,
) -> Tuple[BuildIssue, ...]:
    issues = []
    for roi in proposed:
        retained_index = index_by_locator.get(roi.locator)
        if retained_index is None:
            index_by_locator[roi.locator] = len(retained)
            retained.append(roi)
            continue
        existing = retained[retained_index]
        if _same_roi_observation(existing, roi):
            merged = existing
            for source in roi.sources:
                merged = merged.with_source(source)
            retained[retained_index] = merged
            continue
        issues.append(
            _roi_build_issue(
                row_locator,
                roi.image_id,
                "conflicting_roi_locator",
                "One scoped ROI locator cannot identify conflicting observations.",
                {
                    "locator": roi.locator.to_dict(),
                    "retained_coordinates": list(existing.coordinates),
                    "observed_coordinates": list(roi.coordinates),
                    "retained_sources": [
                        source.to_dict() for source in existing.sources
                    ],
                },
            )
        )
    return tuple(issues)


def _same_roi_observation(
    retained: RegionOfInterest,
    observed: RegionOfInterest,
) -> bool:
    return all(
        getattr(retained, attribute) == getattr(observed, attribute)
        for attribute in (
            "coordinates",
            "locator",
            "image_id",
            "source_provenance",
            "annotation_source",
            "confidence",
            "coordinate_frame_id",
            "source_coordinates",
            "source_coordinate_convention",
        )
    )


def _roi_build_issue(
    source: SourceLocator,
    image_id: str,
    code: str,
    message: str,
    context: Optional[Mapping[str, Any]] = None,
) -> BuildIssue:
    return BuildIssue(
        code=code,
        message=message,
        severity=IssueSeverity.ERROR,
        source=source,
        context={"image_id": image_id, **dict(context or {})},
    )


def _roi_frame_sets(
    row: Row,
    columns: _ColumnAliases,
    image: MammogramImage,
    count: int,
    source: SourceLocator,
) -> Tuple[Tuple[Tuple[int, ...], ...], Optional[BuildIssue], bool]:
    raw_frames = _get(row, columns.roi_frames)
    outer = (
        _sequence_value(raw_frames)
        if raw_frames is not _MISSING and not _is_blank(raw_frames)
        else ()
    )
    populated = any(_sequence_value(value) for value in outer)
    if not image.is_dbt:
        issue = (
            _roi_build_issue(
                source,
                image.image_id,
                "frames_on_2d_roi",
                "2D ROI observations cannot carry DBT frame indices.",
            )
            if populated
            else None
        )
        return ((),) * count, issue, True
    if not populated:
        return ((),) * count, None, True

    if len(outer) != count:
        return (
            (),
            _roi_build_issue(
                source,
                image.image_id,
                "misaligned_roi_frames",
                "DBT ROI frame collections must align exactly with ROI coordinates.",
                {"coordinate_count": count, "frame_collection_count": len(outer)},
            ),
            False,
        )
    try:
        frame_sets = tuple(_frame_indices(value) for value in outer)
    except (TypeError, ValueError, OverflowError) as exc:
        return (
            (),
            _roi_build_issue(
                source,
                image.image_id,
                "invalid_roi_frames",
                "DBT ROI frames must be unique non-negative integers.",
                {"detail": str(exc)},
            ),
            False,
        )
    if image.frame_count is not None and any(
        frame >= image.frame_count
        for frame_indices in frame_sets
        for frame in frame_indices
    ):
        return (
            (),
            _roi_build_issue(
                source,
                image.image_id,
                "roi_frame_out_of_range",
                "ROI frame indices must be below the DBT frame count.",
                {"frame_count": image.frame_count},
            ),
            False,
        )
    return frame_sets, None, True


def _roi_depth_derivation_flags(
    row: Row,
    columns: _ColumnAliases,
    count: int,
    image: MammogramImage,
    source: SourceLocator,
) -> Tuple[Tuple[Optional[bool], ...], Optional[BuildIssue]]:
    raw_flags = _get(row, columns.roi_depth_derived)
    if raw_flags is _MISSING or _is_blank(raw_flags):
        return (None,) * count, None
    outer = _sequence_value(raw_flags)
    if len(outer) != count:
        return (
            (),
            _roi_build_issue(
                source,
                image.image_id,
                "misaligned_roi_depth_derivation_flags",
                "ROI depth-derivation flags must align exactly with ROI coordinates.",
                {
                    "coordinate_count": count,
                    "flag_collection_count": len(outer),
                },
            ),
        )
    if any(not isinstance(value, bool) for value in outer):
        return (
            (),
            _roi_build_issue(
                source,
                image.image_id,
                "invalid_roi_depth_derivation_flags",
                "ROI depth-derivation flags must contain only boolean values.",
                {"raw_value": raw_flags},
            ),
        )
    return tuple(outer), None


def _coordinate_sets(
    row: Row,
    columns: _ColumnAliases,
) -> Tuple[
    Tuple[Tuple[float, float, float, float], ...],
    RoiSourceCountBasis,
]:
    raw_coordinates = _get(row, columns.roi_coordinates)
    if raw_coordinates is not _MISSING and not _is_blank(raw_coordinates):
        parsed = _sequence_value(raw_coordinates)
        if len(parsed) == 4 and not any(isinstance(item, (list, tuple)) for item in parsed):
            return (
                (_coordinate_box(parsed),),
                RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION,
            )
        return (
            tuple(_coordinate_box(_sequence_value(item)) for item in parsed),
            RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION,
        )
    if raw_coordinates is not _MISSING:
        return (), RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION

    values = (
        _get(row, columns.y_min),
        _get(row, columns.x_min),
        _get(row, columns.y_max),
        _get(row, columns.x_max),
    )
    populated = tuple(value is not _MISSING and not _is_blank(value) for value in values)
    if not any(populated):
        return (), RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE
    if not all(populated):
        raise ValueError("Separate ROI bounds must all be populated")
    return (
        (_coordinate_box(values),),
        RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
    )


def _coordinate_box(values: Sequence[Any]) -> Tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError("ROI coordinates must have four values")
    coordinates = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("ROI coordinates must be finite")
    if coordinates[2] < coordinates[0] or coordinates[3] < coordinates[1]:
        raise ValueError("ROI maxima must not precede minima")
    return coordinates  # type: ignore[return-value]


def _frame_indices(value: Any) -> Tuple[int, ...]:
    """Return one ROI's complete DBT frame collection."""

    if value is _MISSING or _is_blank(value):
        return ()
    indices = tuple(_required_frame_index(item) for item in _sequence_value(value))
    if len(set(indices)) != len(indices):
        raise ValueError("ROI frame indices cannot contain duplicates")
    return indices


def _required_frame_index(value: Any) -> int:
    frame = _normalize_exact_integer_source_value(value)
    if frame is None or frame is _INVALID_EXACT_INTEGER or frame < 0:
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


def _matched_value(row: Row, names: Tuple[str, ...]) -> Tuple[Optional[str], Any]:
    """Return the first physically present alias and its value, including null."""

    for name in names:
        if name in row:
            return name, row[name]
    return None, _MISSING


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
