from __future__ import annotations

import json
from datetime import date
from typing import Optional

import pytest

from embed_toolkit.core.build_policy import (
    BuildMode,
    BuildPolicy,
    BuildPolicyError,
)
from embed_toolkit.core.provenance import (
    AvailabilityState,
    BuildIssue,
    IssueSeverity,
    ResolutionState,
    SourceLocator,
    SourceOccurrence,
    SourceScopeKind,
)


def locator(row_ordinal: int) -> SourceLocator:
    return SourceLocator(
        scope="internal-v2-2026-08",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="internal-v2",
        source_table="magview",
        row_ordinal=row_ordinal,
    )


def unresolved_occurrence(row_ordinal: int) -> SourceOccurrence:
    source = locator(row_ordinal)
    issue = BuildIssue(
        code="missing_patient_identity",
        message="Patient identity is required to construct clinical objects.",
        severity=IssueSeverity.ERROR,
        source=source,
        context={"field": "empi_anon"},
    )
    return SourceOccurrence(
        locator=source,
        raw_values={"empi_anon": None, "numfind": None},
        resolution_state=ResolutionState.UNRESOLVED,
        issues=(issue,),
    )


def test_identical_missing_clinical_values_remain_distinct_occurrences() -> None:
    first = unresolved_occurrence(10)
    second = unresolved_occurrence(11)

    assert first.raw_values == second.raw_values
    assert first.locator != second.locator
    assert first != second


def test_build_policy_is_strict_by_default_and_audit_retains_evidence() -> None:
    occurrence = unresolved_occurrence(10)

    with pytest.raises(BuildPolicyError) as exc_info:
        BuildPolicy().review(occurrence)

    assert exc_info.value.issue is occurrence.issues[0]
    assert BuildPolicy(BuildMode.AUDIT).review(occurrence) is occurrence


def test_warning_does_not_raise_in_strict_mode() -> None:
    source = locator(4)
    occurrence = SourceOccurrence(
        locator=source,
        raw_values={"side": "?"},
        resolution_state=ResolutionState.RESOLVED,
        issues=(
            BuildIssue(
                code="unknown_laterality",
                message="Laterality could not be normalized.",
                severity=IssueSeverity.WARNING,
                source=source,
            ),
        ),
    )

    assert BuildPolicy().review(occurrence) is occurrence


def test_contracts_serialize_to_json_ready_values() -> None:
    base = unresolved_occurrence(10)
    occurrence = SourceOccurrence(
        locator=base.locator,
        raw_values={
            "empi_anon": None,
            "numfind": None,
            "observed_on": date(2026, 8, 24),
        },
        resolution_state=base.resolution_state,
        issues=base.issues,
    )
    serialized = occurrence.to_dict()

    assert serialized == {
        "locator": {
            "scope": "internal-v2-2026-08",
            "scope_kind": "materialization",
            "source_profile": "internal-v2",
            "source_table": "magview",
            "row_ordinal": 10,
            "source_key": None,
        },
        "raw_values": {
            "empi_anon": None,
            "numfind": None,
            "observed_on": "2026-08-24",
        },
        "resolution_state": "unresolved",
        "issues": [
            {
                "code": "missing_patient_identity",
                "message": (
                    "Patient identity is required to construct clinical objects."
                ),
                "severity": "error",
                "source": locator(10).to_dict(),
                "context": {"field": "empi_anon"},
            }
        ],
    }
    assert json.loads(json.dumps(serialized)) == serialized
    assert BuildPolicy().to_dict() == {"mode": "strict"}
    assert {state.value for state in AvailabilityState} == {
        "bound",
        "raw_only",
        "unavailable",
        "unmodeled",
        "unsupported",
    }


def test_source_locator_accepts_a_source_key_as_ordinal_alternative() -> None:
    source = SourceLocator(
        scope="embed-v1c",
        scope_kind=SourceScopeKind.DATASET,
        source_profile="internal-v1c",
        source_table="images",
        source_key="SOP-123",
    )

    assert source.row_ordinal is None
    assert source.to_dict()["source_key"] == "SOP-123"


@pytest.mark.parametrize(
    ("row_ordinal", "source_key"),
    [(None, None), (1, "record-1")],
)
def test_source_locator_requires_one_row_address(
    row_ordinal: Optional[int],
    source_key: Optional[str],
) -> None:
    with pytest.raises(ValueError, match="Exactly one"):
        SourceLocator(
            scope="embed-v1c",
            scope_kind=SourceScopeKind.DATASET,
            source_profile="internal-v1c",
            source_table="images",
            row_ordinal=row_ordinal,
            source_key=source_key,
        )
