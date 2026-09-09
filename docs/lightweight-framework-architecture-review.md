# Lightweight framework architecture review and recovery record

Date: 2026-08-26
Status: historical recovery implemented on 2026-08-26; target superseded.

The maintainer-directed [mutable scaffold contract](mutable-scaffold-contract.md)
now governs future work. It replaces conflicting requirements below, including
strict atomic transactions, immutable graph membership, and DataFrame-index
source identity. The new target is not yet implemented.

## Current architecture outcome

The repository now meets the central product goal established by this review: a
small, source-aware framework that researchers can populate from any supported
subset of tables and extend with project-specific workflows. The canonical
`DatasetGraph`/`load_embed` surface provides transactional incremental loading,
the package root exposes a bounded facade, and optional workflows live in
repo-only examples. The replacement-test matrix is recorded in
[lightweight-framework-test-traceability.md](lightweight-framework-test-traceability.md).

The requirements, target construction model, dependency rule, and global
acceptance criteria below describe the earlier architecture contract. The
assessment, topology, findings, risks, and phased plan are retained as the
historical recovery record, not as descriptions of the current tree.

## Historical review baseline

Scope: `unified-system/`, active repository documentation, tests, and relevant
git history as reviewed at baseline revision
`b4e1de8f172d412e0fdd676c31498dee3c8ce110`.

Unless a different revision is written explicitly, every historical source
path and line reference below is commit-qualified by that baseline revision and
is relative to `unified-system/src/embed_toolkit/`. This convention keeps
references to subsequently deleted modules, such as `adapters/embed.py`,
auditable with
`git show b4e1de8:unified-system/src/embed_toolkit/<path>`.

### Pre-recovery executive judgment

At the reviewed baseline, the repository did not meet its central product goal:
a small, source-aware framework that researchers can populate from whatever
subset of tables they have and then extend with project-specific workflows.

The baseline implementation was scientifically careful in several important
ways, but it was pipeline-shaped rather than framework-shaped. The strongest
supported path was one complete, wide, finding-grain MagView row stream,
optionally followed by one image-metadata build and a separate reconciliation
call. Patient-only, clean exam-only, direct DataFrame, incremental, and
multi-table composition were either unsupported or required undocumented
workarounds.

The most consequential problem was not the 13,320-line size by itself. It was
that the size had not purchased a composable user model:

- Clinical, image, and patient-history builders create separate object
  registries.
- The object named `EmbedClinicalImageGraph` is a lossy exam/image projection,
  not the complete clinical graph.
- Assembly clones exams, so patients retain different, image-free exam objects.
- DataFrames are not accepted directly despite being the intended researcher
  input and despite the original architecture promising DataFrame adapters.
- A patient table cannot construct a patient unless it also contains an
  accession; an exam row without a finding is marked erroneous.
- Renaming one input column requires a complete matching profile contract.
- Workflow-specific code and its audit/result machinery occupy a substantial
  portion of the installed runtime and are not independently removable.

This was architectural drift, not a documentation problem. The appropriate
response was not to split the 3,394-line adapter mechanically. The construction
model needed to be replaced with one canonical identity registry and a small
grain-oriented ingestion protocol, then the old wrappers, clone-based assembly,
mandatory governance layers, and workflow leakage needed to be deleted.

The recommended north star is:

> Any supplied table contributes the objects and relationships its own grain can
> safely establish. All tables are optional. Repeated loads enrich the same
> canonical graph. Source-specific rules live in source adapters, and
> opinionated workflows depend on the framework without becoming part of it.

### Pre-recovery review method and evidence

This review used four complementary passes:

1. Read every active runtime package, its exports, project metadata, current
   architecture documents, and the historical design sections governing
   DataFrame ingestion and workflow boundaries.
2. Traced clinical, image, history, and clinical/image assembly call paths from
   their public functions to node construction and reconciliation.
3. Reconstructed realistic researcher journeys at patient, exam, finding,
   image, and combined levels, including executable probes for missing values,
   partial rows, and custom column maps.
4. Audited package size, dependency direction, public surface, test allocation,
   git history, dead/duplicated helpers, packaging, and static quality signals.

Verification performed on 2026-08-26:

- `uv run pytest`: **485 passed** in 0.30 seconds.
- `ruff check unified-system/src/embed_toolkit unified-system/tests`: passed.
- Unconfigured `mypy unified-system/src/embed_toolkit`: **100 errors in 17 of 48
  source files**. Many are cascades from the imprecise return type on
  `CoercibleEnum`, so this is a quality signal rather than 100 independent
  defects.
- The environment created by the project lock contains no pandas, Polars, or
  PyArrow package.
- Direct probes confirmed that a numeric NaN patient ID becomes the literal
  patient identity `"nan"`, a patient-only row constructs no patient, an
  exam-only row receives an error-severity missing-finding issue, and an
  ordinary column override fails profile validation before rows are consumed.

The existing Lucid document is linked from `docs/system-architecture-review.md`
and its three pages are described there. The interactive chart itself was not
retrievable from the review environment, so this assessment is grounded in the
checked-in architecture description and the runtime it summarizes.

## North-star requirements

These should become the governing contract for future architecture decisions.

1. **Every table is optional.** Clinical-only, patient-only, exam-only,
   finding-only, image-only, ROI-only, and history-only inputs are valid.
2. **Each grain has its own minimum identity.** Missing child identifiers do not
   invalidate a safe parent. A patient needs a patient ID; an exam needs an
   accession; a finding needs its finding identity; an image needs an image ID.
3. **There is one graph.** All loads resolve through one identity registry and
   enrich the same objects. Assembly never clones an already-owned node.
4. **Incremental loads are transactional.** Strict failures leave the existing
   graph untouched. Audit mode commits only contributions independently judged
   safe and reports every rejected contribution.
5. **The graph can be viewed at any useful root.** Patient, exam, image, or ROI
   views are projections over the same state, not separately built graphs.
6. **DataFrames are first-class inputs.** Researchers can pass filtered pandas
   DataFrames directly. The runtime should support them through duck typing so
   pandas does not become a mandatory dependency.
7. **Filtering retains source identity.** A DataFrame index or caller-selected
   key is preserved; a new zero-based ordinal is only a fallback.
8. **Missingness and identifiers have one governed path.** Generic table
   extraction recognizes scalar nulls; semantic source adapters decide
   trimming, numeric identifier treatment, leading zeros, and source sentinels.
   `NaN`, `pd.NA`, `NaT`, and whitespace cannot create accidental identities.
9. **Source opinions stay in adapters.** MagView codes, EMBED sentinels, V1c ROI
   rules, source-specific image mappings, and auxiliary-table vocabularies do
   not leak into source-neutral objects or generic workflows.
10. **Workflow bundles are removable.** Deleting ROI transfer or finding-to-ROI
   matching must not require a core change. Core never imports an example or
   workflow package.
11. **Correctness remains visible but inexpensive.** Identity conflicts,
    unresolved relationships, and parsing issues remain inspectable. Ordinary
    loading does not require an exhaustive profile ontology.
12. **Extension cost is local.** Adding one table should normally require one
    adapter, tests, and one source-facade wiring change if it becomes built in;
    adding one mapped field should not require edits to five schema layers.
13. **The common path is obvious.** A new researcher can construct and traverse
    a useful graph from filtered tables in a short README example without
    learning internal provenance or contract classes.

Minimal does not mean removing safeguards or collapsing all values into loose
dictionaries. It means keeping only the mechanisms that enforce current user
stories, locating them at the correct boundary, and making their cost
proportional to the task.

## Pre-recovery topology and scale

### Runtime allocation

| Package | LOC | Baseline role |
|---|---:|---|
| `adapters` | 4,732 | Parsing, construction, reconciliation, graph assembly |
| `workflows` | 1,887 | Localization, matching, transfer, extraction |
| `clinical` | 1,736 | Clinical objects and temporal observations |
| `imaging` | 1,378 | Images, ROIs, geometry, provenance, alignment |
| `config` | 1,312 | Columns, profile contracts, capability and coverage declarations |
| `core` | 1,035 | Primitives, anatomy, BI-RADS, provenance, build policy |
| `audit` | 833 | Evidence, warnings, result types, export |
| `visualization` | 399 | Mammogram render plans |

Total runtime: **13,320 lines across 48 Python modules**.

Supporting machinery—adapters, config, workflows, audit, and visualization—is
9,163 lines, or **68.8% of the runtime**. Optional workflow, audit, and
visualization code alone is 3,119 lines. `adapters/embed.py` is 3,394 lines,
contains 68 top-level functions, and accounts for 25.5% of the runtime.

The cognitive surface is also broad: 136 runtime classes, 88 dataclass
declarations, and 125 names exported across package and subpackage `__all__`
lists. Despite that, the root `embed_toolkit` package exposes only
`__version__`, so the large surface is also poorly discoverable.

Tests contain 11,243 lines and 374 explicitly declared test functions producing
485 collected cases. This is a strong unit-level safety net, but the integration
directory is empty, no test passes a real DataFrame, and no test constructs the
complete graph a researcher expects.

The tracked `temp/` reference code adds another 1,293 lines outside the package.

### Actual construction flow

```text
MagView-like row mappings
    -> build_clinical_tables
    -> EmbedClinicalTables
       -> Patients -> original Exams -> Findings
       -> flat procedures/pathology/links/ledgers

Image-metadata row mappings
    -> build_image_tables
    -> EmbedImageTables
       -> Images
       -> separate flat ROIs/ledgers

EmbedClinicalTables + EmbedImageTables
    -> assemble_clinical_image_graph
    -> clone clinical Exams
    -> attach original Images to cloned Exams
    -> EmbedClinicalImageGraph
       -> no Patients, Histories, ROIs, Procedures, Pathology, or upstream issues

HormoneHist / ProcHist row mappings
    -> build_patient_history_tables
    -> a second Patient registry containing histories only
```

There is therefore no traversal rooted in one object that supports:

```text
Patient -> Exam -> BreastSide -> Image -> ROI
    |         |
    |         -> Finding -> Procedure / Pathology links
    -> Patient history
```

## Pre-recovery researcher-journey assessment

| Desired use | Baseline behavior | Assessment |
|---|---|---|
| Pass a filtered pandas DataFrame | DataFrame iteration yields column labels; users must discover `.to_dict("records")` | Unsupported |
| Build patients from a patient table | Missing accession returns before Patient construction | Unsupported |
| Build exams without findings | Patient and Exam are created, but every row receives an error-severity missing-finding issue | Semantically wrong |
| Build complete MagView finding rows | Patients, exams, sides, findings, procedures, and pathology are projected | Supported, heavily tested |
| Build images without clinical data | Images and ROIs are built without a clinical table | Supported |
| Build histories without exams | Separate Patient objects are built | Locally supported, not composable |
| Combine clinical and images | Exam clones receive images | Partial; patient navigation is not available from the combined result |
| Combine clinical and history | No merge API exists | Unsupported |
| Add a later table to an existing graph | Builders are one-shot and result-specific | Unsupported |
| Rename one column | Built-in contract rejects the new physical field surface | Impractical |
| Supply a custom source | Requires a full contract declaring all governed concepts and exact coverage | Excessive extension cost |
| Preserve filtered DataFrame row identity | Builders replace the original index with call-relative ordinals | Unsupported |
| Start at cohort scope | `Cohort` is manual only; configured cohort ID is raw-only | Unsupported; no demonstrated core user story |
| Load MESH by that name | Before this review, no implemented source adapter or source contract used that name | Undefined |

The historical plan explicitly proposed `EmbedCohortAdapter.from_dataframes`,
`EmbedPatientAdapter.from_dataframe`, `EmbedExamAdapter.from_dataframes`, and
equivalents for images, findings, procedures, and ROIs in
`docs/unified-system-plan.md:601-619`. It also required fixture DataFrame tests
at lines 840-856. Neither the constructors nor the DataFrame tests were
implemented.

The early repository history is revealing. The former `matching.Exam` had a
direct `register(findings: pd.DataFrame, images: pd.DataFrame)` method
(`23b622b:matching/exams.py`). That
implementation was too hard-coded and unsafe to retain, but it served the
researcher's entry point directly. The replacement corrected many scientific
and identity defects, then swung past the intended balance into exhaustive
governance without restoring an equally usable entry point.

## Pre-recovery severity-ranked findings

### Critical: the assembled object is not the clinical graph

`EmbedClinicalTables` holds patients, exams, findings, procedures, pathology,
links, occurrences, issues, and a profile contract
(`adapters/embed.py:237-392`). `EmbedImageTables` separately holds images, ROIs,
occurrences, issues, and its contract (`adapters/embed.py:393-465`).

`assemble_clinical_image_graph` then clones clinical exams at
`adapters/embed.py:209-227` and `:2432`, attaches images to those clones, and
returns the much narrower shape declared at `:467-478`.

Consequences:

- `clinical.patients[0].exams` still references the original image-free exam.
- `combined.exams[0]` is a different object with images but no owning patient.
- `image_tables.rois` must be retained separately.
- Patient histories remain on another set of Patient instances.
- Procedure, pathology, and association collections are absent from the
  combined object.
- The combined object's `build_issues` contains reconciliation issues only, so
  it can appear clean while upstream clinical or image construction contains
  errors.

This defeats the main benefit of an object graph: navigation and progressive
enrichment through stable identity.

### Critical: clinical construction is coupled to one wide child grain

`build_clinical_tables` accepts one stream and `_build_clinical_row` attempts to
project patient attributes, exam attributes, pathology, findings,
interpretations, procedures, and association links from each row
(`adapters/embed.py:889-1300`).

`_clinical_identity_issues` declares patient ID, accession, and finding number
as identities required to construct “clinical objects”
(`adapters/embed.py:3263-3308`). Missing patient or accession stops parent
construction. Missing finding is specially tolerated only after an
error-severity issue is recorded (`:1089-1183`).

The result is grain inversion:

- A lower-grain missing value determines whether a higher-grain object is
  valid.
- A normalized patient table cannot contribute patients.
- A normalized exam table cannot load cleanly.
- Separate tables must be widened or joined before ingestion, which risks row
  multiplication and alters repeated-row reconciliation.
- The parent classes have object-level `add_*` methods but no table-level
  ingestion endpoint.

Each adapter should emit objects at the grain it can establish. Parent creation
must not depend on child presence.

### Critical: real DataFrame missingness can manufacture identities

The main adapter's `_is_blank` recognizes only `None` and a short list of string
tokens, while `_string_value` converts other values with `str(value)` and does
not strip them (`adapters/embed.py:3360-3363`, `:3391-3394`).

An executable probe produced:

```text
input patient ID: float("nan")
result patients: ["nan"]
result issues: []
```

Likely related outcomes include `pd.NA` becoming `"<NA>"`, integral floating IDs
becoming strings such as `"1.0"`, and whitespace creating distinct IDs. The
history adapter independently implements safer numeric-NaN and identifier
normalization (`adapters/embed_history.py:167-188`), so the same source patient
can normalize differently across table paths.

This violates the repository's own strongest identity invariant: missing
identifiers must never manufacture shared clinical identities.

### High: DataFrame and filtered-table usage was designed but not delivered

The public builders accept `Iterable[Mapping[str, Any]]`, not a table protocol
(`adapters/embed.py:109`, `:889-899`, `:2004-2014`; history at
`adapters/embed_history.py:324-333`). A pandas DataFrame iterates column names,
so direct input fails.

Even after manual conversion, builders enumerate records and create new
call-relative row ordinals (`adapters/embed.py:962-969`, `:2049-2057`).
`SourceLocator` supports a stable `source_key`, but no public builder exposes a
key column or callback. Filtering or reordering a DataFrame therefore destroys
the original row address. Default random in-memory scopes make equivalent
rebuilds differ further unless callers know to provide a stable scope.

This matters because several conflict paths retain the first observed value.
Filtering and sorting can change both convenience values and canonical source
evidence without the caller choosing a policy.

### High: profile governance is a schema wall, not an extension seam

The same semantic field surface is declared repeatedly in at least five places:

1. `config/defaults.py`: default physical names.
2. `config/columns.py`: `EmbedColumnConfig` fields.
3. `config/profile_contracts.py`: clinical/image inventory tuples.
4. `config/profile_contracts.py`: accepted candidate aliases and coverage.
5. `adapters/embed.py`: `_ColumnAliases` and its translation.

`ProfileContract` requires exhaustive declarations for all governed concepts,
even irrelevant ones (`config/profile_contracts.py:308-367`). Unknown profiles
require a complete caller-supplied contract (`:659-699`), and the contract's
physical fields must exactly equal the candidates implied by the column config
(`:702-722`).

As a result, this intuitive call fails before reading data:

```python
build_clinical_tables(
    rows,
    columns=EmbedColumnConfig(patient_id="custom_id"),
)
```

Tests need a 78-physical-line test-only helper to make custom mappings
manageable (`tests/unit/profile_contract_support.py`). A new source field such
as `derived_image_type` touched ten files in its implementation commit. Adding
the two auxiliary history tables produced 822 runtime-line additions across two
commits, including 753 lines in new dedicated modules, and created a new
disconnected result rather than plugging into a generic adapter seam.

Full catalog governance may be useful for a dataset-maintenance validation job,
but it should wrap ordinary construction as an opt-in validator. It should not
be the price of renaming a column or adding a project-specific table.

### High: workflow-specific functionality is installed across shared layers

The workflow boundary is wider than the `workflows/` directory suggests.

- ROI transfer is 439 lines but its result contract lives in the shared
  `audit/results.py` module.
- Finding-to-ROI mapping is distributed across finding localization, ROI
  localization, matching, ROI groups, MagView normalization, anatomy/geometry,
  and audit result types.
- `workflows/finding_localization.py:8` imports the MagView adapter directly, so
  a supposedly source-neutral workflow depends on one source system.
- `audit/results.py:19` imports ROI provenance, so supposedly generic audit
  infrastructure is workflow/domain aware.
- `RoiGroup` is exported as general imaging API although its runtime use is the
  matching workflow.
- Importing `embed_toolkit.workflows` eagerly imports every bundled workflow and
  most runtime modules.

The workflow files use service composition rather than subclassing the domain
objects, which is consistent with the historical plan and is a reasonable
choice. The failure is packaging and dependency direction: the workflows are
not removable, self-contained examples because their support types and source
assumptions are spread across the installed framework.

For this project, “self-contained” should mean:

- a generic workflow imports only stable public core objects, while an
  explicitly source-labeled recipe may also call the package's supported source
  facade one way;
- its configuration and result types live beside the workflow;
- it accepts already-normalized domain values unless source normalization is an
  honest part of the labeled recipe;
- deleting the workflow and its tests changes no core file or public core
  export.

### High: core objects carry source-specific and governance-specific burdens

Examples include:

- `Finding` sits in the intended reusable clinical layer but hard-codes the
  EMBED `-9` sentinel into its record type
  (`clinical/findings.py:16-20`, `:106-113`).
- `Finding.merge_observation` mutates an ingestion-specific
  `metadata["source_row_count"]` counter (`:146-172`).
- `MammogramImage` cannot be manually constructed without a non-empty list of
  `SourceLocator` objects (`imaging/images.py:18-51`).
- ROI construction requires a scoped locator, source provenance object, and
  source ledger even for a researcher creating a simple box manually
  (`imaging/rois.py`).
- `clinical/attributes.py` uses 409 lines to model only two patient attributes
  and two exam attributes, and imports build-policy/provenance machinery.
- The clinical Exam directly owns a concrete `MammogramImage`, so importing the
  clinical aggregate surface also pulls in imaging.

Plain geometry and domain values should not require users to manufacture audit
infrastructure. Manual image/ROI construction may use an image-scoped identity
without provenance or accept an explicit caller reference, while graph table
ingestion continues to require complete source evidence.

### High: duplicate handling is safe only inside the current builders

The public low-level aggregate methods silently return an existing object and
discard the incoming object's contents:

- `Patient.add_exam`: `clinical/patients.py:69-78`.
- `Cohort.add_patient`: `clinical/cohorts.py:31-36`.
- `Exam.add_image`: `clinical/exams.py:191-200`.
- `BreastSide.add_finding` and `add_image`: `clinical/exams.py:42-66`.

This means the obvious manual attempt to combine a clinical Patient with a
history-only Patient loses one side's content. Composition behavior is also
inconsistent: `Exam.add_finding` merges, while neighboring methods discard.

One graph registry should own all upsert semantics. A duplicate should be
idempotent, explicitly merged, or reported as a conflict—never silently
ignored based on which public method the user happened to call.

### High: the central adapter is both a change and memory hotspot

`adapters/embed.py` combines:

- patient and exam construction;
- patient and exam attribute reconciliation;
- findings, interpretations, anatomy normalization;
- procedure and pathology projection;
- image and ROI parsing;
- source ledgers and build issues;
- clinical/image reconciliation;
- clone-based graph assembly;
- candidate image projection;
- scalar, list, date, identifier, and null normalization.

Splitting it by helper category would only spread the coupling. Grain-specific
source adapters should emit into one generic registry instead.

The adapter also copies every complete raw row into a `SourceOccurrence`, and
the image path temporarily retains full row dictionaries before copying them
into occurrences. For large research tables, mandatory full raw-row retention
has a real memory cost. Source addressability should not require retaining every
field by default; raw retention should be a deliberate policy.

### Medium: workflow typing is erased and reconstructed

Typed `AnatomicalPosition` objects exist, but `LocalizationResult` stores
positions as generic JSON mappings (`audit/results.py:110-137`). Finding and ROI
localizers emit different mapping shapes, and the matcher reparses those maps
through private context and extraction helpers
(`workflows/finding_roi_matching.py:376-445`, `:598-622`).

Serialization is occurring too early. Workflows should exchange typed values
and serialize only at the export boundary. This would remove validation and
reparsing code while making extensions easier to type and test.

### Medium: public API and documentation do not carry the product

This is intentionally a library with no CLI, API server, persistence layer, or
job runner. That makes its Python API and examples the entire product surface.

At the reviewed baseline:

- `embed_toolkit` exports only `__version__`.
- Users need deep adapter imports.
- The README's only construction example builds images from an undefined
  `rows` value.
- There is no installation example, patient/exam example, DataFrame example,
  complete graph traversal, history composition, or end-to-end workflow.
- Tests modify `sys.path` directly rather than testing a built wheel.
- `pyproject.toml` has no dev/test dependency group or configured lint, typing,
  coverage, or build verification.
- Integration and fixture directories contain only `.gitkeep`.

A broad internal API plus a nearly empty high-level API is the wrong balance for
a framework intended to save researchers time.

### Medium: code hygiene shows unfinished migration boundaries

Concrete examples:

- `_to_plain` is a private serializer in `clinical/procedures.py` imported by
  patients, exams, findings, cohorts, and adapters.
- There are three overlapping serialization policies: `_to_plain`, provenance
  `_json_ready`, and strict audit serialization.
- Unused private helpers remain in `adapters/embed.py`, including
  `_required_string`, `_indexed_value`, `_optional_int`, and `_optional_float`.
- Singleton ROI group identifiers are implemented independently in
  `imaging/roi_groups.py` and `workflows/finding_roi_matching.py`.
- `EmbedColumnConfig` exposes `required_*_columns` helpers that runtime ingestion
  does not use for schema reporting.
- Default config still contains non-empty `PLACEHOLDER_*` field names while its
  dataclass forbids an absent/`None` mapping.
- `INTERNAL_V1C_PROFILE = INTERNAL_V2_PROFILE` conflates an artifact/profile
  name with the underlying contract and deserves a naming/modeling review; it
  should not be deleted blindly as though it were only an API alias.
- Legacy BI-RADS values intentionally represent discontinued source values.
  Their retention belongs in a source-meaning review, not a generic
  compatibility cleanup.
- `temp/` sits at repository root with 1,293 lines of reference implementation.
- A completed governing plan still says strict construction is the default,
  while runtime and README use fail-soft audit mode.

None of these is the main architectural defect, but together they obscure the
active contract and increase the cost of understanding changes.

## Correctness gains that should be preserved

The recovery should not undo the valuable work that led to the current
implementation. In particular, retain these semantic invariants:

1. Blank or missing source identifiers never become shared synthetic domain
   identities.
2. Source-row multiplicity is not assumed to be clinical-object multiplicity.
3. Patient/exam, exam/side, exam/image, and image/ROI containment remain
   distinct from inferred attribution links.
4. Finding-to-image and finding-to-ROI relationships are not presented as
   source ground truth when they are only candidates or algorithmic inference.
5. Bilateral findings can project to unilateral sides without manufacturing a
   third breast-side identity.
6. ROI identity remains image-scoped; DBT frame and derivation provenance is
   not silently lost.
7. Clinical/image patient conflicts remain visible and cannot silently attach.
8. Unsupported or ambiguous rows can remain inspectable without manufacturing
   unsafe domain objects.
9. Fail-soft loading remains available for curation, with explicit strict mode
   for validation jobs.
10. Temporal endpoints with different meanings are not fallback-coalesced.
11. Row-level pathology diagnosis (including severity and documentation date)
    remains distinct from slot-level pathology observations. Parent identity
    failure must not erase either kind of evidence.

The existing test suite contains useful specifications for these behaviors.
Tests should be migrated according to semantic value, not deleted merely
because they cover old classes.

## Recommended target boundary

### Keep in the small framework core

- `Patient`, `Exam`, `BreastSide`, `Finding`, `MammogramImage`, and
  `RegionOfInterest`, plus the plain `Box` geometry value needed to describe a
  region.
- Small records required to traverse those grains: interpretations, patient
  histories, procedures, pathology diagnoses/observations, attribution links,
  and unresolved references. These are graph data, not source adapters or
  workflow services.
- Basic mammography primitives: laterality, view position, modality, and the
  smallest geometry values required by core objects.
- One canonical `DatasetGraph` identity registry with explicit containment and
  unresolved relationship records.
- One small `SourceRef`, `Issue`, and invocation-scoped `LoadReport`.
- One small table-like record iterator at the ingestion boundary.
- One narrow transactional contribution/upsert surface for downstream source
  loaders targeting the existing graph grains.
- Deterministic graph traversal and a single serialization policy.

`Cohort` was deferred from the replacement core because no concrete loading and
traversal story appeared. It was an analytic grouping rather than a necessary
clinical hierarchy level and was deleted instead of migrated automatically.

### Keep in EMBED source adapters

- MagView column meanings and code normalization.
- EMBED `-9` and other dataset-specific sentinels.
- Internal V2/V1c image and ROI parsing.
- HormoneHist and ProcHist vocabularies.
- Source-specific missing-side behavior.
- Exact MESH mapping once the source name and grain are confirmed.
- Optional strict profile validation for maintainers.

### Move into self-contained examples or recipes

- ROI transfer and its relationship/result/evidence types.
- Finding localization, ROI localization, ROI grouping, and finding-to-ROI
  matching.
- Patch extraction.
- Mammogram visualization.
- Algorithm-specific audit/export models.
- Alignment or BI-RADS normalization that is not required by any retained core
  construction story.

“Example” should have an operational meaning: by default these are repo-only,
self-contained recipe bundles under `examples/`, outside the installed base
package. A genuinely simple recipe can remain one file; matching may reasonably
use several local modules. A recipe should become an optional package or extra
only after a real reuse case justifies a supported API. None may be imported by
the base package or required to construct the graph. Patch extraction,
visualization, alignment, and any BI-RADS normalization should first pass a
retention review; moving unused code is not simplification.

### Delete after migration or explicit retention review

- `EmbedClinicalTables`, `EmbedImageTables`, and
  `EmbedClinicalImageGraph` once the canonical graph is live.
- Clone-based assembly and duplicate flattened collections.
- Mandatory profile/capability/coverage machinery on the ordinary load path.
- Generic audit wrappers with no remaining independent consumer.
- Unused helper functions, duplicate serializers, and placeholder column
  declarations. Profile names and legacy source vocabularies require a
  source-meaning review before removal.
- `temp/` reference code after extracting any fixture or documentation evidence
  still needed.
- Public modules that have no current user story, runtime consumer, or explicit
  near-term commitment.

Moving files without reducing dependency fan-out is not sufficient. A workflow
is isolated only when core can be tested, imported, and used after that workflow
is physically removed.

## Target construction model

Names below are illustrative; the behavioral contract matters more than the
final naming.

### One authoritative public loader

```python
from embed_toolkit import load_embed

report = load_embed(
    patients=patient_df,               # every table is optional
    exams=exam_df,
    findings=finding_df,
    images=image_metadata_df,
    rois=roi_df,
    hormone_history=hormone_df,
    procedure_history=procedure_history_df,
    procedures=procedure_df,
    pathology=pathology_df,
    magview=wide_magview_df,            # optional wide-table convenience
    source_scope="curation-2026-08",
    identity_namespace="embed-release-2",
    source_keys={
        "patients": "source_row_id",
        "findings": lambda row: (row["accession"], row["finding_number"]),
    },
    columns={
        "patients": {"patient_id": "custom_patient_id"},
        "exams": {
            "accession": "custom_accession",
            "exam_description": None,
        },
    },
    mode="audit",                        # fail-soft curation default
    retain_raw=False,                    # source address + used/issue fields
)

graph = report.graph
exam = graph.exam("ACC-123")
patient = graph.patient("P-456")

for issue in report.issues:             # issues from this invocation
    print(issue.code, issue.source)
```

The same call works with any subset of arguments, including none; no empty
placeholder table is required. `patients`, `exams`, `findings`, `images`,
`rois`, histories, procedures, and pathology are explicit grain inputs.
`magview` is a convenience for a known wide source that may emit several of
those grains. If an explicit grain table and `magview` both contribute the same
fact, both observations enter the ordinary source/conflict machinery; neither
silently overrides the other. `mode="strict"` is the explicit all-or-nothing
alternative for validation jobs.

Do not publish parallel `Patient.from_tables`, `Exam.from_tables`,
`load_patients`, or `load_exams` facades initially. Researchers choose their
working level through `graph.patients`, `graph.exams`, `graph.images`,
`graph.rois`, and keyed lookups over those same read-only views. Thin class
conveniences can be considered after actual use shows that one loader plus
graph lookup is insufficient. This provides patient- or exam-oriented use
without teaching source columns or DataFrame behavior to domain classes.

### Incremental enrichment

```python
from embed_toolkit import DatasetGraph, load_embed

graph = DatasetGraph(identity_namespace="embed-release-2")

history_report = load_embed(hormone_history=hormone_df, into=graph)
clinical_report = load_embed(findings=finding_df, into=graph)
image_report = load_embed(images=image_metadata_df, into=graph)

assert history_report.graph is graph
```

All three calls resolve through the same patient, exam, image, ROI, and link
indexes. Loading in another order produces an equivalent graph. The report's
issues are those relevant to that invocation; `graph.issues` is the cumulative,
deduplicated audit view. Reloading the same source contribution idempotently
must not duplicate objects or cumulative issue records, although the new report
may reference an existing issue relevant to the replay.

Graph collections should be read-only views. All mutation runs through a
small supported graph transaction/upsert surface so indexes cannot become
stale. In strict mode, any rejected contribution rolls back the complete
invocation. In audit mode, the transaction commits only independently safe
contributions and reports the rest. Mode and raw retention are invocation
policies; they do not mutate graph-wide identity configuration.

### Minimum identities by grain

| Contribution | Minimum safe identity | Optional relationships |
|---|---|---|
| Patient | patient ID | source attributes |
| Exam | accession | patient link |
| Breast side | accession + unilateral side | clinical accession establishes its Exam |
| Finding | accession + finding number | patient evidence, side, interpretation, procedure links |
| Image | image ID or governed image key | accession, patient, side |
| ROI | image key + source ROI key/ordinal | frames, annotation source, grouping |
| Patient history | patient ID + source key | accession context |
| Procedure | patient ID + performed date + procedure type + laterality | exam and finding links |
| Pathology diagnosis | source row reference | diagnosis, severity, documentation date |
| Pathology observation | source row reference + pathology slot | patient/exam/side/finding/procedure attribution |

A clinical grain that carries its own minimum identity can create that node
even when its parent is absent: an accession is a valid Exam, with an unresolved
patient edge if necessary. Reference-only patient or accession evidence on an
image row does not create a Patient or Exam node. It creates an unresolved edge,
so `graph.patient(...)` or `graph.exam(...)` returns no object and root
collections contain no half-resolved clinical node. Later clinical evidence
creates the canonical node and resolves the edge; conflicting ownership remains
unresolved and visible. A missing identifier never creates a sentinel node.

The procedure identity above records the current scientific rule. Making
patient identity optional would be a separate domain decision, not an incidental
effect of generic graph loading.

### Table-like normalization

Start with one small internal `iter_records(table, key=...)` boundary that
recognizes only the inputs required by the primary user stories:

- `Iterable[Mapping]` directly;
- pandas DataFrames with index capture;
- `None` and empty inputs.

Polars and Arrow support should wait for a real consumer. Pandas can be a
development/test dependency and an optional runtime integration rather than a
base dependency.

The boundary yields `(source_key, mapping)` records. Each graph owns a stable
default materialization `source_scope` for its lifetime; reproducible rebuilds
require the caller to supply a stable scope. `source_table` is inferred from the
loader argument, and callers select per-table keys with `source_keys=` using a
column name or callback. The exact identifying fields of `SourceRef` are
`(source_scope, source_table, canonical_typed_source_key)`; any URI, display
label, or diagnostic ordinal is non-identifying. Equal keys in different tables
never collide.

A canonical source key is a tagged immutable scalar or recursively tagged
tuple. NumPy scalars normalize to their corresponding built-in semantic type,
but boolean, integer, floating, string, date/datetime, and tuple tags remain
distinct: `True` is not key `1`. Nulls, NaNs, and unsupported mutable values are
invalid. The tagged form, not Python's loose scalar equality, governs hashing
and serialized round trips.

A requested key that is missing, null, unusable, or duplicated produces a
structured issue rather than a silent stability claim. A meaningful unique
DataFrame index can be used automatically. A `RangeIndex` is only a positional,
one-materialization fallback: an exact replay under the same scope/table/order
can be idempotent, but chunked append or reordered/filtered replay requires a
stable caller key or a deliberately new source scope. Identical content at the
same positional address is defined as replay; if it represents distinct
physical evidence, the caller must give it a new scope or stable key. Different
content at that address conflicts. Duplicate indexes and MultiIndexes require
tested behavior rather than accidental tuple/string conversion.

`identity_namespace` is immutable graph metadata and is separate from
`source_scope`. One graph owns exactly one identity namespace. A load into an
existing graph must omit the namespace or match it; a mismatch is rejected
before mutation. Separate graphs are required for releases whose patient or
accession values must not merge, keeping unqualified `graph.patient(...)` and
`graph.exam(...)` lookups unambiguous.

### Missingness and conflict policy

The table boundary should own only shape-level concerns:

- safe enumeration of mappings;
- source-key extraction;
- generic scalar-null classification, including `pd.NA` values whose truth
  value is invalid.

Source/grain adapters should own semantic concerns: alias resolution,
identifier trimming, numeric-ID and leading-zero policy, source sentinels,
dates, and duplicate-alias diagnostics. Removing the global profile wall must
not collapse “column absent,” “present but null,” “unsupported,” and
“uninterpreted” into one state.

The default conflict behavior should be order-independent. Prefer preserving
all observations and leaving a convenience field unresolved when populated
values conflict. If a project wants `first`, `last`, or another coalescing rule,
that is an explicit policy recorded in the load report. “All observations”
means supported semantic contributions emitted by the adapter, not every
unknown cell in a wide source row.

`SourceRef` identifies a physical source row, not every semantic fact emitted
from it. Internally, each contribution is addressed by
`(SourceRef, grain_or_concept, slot)`, allowing one MagView row to contribute a
patient, exam, finding, procedure, diagnosis, and multiple pathology slots
without collision. Source conflict rules apply to that contribution address:

- same address, same normalized content: idempotent;
- same address, changed content: conflict, with no silent overwrite;
- distinct addresses, equal content: separate evidence for one semantic
  node.

### Provenance and memory

Retain a small `SourceRef`, normalized consumed values, and values needed to
explain an issue for every ingested contribution. Do not copy the complete raw
row by default. `retain_raw=True` is an explicit curation option when the
researcher wants lossless in-memory evidence. A `SourceRef` is an address, not a
resolver: with raw retention off, the caller owns the original DataFrame or
external source if later recovery is required. This is a deliberate clean break
that reduces memory and privacy exposure without inventing multiple retention
modes.

`Box` remains a plain source-free geometry value. A manually constructed ROI
retains an explicit image-scoped ROI key but may omit provenance; an optional
caller-supplied `SourceRef` is evidence, not its identity. A similar image
factory can make manual graph use ergonomic. Table ingestion must always supply
a `SourceRef`, so this does not weaken ingested provenance or ROI identity.

### Profile validation

Replace the ordinary five-layer schema wall with per-table partial field maps
local to each adapter. A simple rename or intentional optional-field unbinding
should be simple:

```python
load_embed(
    patients=patient_df,
    exams=exam_df,
    columns={
        "patients": {"patient_id": "custom_patient"},
        "exams": {
            "accession": "custom_accession",
            "exam_description": None,
        },
    },
)
```

If maintainers need exhaustive Internal V2 catalog conformance, expose it as a
separate, explicit validator around the same field meanings:

```python
from embed_toolkit.sources.embed.validation import validate_internal_v2

validation = validate_internal_v2(wide_magview_df, image_metadata_df)
```

The strict profile layer may retain capability and coverage declarations if a
real validation consumer uses them. Ordinary construction must not require
them. Unmapped physical fields do not become arbitrary domain attributes: with
`retain_raw=True` they remain in source evidence; otherwise they stay only in
the caller-owned input. They are ignored semantically, and the explicit
validator may report them when exact catalog conformance is desired.

### Extension seam without a framework inside the framework

Initially keep concrete grain/source loader functions internal and expose one
small transactional contribution surface for the existing core grains. A plain
downstream loader accepts its table and a graph transaction, then calls typed
upserts such as Patient, Exam, or Finding contributions with source addresses
and issues. A test adapter using only the installed wheel's public API must be
able to load a new source table into those existing grains without editing
core. Arbitrary new entity types are out of scope. Do not add an adapter
registry, `TableSpec`,
`SourceSpec`, or formal `Protocol` until at least two real downstream adapters
demonstrate the same stable need.

## Dependency direction

The target dependency rule should be simple enough to test statically:

```text
package-root convenience facade      --->  public core + EMBED source facade
repo recipes / generic workflows     --->  public core
EMBED source adapters                --->  public core
optional profile validation          --->  EMBED adapters + public core
explicitly MagView-labeled recipe    --->  package facade + public core

public core                           -X->  sources
public core                           -X->  recipes/workflows
```

The package root is a deliberately thin usability facade, so it may re-export
`load_embed` without making the source-neutral core depend on EMBED. It must not
eagerly import recipes or their optional dependencies.

Generic workflows consume normalized domain values and therefore do not import
MagView. An intentionally EMBED/MagView-specific recipe may call the supported
top-level `load_embed(magview=...)` facade; no broader public adapter module is
promised. The important constraints are one-way dependency, honest naming, and
physical removability. Core never knows that either kind of recipe exists.

## Historical phased implementation plan

The project permits clean API breaks and has no declared external consumers.
Use that freedom. Do not create a long-lived parallel v1/v2 architecture or
deprecation shim layer.

### Phase 0: write the contract and establish real package tests

Record the target API, source identity semantics, unresolved-reference policy,
issue ownership, raw-retention policy, and strict/audit transaction behavior as
a short governing decision. Add pandas to the development/test environment and
add a wheel-build/install smoke test now, so later slices are tested through the
actual package boundary.

Create a traceability map from current scientific tests to the replacement
journeys. Do not commit permanently failing tests: each acceptance test lands
with the vertical slice that makes it pass.

Acceptance gate:

- The package builds and imports from a clean wheel environment.
- Pandas fixtures can express nullable dtypes, filtered indexes, duplicate
  indexes, and MultiIndexes.
- Every high-value identity, pathology, ROI, and attribution invariant has an
  identified destination test.

### Phase 1: remove verified dead surface and clear shared typing noise

Delete low-risk, demonstrably unused helpers, eager aggregate exports, duplicate
serializers where behavior is already equivalent, and placeholder declarations
with no consumer. Review `temp/` evidence and optional visualization/alignment
utilities before migrating them. This phase is for making the active boundary
legible, not mechanically rearranging the monolith or deleting source
vocabularies whose meanings still matter.

Fix the shared `CoercibleEnum` return typing here so its cascade does not obscure
type errors introduced by the graph migration.

Acceptance gate:

- Search and tests demonstrate that each removal has no active consumer.
- Core/package imports become narrower without changing scientific behavior.
- No code needed by a planned vertical slice is churned merely to reduce LOC.
- The `CoercibleEnum` cascade no longer masks typing results.

### Phase 2: land the table plus Patient/Exam vertical slice

In one feature slice, implement the small `iter_records` boundary, typed
`SourceRef` rules, `DatasetGraph` Patient/Exam indexes, staged transactions,
and the Patient/Exam portion of `load_embed`. Support direct pandas DataFrames,
iterable mappings, partial per-table column maps, `source_keys`,
`identity_namespace`, `source_scope`, `mode`, `retain_raw`, and `into`.

The old Patient/Exam logic cannot be cleanly deleted yet because it is embedded
in the wide builder still needed for later grains. Keep that builder only as an
unreleased internal oracle/bridge on the feature branch; any bridge must
delegate parent upserts to the new graph instead of creating another registry.
Delete it with the final cohesive clinical slice. Do not release or document two
competing construction APIs.

Acceptance gate:

- Patient-only and exam-only DataFrames load without child-grain errors.
- Filtered keys, nullable scalars, duplicate/MultiIndex keys, ordinal chunking,
  exact replay, and reordered replay have explicit tested behavior.
- Tagged key equality distinguishes booleans from integers, normalizes NumPy
  scalars deliberately, and survives serialization round trips.
- Namespace mismatch on `into=` fails before mutation.
- Same-contribution replay is idempotent; changed same-address payloads
  conflict; equal values from distinct source rows remain distinct evidence.
- Strict failure is atomic; audit mode commits only safe contributions.
- Graph collections are read-only and map-backed lookup/upsert is expected
  constant time.
- A representative scale/memory benchmark establishes the graph and
  raw-retention baseline before more grains propagate the design.
- The wheel smoke test exercises this slice.

### Phase 3: migrate remaining behavior as vertical slices

Use focused source/grain projections into the graph. A likely small layout is:

```text
sources/embed/magview.py
sources/embed/images.py
sources/embed/rois.py
sources/embed/histories.py
sources/embed/columns.py
sources/embed/validation.py    # only if strict catalog validation is retained
```

Land these slices in order:

1. Findings, interpretations, and breast-side projection.
2. Images and ROIs, including image-scoped provenance and unresolved clinical
   references.
3. Hormone and procedure histories.
4. Procedures, pathology diagnoses/observations, and explicit attribution
   links.
5. Wide MagView convenience that emits the already-supported grains.

Each slice includes table extraction, graph upsert, source normalization, a
researcher-facing acceptance test, parity tests for retained invariants, and
deletion of the superseded parser/build-product path. Replace old structural
tests with semantically equivalent graph tests and update the traceability map.

Image loading resolves or records its parent references during the ordinary
transaction; there is no separate public “reconciliation” operation. A
pathology-only diagnosis and its slotted observations remain inspectable even
when their parent links cannot yet resolve.

Acceptance gate for every slice:

- Its table can load alone and can enrich a graph in any order.
- No adapter requires columns belonging to an unrelated grain.
- Image-derived clinical references create no Patient/Exam node, then resolve
  to the canonical node when qualifying clinical evidence arrives.
- Existing scientific semantics pass through the new graph before their old
  code is removed.
- The installed-wheel package test path remains green.

### Phase 4: retire build products and mandatory governance

Before publishing the replacement API, remove `EmbedClinicalTables`,
`EmbedImageTables`, `EmbedPatientHistoryTables`,
`EmbedClinicalImageGraph`, clone assembly, flattened duplicate collections,
and the remaining monolithic builder. Remove exact profile validation from
ordinary loading and eliminate stale inventories/exports after their source
meanings are represented in adapter tests and concise documentation.

Retain exhaustive Internal V2 validation only as the explicit maintainer
function described above and only if a concrete job consumes it. Decide whether
`Cohort` has a real graph story; otherwise remove it. Review legacy BI-RADS
vocabularies and V1c naming on meaning, not merely age.

Acceptance gate:

- There is one graph result and no clone-based assembly.
- No ordinary load constructs or validates a complete concept inventory.
- No old public builder or compatibility wrapper remains alongside
  `load_embed`.
- Adding one mapped field changes only its source/grain adapter, tests, and
  concise documentation.

### Phase 5: isolate or delete optional workflows

Review and handle one logical bundle per commit:

1. ROI transfer.
2. Finding localization, ROI localization, grouping, and matching.
3. Patch extraction.
4. Visualization and alignment.

Retained bundles become repo-only, self-contained recipes by default. Keep
their configuration, typed results, evidence, and serialization local unless a
source-neutral type has two active consumers. Generic recipes consume domain
values; an intentionally MagView-specific recipe may depend one-way on the
top-level source facade and must say so in its name. Delete bundles with no
current user story instead of moving them.

Move workflow-only `RoiGroup` and audit types beside matching, avoid eager
cross-imports, and collapse or delete generic audit machinery as its actual
consumers disappear.

Acceptance gate:

- Physically removing a recipe directory leaves core imports/tests green.
- Importing core imports no recipe; importing one recipe imports no unrelated
  recipe.
- No recipe-specific type appears in the core public API.

### Phase 6: publish the sole researcher-facing API

Bound the package-root `__all__` to `DatasetGraph`, `load_embed`, `LoadReport`,
`Issue`, `SourceRef`, `Patient`, `Exam`, `BreastSide`, `Finding`,
`MammogramImage`, `RegionOfInterest`, and `Box`. Specialist history, procedure,
pathology, interpretation, and link records remain available from focused
submodules rather than expanding the convenience facade.

The graph's transaction method is the narrow supported extension seam. Its
supported mutation vocabulary is limited to `upsert_patient`, `upsert_exam`,
`upsert_finding`, `upsert_image`, `upsert_roi`, `upsert_history`,
`upsert_procedure`, `upsert_pathology_diagnosis`,
`upsert_pathology_observation`, `add_link`, and `add_issue`; it has no arbitrary
entity registry. Document patient-only, exam-only, filtered multi-table,
incremental, issue-inspection, manual ROI, and downstream source-loader
examples. Use graph collections and keyed lookup rather than multiple
construction facades.

Acceptance gate:

- The common filtered MagView plus image-metadata path is a short, direct
  example and inspects `report.issues`.
- Patient, exam, image, and ROI collections are views over exactly the same
  graph.
- `report.issues` is invocation-scoped, `graph.issues` is cumulative and
  deduplicated, and replay appends no duplicate cumulative issue.
- Top-level package imports are sufficient and every repo quickstart executes
  against a built wheel without source-tree path injection.
- No recipe/audit leakage remains when the API is published.

### Phase 7: finish repository and quality cleanup

- Put the active package/project metadata at an obvious repository root or make
  `unified-system/` unambiguously intentional.
- Add installation guidance and retain only the governing architecture
  contract.
- Keep Ruff and the pragmatic mypy baseline configured, and reduce residual
  errors as migrated modules stabilize.
- Add a supported-Python matrix, coverage/quality commands, and regression
  gates around the scale/memory baseline established in Phase 2.
- Remove `temp/` after preserving any evidence found in Phase 1.
- Derive package version from one source.

Acceptance gate:

- Clean-environment wheel, DataFrame subset matrix, and one retained complete
  workflow all pass.
- Ruff and the configured typing gate pass.
- No tracked temporary implementation or contradictory governing plan remains.

## Global acceptance criteria

The recovery is complete only when all of these are true:

1. Any supported table subset can be loaded without manufacturing irrelevant
   columns or passing empty placeholders, including pathology-only evidence.
2. Patient, exam, image, and ROI roots are read-only views over one graph.
3. Direct filtered pandas DataFrames and iterable mappings work without manual
   record conversion.
4. Clinical, image, ROI, history, procedure, and pathology contributions
   converge on canonical identities without a second assembly operation.
5. Loading order does not change graph meaning.
6. Strict loading is all-or-nothing; audit loading commits only independently
   safe contributions.
7. Same-contribution replay is idempotent, changed content at the same
   `(SourceRef, grain/concept, slot)` conflicts, and distinct addresses remain
   distinct evidence even when values match.
8. Typed source keys survive filtering and stable rebuilds, are table-scoped,
   and are kept separate from the graph's identity namespace.
9. DataFrame nulls and whitespace cannot create domain identities; absent,
   present-null, unsupported, and uninterpreted remain distinguishable.
10. A simple column rename or optional-field unbinding needs only a per-table
    partial map.
11. Unknown research fields and `retain_raw` behavior have explicit,
    privacy-aware policies; a source address does not falsely promise that the
    framework can recover caller-owned data.
12. Unresolved relationships and conflicts remain inspectable. Image-derived
    references create no clinical node and resolve only when qualifying
    clinical evidence arrives.
13. Row-level pathology diagnosis and slot-level observations retain distinct
    identities and evidence even when attribution cannot resolve.
14. `report.issues` describes one invocation, `graph.issues` is cumulative and
    deduplicated, and idempotent replay appends no duplicate issue records.
15. Graph mutation cannot bypass the transaction/index invariants.
16. Core imports no source adapter or recipe; each retained recipe is physically
    removable without editing core.
17. A test adapter using only installed-wheel public imports loads a new source
    table into existing graph grains through the supported transaction surface,
    without editing core or requiring a registry/plugin framework.
18. Adding a built-in table normally touches one source/grain adapter, its
    tests, concise documentation, and one loader-facade wiring point—not the
    domain model and a global schema registry.
19. The sole top-level package construction API is small, documented, and
    supports both new and incremental graphs.
20. Repo examples executed against an installed wheel, without source-tree path
    injection, cover patient-only, exam-only, filtered multi-table
    construction, traversal, manual ROI creation, and issue inspection.
21. Scientific invariants retained from the current suite remain verified by a
    traceable replacement test matrix.
22. Map-backed lookup/upsert behaves as expected at representative scale, and a
    memory benchmark makes raw-retention cost visible.

Line count and large modules should be review signals, not hard completion
gates. Success is measured by one graph, import isolation, local extension
cost, researcher-path brevity, predictable performance/memory, and the absence
of mandatory machinery on simple paths. The installed runtime should become
materially smaller as a consequence of deleting duplicate construction paths
and optional code, not by targeting an arbitrary percentage.

## Historical recovery risks and controls

### Identity and count changes

Correct null and whitespace handling will remove manufactured identities such
as `"nan"`. Replacing first-row-wins resolution may change convenience values.

Control: publish before/after synthetic fixtures and count deltas; retain all
source observations so changes are explainable.

### Source locator changes

Preserving DataFrame indices or selected keys will change serialized locators
and synthetic ROI locator equality.

Control: treat this as a deliberate clean break, document the new source-key
contract, and keep positional fallback explicitly limited to exact
one-materialization replay. Chunking, filtering, or reordering requires a
stable key or deliberately new scope.

### Provenance regression during simplification

Moving evidence out of required domain constructors could accidentally make
ingested facts unauditable.

Control: require every table-adapter contribution to carry a `SourceRef`; keep
plain geometry source-free, distinguish manual image-scoped identity from
optional evidence, and test graph-to-source tracing for ingested facts.

### Temporary dual architecture

Adding a canonical graph beside four existing result products can increase
sprawl before it decreases.

Control: keep the migration on an unreleased feature branch. A temporary
internal oracle/bridge may exist only where the monolith prevents immediate
deletion, must delegate migrated grains to the new upserts, and is removed
before the sole API is published. Do not ship two construction systems or
compatibility aliases.

### MESH ambiguity

Before this review, the repository contained no implemented source adapter or
source contract named MESH. It is unclear whether MESH means the current V1c
`image_metadata` surface or a separate table.

Control: confirm the exact table name, grain, keys, and representative columns
before naming the production adapter. This does not block the generic graph and
table boundary.

### No private source data in the repository

Synthetic row tests cannot establish real nullable dtypes, sentinels, column
prevalence, or scale.

Control: use schema-only/deidentified fixtures for integration, then run a
maintainer validation job against representative internal data before retiring
the old path.

### Workflow behavior drift

Moving result types and normalization boundaries can change serialization even
when algorithms remain equivalent.

Control: preserve algorithm-level golden tests and explicitly version example
outputs. Do not preserve generic wrappers solely for byte-for-byte historical
serialization when there are no external consumers.

## Completed initial implementation milestone

The recovery began with the table normalization and canonical Patient/Exam
graph slice rather than workflow movement or a mechanical adapter split. The
first implementation milestone demonstrated this coherent path:

```python
report = load_embed(
    patients=patient_df,  # optional
    exams=exam_df,        # optional
    source_scope="curation-2026-08",
    identity_namespace="embed-release-2",
)
```

The implemented path provides direct DataFrame support, stable source keys,
correct null handling, and the same canonical Patient/Exam objects regardless
of which subset or order was loaded. It also demonstrates invocation-scoped
issue inspection, same-contribution idempotency, and strict rollback. Findings,
images, ROIs, histories, and the retained scientific safeguards now compose
through that root without recreating separate graphs.

That milestone established the central product promise. Subsequent recovery
work was judged by whether it made that path safer, clearer, or more extensible.
