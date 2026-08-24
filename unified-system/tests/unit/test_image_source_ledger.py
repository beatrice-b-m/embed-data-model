from __future__ import annotations

import json
from dataclasses import replace

import pytest

from embed_toolkit.adapters.embed import build_image_tables
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.provenance import ResolutionState, SourceScopeKind
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.landmarks import ImageLandmark, LandmarkType
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiSourceProvenance,
)


def row(image_id: object = "IMG-1", **values: object) -> dict[str, object]:
    return {
        "image_id": image_id,
        "acc_anon": "ACC-1",
        "empi_anon": "P-1",
        "ImageLateralityFinal": "L",
        "ViewPosition": "CC",
        "FinalImageType": "2D",
        **values,
    }


def test_image_builder_scope_validation_and_ephemeral_default() -> None:
    with pytest.raises(ValueError, match="must be supplied explicitly"):
        build_image_tables([], source_scope_kind=SourceScopeKind.DATASET)

    tables = build_image_tables([row()])
    locator = tables.source_occurrences[0].locator
    assert locator.scope.startswith("in-memory:")
    assert locator.scope_kind is SourceScopeKind.MATERIALIZATION
    assert locator.source_profile == "internal-v1c"
    assert locator.source_table == "image_metadata"

    scoped = build_image_tables(
        [row()],
        source_scope="image-release-1",
        source_scope_kind=SourceScopeKind.DATASET,
        source_profile="custom-profile",
        source_table="custom-images",
    )
    scoped_locator = scoped.source_occurrences[0].locator
    assert scoped_locator.scope == "image-release-1"
    assert scoped_locator.scope_kind is SourceScopeKind.DATASET
    assert scoped_locator.source_profile == "custom-profile"
    assert scoped_locator.source_table == "custom-images"


def test_ledger_retains_all_ordinals_and_equal_duplicate_sources() -> None:
    repeated = row()
    tables = build_image_tables(
        [repeated, repeated],
        source_scope="image-materialization",
    )

    assert len(tables.images) == 1
    assert [item.locator.row_ordinal for item in tables.source_occurrences] == [
        0,
        1,
    ]
    assert [item.resolution_state for item in tables.source_occurrences] == [
        ResolutionState.RESOLVED,
        ResolutionState.RESOLVED,
    ]
    assert tables.images[0].sources == [
        item.locator for item in tables.source_occurrences
    ]
    assert tables.images[0].canonical_source is tables.images[0].sources[0]


def test_missing_image_identity_follows_strict_and_audit_policy() -> None:
    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables([row(None)])
    assert exc_info.value.issue.code == "missing_image_identity"

    tables = build_image_tables(
        [row(" ")],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="image-materialization",
    )
    assert tables.images == ()
    assert tables.rois == ()
    assert tables.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED
    assert [issue.code for issue in tables.build_issues] == [
        "missing_image_identity"
    ]


@pytest.mark.parametrize(
    ("values", "attribute"),
    [
        ({"Rows": 0}, "height"),
        ({"Rows": True}, "height"),
        ({"Rows": float("inf")}, "height"),
        ({"Columns": "not-an-integer"}, "width"),
        (
            {"FinalImageType": "DBT", "NumberOfFrames": 1.5},
            "frame_count",
        ),
        ({"PatientOrientation": "['P']"}, "patient_orientation"),
    ],
)
def test_invalid_metadata_follows_strict_and_audit_policy(
    values: dict[str, object],
    attribute: str,
) -> None:
    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables([row(**values)])
    assert exc_info.value.issue.code == "invalid_image_attribute"
    assert exc_info.value.issue.context["attribute"] == attribute

    tables = build_image_tables(
        [row(**values)],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="image-materialization",
    )
    assert tables.images == ()
    assert tables.rois == ()
    assert tables.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED
    assert tables.source_occurrences[0].issues == tables.build_issues


def test_duplicate_unknowns_are_filled_without_overwriting_known_values() -> None:
    tables = build_image_tables(
        [
            row(
                acc_anon=None,
                empi_anon=None,
                ImageLateralityFinal="unknown",
                ViewPosition="unknown",
                FinalImageType="unknown",
            ),
            row(
                acc_anon="ACC-2",
                empi_anon="P-2",
                ImageLateralityFinal="R",
                ViewPosition="MLO",
                FinalImageType="DBT",
                Rows=100,
                Columns=80,
                NumberOfFrames=20,
                PatientOrientation="['P', 'L']",
            ),
            row(
                acc_anon=None,
                empi_anon=None,
                ImageLateralityFinal="unknown",
                ViewPosition="unknown",
                FinalImageType="unknown",
            ),
        ],
        source_scope="image-materialization",
    )

    image = tables.images[0]
    assert image.accession_number == "ACC-2"
    assert image.patient_id == "P-2"
    assert image.laterality is Laterality.RIGHT
    assert image.view_position is ViewPosition.MLO
    assert image.modality is ImageModality.DBT
    assert image.image_shape == (100, 80)
    assert image.frame_count == 20
    assert image.patient_orientation is not None
    assert len(image.sources) == 3
    for attribute in (
        "accession_number",
        "patient_id",
        "laterality",
        "view_position",
        "modality",
        "height",
        "width",
        "frame_count",
        "patient_orientation",
    ):
        assert image.source_for(attribute) is tables.source_occurrences[1].locator
    assert tables.build_issues == ()


def test_image_attribute_sources_survive_copy_and_require_ledger_membership() -> None:
    tables = build_image_tables([row()], source_scope="image-materialization")
    image = tables.images[0]
    copied = replace(image)

    assert copied.attribute_sources == image.attribute_sources
    assert copied.attribute_sources is not image.attribute_sources
    assert copied.source_for("patient_id") is image.source_for("patient_id")

    outside = build_image_tables(
        [row("IMG-2")], source_scope="other-materialization"
    ).images[0].canonical_source
    with pytest.raises(ValueError, match="must occur in sources"):
        MammogramImage(
            image_id="invalid-sources",
            laterality=Laterality.LEFT,
            view_position=ViewPosition.CC,
            sources=[image.canonical_source],
            attribute_sources={"patient_id": outside},
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            {"acc_anon": "ACC-1", "empi_anon": None},
            {"acc_anon": "ACC-2", "empi_anon": "P-2"},
        ),
        (
            {"acc_anon": "ACC-1", "empi_anon": "P-1"},
            {"acc_anon": "ACC-2", "empi_anon": "P-2"},
        ),
    ],
)
def test_strict_duplicate_conflict_is_atomic(
    monkeypatch: pytest.MonkeyPatch,
    first: dict[str, object],
    second: dict[str, object],
) -> None:
    constructed: list[MammogramImage] = []
    original = MammogramImage.__post_init__

    def capture(image: MammogramImage) -> None:
        original(image)
        constructed.append(image)

    monkeypatch.setattr(MammogramImage, "__post_init__", capture)
    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables(
            [row(**first), row(**second)],
            source_scope="image-materialization",
        )

    assert exc_info.value.issue.code == "conflicting_image_attribute"
    assert exc_info.value.issue.context["attribute"] == "accession_number"
    retained = constructed[0]
    assert retained.accession_number == "ACC-1"
    assert retained.patient_id == first["empi_anon"]
    assert len(retained.sources) == 1


def test_audit_conflicts_apply_safe_fill_and_omit_conflict_row_rois() -> None:
    tables = build_image_tables(
        [
            row(acc_anon="ACC-1", empi_anon="P-1", Columns=None),
            row(
                acc_anon="ACC-2",
                empi_anon="P-2",
                Columns=100,
                ROI_coords=[1, 2, 3, 4],
            ),
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="image-materialization",
    )

    image = tables.images[0]
    assert image.accession_number == "ACC-1"
    assert image.patient_id == "P-1"
    assert image.width == 100
    assert len(image.sources) == 2
    assert tables.rois == ()
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "accession_number",
        "patient_id",
    ]
    assert tables.source_occurrences[1].resolution_state is ResolutionState.UNRESOLVED
    assert tables.source_occurrences[1].issues == tables.build_issues
    assert tables.build_issues[0].context["retained_sources"] == [
        tables.source_occurrences[0].locator.to_dict()
    ]


def test_modality_conflict_cannot_fill_dbt_frame_count_into_ffdm_image() -> None:
    rows = [
        row(FinalImageType="2D", Columns=None),
        row(FinalImageType="DBT", NumberOfFrames=20, Columns=100),
    ]

    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables(rows, source_scope="image-materialization")
    assert exc_info.value.issue.code == "conflicting_image_attribute"
    assert exc_info.value.issue.context["attribute"] == "modality"

    tables = build_image_tables(
        rows,
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="image-materialization",
    )
    image = tables.images[0]
    assert image.modality is ImageModality.FFDM
    assert image.frame_count is None
    assert image.width == 100
    assert len(image.sources) == 2
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "modality"
    ]
    assert tables.source_occurrences[1].resolution_state is ResolutionState.UNRESOLVED


def test_equal_duplicate_roi_locator_deduplicates_and_retains_row_evidence() -> None:
    repeated = row(ROI_coords=[1, 2, 3, 4])
    tables = build_image_tables(
        [repeated, repeated],
        source_scope="image-materialization",
    )

    assert len(tables.images) == 1
    assert len(tables.images[0].sources) == 2
    assert len(tables.rois) == 1
    assert tables.rois[0].sources == tuple(tables.images[0].sources)


def test_flat_serialization_retains_raw_row_once_and_uses_source_references() -> None:
    raw = row(
        raw_only_marker="IMAGE-RAW-UNIQUE-MARKER",
        ROI_coords=[1, 2, 3, 4],
    )
    tables = build_image_tables(
        [raw],
        source_scope="image-materialization",
    )

    serialized = tables.to_dict()
    encoded = json.dumps(serialized)
    assert encoded.count("IMAGE-RAW-UNIQUE-MARKER") == 1
    assert serialized["source_occurrences"][0]["raw_values"] == raw
    assert serialized["images"][0]["sources"] == [
        tables.source_occurrences[0].locator.to_dict()
    ]
    assert serialized["images"][0]["attribute_sources"]["patient_id"] == (
        tables.source_occurrences[0].locator.to_dict()
    )
    assert "raw_values" not in serialized["images"][0]
    assert serialized["rois"][0]["image_id"] == "IMG-1"
    assert serialized["rois"][0]["source_references"] == [
        tables.source_occurrences[0].locator.to_dict()
    ]


def test_image_tables_enforce_roi_containment_and_canonical_locator_scope() -> None:
    tables = build_image_tables(
        [row(ROI_coords=[1, 2, 3, 4])],
        source_scope="image-materialization",
    )
    roi = tables.rois[0]

    with pytest.raises(ValueError, match="resolve to a table image"):
        replace(tables, rois=(replace(roi, image_id="missing-image"),))

    combined = build_image_tables(
        [
            row(ROI_coords=[1, 2, 3, 4]),
            row("IMG-2", ROI_coords=[1, 2, 3, 4]),
        ],
        source_scope="image-materialization",
    )
    first, other = combined.rois
    mismatched_scope = replace(
        first,
        locator=other.locator,
        sources=other.sources,
    )
    with pytest.raises(ValueError, match="canonical_source"):
        replace(combined, rois=(mismatched_scope,))


def test_image_tables_reject_roi_modality_and_frame_bound_mismatches() -> None:
    ffdm = build_image_tables(
        [row(ROI_coords=[1, 2, 3, 4])],
        source_scope="image-materialization",
    )
    ffdm_roi = ffdm.rois[0]
    dbt_provenance = RoiSourceProvenance(
        modality=ImageModality.DBT,
        source_count=ffdm_roi.source_provenance.source_count,
        depth_frame_provenance=RoiDepthFrameProvenance.UNAVAILABLE_DBT,
    )
    with pytest.raises(ValueError, match="modality"):
        replace(ffdm, rois=(replace(ffdm_roi, source_provenance=dbt_provenance),))

    dbt = build_image_tables(
        [
            row(
                FinalImageType="DBT",
                NumberOfFrames=5,
                ROI_coords=[1, 2, 3, 4],
                ROI_frames=[2],
            )
        ],
        source_scope="dbt-materialization",
    )
    dbt_roi = dbt.rois[0]
    out_of_range = replace(dbt_roi.source_provenance, frame_indices=(5,))
    with pytest.raises(ValueError, match="frame_count"):
        replace(dbt, rois=(replace(dbt_roi, source_provenance=out_of_range),))


def test_image_source_contract_is_required_unique_and_copy_preserved() -> None:
    tables = build_image_tables([row()], source_scope="image-materialization")
    image = tables.images[0]
    copied = image.with_landmark(
        ImageLandmark(1, 2, LandmarkType.NIPPLE)
    )

    assert copied.sources == image.sources
    assert copied.sources is not image.sources
    assert copied.canonical_source == image.canonical_source
    with pytest.raises(TypeError):
        MammogramImage(  # type: ignore[call-arg]
            "missing",
            Laterality.LEFT,
            ViewPosition.CC,
        )
    with pytest.raises(ValueError, match="at least one"):
        MammogramImage("empty", Laterality.LEFT, ViewPosition.CC, [])
    with pytest.raises(ValueError, match="unique"):
        MammogramImage(
            "duplicate",
            Laterality.LEFT,
            ViewPosition.CC,
            [image.canonical_source, image.canonical_source],
        )
    with pytest.raises(ValueError, match="only valid for DBT"):
        MammogramImage(
            "ffdm-with-frames",
            Laterality.LEFT,
            ViewPosition.CC,
            [image.canonical_source],
            modality=ImageModality.FFDM,
            frame_count=20,
        )
