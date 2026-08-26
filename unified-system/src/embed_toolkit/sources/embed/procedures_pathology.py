"""EMBED normalization for verified procedures and pathology evidence."""

from __future__ import annotations

from math import isfinite
from numbers import Integral, Real
from typing import Any, Mapping, Optional

from embed_toolkit.clinical.pathology import (
    PathologyDiagnosis,
    PathologyObservation,
    PathologySeverity,
)
from embed_toolkit.clinical.procedures import Procedure, ProcedureIdentity
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.source import Issue, SourceRef


def normalize_procedure(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
) -> tuple[Optional[Procedure], tuple[Issue, ...]]:
    patient_id = _identifier(row, columns["patient_id"])
    performed_date = _text(row, columns["performed_date"])
    procedure_type = _text(row, columns["procedure_type"])
    laterality = Laterality.coerce(_text(row, columns["laterality"]))
    missing = tuple(
        name
        for name, value in (
            ("patient_id", patient_id),
            ("performed_date", performed_date),
            ("procedure_type", procedure_type),
            (
                "laterality",
                None if laterality is Laterality.UNKNOWN else laterality,
            ),
        )
        if value is None
    )
    if missing:
        return None, (
            Issue(
                code="incomplete_procedure_identity",
                message="procedure evidence cannot establish its governed identity",
                source=source,
                context={"missing_fields": missing},
            ),
        )
    assert patient_id is not None
    assert performed_date is not None
    assert procedure_type is not None
    return (
        Procedure(
            identity=ProcedureIdentity(
                patient_id=patient_id,
                performed_date=performed_date,
                procedure_type=procedure_type,
                laterality=laterality,
            ),
            sources=[source],
        ),
        (),
    )


def normalize_pathology(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
) -> tuple[
    Optional[PathologyDiagnosis],
    tuple[PathologyObservation, ...],
    tuple[Issue, ...],
]:
    observations = tuple(
        PathologyObservation(
            descriptor=descriptor,
            source_slot=column,
            source_ordinal=index,
            source=source,
        )
        for index in range(1, 11)
        if (column := columns[f"descriptor_{index}"]) is not None
        if (descriptor := _text(row, column)) is not None
    )
    raw_severity = _value(row, columns["severity"])
    severity, severity_issues = _severity(raw_severity, observations, source)
    diagnosis = _text(row, columns["diagnosis"])
    result_category = _text(row, columns["result_category"])
    malignant = _optional_bool(_value(row, columns["malignant"]))
    report_date = _text(row, columns["report_documented_date"])
    if not any(
        (
            diagnosis,
            result_category,
            malignant is not None,
            raw_severity is not None,
            report_date,
            observations,
        )
    ):
        return None, (), ()
    return (
        PathologyDiagnosis(
            source=source,
            diagnosis=diagnosis,
            result_category=result_category,
            malignant=malignant,
            severity=severity,
            raw_severity=raw_severity,
            report_documented_date=report_date,
            validation_issues=severity_issues,
        ),
        observations,
        severity_issues,
    )


def _severity(
    raw: Any,
    observations: tuple[PathologyObservation, ...],
    source: SourceRef,
) -> tuple[Optional[PathologySeverity], tuple[Issue, ...]]:
    if raw is None:
        if not observations:
            return None, ()
        return None, (
            Issue(
                code="descriptors_without_severity",
                message="pathology descriptors require a populated severity",
                source=source,
            ),
        )
    try:
        if isinstance(raw, bool):
            raise ValueError
        numeric = int(raw)
        if float(raw) != numeric:
            raise ValueError
        return PathologySeverity(numeric), ()
    except (TypeError, ValueError):
        return None, (
            Issue(
                code="invalid_pathology_severity",
                message="pathology severity must be an integer from 0 through 5",
                source=source,
                context={"raw_severity": raw},
            ),
        )


def _value(row: Mapping[str, Any], column: Optional[str]) -> Any:
    if column is None:
        return None
    value = row.get(column)
    if value is None or type(value).__name__ in {"NAType", "NaTType"}:
        return None
    try:
        unequal = value != value
        if isinstance(unequal, bool) and unequal:
            return None
    except (TypeError, ValueError):
        return None
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        try:
            value = item()
        except (TypeError, ValueError, OverflowError):
            pass
    return value


def _text(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    value = _value(row, column)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _identifier(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    value = _value(row, column)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        number = float(value)
        if not isfinite(number):
            return None
        return str(int(number)) if number.is_integer() else str(value)
    return _text(row, column)


def _optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = "" if value is None else str(value).strip().upper()
    if text in {"Y", "YES", "TRUE", "1", "MALIGNANT"}:
        return True
    if text in {"N", "NO", "FALSE", "0", "BENIGN"}:
        return False
    return None


__all__ = ["normalize_pathology", "normalize_procedure"]
