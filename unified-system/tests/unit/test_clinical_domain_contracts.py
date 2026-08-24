from __future__ import annotations

import json

import pytest

from embed_toolkit.clinical.associations import (
    AttributionStatus,
    ClinicalObjectKind,
    ClinicalObjectReference,
    FindingProcedureLink,
)
from embed_toolkit.clinical.interpretations import ImagingInterpretation
from embed_toolkit.clinical.pathology import (
    PathologyAttributionLink,
    PathologyDiagnosis,
    PathologyObservation,
    PathologyRecordKind,
    PathologyReference,
    PathologySeverity,
)
from embed_toolkit.clinical.procedures import (
    ProcedureIdentity,
    UnresolvedProcedureOccurrence,
)
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import (
    AvailabilityState,
    ResolutionState,
    SourceLocator,
    SourceOccurrence,
    SourceScopeKind,
)


def source(row_ordinal: int = 3) -> SourceLocator:
    return SourceLocator(
        scope="internal-v2-materialization",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="embed_context_internal",
        source_table="magview",
        row_ordinal=row_ordinal,
    )


def procedure_identity() -> ProcedureIdentity:
    return ProcedureIdentity(
        patient_id="P-1",
        performed_date="2020-01-02",
        procedure_type="core biopsy",
        laterality=Laterality.LEFT,
    )


def test_unresolved_procedure_is_source_evidence_not_resolved_identity() -> None:
    occurrence = SourceOccurrence(
        locator=source(),
        raw_values={"type": "core biopsy", "procdate_anon": None},
        resolution_state=ResolutionState.UNRESOLVED,
    )
    unresolved = UnresolvedProcedureOccurrence(
        occurrence=occurrence,
        missing_identity_fields=("performed_date", "laterality"),
        patient_id="P-1",
        procedure_type="core biopsy",
    )

    assert unresolved.to_dict()["occurrence"]["resolution_state"] == "unresolved"
    assert unresolved.to_dict()["missing_identity_fields"] == [
        "performed_date",
        "laterality",
    ]
    with pytest.raises(ValueError, match="unresolved source state"):
        UnresolvedProcedureOccurrence(
            occurrence=SourceOccurrence(
                locator=source(),
                raw_values={},
                resolution_state=ResolutionState.RESOLVED,
            ),
            missing_identity_fields=("performed_date",),
        )


@pytest.mark.parametrize(
    ("missing_fields", "candidate", "message"),
    [
        (
            ("performed_date", "performed_date", "laterality"),
            {},
            "must not contain duplicates",
        ),
        (
            ("performed_date", "unknown_field", "laterality"),
            {},
            "Unknown procedure identity fields",
        ),
        (
            ("performed_date", "laterality"),
            {"performed_date": "2020-01-02"},
            "must match absent or unknown candidate values",
        ),
        (
            ("performed_date",),
            {"laterality": Laterality.UNKNOWN},
            "must match absent or unknown candidate values",
        ),
    ],
)
def test_unresolved_procedure_fields_match_candidate_values(
    missing_fields: tuple,
    candidate: dict,
    message: str,
) -> None:
    occurrence = SourceOccurrence(
        locator=source(),
        raw_values={},
        resolution_state=ResolutionState.UNRESOLVED,
    )
    values = {
        "patient_id": "P-1",
        "performed_date": None,
        "procedure_type": "core biopsy",
        "laterality": Laterality.LEFT,
    }
    values.update(candidate)

    with pytest.raises(ValueError, match=message):
        UnresolvedProcedureOccurrence(
            occurrence=occurrence,
            missing_identity_fields=missing_fields,
            **values,
        )


def test_resolved_procedure_identity_and_finding_link_are_non_recursive() -> None:
    identity = procedure_identity()
    link = FindingProcedureLink(
        accession_number="ACC-1",
        finding_number="2",
        procedure=identity,
        status=AttributionStatus.SOURCE_COLOCATED,
        source=source(),
    )

    assert identity.to_dict()["laterality"] == "L"
    assert link.to_dict()["procedure"] == identity.to_dict()
    assert link.to_dict()["finding"] == {
        "accession_number": "ACC-1",
        "finding_number": "2",
    }
    assert ProcedureIdentity(
        patient_id="P-1",
        performed_date="2020-01-02",
        procedure_type="biopsy",
        laterality=Laterality.BILATERAL,
    ).laterality is Laterality.BILATERAL
    with pytest.raises(ValueError, match="known laterality"):
        ProcedureIdentity(
            patient_id="P-1",
            performed_date="2020-01-02",
            procedure_type="biopsy",
            laterality=Laterality.UNKNOWN,
        )


def test_pathology_descriptor_occurrences_preserve_slot_order_and_duplicates() -> None:
    first = PathologyObservation("ADH", "path1", 1, source())
    second = PathologyObservation("ADH", "path2", 2, source())

    assert first.descriptor == second.descriptor
    assert first != second
    assert [item.to_dict()["source_slot"] for item in (first, second)] == [
        "path1",
        "path2",
    ]
    with pytest.raises(ValueError, match="positive integer"):
        PathologyObservation("ADH", "path0", 0, source())


def test_pathology_diagnosis_has_explicit_report_documentation_time() -> None:
    diagnosis = PathologyDiagnosis(
        source=source(),
        diagnosis="ductal carcinoma in situ",
        severity=PathologySeverity.SEVERITY_2,
        raw_severity=2,
        report_documented_date="2020-01-05",
    )

    serialized = diagnosis.to_dict()
    assert serialized["report_documented_date"] == "2020-01-05"
    assert serialized["severity"] == 2
    assert json.loads(json.dumps(serialized)) == serialized

    with pytest.raises(ValueError, match="requires represented diagnosis evidence"):
        PathologyDiagnosis(source=source())


def test_pathology_attribution_is_explicit_and_source_scoped() -> None:
    pathology = PathologyReference(
        kind=PathologyRecordKind.OBSERVATION,
        source=source(),
        source_slot="path1",
    )
    target = ClinicalObjectReference(
        kind=ClinicalObjectKind.FINDING,
        identity=("ACC-1", "2"),
    )
    link = PathologyAttributionLink(
        pathology=pathology,
        target=target,
        status=AttributionStatus.SOURCE_COLOCATED,
        source=source(),
    )

    assert link.to_dict()["target"] == {
        "kind": "finding",
        "identity": ["ACC-1", "2"],
    }
    assert link.to_dict()["status"] == "source_colocated"
    assert json.loads(json.dumps(link.to_dict())) == link.to_dict()

    with pytest.raises(ValueError, match="provenance must match"):
        PathologyAttributionLink(
            pathology=pathology,
            target=target,
            status=AttributionStatus.INFERRED,
            source=source(4),
        )


@pytest.mark.parametrize(
    "status",
    [AttributionStatus.CANDIDATE, AttributionStatus.UNRESOLVED],
)
def test_resolved_links_reject_non_attribution_statuses(
    status: AttributionStatus,
) -> None:
    with pytest.raises(ValueError, match="procedure link requires attribution status"):
        FindingProcedureLink(
            accession_number="ACC-1",
            finding_number="2",
            procedure=procedure_identity(),
            status=status,
            source=source(),
        )

    pathology = PathologyReference(
        kind=PathologyRecordKind.OBSERVATION,
        source=source(),
        source_slot="path1",
    )
    with pytest.raises(ValueError, match="pathology link requires attribution status"):
        PathologyAttributionLink(
            pathology=pathology,
            target=ClinicalObjectReference(
                kind=ClinicalObjectKind.FINDING,
                identity=("ACC-1", "2"),
            ),
            status=status,
            source=source(),
        )


def test_clinical_and_pathology_references_reject_non_string_components() -> None:
    with pytest.raises(ValueError, match="identity components"):
        ClinicalObjectReference(
            kind=ClinicalObjectKind.FINDING,
            identity=("ACC-1", None),
        )

    with pytest.raises(ValueError, match="require source_slot"):
        PathologyReference(
            kind=PathologyRecordKind.OBSERVATION,
            source=source(),
            source_slot=3,
        )


def test_interpretation_tracks_field_availability_independently() -> None:
    interpretation = ImagingInterpretation(
        accession_number="ACC-1",
        finding_number="2",
        source=source(),
        assessment="4",
        assessment_availability=AvailabilityState.BOUND,
        recommendation_availability=AvailabilityState.UNAVAILABLE,
    )

    serialized = interpretation.to_dict()
    assert serialized["assessment"] == "4"
    assert serialized["assessment_availability"] == "bound"
    assert serialized["recommendation"] is None
    assert serialized["recommendation_availability"] == "unavailable"
    assert json.loads(json.dumps(serialized)) == serialized

    with pytest.raises(ValueError, match="unless availability is bound"):
        ImagingInterpretation(
            accession_number="ACC-1",
            finding_number="2",
            source=source(),
            recommendation="biopsy",
            recommendation_availability=AvailabilityState.RAW_ONLY,
        )
