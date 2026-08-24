"""Source-neutral provenance and resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple


class SourceScopeKind(str, Enum):
    """Kind of release boundary within which a source locator is meaningful."""

    DATASET = "dataset"
    MATERIALIZATION = "materialization"


class ResolutionState(str, Enum):
    """Whether source evidence resolved to a governed domain object."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class AvailabilityState(str, Enum):
    """Profile-level status of a governed concept or field."""

    BOUND = "bound"
    RAW_ONLY = "raw_only"
    UNAVAILABLE = "unavailable"
    UNMODELED = "unmodeled"
    UNSUPPORTED = "unsupported"


class IssueSeverity(str, Enum):
    """Stable severity vocabulary for build-time issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class SourceLocator:
    """Address one physical source occurrence within an explicit scope.

    A row ordinal is useful for positional source tables, while a source key is
    useful when the table supplies its own record locator. Exactly one is
    required so locator equality has one unambiguous row-addressing rule.
    """

    scope: str
    scope_kind: SourceScopeKind
    source_profile: str
    source_table: str
    row_ordinal: Optional[int] = None
    source_key: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_kind", SourceScopeKind(self.scope_kind))
        for attribute in ("scope", "source_profile", "source_table"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        if (self.row_ordinal is None) == (self.source_key is None):
            raise ValueError("Exactly one of row_ordinal or source_key is required")
        if self.row_ordinal is not None:
            if (
                isinstance(self.row_ordinal, bool)
                or not isinstance(self.row_ordinal, int)
                or self.row_ordinal < 0
            ):
                raise ValueError("row_ordinal must be a non-negative integer")
        if self.source_key is not None:
            if not isinstance(self.source_key, str) or not self.source_key.strip():
                raise ValueError("source_key must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-ready representation of this physical locator."""

        return {
            "scope": self.scope,
            "scope_kind": self.scope_kind.value,
            "source_profile": self.source_profile,
            "source_table": self.source_table,
            "row_ordinal": self.row_ordinal,
            "source_key": self.source_key,
        }


@dataclass(frozen=True)
class BuildIssue:
    """A structured build-time problem tied to its source evidence."""

    code: str
    message: str
    severity: IssueSeverity
    source: SourceLocator
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", IssueSeverity(self.severity))
        for attribute in ("code", "message"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-ready issue record."""

        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source.to_dict(),
            "context": _json_ready(self.context),
        }


@dataclass(frozen=True)
class SourceOccurrence:
    """Independently addressable source evidence, not a clinical object."""

    locator: SourceLocator
    raw_values: Mapping[str, Any]
    resolution_state: ResolutionState
    issues: Tuple[BuildIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resolution_state",
            ResolutionState(self.resolution_state),
        )
        object.__setattr__(self, "raw_values", MappingProxyType(dict(self.raw_values)))
        object.__setattr__(self, "issues", tuple(self.issues))
        if any(issue.source != self.locator for issue in self.issues):
            raise ValueError("SourceOccurrence issues must reference its locator")

    def to_dict(self) -> Dict[str, Any]:
        """Return source evidence in a JSON-ready, non-clinical shape."""

        return {
            "locator": self.locator.to_dict(),
            "raw_values": _json_ready(self.raw_values),
            "resolution_state": self.resolution_state.value,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _json_ready(value: Any) -> Any:
    """Convert source-neutral evidence values to JSON-compatible primitives."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_ready(value.value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
