# Unified EMBED Toolkit

This directory contains the repository's only retained runtime implementation.
The governing implementation contract is the
[clinical object model resolution plan](../docs/clinical-object-model-resolution-plan.md),
with current verification and resolution evidence in the addendum at the top
of the [clinical object model evaluation](../docs/clinical-object-model-evaluation.md).

The [unified-system plan](../docs/unified-system-plan.md) is a historical
architecture plan. It explains the system's origin but does not supersede the
completed resolution contract. The retired repository-level legacy trees have
been removed.

## Development

Install or run tools from this directory so imports resolve to
`unified-system/src/embed_toolkit`.

```bash
python -m pytest
```

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
