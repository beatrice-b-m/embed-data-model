# Downstream migration guide

This guide is for a person or coding agent moving a consumer from the former
WIP project layout to EMBED Data Model. The package keeps version `0.1.0` and
the clinical and imaging behavior is intended to stay the same. The package
identity and repository layout change, so consumers should make the import and
installation updates together.

## Package identity

| Before | After |
| --- | --- |
| Project directory `unified-system/` | Repository root |
| Distribution `embed-toolkit-unified` | Distribution `embed-data-model` |
| Python namespace `embed_toolkit` | Python namespace `embed_data_model` |
| Version `0.1.0` | Version `0.1.0` |

The old `embed_toolkit` name is not retained as a compatibility alias. It is a
separate package name used by an existing `embed-toolkit` library. A consumer
that needs both libraries should import each namespace explicitly and pin each
dependency independently.

## Install the source revision

During 0.x development, install the checkout or a pinned Git revision. There is
no package-index release implied by this migration:

```bash
# Local development
python -m pip install -e /path/to/wip-embed-toolkit

# Reproducible source dependency; replace the placeholder with a qualified SHA
python -m pip install \
  "git+ssh://git@github.com/beatrice-b-m/wip-embed-toolkit.git@<commit-sha>"
```

If the consumer uses `uv`, add the repository URL and exact revision to its
dependency configuration, then lock it. Keep the source revision in the
consumer's lockfile so a later namespace or behavior change cannot arrive by
accident. Do not use `pip install embed-data-model` as evidence that a public
release exists.

## Update imports

Replace the package prefix everywhere in application code, tests, examples,
type-checking configuration, and notebooks:

```text
from embed_toolkit import DatasetGraph, load_embed
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.sources.embed.columns import DEFAULT_COLUMNS
from embed_toolkit.core.validation import validate
```

becomes:

```text
from embed_data_model import DatasetGraph, load_embed
from embed_data_model.clinical.findings import Finding
from embed_data_model.sources.embed.columns import DEFAULT_COLUMNS
from embed_data_model.core.validation import validate
```

The root facade is the preferred import boundary for the common types:
`DatasetGraph`, `Patient`, `Exam`, `Finding`, `Procedure`,
`ProcedureIdentity`, `Pathology`, `CancerRegistryEntry`, `MammogramImage`,
`RegionOfInterest`, `Box`, `Laterality`, `ImageModality`, `ViewPosition`,
`load_embed`, `validate`, `ValidationResult`, `Issue`, `SourceRef`, and
`LoadReport`. Use specialist modules for source mappings and types that are not
exported from the root. Do not add an import fallback such as
`try: import embed_data_model except ImportError: import embed_toolkit`; that
would silently select the other package and make a deployment ambiguous.

An agent doing the cutover can search the consumer with:

```bash
rg -n "embed_toolkit|embed-toolkit-unified|unified-system" .
```

Review each match. Historical notes about the former package can stay in an
archive, but runtime imports, project paths, package metadata, and test setup
must use the new namespace and root layout. The package reports
`embed_data_model.__version__ == "0.1.0"`.

## Update installation paths

Commands that used to run from `unified-system/` now run from the repository
root:

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check src/embed_data_model tests examples benchmarks
uv run --frozen mypy
```

The source tree is `src/embed_data_model`. Update package discovery, mypy file
lists, Ruff paths, wheel smoke tests, and any consumer `PYTHONPATH` references
at the same time. The distribution has no mandatory runtime dependencies;
pandas is a development/test dependency and is not required for object-only
use.

## Recheck table and DataFrame mappings

`load_embed` accepts mappings, iterables of mappings, one-shot generators, and
pandas-like DataFrames. The semantic identity is independent of the physical
DataFrame index. A reset index, duplicated index, or a slice with a different
index must produce the same patient, exam, finding, image, or ROI identity when
the mapped source fields are the same.

The `columns` argument maps semantic names to physical names:

```text
columns["patients"]["patient_id"] = "research_patient_id"
columns["findings"]["finding_number"] = "finding_no"
```

Use `None` to unbind an optional semantic field from an adapter. Required
identity fields cannot be unbound. The mapping is partial: unspecified fields
keep their defaults. The complete current default map is available from
`embed_data_model.sources.embed.columns.DEFAULT_COLUMNS` and is summarized in
the [user guide](user-guide.md).

This complete example uses a renamed DataFrame schema and demonstrates the
expected result:

```python
import pandas as pd

from embed_data_model import load_embed


patients = pd.DataFrame(
    {"research_patient_id": [101], "sex_at_birth": ["F"]},
    index=["row-from-source"],
)
report = load_embed(
    patients=patients,
    columns={
        "patients": {
            "patient_id": "research_patient_id",
            "sex": "sex_at_birth",
        }
    },
)

assert report.graph.patient("101").sex == "F"
assert report.graph.patient("row-from-source") is None
```

`source_keys` is available when a source row key is useful for diagnostics:
`source_keys={"patients": "source_row_id"}` or a callback. A bad or missing
diagnostic key produces an issue, while a valid semantic ID still admits the
row. It is not an alternate identity field.

## Preserve the policy boundary

The package owns source translation, mutable domain objects, explicit
containment, supplied associations, optional validation, and independent graph
movement. Downstream code owns study policy. Keep these decisions in the
consumer repository:

- cohort definitions, inclusion/exclusion rules, and outcome windows;
- pixel reading, preprocessing, alignment, and image-derived measurements;
- finding localization, finding-to-ROI matching, and cross-image
  correspondence;
- ROI transfer, patch extraction, visualization, and model-specific metadata;
- clinical/scientific interpretation and diagnosis inference.

The core does not infer a finding-to-image relationship because an exam or side
is shared. It does not turn a registry reference into a diagnosis. A registry
assignment supplied by the source remains a supplied relationship, and a
patient/exam conflict remains inspectable until a consumer explicitly chooses
ownership with `graph.assign_patient(...)`. `validate(...)` is an explicit
read-only quality report; loading representable but implausible facts is not an
automatic rejection policy.

Do not reintroduce a consumer workflow into the root facade merely to preserve
an old import. Put the workflow in the repository that owns its inputs and
analysis policy, and store the package revision used by that workflow.

## Avoid refresh and merge traps

Treat each call to `load_embed` as one complete grouped snapshot for every
semantic grain that it addresses.

`mode="refresh"` is the default. For bound adapter-managed scalar fields it
resets values that are absent or explicitly null in the incoming snapshot. It
updates the existing object in place, keeps consumer attributes/metadata and
subclasses, and leaves unbound fields and unspecified child grains alone.

`mode="merge"` applies supplied non-null scalar values. Complementary rows in
one invocation combine; conflicting populated values become unknown and add an
issue. It does not infer whether two unkeyed history rows or two revised ROI
collections represent the same event.

These rules make the following results intentional:

```python
from embed_data_model import load_embed


graph = load_embed(exams=[{"acc_anon": "A-001", "desc": "screening"}]).graph
exam = graph.exam("A-001")
exam.consumer_note = "preserve"

load_embed(exams=[{"acc_anon": "A-001", "desc": "reviewed"}], into=graph)
assert graph.exam("A-001") is exam
assert exam.description == "reviewed"
assert exam.consumer_note == "preserve"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], mode="merge", into=graph)
assert exam.description == "reviewed"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], into=graph)
assert exam.description is None

report = load_embed(
    exams=[
        {"acc_anon": "A-001", "desc": "one"},
        {"acc_anon": "A-001", "desc": "two"},
    ],
    mode="merge",
    into=graph,
)
assert exam.description is None
assert any("conflicting_exam" in issue.code for issue in report.issues)
```

Do not split one repeated MagView object across separate refresh calls when the
calls are meant to complement one another. Materialize and group streamed
chunks first. A child-only load, such as `findings=...` or `rois=...`, ensures a
missing parent shell but does not refresh parent scalar fields.

Collections have their own replacement rules:

- An explicit `rois` collection replaces the addressed image collection in
  either mode. Missing or null coordinates preserve the collection; `[]`
  clears it; malformed or conflicting replacements preserve the previous
  collection and add an issue. Save manual ROIs before a valid replacement if
  they must survive.
- A supplied linked-accession or registry-assignment collection replaces that
  collection on refresh. Absent or unbound preserves it; null clears it;
  `merge` unions supplied values.
- Identified history rows use their record ID for in-place refresh. Unkeyed
  history refresh replaces that history kind for the patient. Unkeyed history
  merge cannot establish event equality, so existing facts remain and the
  report explains that explicit IDs are required.

## Confirm expected graph results

Use a synthetic repeated-row fixture before and after the cutover. It checks
that namespace migration did not turn source-row multiplicity into object
multiplicity:

```python
from embed_data_model import load_embed


rows = [
    {
        "empi_anon": "P-001",
        "acc_anon": "A-001",
        "numfind": 1,
        "side": "L",
        "bside": "L",
        "type": "biopsy",
        "procdate_anon": "2024-01-10",
        "pdate_anon": "2024-01-11",
        "path1": "ADH",
    },
    {
        "empi_anon": "P-001",
        "acc_anon": "A-001",
        "numfind": 1,
        "side": "L",
        "bside": "L",
        "type": "biopsy",
        "procdate_anon": "2024-02-10",
        "pdate_anon": "2024-02-11",
        "path1": "ADH",
    },
]
graph = load_embed(magview=rows).graph

assert len(graph.patients) == 1
assert len(graph.exams) == 1
assert len(graph.findings) == 1
assert len(graph.procedures) == 2
assert len(graph.pathology) == 2
finding = graph.finding("A-001", "1")
assert finding is not None
assert len(finding.procedures) == 2
assert len(finding.pathology) == 2
```

The expected cardinalities are one patient, one exam, one finding, two
complete procedures, and two pathology bundles. Reversing `rows` should keep
the same cardinalities and the same canonical object identities. An incomplete
procedure or ambiguous pathology key should remain visible in
`graph.unresolved_records` instead of being promoted using a row ordinal.

## Agent handoff checklist

After changing a consumer:

1. Update all runtime and test imports to `embed_data_model`.
2. Move install, type-check, lint, and test paths from `unified-system/` to the
   repository root.
3. Compare custom `columns` maps with `DEFAULT_COLUMNS`; verify semantic and
   physical directions.
4. Test one complete refresh snapshot and one explicit merge. Include absent,
   null, unbound, and conflicting fields where the consumer depends on them.
5. Test image/ROI collection replacement separately from scalar image metadata.
6. Keep downstream matching, transfer, pixel, and cohort policy in the
   consumer code.
7. Pin the exact source revision and record expected graph cardinalities and
   package version in the consumer's qualification notes.

Run the package's [researcher journey](../examples/researcher_journeys.py) and
the full root checks before accepting the port. Synthetic library tests verify
object behavior; they do not qualify private EMBED data, real pixels, or the
consumer's scientific conclusions.
