"""Source-neutral attributed patient observations and as-of selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Integral
from typing import Any, Iterable, Optional, Tuple, Union, cast

from embed_toolkit.core.entity import MutableEntity, serialize_entity
from embed_toolkit.core.provenance import (
    BuildIssue,
    IssueSeverity,
    ResolutionState,
    SourceLocator,
)
from embed_toolkit.core.source import SourceRef


SourceValue = Union[SourceLocator, SourceRef]


class PatientAttributeName(str, Enum):
    """Governed patient attributes represented by source observations."""

    SEX = "sex"
    BIRTH_YEAR = "birth_year"


class PatientObservationTimeBasis(str, Enum):
    """Source context used to order patient attribute observations."""

    EXAM_DATE_CONTEXT = "exam_date_context"


class ExamAttributeName(str, Enum):
    """Governed invariant attributes reconciled across exam source rows."""

    EXAM_DATE = "exam_date"
    DESCRIPTION = "description"


class UndatedObservationPolicy(str, Enum):
    """Treatment of observations without a usable context date."""

    REJECT = "reject"
    EXCLUDE = "exclude"


def _optional_source(source: Optional[object]) -> Optional[SourceValue]:
    if source is not None and not isinstance(source, (SourceLocator, SourceRef)):
        raise TypeError("source must be a SourceRef or SourceLocator")
    return source


def _source_dict(source: Optional[SourceValue]) -> Optional[dict[str, object]]:
    return None if source is None else source.to_dict()


class ExamAttributeObservation(MutableEntity):
    """One source-attributed observation of an invariant exam fact."""

    __key_fields__ = ("accession_number", "attribute", "source")

    def __init__(
        self,
        accession_number: str,
        attribute: ExamAttributeName,
        value: Optional[str],
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        if not isinstance(accession_number, str) or not accession_number.strip():
            raise ValueError("accession_number must be a non-empty string")
        self.accession_number = accession_number.strip()
        self.attribute = ExamAttributeName(attribute)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise TypeError("exam attribute value must be a string or None")
            value = value.strip()
        self.value = value
        self.source = _optional_source(source)
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, ExamAttributeName, Optional[SourceValue]]:
        return self.accession_number, self.attribute, self.source

    def reference_dict(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "attribute": self.attribute.value,
            "source": _source_dict(self.source),
        }

    def _to_dict_data(self, state: Any) -> dict[str, object]:
        return {**self.reference_dict(), "value": self.value}

    def to_dict(self) -> dict[str, object]:
        return serialize_entity(self)


class PatientAttributeObservation(MutableEntity):
    """One source-attributed patient value, including an explicit null."""

    __key_fields__ = ("patient_id", "attribute", "source")

    def __init__(
        self,
        patient_id: str,
        attribute: PatientAttributeName,
        value: Any,
        source: Optional[object] = None,
        context_date: Optional[date] = None,
        time_basis: PatientObservationTimeBasis = (
            PatientObservationTimeBasis.EXAM_DATE_CONTEXT
        ),
    ) -> None:
        super().__init__()
        if not isinstance(patient_id, str) or not patient_id.strip():
            raise ValueError("patient_id must be a non-empty string")
        self.patient_id = patient_id.strip()
        self.attribute = PatientAttributeName(attribute)
        self.time_basis = PatientObservationTimeBasis(time_basis)
        if context_date is not None and type(context_date) is not date:
            raise TypeError("context_date must be a date or None")
        self.context_date = context_date
        self.source = _optional_source(source)
        if self.attribute is PatientAttributeName.SEX:
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise TypeError("sex observation value must be a string or None")
            if isinstance(value, str):
                value = value.strip()
        elif value is not None:
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(
                    "birth_year observation value must be an integral value or None"
                )
            value = int(value)
        self.value = value
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, PatientAttributeName, Optional[SourceValue]]:
        """Governed identity for one attributed observation."""

        return self.patient_id, self.attribute, self.source

    def reference_dict(self) -> dict[str, object]:
        """Return the governed identity used by flat graph serialization."""

        return {
            "patient_id": self.patient_id,
            "attribute": self.attribute.value,
            "source": _source_dict(self.source),
        }

    def _to_dict_data(self, state: Any) -> dict[str, object]:
        return {
            **self.reference_dict(),
            "value": self.value,
            "context_date": (
                self.context_date.isoformat()
                if self.context_date is not None
                else None
            ),
            "time_basis": self.time_basis.value,
        }

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready attributed observation."""

        return serialize_entity(self)


@dataclass(frozen=True)
class PatientAttributeAsOfPolicy:
    """Explicit temporal policy for selecting one patient attribute value."""

    as_of_date: date
    time_basis: PatientObservationTimeBasis
    undated: UndatedObservationPolicy

    def __post_init__(self) -> None:
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date must be a date")
        object.__setattr__(
            self,
            "time_basis",
            PatientObservationTimeBasis(self.time_basis),
        )
        object.__setattr__(self, "undated", UndatedObservationPolicy(self.undated))

    def to_dict(self) -> dict[str, str]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "time_basis": self.time_basis.value,
            "undated": self.undated.value,
        }


@dataclass(frozen=True)
class PatientAttributeSelection:
    """Resolved or unresolved result of one explicit as-of selection."""

    patient_id: str
    attribute: PatientAttributeName
    as_of_policy: PatientAttributeAsOfPolicy
    resolution_state: ResolutionState
    selected_value: Any = None
    selected_context_date: Optional[date] = None
    supporting_sources: Tuple[Optional[SourceValue], ...] = ()
    reason: str = ""
    issues: Tuple[BuildIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.patient_id, str) or not self.patient_id.strip():
            raise ValueError("patient_id must be a non-empty string")
        object.__setattr__(self, "attribute", PatientAttributeName(self.attribute))
        if not isinstance(self.as_of_policy, PatientAttributeAsOfPolicy):
            raise TypeError("as_of_policy must be a PatientAttributeAsOfPolicy")
        object.__setattr__(
            self,
            "resolution_state",
            ResolutionState(self.resolution_state),
        )
        if (
            self.selected_context_date is not None
            and type(self.selected_context_date) is not date
        ):
            raise TypeError("selected_context_date must be a date or None")
        sources = tuple(self.supporting_sources)
        if any(
            source is not None
            and not isinstance(source, (SourceLocator, SourceRef))
            for source in sources
        ):
            raise TypeError(
                "supporting_sources must contain SourceRef, SourceLocator, or None"
            )
        if len(set(sources)) != len(sources):
            raise ValueError("supporting_sources must be unique")
        object.__setattr__(self, "supporting_sources", sources)
        issues = tuple(self.issues)
        if any(not isinstance(issue, BuildIssue) for issue in issues):
            raise TypeError("issues must contain BuildIssue values")
        if any(issue.source not in sources for issue in issues):
            raise ValueError(
                "selection issues must reference supporting source evidence"
            )
        object.__setattr__(self, "issues", issues)
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        if self.attribute is PatientAttributeName.SEX:
            if self.selected_value is not None and not isinstance(
                self.selected_value, str
            ):
                raise TypeError("selected sex value must be a string or None")
            if (
                isinstance(self.selected_value, str)
                and not self.selected_value.strip()
            ):
                raise ValueError("selected sex value must not be blank")
            if isinstance(self.selected_value, str):
                object.__setattr__(
                    self,
                    "selected_value",
                    self.selected_value.strip(),
                )
        elif self.selected_value is not None:
            if isinstance(self.selected_value, bool) or not isinstance(
                self.selected_value, Integral
            ):
                raise TypeError(
                    "selected birth_year value must be integral or None"
                )
            object.__setattr__(self, "selected_value", int(self.selected_value))
        if self.resolution_state is ResolutionState.RESOLVED:
            if self.selected_context_date is None or not sources or issues:
                raise ValueError(
                    "resolved selection requires a date and supporting sources "
                    "and cannot contain issues"
                )
        elif self.selected_context_date is not None or self.selected_value is not None:
            raise ValueError(
                "unresolved selection cannot expose a selected value or date"
            )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready selection result."""

        return {
            "patient_id": self.patient_id,
            "attribute": self.attribute.value,
            "as_of_policy": self.as_of_policy.to_dict(),
            "resolution_state": self.resolution_state.value,
            "selected_value": self.selected_value,
            "selected_context_date": (
                self.selected_context_date.isoformat()
                if self.selected_context_date is not None
                else None
            ),
            "supporting_sources": [
                _source_dict(source) for source in self.supporting_sources
            ],
            "reason": self.reason,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def select_patient_attribute_as_of(
    observations: Iterable[PatientAttributeObservation],
    *,
    patient_id: str,
    attribute: PatientAttributeName,
    policy: PatientAttributeAsOfPolicy,
) -> PatientAttributeSelection:
    """Select an attributed value only under an explicit temporal policy."""

    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ValueError("patient_id must be a non-empty string")
    selected_attribute = PatientAttributeName(attribute)
    if not isinstance(policy, PatientAttributeAsOfPolicy):
        raise TypeError("policy must be a PatientAttributeAsOfPolicy")
    candidates = tuple(observations)
    if any(not isinstance(item, PatientAttributeObservation) for item in candidates):
        raise TypeError(
            "observations must contain PatientAttributeObservation values"
        )
    candidates = tuple(
        item
        for item in candidates
        if item.patient_id == patient_id
        and item.attribute is selected_attribute
        and item.time_basis is policy.time_basis
    )
    undated = tuple(item for item in candidates if item.context_date is None)
    if undated and policy.undated is UndatedObservationPolicy.REJECT:
        issues = tuple(
            BuildIssue(
                code="undated_patient_attribute_observation",
                message=(
                    "Patient attribute observation lacks the date required by "
                    "the as-of policy."
                ),
                severity=IssueSeverity.ERROR,
                source=cast(SourceLocator, item.source),
                context={
                    "patient_id": patient_id,
                    "attribute": selected_attribute.value,
                    "time_basis": policy.time_basis.value,
                },
            )
            for item in undated
            if item.source is not None
        )
        return PatientAttributeSelection(
            patient_id=patient_id,
            attribute=selected_attribute,
            as_of_policy=policy,
            resolution_state=ResolutionState.UNRESOLVED,
            supporting_sources=_unique_sources(undated),
            reason="undated_observation_rejected",
            issues=issues,
        )

    dated = tuple(
        item
        for item in candidates
        if item.context_date is not None
        and item.context_date <= policy.as_of_date
    )
    if not dated:
        return PatientAttributeSelection(
            patient_id=patient_id,
            attribute=selected_attribute,
            as_of_policy=policy,
            resolution_state=ResolutionState.UNRESOLVED,
            reason="no_eligible_observation",
        )
    selected_date = max(
        item.context_date for item in dated if item.context_date is not None
    )
    latest = tuple(item for item in dated if item.context_date == selected_date)
    distinct_values = []
    for item in latest:
        if item.value not in distinct_values:
            distinct_values.append(item.value)
    sources = _unique_sources(latest)
    if len(distinct_values) > 1:
        issue_source = next(
            (item.source for item in latest if item.source is not None),
            None,
        )
        issue = (
            BuildIssue(
                code="conflicting_patient_attribute_as_of",
                message=(
                    "Patient attribute observations conflict at the latest "
                    "eligible context date."
                ),
                severity=IssueSeverity.ERROR,
                source=cast(SourceLocator, issue_source),
                context={
                    "patient_id": patient_id,
                    "attribute": selected_attribute.value,
                    "context_date": selected_date.isoformat(),
                    "values": distinct_values,
                },
            )
            if issue_source is not None
            else None
        )
        return PatientAttributeSelection(
            patient_id=patient_id,
            attribute=selected_attribute,
            as_of_policy=policy,
            resolution_state=ResolutionState.UNRESOLVED,
            supporting_sources=sources,
            reason="conflicting_latest_observations",
            issues=() if issue is None else (issue,),
        )
    return PatientAttributeSelection(
        patient_id=patient_id,
        attribute=selected_attribute,
        as_of_policy=policy,
        resolution_state=ResolutionState.RESOLVED,
        selected_value=distinct_values[0],
        selected_context_date=selected_date,
        supporting_sources=sources,
        reason="latest_eligible_observation",
    )


def _unique_sources(
    observations: Iterable[PatientAttributeObservation],
) -> Tuple[Optional[SourceValue], ...]:
    sources = []
    for observation in observations:
        if observation.source not in sources:
            sources.append(observation.source)
    return tuple(sources)
