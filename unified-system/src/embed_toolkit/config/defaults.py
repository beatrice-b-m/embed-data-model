"""Default source-column names for EMBED adapters."""

DEFAULT_EMBED_COLUMN_NAMES = {
    "patient_id": "empi_anon",
    # Internal V2 exposes an anonymized birth date, not a governed birth-year
    # occurrence. Keep this configurable placeholder for custom profiles while
    # the built-in Internal V2 contract marks it unavailable.
    "birth_year": "birth_year",
    "sex": "GENDER_DESC",
    "cohort_id": "cohort_num",
    "accession": "acc_anon",
    "study_date": "studydate_anon",
    "exam_description": "desc",
    "image_path": "anon_dicom_path",
    "image_id": "anon_dicom_path",
    "image_laterality": "ImageLateralityFinal",
    "image_view": "ViewPosition",
    "image_orientation": "PatientOrientation",
    "image_height": "Rows",
    "image_width": "Columns",
    "image_frames": "ImagesInAcquisition",
    "image_modality": "Modality",
    "derived_image_type": "FinalImageType",
    "series_id": "SeriesInstanceUID",
    "sop_instance_uid": "anon_dicom_path",
    "acquisition_group_id": "acquisition_group_id",
    "roi_coords": "ROI_coords",
    "roi_frames": "ROI_frames",
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
    "finding_recommendation": "recc",
    "procedure_laterality": "bside",
    "procedure_date": "procdate_anon",
    "procedure_type": "type",
    "pathology_severity": "path_severity",
    "pathology_report_date": "pdate_anon",
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
