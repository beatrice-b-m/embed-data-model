"""Default source-column names for EMBED adapters."""

DEFAULT_EMBED_COLUMN_NAMES = {
    "patient_id": "empi_anon",
    "cohort_id": "cohort_num",
    "accession": "acc_anon",
    "study_date": "studydate_anon",
    "image_path": "anon_dicom_path",
    "image_id": "PLACEHOLDER_IMAGE_ID",
    "image_laterality": "ImageLateralityFinal",
    "image_view": "ViewPosition",
    "image_orientation": "PatientOrientation",
    "image_height": "Rows",
    "image_width": "Columns",
    "image_frames": "ImagesInAcquisition",
    "image_modality": "FinalImageType",
    "series_id": "PLACEHOLDER_SERIES_ID",
    "sop_instance_uid": "PLACEHOLDER_SOP_INSTANCE_UID",
    "acquisition_group_id": "PLACEHOLDER_ACQUISITION_GROUP_ID",
    "roi_coords": "ROI_coords",
    "roi_frames": "PLACEHOLDER_ROI_FRAMES",
    "roi_source": "PLACEHOLDER_ROI_SOURCE",
    "nipple_x": "nipple_x",
    "nipple_y": "nipple_y",
    "nipple_confidence": "PLACEHOLDER_NIPPLE_CONFIDENCE",
    "pnl_slope": "pnl_slope",
    "finding_number": "numfind",
    "finding_laterality": "side",
    "finding_location": "location",
    "finding_depth": "depth",
    "finding_distance": "distance",
    "finding_assessment": "asses",
    "procedure_laterality": "bside",
    "procedure_date": "procdate_anon",
    "procedure_type": "type",
    "pathology_severity": "path_severity",
    "pathology_diagnosis_prefix": "path",
}


DEFAULT_EMBED_REQUIRED_IMAGE_COLUMNS = (
    "image_path",
    "image_laterality",
    "image_view",
)


DEFAULT_EMBED_REQUIRED_ROI_COLUMNS = ("roi_coords",)


DEFAULT_EMBED_REQUIRED_FINDING_COLUMNS = (
    "accession",
    "finding_number",
    "finding_laterality",
)
