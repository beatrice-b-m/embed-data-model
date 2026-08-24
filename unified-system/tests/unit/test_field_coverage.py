from __future__ import annotations

import json

import pytest

from embed_toolkit.config.field_coverage import (
    FieldCoverageDeclaration,
    FieldCoverageManifest,
)
from embed_toolkit.core.provenance import AvailabilityState, ResolutionState


def declaration(
    governed_field: str,
    state: object,
    reason: str = "Test coverage rationale.",
    source_fields: tuple[str, ...] = (),
) -> FieldCoverageDeclaration:
    return FieldCoverageDeclaration(
        governed_field=governed_field,
        state=state,  # type: ignore[arg-type]
        reason=reason,
        source_fields=source_fields,
    )


def test_manifest_classifies_every_supported_coverage_state_deterministically() -> None:
    governed_fields = tuple(f"finding.field_{index}" for index in range(6))
    declarations = (
        declaration(
            governed_fields[5],
            AvailabilityState.UNSUPPORTED,
        ),
        declaration(
            governed_fields[0],
            AvailabilityState.BOUND,
            source_fields=("z_source", "a_source"),
        ),
        declaration(governed_fields[3], AvailabilityState.UNAVAILABLE),
        declaration(governed_fields[2], ResolutionState.UNRESOLVED),
        declaration(governed_fields[4], AvailabilityState.UNMODELED),
        declaration(governed_fields[1], AvailabilityState.RAW_ONLY),
    )
    manifest = FieldCoverageManifest(
        source_profile="test-profile",
        governed_fields=tuple(reversed(governed_fields)),
        declarations=declarations,
    )

    serialized = manifest.to_dict()

    assert [item["state"] for item in serialized["declarations"]] == [
        "bound",
        "raw_only",
        "unresolved",
        "unavailable",
        "unmodeled",
        "unsupported",
    ]
    assert serialized["declarations"][0]["source_fields"] == [
        "a_source",
        "z_source",
    ]
    assert serialized["governed_fields"] == list(governed_fields)
    assert json.loads(json.dumps(serialized)) == serialized


def test_manifest_detects_missing_duplicate_and_unexpected_declarations() -> None:
    first = declaration("finding.location", AvailabilityState.BOUND)
    second = declaration("finding.depth", AvailabilityState.RAW_ONLY)

    with pytest.raises(ValueError, match="Missing field coverage declarations"):
        FieldCoverageManifest(
            "internal-v2",
            ("finding.location", "finding.depth"),
            (first,),
        )
    with pytest.raises(ValueError, match="Duplicate field coverage declarations"):
        FieldCoverageManifest(
            "internal-v2",
            ("finding.location",),
            (first, first),
        )
    with pytest.raises(ValueError, match="Duplicate governed fields"):
        FieldCoverageManifest(
            "internal-v2",
            ("finding.location", "finding.location"),
            (first,),
        )
    with pytest.raises(ValueError, match="Unexpected field coverage declarations"):
        FieldCoverageManifest(
            "internal-v2",
            ("finding.location",),
            (first, second),
        )


def test_field_declarations_validate_state_reason_and_source_field_identity() -> None:
    coverage = declaration(
        "pathology.report_documented_date",
        "unresolved",
        "The profile binding is provisional.",
        ("pdate_anon",),
    )

    assert coverage.state is ResolutionState.UNRESOLVED
    assert coverage.to_dict()["source_fields"] == ["pdate_anon"]

    with pytest.raises(ValueError, match="cannot use the resolved state"):
        declaration("finding.location", ResolutionState.RESOLVED)
    with pytest.raises(ValueError, match="reason must be a non-empty"):
        declaration("finding.location", AvailabilityState.BOUND, reason="")
    with pytest.raises(ValueError, match="Duplicate source fields"):
        declaration(
            "finding.location",
            AvailabilityState.BOUND,
            source_fields=("loc", "loc"),
        )


def test_declaration_lookup_is_explicit_for_fields_outside_the_manifest() -> None:
    coverage = declaration("finding.location", AvailabilityState.RAW_ONLY)
    manifest = FieldCoverageManifest(
        "internal-v2",
        ("finding.location",),
        (coverage,),
    )

    assert manifest.declaration_for("finding.location") is coverage
    with pytest.raises(KeyError, match="finding.depth"):
        manifest.declaration_for("finding.depth")
