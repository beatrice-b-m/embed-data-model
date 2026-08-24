from __future__ import annotations

import json

from embed_toolkit.audit.results import ResultStatus
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.core.anatomy import (
    AnatomicalLocationCategory,
    AnatomicalPosition,
    ClockFacePosition,
    DepthThird,
    MedialLateralAxis,
    Quadrant,
    SuperiorInferiorAxis,
)
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.workflows.finding_localization import FindingLocalizer


def warning_codes(result: object) -> set[str]:
    return {warning.code for warning in result.warnings}


def test_existing_finding_anatomical_position_is_preferred() -> None:
    position = AnatomicalPosition(
        laterality=Laterality.LEFT,
        quadrant=Quadrant(
            laterality=Laterality.LEFT,
            ml=MedialLateralAxis.MEDIAL,
            si=SuperiorInferiorAxis.SUPERIOR,
            depth=DepthThird.POSTERIOR,
        ),
        clock_position=ClockFacePosition(10),
    )
    finding = Finding(
        accession_number="ACC-1",
        laterality=Laterality.LEFT,
        finding_number=1,
        anatomical_position=position,
        source_location_codes={"loc": "Y"},
        source_depth_codes={"depth": "A"},
    )

    result = FindingLocalizer().localize(finding)

    assert result.status is ResultStatus.SUCCESS
    assert result.subject_id == "ACC-1:1"
    assert result.anatomical_position["clock_position"] == {"hour": 10}
    assert result.anatomical_position["quadrant"]["ml"] == "medial"
    assert result.metadata["preferred_source"] == "finding.anatomical_position"
    assert result.evidence[0].source == "finding"
    json.dumps(result.to_dict())


def test_direct_clock_code_drives_axes_and_preserves_quadrant_evidence() -> None:
    result = FindingLocalizer().localize(
        laterality="L",
        clock_code="3",
        location_code="IN",
        subject_id="finding-direct",
    )

    assert result.status is ResultStatus.PARTIAL
    assert result.anatomical_position["clock_position"] == {"hour": 3}
    assert result.anatomical_position["quadrant"]["ml"] == "lateral"
    assert result.anatomical_position["quadrant"]["si"] == "central"
    assert any(item.kind == "clock" for item in result.evidence)
    assert any(item.kind == "location" for item in result.evidence)
    assert "conflicting_clock_quadrant" in warning_codes(result)


def test_finding_source_codes_normalize_quadrant_and_depth() -> None:
    finding = Finding(
        accession_number="ACC-2",
        laterality="R",
        finding_number=7,
        source_location_codes={"loc": "W"},
        source_depth_codes={"depth": "P"},
    )

    result = FindingLocalizer().localize(finding)

    assert result.status is ResultStatus.SUCCESS
    assert result.anatomical_position["quadrant"] == {
        "laterality": "R",
        "ml": "lateral",
        "si": "superior",
        "depth": "posterior",
    }
    assert {item.kind for item in result.evidence} == {"location", "depth"}


def test_explicit_raw_localization_input_supplies_clock_location_and_depth() -> None:
    finding = Finding(
        accession_number="ACC-3",
        laterality="L",
        finding_number=4,
    )

    result = FindingLocalizer().localize(
        finding,
        raw_source_fields={
            "finding_location_code": "W",
            "finding_depth": "M",
            "clock_face": "2:00",
        },
    )

    assert result.status is ResultStatus.SUCCESS
    assert result.anatomical_position["clock_position"] == {"hour": 2}
    assert result.anatomical_position["quadrant"]["ml"] == "lateral"
    assert result.anatomical_position["quadrant"]["si"] == "superior"
    assert result.anatomical_position["quadrant"]["depth"] == "middle"


def test_retroareolar_central_and_axillary_tail_categories_are_preserved() -> None:
    localizer = FindingLocalizer()

    retro = localizer.localize(laterality="L", location_code="RA")
    central = localizer.localize(laterality="R", location_code="central")
    axillary_tail = localizer.localize(laterality="L", location_code="T")

    assert (
        retro.anatomical_position["location_category"]
        == AnatomicalLocationCategory.RETROAREOLAR.value
    )
    assert retro.anatomical_position["quadrant"]["depth"] == DepthThird.ANTERIOR.value
    assert (
        central.anatomical_position["location_category"]
        == AnatomicalLocationCategory.CENTRAL.value
    )
    assert (
        axillary_tail.anatomical_position["location_category"]
        == AnatomicalLocationCategory.AXILLARY_TAIL.value
    )
    assert axillary_tail.anatomical_position["quadrant"]["si"] == "superior"
    assert axillary_tail.anatomical_position["quadrant"]["depth"] == "posterior"


def test_unknown_or_missing_location_evidence_warns_without_crashing() -> None:
    unknown = FindingLocalizer().localize(
        laterality="L",
        location_code="??",
        depth_code="deep",
        clock_code="13",
    )
    missing = FindingLocalizer().localize(laterality="R")

    assert unknown.status is ResultStatus.FAILED
    assert {
        "unknown_location_code",
        "unknown_depth_code",
        "unknown_clock_code",
        "missing_location_evidence",
    }.issubset(warning_codes(unknown))
    assert missing.status is ResultStatus.FAILED
    assert "missing_location_evidence" in warning_codes(missing)


def test_ambiguous_depth_warning_returns_partial_localization() -> None:
    result = FindingLocalizer().localize(
        laterality="R",
        location_code="W",
        depth_code=("A", "P"),
    )

    assert result.status is ResultStatus.PARTIAL
    assert result.anatomical_position["quadrant"]["depth"] == "anterior"
    assert "conflicting_depth_code" in warning_codes(result)
