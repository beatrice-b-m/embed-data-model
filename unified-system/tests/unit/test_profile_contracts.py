from __future__ import annotations

import json
from dataclasses import replace

import pytest

from embed_toolkit.adapters.embed import (
    assemble_clinical_image_graph,
    build_clinical_tables,
    build_image_tables,
)
from embed_toolkit.config.capabilities import (
    CapabilityDeclaration,
    GovernedConcept,
    ProfileCapabilities,
)
from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import (
    INTERNAL_V1C_CONTRACT,
    INTERNAL_V1C_FIELD_INVENTORY,
    INTERNAL_V2_CONTRACT,
    INTERNAL_V2_FIELD_INVENTORY,
    REPOSITORY_FIELD_INVENTORY,
    ProfileContract,
)
from embed_toolkit.core.provenance import (
    AvailabilityState,
    BuildIssue,
    IssueSeverity,
    ResolutionState,
)
from profile_contract_support import contract_for_columns


def test_repository_inventory_is_repo_scoped_and_externally_unresolved() -> None:
    assert REPOSITORY_FIELD_INVENTORY.governed_fields == tuple(
        sorted(EmbedColumnConfig.field_names())
    )
    assert (
        REPOSITORY_FIELD_INVENTORY.external_catalog_completeness
        is ResolutionState.UNRESOLVED
    )
    serialized = REPOSITORY_FIELD_INVENTORY.to_dict()
    assert "count" not in serialized
    assert "external" in serialized["completeness_scope"]
    json.dumps(serialized)


def test_profile_inventories_have_exact_configured_boundaries() -> None:
    assert INTERNAL_V2_FIELD_INVENTORY.governed_fields == (
        "accession",
        "cohort_id",
        "exam_description",
        "finding_assessment",
        "finding_depth",
        "finding_distance",
        "finding_laterality",
        "finding_location",
        "finding_number",
        "finding_recommendation",
        "pathology_diagnosis_prefix",
        "pathology_report_date",
        "pathology_severity",
        "patient_id",
        "procedure_date",
        "procedure_laterality",
        "procedure_type",
        "sex",
        "study_date",
    )
    assert INTERNAL_V1C_FIELD_INVENTORY.governed_fields == (
        "accession",
        "acquisition_group_id",
        "derived_image_type",
        "image_frames",
        "image_height",
        "image_id",
        "image_laterality",
        "image_modality",
        "image_orientation",
        "image_path",
        "image_view",
        "image_width",
        "nipple_confidence",
        "nipple_x",
        "nipple_y",
        "patient_id",
        "pnl_slope",
        "roi_coords",
        "roi_depth_derived",
        "roi_frames",
        "roi_source",
        "series_id",
        "sop_instance_uid",
    )
    assert INTERNAL_V2_FIELD_INVENTORY.provenance == (
        "embed_toolkit.config.columns.EmbedColumnConfig",
    )
    assert INTERNAL_V1C_FIELD_INVENTORY.provenance == (
        "embed_toolkit.config.columns.EmbedColumnConfig",
    )
    assert (
        INTERNAL_V2_CONTRACT.field_coverage.declaration_for(
            "pathology_diagnosis_prefix"
        ).source_fields
        == ("path1", "path10", "path2", "path3", "path4", "path5", "path6", "path7", "path8", "path9")
    )


def test_built_in_profiles_expose_only_evidenced_capability_boundaries() -> None:
    expected_v2 = {
        GovernedConcept.PATIENT: AvailabilityState.BOUND,
        GovernedConcept.IMAGING_EPISODE: ResolutionState.UNRESOLVED,
        GovernedConcept.IMAGING_EXAM: AvailabilityState.BOUND,
        GovernedConcept.BREAST_SIDE: AvailabilityState.BOUND,
        GovernedConcept.IMAGING_FINDING: AvailabilityState.BOUND,
        GovernedConcept.IMAGING_INTERPRETATION: AvailabilityState.BOUND,
        GovernedConcept.RADIOLOGY_REPORT: AvailabilityState.UNAVAILABLE,
        GovernedConcept.IMAGE: AvailabilityState.UNAVAILABLE,
        GovernedConcept.REGION_OF_INTEREST: AvailabilityState.UNAVAILABLE,
        GovernedConcept.PROCEDURE: AvailabilityState.BOUND,
        GovernedConcept.PATHOLOGY_SPECIMEN: AvailabilityState.UNSUPPORTED,
        GovernedConcept.PATHOLOGY_OBSERVATION: AvailabilityState.BOUND,
        GovernedConcept.PATHOLOGY_DIAGNOSIS: AvailabilityState.BOUND,
        GovernedConcept.RISK_ASSESSMENT: ResolutionState.UNRESOLVED,
    }
    expected_v1c = {
        GovernedConcept.PATIENT: ResolutionState.UNRESOLVED,
        GovernedConcept.IMAGING_EPISODE: AvailabilityState.UNAVAILABLE,
        GovernedConcept.IMAGING_EXAM: ResolutionState.UNRESOLVED,
        GovernedConcept.BREAST_SIDE: ResolutionState.UNRESOLVED,
        GovernedConcept.IMAGING_FINDING: AvailabilityState.UNAVAILABLE,
        GovernedConcept.IMAGING_INTERPRETATION: AvailabilityState.UNAVAILABLE,
        GovernedConcept.RADIOLOGY_REPORT: AvailabilityState.UNAVAILABLE,
        GovernedConcept.IMAGE: AvailabilityState.BOUND,
        GovernedConcept.REGION_OF_INTEREST: AvailabilityState.BOUND,
        GovernedConcept.PROCEDURE: AvailabilityState.UNAVAILABLE,
        GovernedConcept.PATHOLOGY_SPECIMEN: AvailabilityState.UNSUPPORTED,
        GovernedConcept.PATHOLOGY_OBSERVATION: AvailabilityState.UNAVAILABLE,
        GovernedConcept.PATHOLOGY_DIAGNOSIS: AvailabilityState.UNAVAILABLE,
        GovernedConcept.RISK_ASSESSMENT: AvailabilityState.UNAVAILABLE,
    }
    assert {
        concept: INTERNAL_V2_CONTRACT.capabilities.declaration_for(concept).state
        for concept in GovernedConcept
    } == expected_v2
    assert {
        concept: INTERNAL_V1C_CONTRACT.capabilities.declaration_for(concept).state
        for concept in GovernedConcept
    } == expected_v1c
    for contract in (INTERNAL_V2_CONTRACT, INTERNAL_V1C_CONTRACT):
        assert (
            contract.field_coverage.governed_fields
            == contract.field_inventory.governed_fields
        )
    assert (
        INTERNAL_V1C_CONTRACT.field_coverage.declaration_for("image_id").state
        is AvailabilityState.BOUND
    )
    assert (
        INTERNAL_V1C_CONTRACT.field_coverage.declaration_for("nipple_x").state
        is AvailabilityState.RAW_ONLY
    )
    assert "birth_year" not in INTERNAL_V2_CONTRACT.field_inventory.governed_fields


def test_contract_rejects_incomplete_boundaries_and_false_source_claims() -> None:
    contract = _custom_contract("custom-clinical")
    incomplete_capabilities = ProfileCapabilities(
        source_profile=contract.source_profile,
        governed_concepts=(GovernedConcept.PATIENT,),
        declarations=(
            CapabilityDeclaration(
                GovernedConcept.PATIENT,
                AvailabilityState.BOUND,
                "The caller binds patient identity.",
            ),
        ),
    )
    with pytest.raises(ValueError, match="complete governed concept boundary"):
        replace(contract, capabilities=incomplete_capabilities)

    wider_inventory = replace(
        contract.field_inventory,
        governed_fields=("patient_id", "sex"),
    )
    with pytest.raises(ValueError, match="exactly match"):
        replace(contract, field_inventory=wider_inventory)

    declaration = contract.field_coverage.declaration_for("patient_id")
    no_evidence = replace(declaration, source_fields=())
    with pytest.raises(ValueError, match="physical source evidence"):
        replace(
            contract,
            field_coverage=replace(
                contract.field_coverage,
                declarations=tuple(
                    no_evidence if item is declaration else item
                    for item in contract.field_coverage.declarations
                ),
            ),
        )

    false_claim = replace(
        declaration,
        state=AvailabilityState.UNAVAILABLE,
        source_fields=("custom_patient_id",),
    )
    with pytest.raises(ValueError, match="cannot claim source fields"):
        replace(
            contract,
            field_coverage=replace(
                contract.field_coverage,
                declarations=tuple(
                    false_claim if item is declaration else item
                    for item in contract.field_coverage.declarations
                ),
            ),
        )

    unresolved = INTERNAL_V1C_CONTRACT.field_coverage.declaration_for("image_id")
    unresolved_without_candidate = replace(unresolved, source_fields=())
    with pytest.raises(ValueError, match="unresolved fields require"):
        replace(
            INTERNAL_V1C_CONTRACT,
            field_coverage=replace(
                INTERNAL_V1C_CONTRACT.field_coverage,
                declarations=tuple(
                    unresolved_without_candidate if item is unresolved else item
                    for item in INTERNAL_V1C_CONTRACT.field_coverage.declarations
                ),
            ),
        )


def _custom_contract(source_profile: str) -> ProfileContract:
    return replace(
        INTERNAL_V2_CONTRACT,
        source_profile=source_profile,
        capabilities=replace(
            INTERNAL_V2_CONTRACT.capabilities,
            source_profile=source_profile,
        ),
        field_coverage=replace(
            INTERNAL_V2_CONTRACT.field_coverage,
            source_profile=source_profile,
        ),
    )


def test_unknown_profiles_require_caller_contracts_and_get_no_builtin_claims() -> None:
    with pytest.raises(ValueError, match="caller-supplied contract"):
        build_clinical_tables([], source_profile="custom-clinical")
    with pytest.raises(ValueError, match="caller-supplied contract"):
        build_image_tables([], source_profile="custom-image")

    contract = _custom_contract("custom-clinical")
    built = build_clinical_tables(
        [],
        source_profile="custom-clinical",
        profile_contract=contract,
    )
    assert built.profile_contract is contract
    assert set(built.profile_contract.capabilities.governed_concepts) == set(
        GovernedConcept
    )


def test_profile_validation_is_exact_and_precedes_row_consumption() -> None:
    class ExplodingRows:
        def __iter__(self):
            raise AssertionError("rows must not be consumed before profile validation")

    for legacy_or_unknown in ("embed_context_internal", "public-v1c"):
        with pytest.raises(ValueError, match="caller-supplied contract"):
            build_clinical_tables(
                ExplodingRows(),
                source_profile=legacy_or_unknown,
            )

    clinical_contract = _custom_contract("custom-clinical")
    with pytest.raises(ValueError, match="kind must be 'image'"):
        build_image_tables(
            ExplodingRows(),
            source_profile="custom-clinical",
            profile_contract=clinical_contract,
        )

    with pytest.raises(ValueError, match="profile identity"):
        build_clinical_tables(
            ExplodingRows(),
            source_profile="different-profile",
            profile_contract=clinical_contract,
        )

    overridden_columns = EmbedColumnConfig(patient_id="custom_patient_id")
    with pytest.raises(ValueError, match="source_fields for 'patient_id'"):
        build_clinical_tables(
            ExplodingRows(),
            columns=overridden_columns,
        )
    with pytest.raises(ValueError, match="source_fields for 'patient_id'"):
        build_image_tables(
            ExplodingRows(),
            columns=overridden_columns,
        )
    with pytest.raises(ValueError, match="source_fields for 'patient_id'"):
        build_clinical_tables(
            ExplodingRows(),
            columns=overridden_columns,
            source_profile="custom-clinical",
            profile_contract=clinical_contract,
        )


def test_custom_builder_accepts_state_appropriate_empty_source_claims() -> None:
    columns = EmbedColumnConfig(patient_id="custom_patient_id")
    contract = contract_for_columns(
        INTERNAL_V2_CONTRACT,
        "state-aware-custom-clinical",
        columns,
    )
    no_source_states = {
        "cohort_id": AvailabilityState.UNMODELED,
        "sex": AvailabilityState.UNSUPPORTED,
    }
    contract = replace(
        contract,
        field_coverage=replace(
            contract.field_coverage,
            declarations=tuple(
                replace(
                    declaration,
                    state=no_source_states[declaration.governed_field],
                    source_fields=(),
                )
                if declaration.governed_field in no_source_states
                else declaration
                for declaration in contract.field_coverage.declarations
            ),
        ),
    )

    built = build_clinical_tables(
        [],
        columns=columns,
        source_profile=contract.source_profile,
        profile_contract=contract,
    )

    patient_declaration = built.profile_contract.field_coverage.declaration_for(
        "patient_id"
    )
    assert patient_declaration.state is AvailabilityState.BOUND
    assert "custom_patient_id" in patient_declaration.source_fields
    for governed_field, state in no_source_states.items():
        declaration = built.profile_contract.field_coverage.declaration_for(
            governed_field
        )
        assert declaration.state is state
        assert declaration.source_fields == ()


def test_build_results_and_combined_graph_preserve_distinct_contracts() -> None:
    clinical = build_clinical_tables([])
    images = build_image_tables([])
    graph = assemble_clinical_image_graph(clinical, images)

    assert clinical.profile_contract is INTERNAL_V2_CONTRACT
    assert images.profile_contract is INTERNAL_V1C_CONTRACT
    assert graph.clinical_profile_contract is clinical.profile_contract
    assert graph.image_profile_contract is images.profile_contract
    serialized = graph.to_dict()
    assert serialized["clinical_profile_contract"]["source_profile"] == "internal-v2"
    assert serialized["image_profile_contract"]["source_profile"] == "internal-v2"
    json.dumps(serialized)


def test_clinical_constructor_rejects_wrong_profile_nested_evidence() -> None:
    clinical = build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "birth_year": 1970,
                "acc_anon": "ACC-1",
                "numfind": "1",
                "side": "L",
                "asses": "4",
                "location": "upper outer quadrant",
                "procedure_type": "biopsy",
                "procedure_date": "2020-01-01",
                "bside": "L",
                "path_severity": 2,
                "path1": "descriptor",
            }
        ]
    )
    wrong = replace(
        clinical.source_occurrences[0].locator,
        source_profile="wrong-clinical-profile",
    )
    finding = clinical.findings[0]
    bad_interpretation = replace(finding.interpretation, sources=(wrong,))
    bad_finding = replace(finding, interpretation=bad_interpretation)
    bad_exam = replace(clinical.exams[0], findings=[bad_finding])
    bad_patient = replace(clinical.patients[0], exams=[bad_exam])
    with pytest.raises(ValueError, match="Clinical tables source profile"):
        replace(clinical, patients=(bad_patient,))

    bad_procedure = replace(clinical.procedures[0], sources=[wrong])
    with pytest.raises(ValueError, match="Clinical tables source profile"):
        replace(clinical, procedures=(bad_procedure,))

    bad_pathology = replace(clinical.pathology_observations[0], source=wrong)
    with pytest.raises(ValueError, match="Clinical tables source profile"):
        replace(clinical, pathology_observations=(bad_pathology,))

    bad_issue = BuildIssue(
        code="wrong_profile",
        message="Wrong profile evidence for constructor validation.",
        severity=IssueSeverity.WARNING,
        source=wrong,
    )
    with pytest.raises(ValueError, match="Clinical tables source profile"):
        replace(clinical, build_issues=(bad_issue,))

    image = build_image_tables(
        [
            {
                "image_id": "IMG-CLINICAL-LEAK",
                "acc_anon": "ACC-1",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
            }
        ]
    ).images[0]
    clinical.exams[0].add_image(image)
    with pytest.raises(ValueError, match="cannot own image evidence"):
        replace(clinical)


def test_image_and_graph_constructors_reject_wrong_profile_nested_evidence() -> None:
    image_tables = build_image_tables(
        [
            {
                "image_id": "IMG-1",
                "acc_anon": "ACC-1",
                "empi_anon": "P-1",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
                "FinalImageType": "2D",
                "ROI_coords": [[1, 2, 3, 4]],
            }
        ]
    )
    wrong_image = replace(
        image_tables.source_occurrences[0].locator,
        source_profile="wrong-image-profile",
    )
    bad_locator = replace(
        image_tables.rois[0].locator,
        image_locator=wrong_image,
    )
    bad_roi = replace(
        image_tables.rois[0],
        locator=bad_locator,
        sources=(wrong_image,),
    )
    with pytest.raises(ValueError, match="Image tables source profile"):
        replace(image_tables, rois=(bad_roi,))

    bad_image = replace(
        image_tables.images[0],
        sources=[wrong_image],
        attribute_sources={},
    )
    with pytest.raises(ValueError, match="Image tables source profile"):
        replace(image_tables, images=(bad_image,), rois=())

    clinical = build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "numfind": "1",
                "side": "L",
                "asses": "4",
            }
        ]
    )
    graph = assemble_clinical_image_graph(clinical, image_tables)
    wrong_clinical = replace(
        clinical.source_occurrences[0].locator,
        source_profile="wrong-clinical-profile",
    )
    finding = graph.exams[0].findings[0]
    bad_interpretation = replace(finding.interpretation, sources=(wrong_clinical,))
    bad_finding = replace(finding, interpretation=bad_interpretation)
    bad_exam = replace(graph.exams[0], findings=[bad_finding])
    with pytest.raises(ValueError, match="Graph clinical evidence source profile"):
        replace(graph, exams=(bad_exam,))

    graph_bad_image = replace(
        graph.images[0],
        sources=[wrong_image],
        attribute_sources={},
    )
    with pytest.raises(ValueError, match="Graph image and reconciliation evidence"):
        replace(graph, images=(graph_bad_image,))

    bad_reconciliation_issue = BuildIssue(
        code="wrong_profile",
        message="Wrong reconciliation profile evidence.",
        severity=IssueSeverity.WARNING,
        source=wrong_clinical,
    )
    with pytest.raises(ValueError, match="Graph image and reconciliation evidence"):
        replace(graph, build_issues=(bad_reconciliation_issue,))
