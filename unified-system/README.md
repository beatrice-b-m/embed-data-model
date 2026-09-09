# Unified EMBED Toolkit

Mutable clinical and mammography objects, semantic table loading, and an indexed
`DatasetGraph`. Every table is optional. The governing [mutable scaffold contract](../docs/mutable-scaffold-contract.md)
and [API decisions](../docs/mutable-scaffold-api.md) define the public behavior.

## Construct and extend objects

```python
from embed_toolkit import DatasetGraph, Patient, Exam, Finding, Laterality

class ResearchExam(Exam):
    pass

patient = Patient("P")
exam = patient.add_exam(ResearchExam("A", description="screening"))
exam.metadata["review"] = {"complete": False}
finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
graph = DatasetGraph()
graph.register(patient)
exam.update(description="reviewed")
```

Objects also work without a graph. Convenience add/remove/update methods maintain
membership when registered. Patient and exam traversal exposes findings, procedures,
and pathology; findings expose procedures and pathology; procedures expose pathology.
Shared descendants are deduplicated. `exam.registry_pathology` distinguishes registry
entries. Images and findings grouped by breast side do not imply correspondence.
Child collections are tuple views; mutate through methods instead of editing lists.

Ordinary attributes and consumer metadata are editable. Registered identifiers use
`entity.rekey(...)` or `graph.rekey(entity, ...)`, which updates dependent indexes.
Distinct objects at an occupied semantic key raise `ValueError`; repeated registration
of the same instance is idempotent. Operations check local invariants; a load is not
a graph-wide atomic transaction. Consumers can subclass entities and attach fields.

## Load complete semantic snapshots

```python
from embed_toolkit import load_embed

report = load_embed(
    magview=[{"empi_anon": "P", "acc_anon": "A", "numfind": 1, "side": "L"}],
    images=[{"acc_anon": "A", "anon_dicom_path": "/data/cohort1/P/study/series/SOP.dcm",
             "Rows": 100, "Columns": 100, "ROI_coords": "[(1, 2, 10, 20)]"}],
    into=graph,
)
load_embed(exams=[{"acc_anon": "A", "desc": "corrected"}], into=graph)
assert graph.exam("A") is exam
assert exam.metadata["review"] == {"complete": False}
```

Inputs accept DataFrames or iterables of mappings, including one-shot generators.
Indexes, reset indexes, and diagnostic source keys do not determine admission or
clinical identity. Numeric semantic IDs normalize consistently. `columns` supplies
partial mappings, for example `{"patients": {"patient_id": "research_id"}}`;
set a semantic mapping to `None` to leave that field outside the adapter's control.

The default `mode="refresh"` resets bound scalar fields of each supplied grain,
including absent/null fields, then applies its grouped snapshot. It preserves live
object references, subclasses, consumer attributes/metadata, unbound fields, and
unspecified child grains. `mode="merge"` applies supplied non-null scalar values.
Explicit mutation can clear a value. Repeated complementary rows combine; conflicting
populated values become unknown and produce an issue. Wide and narrow tables share
these rules. Loading only a child creates missing parent shells without refreshing
existing parent payload.

One invocation is one snapshot. Assemble complete semantic groups before loading
streamed chunks; splitting one repeated object across refresh calls would submit
separate snapshots. Complete patient groups may be loaded independently. No raw-row
ledger is needed. Optional `source_keys`/`source_scope` provide diagnostics only;
`report.issues` reports that invocation, and `graph.issues` keeps cumulative issues.

Other inputs include `patients`, `exams`, `findings`, `procedures`, `pathology`,
`hormone_history`, `procedure_history`, and `registry`. Identified histories refresh
in place. Without event IDs, histories are patient/kind reported-fact snapshots;
refresh replaces that kind, while merge preserves it and reports that explicit IDs
are needed. These histories are distinct from performed procedures.
Pathology prefers supplied record IDs; the documented attachment/date fallback
preserves ordered descriptor slots. Insufficient or ambiguous keys remain accessible
through `graph.unresolved_records` instead of invented row identities.

## Ownership and supplied associations

An accession identifies one exam. `exam.asserted_patient_ids` preserves patient
claims; conflicting claims leave ownership unresolved. `graph.assign_patient(exam,
"P")` explicitly chooses an owner while retaining the conflict for validation.
Accession-addressed images and clinical facts still attach. Source patient IDs on
associated facts are not rewritten by that choice.

```python
load_embed(magview=[{"acc_anon": "A", "empi_anon": "P",
                     "cancer_outcome_registry_id": 7, "linkedaccession_anon": "B"}],
           into=graph)
load_embed(registry=[{"empi_anon": "P", "cancer_registry_id": 7}], into=graph)
assert graph.exam("A").registry_pathology[0] is graph.registry_entry("P", "7")
print(graph.unresolved_references)
```

Registry keys are patient-scoped. The maintainer-approved initial mapping binds
`empi_anon` and `cancer_registry_id`; additional payload mappings are deferred.
Assignments remain confirmed even before endpoints arrive; one registry entry can
be associated with several exams. Linked exams resolve in either arrival order and
may form cycles. Supplied assignment/link columns replace the addressed exam's
collection on refresh; null clears, absent/unbound preserves, merge unions. Clearing
an association leaves its target registered. Missing endpoints stay pending.

## Images and ROI collections

`image_id` is mutable toolkit identity, `source_sop_instance_uid` is original image
identity, and `source_paths` holds aliases. The adapter parses trailing
`cohortN/patient/study/series/SOP.dcm` without opening pixels. Explicit SOP UID wins
over a conflicting path UID, with an issue. Relocation adds aliases; source reload
finds the original image even after toolkit rekey. Derivatives need an explicit
mapped toolkit ID and `derived_from`; they never replace the source SOP object.

Metadata projects ROIs automatically. Explicit `rois` rows override that projection
for addressed images. Each supplied collection is a complete image snapshot:
missing/null preserves, `[]` clears, malformed/conflicting input preserves with an
issue. Refresh and merge both replace addressed collections, including manual ROIs.
Save/pop manual annotations first if they should survive replacement. Unaddressed
images remain unchanged; ROI-only input can create a source-image shell.

```python
image = graph.source_image("SOP")
roi = image.rois[0]
image.rekey(image_id="research-SOP")
assert graph.roi_at_source("/data/cohort1/P/study/series/SOP.dcm", 0) is roi
roi.update(coordinates=(2, 3, 12, 22))
```

ROI source addresses are path plus zero-based collection position, even for a
singleton. Equal boxes occupy distinct slots. Geometry uses half-open y/x bounds;
EMBED inclusive maxima are converted once, with original coordinates retained.
Supplied frames and the `ROI_depth_derived` flag are retained without inferring depth.
Individual ROI updates retain references; collection replacement may create new ROIs.
Manual ROIs use explicit image-local keys and need no source locator.

## Move, select, validate, and partition

```python
from embed_toolkit import validate

selection = graph.select(level="exam", predicate=lambda obj: obj.description is None)
parts = graph.partition(level="exam", key=lambda obj: obj.description or "unknown")
valid, invalid = graph.partition_by_validation(level="exam", validator=validate)
detached = graph.pop(exam, boundary="copy_shared")
other = DatasetGraph()
other.register(detached)
```

A selection holds live, non-owning objects. Partitions are independent owning copies:
one copy per shared object per output, copied ancestor context marked `context=True`,
and only selected branches. A list/set returned by the key function selects multiple
outputs; a tuple is one key. Supported clinical levels are patient, exam, finding,
procedure, and pathology, with image/ROI/registry levels also available.

Pop moves exclusive descendants. A shared descendant needed in the retained graph
stays there and is copied into the detached subtree (`copy_shared`). Linked exams
stay semantic references across boundaries. Registering a foreign-owned subtree
moves its membership with the same policy. Detach removes an edge and leaves the
child registered, even when it has no remaining parents. Deep-copy hooks support
consumer state; uncopyable fields raise an informative error instead of being shared
silently across owning outputs.

`validate` is explicit and read-only. Representable out-of-range geometry, confidence,
age/date, severity, and frame facts can load first and be inspected later. Errors
invalidate; warnings do not unless `warnings_invalid=True`. Missing optional tables
alone are valid. Custom validators can inspect consumer fields. Valid/invalid
partitions use the same independent-copy and context rules.

## Development and scope

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check src/embed_toolkit tests examples benchmarks
uv run --frozen mypy
```

Python 3.9–3.13 is the declared test matrix. The package has no runtime dependencies;
pandas is a development/test dependency. The wheel acceptance test uses only public
imports outside the checkout without `PYTHONPATH`. See [qualification](../docs/mutable-scaffold-qualification.md)
and [synthetic benchmarks](benchmarks/README.md).

The obsolete locator-based patch extraction recipe is retired. Matching and transfer
workflows are separate consumer ports described in the implementation plan; they are
not required by the core. [Legacy test disposition](../docs/mutable-scaffold-test-disposition.md)
records replacement coverage and intentional retirements.
