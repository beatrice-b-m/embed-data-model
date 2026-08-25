from __future__ import annotations

import pytest

from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.config.defaults import DEFAULT_EMBED_COLUMN_NAMES


def test_default_embed_columns_match_documented_embed_names() -> None:
    config = EmbedColumnConfig()

    assert config.patient_id == "empi_anon"
    assert config.accession == "acc_anon"
    assert config.sex == "GENDER_DESC"
    assert config.exam_description == "desc"
    assert config.image_path == "anon_dicom_path"
    assert config.image_laterality == "ImageLateralityFinal"
    assert config.image_modality == "Modality"
    assert config.derived_image_type == "FinalImageType"
    assert config.roi_coords == "ROI_coords"
    assert config.nipple_x == "nipple_x"
    assert config.nipple_y == "nipple_y"
    assert config.finding_number == "numfind"
    assert config.finding_recommendation == "recc"
    assert config.pathology_report_date == "pdate_anon"
    assert config.to_dict() == DEFAULT_EMBED_COLUMN_NAMES


def test_v1c_columns_bind_known_identifiers_and_roi_frames() -> None:
    config = EmbedColumnConfig.default()

    assert config.image_id == "anon_dicom_path"
    assert config.series_id == "SeriesInstanceUID"
    assert config.sop_instance_uid == "anon_dicom_path"
    assert config.acquisition_group_id == "acquisition_group_id"
    assert config.roi_frames == "ROI_frames"
    assert config.roi_depth_derived == "ROI_depth_derived"
    assert config.roi_source == "PLACEHOLDER_ROI_SOURCE"
    assert config.nipple_confidence == "PLACEHOLDER_NIPPLE_CONFIDENCE"

    assert config.roi_columns() == (
        "ROI_coords",
        "ROI_frames",
        "ROI_depth_derived",
        "PLACEHOLDER_ROI_SOURCE",
    )
    assert config.landmark_columns() == (
        "nipple_x",
        "nipple_y",
        "PLACEHOLDER_NIPPLE_CONFIDENCE",
        "pnl_slope",
    )


def test_custom_column_names_can_be_supplied_directly() -> None:
    config = EmbedColumnConfig(
        patient_id="patient_key",
        image_path="dicom_path",
        image_laterality="laterality",
        roi_coords="boxes",
        roi_frames="frame_range",
    )

    assert config.patient_id == "patient_key"
    assert config.required_image_columns() == (
        "dicom_path",
        "laterality",
        "ViewPosition",
    )
    assert config.required_roi_columns() == ("boxes",)
    assert config.landmark_columns() == (
        "nipple_x",
        "nipple_y",
        "PLACEHOLDER_NIPPLE_CONFIDENCE",
        "pnl_slope",
    )


def test_with_overrides_preserves_original_config() -> None:
    config = EmbedColumnConfig()

    custom = config.with_overrides(image_view="view", finding_distance="dist_cm")

    assert config.image_view == "ViewPosition"
    assert config.finding_distance == "distance"
    assert custom.image_view == "view"
    assert custom.finding_distance == "dist_cm"
    assert custom.finding_columns()[-3:] == ("dist_cm", "asses", "recc")


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
