from __future__ import annotations

import json
import math

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import INTERNAL_V2_CONTRACT
from embed_toolkit.clinical.exams import Exam
from embed_toolkit.core.anatomy import (
    AnatomicalLocationCategory,
    DepthThird,
    MedialLateralAxis,
    SuperiorInferiorAxis,
)
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.workflows.finding_localization import FindingLocalizer
from profile_contract_support import contract_for_columns


def row(**values: object) -> dict[str, object]:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": "1",
        "side": "L",
        **values,
    }


def test_location_clock_category_and_explicit_depth_are_normalized() -> None:
    tables = build_clinical_tables(
        [row(location="10;S", depth="P")],
        source_scope="clinical-materialization",
    )

    finding = tables.findings[0]
    position = finding.anatomical_position
    assert position is not None
    assert position.clock_position.hour == 10
    assert position.location_category is AnatomicalLocationCategory.SUBAREOLAR
    assert position.quadrant.ml is MedialLateralAxis.MEDIAL
    assert position.quadrant.si is SuperiorInferiorAxis.SUPERIOR
    assert position.quadrant.depth is DepthThird.POSTERIOR
    assert finding.source_location_codes == {"location": "10;S"}
    assert finding.source_depth_codes == {"depth": "P"}
    assert {item.source_field for item in finding.normalization_evidence} == {
        "location",
        "depth",
    }


def test_distance_only_creates_unknown_unilateral_position() -> None:
    finding = build_clinical_tables(
        [row(distance="4.5")],
        source_scope="clinical-materialization",
    ).findings[0]

    position = finding.anatomical_position
    assert position is not None
    assert position.laterality is Laterality.LEFT
    assert position.quadrant.ml is MedialLateralAxis.UNKNOWN
    assert position.quadrant.si is SuperiorInferiorAxis.UNKNOWN
    assert position.quadrant.depth is DepthThird.UNKNOWN
    assert position.distance_from_nipple_cm == 4.5
    assert finding.source_distance_codes == {"distance": "4.5"}
    assert finding.normalization_evidence[0].normalized_value == 4.5


def test_null_and_blank_anatomy_fields_preserve_codes_without_position() -> None:
    finding = build_clinical_tables(
        [row(location=None, depth="", distance=None)],
        source_scope="clinical-materialization",
    ).findings[0]

    assert finding.anatomical_position is None
    assert finding.source_location_codes == {"location": None}
    assert finding.source_depth_codes == {"depth": ""}
    assert finding.source_distance_codes == {"distance": None}
    assert finding.normalization_evidence == []
    assert finding.normalization_warnings == []


def test_aliases_and_custom_columns_preserve_actual_matched_names() -> None:
    aliased = build_clinical_tables(
        [row(loc="W", finding_depth="M", finding_distance="2")],
        source_scope="clinical-materialization",
    ).findings[0]
    custom_columns = EmbedColumnConfig(
        finding_location="custom_loc",
        finding_depth="custom_depth",
        finding_distance="custom_distance",
    )
    custom = build_clinical_tables(
        [row(custom_loc="Z", custom_depth="P", custom_distance="3")],
        columns=custom_columns,
        source_scope="clinical-materialization",
        source_profile="custom-finding-profile",
        profile_contract=contract_for_columns(
            INTERNAL_V2_CONTRACT,
            "custom-finding-profile",
            custom_columns,
        ),
    ).findings[0]

    assert aliased.source_location_codes == {"loc": "W"}
    assert aliased.source_depth_codes == {"finding_depth": "M"}
    assert aliased.source_distance_codes == {"finding_distance": "2"}
    assert custom.source_location_codes == {"custom_loc": "Z"}
    assert custom.source_depth_codes == {"custom_depth": "P"}
    assert custom.source_distance_codes == {"custom_distance": "3"}
    assert {item.source_field for item in custom.normalization_evidence} == {
        "custom_loc",
        "custom_depth",
        "custom_distance",
    }


def test_unknown_codes_emit_source_scoped_structured_warnings() -> None:
    finding = build_clinical_tables(
        [row(loc="??", finding_depth="deep")],
        source_scope="clinical-materialization",
    ).findings[0]

    assert {warning.code for warning in finding.normalization_warnings} == {
        "unknown_location_code",
        "unknown_depth_code",
    }
    assert {warning.source_field for warning in finding.normalization_warnings} == {
        "loc",
        "finding_depth",
    }
    assert all(
        warning.source.scope == "clinical-materialization"
        for warning in finding.normalization_warnings
    )


@pytest.mark.parametrize("side", ["B", "unknown-code"])
def test_non_unilateral_finding_preserves_evidence_without_anatomical_meaning(
    side: str,
) -> None:
    finding = build_clinical_tables(
        [row(side=side, location="10;S", depth="P")],
        source_scope="clinical-materialization",
    ).findings[0]

    position = finding.anatomical_position
    assert position is not None
    assert position.clock_position is None
    assert position.location_category is None
    assert position.quadrant.ml is MedialLateralAxis.UNKNOWN
    assert position.quadrant.si is SuperiorInferiorAxis.UNKNOWN
    assert position.quadrant.depth is DepthThird.UNKNOWN
    assert any(
        warning.code == "unsupported_laterality"
        and warning.source_field == "side"
        for warning in finding.normalization_warnings
    )
    assert all(
        item.normalized_value is None for item in finding.normalization_evidence
    )


def test_bilateral_distance_only_preserves_raw_evidence_and_warns() -> None:
    finding = build_clinical_tables(
        [row(side="B", distance="2")],
        source_scope="clinical-materialization",
    ).findings[0]

    assert finding.anatomical_position is None
    assert finding.source_distance_codes == {"distance": "2"}
    assert finding.normalization_evidence[0].normalized_value == 2.0
    assert [warning.code for warning in finding.normalization_warnings] == [
        "unsupported_laterality"
    ]


@pytest.mark.parametrize("distance", [-1, math.nan, math.inf, -math.inf, "bad"])
def test_invalid_distance_strict_raises(distance: object) -> None:
    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(
            [row(distance=distance)],
            source_scope="clinical-materialization",
            build_policy=BuildPolicy.strict(),
        )

    assert exc_info.value.issue.code == "invalid_finding_distance"
    assert exc_info.value.issue.context["source_field"] == "distance"


@pytest.mark.parametrize("distance", [-1, math.nan, math.inf])
def test_invalid_distance_audit_retains_raw_without_normalized_distance(
    distance: object,
) -> None:
    tables = build_clinical_tables(
        [row(distance=distance)],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )

    finding = tables.findings[0]
    assert finding.anatomical_position is None
    assert finding.source_distance_codes["distance"] is distance
    assert finding.normalization_evidence[0].normalized_value is None
    assert [issue.code for issue in tables.build_issues] == [
        "invalid_finding_distance"
    ]


def test_repeated_rows_fill_missing_anatomy_and_accumulate_evidence() -> None:
    tables = build_clinical_tables(
        [row(location="OU"), row(depth="P"), row(distance="2.5")],
        source_scope="clinical-materialization",
    )

    finding = tables.findings[0]
    position = finding.anatomical_position
    assert position is not None
    assert position.quadrant.ml is MedialLateralAxis.LATERAL
    assert position.quadrant.depth is DepthThird.POSTERIOR
    assert position.distance_from_nipple_cm == 2.5
    assert len(finding.normalization_evidence) == 3
    assert [item.source.row_ordinal for item in finding.normalization_evidence] == [
        0,
        1,
        2,
    ]


def test_repeated_anatomy_conflicts_are_governed_and_retain_first_in_audit() -> None:
    rows = [row(depth="A", distance="1"), row(depth="P", distance="2")]
    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(
            rows,
            source_scope="clinical-materialization",
            build_policy=BuildPolicy.strict(),
        )
    assert exc_info.value.issue.code == "conflicting_finding_anatomical_value"
    assert exc_info.value.issue.context["attribute"] == "quadrant.depth"

    tables = build_clinical_tables(
        rows,
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )
    position = tables.findings[0].anatomical_position
    assert position is not None
    assert position.quadrant.depth is DepthThird.ANTERIOR
    assert position.distance_from_nipple_cm == 1.0
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "quadrant.depth",
        "distance_from_nipple_cm",
    ]
    assert len(tables.findings[0].normalization_evidence) == 4


def test_strict_anatomy_conflict_does_not_mutate_retained_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retained_findings = []
    original_add = Exam.add_finding

    def capture_add(exam: Exam, finding: object):
        retained = original_add(exam, finding)  # type: ignore[arg-type]
        if not retained_findings:
            retained_findings.append(retained)
        return retained

    monkeypatch.setattr(Exam, "add_finding", capture_add)

    with pytest.raises(BuildPolicyError):
        build_clinical_tables(
            [row(depth="A", distance="1"), row(depth="P", distance="2")],
            source_scope="clinical-materialization",
            build_policy=BuildPolicy.strict(),
        )

    retained = retained_findings[0]
    assert retained.anatomical_position.quadrant.depth is DepthThird.ANTERIOR
    assert retained.anatomical_position.distance_from_nipple_cm == 1.0
    assert len(retained.normalization_evidence) == 2


def test_finding_anatomy_serialization_is_json_ready() -> None:
    finding = build_clinical_tables(
        [row(location="RA", depth="P", distance="1.25")],
        source_scope="clinical-materialization",
    ).findings[0]

    serialized = finding.to_dict()

    assert serialized["source_distance_codes"] == {"distance": "1.25"}
    assert serialized["normalization_evidence"][0]["source_field"] == "depth"
    assert serialized["anatomical_position"]["distance_from_nipple_cm"] == 1.25
    json.dumps(serialized)


def test_localizer_propagates_structured_evidence_and_warning_codes() -> None:
    finding = build_clinical_tables(
        [row(location="10;OU")],
        source_scope="clinical-materialization",
    ).findings[0]

    result = FindingLocalizer().localize(finding)

    assert result.metadata["preferred_source"] == "finding.anatomical_position"
    assert "conflicting_clock_quadrant" in {
        warning.code for warning in result.warnings
    }
    warning = next(
        warning
        for warning in result.warnings
        if warning.code == "conflicting_clock_quadrant"
    )
    assert warning.payload["field"] == "location"
    assert warning.payload["source"]["row_ordinal"] == 0
    normalized = next(item for item in result.evidence if item.kind == "clock")
    assert normalized.payload["field"] == "location"
    assert normalized.payload["source"]["scope"] == "clinical-materialization"
