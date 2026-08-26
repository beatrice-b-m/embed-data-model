"""Patient and exam ingestion for the EMBED source."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from math import isfinite
from numbers import Integral, Real
from typing import Any, Callable, Iterator, Mapping, Optional, Union

from embed_toolkit.core.tables import (
    TableNormalizationError,
    TableRecord,
    iter_records,
)
from embed_toolkit.clinical.associations import AssociationLink, AttributionStatus
from embed_toolkit.clinical.attributes import PatientAttributeName
from embed_toolkit.clinical.findings import (
    FindingNormalizationEvidence,
    FindingNormalizationWarning,
)
from embed_toolkit.core.anatomy import AnatomicalPosition, Quadrant
from embed_toolkit.core.graph import DatasetGraph
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.source import Issue, SourceRef
from embed_toolkit.sources.embed.columns import resolve_columns
from embed_toolkit.sources.embed.histories import (
    normalize_medication_history,
    normalize_procedure_history,
)
from embed_toolkit.sources.embed.magview import normalize_magview_location
from embed_toolkit.sources.embed.procedures_pathology import (
    normalize_pathology,
    normalize_procedure,
)


SourceKeySelector = Union[str, Callable[[Mapping[str, Any]], Any]]
_MAGVIEW_SOURCE_KEY = object()


@dataclass(frozen=True)
class LoadReport:
    """The graph and invocation-local issues produced by one load."""

    graph: DatasetGraph
    issues: tuple[Issue, ...]
    source_scope: str


def load_embed(
    *,
    patients: Any = None,
    exams: Any = None,
    findings: Any = None,
    images: Any = None,
    rois: Any = None,
    hormone_history: Any = None,
    procedure_history: Any = None,
    procedures: Any = None,
    pathology: Any = None,
    magview: Any = None,
    into: Optional[DatasetGraph] = None,
    source_scope: Optional[str] = None,
    identity_namespace: Optional[str] = None,
    source_keys: Optional[Mapping[str, SourceKeySelector]] = None,
    columns: Optional[Mapping[str, Mapping[str, Optional[str]]]] = None,
    mode: str = "audit",
    retain_raw: bool = False,
) -> LoadReport:
    """Load any supplied EMBED clinical grain tables into one graph.

    Tables may be pandas DataFrames or iterables of row mappings. Every table
    is optional, and an exam is safe to load without either a patient table or
    a populated patient reference.
    """

    if into is not None and not isinstance(into, DatasetGraph):
        raise TypeError("into must be a DatasetGraph or None")
    if mode not in {"audit", "strict"}:
        raise ValueError("mode must be 'audit' or 'strict'")
    if not isinstance(retain_raw, bool):
        raise TypeError("retain_raw must be a bool")
    if source_scope is not None and (
        not isinstance(source_scope, str) or not source_scope.strip()
    ):
        raise ValueError("source_scope must be a non-empty string or None")
    if identity_namespace is not None and (
        not isinstance(identity_namespace, str) or not identity_namespace.strip()
    ):
        raise ValueError("identity_namespace must be a non-empty string or None")

    column_maps = resolve_columns(columns)
    key_selectors = _resolve_source_keys(source_keys)

    # Identity metadata is immutable. Check this before opening a transaction
    # or even consuming a possibly stateful input iterable.
    if (
        into is not None
        and identity_namespace is not None
        and identity_namespace != into.identity_namespace
    ):
        raise ValueError("identity_namespace does not match the target DatasetGraph")

    graph = into or DatasetGraph(
        identity_namespace=identity_namespace,
        source_scope=source_scope,
    )
    resolved_scope = source_scope or graph.source_scope

    with graph.transaction(mode=mode) as transaction:
        _load_patients(
            patients,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["patients"],
            columns=column_maps["patients"],
            retain_raw=retain_raw,
        )
        _load_exams(
            exams,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["exams"],
            columns=column_maps["exams"],
            retain_raw=retain_raw,
        )
        _load_findings(
            findings,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["findings"],
            columns=column_maps["findings"],
            retain_raw=retain_raw,
        )
        _load_images(
            images,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["images"],
            columns=column_maps["images"],
            retain_raw=retain_raw,
        )
        _load_rois(
            rois,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["rois"],
            columns=column_maps["rois"],
            retain_raw=retain_raw,
        )
        _load_histories(
            hormone_history,
            table_name="hormone_history",
            normalizer=normalize_medication_history,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["hormone_history"],
            columns=column_maps["hormone_history"],
            retain_raw=retain_raw,
        )
        _load_magview(
            magview,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["magview"],
            column_maps=column_maps,
            retain_raw=retain_raw,
        )
        _load_procedures(
            procedures,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["procedures"],
            columns=column_maps["procedures"],
            retain_raw=retain_raw,
        )
        _load_pathology(
            pathology,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["pathology"],
            columns=column_maps["pathology"],
            retain_raw=retain_raw,
        )
        _load_histories(
            procedure_history,
            table_name="procedure_history",
            normalizer=normalize_procedure_history,
            transaction=transaction,
            source_scope=resolved_scope,
            source_key=key_selectors["procedure_history"],
            columns=column_maps["procedure_history"],
            retain_raw=retain_raw,
        )

    return LoadReport(
        graph=graph,
        issues=tuple(transaction.issues),
        source_scope=resolved_scope,
    )


def _resolve_source_keys(
    source_keys: Optional[Mapping[str, SourceKeySelector]],
) -> dict[str, Optional[SourceKeySelector]]:
    resolved: dict[str, Optional[SourceKeySelector]] = {
        "patients": None,
        "exams": None,
        "findings": None,
        "images": None,
        "rois": None,
        "hormone_history": None,
        "procedure_history": None,
        "procedures": None,
        "pathology": None,
        "magview": None,
    }
    if source_keys is None:
        return resolved
    if not isinstance(source_keys, Mapping):
        raise TypeError("source_keys must be a mapping")
    unknown = set(source_keys).difference(resolved)
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(f"Unknown source_keys table(s): {names}")
    for table, selector in source_keys.items():
        if not callable(selector) and not (
            isinstance(selector, str) and selector.strip()
        ):
            raise TypeError(
                f"source_keys[{table!r}] must be a non-empty column name or callable"
            )
        resolved[table] = selector
    return resolved


def _load_magview(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    column_maps: Mapping[str, Mapping[str, Optional[str]]],
    retain_raw: bool,
) -> None:
    """Project one normalized wide row stream through existing grain loaders."""

    projected: dict[str, list[Mapping[Any, Any]]] = {
        "patients": [],
        "exams": [],
        "findings": [],
        "procedures": [],
        "pathology": [],
    }
    for record in _table_records(table, source_key, "magview", transaction):
        source = _record_source(record, source_scope, "magview")
        if not _add_table_issues(record, source, transaction):
            continue
        row = dict(record.mapping)
        row[_MAGVIEW_SOURCE_KEY] = record.source_key
        if _has_semantic_value(row, column_maps["patients"], "patient_id"):
            projected["patients"].append(row)
        if _has_semantic_value(row, column_maps["exams"], "accession"):
            projected["exams"].append(row)
        if _has_semantic_value(row, column_maps["findings"], "finding_number"):
            projected["findings"].append(row)
        if any(
            _has_semantic_value(row, column_maps["procedures"], semantic)
            for semantic in ("performed_date", "procedure_type", "laterality")
        ):
            projected["procedures"].append(row)
        if any(
            _has_semantic_value(row, column_maps["pathology"], semantic)
            for semantic in (
                "diagnosis",
                "result_category",
                "malignant",
                "severity",
                "report_documented_date",
                *(f"descriptor_{index}" for index in range(1, 11)),
            )
        ):
            projected["pathology"].append(row)

    def selector(row: Mapping[Any, Any]) -> Any:
        return row[_MAGVIEW_SOURCE_KEY]

    common = {
        "transaction": transaction,
        "source_scope": source_scope,
        "source_key": selector,
        "retain_raw": retain_raw,
        "source_table": "magview",
    }
    _load_patients(projected["patients"], columns=column_maps["patients"], **common)
    _load_exams(projected["exams"], columns=column_maps["exams"], **common)
    _load_findings(projected["findings"], columns=column_maps["findings"], **common)
    _load_procedures(
        projected["procedures"], columns=column_maps["procedures"], **common
    )
    _load_pathology(
        projected["pathology"], columns=column_maps["pathology"], **common
    )


def _has_semantic_value(
    row: Mapping[Any, Any],
    columns: Mapping[str, Optional[str]],
    semantic: str,
) -> bool:
    column = columns[semantic]
    return column is not None and not _is_missing(row.get(column))


def _load_patients(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
    source_table: str = "patients",
) -> None:
    patient_column = columns["patient_id"]
    assert patient_column is not None
    for record in _table_records(table, source_key, source_table, transaction):
        source = _record_source(record, source_scope, source_table)
        if not _add_table_issues(record, source, transaction):
            continue
        raw_identifier = record.mapping.get(patient_column)
        patient_id = _normalize_identifier(raw_identifier)
        if patient_id is None:
            transaction.add_issue(
                _identity_issue("patient_id", raw_identifier, source, patient_column)
            )
            continue
        values = {"patient_id": patient_id}
        attributes: dict[PatientAttributeName, Any] = {}
        sex_column = columns["sex"]
        if sex_column is not None and sex_column in record.mapping:
            attributes[PatientAttributeName.SEX] = _mapped_text(
                record.mapping, sex_column
            )
        birth_year_column = columns["birth_year"]
        if birth_year_column is not None and birth_year_column in record.mapping:
            raw_birth_year = _mapped_value(record.mapping, birth_year_column)
            if raw_birth_year is None:
                attributes[PatientAttributeName.BIRTH_YEAR] = None
            else:
                birth_year = _exact_integer(raw_birth_year)
                if birth_year is None:
                    transaction.add_issue(
                        Issue(
                            code="invalid_patient_attribute_value",
                            message="birth_year must represent an exact finite integer",
                            source=source,
                            context={
                                "attribute": "birth_year",
                                "column": birth_year_column,
                                "value": raw_birth_year,
                            },
                        )
                    )
                else:
                    attributes[PatientAttributeName.BIRTH_YEAR] = birth_year
        context_column = columns["context_date"]
        raw_context = _mapped_value(record.mapping, context_column)
        context_date = _calendar_date(raw_context)
        if raw_context is not None and context_date is None and attributes:
            transaction.add_issue(
                Issue(
                    code="invalid_patient_attribute_context_date",
                    message="patient attribute context date could not be parsed",
                    source=source,
                    context={"column": context_column, "value": raw_context},
                )
            )
        transaction.upsert_patient(
            patient_id,
            source,
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
            attributes=attributes,
            context_date=context_date,
        )


def _load_exams(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
    source_table: str = "exams",
) -> None:
    accession_column = columns["accession"]
    assert accession_column is not None
    for record in _table_records(table, source_key, source_table, transaction):
        source = _record_source(record, source_scope, source_table)
        if not _add_table_issues(record, source, transaction):
            continue
        raw_accession = record.mapping.get(accession_column)
        accession = _normalize_identifier(raw_accession)
        if accession is None:
            transaction.add_issue(
                _identity_issue("accession", raw_accession, source, accession_column)
            )
            continue

        patient_column = columns["patient_id"]
        raw_patient_id = (
            record.mapping.get(patient_column) if patient_column is not None else None
        )
        patient_id = _normalize_identifier(raw_patient_id)
        if (
            patient_column is not None
            and not _is_missing(raw_patient_id)
            and patient_id is None
        ):
            transaction.add_issue(
                Issue(
                    code="invalid_patient_id",
                    message=(
                        "patient_id is not a supported EMBED identifier; "
                        "the exam was retained without a patient link"
                    ),
                    severity="error",
                    source=source,
                    context={
                        "column": patient_column,
                        "value": raw_patient_id,
                    },
                )
            )
        exam_date = _mapped_text(record.mapping, columns["exam_date"])
        description = _mapped_text(record.mapping, columns["exam_description"])
        values = {
            "accession": accession,
            "patient_id": patient_id,
            "exam_date": exam_date,
            "exam_description": description,
            "exam_date_present": (
                columns["exam_date"] is not None
                and columns["exam_date"] in record.mapping
            ),
            "exam_description_present": (
                columns["exam_description"] is not None
                and columns["exam_description"] in record.mapping
            ),
        }
        transaction.upsert_exam(
            accession,
            source,
            patient_id=patient_id,
            exam_date=exam_date,
            description=description,
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
        )


def _load_findings(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
    source_table: str = "findings",
) -> None:
    accession_column = columns["accession"]
    number_column = columns["finding_number"]
    assert accession_column is not None and number_column is not None
    for record in _table_records(table, source_key, source_table, transaction):
        source = _record_source(record, source_scope, source_table)
        if not _add_table_issues(record, source, transaction):
            continue
        raw_accession = record.mapping.get(accession_column)
        accession = _normalize_identifier(raw_accession)
        if accession is None:
            transaction.add_issue(
                _identity_issue("accession", raw_accession, source, accession_column)
            )
            continue
        raw_number = record.mapping.get(number_column)
        finding_number = _normalize_identifier(raw_number)
        if finding_number is None:
            transaction.add_issue(
                _identity_issue("finding_number", raw_number, source, number_column)
            )
            continue

        laterality_column = columns["laterality"]
        raw_laterality = (
            record.mapping.get(laterality_column)
            if laterality_column is not None
            else None
        )
        laterality = Laterality.coerce(_plain_scalar(raw_laterality))
        if not _is_missing(raw_laterality) and laterality is Laterality.UNKNOWN:
            transaction.add_issue(
                Issue(
                    code="unsupported_finding_laterality",
                    message="finding laterality was retained as unknown",
                    severity="warning",
                    source=source,
                    context={"column": laterality_column, "value": raw_laterality},
                )
            )
        values = {
            "accession": accession,
            "finding_number": finding_number,
            "laterality": laterality.value,
            "finding_type": _mapped_text(record.mapping, columns["finding_type"]),
            "assessment": _mapped_text(record.mapping, columns["assessment"]),
            "recommendation": _mapped_text(record.mapping, columns["recommendation"]),
        }
        anatomy = _finding_anatomy(
            record.mapping,
            columns,
            source,
            laterality,
            transaction,
        )
        transaction.upsert_finding(
            accession,
            finding_number,
            source,
            laterality=laterality,
            finding_type=values["finding_type"],
            assessment=values["assessment"],
            recommendation=values["recommendation"],
            anatomical_position=anatomy["position"],
            location_codes=anatomy["location_codes"],
            depth_codes=anatomy["depth_codes"],
            distance_codes=anatomy["distance_codes"],
            anatomy_evidence=anatomy["evidence"],
            anatomy_warnings=anatomy["warnings"],
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
        )


def _finding_anatomy(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
    laterality: Laterality,
    transaction: Any,
) -> dict[str, Any]:
    location_column = columns["location"]
    depth_column = columns["depth"]
    distance_column = columns["distance"]
    side_column = columns["laterality"]
    location_present = location_column is not None and location_column in row
    depth_present = depth_column is not None and depth_column in row
    distance_present = distance_column is not None and distance_column in row
    location_value = row.get(location_column) if location_present else None
    depth_value = row.get(depth_column) if depth_present else None
    distance_value = row.get(distance_column) if distance_present else None
    location_codes = {location_column: location_value} if location_present else {}
    depth_codes = {depth_column: depth_value} if depth_present else {}
    distance_codes = {distance_column: distance_value} if distance_present else {}
    evidence: list[FindingNormalizationEvidence] = []
    warnings: list[FindingNormalizationWarning] = []
    position: Optional[AnatomicalPosition] = None
    has_location = location_present and not _is_missing(location_value)
    has_depth = depth_present and not _is_missing(depth_value)
    if has_location or has_depth:
        normalized = normalize_magview_location(
            laterality=laterality,
            location_code=location_value if has_location else None,
            depth_code=depth_value if has_depth else None,
        )
        source_fields = {
            "location_code": (location_column, location_value),
            "depth_code": (depth_column, depth_value),
            "laterality": (side_column, row.get(side_column)),
        }
        for item in normalized.evidence:
            source_field, raw_value = source_fields[item.field]
            if source_field is not None:
                evidence.append(
                    FindingNormalizationEvidence(
                        source=source,
                        source_field=source_field,
                        raw_value=raw_value,
                        normalized_kind=item.normalized_kind,
                        normalized_value=(
                            item.normalized_value
                            if laterality.is_unilateral
                            else None
                        ),
                    )
                )
        for warning in normalized.warnings:
            source_field, raw_value = source_fields.get(
                warning.field, (None, warning.raw_value)
            )
            warnings.append(
                FindingNormalizationWarning(
                    source=source,
                    source_field=source_field,
                    raw_value=raw_value,
                    code=warning.code,
                    message=warning.message,
                )
            )
        position = (
            normalized.position
            if laterality.is_unilateral
            else AnatomicalPosition(
                laterality=laterality,
                quadrant=Quadrant(laterality=laterality),
            )
        )

    has_distance = distance_present and not _is_missing(distance_value)
    if has_distance:
        distance: Optional[float]
        try:
            if isinstance(distance_value, bool):
                raise ValueError
            distance = float(distance_value)
            if not isfinite(distance) or distance < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            distance = None
            transaction.add_issue(
                Issue(
                    code="invalid_finding_distance",
                    message="finding distance must be finite and nonnegative",
                    source=source,
                    context={
                        "source_field": distance_column,
                        "raw_value": distance_value,
                    },
                )
            )
        assert distance_column is not None
        evidence.append(
            FindingNormalizationEvidence(
                source=source,
                source_field=distance_column,
                raw_value=distance_value,
                normalized_kind="distance_from_nipple_cm",
                normalized_value=distance,
            )
        )
        if position is None and distance is not None and laterality.is_unilateral:
            position = AnatomicalPosition(
                laterality=laterality,
                quadrant=Quadrant(laterality=laterality),
            )
        if position is not None and distance is not None:
            position = replace(position, distance_from_nipple_cm=distance)

    if (
        (has_location or has_depth or has_distance)
        and not laterality.is_unilateral
        and not any(warning.code == "unsupported_laterality" for warning in warnings)
    ):
        warnings.append(
            FindingNormalizationWarning(
                source=source,
                source_field=side_column,
                raw_value=row.get(side_column) if side_column is not None else None,
                code="unsupported_laterality",
                message="finding anatomy requires left or right laterality",
            )
        )
    return {
        "position": position,
        "location_codes": location_codes,
        "depth_codes": depth_codes,
        "distance_codes": distance_codes,
        "evidence": tuple(evidence),
        "warnings": tuple(warnings),
    }


def _load_images(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
) -> None:
    image_column = columns["image_id"]
    assert image_column is not None
    for record in _table_records(table, source_key, "images", transaction):
        source = _record_source(record, source_scope, "images")
        if not _add_table_issues(record, source, transaction):
            continue
        raw_image_id = record.mapping.get(image_column)
        image_id = _normalize_identifier(raw_image_id)
        if image_id is None:
            transaction.add_issue(
                _identity_issue("image_id", raw_image_id, source, image_column)
            )
            continue
        patient_id = _mapped_identifier(record.mapping, columns["patient_id"])
        accession = _mapped_identifier(record.mapping, columns["accession"])
        raw_laterality = _mapped_value(record.mapping, columns["laterality"])
        raw_view = _mapped_value(record.mapping, columns["view_position"])
        laterality = Laterality.coerce(raw_laterality)
        view_position = ViewPosition.coerce(raw_view)
        source_modality = _mapped_text(record.mapping, columns["modality"])
        derived_image_type = _mapped_text(
            record.mapping, columns["derived_image_type"]
        )
        modality = ImageModality.coerce(source_modality)
        if modality is ImageModality.UNKNOWN:
            modality = ImageModality.coerce(derived_image_type)
        for semantic, raw_value, normalized in (
            ("laterality", raw_laterality, laterality),
            ("view_position", raw_view, view_position),
        ):
            if not _is_missing(raw_value) and normalized.value == "UNKNOWN":
                transaction.add_issue(
                    Issue(
                        code=f"unsupported_image_{semantic}",
                        message=f"image {semantic} was retained as unknown",
                        severity="warning",
                        source=source,
                        context={"value": raw_value},
                    )
                )
        values = {
            "image_id": image_id,
            "patient_id": patient_id,
            "accession": accession,
            "laterality": laterality.value,
            "view_position": view_position.value,
            "modality": modality.value,
            "source_modality": source_modality,
            "derived_image_type": derived_image_type,
            "height": _mapped_positive_int(
                record.mapping, columns["height"], "height", source, transaction
            ),
            "width": _mapped_positive_int(
                record.mapping, columns["width"], "width", source, transaction
            ),
            "frame_count": _mapped_positive_int(
                record.mapping,
                columns["frame_count"],
                "frame_count",
                source,
                transaction,
            ),
            "study_instance_uid": _mapped_text(
                record.mapping, columns["study_instance_uid"]
            ),
            "series_instance_uid": _mapped_text(
                record.mapping, columns["series_instance_uid"]
            ),
            "sop_instance_uid": _mapped_text(
                record.mapping, columns["sop_instance_uid"]
            ),
            "coordinate_frame_id": _mapped_text(
                record.mapping, columns["coordinate_frame_id"]
            ),
        }
        transaction.upsert_image(
            image_id,
            source,
            patient_id=patient_id,
            accession=accession,
            laterality=laterality,
            view_position=view_position,
            modality=modality,
            source_modality=source_modality,
            derived_image_type=derived_image_type,
            height=values["height"],
            width=values["width"],
            frame_count=values["frame_count"],
            study_instance_uid=values["study_instance_uid"],
            series_instance_uid=values["series_instance_uid"],
            sop_instance_uid=values["sop_instance_uid"],
            coordinate_frame_id=values["coordinate_frame_id"],
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
        )


def _load_rois(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
) -> None:
    image_column = columns["image_id"]
    coordinates_column = columns["coordinates"]
    assert image_column is not None and coordinates_column is not None
    for record in _table_records(table, source_key, "rois", transaction):
        source = _record_source(record, source_scope, "rois")
        if not _add_table_issues(record, source, transaction):
            continue
        raw_image_id = record.mapping.get(image_column)
        image_id = _normalize_identifier(raw_image_id)
        if image_id is None:
            transaction.add_issue(
                _identity_issue("image_id", raw_image_id, source, image_column)
            )
            continue
        base_roi_key = _mapped_identifier(record.mapping, columns["roi_key"])
        if base_roi_key is None:
            base_roi_key = json.dumps(
                source.key.to_dict(), sort_keys=True, separators=(",", ":")
            )
        raw_coordinates = record.mapping.get(coordinates_column)
        coordinate_collection = _coordinate_collection(raw_coordinates)
        if coordinate_collection is None:
            transaction.add_issue(
                Issue(
                    code="invalid_roi_coordinates",
                    message="ROI coordinates must contain four finite ordered values",
                    severity="error",
                    source=source,
                    context={
                        "column": coordinates_column,
                        "value": raw_coordinates,
                    },
                )
            )
            continue
        raw_frames = _mapped_value(record.mapping, columns["frame_indices"])
        frame_collections = _roi_frame_collections(
            raw_frames, len(coordinate_collection)
        )
        if frame_collections is None:
            transaction.add_issue(
                Issue(
                    code="invalid_roi_frames",
                    message="ROI frame indices must be unique non-negative integers",
                    severity="error",
                    source=source,
                )
            )
            frame_collections = tuple(() for _ in coordinate_collection)
        derived_flags = _roi_derived_flags(
            _mapped_value(record.mapping, columns["depth_derived"]),
            len(coordinate_collection),
        )
        if derived_flags is None:
            transaction.add_issue(
                Issue(
                    code="invalid_roi_depth_derived",
                    message="ROI derived-depth flags must align with ROI coordinates",
                    severity="warning",
                    source=source,
                )
            )
            derived_flags = tuple(False for _ in coordinate_collection)
        confidence = _optional_confidence(
            _mapped_value(record.mapping, columns["confidence"])
        )
        annotation_source = _mapped_text(
            record.mapping, columns["annotation_source"]
        )
        coordinate_frame_id = _mapped_text(
            record.mapping, columns["coordinate_frame_id"]
        )
        for ordinal, (source_coordinates, frame_indices, derived) in enumerate(
            zip(coordinate_collection, frame_collections, derived_flags)
        ):
            roi_key = (
                base_roi_key
                if len(coordinate_collection) == 1
                else f"{base_roi_key}:{ordinal}"
            )
            y_min, x_min, y_max, x_max = source_coordinates
            coordinates = (y_min, x_min, y_max + 1.0, x_max + 1.0)
            frame_provenance = (
                "derived"
                if derived
                else "source_supplied"
                if frame_indices
                else "unavailable"
            )
            derivation_method = "embed_roi_depth_derived" if derived else None
            values = {
                "image_id": image_id,
                "roi_key": roi_key,
                "coordinates": coordinates,
                "frame_indices": frame_indices,
                "annotation_source": annotation_source,
                "confidence": confidence,
                "coordinate_frame_id": coordinate_frame_id,
                "source_coordinates": source_coordinates,
                "source_coordinate_convention": "inclusive_maxima",
                "frame_provenance": frame_provenance,
                "frame_derivation_method": derivation_method,
            }
            transaction.upsert_roi(
                image_id,
                roi_key,
                source,
                coordinates=coordinates,
                frame_indices=frame_indices,
                annotation_source=annotation_source,
                confidence=confidence,
                coordinate_frame_id=coordinate_frame_id,
                source_coordinates=source_coordinates,
                source_coordinate_convention="inclusive_maxima",
                frame_provenance=frame_provenance,
                frame_derivation_method=derivation_method,
                values=values,
                metadata=_evidence(record.mapping, retain_raw),
            )


def _load_histories(
    table: Any,
    *,
    table_name: str,
    normalizer: Callable[..., Any],
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
) -> None:
    patient_column = columns["patient_id"]
    assert patient_column is not None
    for record in _table_records(table, source_key, table_name, transaction):
        source = _record_source(record, source_scope, table_name)
        if not _add_table_issues(record, source, transaction):
            continue
        raw_patient_id = record.mapping.get(patient_column)
        patient_id = _normalize_identifier(raw_patient_id)
        if patient_id is None:
            transaction.add_issue(
                _identity_issue("patient_id", raw_patient_id, source, patient_column)
            )
            continue
        transaction.upsert_patient(
            patient_id,
            source,
            values={"patient_id": patient_id},
            metadata=_evidence(record.mapping, retain_raw),
        )
        observation, issues = normalizer(
            record.mapping, columns, source, patient_id
        )
        for issue in issues:
            transaction.add_issue(issue)
        if observation is None:
            continue
        values = dict(observation.to_dict())
        values.pop("source", None)
        transaction.upsert_history(
            observation,
            source,
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
        )


def _load_procedures(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
    source_table: str = "procedures",
) -> None:
    for record in _table_records(table, source_key, source_table, transaction):
        source = _record_source(record, source_scope, source_table)
        if not _add_table_issues(record, source, transaction):
            continue
        patient_id = _mapped_identifier(record.mapping, columns["patient_id"])
        if patient_id is not None:
            transaction.upsert_patient(
                patient_id,
                source,
                values={"patient_id": patient_id},
                metadata=_evidence(record.mapping, retain_raw),
            )
        procedure, issues = normalize_procedure(record.mapping, columns, source)
        for issue in issues:
            transaction.add_issue(issue)
        if procedure is None:
            continue
        transaction.upsert_procedure(
            procedure,
            source,
            values=procedure.identity.to_dict(),
            metadata=_evidence(record.mapping, retain_raw),
        )
        procedure_identity = procedure.identity
        source_identity = (
            procedure_identity.patient_id,
            procedure_identity.performed_date,
            procedure_identity.procedure_type,
            procedure_identity.laterality.value,
        )
        for target_kind, target_identity in _clinical_targets(
            record.mapping, columns, include_procedure=False
        ):
            transaction.add_link(
                AssociationLink(
                    source_kind="procedure",
                    source_identity=source_identity,
                    target_kind=target_kind,
                    target_identity=target_identity,
                    status=AttributionStatus.SOURCE_COLOCATED,
                    source=source,
                ),
                source,
            )


def _load_pathology(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
    source_table: str = "pathology",
) -> None:
    for record in _table_records(table, source_key, source_table, transaction):
        source = _record_source(record, source_scope, source_table)
        if not _add_table_issues(record, source, transaction):
            continue
        diagnosis, observations, issues = normalize_pathology(
            record.mapping, columns, source
        )
        for issue in issues:
            transaction.add_issue(issue)
        if diagnosis is not None:
            values = {
                "diagnosis": diagnosis.diagnosis,
                "result_category": diagnosis.result_category,
                "malignant": diagnosis.malignant,
                "severity": (
                    int(diagnosis.severity)
                    if diagnosis.severity is not None
                    else None
                ),
                "raw_severity": diagnosis.raw_severity,
                "report_documented_date": diagnosis.report_documented_date,
            }
            transaction.upsert_pathology_diagnosis(
                diagnosis,
                source,
                values=values,
                metadata=_evidence(record.mapping, retain_raw),
            )
            _add_pathology_links(
                transaction,
                record.mapping,
                columns,
                source,
                source_kind="pathology_diagnosis",
                source_identity=("diagnosis", _source_identity_text(source)),
            )
        for observation in observations:
            transaction.upsert_pathology_observation(
                observation,
                source,
                values={
                    "descriptor": observation.descriptor,
                    "source_slot": observation.source_slot,
                    "source_ordinal": observation.source_ordinal,
                },
                metadata=_evidence(record.mapping, retain_raw),
            )
            _add_pathology_links(
                transaction,
                record.mapping,
                columns,
                source,
                source_kind="pathology_observation",
                source_identity=(
                    "observation",
                    observation.source_slot,
                    _source_identity_text(source),
                ),
            )


def _add_pathology_links(
    transaction: Any,
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
    *,
    source_kind: str,
    source_identity: tuple[str, ...],
) -> None:
    for target_kind, target_identity in _clinical_targets(
        row, columns, include_procedure=True
    ):
        transaction.add_link(
            AssociationLink(
                source_kind=source_kind,
                source_identity=source_identity,
                target_kind=target_kind,
                target_identity=target_identity,
                status=AttributionStatus.SOURCE_COLOCATED,
                source=source,
            ),
            source,
        )


def _clinical_targets(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    *,
    include_procedure: bool,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    targets: list[tuple[str, tuple[str, ...]]] = []
    patient_id = _mapped_identifier(row, columns.get("patient_id"))
    accession = _mapped_identifier(row, columns.get("accession"))
    finding_number = _mapped_identifier(row, columns.get("finding_number"))
    raw_laterality = _mapped_text(row, columns.get("laterality"))
    laterality = Laterality.coerce(raw_laterality)
    if patient_id is not None:
        targets.append(("patient", (patient_id,)))
    if accession is not None:
        targets.append(("exam", (accession,)))
        if laterality.is_unilateral:
            targets.append(("breast_side", (accession, laterality.value)))
        if finding_number is not None:
            targets.append(("finding", (accession, finding_number)))
    if include_procedure and patient_id is not None and laterality is not Laterality.UNKNOWN:
        procedure_date = _mapped_text(row, columns.get("procedure_date"))
        procedure_type = _mapped_text(row, columns.get("procedure_type"))
        if procedure_date is not None and procedure_type is not None:
            targets.append(
                (
                    "procedure",
                    (
                        patient_id,
                        procedure_date,
                        procedure_type,
                        laterality.value,
                    ),
                )
            )
    return tuple(targets)


def _source_identity_text(source: SourceRef) -> str:
    return json.dumps(source.to_dict(), sort_keys=True, separators=(",", ":"))


def _record_source(
    record: TableRecord, source_scope: str, source_table: str
) -> Optional[SourceRef]:
    if record.source_key is None:
        return None
    return SourceRef(source_scope, source_table, record.source_key)


def _table_records(
    table: Any,
    source_key: Optional[SourceKeySelector],
    source_table: str,
    transaction: Any,
) -> Iterator[TableRecord]:
    """Turn table-wide normalization failures into invocation issues."""

    try:
        yield from iter_records(table, key=source_key)
    except TableNormalizationError as error:
        transaction.add_issue(
            Issue(
                code=error.code,
                message=str(error),
                severity="error",
                context={
                    "source_table": source_table,
                    "ordinal": error.ordinal,
                },
            )
        )


def _add_table_issues(
    record: TableRecord,
    source: Optional[SourceRef],
    transaction: Any,
) -> bool:
    for table_issue in record.issues:
        transaction.add_issue(
            Issue(
                code=table_issue.code,
                message=table_issue.message,
                severity=table_issue.severity,
                source=source,
                context={
                    "ordinal": table_issue.ordinal,
                    "key_name": table_issue.key_name,
                    "raw_key": table_issue.raw_key,
                },
            )
        )
    return source is not None


def _identity_issue(
    semantic: str,
    raw_value: Any,
    source: Optional[SourceRef],
    physical_column: str,
) -> Issue:
    missing = _is_missing(raw_value)
    return Issue(
        code=f"{'missing' if missing else 'invalid'}_{semantic}",
        message=(
            f"{semantic} is required to construct this source row's grain"
            if missing
            else f"{semantic} is not a supported EMBED identifier"
        ),
        severity="error",
        source=source,
        context={"column": physical_column, "value": raw_value},
    )


def _normalize_identifier(value: Any) -> Optional[str]:
    value = _plain_scalar(value)
    if _is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        numeric = float(value)
        if not isfinite(numeric):
            return None
        if numeric.is_integer():
            return str(int(numeric))
        return str(value)
    return None


def _mapped_text(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    if column is None:
        return None
    value = _plain_scalar(row.get(column))
    if _is_missing(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real) and float(value).is_integer():
        return str(int(value))
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _mapped_value(row: Mapping[str, Any], column: Optional[str]) -> Any:
    if column is None:
        return None
    value = _plain_scalar(row.get(column))
    return None if _is_missing(value) else value


def _mapped_identifier(
    row: Mapping[str, Any], column: Optional[str]
) -> Optional[str]:
    return _normalize_identifier(_mapped_value(row, column))


def _mapped_positive_int(
    row: Mapping[str, Any],
    column: Optional[str],
    semantic: str,
    source: Optional[SourceRef],
    transaction: Any,
) -> Optional[int]:
    value = _mapped_value(row, column)
    if value is None:
        return None
    value = _plain_scalar(value)
    if isinstance(value, bool):
        normalized = None
    elif isinstance(value, Integral):
        normalized = int(value)
    elif isinstance(value, Real) and float(value).is_integer():
        normalized = int(value)
    else:
        normalized = None
    if normalized is None or normalized <= 0:
        transaction.add_issue(
            Issue(
                code=f"invalid_image_{semantic}",
                message=f"image {semantic} must be a positive integer",
                severity="error",
                source=source,
                context={"column": column, "value": value},
            )
        )
        return None
    return normalized


def _exact_integer(value: Any) -> Optional[int]:
    value = _plain_scalar(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        return int(numeric) if isfinite(numeric) and numeric.is_integer() else None
    if isinstance(value, str):
        try:
            numeric = Decimal(value.strip())
        except InvalidOperation:
            return None
        if numeric.is_finite() and numeric == numeric.to_integral():
            return int(numeric)
    return None


def _calendar_date(value: Any) -> Optional[date]:
    value = _plain_scalar(value)
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if value is None:
        return None
    text = str(value).strip()
    try:
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        return date.fromisoformat(text)
    except ValueError:
        return None


def _literal_sequence(value: Any) -> Any:
    value = _plain_scalar(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return None
    return value


def _coordinate_tuple(value: Any) -> Optional[tuple[float, float, float, float]]:
    value = _literal_sequence(value)
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        coordinates = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(isfinite(item) for item in coordinates):
        return None
    if coordinates[2] < coordinates[0] or coordinates[3] < coordinates[1]:
        return None
    return coordinates


def _coordinate_collection(
    value: Any,
) -> Optional[tuple[tuple[float, float, float, float], ...]]:
    parsed = _literal_sequence(value)
    single = _coordinate_tuple(parsed)
    if single is not None:
        return (single,)
    if not isinstance(parsed, (list, tuple)) or not parsed:
        return None
    coordinates = tuple(_coordinate_tuple(item) for item in parsed)
    if any(item is None for item in coordinates):
        return None
    return tuple(item for item in coordinates if item is not None)


def _roi_frame_collections(
    value: Any, count: int
) -> Optional[tuple[tuple[int, ...], ...]]:
    if value is None:
        return tuple(() for _ in range(count))
    parsed = _literal_sequence(value)
    if count == 1:
        if (
            isinstance(parsed, (list, tuple))
            and len(parsed) == 1
            and isinstance(parsed[0], (list, tuple))
        ):
            parsed = parsed[0]
        frames = _nonnegative_int_tuple(parsed)
        return None if frames is None else (frames,)
    if not isinstance(parsed, (list, tuple)) or len(parsed) != count:
        return None
    collections = tuple(_nonnegative_int_tuple(item) for item in parsed)
    if any(item is None for item in collections):
        return None
    return tuple(item for item in collections if item is not None)


def _roi_derived_flags(value: Any, count: int) -> Optional[tuple[bool, ...]]:
    if value is None:
        return tuple(False for _ in range(count))
    parsed = _literal_sequence(value)
    if parsed is None and isinstance(value, str):
        parsed = value
    if isinstance(parsed, (list, tuple)):
        if len(parsed) != count:
            return None
        flags = tuple(_derived_flag(item) for item in parsed)
    else:
        flag = _derived_flag(parsed)
        flags = tuple(flag for _ in range(count))
    return None if any(flag is None for flag in flags) else tuple(bool(flag) for flag in flags)


def _derived_flag(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, Real) and not isinstance(value, bool):
        if float(value) == 1.0:
            return True
        if float(value) == 0.0:
            return False
    text = "" if value is None else str(value).strip().upper()
    if text in {"Y", "YES", "TRUE", "DERIVED"}:
        return True
    if text in {"N", "NO", "FALSE", "SOURCE", "SOURCE_SUPPLIED", ""}:
        return False
    return None


def _nonnegative_int_tuple(value: Any) -> Optional[tuple[int, ...]]:
    if value is None:
        return ()
    value = _literal_sequence(value)
    if not isinstance(value, (list, tuple)):
        value = (value,)
    normalized: list[int] = []
    for item in value:
        item = _plain_scalar(item)
        if isinstance(item, bool):
            return None
        if isinstance(item, Integral):
            integer = int(item)
        elif isinstance(item, Real) and float(item).is_integer():
            integer = int(item)
        else:
            return None
        if integer < 0:
            return None
        normalized.append(integer)
    if len(set(normalized)) != len(normalized):
        return None
    return tuple(normalized)


def _optional_confidence(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if isfinite(normalized) and 0.0 <= normalized <= 1.0 else None


def _plain_scalar(value: Any) -> Any:
    """Unbox NumPy-like scalars without importing an optional dependency."""

    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        try:
            return item()
        except (TypeError, ValueError, OverflowError):
            return value
    return value


def _is_missing(value: Any) -> bool:
    if value is None or type(value).__name__ in {"NAType", "NaTType"}:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        unequal = value != value
        return isinstance(unequal, bool) and unequal
    except (TypeError, ValueError):
        return False


def _evidence(
    row: Mapping[str, Any],
    retain_raw: bool,
) -> Optional[Mapping[str, Any]]:
    if retain_raw:
        return {
            "raw": {
                key: value
                for key, value in row.items()
                if key is not _MAGVIEW_SOURCE_KEY
            }
        }
    # Normalized consumed fields are already retained by ``values``. Avoid a
    # second copy unless the caller explicitly requests the complete row.
    return None


__all__ = ["LoadReport", "load_embed"]
