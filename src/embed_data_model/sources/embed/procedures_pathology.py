"""EMBED normalization for verified procedures and pathology evidence."""

from __future__ import annotations

from math import isfinite
from numbers import Integral, Real
from typing import Any, Mapping, Optional

from embed_data_model.clinical.pathology import (
    PathologyObservation,
    PathologySeverity,
)
from embed_data_model.clinical.procedures import Procedure, ProcedureIdentity
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.source import Issue, SourceRef


def normalize_procedure(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: Optional[SourceRef] = None,
) -> tuple[Optional[Procedure], tuple[Issue, ...]]:
    """Normalize one performed procedure without guessing missing identity.

    Parameters
    ----------
    row : mapping
        Source column names to raw values; not mutated.
    columns : mapping
        Semantic field names to physical columns; None bindings omit fields.
        Use the matching map from resolve_columns for EMBED defaults.
    source : SourceRef or None
        Physical diagnostic provenance, not clinical identity.

    Returns
    -------
    Procedure or None, tuple of Issue
        Resolved entity only with complete patient/date/type/known-side identity.
        Missing components produce None and an incomplete_procedure_identity issue.

    Notes
    -----
    No graph is mutated, no files are read and no scientific validity is inferred.
    """

    patient_id = _identifier(row, columns.get("patient_id"))
    performed_date = _text(
        row, columns.get("performed_date", columns.get("procedure_date"))
    )
    procedure_type = _code(row, columns.get("procedure_type"))
    laterality = Laterality.coerce(_text(row, columns.get("laterality")))
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
            sources=[] if source is None else [source],
        ),
        (),
    )


def normalize_pathology(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: Optional[SourceRef] = None,
) -> tuple[dict[str, Any], tuple[PathologyObservation, ...]]:
    """Normalize reported pathology fields and ordered descriptor slots.

    Parameters
    ----------
    row : mapping
        Source column names to raw values; not mutated.
    columns : mapping
        Semantic field names to physical columns; None bindings omit fields.
        Use the matching map from resolve_columns for EMBED defaults.
    source : SourceRef or None
        Physical diagnostic provenance, not clinical identity.

    Returns
    -------
    dict, tuple of PathologyObservation
        Supplied non-null Pathology fields (``diagnosis``, ``result_category``,
        ``malignant``, ``severity``, ``raw_severity``,
        ``report_documented_date``), and descriptor slots 1-10 in slot order
        with duplicates kept. A severity outside the 0-5 scale is kept only as
        ``raw_severity``. No clinical event identity is inferred.
    """

    observations = tuple(
        PathologyObservation(
            descriptor=descriptor,
            source_slot=column,
            source_ordinal=index,
            source=source,
        )
        for index in range(1, 11)
        if (column := columns.get(f"descriptor_{index}")) is not None
        if (descriptor := _code(row, column)) is not None
    )
    raw_severity = _value(row, columns.get("severity"))
    values = {
        "diagnosis": _text(row, columns.get("diagnosis")),
        "result_category": _text(row, columns.get("result_category")),
        "malignant": _optional_bool(_value(row, columns.get("malignant"))),
        "severity": _severity(raw_severity),
        "raw_severity": raw_severity,
        "report_documented_date": _text(row, columns.get("report_documented_date")),
    }
    return {name: value for name, value in values.items() if value is not None}, observations


def _severity(raw: Any) -> Optional[PathologySeverity]:
    """Return the governed severity for a whole-number code 0-5, else None."""

    if raw is None or isinstance(raw, bool):
        return None
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        return None
    if not numeric.is_integer() or int(numeric) not in PathologySeverity._value2member_map_:
        return None
    return PathologySeverity(int(numeric))


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


def _code(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    """Return a MagView code trimmed and uppercased for comparison."""

    text = _text(row, column)
    return None if text is None else text.upper()


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
