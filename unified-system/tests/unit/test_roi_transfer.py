from __future__ import annotations

from embed_toolkit.audit.results import ResultStatus
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.workflows.roi_transfer import (
    AcquisitionKind,
    AcquisitionRelationship,
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
) -> MammogramImage:
    return MammogramImage(
        image_id=image_id,
        laterality=laterality,
        view_position=view_position,
        modality=modality,
        height=height,
        width=width,
        accession_number="acc-1",
        study_instance_uid="study-1",
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
    assert relationship.related
    assert relationship.can_transfer


def test_transfer_roi_scales_between_related_same_breast_same_view_images() -> None:
    source = image("src", height=100, width=200)
    target = image("target", height=50, width=400)
    roi = RegionOfInterest((10, 20, 30, 60), roi_id="roi-1", image_id="src")

    result = transfer_roi(roi, source, target)

    assert result.status is ResultStatus.SUCCESS
    assert result.transferred_roi["coordinates"] == [5.0, 40.0, 15.0, 120.0]
    assert result.transferred_roi["image_id"] == "target"
    assert result.transform["scale"] == [0.5, 2.0]
    assert result.warnings == []


def test_transfer_roi_skips_side_or_view_mismatch() -> None:
    source = image("src", laterality=Laterality.LEFT, view_position=ViewPosition.CC)
    target = image("target", laterality=Laterality.RIGHT, view_position=ViewPosition.MLO)
    roi = RegionOfInterest((10, 20, 30, 60), roi_id="roi-1", image_id="src")

    result = transfer_roi(roi, source, target)

    assert result.status is ResultStatus.SKIPPED
    assert result.transferred_roi == {}
    assert result.transform == {}
    assert result.warnings[0].code == "incompatible_transfer"
    assert result.warnings[0].payload == {
        "same_breast": False,
        "same_view": False,
        "related": True,
    }


def test_transfer_roi_fails_with_missing_dimensions_warning() -> None:
    source = image("src", height=None, width=200)
    target = image("target", height=50, width=400)
    roi = RegionOfInterest((10, 20, 30, 60), roi_id="roi-1", image_id="src")

    result = transfer_roi(roi, source, target)

    assert result.status is ResultStatus.FAILED
    assert result.transferred_roi == {}
    assert result.warnings[0].code == "missing_image_dimensions"
    assert result.warnings[0].payload["source_shape"] is None
    assert result.warnings[0].payload["target_shape"] == (50, 400)


def test_transfer_roi_preserves_dbt_frame_by_default() -> None:
    source = image("dbt", modality=ImageModality.DBT, height=80, width=80)
    target = image("s2d", modality=ImageModality.S2D, height=160, width=40)
    roi = RegionOfInterest(
        (4, 10, 20, 30),
        roi_id="roi-dbt",
        image_id="dbt",
        frame_index=12,
    )

    result = transfer_roi(roi, source, target)

    assert result.status is ResultStatus.SUCCESS
    assert result.transferred_roi["coordinates"] == [8.0, 5.0, 40.0, 15.0]
    assert result.transferred_roi["frame_index"] == 12
    assert result.warnings[0].code == "approximate_transfer"
    assert result.warnings[0].payload["preserved_frame_index"] == 12


def test_transfer_roi_can_drop_dbt_frame_when_requested() -> None:
    source = image("dbt", modality=ImageModality.DBT)
    target = image("s2d", modality=ImageModality.S2D)
    roi = RegionOfInterest(
        (4, 10, 20, 30),
        roi_id="roi-dbt",
        image_id="dbt",
        frame_index=12,
    )

    result = transfer_roi(roi, source, target, preserve_dbt_frame=False)

    assert result.status is ResultStatus.SUCCESS
    assert "frame_index" not in result.transferred_roi
    assert result.warnings[0].payload["preserved_frame_index"] is None


def test_transfer_roi_result_is_serializable() -> None:
    result = transfer_roi(
        RegionOfInterest((10, 20, 30, 60), roi_id="roi-1", image_id="src"),
        image("src", height=100, width=200),
        image("target", height=50, width=400),
    )

    serialized = result.to_dict()

    assert serialized["status"] == "success"
    assert serialized["transferred_roi"]["coordinates"] == [5.0, 40.0, 15.0, 120.0]
    assert serialized["evidence"][0]["kind"] == "acquisition_relationship"


def test_transfer_roi_rejects_unrelated_images_when_relationship_says_so() -> None:
    source = image("src")
    target = image("target")
    roi = RegionOfInterest((10, 20, 30, 60), roi_id="roi-1", image_id="src")
    relationship = AcquisitionRelationship.from_images(source, target, related=False)

    result = transfer_roi(roi, source, target, relationship=relationship)

    assert result.status is ResultStatus.SKIPPED
    assert result.warnings[0].payload["same_breast"]
    assert result.warnings[0].payload["same_view"]
    assert not result.warnings[0].payload["related"]
