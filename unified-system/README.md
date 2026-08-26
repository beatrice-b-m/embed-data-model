# Unified EMBED Toolkit

This package is a small, source-aware object graph for EMBED mammography data.
Every input table is optional, pandas is supported without becoming a runtime
dependency, and later loads enrich the same canonical `DatasetGraph`.

The governing contract is the
[lightweight framework architecture review](../docs/lightweight-framework-architecture-review.md).

## Load the tables you have

`load_embed` accepts pandas DataFrames or iterables of row mappings. Patient-only
and exam-only loads are useful on their own:

```python
from embed_toolkit import load_embed

patient_report = load_embed(
    patients=patient_df,
    source_scope="curation-2026-08",
    identity_namespace="embed-release-2",
)
patient = patient_report.graph.patient("P-456")

exam_report = load_embed(
    exams=[{"acc_anon": "ACC-123", "empi_anon": "P-456"}],
    source_scope="curation-2026-08",
    identity_namespace="embed-release-2",
)
exam = exam_report.graph.exam("ACC-123")
```

Filtered DataFrame indexes remain physical source keys. Column maps are partial,
so one rename does not require a schema profile:

```python
report = load_embed(
    patients=patients.loc[selected_ids],
    exams=exams.query("exam_year >= 2024"),
    images=images.loc[image_ids],
    rois=rois.loc[roi_ids],
    columns={"patients": {"patient_id": "research_id"}},
    source_scope="analysis-cohort-7",
    identity_namespace="embed-release-2",
)

for patient in report.graph.patients:
    for exam in patient.exams:
        for image in exam.images:
            print(patient.patient_id, exam.accession_number, image.image_id)
```

Other optional inputs are `findings`, `hormone_history`, `procedure_history`,
`procedures`, `pathology`, and the wide `magview` convenience table.

The common wide MagView plus image-metadata path is equally direct:

```python
report = load_embed(
    magview=magview_df.loc[selected_findings],
    images=image_metadata_df.loc[selected_images],
    source_scope="analysis-cohort-7",
    identity_namespace="embed-release-2",
)

for issue in report.issues:
    print(issue.code, issue.source)
```

## Enrich one graph incrementally

Loads can arrive in any order. Use `into=` to preserve canonical object
identity:

```python
from embed_toolkit import DatasetGraph, load_embed

graph = DatasetGraph(
    identity_namespace="embed-release-2",
    source_scope="analysis-cohort-7",
)
load_embed(images=image_df, into=graph)
load_embed(exams=exam_df, into=graph)
load_embed(patients=patient_df, into=graph)

print(graph.unresolved_references)
```

Audit mode is the default: it commits independently safe contributions and
reports rejected ones. `mode="strict"` rolls back the entire invocation when an
error issue occurs. `report.issues` covers only that call; `graph.issues` is the
deduplicated cumulative view.

```python
report = load_embed(exams=exam_df, into=graph, mode="audit")
for issue in report.issues:
    print(issue.severity.value, issue.code, issue.source)
```

Raw rows are not retained by default. `retain_raw=True` keeps a frozen copy as
internal contribution metadata for audit/debugging and increases memory use;
it does not make caller-owned DataFrames recoverable from a `SourceRef`.

## Construct image-local geometry manually

Plain geometry does not require source or audit objects:

```python
from embed_toolkit import Box, RegionOfInterest

roi = RegionOfInterest(
    Box(y_min=20, x_min=40, y_stop=80, x_stop=120),
    image_id="IMG-9",
    roi_key="manual-1",
    annotation_source="radiologist-review",
)
```

## Add a project-specific loader

`DatasetGraph.transaction()` is the supported extension seam. A downstream
loader constructs `SourceRef` values and calls the bounded upsert vocabulary;
there is no registry or plugin framework to edit:

```python
from embed_toolkit import DatasetGraph, SourceRef


def load_registry_patients(rows, *, into: DatasetGraph) -> DatasetGraph:
    with into.transaction(mode="strict") as transaction:
        for ordinal, row in enumerate(rows):
            source = SourceRef("registry-2026", "patients", ordinal)
            transaction.upsert_patient(row["research_id"], source)
    return into
```

Specialist history, procedure, pathology, interpretation, and link records are
available from focused `embed_toolkit.clinical` submodules. `LoadError` and
other construction internals live in their focused modules rather than the
package-root convenience facade.

## Repo-only patch extraction recipe

Patch extraction is intentionally not installed with the framework. The
self-contained recipe under `examples/patch_extraction` consumes public image
and ROI domain types and owns its configuration, results, warnings, and
serialization locally.

## Development

From this directory:

```bash
uv run pytest
uv run ruff check src/embed_toolkit tests examples
```
