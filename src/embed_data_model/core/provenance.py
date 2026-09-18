"""Source-neutral provenance and resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple


class SourceScopeKind(str, Enum):
    """Kind of release boundary within which a source locator is meaningful.

    Members
    -------
    DATASET='dataset', MATERIALIZATION='materialization'.
    """

    DATASET = "dataset"
    MATERIALIZATION = "materialization"


class ResolutionState(str, Enum):
    """Whether source evidence resolved to a governed domain object.

    Members
    -------
    RESOLVED='resolved', UNRESOLVED='unresolved'.
    """

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class AvailabilityState(str, Enum):
    """Profile-level status of a governed concept or field.

    Members
    -------
    BOUND='bound', RAW_ONLY='raw_only', UNAVAILABLE='unavailable',
    UNMODELED='unmodeled', UNSUPPORTED='unsupported'.
    """

    BOUND = "bound"
    RAW_ONLY = "raw_only"
    UNAVAILABLE = "unavailable"
    UNMODELED = "unmodeled"
    UNSUPPORTED = "unsupported"


class IssueSeverity(str, Enum):
    """Stable severity vocabulary for build-time issues.

    Members
    -------
    INFO='info', WARNING='warning', ERROR='error'.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class SourceLocator:
    """Address one physical source occurrence within an explicit scope.

    A row ordinal is useful for positional source tables, while a source key is
    useful when the table supplies its own record locator. Exactly one is
    required so locator equality has one unambiguous row-addressing rule.

    Attributes
    ----------
    scope : str
        Non-empty dataset/materialization scope label.
    scope_kind : SourceScopeKind
        Whether scope identifies a dataset or one materialization.
    source_profile : str
        Non-empty source-profile label.
    source_table : str
        Non-empty physical source table label.
    row_ordinal : Optional[int]
        Zero-based physical position, or None. Exactly one of
        row_ordinal/source_key is required. Default: None.
    source_key : Optional[str]
        Physical source row key; does not supply clinical identity. Default:
        None.
    """

    scope: str
    """Non-empty dataset/materialization scope label."""
    scope_kind: SourceScopeKind
    """Whether scope identifies a dataset or one materialization."""
    source_profile: str
    """Non-empty source-profile label."""
    source_table: str
    """Non-empty physical source table label."""
    row_ordinal: Optional[int] = None
    """Zero-based physical position, or None. Exactly one of row_ordinal/source_key
    is required. Default: None.
    """
    source_key: Optional[str] = None
    """Physical source row key; does not supply clinical identity. Default: None."""

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
    """A structured build-time problem tied to its source evidence.

    Attributes
    ----------
    code : str
        Non-empty machine-readable diagnostic code.
    message : str
        Non-empty human-readable diagnostic explanation.
    severity : IssueSeverity
        Diagnostic level: info, warning or error. Errors invalidate
        ValidationResult; warnings do not by default.
    source : SourceLocator
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events.
    context : Mapping[str, Any]
        Shallow-copied read-only diagnostic mapping. Nested mutable values are
        not frozen. Default: a fresh empty mapping.
    """

    code: str
    """Non-empty machine-readable diagnostic code."""
    message: str
    """Non-empty human-readable diagnostic explanation."""
    severity: IssueSeverity
    """Diagnostic level: info, warning or error. Errors invalidate
    ValidationResult; warnings do not by default.
    """
    source: SourceLocator
    """Optional provenance. SourceRef and SourceLocator identify evidence, not clinical events."""
    context: Mapping[str, Any] = field(default_factory=dict)
    """Shallow-copied read-only diagnostic mapping. Nested mutable values are not
    frozen. Default: a fresh empty mapping.
    """

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
    """Independently addressable source evidence, not a clinical object.

    Attributes
    ----------
    locator : SourceLocator
        Physical evidence address, never a clinical identity.
    raw_values : Mapping[str, Any]
        Shallow-copied read-only source mapping; nested values remain shared.
    resolution_state : ResolutionState
        Whether evidence resolved; UNRESOLVED means no supported result could be
        selected.
    issues : Tuple[BuildIssue, ...]
        Ordered diagnostics supplied by this operation; empty means none.
        Default: ().
    """

    locator: SourceLocator
    """Physical evidence address, never a clinical identity."""
    raw_values: Mapping[str, Any]
    """Shallow-copied read-only source mapping; nested values remain shared."""
    resolution_state: ResolutionState
    """Whether evidence resolved; UNRESOLVED means no supported result could be selected."""
    issues: Tuple[BuildIssue, ...] = ()
    """Ordered diagnostics supplied by this operation; empty means none. Default: ()."""

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
