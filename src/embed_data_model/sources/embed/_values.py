"""Value comparison shared by the EMBED adapters."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, MutableMapping

from embed_data_model.core.source import Issue, IssueSeverity


def same(left: Any, right: Any) -> bool:
    """Compare source values, tolerating array-like and unorderable scalars."""

    try:
        equal = left == right
        if type(equal) is bool:
            return equal
        item = getattr(equal, "item", None)
        return bool(item()) if callable(item) else False
    except (TypeError, ValueError):
        return repr(left) == repr(right)


def is_unknown(value: Any) -> bool:
    """Return whether a stored value carries no populated fact."""

    return value is None or (isinstance(value, Enum) and value.name == "UNKNOWN")


def reconcile_merge(
    current: Mapping[str, Any],
    updates: MutableMapping[str, Any],
    *,
    grain: str,
    key: Any,
    issues: list[Issue],
) -> None:
    """Turn merged values that contradict populated current values into unknowns.

    Merge fills gaps; it must not silently overwrite one populated fact with
    another. For each populated update whose field already holds a different
    populated value, the update becomes unknown (None, or the enum's UNKNOWN
    member) and a warning is recorded.
    ``updates`` is modified in place.
    """

    for name, value in list(updates.items()):
        existing = current.get(name)
        if is_unknown(value) or is_unknown(existing) or same(existing, value):
            continue
        # An enum field becomes its UNKNOWN member rather than None.
        updates[name] = getattr(type(existing), "UNKNOWN", None) if isinstance(existing, Enum) else None
        issues.append(
            Issue(
                code=f"conflicting_{grain}_{name}",
                message="Merged value conflicts with the current value and became unknown",
                severity=IssueSeverity.WARNING,
                context={"identity": key, "field": name, "values": [existing, value]},
            )
        )
