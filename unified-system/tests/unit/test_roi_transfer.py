from __future__ import annotations

import pytest

from embed_toolkit.audit.results import ResultStatus
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.workflows.roi_transfer import (
    AcquisitionKind,
    AcquisitionRelationship,
    RelatednessBasis,
    transfer_roi,
)


def image(
    image_id: str,
    *,
    laterality: Laterality = Laterality.LEFT,
    view_position: ViewPosition = ViewPosition.CC,
    modality: ImageModality = ImageModality.FFDM,
    height: int | None = 100,
    width: int | None = 200,
    frame_count: int | None = None,
    patient_id: str | None = "patient-1",
    accession_number: str | None = "acc-1",
    study_instance_uid: str | None = "study-1",
    series_instance_uid: str | None = None,
    coordinate_frame_id: str | None = "group-1",
) -> MammogramImage:
    return MammogramImage(
        image_id=image_id,
        laterality=laterality,
        view_position=view_position,
        sources=[
            SourceLocator(
                scope="roi-transfer-tests",
                scope_kind=SourceScopeKind.MATERIALIZATION,
                source_profile="test",
                source_table="images",
                source_key=image_id,
            )
        ],
        modality=modality,
        height=height,
        width=width,
        frame_count=frame_count,
        patient_id=patient_id,
        accession_number=accession_number,
        study_instance_uid=study_instance_uid,
        series_instance_uid=series_instance_uid,
        coordinate_frame_id=coordinate_frame_id,
    )


def roi(
    source_image: MammogramImage,
    coordinates: tuple[float, float, float, float] = (10, 20, 30, 60),
    *,
    frame_indices: tuple[int, ...] = (),
    locator_source: SourceLocator | None = None,
) -> RegionOfInterest:
    locator_source = locator_source or source_image.canonical_source
    locator = RoiLocator.from_source(
        image_locator=locator_source,
        source_value="roi-1",
    )
    return RegionOfInterest(
        coordinates,
        locator=locator,
        image_id=source_image.image_id,
        source_provenance=RoiSourceProvenance(
            modality=source_image.modality,
            source_count=RoiSourceCount(
                1,
                RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
            ),
            depth_frame_provenance=(
                RoiDepthFrameProvenance.SOURCE_SUPPLIED
                if frame_indices
                else RoiDepthFrameProvenance.UNAVAILABLE_DBT
                if source_image.is_dbt
                else RoiDepthFrameProvenance.UNRESOLVED_MODALITY
                if source_image.modality is ImageModality.UNKNOWN
                else RoiDepthFrameProvenance.NOT_APPLICABLE_2D
            ),
            frame_indices=frame_indices,
        ),
        sources=(locator_source,),
    )


def test_acquisition_relationship_identifies_supported_modalities_and_checks() -> None:
    relationship = AcquisitionRelationship.from_images(
        image("dbt", modality=ImageModality.DBT),
        image("s2d", modality=ImageModality.S2D),
    )

    assert relationship.source_kind is AcquisitionKind.DBT
    assert relationship.target_kind is AcquisitionKind.SYNTHETIC_2D
    assert relationship.same_breast
    assert relationship.same_view
    assert relationship.same_patient
    assert relationship.related
    assert relationship.relatedness_basis is (
        RelatednessBasis.PROFILE_ACQUISITION_GROUP
    )
    assert relationship.can_transfer


@pytest.mark.parametrize("target_group", [None, "", "group-2"])
def test_default_relatedness_requires_matching_populated_acquisition_group(
    target_group: str | None,
) -> None:
    relationship = AcquisitionRelationship.from_images(
        image("source", coordinate_frame_id="group-1"),
        image(
            "target",
            coordinate_frame_id=target_group,
            accession_number="acc-1",
            study_instance_uid="study-1",
            series_instance_uid="series-1",
        ),
    )

    assert not relationship.related
    assert relationship.relatedness_basis is RelatednessBasis.UNAVAILABLE
    assert relationship.evidence["shared_accession"]
    assert relationship.evidence["shared_study_uid"]
    assert not relationship.evidence["matching_acquisition_group"]


def test_related_override_is_labeled_as_caller_assertion() -> None:
    relationship = AcquisitionRelationship.from_images(
        image("source", coordinate_frame_id="group-1"),
        image("target", coordinate_frame_id="group-2"),
        related=True,
    )

    assert relationship.related
    assert relationship.relatedness_basis is RelatednessBasis.CALLER_ASSERTION
    assert not relationship.evidence["matching_acquisition_group"]
    assert relationship.to_dict()["relatedness_basis"] == "caller_assertion"


def test_transfer_roi_scales_between_related_same_breast_same_view_images() -> None:
    source = image("src", height=100, width=200)
    target = image("target", height=50, width=400)
    observed = roi(source)

    result = transfer_roi(observed, source, target)

    assert result.status is ResultStatus.SUCCESS
    assert result.transferred_roi["coordinates"] == (5.0, 40.0, 15.0, 120.0)
    assert result.transferred_roi["target_image_id"] == "target"
    assert "locator" not in result.transferred_roi
    assert result.transform["scale"] == (0.5, 2.0)
    assert result.warnings == ()


def test_transfer_roi_skips_unresolved_acquisition_kind() -> None:
    source = image("src", modality=ImageModality.UNKNOWN)
    target = image("target", modality=ImageModality.FFDM)

    result = transfer_roi(roi(source), source, target)

    assert result.status is ResultStatus.SKIPPED
    assert result.warnings[0].code == "unresolved_acquisition_kind"


def test_transfer_roi_skips_side_or_view_mismatch() -> None:
    source = image("src", laterality=Laterality.LEFT, view_position=ViewPosition.CC)
    target = image(
        "target", laterality=Laterality.RIGHT, view_position=ViewPosition.MLO
    )
    observed = roi(source)

    result = transfer_roi(observed, source, target)

    assert result.status is ResultStatus.SKIPPED
    assert result.transferred_roi == {}
    assert result.transform == {}
    assert result.warnings[0].code == "incompatible_transfer"
    assert result.warnings[0].payload == {
        "same_patient": True,
        "same_breast": False,
        "same_view": False,
        "related": True,
    }


def test_transfer_roi_fails_with_missing_dimensions_warning() -> None:
    source = image("src", height=None, width=200)
    target = image("target", height=50, width=400)
    observed = roi(source)

    result = transfer_roi(observed, source, target)

    assert result.status is ResultStatus.FAILED
    assert result.transferred_roi == {}
    assert result.warnings[0].code == "missing_image_dimensions"
    assert result.warnings[0].payload["source_shape"] is None
    assert result.warnings[0].payload["target_shape"] == (50, 400)


def test_transfer_retains_explicitly_named_source_frame_evidence_by_default() -> None:
    source = image("dbt", modality=ImageModality.DBT, height=80, width=80)
    target = image("s2d", modality=ImageModality.S2D, height=160, width=40)
    observed = roi(source, (4, 10, 20, 30), frame_indices=(12,))

    result = transfer_roi(observed, source, target)

    assert result.status is ResultStatus.SUCCESS
    assert result.transferred_roi["coordinates"] == (8.0, 5.0, 40.0, 15.0)
    assert "frame_indices" not in result.transferred_roi
    assert result.transferred_roi["source_frame_indices"] == (12,)
    assert result.warnings[0].code == "approximate_transfer"
    assert result.warnings[0].payload["retained_source_frame_indices"] == (12,)


def test_transfer_roi_can_drop_source_frame_evidence_when_requested() -> None:
    source = image("dbt", modality=ImageModality.DBT)
    target = image("s2d", modality=ImageModality.S2D)
    observed = roi(source, (4, 10, 20, 30), frame_indices=(12,))

    result = transfer_roi(
        observed,
        source,
        target,
        retain_source_frame_evidence=False,
    )

    assert result.status is ResultStatus.SUCCESS
    assert result.transferred_roi["source_frame_indices"] == ()
    assert result.warnings[0].payload["retained_source_frame_indices"] == ()


def test_transfer_source_frame_evidence_is_independent_of_target_frame_count() -> None:
    source = image(
        "dbt-source",
        modality=ImageModality.DBT,
        frame_count=20,
    )
    observed = roi(source, frame_indices=(12,))

    unknown_target_depth = transfer_roi(
        observed,
        source,
        image("dbt-target", modality=ImageModality.DBT, frame_count=None),
    )
    short_target = transfer_roi(
        observed,
        source,
        image("short-target", modality=ImageModality.DBT, frame_count=10),
    )

    assert unknown_target_depth.transferred_roi["source_frame_indices"] == (12,)
    assert short_target.transferred_roi["source_frame_indices"] == (12,)
    assert "frame_indices" not in unknown_target_depth.transferred_roi
    assert "frame_indices" not in short_target.transferred_roi


def test_transfer_roi_result_is_serializable() -> None:
    source = image("src", height=100, width=200)
    result = transfer_roi(roi(source), source, image("target", height=50, width=400))

    serialized = result.to_dict()

    assert serialized["status"] == "success"
    assert serialized["transferred_roi"]["coordinates"] == [5.0, 40.0, 15.0, 120.0]
    assert serialized["evidence"][0]["kind"] == "acquisition_relationship"


def test_transfer_roi_rejects_unrelated_images_when_relationship_says_so() -> None:
    source = image("src")
    target = image("target")
    observed = roi(source)
    relationship = AcquisitionRelationship.from_images(source, target, related=False)

    result = transfer_roi(observed, source, target, relationship=relationship)

    assert result.status is ResultStatus.SKIPPED
    assert result.warnings[0].payload["same_breast"]
    assert result.warnings[0].payload["same_view"]
    assert not result.warnings[0].payload["related"]


def test_transfer_rejects_contradictory_relationship_and_wrong_source_image() -> None:
    source = image("src")
    target = image("target", laterality=Laterality.RIGHT)
    observed = roi(source)
    contradictory = AcquisitionRelationship(
        source_kind=AcquisitionKind.FFDM,
        target_kind=AcquisitionKind.FFDM,
        same_patient=True,
        same_breast=True,
        same_view=True,
        related=True,
        relatedness_basis=RelatednessBasis.CALLER_ASSERTION,
        evidence={},
    )

    with pytest.raises(ValueError, match="contradicts"):
        transfer_roi(observed, source, target, relationship=contradictory)
    with pytest.raises(ValueError, match="source image"):
        transfer_roi(observed, image("other"), target)


def test_transfer_skips_different_patient_or_acquisition_context() -> None:
    source = image("source")

    different_patient = transfer_roi(
        roi(source),
        source,
        image("different-patient", patient_id="patient-2"),
    )
    different_context = transfer_roi(
        roi(source),
        source,
        image(
            "different-context",
            accession_number="acc-2",
            study_instance_uid="study-2",
            coordinate_frame_id="group-2",
        ),
    )

    assert different_patient.status is ResultStatus.SKIPPED
    assert not different_patient.warnings[0].payload["same_patient"]
    assert different_context.status is ResultStatus.SKIPPED
    assert not different_context.evidence[0].payload["matching_acquisition_group"]

    whitespace_patient = transfer_roi(
        roi(source),
        source,
        image("whitespace-patient", patient_id="   "),
    )
    assert whitespace_patient.status is ResultStatus.SKIPPED
    assert not whitespace_patient.warnings[0].payload["same_patient"]


@pytest.mark.parametrize("related", [1, 0, "true", "false"])
def test_relationship_rejects_non_boolean_related_override(related: object) -> None:
    with pytest.raises(TypeError, match="related must be a bool"):
        AcquisitionRelationship.from_images(
            image("source"),
            image("target"),
            related=related,  # type: ignore[arg-type]
        )


def test_relationship_evidence_is_deeply_frozen_and_serializes_fresh() -> None:
    payload = {"nested": [{"value": 1}]}
    relationship = AcquisitionRelationship(
        source_kind=AcquisitionKind.FFDM,
        target_kind=AcquisitionKind.FFDM,
        same_patient=True,
        same_breast=True,
        same_view=True,
        related=True,
        relatedness_basis=RelatednessBasis.CALLER_ASSERTION,
        evidence=payload,
    )
    payload["nested"][0]["value"] = 2

    assert relationship.evidence["nested"][0]["value"] == 1
    serialized = relationship.to_dict()
    serialized["evidence"]["nested"][0]["value"] = 3
    assert relationship.to_dict()["evidence"]["nested"][0]["value"] == 1
    with pytest.raises(ValueError, match="finite"):
        AcquisitionRelationship(
            source_kind=AcquisitionKind.FFDM,
            target_kind=AcquisitionKind.FFDM,
            same_patient=True,
            same_breast=True,
            same_view=True,
            related=True,
            relatedness_basis=RelatednessBasis.CALLER_ASSERTION,
            evidence={"invalid": float("nan")},
        )


def test_transfer_accepts_noncanonical_source_ledger_locator() -> None:
    source = image("source")
    row_two = SourceLocator(
        scope="roi-transfer-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="images",
        source_key="source-row-2",
    )
    source.add_source(row_two)
    observed = roi(source, locator_source=row_two)

    result = transfer_roi(observed, source, image("target"))

    assert result.status is ResultStatus.SUCCESS
    assert result.source_roi_locator.image_locator == row_two
