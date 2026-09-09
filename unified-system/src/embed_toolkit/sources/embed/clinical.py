"""Grouped clinical projections over rows already normalized by the loader.

One call is one complete refresh snapshot. Registry payload fields are opt-in:
only non-key entries in columns['registry'] are projected. The supplied EMBED
binding identifies entries but does not bind their payload. No physical row
address, payload hash, or row ordinal identifies a clinical event.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Mapping, Optional, Iterable

from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.pathology import CancerRegistryEntry, Pathology
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.core.source import Issue
from embed_toolkit.sources.embed.procedures_pathology import (
    _identifier,
    _value,
    normalize_pathology,
    normalize_procedure,
)


def load_clinical(
    *,
    procedures: list[Mapping],
    pathology: list[Mapping],
    magview: list[Mapping],
    registry: list[Mapping],
    graph: Any,
    columns: Mapping,
    mode: str,
    issues: list[Issue],
) -> None:
    """Apply narrow and wide projections together, preserving object references."""
    if mode not in {"refresh", "merge"}:
        raise ValueError("mode must be 'refresh' or 'merge'")
    merge = mode == "merge"
    procedure_groups: dict[Any, list] = defaultdict(list)
    pathology_groups: dict[Any, list] = defaultdict(list)
    snapshots: dict[Any, list] = defaultdict(list)
    addressed = set()
    key: Any

    def unresolved(
        kind: str, attachment: Any, row: Mapping[str, Any], reason: str
    ) -> None:
        address = ("clinical", kind, attachment)
        addressed.add(address)
        snapshots[address].append(
            {"payload": deepcopy(dict(row)), "attachment": attachment, "reason": reason}
        )
        issues.append(
            Issue(
                code=reason,
                message="Clinical record needs explicit identity",
                context={"attachment": attachment},
            )
        )

    for rows, cmap, grain, wide in (
        (procedures, columns.get("procedures", {}), "procedure", False),
        (magview, columns.get("procedures", {}), "procedure", True),
        (pathology, columns.get("pathology", {}), "pathology", False),
        (magview, columns.get("pathology", {}), "pathology", True),
    ):
        for row in rows:
            attachment = _attachment(row, cmap)
            patient_id = _identifier(row, cmap.get("patient_id"))
            if grain == "procedure":
                if wide and not any(
                    _value(row, cmap.get(k)) is not None
                    for k in ("performed_date", "procedure_type")
                ):
                    continue
                _claim(graph, row, cmap)
                addressed.add(("clinical", grain, attachment))
                procedure, errors = normalize_procedure(row, cmap)
                if procedure is None:
                    unresolved(grain, attachment, row, "incomplete_procedure_identity")
                    continue
                procedure_groups[procedure.identity].append(
                    (procedure, attachment, row, cmap)
                )
            else:
                diagnosis, descriptors, errors = normalize_pathology(row, cmap)
                issues.extend(errors)
                record_id = _identifier(row, cmap.get("record_id"))
                if diagnosis is None and not descriptors and record_id is None:
                    continue
                _claim(graph, row, cmap)
                procedure, _ = normalize_procedure(row, cmap)
                if procedure is not None:
                    procedure_groups[procedure.identity].append(
                        (procedure, attachment, row, {})
                    )
                    attachment = ("procedure", procedure.identity)
                addressed.add(("clinical", grain, attachment))
                date = getattr(diagnosis, "report_documented_date", None)
                if record_id is not None and patient_id is not None:
                    key = (patient_id, record_id)
                    explicit = True
                elif record_id is None and attachment is not None and date is not None:
                    key = ("magview", attachment[1], date)
                    explicit = False
                else:
                    unresolved(grain, attachment, row, "incomplete_pathology_identity")
                    continue
                pathology_groups[key].append(
                    (diagnosis, descriptors, attachment, row, cmap, explicit)
                )

    for key, group in procedure_groups.items():
        entity = graph.get("procedure", key)
        if entity is None:
            entity = graph.register(group[0][0])
        payload_maps = [
            {
                k: v
                for k, v in item[3].items()
                if k
                not in {
                    "patient_id",
                    "performed_date",
                    "procedure_date",
                    "procedure_type",
                    "laterality",
                    "accession",
                    "finding_number",
                }
            }
            for item in group
        ]
        issue_start = len(issues)
        values = _combine(
            [(item[2], cmap) for item, cmap in zip(group, payload_maps)], issues, key
        )
        conflicts = _conflict_fields(issues[issue_start:])
        graph.update(
            entity,
            **{
                k: v
                for k, v in values.items()
                if not merge or v is not None or k in conflicts
            },
        )
        for _, attachment, row, cmap in group:
            _link(graph, "procedure", key, attachment)

    for key, group in pathology_groups.items():
        slots: dict[int, list] = defaultdict(list)
        for _, descriptors, *_ in group:
            for descriptor in descriptors:
                if descriptor.descriptor not in slots[descriptor.source_ordinal]:
                    slots[descriptor.source_ordinal].append(descriptor.descriptor)
        if not group[0][5] and any(len(values) > 1 for values in slots.values()):
            existing = graph.get("pathology", key)
            if existing is not None and not merge:
                graph.pop(existing)
            for _, _, attachment, row, _, _ in group:
                unresolved("pathology", attachment, row, "ambiguous_pathology_identity")
            continue
        for slot, candidates in slots.items():
            if len(candidates) > 1:
                issues.append(
                    Issue(
                        code="conflicting_clinical_values",
                        message="Conflicting descriptor slot becomes unknown",
                        context={"identity": key, "slot": slot, "values": candidates},
                    )
                )
        entity = graph.get("pathology", key)
        issue_start = len(issues)
        values = _combine(
            [
                (
                    row,
                    {
                        k: v
                        for k, v in cmap.items()
                        if k
                        in {
                            "diagnosis",
                            "result_category",
                            "malignant",
                            "severity",
                            "report_documented_date",
                        }
                    },
                )
                for _, _, _, row, cmap, _ in group
            ],
            issues,
            key,
        )
        # Reuse the normalizer after combining scalar source values.
        normalized, _, errors = normalize_pathology(values, {k: k for k in values})
        issues.extend(errors)
        descriptor_values = tuple(
            next(d for _, ds, *_ in group for d in ds if d.source_ordinal == slot)
            for slot in sorted(slots)
            if len(slots[slot]) == 1
        )
        updates = {
            field: getattr(normalized, field) if normalized is not None else None
            for field in values
        }
        if "severity" in values:
            updates["raw_severity"] = values["severity"]
        if merge:
            conflicts = _conflict_fields(issues[issue_start:])
            if "severity" in conflicts:
                conflicts.add("raw_severity")
            updates = {
                k: v for k, v in updates.items() if v is not None or k in conflicts
            }
        if entity is None:
            entity = graph.register(
                Pathology(identity=key, **updates, descriptors=descriptor_values)
            )
        else:
            bound_slots = {
                int(k.split("_")[1])
                for *_, cmap, explicit in group
                for k, v in cmap.items()
                if k.startswith("descriptor_") and v is not None
            }
            if bound_slots:
                retained = {
                    d.source_ordinal: d
                    for d in entity.descriptors
                    if merge or d.source_ordinal not in bound_slots
                }
                for slot, candidates in slots.items():
                    if len(candidates) > 1:
                        retained.pop(slot, None)
                retained.update({d.source_ordinal: d for d in descriptor_values})
                updates["descriptors"] = tuple(retained[k] for k in sorted(retained))
            graph.update(entity, **updates)
        for _, _, attachment, _, _, _ in group:
            _link(graph, "pathology", key, attachment)

    for address in addressed:
        incoming = snapshots.get(address, [])
        # Unidentified facts have no event key with which to perform a merge.
        # Keep one current snapshot, rather than accumulating repeated loads.
        if merge and not incoming:
            continue
        if incoming:
            # A collection of facts, not inferred distinct event identities.
            graph.unresolved_records[address] = incoming
        else:
            graph.unresolved_records.pop(address, None)

    registry_map = columns.get(
        "registry", {"patient_id": "empi_anon", "registry_id": "cancer_registry_id"}
    )
    groups: dict[Any, list] = defaultdict(list)
    for row in registry:
        key = (
            _identifier(row, registry_map.get("patient_id")),
            _identifier(row, registry_map.get("registry_id")),
        )
        if None in key:
            issues.append(
                Issue(
                    code="incomplete_registry_identity",
                    message="Registry needs patient and entry IDs",
                    context={"payload": dict(row)},
                )
            )
            continue
        groups[key].append(row)
    for key, rows in groups.items():
        cmap = {
            k: v
            for k, v in registry_map.items()
            if k not in {"patient_id", "registry_id"}
        }
        issue_start = len(issues)
        payload = _combine([(row, cmap) for row in rows], issues, key)
        conflicts = _conflict_fields(issues[issue_start:])
        entity = graph.registry_entry(*key)
        if entity is None:
            graph.register(CancerRegistryEntry(key[0], key[1], payload=payload))
        else:
            retained = dict(entity.payload)
            retained.update(
                {
                    k: v
                    for k, v in payload.items()
                    if not merge or v is not None or k in conflicts
                }
            )
            graph.update(entity, payload=retained)
    _collections(magview, graph, columns, merge, issues)


def _attachment(
    row: Mapping[str, Any], cmap: Mapping[str, Optional[str]]
) -> Optional[tuple[str, Any]]:
    accession = _identifier(row, cmap.get("accession"))
    finding = _identifier(row, cmap.get("finding_number"))
    if accession is None:
        return None
    return (
        ("finding", (accession, finding))
        if finding is not None
        else ("exam", accession)
    )


def _claim(
    graph: Any, row: Mapping[str, Any], cmap: Mapping[str, Optional[str]]
) -> None:
    accession = _identifier(row, cmap.get("accession"))
    patient = _identifier(row, cmap.get("patient_id"))
    if patient is not None and graph.patient(patient) is None:
        graph.register(Patient(patient))
    if accession is not None:
        exam = graph.exam(accession)
        if exam is None:
            exam = graph.register(Exam(accession))
        if patient is not None:
            graph.claim_patient(exam, {patient})


def _link(
    graph: Any, kind: str, key: Any, attachment: Optional[tuple[str, Any]]
) -> None:
    if attachment is not None:
        graph.reference(attachment[0], attachment[1], kind, key)


def _combine(
    rows: Iterable[tuple[Mapping[str, Any], Mapping[str, Optional[str]]]],
    issues: list[Issue],
    key: Any,
) -> dict[str, Any]:
    grouped: dict[str, list] = defaultdict(list)
    for row, cmap in rows:
        for field, physical in cmap.items():
            if physical is None:
                continue
            values = grouped[field]
            value = _value(row, physical)
            if value is not None and value not in values:
                values.append(value)
    result = {}
    for field, values in grouped.items():
        result[field] = values[0] if len(values) == 1 else None
        if len(values) > 1:
            issues.append(
                Issue(
                    code="conflicting_clinical_values",
                    message="Conflicting populated values become unknown",
                    context={"identity": key, "field": field, "values": values},
                )
            )
    return result


def _conflict_fields(issues: Iterable[Issue]) -> set[str]:
    return {
        issue.context["field"]
        for issue in issues
        if issue.code == "conflicting_clinical_values" and "field" in issue.context
    }


def _collections(
    rows: list[Mapping], graph: Any, columns: Mapping, merge: bool, issues: list[Issue]
) -> None:
    cmap = dict(columns.get("exams", {}))
    cmap.update(columns.get("magview", {}))
    assignment = cmap.get("registry_assignment", "cancer_outcome_registry_id")
    linked = cmap.get(
        "linked_accession", cmap.get("linkedaccession_anon", "linkedaccession_anon")
    )
    assignments: dict[str, set] = defaultdict(set)
    links: dict[str, set] = defaultdict(set)
    for row in rows:
        accession = _identifier(row, cmap.get("accession", "acc_anon"))
        if accession is None:
            continue
        _claim(graph, row, cmap)
        if assignment is not None and assignment in row:
            values = assignments[accession]
            patient = _identifier(row, cmap.get("patient_id", "empi_anon"))
            raw_ids = _value(row, assignment)
            for value in (
                raw_ids if isinstance(raw_ids, (list, tuple, set)) else [raw_ids]
            ):
                rid = _identifier({"value": value}, "value")
                if rid is not None and patient is not None:
                    values.add((patient, rid))
                elif rid is not None:
                    issues.append(
                        Issue(
                            code="incomplete_registry_assignment",
                            message="Confirmed registry assignment lacks source patient",
                            context={"accession": accession, "registry_id": rid},
                        )
                    )
        if linked is not None and linked in row:
            values = links[accession]
            raw = _value(row, linked)
            for value in raw if isinstance(raw, (list, tuple, set)) else [raw]:
                target = _identifier({"value": value}, "value")
                if target is not None:
                    values.add(target)
    for accession, values in assignments.items():
        graph.set_registry_assignments(graph.exam(accession), values, merge=merge)
    for accession, values in links.items():
        graph.set_linked_accessions(graph.exam(accession), values, merge=merge)
