from __future__ import annotations

import json
from typing import Optional

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.clinical.attributes import (
    ExamAttributeName,
    ExamAttributeObservation,
)
from embed_toolkit.clinical.exams import Exam
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
        scope="exam-attribute-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="clinical",
        row_ordinal=row_ordinal,
    )


def observation(
    attribute: ExamAttributeName,
    value: Optional[str],
    row_ordinal: int,
    *,
    accession_number: str = "ACC-1",
) -> ExamAttributeObservation:
    return ExamAttributeObservation(
        accession_number=accession_number,
        attribute=attribute,
        value=value,
        source=source(row_ordinal),
    )


def row(finding_number: str, **values: object) -> dict[str, object]:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": finding_number,
        "side": "L",
        **values,
    }


def test_exam_owns_validated_source_attributed_observations() -> None:
    item = observation(ExamAttributeName.EXAM_DATE, " 2020-01-02 ", 0)
    exam = Exam("ACC-1", attribute_observations=[item])

    assert item.value == "2020-01-02"
    assert item.identity == ("ACC-1", ExamAttributeName.EXAM_DATE, source(0))
    assert exam.attribute_observations == [item]
    assert exam.add_attribute_observation(item) is item
    with pytest.raises(ValueError, match="cannot represent different values"):
        exam.add_attribute_observation(
            observation(ExamAttributeName.EXAM_DATE, "2021-01-02", 0)
        )
    with pytest.raises(ValueError, match="must match Exam"):
        exam.add_attribute_observation(
            observation(
                ExamAttributeName.DESCRIPTION,
                "screening",
                1,
                accession_number="ACC-2",
            )
        )
    with pytest.raises(TypeError, match="string or None"):
        ExamAttributeObservation(
            accession_number="ACC-1",
            attribute=ExamAttributeName.DESCRIPTION,
            value=1,
            source=source(1),
        )


def test_first_null_then_populated_fills_both_invariants() -> None:
    tables = build_clinical_tables(
        [
            row("1", studydate_anon=None, exam_description=" "),
            row(
                "2",
                studydate_anon=" 2020-01-02 ",
                exam_description=" screening ",
            ),
        ],
        source_scope="exam-attribute-tests",
    )

    exam = tables.exams[0]
    assert exam.exam_date == "2020-01-02"
    assert exam.description == "screening"
    assert [item.value for item in tables.exam_attribute_observations] == [
        None,
        None,
        "2020-01-02",
        "screening",
    ]
    assert tables.build_issues == ()
    assert all(
        item.resolution_state is ResolutionState.RESOLVED
        for item in tables.source_occurrences
    )


def test_absent_attribute_creates_no_observation_but_explicit_null_does() -> None:
    columns = EmbedColumnConfig(exam_description="source_description")
    tables = build_clinical_tables(
        [row("1"), row("2", source_description=None)],
        columns=columns,
        source_scope="exam-attribute-tests",
        source_profile="custom-exam-profile",
        profile_contract=contract_for_columns(
            INTERNAL_V2_CONTRACT,
            "custom-exam-profile",
            columns,
        ),
    )

    assert len(tables.exam_attribute_observations) == 1
    assert tables.exam_attribute_observations[0].attribute is (
        ExamAttributeName.DESCRIPTION
    )
    assert tables.exam_attribute_observations[0].value is None
    assert tables.exam_attribute_observations[0].source.row_ordinal == 1
    assert tables.exams[0].description is None
    assert tables.build_issues == ()


def test_equal_repeats_retain_all_supporting_observations() -> None:
    tables = build_clinical_tables(
        [
            row("1", studydate_anon="2020-01-02"),
            row("2", studydate_anon="2020-01-02"),
        ],
        source_scope="exam-attribute-tests",
    )

    assert tables.exams[0].exam_date == "2020-01-02"
    assert len(tables.exam_attribute_observations) == 2
    assert [item.source.row_ordinal for item in tables.exam_attribute_observations] == [
        0,
        1,
    ]
    assert tables.build_issues == ()


def test_explicit_null_does_not_clear_a_populated_invariant() -> None:
    tables = build_clinical_tables(
        [
            row("1", exam_description="screening"),
            row("2", exam_description=None),
        ],
        source_scope="exam-attribute-tests",
    )

    assert tables.exams[0].description == "screening"
    assert [item.value for item in tables.exam_attribute_observations] == [
        "screening",
        None,
    ]
    assert tables.build_issues == ()


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            {"studydate_anon": "2020-01-02", "exam_description": None},
            {"studydate_anon": "2021-01-02", "exam_description": "filled"},
        ),
        (
            {"studydate_anon": "2020-01-02", "exam_description": "first"},
            {"studydate_anon": "2021-01-02", "exam_description": "second"},
        ),
    ],
)
def test_strict_conflict_preflight_is_atomic(
    monkeypatch: pytest.MonkeyPatch,
    first: dict[str, object],
    second: dict[str, object],
) -> None:
    captured: list[Exam] = []
    original = Exam.add_attribute_observation

    def capture(
        exam: Exam,
        item: ExamAttributeObservation,
    ) -> ExamAttributeObservation:
        if exam not in captured:
            captured.append(exam)
        return original(exam, item)

    monkeypatch.setattr(Exam, "add_attribute_observation", capture)
    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(
            [row("1", **first), row("2", **second)],
            source_scope="exam-attribute-tests",
            build_policy=BuildPolicy.strict(),
        )

    assert exc_info.value.issue.code == "conflicting_exam_attribute"
    assert exc_info.value.issue.context["attribute"] == "exam_date"
    exam = captured[0]
    assert exam.exam_date == "2020-01-02"
    assert exam.description == first["exam_description"]
    assert len(exam.attribute_observations) == 2
    assert all(item.source.row_ordinal == 0 for item in exam.attribute_observations)


def test_audit_conflicts_retain_values_evidence_and_safe_findings() -> None:
    tables = build_clinical_tables(
        [
            row(
                "1",
                studydate_anon="2020-01-02",
                exam_description="first",
            ),
            row(
                "2",
                studydate_anon="2021-01-02",
                exam_description="second",
            ),
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="exam-attribute-tests",
    )

    exam = tables.exams[0]
    assert exam.exam_date == "2020-01-02"
    assert exam.description == "first"
    assert len(exam.attribute_observations) == 4
    assert len(tables.findings) == 2
    assert [finding.finding_number for finding in tables.findings] == ["1", "2"]
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "exam_date",
        "description",
    ]
    assert tables.source_occurrences[1].resolution_state is ResolutionState.UNRESOLVED
    assert tables.source_occurrences[1].issues == tables.build_issues
    for issue in tables.build_issues:
        assert issue.context["accession_number"] == "ACC-1"
        assert issue.context["retained_supporting_sources"] == [
            tables.exam_attribute_observations[0].source.to_dict()
        ]


def test_audit_conflict_still_applies_independent_safe_fill() -> None:
    tables = build_clinical_tables(
        [
            row(
                "1",
                studydate_anon="2020-01-02",
                exam_description=None,
            ),
            row(
                "2",
                studydate_anon="2021-01-02",
                exam_description="filled",
            ),
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="exam-attribute-tests",
    )

    assert tables.exams[0].exam_date == "2020-01-02"
    assert tables.exams[0].description == "filled"
    assert len(tables.exam_attribute_observations) == 4
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "exam_date"
    ]
    assert len(tables.findings) == 2


def test_patient_identity_conflict_prevents_exam_attribute_mutation() -> None:
    tables = build_clinical_tables(
        [
            row("1", studydate_anon="2020-01-02"),
            {
                **row("2", studydate_anon="2021-01-02"),
                "empi_anon": "P-2",
            },
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="exam-attribute-tests",
    )

    assert tables.exams[0].exam_date == "2020-01-02"
    assert len(tables.exam_attribute_observations) == 1
    assert [issue.code for issue in tables.build_issues] == [
        "conflicting_accession_patient_identity"
    ]


def test_exam_observation_serialization_is_owned_or_flat_by_reference() -> None:
    tables = build_clinical_tables(
        [
            row(
                "1",
                studydate_anon="2020-01-02",
                exam_description="screening",
            )
        ],
        source_scope="exam-attribute-tests",
    )
    exam = tables.exams[0]

    standalone = exam.to_dict()
    flattened = tables.to_dict()
    flat_exam = flattened["exams"][0]

    assert standalone["attribute_observations"] == [
        item.to_dict() for item in exam.attribute_observations
    ]
    assert "attribute_observations" not in flat_exam
    assert flat_exam["exam_attribute_observation_references"] == [
        item.reference_dict() for item in exam.attribute_observations
    ]
    assert flattened["exam_attribute_observations"] == [
        item.to_dict() for item in tables.exam_attribute_observations
    ]
    assert exam.attribute_observations[0] is tables.exam_attribute_observations[0]
    json.dumps(standalone)
    json.dumps(flattened)
