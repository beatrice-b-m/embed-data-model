from __future__ import annotations

import json

import pytest

from embed_toolkit.config.capabilities import (
    CapabilityDeclaration,
    GovernedConcept,
    ProfileCapabilities,
)
from embed_toolkit.core.provenance import AvailabilityState, ResolutionState


def test_capabilities_express_unresolved_unavailable_and_unsupported_concepts() -> None:
    governed_concepts = (
        GovernedConcept.IMAGING_EPISODE,
        GovernedConcept.RADIOLOGY_REPORT,
        GovernedConcept.RISK_ASSESSMENT,
        GovernedConcept.PATHOLOGY_SPECIMEN,
    )
    capabilities = ProfileCapabilities(
        source_profile="internal-v2",
        governed_concepts=governed_concepts,
        declarations=(
            CapabilityDeclaration(
                GovernedConcept.PATHOLOGY_SPECIMEN,
                AvailabilityState.UNSUPPORTED,
                "The source surface does not establish specimen identity.",
            ),
            CapabilityDeclaration(
                GovernedConcept.IMAGING_EPISODE,
                ResolutionState.UNRESOLVED,
                "Linked accessions do not define complete episode boundaries.",
            ),
            CapabilityDeclaration(
                GovernedConcept.RISK_ASSESSMENT,
                ResolutionState.UNRESOLVED,
                "The output scale and time horizon are not governed.",
            ),
            CapabilityDeclaration(
                GovernedConcept.RADIOLOGY_REPORT,
                AvailabilityState.UNAVAILABLE,
                "The profile has no physical report-version binding.",
            ),
        ),
    )

    serialized = capabilities.to_dict()

    assert serialized["governed_concepts"] == [
        "imaging_episode",
        "pathology_specimen",
        "radiology_report",
        "risk_assessment",
    ]
    assert [item["concept"] for item in serialized["declarations"]] == [
        "imaging_episode",
        "pathology_specimen",
        "radiology_report",
        "risk_assessment",
    ]
    assert capabilities.declaration_for(
        GovernedConcept.IMAGING_EPISODE
    ).state is ResolutionState.UNRESOLVED
    assert capabilities.declaration_for(
        GovernedConcept.PATHOLOGY_SPECIMEN
    ).state is AvailabilityState.UNSUPPORTED
    assert json.loads(json.dumps(serialized)) == serialized


def test_capability_declarations_reject_duplicates_empty_reasons_and_resolved() -> None:
    episode = CapabilityDeclaration(
        GovernedConcept.IMAGING_EPISODE,
        "unresolved",
        "Episode boundaries are unresolved.",
    )

    with pytest.raises(ValueError, match="Duplicate capability declarations"):
        ProfileCapabilities(
            "internal-v2",
            (GovernedConcept.IMAGING_EPISODE,),
            (episode, episode),
        )
    with pytest.raises(ValueError, match="reason must be a non-empty"):
        CapabilityDeclaration(
            GovernedConcept.RADIOLOGY_REPORT,
            AvailabilityState.UNAVAILABLE,
            "",
        )
    with pytest.raises(ValueError, match="cannot use the resolved state"):
        CapabilityDeclaration(
            GovernedConcept.RISK_ASSESSMENT,
            ResolutionState.RESOLVED,
            "Invalid classification.",
        )


def test_capability_manifest_does_not_require_fabricated_concept_instances() -> None:
    declaration = CapabilityDeclaration(
        GovernedConcept.RADIOLOGY_REPORT,
        AvailabilityState.UNMODELED,
        "The portable concept exists without an active model binding.",
    )

    capabilities = ProfileCapabilities(
        "portable",
        (GovernedConcept.RADIOLOGY_REPORT,),
        (declaration,),
    )

    assert capabilities.to_dict() == {
        "source_profile": "portable",
        "governed_concepts": ["radiology_report"],
        "declarations": [
            {
                "concept": "radiology_report",
                "state": "unmodeled",
                "reason": (
                    "The portable concept exists without an active model binding."
                ),
            }
        ],
    }
    with pytest.raises(KeyError, match="risk_assessment"):
        capabilities.declaration_for(GovernedConcept.RISK_ASSESSMENT)


def test_capabilities_require_complete_unique_governed_boundary() -> None:
    episode = CapabilityDeclaration(
        GovernedConcept.IMAGING_EPISODE,
        ResolutionState.UNRESOLVED,
        "Episode boundaries are unresolved.",
    )
    report = CapabilityDeclaration(
        GovernedConcept.RADIOLOGY_REPORT,
        AvailabilityState.UNAVAILABLE,
        "Report versions have no physical binding.",
    )

    with pytest.raises(ValueError, match="Duplicate governed concepts"):
        ProfileCapabilities(
            "internal-v2",
            (
                GovernedConcept.IMAGING_EPISODE,
                GovernedConcept.IMAGING_EPISODE,
            ),
            (episode,),
        )
    with pytest.raises(ValueError, match="Missing capability declarations"):
        ProfileCapabilities(
            "internal-v2",
            (
                GovernedConcept.IMAGING_EPISODE,
                GovernedConcept.RADIOLOGY_REPORT,
            ),
            (episode,),
        )
    with pytest.raises(ValueError, match="Unexpected capability declarations"):
        ProfileCapabilities(
            "internal-v2",
            (GovernedConcept.IMAGING_EPISODE,),
            (episode, report),
        )
