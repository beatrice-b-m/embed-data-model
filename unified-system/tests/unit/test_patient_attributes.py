from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.clinical.attributes import (
    PatientAttributeAsOfPolicy,
    PatientAttributeName,
    PatientAttributeObservation,
    PatientObservationTimeBasis,
    UndatedObservationPolicy,
    select_patient_attribute_as_of,
)
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import INTERNAL_V2_CONTRACT
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.provenance import (
    ResolutionState,
    SourceLocator,
    SourceScopeKind,
)
from profile_contract_support import contract_for_columns


def source(row_ordinal: int) -> SourceLocator:
    return SourceLocator(
        scope="patient-attribute-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="clinical",
        row_ordinal=row_ordinal,
    )


def observation(
    value: object,
    context_date: Optional[date],
    row_ordinal: int,
    *,
    attribute: PatientAttributeName = PatientAttributeName.SEX,
    patient_id: str = "P-1",
) -> PatientAttributeObservation:
    return PatientAttributeObservation(
        patient_id=patient_id,
        attribute=attribute,
        value=value,
        source=source(row_ordinal),
        context_date=context_date,
        time_basis=PatientObservationTimeBasis.EXAM_DATE_CONTEXT,
    )


def as_of(
    value: date,
    *,
    undated: UndatedObservationPolicy = UndatedObservationPolicy.EXCLUDE,
) -> PatientAttributeAsOfPolicy:
    return PatientAttributeAsOfPolicy(
        as_of_date=value,
        time_basis=PatientObservationTimeBasis.EXAM_DATE_CONTEXT,
        undated=undated,
    )


def clinical_row(**values: object) -> dict[str, object]:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": "1",
        "side": "L",
        **values,
    }


def build_custom_birth_year_tables(
    rows: list[dict[str, object]],
    *,
    build_policy: Optional[BuildPolicy] = None,
    columns: Optional[EmbedColumnConfig] = None,
):
    resolved_columns = columns or EmbedColumnConfig()
    source_profile = "custom-birth-year-profile"
    return build_clinical_tables(
        rows,
        columns=resolved_columns,
        build_policy=build_policy,
        source_scope="patient-attribute-tests",
        source_profile=source_profile,
        profile_contract=contract_for_columns(
            INTERNAL_V2_CONTRACT,
            source_profile,
            resolved_columns,
            additional_bound_fields=("birth_year",),
        ),
    )


def test_patient_attribute_contracts_validate_identity_value_and_json() -> None:
    item = observation(
        1980,
        date(2020, 1, 2),
        0,
        attribute=PatientAttributeName.BIRTH_YEAR,
    )
    patient = Patient("P-1", attribute_observations=[item])

    assert patient.attribute_observations == [item]
    assert item.identity == ("P-1", PatientAttributeName.BIRTH_YEAR, source(0))
    assert item.to_dict()["context_date"] == "2020-01-02"
    json.dumps(item.to_dict())

    with pytest.raises(TypeError, match="integral"):
        observation(
            True,
            date(2020, 1, 2),
            1,
            attribute=PatientAttributeName.BIRTH_YEAR,
        )
    with pytest.raises(TypeError, match="context_date"):
        observation("F", datetime(2020, 1, 2), 1)
    with pytest.raises(ValueError, match="must match Patient"):
        patient.add_attribute_observation(
            observation("F", date(2020, 1, 2), 2, patient_id="P-2")
        )


def test_builder_distinguishes_absent_and_null_and_uses_alias_config() -> None:
    columns = EmbedColumnConfig(sex="source_sex", birth_year="source_birth_year")
    tables = build_clinical_tables(
        [
            clinical_row(),
            clinical_row(
                source_sex=" ",
                source_birth_year=None,
                studydate_anon="20200102",
            ),
        ],
        columns=columns,
        source_scope="patient-attribute-tests",
        source_profile="custom-patient-profile",
        profile_contract=contract_for_columns(
            INTERNAL_V2_CONTRACT,
            "custom-patient-profile",
            columns,
            additional_bound_fields=("birth_year",),
        ),
    )

    observations = tables.patient_attribute_observations
    assert [item.attribute for item in observations] == [
        PatientAttributeName.SEX,
        PatientAttributeName.BIRTH_YEAR,
    ]
    assert [item.value for item in observations] == [None, None]
    assert [item.context_date for item in observations] == [
        date(2020, 1, 2),
        date(2020, 1, 2),
    ]
    assert [item.source.row_ordinal for item in observations] == [1, 1]
    patient = tables.patients[0]
    assert patient.attribute_observations[0] is observations[0]
    assert patient.attribute_observations[1] is observations[1]
    assert not hasattr(patient, "sex")
    assert not hasattr(patient, "birth_year")


def test_internal_v2_omits_birth_year_but_retains_raw_values() -> None:
    tables = build_clinical_tables(
        [
            clinical_row(sex="F", birth_year=1980, studydate_anon="2020-01-01"),
            clinical_row(
                acc_anon="ACC-2",
                sex="X",
                birth_year=1981,
                studydate_anon="2021-01-01",
            ),
        ],
        source_scope="patient-attribute-tests",
    )

    values = [
        (item.attribute, item.value)
        for item in tables.patient_attribute_observations
    ]
    assert values == [
        (PatientAttributeName.SEX, "F"),
        (PatientAttributeName.SEX, "X"),
    ]
    ordinals = [
        item.source.row_ordinal
        for item in tables.patient_attribute_observations
    ]
    assert ordinals == [
        0,
        1,
    ]
    assert tables.source_occurrences[0].raw_values["birth_year"] == 1980
    assert tables.source_occurrences[1].raw_values["birth_year"] == 1981


@pytest.mark.parametrize("source_value", [1980, 1980.0, "1980"])
def test_builder_normalizes_exact_birth_year_representations(
    source_value: object,
) -> None:
    tables = build_custom_birth_year_tables(
        [clinical_row(birth_year=source_value)]
    )

    assert len(tables.patient_attribute_observations) == 1
    assert tables.patient_attribute_observations[0].value == 1980
    assert type(tables.patient_attribute_observations[0].value) is int


@pytest.mark.parametrize(
    "source_value",
    [1980.5, float("nan"), float("inf"), True, "not-a-year"],
)
def test_builder_rejects_invalid_birth_year_representations_strict(
    source_value: object,
) -> None:
    with pytest.raises(BuildPolicyError) as exc_info:
        build_custom_birth_year_tables(
            [clinical_row(birth_year=source_value)],
            build_policy=BuildPolicy.strict(),
        )

    assert exc_info.value.issue.code == "invalid_patient_attribute_value"


def test_builder_audits_and_omits_invalid_birth_year_representations() -> None:
    invalid_values = (1980.5, float("nan"), float("inf"), True, "not-a-year")
    tables = build_custom_birth_year_tables(
        [clinical_row(birth_year=value) for value in invalid_values],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    assert tables.patient_attribute_observations == ()
    assert [issue.code for issue in tables.build_issues] == [
        "invalid_patient_attribute_value"
    ] * len(invalid_values)
    assert all(
        occurrence.resolution_state is ResolutionState.UNRESOLVED
        for occurrence in tables.source_occurrences
    )


def test_invalid_birth_year_and_context_date_follow_build_policy_and_ledger() -> None:
    invalid_birth = clinical_row(birth_year="1980.5", studydate_anon="2020-01-01")
    with pytest.raises(BuildPolicyError) as birth_error:
        build_custom_birth_year_tables(
            [invalid_birth],
            build_policy=BuildPolicy.strict(),
        )
    assert birth_error.value.issue.code == "invalid_patient_attribute_value"

    invalid_date = clinical_row(sex="F", studydate_anon="not-a-date")
    with pytest.raises(BuildPolicyError) as date_error:
        build_clinical_tables([invalid_date], build_policy=BuildPolicy.strict())
    assert date_error.value.issue.code == "invalid_patient_attribute_context_date"

    tables = build_custom_birth_year_tables(
        [clinical_row(sex="F", birth_year="1980.5", studydate_anon="not-a-date")],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    retained = [
        (item.attribute, item.value, item.context_date)
        for item in tables.patient_attribute_observations
    ]
    assert retained == [
        (PatientAttributeName.SEX, "F", None)
    ]
    assert [issue.code for issue in tables.source_occurrences[0].issues] == [
        "invalid_patient_attribute_context_date",
        "invalid_patient_attribute_value",
    ]
    assert tables.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED


def test_selector_uses_latest_eligible_date_without_first_row_fallback() -> None:
    observations = (
        observation("F", date(2020, 1, 1), 0),
        observation("X", date(2021, 1, 1), 1),
    )

    earlier = select_patient_attribute_as_of(
        observations,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=as_of(date(2020, 6, 1)),
    )
    later = select_patient_attribute_as_of(
        observations,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=as_of(date(2022, 1, 1)),
    )
    none = select_patient_attribute_as_of(
        observations,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=as_of(date(2019, 1, 1)),
    )

    assert (earlier.selected_value, earlier.selected_context_date) == (
        "F",
        date(2020, 1, 1),
    )
    assert later.selected_value == "X"
    assert none.resolution_state is ResolutionState.UNRESOLVED
    assert none.reason == "no_eligible_observation"
    assert none.supporting_sources == ()


def test_selector_resolves_duplicate_support_and_explicit_null() -> None:
    duplicate = (
        observation("F", date(2020, 1, 1), 0),
        observation("F", date(2020, 1, 1), 1),
    )
    selected = select_patient_attribute_as_of(
        duplicate,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=as_of(date(2020, 1, 1)),
    )
    null_selected = select_patient_attribute_as_of(
        (
            observation(None, date(2020, 1, 1), 2),
            observation(None, date(2020, 1, 1), 3),
        ),
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=as_of(date(2020, 1, 1)),
    )

    assert selected.resolution_state is ResolutionState.RESOLVED
    assert selected.supporting_sources == (source(0), source(1))
    assert null_selected.resolution_state is ResolutionState.RESOLVED
    assert null_selected.selected_value is None
    assert null_selected.selected_context_date == date(2020, 1, 1)
    assert null_selected.supporting_sources == (source(2), source(3))
    json.dumps(null_selected.to_dict())


def test_selector_same_date_conflict_is_explicit_strict_or_default_audit() -> None:
    observations = (
        observation("F", date(2020, 1, 1), 0),
        observation("X", date(2020, 1, 1), 1),
    )
    policy = as_of(date(2020, 1, 1))

    with pytest.raises(BuildPolicyError) as exc_info:
        select_patient_attribute_as_of(
            observations,
            patient_id="P-1",
            attribute=PatientAttributeName.SEX,
            policy=policy,
            build_policy=BuildPolicy.strict(),
        )
    assert exc_info.value.issue.code == "conflicting_patient_attribute_as_of"

    selected = select_patient_attribute_as_of(
        observations,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=policy,
    )
    assert selected.resolution_state is ResolutionState.UNRESOLVED
    assert selected.selected_value is None
    assert selected.selected_context_date is None
    assert selected.supporting_sources == (source(0), source(1))
    assert [issue.code for issue in selected.issues] == [
        "conflicting_patient_attribute_as_of"
    ]


def test_selector_undated_reject_and_exclude_are_explicit() -> None:
    observations = (
        observation("F", None, 0),
        observation("X", date(2020, 1, 1), 1),
    )
    reject = as_of(date(2020, 1, 1), undated=UndatedObservationPolicy.REJECT)
    with pytest.raises(BuildPolicyError) as exc_info:
        select_patient_attribute_as_of(
            observations,
            patient_id="P-1",
            attribute=PatientAttributeName.SEX,
            policy=reject,
            build_policy=BuildPolicy.strict(),
        )
    assert exc_info.value.issue.code == "undated_patient_attribute_observation"

    audited = select_patient_attribute_as_of(
        observations,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=reject,
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    excluded = select_patient_attribute_as_of(
        observations,
        patient_id="P-1",
        attribute=PatientAttributeName.SEX,
        policy=as_of(date(2020, 1, 1)),
    )
    assert audited.resolution_state is ResolutionState.UNRESOLVED
    assert audited.reason == "undated_observation_rejected"
    assert audited.supporting_sources == (source(0),)
    assert excluded.resolution_state is ResolutionState.RESOLVED
    assert excluded.selected_value == "X"


def test_flat_result_serializes_observations_once_by_identity_reference() -> None:
    tables = build_clinical_tables(
        [clinical_row(sex="F", birth_year=1980, studydate_anon="2020-01-02")],
        source_scope="patient-attribute-tests",
    )

    serialized = tables.to_dict()
    patient = serialized["patients"][0]
    observations = serialized["patient_attribute_observations"]

    assert "sex" not in patient
    assert "birth_year" not in patient
    assert "attribute_observations" not in patient
    assert patient["patient_attribute_observation_references"] == [
        item.reference_dict() for item in tables.patient_attribute_observations
    ]
    assert observations == [
        item.to_dict() for item in tables.patient_attribute_observations
    ]
    assert tables.patients[0].attribute_observations[0] is (
        tables.patient_attribute_observations[0]
    )
    json.dumps(serialized)
