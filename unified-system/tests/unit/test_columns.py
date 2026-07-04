from __future__ import annotations

import pytest

from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.config.defaults import DEFAULT_EMBED_COLUMN_NAMES


def test_default_embed_columns_match_documented_embed_names() -> None:
    config = EmbedColumnConfig()

    assert config.patient_id == "empi_anon"
    assert config.accession == "acc_anon"
    assert config.image_path == "anon_dicom_path"
    assert config.image_laterality == "ImageLateralityFinal"
    assert config.roi_coords == "ROI_coords"
    assert config.nipple_x == "nipple_x"
    assert config.nipple_y == "nipple_y"
    assert config.finding_number == "numfind"
    assert config.to_dict() == DEFAULT_EMBED_COLUMN_NAMES


def test_placeholder_columns_cover_identifiers_roi_frames_and_landmarks() -> None:
    config = EmbedColumnConfig.default()

    assert config.image_id == "PLACEHOLDER_IMAGE_ID"
    assert config.series_id == "PLACEHOLDER_SERIES_ID"
    assert config.sop_instance_uid == "PLACEHOLDER_SOP_INSTANCE_UID"
    assert config.acquisition_group_id == "PLACEHOLDER_ACQUISITION_GROUP_ID"
    assert config.roi_frames == "PLACEHOLDER_ROI_FRAMES"
    assert config.roi_source == "PLACEHOLDER_ROI_SOURCE"
    assert config.nipple_confidence == "PLACEHOLDER_NIPPLE_CONFIDENCE"
    assert config.posterior_endpoint_x == "PLACEHOLDER_POSTERIOR_ENDPOINT_X"
    assert config.posterior_endpoint_y == "PLACEHOLDER_POSTERIOR_ENDPOINT_Y"

    assert config.roi_columns() == (
        "ROI_coords",
        "PLACEHOLDER_ROI_FRAMES",
        "PLACEHOLDER_ROI_SOURCE",
    )
    assert config.landmark_columns() == (
        "nipple_x",
        "nipple_y",
        "PLACEHOLDER_NIPPLE_CONFIDENCE",
        "pnl_slope",
        "PLACEHOLDER_POSTERIOR_ENDPOINT_X",
        "PLACEHOLDER_POSTERIOR_ENDPOINT_Y",
    )


def test_custom_column_names_can_be_supplied_directly() -> None:
    config = EmbedColumnConfig(
        patient_id="patient_key",
        image_path="dicom_path",
        image_laterality="laterality",
        roi_coords="boxes",
        roi_frames="frame_range",
        posterior_endpoint_x="posterior_x",
        posterior_endpoint_y="posterior_y",
    )

    assert config.patient_id == "patient_key"
    assert config.required_image_columns() == (
        "dicom_path",
        "laterality",
        "ViewPosition",
    )
    assert config.required_roi_columns() == ("boxes",)
    assert config.landmark_columns()[-2:] == ("posterior_x", "posterior_y")


def test_with_overrides_preserves_original_config() -> None:
    config = EmbedColumnConfig()

    custom = config.with_overrides(image_view="view", finding_distance="dist_cm")

    assert config.image_view == "ViewPosition"
    assert config.finding_distance == "distance"
    assert custom.image_view == "view"
    assert custom.finding_distance == "dist_cm"
    assert custom.finding_columns()[-2:] == ("dist_cm", "asses")


def test_mapping_round_trip_is_serialization_friendly() -> None:
    config = EmbedColumnConfig(
        accession="accession_id",
        image_id="image_uid",
        roi_source="annotation_source",
    )

    serialized = config.to_dict()
    rebuilt = EmbedColumnConfig.from_mapping(serialized)

    assert rebuilt == config
    assert default_embed_columns() == EmbedColumnConfig()


def test_unknown_or_empty_column_config_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown EMBED column config fields"):
        EmbedColumnConfig.from_mapping({"not_a_field": "source_column"})

    with pytest.raises(ValueError, match="patient_id must be a non-empty column name"):
        EmbedColumnConfig(patient_id="")
