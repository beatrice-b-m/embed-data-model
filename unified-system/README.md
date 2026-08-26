# Unified EMBED Toolkit

This directory contains the repository's only retained runtime implementation.
The governing recovery contract is the
[lightweight framework architecture review](../docs/lightweight-framework-architecture-review.md).
The canonical graph migration is being delivered as vertical slices; the
Patient/Exam and table-normalization slice described in Phase 2 is available
through the package root.

The [unified-system plan](../docs/unified-system-plan.md) is a historical
architecture plan. It explains the system's origin but does not supersede the
completed resolution contract. The retired repository-level legacy trees have
been removed.

## Development

Install or run tools from this directory so imports resolve to
`unified-system/src/embed_toolkit`.

```bash
uv run pytest
```

## Load patients and exams

`load_embed` accepts pandas DataFrames directly without making pandas a runtime
dependency. Every table is optional, filtered DataFrame indices are retained as
source keys, and per-table column overrides are partial:

```python
from embed_toolkit import load_embed

report = load_embed(
    patients=patient_df,
    exams=exam_df,
    source_scope="curation-2026-08",
    identity_namespace="embed-release-2",
    columns={"patients": {"patient_id": "custom_patient_id"}},
)

patient = report.graph.patient("P-456")
exam = report.graph.exam("ACC-123")

for issue in report.issues:
    print(issue.code, issue.source)
```

The same graph can be enriched in any order. Image-derived and other grains
will move onto this transaction surface in later vertical slices:

```python
from embed_toolkit import DatasetGraph, load_embed

graph = DatasetGraph(identity_namespace="embed-release-2")
load_embed(exams=exam_df, into=graph)
load_embed(patients=patient_df, into=graph)
```

Ordinary audit mode commits independently safe rows and reports rejected rows.
Use `mode="strict"` when any error should roll back the entire invocation.

## Construction policy

Source construction is fail-soft by default. The clinical and image builders,
clinical/image graph assembly, and patient-attribute temporal selection retain
structured issues instead of raising for ordinary source defects:

```python
from embed_toolkit.adapters.embed import build_image_tables

tables = build_image_tables(rows)
for issue in tables.build_issues:
    print(issue.code, issue.message)
```

Use strict policy explicitly for validation jobs that should stop on the first
error-severity issue:

```python
from embed_toolkit.core.build_policy import BuildPolicy

tables = build_image_tables(rows, build_policy=BuildPolicy.strict())
```

Rows without sufficient identity remain unresolved source occurrences; audit
mode does not manufacture domain objects for them.

## Internal V2 image and ROI semantics

`MammogramImage.source_modality` preserves source DICOM `Modality`,
`derived_image_type` preserves the open `FinalImageType` value, and `modality`
is the normalized `ImageModality` helper used by workflows. Values such as
`ROI_SS`, `ROI_SSC`, `other`, and future pipeline types are retained without
default filtering.

For DBT ROIs, `ROI_depth_derived` is aligned with `ROI_coords`. A true flag
produces `RoiDepthFrameProvenance.DERIVED`; false produces
`SOURCE_SUPPLIED`. Images whose acquisition kind cannot be normalized still
retain valid ROI coordinates with `UNRESOLVED_MODALITY`, while raw frame data
remains in the source occurrence rather than being interpreted.

Default ROI-transfer relatedness requires equal, populated
`coordinate_frame_id` values sourced from `acquisition_group_id`. Matching
accession, study, or series identifiers are descriptive evidence only. A
project may supply an explicit relatedness override, which is serialized as a
caller assertion or denial and is not presented as profile-backed evidence.
