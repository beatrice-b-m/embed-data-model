"""EMBED table builders for clinical rows and image metadata rows.

The public EMBED tables have two different meanings: MagView clinical rows
describe findings and finding-owned procedures, while image metadata rows
describe files and optional image-local ROIs. This adapter keeps those sources
separate and only links them through explicit side-aware join helpers.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from embed_toolkit.clinical.exams import BreastSide, Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.procedures import PathologyEvent, Procedure
from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.core.primitives import (
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewPosition,
)
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.rois import RegionOfInterest


Row = Mapping[str, Any]


@dataclass(frozen=True)
class EmbedClinicalTables:
    """Clinical objects built from MagView-derived rows."""

    patients: Tuple[Patient, ...]
    exams: Tuple[Exam, ...]
    findings: Tuple[Finding, ...]
    breast_sides: Tuple[BreastSide, ...]


@dataclass(frozen=True)
class EmbedImageTables:
    """Image objects built from image metadata rows."""

    images: Tuple[MammogramImage, ...]
    rois: Tuple[RegionOfInterest, ...]


@dataclass(frozen=True)
class FindingImageJoin:
    """An intentional clinical-to-image side-aware join result."""

    finding: Finding
    images: Tuple[MammogramImage, ...]


@dataclass(frozen=True)
class _ColumnAliases:
    patient_id: Tuple[str, ...]
    birth_year: Tuple[str, ...] = ("birth_year", "PatientBirthYear")
    sex: Tuple[str, ...] = ("sex", "PatientSex")
    accession: Tuple[str, ...] = ()
    exam_date: Tuple[str, ...] = ()
    exam_description: Tuple[str, ...] = ("exam_description", "StudyDescription")
    finding_number: Tuple[str, ...] = ()
    clinical_side: Tuple[str, ...] = ()
    finding_type: Tuple[str, ...] = ("finding_type", "massshape", "finding")
    assessment: Tuple[str, ...] = ()
    procedure_id: Tuple[str, ...] = ("procedure_id", "proc_id")
    procedure_type: Tuple[str, ...] = ()
    procedure_date: Tuple[str, ...] = ()
    pathology_id: Tuple[str, ...] = ("pathology_id", "path_id")
    pathology_diagnosis: Tuple[str, ...] = ("pathology_diagnosis", "path_diag")
    pathology_category: Tuple[str, ...] = ()
    pathology_date: Tuple[str, ...] = ("pathology_date", "path_date")
    pathology_malignant: Tuple[str, ...] = ("pathology_malignant", "malignant")
    image_id: Tuple[str, ...] = ()
    image_side: Tuple[str, ...] = ()
    view_position: Tuple[str, ...] = ()
    modality: Tuple[str, ...] = ()
    height: Tuple[str, ...] = ()
    width: Tuple[str, ...] = ()
    frame_count: Tuple[str, ...] = ()
    study_uid: Tuple[str, ...] = ("StudyInstanceUID", "study_instance_uid")
    series_uid: Tuple[str, ...] = ()
    sop_uid: Tuple[str, ...] = ()
    patient_orientation: Tuple[str, ...] = ()
    coordinate_frame_id: Tuple[str, ...] = ()
    roi_id: Tuple[str, ...] = ("roi_id", "ROI_ID")
    roi_source: Tuple[str, ...] = ()
    roi_confidence: Tuple[str, ...] = ("roi_confidence", "ROI_confidence")
    roi_coordinates: Tuple[str, ...] = ()
    roi_frames: Tuple[str, ...] = ()
    y_min: Tuple[str, ...] = ("y_min", "YMin")
    x_min: Tuple[str, ...] = ("x_min", "XMin")
    y_max: Tuple[str, ...] = ("y_max", "YMax")
    x_max: Tuple[str, ...] = ("x_max", "XMax")


_MISSING = object()


def _column_aliases(config: Optional[EmbedColumnConfig]) -> _ColumnAliases:
    columns = config or default_embed_columns()
    return _ColumnAliases(
        patient_id=_aliases(columns.patient_id, "patient_id", "PatientID"),
        accession=_aliases(columns.accession, "accession_number", "AccessionNumber"),
        exam_date=_aliases(columns.study_date, "exam_date", "StudyDate"),
        finding_number=_aliases(columns.finding_number, "finding_number"),
        clinical_side=_aliases(columns.finding_laterality, "laterality"),
        assessment=_aliases(columns.finding_assessment, "assessment", "birads"),
        procedure_type=_aliases(columns.procedure_type, "procedure_type", "proc_type"),
        procedure_date=_aliases(columns.procedure_date, "procedure_date", "proc_date"),
        pathology_category=_aliases(
            columns.pathology_severity,
            "pathology_category",
            "path_result",
        ),
        image_id=_aliases(columns.image_id, "image_id", "ImageID", columns.image_path),
        image_side=_aliases(columns.image_laterality, "image_laterality"),
        view_position=_aliases(columns.image_view, "view_position"),
        modality=_aliases(columns.image_modality, "ImageType", "modality"),
        height=_aliases(columns.image_height, "height", "image_height"),
        width=_aliases(columns.image_width, "width", "image_width"),
        frame_count=_aliases(columns.image_frames, "NumberOfFrames", "frame_count"),
        series_uid=_aliases(columns.series_id, "SeriesInstanceUID", "series_instance_uid"),
        sop_uid=_aliases(columns.sop_instance_uid, "SOPInstanceUID", "sop_instance_uid"),
        patient_orientation=_aliases(columns.image_orientation, "patient_orientation"),
        coordinate_frame_id=_aliases(
            columns.acquisition_group_id,
            "coordinate_frame_id",
        ),
        roi_source=_aliases(columns.roi_source, "roi_source", "ROI_source"),
        roi_coordinates=_aliases(columns.roi_coords, "roi_coordinates"),
        roi_frames=_aliases(columns.roi_frames, "ROI_frames", "roi_frames"),
    )


def _aliases(*names: str) -> Tuple[str, ...]:
    ordered = []
    for name in names:
        if name and name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def build_clinical_tables(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> EmbedClinicalTables:
    """Build patients, exams, sides, findings, procedures, and pathology."""

    column_aliases = _column_aliases(columns)
    patients: dict[str, Patient] = {}
    exams: dict[str, Exam] = {}

    for row in rows:
        patient_id = (
            _string_value(_get(row, column_aliases.patient_id)) or "UNKNOWN_PATIENT"
        )
        accession = _required_string(row, column_aliases.accession, "accession_number")
        patient = patients.setdefault(
            patient_id,
            Patient(
                patient_id=patient_id,
                sex=_string_value(_get(row, column_aliases.sex)),
                birth_year=_optional_int(_get(row, column_aliases.birth_year)),
            ),
        )
        exam = exams.get(accession)
        if exam is None:
            exam = Exam(
                accession_number=accession,
                patient_id=patient_id,
                exam_date=_string_value(_get(row, column_aliases.exam_date)),
                description=_string_value(_get(row, column_aliases.exam_description)),
            )
            exams[accession] = patient.add_exam(exam)
        else:
            patient.add_exam(exam)

        for side in _clinical_sides(_get(row, column_aliases.clinical_side)):
            finding = Finding(
                accession_number=accession,
                laterality=side,
                finding_number=_finding_number(row, column_aliases),
                finding_type=_string_value(_get(row, column_aliases.finding_type)),
                assessment=_string_value(_get(row, column_aliases.assessment)),
                raw_source_fields=dict(row),
            )
            finding = exam.add_finding(finding)
            procedure = _procedure_from_row(
                row,
                column_aliases,
                accession,
                side,
                finding.finding_number,
            )
            if procedure is not None:
                finding.add_procedure(procedure)

    ordered_patients = tuple(patients.values())
    ordered_exams = tuple(exams.values())
    ordered_findings = tuple(finding for exam in ordered_exams for finding in exam.findings)
    ordered_sides = tuple(
        side for exam in ordered_exams for side in exam.breast_sides.values()
    )
    return EmbedClinicalTables(
        patients=ordered_patients,
        exams=ordered_exams,
        findings=ordered_findings,
        breast_sides=ordered_sides,
    )


def build_image_tables(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> EmbedImageTables:
    """Build images and image-local ROIs from image metadata rows."""

    column_aliases = _column_aliases(columns)
    images: list[MammogramImage] = []
    rois: list[RegionOfInterest] = []
    seen_image_ids: set[str] = set()

    for row in rows:
        image_id = _required_string(row, column_aliases.image_id, "image_id")
        coordinate_frame_id = _string_value(_get(row, column_aliases.coordinate_frame_id))
        if image_id not in seen_image_ids:
            images.append(
                MammogramImage(
                    image_id=image_id,
                    laterality=Laterality.coerce(_get(row, column_aliases.image_side)),
                    view_position=ViewPosition.coerce(
                        _get(row, column_aliases.view_position)
                    ),
                    modality=ImageModality.coerce(_get(row, column_aliases.modality)),
                    height=_optional_int(_get(row, column_aliases.height)),
                    width=_optional_int(_get(row, column_aliases.width)),
                    frame_count=_optional_int(_get(row, column_aliases.frame_count)),
                    accession_number=_string_value(_get(row, column_aliases.accession)),
                    study_instance_uid=_string_value(
                        _get(row, column_aliases.study_uid)
                    ),
                    series_instance_uid=_string_value(
                        _get(row, column_aliases.series_uid)
                    ),
                    sop_instance_uid=_string_value(_get(row, column_aliases.sop_uid)),
                    patient_orientation=_patient_orientation(row, column_aliases),
                    coordinate_frame_id=coordinate_frame_id,
                )
            )
            seen_image_ids.add(image_id)
        rois.extend(_rois_from_row(row, column_aliases, image_id, coordinate_frame_id))

    return EmbedImageTables(images=tuple(images), rois=tuple(rois))


def join_findings_to_images(
    findings: Iterable[Finding],
    images: Iterable[MammogramImage],
) -> Tuple[FindingImageJoin, ...]:
    """Join clinical findings to images by accession and compatible side."""

    image_list = tuple(images)
    joins = []
    for finding in findings:
        compatible_sides = _join_sides(finding.laterality)
        joins.append(
            FindingImageJoin(
                finding=finding,
                images=tuple(
                    image
                    for image in image_list
                    if image.accession_number == finding.accession_number
                    and image.laterality in compatible_sides
                ),
            )
        )
    return tuple(joins)


def build_patients(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[Patient, ...]:
    """Convenience wrapper returning only patient aggregates."""

    return build_clinical_tables(rows, columns=columns).patients


def build_exams(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[Exam, ...]:
    """Convenience wrapper returning only exam aggregates."""

    return build_clinical_tables(rows, columns=columns).exams


def build_images(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[MammogramImage, ...]:
    """Convenience wrapper returning only image objects."""

    return build_image_tables(rows, columns=columns).images


def build_rois(
    rows: Iterable[Row],
    *,
    columns: Optional[EmbedColumnConfig] = None,
) -> Tuple[RegionOfInterest, ...]:
    """Convenience wrapper returning only ROI objects."""

    return build_image_tables(rows, columns=columns).rois


def _clinical_sides(value: Any) -> Tuple[Laterality, ...]:
    side = Laterality.coerce(value)
    if side is Laterality.BILATERAL:
        return side.expand()
    return (side,)


def _join_sides(value: Any) -> Tuple[Laterality, ...]:
    side = Laterality.coerce(value)
    if side is Laterality.UNKNOWN:
        return (Laterality.LEFT, Laterality.RIGHT)
    expanded = side.expand()
    return expanded if expanded else (side,)


def _procedure_from_row(
    row: Row,
    columns: _ColumnAliases,
    accession: str,
    side: Laterality,
    finding_number: str,
) -> Optional[Procedure]:
    procedure_id = _string_value(_get(row, columns.procedure_id))
    procedure_type = _string_value(_get(row, columns.procedure_type))
    procedure_date = _string_value(_get(row, columns.procedure_date))
    if not any((procedure_id, procedure_type, procedure_date)):
        return None

    procedure = Procedure(
        procedure_id=procedure_id,
        procedure_type=procedure_type,
        accession_number=accession,
        laterality=side,
        finding_number=finding_number,
        performed_date=procedure_date,
        raw_source_fields=dict(row),
    )
    pathology = _pathology_from_row(row, columns)
    if pathology is not None:
        procedure.add_pathology_event(pathology)
    return procedure


def _pathology_from_row(row: Row, columns: _ColumnAliases) -> Optional[PathologyEvent]:
    pathology_id = _string_value(_get(row, columns.pathology_id))
    diagnosis = _string_value(_get(row, columns.pathology_diagnosis))
    category = _string_value(_get(row, columns.pathology_category))
    event_date = _string_value(_get(row, columns.pathology_date))
    malignant = _optional_bool(_get(row, columns.pathology_malignant))
    if not any((pathology_id, diagnosis, category, event_date, malignant is not None)):
        return None
    return PathologyEvent(
        pathology_id=pathology_id,
        diagnosis=diagnosis,
        result_category=category,
        event_date=event_date,
        malignant=malignant,
        raw_source_fields=dict(row),
    )


def _rois_from_row(
    row: Row,
    columns: _ColumnAliases,
    image_id: str,
    coordinate_frame_id: Optional[str],
) -> Tuple[RegionOfInterest, ...]:
    coordinate_sets = _coordinate_sets(row, columns)
    if not coordinate_sets:
        return ()

    frames = _sequence_value(_get(row, columns.roi_frames))
    roi_ids = _sequence_value(_get(row, columns.roi_id))
    source = _string_value(_get(row, columns.roi_source))
    confidence = _optional_float(_get(row, columns.roi_confidence))
    rois = []
    for index, coordinates in enumerate(coordinate_sets):
        rois.append(
            RegionOfInterest.from_embed_coordinates(
                coordinates=coordinates,
                roi_id=_indexed_value(roi_ids, index)
                or _string_value(_get(row, columns.roi_id))
                or f"{image_id}:roi:{index + 1}",
                image_id=image_id,
                frame_index=_optional_int(_indexed_value(frames, index)),
                source=source,
                confidence=confidence,
                coordinate_frame_id=coordinate_frame_id,
            )
        )
    return tuple(rois)


def _coordinate_sets(
    row: Row,
    columns: _ColumnAliases,
) -> Tuple[Tuple[float, float, float, float], ...]:
    raw_coordinates = _get(row, columns.roi_coordinates)
    if raw_coordinates is not _MISSING:
        parsed = _sequence_value(raw_coordinates)
        if len(parsed) == 4 and not any(isinstance(item, (list, tuple)) for item in parsed):
            return (_coordinate_box(parsed),)
        return tuple(_coordinate_box(_sequence_value(item)) for item in parsed)

    values = (
        _get(row, columns.y_min),
        _get(row, columns.x_min),
        _get(row, columns.y_max),
        _get(row, columns.x_max),
    )
    if any(value is _MISSING or _is_blank(value) for value in values):
        return ()
    return (_coordinate_box(values),)


def _coordinate_box(values: Sequence[Any]) -> Tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError("ROI coordinates must have four values")
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _patient_orientation(
    row: Row,
    columns: _ColumnAliases,
) -> Optional[PatientOrientation]:
    value = _get(row, columns.patient_orientation)
    if value is _MISSING or _is_blank(value):
        return None
    return PatientOrientation.coerce(value)


def _finding_number(row: Row, columns: _ColumnAliases) -> str:
    value = _get(row, columns.finding_number)
    if value is _MISSING or _is_blank(value):
        return "0"
    return str(value)


def _required_string(row: Row, names: Tuple[str, ...], logical_name: str) -> str:
    value = _get(row, names)
    text = _string_value(value)
    if text is None:
        raise ValueError(f"Missing required EMBED column: {logical_name}")
    return text


def _get(row: Row, names: Tuple[str, ...]) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return _MISSING


def _sequence_value(value: Any) -> Tuple[Any, ...]:
    if value is _MISSING or _is_blank(value):
        return ()
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return (value,)
        return _sequence_value(parsed)
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _indexed_value(values: Tuple[Any, ...], index: int) -> Any:
    if not values:
        return _MISSING
    if index < len(values):
        return values[index]
    return _MISSING


def _string_value(value: Any) -> Optional[str]:
    if value is _MISSING or _is_blank(value):
        return None
    return str(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is _MISSING or _is_blank(value):
        return None
    return int(value)


def _optional_float(value: Any) -> Optional[float]:
    if value is _MISSING or _is_blank(value):
        return None
    return float(value)


def _optional_bool(value: Any) -> Optional[bool]:
    if value is _MISSING or _is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in {"1", "Y", "YES", "TRUE", "MALIGNANT"}:
        return True
    if text in {"0", "N", "NO", "FALSE", "BENIGN"}:
        return False
    return None


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}
