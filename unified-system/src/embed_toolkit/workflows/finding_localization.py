"""Finding localization workflow for clinical/source location evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from embed_toolkit.adapters.magview import normalize_magview_location
from embed_toolkit.audit.evidence import AuditWarning, Evidence
from embed_toolkit.audit.results import LocalizationResult, ResultStatus
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.core.anatomy import AnatomicalPosition, Quadrant
from embed_toolkit.core.primitives import Laterality


@dataclass(frozen=True)
class FindingLocalizer:
    """Convert clinical finding location evidence into anatomical expectations."""

    source: str = "magview"

    def localize(
        self,
        finding: Optional[Finding] = None,
        *,
        laterality: Any = None,
        location_code: Any = None,
        depth_code: Any = None,
        clock_code: Any = None,
        raw_source_fields: Optional[Mapping[str, Any]] = None,
        subject_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> LocalizationResult:
        """Return a structured localization result for a finding or raw codes."""

        context = _LocalizationContext.from_inputs(
            finding=finding,
            laterality=laterality,
            location_code=location_code,
            depth_code=depth_code,
            clock_code=clock_code,
            raw_source_fields=raw_source_fields,
            subject_id=subject_id,
        )
        evidence: list[Evidence] = []
        warnings: list[AuditWarning] = []
        result_metadata: dict[str, Any] = {
            "workflow": "finding_localization",
            "source": self.source,
        }
        if metadata:
            result_metadata.update(dict(metadata))

        if finding is not None:
            evidence.extend(
                Evidence(
                    kind=item.normalized_kind,
                    source=item.source.source_profile,
                    payload={
                        "source": item.source.to_dict(),
                        "field": item.source_field,
                        "raw_value": item.raw_value,
                        "normalized_value": item.normalized_value,
                    },
                )
                for item in finding.normalization_evidence
            )
            warnings.extend(
                AuditWarning(
                    code=warning.code,
                    message=warning.message,
                    payload={
                        "source": warning.source.to_dict(),
                        "field": warning.source_field,
                        "raw_value": warning.raw_value,
                        "finding_id": finding.finding_id,
                    },
                )
                for warning in finding.normalization_warnings
            )

        if finding is not None and finding.anatomical_position is not None:
            position = finding.anatomical_position
            evidence.append(
                Evidence(
                    kind="anatomical_position",
                    source="finding",
                    payload=_anatomical_position_payload(position),
                    note="Existing finding anatomical position was used.",
                )
            )
            result_metadata["preferred_source"] = "finding.anatomical_position"
            status = _status_for_position(position=position, warnings=warnings)
        else:
            normalized = normalize_magview_location(
                laterality=context.laterality,
                location_code=context.location_code,
                depth_code=context.depth_code,
                clock_code=context.clock_code,
            )
            position = normalized.position
            evidence.extend(
                Evidence(
                    kind=item.normalized_kind,
                    source=self.source,
                    payload={
                        "field": item.field,
                        "raw_value": item.raw_value,
                        "normalized_value": item.normalized_value,
                    },
                )
                for item in normalized.evidence
            )
            warnings.extend(
                AuditWarning(
                    code=item.code,
                    message=item.message,
                    payload={
                        "field": item.field,
                        "raw_value": item.raw_value,
                    },
                )
                for item in normalized.warnings
            )
            if not evidence:
                warnings.append(
                    AuditWarning(
                        code="missing_location_evidence",
                        message="No clinical location, depth, or clock evidence was available.",
                    )
                )
            result_metadata["preferred_source"] = self.source
            status = _status_for_position(position=position, warnings=warnings)

        return LocalizationResult(
            status=status,
            subject_id=context.subject_id,
            subject_type="finding",
            anatomical_position=_anatomical_position_payload(position),
            evidence=evidence,
            warnings=warnings,
            metadata=result_metadata,
        )


@dataclass(frozen=True)
class _LocalizationContext:
    subject_id: str
    laterality: Laterality
    location_code: Any = None
    depth_code: Any = None
    clock_code: Any = None

    @classmethod
    def from_inputs(
        cls,
        *,
        finding: Optional[Finding],
        laterality: Any,
        location_code: Any,
        depth_code: Any,
        clock_code: Any,
        raw_source_fields: Optional[Mapping[str, Any]],
        subject_id: Optional[str],
    ) -> "_LocalizationContext":
        if finding is not None:
            raw_fields = dict(finding.raw_source_fields)
            if raw_source_fields:
                raw_fields.update(dict(raw_source_fields))
            return cls(
                subject_id=subject_id or finding.finding_id,
                laterality=finding.laterality,
                location_code=_first_present(
                    location_code,
                    tuple(finding.source_location_codes.values()),
                    _fields_by_name(raw_fields, ("loc", "location")),
                ),
                depth_code=_first_present(
                    depth_code,
                    tuple(finding.source_depth_codes.values()),
                    _fields_by_name(raw_fields, ("depth",)),
                ),
                clock_code=_first_present(
                    clock_code,
                    _fields_by_name(raw_fields, ("clock",)),
                ),
            )

        raw_fields = dict(raw_source_fields or {})
        side = Laterality.coerce(laterality)
        return cls(
            subject_id=subject_id or "",
            laterality=side,
            location_code=_first_present(
                location_code,
                _fields_by_name(raw_fields, ("loc", "location")),
            ),
            depth_code=_first_present(depth_code, _fields_by_name(raw_fields, ("depth",))),
            clock_code=_first_present(clock_code, _fields_by_name(raw_fields, ("clock",))),
        )


def _first_present(*values: Any) -> Any:
    flattened: list[Any] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, tuple):
            flattened.extend(item for item in value if item is not None)
            continue
        flattened.append(value)
    if not flattened:
        return None
    if len(flattened) == 1:
        return flattened[0]
    return tuple(flattened)


def _fields_by_name(fields: Mapping[str, Any], tokens: tuple[str, ...]) -> tuple[Any, ...]:
    matches = []
    for key, value in fields.items():
        normalized = str(key).lower()
        if value is None:
            continue
        if any(token in normalized for token in tokens):
            matches.append(value)
    return tuple(matches)


def _status_for_position(
    *, position: AnatomicalPosition, warnings: list[AuditWarning]
) -> ResultStatus:
    quadrant = position.quadrant
    has_location = (
        position.clock_position is not None
        or position.location_category is not None
        or quadrant.ml.value != "unknown"
        or quadrant.si.value != "unknown"
        or quadrant.depth.value != "unknown"
        or position.distance_from_nipple_cm is not None
    )
    if not has_location:
        return ResultStatus.FAILED
    if warnings:
        return ResultStatus.PARTIAL
    return ResultStatus.SUCCESS


def _anatomical_position_payload(position: AnatomicalPosition) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "laterality": position.laterality.value,
        "quadrant": _quadrant_payload(position.quadrant),
    }
    if position.clock_position is not None:
        payload["clock_position"] = {"hour": position.clock_position.hour}
    if position.location_category is not None:
        payload["location_category"] = position.location_category.value
    if position.distance_from_nipple_cm is not None:
        payload["distance_from_nipple_cm"] = position.distance_from_nipple_cm
    return payload


def _quadrant_payload(quadrant: Quadrant) -> dict[str, str]:
    return {
        "laterality": quadrant.laterality.value,
        "ml": quadrant.ml.value,
        "si": quadrant.si.value,
        "depth": quadrant.depth.value,
    }
