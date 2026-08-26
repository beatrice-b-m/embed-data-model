"""Patient and exam ingestion for the EMBED source."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real
from typing import Any, Callable, Iterator, Mapping, Optional, Union

from embed_toolkit.adapters.tables import (
    TableNormalizationError,
    TableRecord,
    iter_records,
)
from embed_toolkit.core.graph import DatasetGraph
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.source import Issue, SourceRef
from embed_toolkit.sources.embed.columns import resolve_columns


SourceKeySelector = Union[str, Callable[[Mapping[str, Any]], Any]]


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


def _load_patients(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
) -> None:
    patient_column = columns["patient_id"]
    assert patient_column is not None
    for record in _table_records(table, source_key, "patients", transaction):
        source = _record_source(record, source_scope, "patients")
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
        transaction.upsert_patient(
            patient_id,
            source,
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
        )


def _load_exams(
    table: Any,
    *,
    transaction: Any,
    source_scope: str,
    source_key: Optional[SourceKeySelector],
    columns: Mapping[str, Optional[str]],
    retain_raw: bool,
) -> None:
    accession_column = columns["accession"]
    assert accession_column is not None
    for record in _table_records(table, source_key, "exams", transaction):
        source = _record_source(record, source_scope, "exams")
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
) -> None:
    accession_column = columns["accession"]
    number_column = columns["finding_number"]
    assert accession_column is not None and number_column is not None
    for record in _table_records(table, source_key, "findings", transaction):
        source = _record_source(record, source_scope, "findings")
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
        transaction.upsert_finding(
            accession,
            finding_number,
            source,
            laterality=laterality,
            finding_type=values["finding_type"],
            assessment=values["assessment"],
            recommendation=values["recommendation"],
            values=values,
            metadata=_evidence(record.mapping, retain_raw),
        )


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
        return {"raw": dict(row)}
    # Normalized consumed fields are already retained by ``values``. Avoid a
    # second copy unless the caller explicitly requests the complete row.
    return None


__all__ = ["LoadReport", "load_embed"]
