"""Column-name configuration for EMBED source tables."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Mapping, Tuple

from embed_toolkit.config.defaults import (
    DEFAULT_EMBED_COLUMN_NAMES,
    DEFAULT_EMBED_REQUIRED_FINDING_COLUMNS,
    DEFAULT_EMBED_REQUIRED_IMAGE_COLUMNS,
    DEFAULT_EMBED_REQUIRED_ROI_COLUMNS,
)


@dataclass(frozen=True)
class EmbedColumnConfig:
    """Serializable EMBED column-name map used by table adapters.

    Fields describe semantic inputs consumed by the unified toolkit; values are
    the concrete column names in a source export. Placeholder defaults mark
    known local/export fields that need confirmation before production use.
    """

    patient_id: str = DEFAULT_EMBED_COLUMN_NAMES["patient_id"]
    birth_year: str = DEFAULT_EMBED_COLUMN_NAMES["birth_year"]
    sex: str = DEFAULT_EMBED_COLUMN_NAMES["sex"]
    cohort_id: str = DEFAULT_EMBED_COLUMN_NAMES["cohort_id"]
    accession: str = DEFAULT_EMBED_COLUMN_NAMES["accession"]
    study_date: str = DEFAULT_EMBED_COLUMN_NAMES["study_date"]
    exam_description: str = DEFAULT_EMBED_COLUMN_NAMES["exam_description"]
    image_path: str = DEFAULT_EMBED_COLUMN_NAMES["image_path"]
    image_id: str = DEFAULT_EMBED_COLUMN_NAMES["image_id"]
    image_laterality: str = DEFAULT_EMBED_COLUMN_NAMES["image_laterality"]
    image_view: str = DEFAULT_EMBED_COLUMN_NAMES["image_view"]
    image_orientation: str = DEFAULT_EMBED_COLUMN_NAMES["image_orientation"]
    image_height: str = DEFAULT_EMBED_COLUMN_NAMES["image_height"]
    image_width: str = DEFAULT_EMBED_COLUMN_NAMES["image_width"]
    image_frames: str = DEFAULT_EMBED_COLUMN_NAMES["image_frames"]
    image_modality: str = DEFAULT_EMBED_COLUMN_NAMES["image_modality"]
    series_id: str = DEFAULT_EMBED_COLUMN_NAMES["series_id"]
    sop_instance_uid: str = DEFAULT_EMBED_COLUMN_NAMES["sop_instance_uid"]
    acquisition_group_id: str = DEFAULT_EMBED_COLUMN_NAMES["acquisition_group_id"]
    roi_coords: str = DEFAULT_EMBED_COLUMN_NAMES["roi_coords"]
    roi_frames: str = DEFAULT_EMBED_COLUMN_NAMES["roi_frames"]
    roi_source: str = DEFAULT_EMBED_COLUMN_NAMES["roi_source"]
    nipple_x: str = DEFAULT_EMBED_COLUMN_NAMES["nipple_x"]
    nipple_y: str = DEFAULT_EMBED_COLUMN_NAMES["nipple_y"]
    nipple_confidence: str = DEFAULT_EMBED_COLUMN_NAMES["nipple_confidence"]
    pnl_slope: str = DEFAULT_EMBED_COLUMN_NAMES["pnl_slope"]
    finding_number: str = DEFAULT_EMBED_COLUMN_NAMES["finding_number"]
    finding_laterality: str = DEFAULT_EMBED_COLUMN_NAMES["finding_laterality"]
    finding_location: str = DEFAULT_EMBED_COLUMN_NAMES["finding_location"]
    finding_depth: str = DEFAULT_EMBED_COLUMN_NAMES["finding_depth"]
    finding_distance: str = DEFAULT_EMBED_COLUMN_NAMES["finding_distance"]
    finding_assessment: str = DEFAULT_EMBED_COLUMN_NAMES["finding_assessment"]
    finding_recommendation: str = DEFAULT_EMBED_COLUMN_NAMES[
        "finding_recommendation"
    ]
    procedure_laterality: str = DEFAULT_EMBED_COLUMN_NAMES["procedure_laterality"]
    procedure_date: str = DEFAULT_EMBED_COLUMN_NAMES["procedure_date"]
    procedure_type: str = DEFAULT_EMBED_COLUMN_NAMES["procedure_type"]
    pathology_severity: str = DEFAULT_EMBED_COLUMN_NAMES["pathology_severity"]
    pathology_report_date: str = DEFAULT_EMBED_COLUMN_NAMES["pathology_report_date"]
    pathology_diagnosis_prefix: str = DEFAULT_EMBED_COLUMN_NAMES[
        "pathology_diagnosis_prefix"
    ]

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field.name} must be a non-empty column name")

    @classmethod
    def default(cls) -> "EmbedColumnConfig":
        """Return the standard EMBED column configuration."""

        return cls()

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "EmbedColumnConfig":
        """Build a config from serialized field-name to column-name values."""

        known_fields = cls.field_names()
        unknown = tuple(sorted(set(values) - set(known_fields)))
        if unknown:
            raise ValueError(f"Unknown EMBED column config fields: {unknown}")
        return cls(**dict(values))

    def with_overrides(self, **overrides: str) -> "EmbedColumnConfig":
        """Return a copy with selected semantic fields remapped."""

        return replace(self, **overrides)

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable mapping of semantic fields to columns."""

        return asdict(self)

    @classmethod
    def field_names(cls) -> Tuple[str, ...]:
        """Return semantic configuration field names."""

        return tuple(field.name for field in fields(cls))

    def column_names(self) -> Tuple[str, ...]:
        """Return all configured source column names in field order."""

        return tuple(self.to_dict().values())

    def image_columns(self) -> Tuple[str, ...]:
        """Return configured columns commonly used for image metadata."""

        return self._columns_for(
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
        )

    def roi_columns(self) -> Tuple[str, ...]:
        """Return configured columns commonly used for ROI construction."""

        return self._columns_for(
            "roi_coords",
            "roi_frames",
            "roi_source",
        )

    def landmark_columns(self) -> Tuple[str, ...]:
        """Return configured nipple and PNL columns."""

        return self._columns_for(
            "nipple_x",
            "nipple_y",
            "nipple_confidence",
            "pnl_slope",
        )

    def finding_columns(self) -> Tuple[str, ...]:
        """Return configured columns commonly used for clinical findings."""

        return self._columns_for(
            "accession",
            "finding_number",
            "finding_laterality",
            "finding_location",
            "finding_depth",
            "finding_distance",
            "finding_assessment",
            "finding_recommendation",
        )

    def required_image_columns(self) -> Tuple[str, ...]:
        return self._columns_for(*DEFAULT_EMBED_REQUIRED_IMAGE_COLUMNS)

    def required_roi_columns(self) -> Tuple[str, ...]:
        return self._columns_for(*DEFAULT_EMBED_REQUIRED_ROI_COLUMNS)

    def required_finding_columns(self) -> Tuple[str, ...]:
        return self._columns_for(*DEFAULT_EMBED_REQUIRED_FINDING_COLUMNS)

    def _columns_for(self, *field_names: str) -> Tuple[str, ...]:
        return tuple(getattr(self, field_name) for field_name in field_names)


def default_embed_columns() -> EmbedColumnConfig:
    """Return the standard EMBED column configuration."""

    return EmbedColumnConfig.default()
