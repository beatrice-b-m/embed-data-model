# EMBED Data Model user guide

This guide describes the mutable object model and the source-table adapter.
The current Python project is at the repository root and is installed as
`embed-data-model`; import `embed_data_model`. This file remains beside the
former `unified-system/` project directory as a longer user guide. Start with
the repository [README](../README.md), then use the
[documentation index](../docs/README.md) for contracts and migration notes.

The examples below are standalone unless a block says otherwise. They use
synthetic rows and public imports, so they do not require access to private
EMBED files.

## Public surface

The root facade exports the common working types:

```python
from embed_data_model import (
    BreastSide,
    Box,
    CancerRegistryEntry,
    DatasetGraph,
    Exam,
    Finding,
    ImageModality,
    Issue,
    Laterality,
    LoadReport,
    MammogramImage,
    Pathology,
    Patient,
    Procedure,
    ProcedureIdentity,
    RegionOfInterest,
    SourceRef,
    ValidationResult,
    ViewPosition,
    load_embed,
    validate,
)
```

The source adapter's complete default table map is intentionally available in
its specialist module rather than on the root facade:

```python
from embed_data_model.sources.embed.columns import DEFAULT_COLUMNS

assert DEFAULT_COLUMNS["patients"]["patient_id"] == "empi_anon"
assert DEFAULT_COLUMNS["findings"]["finding_number"] == "numfind"
```

`DEFAULT_COLUMNS` is a read-only mapping of semantic names to physical source
columns. Pass partial overrides through `load_embed(columns=...)`; the map is
validated before rows are consumed. The full reference is summarized below.

## Construct and extend objects

Objects can be built without a graph. Once a graph owns them, their convenience
methods delegate membership changes to that graph so indexes and reverse links
stay coherent.

```python
from embed_data_model import DatasetGraph, Exam, Finding, Laterality, Patient


class ResearchExam(Exam):
    pass


patient = Patient("P-001")
exam = patient.add_exam(ResearchExam("A-001", description="screening"))
exam.metadata["review"] = {"complete": False}
finding = exam.add_finding(Finding("A-001", Laterality.LEFT, "1"))

graph = DatasetGraph()
graph.register(patient)
exam.update(description="reviewed")

assert graph.patient("P-001") is patient
assert graph.exam("A-001") is exam
assert graph.finding("A-001", "1") is finding
assert exam.metadata["review"] == {"complete": False}
```

`Patient -> Exam -> Finding` is the main clinical containment path. An exam
also contains images, procedures, pathology bundles, and patient-scoped
registry entries. An image contains its ROIs. Findings and images grouped under
the same exam or breast side are separate facts; the core does not infer a
finding-to-image or finding-to-ROI association from shared scope.

Child collections such as `patient.exams`, `exam.findings`, `image.rois`, and
`exam.breast_sides` are read-only tuple or mapping views. Use `add_*`,
`attach`, `detach`, `replace_rois`, or an explicit update instead of editing a
collection in place. Ordinary attributes, `metadata`, and consumer-added
attributes remain editable. Registered identity fields must change through
`entity.rekey(...)` or `graph.rekey(...)`.

Repeated registration of the same instance is idempotent. A distinct object at
an occupied semantic key raises `ValueError`. Every entity belongs to zero or
one graph. Registering a detached subtree moves its membership; a shared
descendant that must remain in the original graph is copied at the movement
boundary.

## Load semantic snapshots

`load_embed` accepts any combination of these optional inputs: `patients`,
`exams`, `findings`, `images`, `rois`, `hormone_history`, `procedure_history`,
`procedures`, `pathology`, `magview`, and `registry` (with `registry_rows` as an
alias when `registry` is omitted). It accepts iterables of mappings, one-shot
generators, and DataFrame-like values. It returns a `LoadReport` with:

- `report.graph`, the target `DatasetGraph`;
- `report.issues`, issues from this invocation; and
- `report.source_scope`, the source scope used for optional diagnostics.

This complete synthetic load creates one patient, one exam, and one finding:

```python
from embed_data_model import DatasetGraph, Laterality, load_embed


graph = DatasetGraph()
report = load_embed(
    magview=[
        {
            "empi_anon": "P-001",
            "acc_anon": "A-001",
            "numfind": 1,
            "side": "L",
            "desc": "screening",
            "asses": "4",
            "recc": "biopsy",
            "location": "UOQ",
            "depth": "P",
        }
    ],
    into=graph,
)

exam = graph.exam("A-001")
finding = graph.finding("A-001", "1")
assert exam is not None and finding is not None
assert graph.patient("P-001") is not None
assert finding.laterality is Laterality.LEFT
assert finding.interpretation.assessment == "4"
assert finding.interpretation.recommendation == "biopsy"
assert not report.issues
```

The loader groups rows by semantic identity before updating an object. A
patient is keyed by `patient_id`, an exam by accession, and a finding by
`(accession, finding_number)`. Numeric identifiers normalize to stable strings;
blank identifiers do not manufacture shared objects. A `magview` row projects
supported patient, exam, and finding grains while its procedure, pathology,
registry, and linked-accession columns are handled by their corresponding
adapters.

## Refresh and merge

One invocation is one complete grouped snapshot for each grain it addresses.
The default `mode="refresh"` resets bound adapter-managed scalar fields,
including fields that are absent or explicitly null in that snapshot. It keeps
the same Python object, subclass, consumer attributes and metadata, unbound
fields, and child grains that were not supplied. A child-only load ensures
missing parent shells but does not refresh the parent's fields.

`mode="merge"` applies supplied non-null scalar values. Complementary rows
combine. When one snapshot supplies conflicting populated values for a field,
the field becomes unknown and the load report contains an issue. Merge does not
guess equality for unkeyed history facts or for revised ROI collections.

```python
from embed_data_model import load_embed


graph = load_embed(exams=[{"acc_anon": "A-001", "desc": "screening"}]).graph
exam = graph.exam("A-001")
exam.research_note = "keep this"

load_embed(exams=[{"acc_anon": "A-001", "desc": "reviewed"}], into=graph)
assert graph.exam("A-001") is exam
assert exam.description == "reviewed"
assert exam.research_note == "keep this"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], mode="merge", into=graph)
assert exam.description == "reviewed"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], into=graph)
assert exam.description is None
```

Assemble complete semantic groups before calling refresh on streamed chunks.
Two refresh calls containing different columns for the same exam are two
snapshots: the second call can clear fields that the first call supplied. A
single generator is consumed once. `source_scope` and `source_keys` add
diagnostic source references; they do not decide admission, identity, or
replay. `graph.issues` is cumulative, while `report.issues` is local to the
invocation.

## DataFrames and column maps

The adapter accepts a pandas DataFrame or another object that supports
`to_dict(orient="records")`, `index`, and `columns`. DataFrame index values,
including a reset or duplicated index, are never used as semantic identity.
`source_keys` can name a physical diagnostic column or provide a callback. A
missing or duplicate diagnostic key produces an issue but does not prevent a
row with valid clinical identifiers from loading.

The semantic-to-physical direction is always
`columns[table][semantic] = "physical_column"`. Optional fields can be
explicitly unbound with `None`. Required identity fields cannot be unbound.

```python
import pandas as pd

from embed_data_model import load_embed


patients = pd.DataFrame(
    {"research_patient_id": [101], "sex_at_birth": ["F"]},
    index=["source-row-7"],
)
report = load_embed(
    patients=patients,
    columns={
        "patients": {
            "patient_id": "research_patient_id",
            "sex": "sex_at_birth",
        }
    },
    source_keys={"patients": "source-row-id"},
)

patient = report.graph.patient("101")
assert patient is not None and patient.sex == "F"
assert report.graph.patient("source-row-7") is None
```

The requested source key above is absent, so it may produce a diagnostic
warning. The row still loads because `research_patient_id` is its semantic
identity. A DataFrame index is not a substitute for a missing `patient_id`.

The supported default map is:

| Input | Identity and default bindings |
| --- | --- |
| `patients` | `patient_id <- empi_anon`; `sex <- GENDER_DESC`; `birth_year <- birth_year`; `context_date <- studydate_anon` |
| `exams` | `accession <- acc_anon`; `patient_id <- empi_anon`; `exam_date <- studydate_anon`; `exam_description <- desc` |
| `findings` | `(accession, finding_number) <- (acc_anon, numfind)`; `patient_id <- empi_anon`; `laterality <- side`; `assessment <- asses`; `recommendation <- recc`; `location <- location`; `depth <- depth`; `distance <- distance` |
| `images` | source path `anon_dicom_path`; patient/accession `empi_anon`/`acc_anon`; laterality/view `ImageLateralityFinal`/`ViewPosition`; modality `Modality`; derived type `FinalImageType`; dimensions `Rows`/`Columns`; frames `ImagesInAcquisition`; series UID `SeriesInstanceUID` |
| `rois` | source path `anon_dicom_path`; coordinates `ROI_coords`; frame facts `ROI_frames`; depth flag `ROI_depth_derived` |
| `procedures` | identity `(empi_anon, procdate_anon, type, bside)`; optional accession/finding `(acc_anon, numfind)` |
| `pathology` | optional record ID; attachment `(empi_anon, acc_anon, numfind, bside)`; procedure date `procdate_anon`; report date `pdate_anon`; descriptors `path1` through `path10` |
| `hormone_history` | patient `empi_anon`; category/code `type`/`code`; accession `acc_anon`; timing `first_age`, `mfirst`, `yfirst`, `last_age`, `mlast`, `ylast` |
| `procedure_history` | patient `empi_anon`; category/procedure `type`/`pcode`; accession `acc_anon`; laterality `side`; result `result` |
| `registry` | required patient/entry identity `empi_anon`/`cancer_registry_id`; payload is unbound by default |
| `magview` | patient/accession/finding `empi_anon`/`acc_anon`/`numfind`; registry assignment `cancer_outcome_registry_id`; linked accession `linkedaccession_anon` |

`DEFAULT_COLUMNS` is the authoritative mapping object; the table above is a
quick reference. The registry identity binding is deliberately narrower than
the rest of its possible payload. Map additional registry payload fields only
when their source meanings are established.

## Clinical relationships

An accession identifies one exam. Source patient claims are retained in
`exam.asserted_patient_ids`. If claims disagree, accession-addressed findings,
procedures, pathology, and registry assignments can still attach while
`exam.patient_id` remains unset. Choose ownership explicitly with
`graph.assign_patient(exam, "P-001")`; this preserves the source claims and does
not rewrite source patient IDs on associated facts.

Linked accessions and registry assignments are supplied relationships. They
resolve in either arrival order and can remain pending when an endpoint has not
been loaded:

```python
from embed_data_model import load_embed


graph = load_embed(
    magview=[
        {
            "empi_anon": "P-001",
            "acc_anon": "A-001",
            "cancer_outcome_registry_id": 7,
            "linkedaccession_anon": "B-001",
        }
    ],
    registry=[{"empi_anon": "P-001", "cancer_registry_id": 7}],
).graph

exam = graph.exam("A-001")
entry = graph.registry_entry("P-001", "7")
assert exam is not None and entry is not None
assert exam.registry_pathology == (entry,)
assert graph.unresolved_references

load_embed(exams=[{"acc_anon": "B-001"}], into=graph)
assert graph.exam("B-001") in exam.linked_exams
```

`graph.set_linked_accessions(exam, values)` and
`graph.set_registry_assignments(exam, keys)` replace the addressed collection;
pass `merge=True` to union it. In source-table refresh, an absent or unbound
association preserves the existing set, a null clears it, and a supplied set
replaces it. A registry entry is patient-scoped and can be assigned to several
exams. A registry ID by itself does not create a diagnosis.

Verified `procedures` use the complete identity `(patient_id, performed_date,
procedure_type, laterality)`. Incomplete records remain accessible through
`graph.unresolved_records` rather than becoming one procedure per physical row.
Pathology prefers a supplied patient-scoped record ID. Without one, the
documented attachment plus report-documentation-date fallback is used; an
ambiguous or insufficient key remains unresolved. Descriptor slots retain
order and duplicate values. A report date is not substituted for the procedure
date or a diagnosis event date.

`hormone_history` and `procedure_history` are patient-owned reported facts.
They are distinct from performed procedures. Identified history rows refresh
their existing object in place. Without an event ID, refresh replaces that
history kind as a patient snapshot; merge requires explicit record IDs and
preserves existing unkeyed facts while reporting the limitation.

## Images and ROI collections

`MammogramImage.image_id` is the mutable toolkit identity. The original
`source_sop_instance_uid` and `source_paths` are separate source facts. A path
matching the EMBED convention
`cohortN/patient/study/series/SOP.dcm` can supply source identity and study or
series context without opening pixels. An explicit SOP UID wins if it conflicts
with a path-derived UID, and the report carries an issue. Relocating a file
adds a path alias; rekeying the toolkit image does not break source lookup.

Image metadata automatically projects its `ROI_coords` collection. A row in
the explicit `rois` input overrides the automatic collection for the image it
addresses. Each collection is complete for that image: missing or null
coordinates preserve the current collection, `[]` clears it, and malformed or
conflicting collections preserve the previous collection with an issue. A
valid replacement creates image-local ROI objects, so manual annotations and
old ROI references should be saved before replacement. This behavior applies
in both refresh and merge modes.

```python
from embed_data_model import load_embed


path = "/data/cohort1/P-001/study-1/series-1/SOP-001.dcm"
report = load_embed(
    images=[
        {
            "anon_dicom_path": path,
            "ROI_coords": "[(10, 20, 30, 50)]",
            "Rows": 100,
            "Columns": 120,
        }
    ]
)

graph = report.graph
image = graph.source_image("SOP-001")
assert image is not None and len(image.rois) == 1
roi = image.rois[0]
assert roi.identity == (image.image_id, "0")
assert roi.coordinates == (10.0, 20.0, 31.0, 51.0)

image.rekey(image_id="processed-SOP-001")
roi.update(confidence=0.75)
assert graph.roi("processed-SOP-001", "0") is roi
assert graph.roi_at_source(path, 0) is roi
```

ROI coordinates are stored as half-open `(y_min, x_min, y_stop, x_stop)`
geometry. EMBED inclusive maxima are converted once; `source_coordinates`
retains the original values. The collection position is zero-based and is part
of the source lookup address. Equal boxes in different positions are distinct
ROIs. `ROI_frames` remains a tuple of supplied frame facts, and
`ROI_depth_derived` records whether depth was source-supplied or derived; the
loader does not invent frame indices or clinical correspondence.

Derivatives require an explicit toolkit `image_id` and `derived_from`. Their
metadata and ROIs do not replace the original source image or its source-path
lookups. Images with an accession can establish an exam shell and source patient
claim; an image row without clinical context remains image-local.

## Selection, validation, partitioning, and movement

`graph.select(level=..., predicate=...)` returns a live, non-owning selection.
Editing a selected object edits the source graph. `graph.partition(level=...,
key=...)` returns independent owning graph copies. A scalar key, including a
tuple, selects one output; a list or set key places the object in several
outputs. Lower-level partitions carry copied ancestor context and only the
selected branches. Supported levels include patient, exam, finding, procedure,
pathology, image, ROI, and registry.

Validation is separate from loading and selection:

```python
from embed_data_model import load_embed


graph = load_embed(
    images=[
        {
            "anon_dicom_path": "/data/cohort1/P/study/series/SOP.dcm",
            "Rows": 100,
            "Columns": 100,
            "ROI_coords": "[(1, 2, 10, 20)]",
        }
    ]
).graph

selected = graph.select(level="image", predicate=lambda image: image.height == 100)
assert len(selected) == 1
valid, invalid = graph.partition_by_validation(level="image")
assert valid.image("SOP") is not None
assert invalid.images == ()
```

`validate` is read-only. It reports represented quality facts such as
contradictory patient claims, confidence and dimension ranges, ROI ordering and
bounds, frame consistency, date plausibility, and pathology severity. Errors
make `ValidationResult.valid` false; warnings remain valid unless
`warnings_invalid=True`. Missing optional tables are not errors. Custom
validators can inspect consumer fields.

`graph.pop(entity, boundary="copy_shared")` moves an owning subtree out of its
graph. Exclusive descendants keep their Python identity. A shared descendant
needed by the retained graph is independently copied into the moved subtree;
linked exams remain semantic references. Register the returned subtree in
another graph to complete the move. A foreign-owned subtree passed to
`register` follows the same boundary policy.

## Serialization and diagnostics

`entity.to_dict()` and `graph.to_dict()` return JSON-ready structures. Repeated
objects and linked cycles are emitted as references instead of recursively
duplicating the graph. `Issue` and `SourceRef` preserve optional source scope,
table, and typed diagnostic key information. `graph.unresolved_references`
reports association endpoints that have not arrived; `graph.unresolved_records`
holds source records whose clinical identity is insufficient or ambiguous.

These diagnostics do not turn physical rows into clinical identities. A caller
that needs an audit ledger or a stricter rejection policy should build that
policy around the returned report and unresolved collections.

## Development

Run from the repository root:

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check src/embed_data_model tests examples benchmarks
uv run --frozen mypy
uv run --frozen python -m examples.researcher_journeys
```

The package has no mandatory runtime dependencies. pandas is used by the
development and test environment; DataFrame-like support is duck-typed at the
table boundary. The full suite includes an installed-wheel journey outside the
checkout. Synthetic checks establish library behavior, not private EMBED-data,
real-pixel, or downstream scientific validity.

Matching, localization, transfer, patch extraction, and visualization are
consumer workflows. Keep them in the downstream repository that owns the
relevant image data and analysis policy. The current contract and settled API
semantics are [mutable-scaffold-contract.md](../docs/mutable-scaffold-contract.md)
and [mutable-scaffold-api.md](../docs/mutable-scaffold-api.md).
