"""Export helpers for JSON-compatible workflow audit results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Dict

from embed_toolkit.audit.evidence import JsonValue, serialize_mapping


def export_result(result: Any) -> Dict[str, JsonValue]:
    """Serialize one result object or mapping into a deterministic JSON mapping."""

    if isinstance(result, Mapping):
        return _sort_json_mapping(serialize_mapping(result))

    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if not isinstance(payload, Mapping):
            raise TypeError("Result to_dict() must return a mapping")
        return _sort_json_mapping(serialize_mapping(payload))

    raise TypeError(f"Unsupported audit export value: {type(result).__name__}")


def export_results(results: Sequence[Any]) -> Dict[str, JsonValue]:
    """Serialize an ordered collection of result objects or mappings."""

    if isinstance(results, (str, bytes, bytearray)) or isinstance(results, Mapping):
        raise TypeError("Audit result collections must be non-string sequences")

    serialized_results = [export_result(result) for result in results]
    return {
        "count": len(serialized_results),
        "summary": summarize_results(serialized_results),
        "results": serialized_results,
    }


def summarize_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, JsonValue]:
    """Build deterministic review summary fields from serialized result mappings."""

    if isinstance(results, (str, bytes, bytearray)) or isinstance(results, Mapping):
        raise TypeError("Audit summaries require a sequence of result mappings")

    status_counts: Counter[str] = Counter()
    result_type_counts: Counter[str] = Counter()
    evidence_count = 0
    warning_count = 0

    for result in results:
        if not isinstance(result, Mapping):
            raise TypeError("Audit summaries require result mappings")

        status = result.get("status")
        if isinstance(status, str):
            status_counts[status] += 1

        result_type = result.get("result_type")
        if isinstance(result_type, str) and result_type:
            result_type_counts[result_type] += 1

        evidence = result.get("evidence", [])
        if isinstance(evidence, list):
            evidence_count += len(evidence)

        warnings = result.get("warnings", [])
        if isinstance(warnings, list):
            warning_count += len(warnings)

    return {
        "total": len(results),
        "statuses": _sorted_counts(status_counts),
        "result_types": _sorted_counts(result_type_counts),
        "evidence_count": evidence_count,
        "warning_count": warning_count,
    }


def _sorted_counts(counts: Counter[str]) -> Dict[str, int]:
    return {key: counts[key] for key in sorted(counts)}


def _sort_json_mapping(value: Mapping[str, JsonValue]) -> Dict[str, JsonValue]:
    return {key: _sort_json_value(value[key]) for key in sorted(value)}


def _sort_json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return _sort_json_mapping(value)
    if isinstance(value, list):
        return [_sort_json_value(item) for item in value]
    return value
