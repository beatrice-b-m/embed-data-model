"""Governed profile contracts for repository-supported source surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple

from embed_toolkit.config.capabilities import (
    CapabilityDeclaration,
    GovernedConcept,
    ProfileCapabilities,
)
from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.config.field_coverage import (
    FieldCoverageDeclaration,
    FieldCoverageManifest,
)
from embed_toolkit.core.provenance import AvailabilityState, ResolutionState


INTERNAL_V2_PROFILE = "internal-v2"
INTERNAL_V1C_PROFILE = "internal-v1c"


class ProfileKind(str, Enum):
    """Repository build surface governed by a profile contract."""

    CLINICAL = "clinical"
    IMAGE = "image"


_CLINICAL_FIELDS = (
    "patient_id",
    "birth_year",
    "sex",
    "cohort_id",
    "accession",
    "study_date",
    "exam_description",
    "finding_number",
    "finding_laterality",
    "finding_location",
    "finding_depth",
    "finding_distance",
    "finding_assessment",
    "finding_recommendation",
    "procedure_laterality",
    "procedure_date",
    "procedure_type",
    "pathology_severity",
    "pathology_report_date",
    "pathology_diagnosis_prefix",
)

_IMAGE_FIELDS = (
    "patient_id",
    "accession",
    "image_path",
    "image_id",
    "image_laterality",
    "image_view",
    "image_orientation",
    "image_height",
    "image_width",
    "image_frames",
    "image_modality",
    "series_id",
    "sop_instance_uid",
    "acquisition_group_id",
    "roi_coords",
    "roi_frames",
    "roi_source",
    "nipple_x",
    "nipple_y",
    "nipple_confidence",
    "pnl_slope",
)

_PROFILE_FIELDS = {
    ProfileKind.CLINICAL: tuple(sorted(_CLINICAL_FIELDS)),
    ProfileKind.IMAGE: tuple(sorted(_IMAGE_FIELDS)),
}


def _candidates(*names: str) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(name for name in names if name))


def profile_source_field_candidates(
    columns: EmbedColumnConfig,
    kind: ProfileKind,
) -> Dict[str, Tuple[str, ...]]:
    """Return the intentional physical candidates accepted for configured fields."""

    if not isinstance(columns, EmbedColumnConfig):
        raise TypeError("columns must be an EmbedColumnConfig")
    resolved_kind = ProfileKind(kind)
    common = {
        "patient_id": _candidates(columns.patient_id, "patient_id", "PatientID"),
        "accession": _candidates(
            columns.accession,
            "accession_number",
            "AccessionNumber",
        ),
    }
    if resolved_kind is ProfileKind.CLINICAL:
        return {
            **common,
            "birth_year": _candidates(
                columns.birth_year,
                "birth_year",
                "PatientBirthYear",
            ),
            "sex": _candidates(columns.sex, "sex", "PatientSex"),
            "cohort_id": _candidates(columns.cohort_id),
            "study_date": _candidates(columns.study_date, "exam_date", "StudyDate"),
            "exam_description": _candidates(
                columns.exam_description,
                "exam_description",
                "StudyDescription",
            ),
            "finding_number": _candidates(
                columns.finding_number,
                "finding_number",
            ),
            "finding_laterality": _candidates(
                columns.finding_laterality,
                "laterality",
            ),
            "finding_location": _candidates(
                columns.finding_location,
                "finding_location",
                "location",
                "loc",
            ),
            "finding_depth": _candidates(
                columns.finding_depth,
                "finding_depth",
                "depth",
            ),
            "finding_distance": _candidates(
                columns.finding_distance,
                "finding_distance",
                "distance",
            ),
            "finding_assessment": _candidates(
                columns.finding_assessment,
                "assessment",
                "birads",
            ),
            "finding_recommendation": _candidates(
                columns.finding_recommendation,
                "recommendation",
            ),
            "procedure_laterality": _candidates(
                columns.procedure_laterality,
                "bside",
                "procedure_laterality",
            ),
            "procedure_date": _candidates(
                columns.procedure_date,
                "procedure_date",
                "proc_date",
            ),
            "procedure_type": _candidates(
                columns.procedure_type,
                "procedure_type",
                "proc_type",
            ),
            "pathology_severity": _candidates(columns.pathology_severity),
            "pathology_report_date": _candidates(
                columns.pathology_report_date,
                "pathology_report_date",
            ),
            "pathology_diagnosis_prefix": tuple(
                f"{columns.pathology_diagnosis_prefix}{index}"
                for index in range(1, 11)
            ),
        }
    return {
        **common,
        "image_path": _candidates(columns.image_path),
        "image_id": _candidates(
            columns.image_id,
            "image_id",
            "ImageID",
            columns.image_path,
        ),
        "image_laterality": _candidates(
            columns.image_laterality,
            "image_laterality",
        ),
        "image_view": _candidates(columns.image_view, "view_position"),
        "image_orientation": _candidates(
            columns.image_orientation,
            "patient_orientation",
        ),
        "image_height": _candidates(
            columns.image_height,
            "height",
            "image_height",
        ),
        "image_width": _candidates(
            columns.image_width,
            "width",
            "image_width",
        ),
        "image_frames": _candidates(
            columns.image_frames,
            "frame_count",
        ),
        "image_modality": _candidates(
            columns.image_modality,
            "ImageType",
            "modality",
        ),
        "series_id": _candidates(
            columns.series_id,
            "SeriesInstanceUID",
            "series_instance_uid",
        ),
        "sop_instance_uid": _candidates(
            columns.sop_instance_uid,
            "SOPInstanceUID",
            "sop_instance_uid",
        ),
        "acquisition_group_id": _candidates(
            columns.acquisition_group_id,
            "coordinate_frame_id",
        ),
        "roi_coords": _candidates(
            columns.roi_coords,
            "roi_coordinates",
            "y_min",
            "YMin",
            "x_min",
            "XMin",
            "y_max",
            "YMax",
            "x_max",
            "XMax",
        ),
        "roi_frames": _candidates(columns.roi_frames, "ROI_frames", "roi_frames"),
        "roi_source": _candidates(columns.roi_source, "roi_source", "ROI_source"),
        "nipple_x": _candidates(columns.nipple_x),
        "nipple_y": _candidates(columns.nipple_y),
        "nipple_confidence": _candidates(columns.nipple_confidence),
        "pnl_slope": _candidates(columns.pnl_slope),
    }


@dataclass(frozen=True)
class RepositoryFieldInventory:
    """The repository-configured field boundary, without external count claims."""

    inventory_id: str
    governed_fields: Tuple[str, ...]
    provenance: Tuple[str, ...]
    completeness_scope: str
    external_catalog_completeness: ResolutionState

    def __post_init__(self) -> None:
        for name in ("inventory_id", "completeness_scope"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        governed_fields = tuple(self.governed_fields)
        if any(not isinstance(value, str) or not value.strip() for value in governed_fields):
            raise ValueError("governed_fields must contain non-empty strings")
        if len(set(governed_fields)) != len(governed_fields):
            raise ValueError("governed_fields must be unique")
        provenance = tuple(self.provenance)
        if not provenance or any(
            not isinstance(value, str) or not value.strip() for value in provenance
        ):
            raise ValueError("provenance must contain non-empty evidence references")
        completeness = ResolutionState(self.external_catalog_completeness)
        if completeness is not ResolutionState.UNRESOLVED:
            raise ValueError("External catalog completeness must remain unresolved")
        object.__setattr__(self, "governed_fields", tuple(sorted(governed_fields)))
        object.__setattr__(self, "provenance", tuple(sorted(provenance)))
        object.__setattr__(self, "external_catalog_completeness", completeness)

    def to_dict(self) -> Dict[str, object]:
        return {
            "inventory_id": self.inventory_id,
            "governed_fields": list(self.governed_fields),
            "provenance": list(self.provenance),
            "completeness_scope": self.completeness_scope,
            "external_catalog_completeness": (
                self.external_catalog_completeness.value
            ),
        }


@dataclass(frozen=True)
class ProfileContract:
    """Bind one exact profile identity to capabilities and field coverage."""

    source_profile: str
    kind: ProfileKind
    field_inventory: RepositoryFieldInventory
    capabilities: ProfileCapabilities
    field_coverage: FieldCoverageManifest

    def __post_init__(self) -> None:
        if not isinstance(self.source_profile, str) or not self.source_profile.strip():
            raise ValueError("source_profile must be a non-empty string")
        object.__setattr__(self, "kind", ProfileKind(self.kind))
        if not isinstance(self.field_inventory, RepositoryFieldInventory):
            raise TypeError("field_inventory must be a RepositoryFieldInventory")
        if not isinstance(self.capabilities, ProfileCapabilities):
            raise TypeError("capabilities must be ProfileCapabilities")
        if not isinstance(self.field_coverage, FieldCoverageManifest):
            raise TypeError("field_coverage must be a FieldCoverageManifest")
        if self.capabilities.source_profile != self.source_profile:
            raise ValueError("Capability profile identity must match contract")
        if self.field_coverage.source_profile != self.source_profile:
            raise ValueError("Field coverage profile identity must match contract")
        if set(self.capabilities.governed_concepts) != set(GovernedConcept):
            raise ValueError(
                "Profile contracts must declare the complete governed concept boundary"
            )
        if self.field_coverage.governed_fields != self.field_inventory.governed_fields:
            raise ValueError(
                "Field coverage boundary must exactly match the profile field inventory"
            )
        if self.field_inventory.governed_fields != _PROFILE_FIELDS[self.kind]:
            raise ValueError(
                f"{self.kind.value.capitalize()} profile field inventory must exactly "
                "match its configured EmbedColumnConfig boundary"
            )
        for declaration in self.field_coverage.declarations:
            if declaration.state in {
                AvailabilityState.BOUND,
                AvailabilityState.RAW_ONLY,
                ResolutionState.UNRESOLVED,
            } and not declaration.source_fields:
                raise ValueError(
                    "Bound, raw-only, and unresolved fields require physical source evidence"
                )
            if declaration.state in {
                AvailabilityState.UNAVAILABLE,
                AvailabilityState.UNMODELED,
                AvailabilityState.UNSUPPORTED,
            } and declaration.source_fields:
                raise ValueError(
                    "Unavailable, unmodeled, and unsupported fields cannot claim source fields"
                )

    def to_dict(self) -> Dict[str, object]:
        return {
            "source_profile": self.source_profile,
            "kind": self.kind.value,
            "field_inventory": self.field_inventory.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "field_coverage": self.field_coverage.to_dict(),
        }


REPOSITORY_FIELD_INVENTORY = RepositoryFieldInventory(
    inventory_id="embed-toolkit-configured-fields-v1",
    governed_fields=EmbedColumnConfig.field_names(),
    provenance=(
        "embed_toolkit.config.columns.EmbedColumnConfig",
        "embed_toolkit.config.defaults.DEFAULT_EMBED_COLUMN_NAMES",
    ),
    completeness_scope=(
        "Complete only for semantic fields configured by this repository; "
        "external catalog coverage is not asserted."
    ),
    external_catalog_completeness=ResolutionState.UNRESOLVED,
)


def _profile_inventory(
    inventory_id: str,
    governed_fields: Tuple[str, ...],
    profile_name: str,
) -> RepositoryFieldInventory:
    return RepositoryFieldInventory(
        inventory_id=inventory_id,
        governed_fields=governed_fields,
        provenance=("embed_toolkit.config.columns.EmbedColumnConfig",),
        completeness_scope=(
            f"Complete only for {profile_name} semantic fields selected from "
            "EmbedColumnConfig; adapter aliases and external catalog coverage "
            "are not inventory claims."
        ),
        external_catalog_completeness=ResolutionState.UNRESOLVED,
    )


INTERNAL_V2_FIELD_INVENTORY = _profile_inventory(
    "internal-v2-repository-clinical-fields-v1",
    _CLINICAL_FIELDS,
    INTERNAL_V2_PROFILE,
)

INTERNAL_V1C_FIELD_INVENTORY = _profile_inventory(
    "internal-v1c-repository-image-fields-v1",
    _IMAGE_FIELDS,
    INTERNAL_V1C_PROFILE,
)


def _capability(
    concept: GovernedConcept,
    state: AvailabilityState | ResolutionState,
    reason: str,
) -> CapabilityDeclaration:
    return CapabilityDeclaration(concept, state, reason)


def _internal_v2_capabilities() -> ProfileCapabilities:
    states: Mapping[
        GovernedConcept,
        Tuple[AvailabilityState | ResolutionState, str],
    ] = {
        GovernedConcept.PATIENT: (
            AvailabilityState.BOUND,
            "Patient identity and represented attributes have repository bindings.",
        ),
        GovernedConcept.IMAGING_EPISODE: (
            ResolutionState.UNRESOLVED,
            "Linked accessions do not establish complete episode boundaries.",
        ),
        GovernedConcept.IMAGING_EXAM: (
            AvailabilityState.BOUND,
            "Exam identity is bound through accession evidence.",
        ),
        GovernedConcept.BREAST_SIDE: (
            AvailabilityState.BOUND,
            "Unilateral exam-side identity is represented with explicit projection rules.",
        ),
        GovernedConcept.IMAGING_FINDING: (
            AvailabilityState.BOUND,
            "Finding identity and represented finding attributes are bound.",
        ),
        GovernedConcept.IMAGING_INTERPRETATION: (
            AvailabilityState.BOUND,
            "Assessment and recommendation are represented at finding scope.",
        ),
        GovernedConcept.RADIOLOGY_REPORT: (
            AvailabilityState.UNAVAILABLE,
            "No physical report-version binding is configured.",
        ),
        GovernedConcept.IMAGE: (
            AvailabilityState.UNAVAILABLE,
            "Image binding belongs to the separate internal-v1c contract.",
        ),
        GovernedConcept.REGION_OF_INTEREST: (
            AvailabilityState.UNAVAILABLE,
            "ROI binding belongs to the separate internal-v1c contract.",
        ),
        GovernedConcept.PROCEDURE: (
            AvailabilityState.BOUND,
            "Complete procedure identity is bound and incomplete occurrences remain unresolved.",
        ),
        GovernedConcept.PATHOLOGY_SPECIMEN: (
            AvailabilityState.UNSUPPORTED,
            "The configured source surface does not establish specimen identity.",
        ),
        GovernedConcept.PATHOLOGY_OBSERVATION: (
            AvailabilityState.BOUND,
            "Descriptor occurrences retain source-slot identity and evidence.",
        ),
        GovernedConcept.PATHOLOGY_DIAGNOSIS: (
            AvailabilityState.BOUND,
            "Represented diagnosis state and governed severity are bound.",
        ),
        GovernedConcept.RISK_ASSESSMENT: (
            ResolutionState.UNRESOLVED,
            "Risk output scale, model version, horizon, and probability semantics are unresolved.",
        ),
    }
    concepts = tuple(states)
    return ProfileCapabilities(
        source_profile=INTERNAL_V2_PROFILE,
        governed_concepts=concepts,
        declarations=tuple(
            _capability(concept, state, reason)
            for concept, (state, reason) in states.items()
        ),
    )


def _internal_v1c_capabilities() -> ProfileCapabilities:
    states: Mapping[GovernedConcept, Tuple[AvailabilityState | ResolutionState, str]] = {
        GovernedConcept.PATIENT: (
            ResolutionState.UNRESOLVED,
            "Patient identifiers occur on image rows without a patient-object binding.",
        ),
        GovernedConcept.IMAGING_EPISODE: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not supply episode boundaries.",
        ),
        GovernedConcept.IMAGING_EXAM: (
            ResolutionState.UNRESOLVED,
            "Accessions occur on images without a complete exam-object binding.",
        ),
        GovernedConcept.BREAST_SIDE: (
            ResolutionState.UNRESOLVED,
            "Image laterality does not establish the governed clinical breast-side grain.",
        ),
        GovernedConcept.IMAGING_FINDING: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind clinical findings.",
        ),
        GovernedConcept.IMAGING_INTERPRETATION: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind interpretations.",
        ),
        GovernedConcept.RADIOLOGY_REPORT: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind report versions.",
        ),
        GovernedConcept.IMAGE: (
            AvailabilityState.BOUND,
            "Image identity, acquisition metadata, and geometry are represented.",
        ),
        GovernedConcept.REGION_OF_INTEREST: (
            AvailabilityState.BOUND,
            "Image-scoped ROI geometry and governed source provenance are represented.",
        ),
        GovernedConcept.PROCEDURE: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind clinical procedures.",
        ),
        GovernedConcept.PATHOLOGY_SPECIMEN: (
            AvailabilityState.UNSUPPORTED,
            "The image surface cannot establish pathology specimen identity.",
        ),
        GovernedConcept.PATHOLOGY_OBSERVATION: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind pathology observations.",
        ),
        GovernedConcept.PATHOLOGY_DIAGNOSIS: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind pathology diagnoses.",
        ),
        GovernedConcept.RISK_ASSESSMENT: (
            AvailabilityState.UNAVAILABLE,
            "The image profile does not bind risk assessments.",
        ),
    }
    return ProfileCapabilities(
        source_profile=INTERNAL_V1C_PROFILE,
        governed_concepts=tuple(states),
        declarations=tuple(
            _capability(concept, state, reason)
            for concept, (state, reason) in states.items()
        ),
    )


def _field_coverage(
    source_profile: str,
    governed_fields: Tuple[str, ...],
    states: Mapping[str, AvailabilityState | ResolutionState],
    source_field_candidates: Mapping[str, Tuple[str, ...]],
) -> FieldCoverageManifest:
    declarations = []
    for governed_field in governed_fields:
        state = states.get(governed_field, AvailabilityState.BOUND)
        if state is AvailabilityState.BOUND:
            reason = "The adapter projects this configured repository field."
        elif state is AvailabilityState.RAW_ONLY:
            reason = "The field is retained in source evidence but has no normalized projection."
        else:
            reason = "The configured physical binding is a placeholder requiring confirmation."
        declarations.append(
            FieldCoverageDeclaration(
                governed_field=governed_field,
                state=state,
                reason=reason,
                source_fields=source_field_candidates[governed_field],
            )
        )
    return FieldCoverageManifest(
        source_profile=source_profile,
        governed_fields=governed_fields,
        declarations=tuple(declarations),
    )


INTERNAL_V2_CONTRACT = ProfileContract(
    source_profile=INTERNAL_V2_PROFILE,
    kind=ProfileKind.CLINICAL,
    field_inventory=INTERNAL_V2_FIELD_INVENTORY,
    capabilities=_internal_v2_capabilities(),
    field_coverage=_field_coverage(
        INTERNAL_V2_PROFILE,
        _CLINICAL_FIELDS,
        {"cohort_id": AvailabilityState.RAW_ONLY},
        profile_source_field_candidates(
            default_embed_columns(),
            ProfileKind.CLINICAL,
        ),
    ),
)

INTERNAL_V1C_CONTRACT = ProfileContract(
    source_profile=INTERNAL_V1C_PROFILE,
    kind=ProfileKind.IMAGE,
    field_inventory=INTERNAL_V1C_FIELD_INVENTORY,
    capabilities=_internal_v1c_capabilities(),
    field_coverage=_field_coverage(
        INTERNAL_V1C_PROFILE,
        _IMAGE_FIELDS,
        {
            "image_id": ResolutionState.UNRESOLVED,
            "series_id": ResolutionState.UNRESOLVED,
            "sop_instance_uid": ResolutionState.UNRESOLVED,
            "acquisition_group_id": ResolutionState.UNRESOLVED,
            "roi_frames": ResolutionState.UNRESOLVED,
            "roi_source": ResolutionState.UNRESOLVED,
            "nipple_x": AvailabilityState.RAW_ONLY,
            "nipple_y": AvailabilityState.RAW_ONLY,
            "nipple_confidence": ResolutionState.UNRESOLVED,
            "pnl_slope": AvailabilityState.RAW_ONLY,
        },
        profile_source_field_candidates(
            default_embed_columns(),
            ProfileKind.IMAGE,
        ),
    ),
)


_BUILT_IN_CONTRACTS = {
    INTERNAL_V2_PROFILE: INTERNAL_V2_CONTRACT,
    INTERNAL_V1C_PROFILE: INTERNAL_V1C_CONTRACT,
}


def profile_contract_for(
    source_profile: str,
    supplied_contract: Optional[ProfileContract] = None,
    *,
    expected_kind: Optional[ProfileKind] = None,
) -> ProfileContract:
    """Resolve an exact built-in contract or require an explicit caller contract."""

    if not isinstance(source_profile, str) or not source_profile.strip():
        raise ValueError("source_profile must be a non-empty string")
    built_in = _BUILT_IN_CONTRACTS.get(source_profile)
    if built_in is not None:
        if supplied_contract is not None and supplied_contract != built_in:
            raise ValueError("Built-in profiles require their governed built-in contract")
        resolved = built_in
    else:
        if supplied_contract is None:
            raise ValueError(
                f"Unknown source profile {source_profile!r} requires a caller-supplied contract"
            )
        if not isinstance(supplied_contract, ProfileContract):
            raise TypeError("supplied_contract must be a ProfileContract")
        if supplied_contract.source_profile != source_profile:
            raise ValueError("Supplied contract profile identity must match source_profile")
        resolved = supplied_contract
    if expected_kind is not None and resolved.kind is not ProfileKind(expected_kind):
        raise ValueError(
            f"Profile contract kind must be {ProfileKind(expected_kind).value!r}"
        )
    return resolved


def validate_contract_source_fields(
    contract: ProfileContract,
    columns: EmbedColumnConfig,
) -> None:
    """Require contract evidence to equal the physical surface for this invocation."""

    expected = profile_source_field_candidates(columns, contract.kind)
    for governed_field in contract.field_inventory.governed_fields:
        declaration = contract.field_coverage.declaration_for(governed_field)
        if declaration.state in {
            AvailabilityState.UNAVAILABLE,
            AvailabilityState.UNMODELED,
            AvailabilityState.UNSUPPORTED,
        }:
            continue
        expected_fields = tuple(sorted(expected[governed_field]))
        if declaration.source_fields != expected_fields:
            raise ValueError(
                f"Field coverage source_fields for {governed_field!r} must exactly "
                f"match accepted candidates {expected_fields!r}"
            )
