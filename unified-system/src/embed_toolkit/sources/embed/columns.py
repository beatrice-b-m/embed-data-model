"""Small, table-local column maps for the EMBED source loader.

The maps bind only source facts that are established at this adapter boundary.
In particular, registry payload fields and future image identity fields remain
explicitly configurable instead of being guessed from similarly named columns.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional


ColumnMap = Mapping[str, Optional[str]]


DEFAULT_COLUMNS: Mapping[str, ColumnMap] = MappingProxyType(
    {
        "patients": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "sex": "GENDER_DESC",
                "birth_year": "birth_year",
                "context_date": "studydate_anon",
            }
        ),
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
                "interpretation": None,
                "location": "location",
                "depth": "depth",
                "distance": "distance",
                "clock_position": None,
                "record_type": None,
                "descriptors": None,
            }
        ),
        "images": MappingProxyType(
            {
                # These three identities are intentionally unbound until the
                # imaging adapter qualifies its physical source convention.
                "image_id": None,
                "source_path": None,
                "source_sop_instance_uid": None,
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
                "coordinate_frame_id": None,
            }
        ),
        "rois": MappingProxyType(
            {
                "image_id": None,
                "source_path": None,
                "roi_key": None,
                "coordinates": "ROI_coords",
                "frame_indices": "ROI_frames",
                "depth_derived": "ROI_depth_derived",
                "annotation_source": None,
                "confidence": None,
                "coordinate_frame_id": None,
            }
        ),
        "hormone_history": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
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
                "record_id": None,
                "accession": "acc_anon",
                "category": "type",
                "procedure": "pcode",
                "laterality": "side",
                "result": "result",
            }
        ),
        "procedures": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
                "performed_date": "procdate_anon",
                "procedure_type": "type",
                "laterality": "bside",
                "accession": "acc_anon",
                "finding_number": "numfind",
            }
        ),
        "pathology": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
                "accession": "acc_anon",
                "finding_number": "numfind",
                "laterality": "bside",
                "procedure_date": "procdate_anon",
                "procedure_type": "type",
                "diagnosis": "pathology_diagnosis",
                "result_category": "pathology_result_category",
                "malignant": "pathology_malignant",
                "severity": "path_severity",
                "report_documented_date": "pdate_anon",
                **{f"descriptor_{index}": f"path{index}" for index in range(1, 11)},
            }
        ),
        "registry": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "registry_id": "cancer_registry_id",
                "record_id": None,
                "diagnosis": None,
                "result_category": None,
                "malignant": None,
                "severity": None,
                "report_documented_date": None,
                **{f"descriptor_{index}": None for index in range(1, 11)},
            }
        ),
        "magview": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "finding_number": "numfind",
                "registry_assignment": "cancer_outcome_registry_id",
                "linked_accession": "linkedaccession_anon",
            }
        ),
    }
)


_REQUIRED = {
    "patients": frozenset({"patient_id"}),
    "exams": frozenset({"accession"}),
    "findings": frozenset({"accession", "finding_number"}),
    # Image identity can be supplied by toolkit ID, source path, or source
    # SOP UID.  The imaging adapter reports when none of those are bound.
    "images": frozenset(),
    "rois": frozenset({"coordinates"}),
    "hormone_history": frozenset({"patient_id", "category", "medication"}),
    "procedure_history": frozenset({"patient_id", "category", "procedure"}),
    "procedures": frozenset(
        {"patient_id", "performed_date", "procedure_type", "laterality"}
    ),
    "pathology": frozenset(),
    "registry": frozenset({"patient_id", "registry_id"}),
    "magview": frozenset(),
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
