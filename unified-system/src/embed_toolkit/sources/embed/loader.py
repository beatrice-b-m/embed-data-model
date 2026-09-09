"""Semantic-grain EMBED loading with mutable refresh and merge semantics."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from numbers import Integral, Real
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import (
    Finding,
    FindingNormalizationEvidence,
    FindingNormalizationWarning,
    FindingRecordType,
)
from embed_toolkit.clinical.histories import (
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_toolkit.clinical.interpretations import ImagingInterpretation
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.core.anatomy import AnatomicalPosition, Quadrant
from embed_toolkit.core.graph import DatasetGraph
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.source import Issue, IssueSeverity, SourceRef
from embed_toolkit.core.tables import TableNormalizationError, TableRecord, iter_records
from embed_toolkit.sources.embed.columns import resolve_columns
from embed_toolkit.sources.embed.histories import (
    normalize_medication_history,
    normalize_procedure_history,
)
from embed_toolkit.sources.embed.magview import normalize_magview_location


SourceKeySelector = Union[str, Callable[[Mapping[str, Any]], Any]]
_MISSING = object()


@dataclass(frozen=True)
class LoadReport:
    """The graph and invocation-local issues produced by one load."""

    graph: DatasetGraph
    issues: tuple[Issue, ...]
    source_scope: str


@dataclass(frozen=True)
class _InputRow:
    """One materialized source mapping and optional physical diagnostics."""

    table: str
    mapping: Mapping[str, Any]
    source: Optional[SourceRef]
    ordinal: int


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
    registry: Any = None,
    registry_rows: Any = None,
    into: Optional[DatasetGraph] = None,
    source_scope: Optional[str] = None,
    identity_namespace: Optional[str] = None,
    source_keys: Optional[Mapping[str, SourceKeySelector]] = None,
    columns: Optional[Mapping[str, Mapping[str, Optional[str]]]] = None,
    mode: str = "refresh",
    retain_raw: bool = False,
) -> LoadReport:
    """Load optional EMBED tables into one mutable semantic graph.

    One invocation is one complete grouped snapshot.  ``refresh`` resets the
    bound adapter-managed fields for each addressed grain; ``merge`` applies
    supplied non-null fields and requires explicit collection identifiers where
    equality cannot be established.  A missing table never refreshes that
    grain, and a child projection only ensures its parents.
    """

    if into is not None and not isinstance(into, DatasetGraph):
        raise TypeError("into must be a DatasetGraph or None")
    if mode not in {"refresh", "merge"}:
        raise ValueError("mode must be 'refresh' or 'merge'")
    if not isinstance(retain_raw, bool):
        raise TypeError("retain_raw must be a bool")
    if registry is not None and registry_rows is not None:
        raise TypeError("use either registry or registry_rows, not both")
    if registry is None:
        registry = registry_rows
    if source_scope is not None and (
        not isinstance(source_scope, str) or not source_scope.strip()
    ):
        raise ValueError("source_scope must be a non-empty string or None")
    if identity_namespace is not None and (
        not isinstance(identity_namespace, str) or not identity_namespace.strip()
    ):
        raise ValueError("identity_namespace must be a non-empty string or None")

    column_maps = resolve_columns(columns)
    selectors = _resolve_source_keys(source_keys)
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
    issues: list[Issue] = []

    materialized = {
        table: _materialize(
            value,
            table,
            selectors[table],
            resolved_scope,
            issues,
        )
        for table, value in (
            ("patients", patients),
            ("exams", exams),
            ("findings", findings),
            ("images", images),
            ("rois", rois),
            ("hormone_history", hormone_history),
            ("procedure_history", procedure_history),
            ("procedures", procedures),
            ("pathology", pathology),
            ("magview", magview),
            ("registry", registry),
        )
    }

    magview_rows = materialized["magview"]
    projected = _project_core_rows(magview_rows, column_maps)
    core_rows = {
        "patients": materialized["patients"] + projected["patients"],
        "exams": materialized["exams"] + projected["exams"],
        "findings": materialized["findings"] + projected["findings"],
    }
    _load_patients(core_rows["patients"], graph, column_maps["patients"], mode, issues)
    _load_exams(core_rows["exams"], graph, column_maps["exams"], mode, issues)
    _load_findings(core_rows["findings"], graph, column_maps["findings"], mode, issues, resolved_scope)

    _load_history(
        materialized["hormone_history"],
        graph,
        column_maps["hormone_history"],
        mode,
        issues,
        kind="medication",
    )
    _load_history(
        materialized["procedure_history"],
        graph,
        column_maps["procedure_history"],
        mode,
        issues,
        kind="reported_procedure",
    )

    # Source adapters share the one normalized invocation snapshot.
    from embed_toolkit.sources.embed.clinical import load_clinical
    from embed_toolkit.sources.embed.imaging import load_imaging

    load_clinical(
        procedures=[dict(item.mapping) for item in materialized["procedures"]],
        pathology=[dict(item.mapping) for item in materialized["pathology"]],
        magview=[dict(item.mapping) for item in materialized["magview"]],
        registry=[dict(item.mapping) for item in materialized["registry"]],
        graph=graph,
        columns=column_maps,
        mode=mode,
        issues=issues,
    )
    load_imaging(
        images=[dict(item.mapping) for item in materialized["images"]],
        rois=None if rois is None else [dict(item.mapping) for item in materialized["rois"]],
        graph=graph,
        columns=column_maps,
        mode=mode,
        issues=issues,
    )

    return LoadReport(graph=graph, issues=tuple(issues), source_scope=resolved_scope)


def _resolve_source_keys(
    source_keys: Optional[Mapping[str, SourceKeySelector]],
) -> dict[str, Optional[SourceKeySelector]]:
    tables = (
        "patients",
        "exams",
        "findings",
        "images",
        "rois",
        "hormone_history",
        "procedure_history",
        "procedures",
        "pathology",
        "magview",
        "registry",
    )
    resolved: dict[str, Optional[SourceKeySelector]] = {table: None for table in tables}
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


def _materialize(
    table: Any,
    table_name: str,
    source_key: Optional[SourceKeySelector],
    source_scope: str,
    issues: list[Issue],
) -> list[_InputRow]:
    if table is None:
        return []
    try:
        records = iter_records(table, key=source_key)
        result: list[_InputRow] = []
        for record in records:
            source = _record_source(record, source_scope, table_name)
            for table_issue in record.issues:
                issues.append(
                    Issue(
                        code=table_issue.code,
                        message=table_issue.message,
                        severity=IssueSeverity(table_issue.severity),
                        source=source,
                        context={
                            "table": table_name,
                            "ordinal": table_issue.ordinal,
                            "key_name": table_issue.key_name,
                            "raw_key": table_issue.raw_key,
                        },
                    )
                )
            result.append(
                _InputRow(
                    table=table_name,
                    mapping=dict(record.mapping),
                    source=source,
                    ordinal=record.ordinal,
                )
            )
        return result
    except TableNormalizationError as error:
        issues.append(
            Issue(
                code=error.code,
                message=str(error),
                severity=IssueSeverity.ERROR,
                context={"table": table_name, "ordinal": error.ordinal},
            )
        )
        return []


def _record_source(
    record: TableRecord,
    source_scope: str,
    table_name: str,
) -> Optional[SourceRef]:
    if record.source_key is None:
        return None
    return SourceRef(source_scope, table_name, record.source_key)


def _project_core_rows(
    rows: Sequence[_InputRow],
    columns: Mapping[str, Mapping[str, Optional[str]]],
) -> dict[str, list[_InputRow]]:
    result: dict[str, list[_InputRow]] = {
        "patients": [],
        "exams": [],
        "findings": [],
    }
    for row in rows:
        for grain, identity in (
            ("patients", ("patient_id",)),
            ("exams", ("accession",)),
            ("findings", ("accession", "finding_number")),
        ):
            cmap = columns[grain]
            if _semantic_key(row.mapping, cmap, identity) is not None:
                result[grain].append(row)
    return result


def _load_patients(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
) -> None:
    groups = _group_rows(rows, columns, ("patient_id",), "patient", issues)
    for key in sorted(groups, key=repr):
        group = groups[key]
        patient = _ensure_patient(graph, key)
        fields, conflicts = _combine_fields(
            group,
            columns,
            {
                "sex": _text_value,
                "birth_year": _birth_year_value,
                "context_date": _date_value,
            },
            "patient",
            key,
            issues,
        )
        updates = _updates_for_mode(fields, conflicts, columns, mode)
        if updates:
            _update_entity(graph, patient, updates)


def _load_exams(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
) -> None:
    groups = _group_rows(rows, columns, ("accession",), "exam", issues)
    for key in sorted(groups, key=repr):
        group = groups[key]
        exam = _ensure_exam(graph, key)
        fields, conflicts = _combine_fields(
            group,
            columns,
            {"exam_date": _text_value, "exam_description": _text_value},
            "exam",
            key,
            issues,
        )
        updates = _updates_for_mode(
            {
                "exam_date": fields.get("exam_date"),
                "description": fields.get("exam_description"),
            },
            {
                "exam_date": conflicts.get("exam_date", False),
                "description": conflicts.get("exam_description", False),
            },
            {
                "exam_date": columns.get("exam_date"),
                "description": columns.get("exam_description"),
            },
            mode,
        )
        if updates:
            _update_entity(graph, exam, updates)
        _claim_exam_from_rows(graph, exam, group, columns)


def _load_findings(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
    source_scope: str,
) -> None:
    groups = _group_rows(
        rows,
        columns,
        ("accession", "finding_number"),
        "finding",
        issues,
    )
    for key in sorted(groups, key=repr):
        group = groups[key]
        accession, finding_number = key
        exam = _ensure_exam(graph, accession)
        _claim_exam_from_rows(graph, exam, group, columns)
        fields, conflicts = _combine_fields(
            group,
            columns,
            {
                "laterality": lambda value: Laterality.coerce(value),
                "finding_type": _text_value,
                "assessment": _text_value,
                "recommendation": _text_value,
                "record_type": _text_value,
                "location": _raw_value,
                "depth": _raw_value,
                "distance": _raw_value,
                "descriptors": _literal_value,
            },
            "finding",
            key,
            issues,
        )
        if fields.get("laterality") is None:
            laterality = Laterality.UNKNOWN
        else:
            laterality = fields["laterality"]
        record_type = _finding_record_type(fields.get("record_type"), finding_number)
        interpretation = _interpretation(
            accession,
            finding_number,
            fields.get("assessment"),
            fields.get("recommendation"),
            _semantic_source(group, source_scope, "finding", key),
        )
        anatomy = _finding_anatomy(
            fields,
            laterality,
            group,
            source_scope,
            key,
            issues,
        )
        source = _semantic_source(group, source_scope, "finding", key)
        evidence = anatomy["evidence"] if source is not None else ()
        warnings = anatomy["warnings"] if source is not None else ()
        descriptors = fields.get("descriptors")
        if descriptors is None:
            descriptor_map: dict[str, Any] = {}
        elif isinstance(descriptors, Mapping):
            descriptor_map = dict(descriptors)
        else:
            descriptor_map = {"value": descriptors}
        updates = {
            "laterality": laterality,
            "finding_type": fields.get("finding_type"),
            "interpretation": interpretation,
            "anatomical_position": anatomy["position"],
            "source_location_codes": anatomy["location_codes"],
            "source_depth_codes": anatomy["depth_codes"],
            "source_distance_codes": anatomy["distance_codes"],
            "normalization_evidence": evidence,
            "normalization_warnings": warnings,
            "descriptors": descriptor_map,
            "record_type": record_type,
        }
        dependencies = {
            "interpretation": ("assessment", "recommendation"),
            "anatomical_position": ("location", "depth", "distance"),
            "normalization_evidence": ("location", "depth", "distance"),
            "normalization_warnings": ("location", "depth", "distance"),
        }
        managed_updates = {}
        for name, value in updates.items():
            semantics = dependencies.get(name, (_finding_field(name),))
            if not any(columns.get(semantic) is not None for semantic in semantics):
                continue
            if mode == "refresh" or any(conflicts.get(semantic) or fields.get(semantic) is not None for semantic in semantics):
                managed_updates[name] = value
        updates = managed_updates
        existing = graph.get("finding", key)
        if existing is not None and "interpretation" in updates and existing.interpretation is not None:
            # Interpretations share the finding grain; refresh their bound fields
            # without discarding a consumer's live reference or extension state.
            current = existing.interpretation
            for name in ("assessment", "recommendation"):
                if columns.get(name) is not None and (
                    mode == "refresh" or conflicts.get(name) or fields.get(name) is not None
                ):
                    current.update(**{name: fields.get(name)})
            updates["interpretation"] = current
        if existing is None:
            finding = Finding(
                accession_number=accession,
                laterality=laterality,
                finding_number=finding_number,
                finding_type=updates.get("finding_type"),
                interpretation=updates.get("interpretation"),
                anatomical_position=updates.get("anatomical_position"),
                source_location_codes=updates.get("source_location_codes", {}),
                source_depth_codes=updates.get("source_depth_codes", {}),
                source_distance_codes=updates.get("source_distance_codes", {}),
                normalization_evidence=updates.get("normalization_evidence", ()),
                descriptors=updates.get("descriptors", {}),
                normalization_warnings=updates.get("normalization_warnings", ()),
                record_type=updates.get("record_type", record_type),
                source=source,
            )
            finding = graph.register(finding)
        elif updates:
            _update_entity(graph, existing, updates)
            finding = existing
        else:
            finding = existing
        graph.reference("finding", key, "exam", accession, relation="parent")


def _load_history(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
    *,
    kind: str,
) -> None:
    groups = _group_rows(rows, columns, ("patient_id",), f"{kind}_history", issues)
    normalizer = (
        normalize_medication_history
        if kind == "medication"
        else normalize_procedure_history
    )
    observation_type = (
        MedicationHistoryObservation
        if kind == "medication"
        else ProcedureHistoryObservation
    )
    for patient_id in sorted(groups, key=repr):
        patient = _ensure_patient(graph, patient_id)
        observations: list[Any] = []
        for row in groups[patient_id]:
            source = row.source
            record_id = _mapped_identifier(row.mapping, columns.get("record_id"))
            observation, row_issues = normalizer(row.mapping, columns, source, patient_id, record_id=record_id)
            issues.extend(row_issues)
            if observation is not None and isinstance(observation, observation_type):
                observations.append(observation)
        if not observations and not groups[patient_id]:
            continue
        _apply_history_snapshot(
            patient,
            observations,
            kind,
            mode,
            issues,
        )


def _apply_history_snapshot(
    patient: Any,
    incoming: Sequence[Any],
    kind: str,
    mode: str,
    issues: list[Issue],
) -> None:
    current = list(patient.history_observations)
    other = [item for item in current if not _history_kind(item, kind)]
    old_facts = [item for item in current if _history_kind(item, kind) and item.record_id is None]
    keyed = {item.record_id: item for item in current if _history_kind(item, kind) and item.record_id is not None}
    incoming_groups: dict[str, list[Any]] = {}
    facts = []
    for item in incoming:
        if item.record_id is None:
            facts.append(item)
        else:
            incoming_groups.setdefault(item.record_id, []).append(item)
    managed = ("category", "medication", "context_accession", "continuous", "current", "reported_duration", "started", "stopped", "comment") if kind == "medication" else ("category", "procedure", "detail", "context_accession", "laterality", "reported_result")
    for record_id, observations in incoming_groups.items():
        target = keyed.get(record_id)
        updates: dict[str, Any] = {}
        for field in managed:
            candidates: list[tuple[Any, Any]] = []
            for observation in observations:
                value: Any = getattr(observation, field, None)
                comparable = value.to_dict() if hasattr(value, "to_dict") else value
                if value is not None and not any(_same(comparable, existing[0]) for existing in candidates):
                    candidates.append((comparable, value))
            if len(candidates) > 1:
                issues.append(Issue("conflicting_history_field", "Conflicting reported record values become unknown", context={"patient_id":patient.patient_id,"record_id":record_id,"field":field}))
                updates[field] = None
            elif candidates:
                updates[field] = candidates[0][1]
            elif mode == "refresh":
                updates[field] = None
        if target is None:
            target = observations[0]
        target.update(**updates)
        keyed[record_id] = target
    if mode == "merge":
        if facts:
            issues.append(Issue("history_merge_requires_record_id", "Unkeyed history merge requires supplied record IDs; existing facts preserved", context={"patient_id":patient.patient_id,"kind":kind}))
        facts = old_facts
    elif not facts and incoming_groups:
        facts = old_facts
    _set_history_values(patient, other + list(keyed.values()) + facts)


def _history_kind(item: Any, kind: str) -> bool:
    if kind == "medication":
        return isinstance(item, MedicationHistoryObservation)
    return isinstance(item, ProcedureHistoryObservation)


def _set_history_values(patient: Any, values: Sequence[Any]) -> None:
    patient.replace_history("medication", [item for item in values if isinstance(item, MedicationHistoryObservation)])
    patient.replace_history("reported_procedure", [item for item in values if isinstance(item, ProcedureHistoryObservation)])


def _ensure_patient(graph: DatasetGraph, patient_id: str) -> Any:
    patient = graph.get("patient", patient_id)
    if patient is not None:
        return patient
    return graph.register(Patient(patient_id))


def _ensure_exam(graph: DatasetGraph, accession: str) -> Any:
    exam = graph.get("exam", accession)
    if exam is not None:
        return exam
    return graph.register(Exam(accession))


def _claim_exam_from_rows(
    graph: DatasetGraph,
    exam: Any,
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
) -> None:
    patient_column = columns.get("patient_id")
    claims = {
        identifier
        for row in rows
        if (identifier := _mapped_identifier(row.mapping, patient_column)) is not None
    }
    for patient_id in claims:
        _ensure_patient(graph, patient_id)
    if claims:
        graph.claim_patient(exam, claims)


def _group_rows(
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
    identity: Sequence[str],
    grain: str,
    issues: list[Issue],
) -> dict[Any, list[_InputRow]]:
    result: dict[Any, list[_InputRow]] = {}
    for row in rows:
        key = _semantic_key(row.mapping, columns, identity)
        if key is None:
            fields = ", ".join(identity)
            issues.append(
                Issue(
                    code=f"missing_{grain}_identity",
                    message=f"{grain} row has no usable semantic identity ({fields})",
                    severity=IssueSeverity.ERROR,
                    source=row.source,
                    context={"table": row.table, "ordinal": row.ordinal},
                )
            )
            continue
        result.setdefault(key, []).append(row)
    return result


def _semantic_key(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    identity: Sequence[str],
) -> Any:
    values = tuple(_mapped_identifier(row, columns.get(field)) for field in identity)
    if any(value is None for value in values):
        return None
    return values[0] if len(values) == 1 else values


def _combine_fields(
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
    converters: Mapping[str, Callable[[Any], Any]],
    grain: str,
    key: Any,
    issues: list[Issue],
) -> tuple[dict[str, Any], dict[str, bool]]:
    values: dict[str, Any] = {}
    conflicts: dict[str, bool] = {}
    for semantic, converter in converters.items():
        physical = columns.get(semantic)
        if physical is None:
            continue
        candidates: list[Any] = []
        for row in rows:
            if physical not in row.mapping:
                continue
            raw = _plain_scalar(row.mapping.get(physical))
            if _is_missing(raw):
                continue
            try:
                candidate = converter(raw)
            except (TypeError, ValueError, OverflowError, InvalidOperation):
                candidate = None
            if candidate is not None and not any(_same(candidate, item) for item in candidates):
                candidates.append(candidate)
        candidates.sort(key=repr)
        if len(candidates) > 1:
            conflicts[semantic] = True
            values[semantic] = None
            issues.append(
                Issue(
                    code=f"conflicting_{grain}_{semantic}",
                    message="Conflicting populated values became unknown",
                    severity=IssueSeverity.WARNING,
                    context={"identity": key, "field": semantic, "values": candidates},
                )
            )
        else:
            conflicts[semantic] = False
            values[semantic] = candidates[0] if candidates else None
    return values, conflicts


def _updates_for_mode(
    fields: Mapping[str, Any],
    conflicts: Mapping[str, bool],
    columns: Mapping[str, Optional[str]],
    mode: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for semantic, value in fields.items():
        if columns.get(semantic) is None:
            continue
        if mode == "refresh" or conflicts.get(semantic, False) or value is not None:
            result[semantic] = value
    return result


def _update_entity(graph: DatasetGraph, entity: Any, updates: Mapping[str, Any]) -> None:
    prepared: dict[str, Any] = {}
    private_fields = {
        "source_location_codes": "_source_location_codes",
        "source_depth_codes": "_source_depth_codes",
        "source_distance_codes": "_source_distance_codes",
        "normalization_evidence": "_normalization_evidence",
        "normalization_warnings": "_normalization_warnings",
        "descriptors": "_descriptors",
        "metadata": "_metadata",
        "history_observations": "_history_observations",
    }
    for field, value in updates.items():
        target = private_fields.get(field, field)
        if target in {"_normalization_evidence", "_normalization_warnings"}:
            value = list(value or ())
        elif target == "_descriptors":
            value = dict(value or {})
        elif target == "_metadata":
            value = dict(value or {})
        prepared[target] = value
    graph.update(entity, **prepared)


def _finding_anatomy(
    fields: Mapping[str, Any],
    laterality: Laterality,
    rows: Sequence[_InputRow],
    source_scope: str,
    key: Any,
    issues: list[Issue],
) -> dict[str, Any]:
    location = fields.get("location")
    depth = fields.get("depth")
    distance_raw = fields.get("distance")
    location_codes = {"location": location} if location is not None else {}
    depth_codes = {"depth": depth} if depth is not None else {}
    distance_codes = {"distance": distance_raw} if distance_raw is not None else {}
    has_anatomy = any(value is not None for value in (location, depth, distance_raw))
    position: Optional[AnatomicalPosition] = None
    evidence: list[FindingNormalizationEvidence] = []
    warnings: list[FindingNormalizationWarning] = []
    source = _semantic_source(rows, source_scope, "finding", key)
    if has_anatomy:
        normalized = normalize_magview_location(
            laterality=laterality,
            location_code=location,
            depth_code=depth,
        )
        position = normalized.position
        if source is not None:
            source_fields = {
                "location_code": ("location", location),
                "depth_code": ("depth", depth),
                "laterality": ("laterality", laterality.value),
            }
            for item in normalized.evidence:
                source_field, raw_value = source_fields.get(
                    item.field, (item.field, item.raw_value)
                )
                evidence.append(
                    FindingNormalizationEvidence(
                        source=source,
                        source_field=source_field,
                        raw_value=raw_value,
                        normalized_kind=item.normalized_kind,
                        normalized_value=item.normalized_value,
                    )
                )
            for warning in normalized.warnings:
                source_field, raw_value = source_fields.get(
                    warning.field or "", (warning.field or "location", warning.raw_value)
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
            for warning in normalized.warnings:
                issues.append(
                    Issue(
                        code=warning.code,
                        message=warning.message,
                        severity=IssueSeverity.WARNING,
                        source=source,
                        context={"identity": key},
                    )
                )
    distance: Optional[float] = None
    if distance_raw is not None:
        try:
            distance = float(distance_raw)
            if not isfinite(distance):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            issues.append(
                Issue(
                    code="invalid_finding_distance",
                    message="finding distance could not be parsed as a finite number",
                    severity=IssueSeverity.WARNING,
                    source=source,
                    context={"identity": key, "value": distance_raw},
                )
            )
        if distance is not None and position is None and laterality is not Laterality.UNKNOWN:
            position = AnatomicalPosition(
                laterality=laterality,
                quadrant=Quadrant(laterality=laterality),
            )
        if distance is not None and position is not None:
            position = AnatomicalPosition(
                laterality=position.laterality,
                quadrant=position.quadrant,
                clock_position=position.clock_position,
                location_category=position.location_category,
                distance_from_nipple_cm=distance,
            )
    return {
        "position": position,
        "location_codes": location_codes,
        "depth_codes": depth_codes,
        "distance_codes": distance_codes,
        "evidence": tuple(evidence),
        "warnings": tuple(warnings),
    }


def _source_code_map(
    rows: Sequence[_InputRow],
    semantic: str,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in rows:
        value = row.mapping.get(semantic)
        if value is not None:
            values[semantic] = value
    return values


def _interpretation(
    accession: str,
    finding_number: str,
    assessment: Any,
    recommendation: Any,
    source: Optional[SourceRef],
) -> Optional[ImagingInterpretation]:
    if assessment is None and recommendation is None:
        return None
    return ImagingInterpretation(
        accession_number=accession,
        finding_number=finding_number,
        sources=(source,) if source is not None else (),
        assessment=assessment,
        recommendation=recommendation,
    )


def _finding_record_type(value: Any, finding_number: str) -> FindingRecordType:
    if value is None and finding_number == "-9":
        return FindingRecordType.SYNTHETIC_CONTRALATERAL_NEGATIVE
    if value is None:
        return FindingRecordType.FINDING
    try:
        return FindingRecordType(value)
    except ValueError:
        return FindingRecordType.FINDING


def _finding_field(name: str) -> str:
    return {
        "laterality": "laterality",
        "finding_type": "finding_type",
        "interpretation": "assessment",
        "anatomical_position": "location",
        "source_location_codes": "location",
        "source_depth_codes": "depth",
        "source_distance_codes": "distance",
        "normalization_evidence": "location",
        "normalization_warnings": "location",
        "descriptors": "descriptors",
        "record_type": "record_type",
    }.get(name, name)


def _all_values_absent(
    fields: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    semantic: str,
) -> bool:
    return columns.get(semantic) is not None and fields.get(semantic) is None


def _semantic_source(
    rows: Sequence[_InputRow],
    source_scope: str,
    grain: str,
    key: Any,
) -> Optional[SourceRef]:
    for row in rows:
        if row.source is not None:
            return row.source
    return None


def _mapped_identifier(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    if column is None:
        return None
    return _normalize_identifier(row.get(column))


def _text_value(value: Any) -> Optional[str]:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _raw_value(value: Any) -> Any:
    return None if _is_missing(value) else _plain_scalar(value)


def _literal_value(value: Any) -> Any:
    value = _raw_value(value)
    if isinstance(value, str):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value
    return value


def _birth_year_value(value: Any) -> Optional[int]:
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
            decimal_numeric = Decimal(value.strip())
        except InvalidOperation:
            return None
        return int(decimal_numeric) if decimal_numeric.is_finite() and decimal_numeric == decimal_numeric.to_integral() else None
    return None


def _date_value(value: Any) -> Optional[date]:
    value = _plain_scalar(value)
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _is_missing(value: Any) -> bool:
    if value is None or type(value).__name__ in {"NAType", "NaTType"}:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        unequal = value != value
        if type(unequal) is bool:
            return unequal
        item = getattr(unequal, "item", None)
        if callable(item):
            scalar = item()
            return type(scalar) is bool and scalar
    except (TypeError, ValueError):
        return False
    return False


def _plain_scalar(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        try:
            return item()
        except (TypeError, ValueError, OverflowError):
            return value
    return value


def _normalize_identifier(value: Any) -> Optional[str]:
    value = _plain_scalar(value)
    if _is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        numeric = float(value)
        if not isfinite(numeric):
            return None
        return str(int(numeric)) if numeric.is_integer() else str(value)
    return None


def _same(left: Any, right: Any) -> bool:
    try:
        equal = left == right
        if type(equal) is bool:
            return equal
        item = getattr(equal, "item", None)
        return bool(item()) if callable(item) else False
    except (TypeError, ValueError):
        return repr(left) == repr(right)


__all__ = ["LoadReport", "load_embed"]
