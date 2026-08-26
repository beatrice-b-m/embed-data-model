"""Small, table-local column maps for the EMBED source loader."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional


ColumnMap = Mapping[str, Optional[str]]

DEFAULT_COLUMNS: Mapping[str, ColumnMap] = MappingProxyType(
    {
        "patients": MappingProxyType({"patient_id": "empi_anon"}),
        "exams": MappingProxyType(
            {
                "accession": "acc_anon",
                "patient_id": "empi_anon",
                "exam_date": "studydate_anon",
                "exam_description": "desc",
            }
        ),
        "findings": MappingProxyType(
            {
                "accession": "acc_anon",
                "finding_number": "numfind",
                "laterality": "side",
                "finding_type": None,
                "assessment": "asses",
                "recommendation": "recc",
            }
        ),
        "images": MappingProxyType(
            {
                "image_id": "anon_dicom_path",
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "laterality": "ImageLateralityFinal",
                "view_position": "ViewPosition",
                "modality": "Modality",
                "derived_image_type": "FinalImageType",
                "height": "Rows",
                "width": "Columns",
                "frame_count": "ImagesInAcquisition",
                "study_instance_uid": None,
                "series_instance_uid": "SeriesInstanceUID",
                "sop_instance_uid": "anon_dicom_path",
                "coordinate_frame_id": None,
            }
        ),
        "rois": MappingProxyType(
            {
                "image_id": "anon_dicom_path",
                "roi_key": None,
                "coordinates": "ROI_coords",
                "frame_indices": "ROI_frames",
                "annotation_source": None,
                "confidence": None,
                "coordinate_frame_id": None,
            }
        ),
        "hormone_history": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "category": "type",
                "medication": "code",
                "continuous": "continuous",
                "current": "current",
                "duration": "duration",
                "start_age": "first_age",
                "start_month": "mfirst",
                "start_year": "yfirst",
                "stop_age": "last_age",
                "stop_month": "mlast",
                "stop_year": "ylast",
                "comment": "comment",
            }
        ),
        "procedure_history": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "category": "type",
                "procedure": "pcode",
                "laterality": "side",
                "result": "result",
            }
        ),
    }
)

_REQUIRED = {
    "patients": frozenset({"patient_id"}),
    "exams": frozenset({"accession"}),
    "findings": frozenset({"accession", "finding_number"}),
    "images": frozenset({"image_id"}),
    "rois": frozenset({"image_id", "coordinates"}),
    "hormone_history": frozenset({"patient_id", "category", "medication"}),
    "procedure_history": frozenset({"patient_id", "category", "procedure"}),
}


def resolve_columns(
    overrides: Optional[Mapping[str, Mapping[str, Optional[str]]]],
) -> dict[str, dict[str, Optional[str]]]:
    """Merge validated partial overrides with EMBED's default field names."""

    resolved = {table: dict(fields) for table, fields in DEFAULT_COLUMNS.items()}
    if overrides is None:
        return resolved
    if not isinstance(overrides, Mapping):
        raise TypeError("columns must be a mapping of table names to field maps")

    unknown_tables = set(overrides).difference(DEFAULT_COLUMNS)
    if unknown_tables:
        names = ", ".join(sorted(str(name) for name in unknown_tables))
        raise ValueError(f"Unknown columns table(s): {names}")

    for table, field_overrides in overrides.items():
        if not isinstance(field_overrides, Mapping):
            raise TypeError(f"columns[{table!r}] must be a mapping")
        unknown_fields = set(field_overrides).difference(DEFAULT_COLUMNS[table])
        if unknown_fields:
            names = ", ".join(sorted(str(name) for name in unknown_fields))
            raise ValueError(f"Unknown {table} semantic column(s): {names}")
        for semantic, physical in field_overrides.items():
            if physical is not None and (
                not isinstance(physical, str) or not physical.strip()
            ):
                raise ValueError(
                    f"columns[{table!r}][{semantic!r}] must be a "
                    "non-empty string or None"
                )
            if semantic in _REQUIRED[table] and physical is None:
                raise ValueError(
                    f"Required {table} semantic column {semantic!r} cannot be unbound"
                )
            resolved[table][semantic] = physical
    return resolved


__all__ = ["ColumnMap", "DEFAULT_COLUMNS", "resolve_columns"]
