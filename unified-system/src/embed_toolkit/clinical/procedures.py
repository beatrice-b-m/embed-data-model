"""Finding-owned procedures and pathology events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from embed_toolkit.core.primitives import Laterality


def _to_plain(value: Any) -> Any:
    """Convert nested domain objects to JSON-ready Python primitives."""

    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


@dataclass
class PathologyEvent:
    """Pathology information linked through a clinical procedure."""

    pathology_id: Optional[str] = None
    diagnosis: Optional[str] = None
    result_category: Optional[str] = None
    event_date: Optional[str] = None
    malignant: Optional[bool] = None
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(self)


@dataclass
class Procedure:
    """Clinical procedure row associated with a finding."""

    procedure_id: Optional[str] = None
    procedure_type: Optional[str] = None
    accession_number: Optional[str] = None
    laterality: Laterality = Laterality.UNKNOWN
    finding_number: Optional[str] = None
    performed_date: Optional[str] = None
    pathology_events: List[PathologyEvent] = field(default_factory=list)
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        if self.finding_number is not None:
            self.finding_number = str(self.finding_number)

    def add_pathology_event(self, event: PathologyEvent) -> PathologyEvent:
        """Attach pathology to this procedure and return it for chaining."""

        self.pathology_events.append(event)
        return event

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(self)
