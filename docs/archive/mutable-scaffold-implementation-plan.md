# Mutable EMBED scaffold: implementation plan

Status: W0–W9 implemented and locally qualified on 2026-09-09.
Qualifying runtime revision after review fixes: `664b4e2`; wheel version: `0.1.0`.
See [qualification evidence](mutable-scaffold-qualification.md) for results and limits.
The [completed implementation review](mutable-scaffold-review.md) is resolved.
Historical plan review: 2026-09-09 against `f55ecfe62a0e8de9ba2247299be65271e86228a2`.
Authority: [mutable scaffold target contract](../mutable-scaffold-contract.md).

The target requires replacing the graph's contribution-replay architecture with
a mutable object registry and semantic-grain loading. Preserve useful clinical
normalization, mammography primitives, and packaging; do not first repair the old
transaction or source-row identity architecture. Complete the public scaffold
contract before porting matching or transfer into separate repositories.

This plan distinguishes established requirements from proposed decisions. The
decisions below preserve the kickoff proposals. Their accepted resolutions are
recorded in the [API specification](../mutable-scaffold-api.md), including the
maintainer-approved initial registry identity mapping. This document supersedes
the implementation sequence in the September assessment for this work; historical
assessment results remain evidence about their reviewed revision.

## 1. Pre-cutover implementation and gaps (historical baseline)

Paths in the table are relative to `unified-system/src/embed_toolkit/`. Symbols
identify the reviewed code even after nearby line numbers change.

| Area | Current evidence | Required change |
|---|---|---|
| Registry and loading | `core/graph.py`: `GraphTransaction`, `_Contribution`, `_stage`, `_commit`; `sources/embed/loader.py`: `load_embed` accepts `audit`/`strict` | Remove transaction/replay as the public mutation and reload mechanism. Introduce semantic grouping, in-place refresh, and explicit merge. |
| Identity | `core/tables.py`: `_records_from_rows`; loader `_add_table_issues` requires a usable source key; `_stage` rejects changed payloads at a reused physical address | DataFrame indexes and optional diagnostic keys cannot determine object identity or admission. Preserve semantic identifiers through slices, resets, and reordered input. |
| Clinical structure | Patient exposes exams/findings; Exam exposes findings/images/sides. Procedure has no pathology children; Finding has no procedures. Pathology lives in graph registries keyed by `SourceRef`; loader `_clinical_targets` emits broad flat links | Expose actual procedure/pathology objects at supported clinical levels and descendant traversal. Keep reported histories distinct from performed procedures. |
| Attribution | `_resolve_links` checks target existence only; `_has_target` cannot resolve pathology targets. `_resolve_images` declines accession attachment on patient disagreement | Resolve both relationship endpoints, preserve accession-level attachment and conflicting identity claims, and keep missing endpoints pending. |
| Registry and linked exams | No mapping/loader for `cancer_outcome_registry_id` or `linkedaccession_anon` | Add patient-scoped registry entries and confirmed exam assignments, plus explicit exam links and deferred resolution. |
| Image identity | `sources/embed/columns.py` maps both image ID and SOP UID to `anon_dicom_path`; image `identity` includes mutable metadata | Separate mutable toolkit ID, source SOP UID, and location; normalize the documented path at the adapter boundary. |
| ROI loading | `_load_images` and `_load_rois` are independent. `_load_rois` derives keys from source row keys, with ordinal suffixes only for multiple boxes. Empty input emits no removal | Metadata projects images and ROIs by default. Use image-local collection positions; distinguish unavailable, malformed, and explicitly empty collections; replace addressed collections. |
| Mutation | Patient/Exam/Finding/Procedure/Image are mutable but their methods bypass registry indexes. ROI, pathology, histories, and interpretations are frozen | Provide one supported mutation/membership surface, standalone use, coherent rekeying, and mutable domain entities. |
| Movement and filtering | No graph registration, pop/detach, transfer, selection, partition, or clinical validation-result partition API | Implement single-container membership and extraction rules that distinguish containment from shared associations. |
| Validation | Geometry, confidence, image/frame restrictions, history plausibility, and pathology quality checks occur in constructors/adapters | Retain representation checks; move clinical/geometric quality rules to manually invoked validators. |
| Scale | `_resolve_exam` scans all patients. Commit rebuilds image/ROI/link memberships and histories; several conflict helpers scan all pending contributions. Tables are materialized repeatedly | Maintain parent and pending-target indexes; update touched identities; normalize/group once and support patient-independent construction. |
| Delivery | Wheel smoke exists; benchmark covers patient-only loading and lookup. README calls the old architecture governing | Replace incompatible tests/docs, expand multi-grain scale and installed-public-API checks, then qualify the cutover. |

Reusable foundations include accession/finding-number identity, the existing
procedure tuple, laterality and bilateral side traversal, MagView anatomy and
synthetic-negative normalization, inclusive-to-half-open ROI conversion, FFDM /
DBT / synthetic 2D modality vocabulary, partial-table support, and the wheel/CI
scaffolding. Reuse their meaning without preserving mandatory provenance or
ingestion-quality gates.

### Verification performed for this review

From `unified-system`, the following command returned **212 passed**, with three
importlib metadata deprecation warnings, on local Python 3.13. The wheel test and
other Python versions were not rerun. Passing these tests is a baseline, not
evidence of conformance to the new target.

```bash
.venv/bin/python -m pytest -q --ignore=tests/integration/test_wheel_smoke.py
```

Small synthetic probes using public APIs reproduced these current behaviors:

| Probe | Observed result |
|---|---|
| Load four patients in two two-row DataFrame subsets, resetting the second index | Only the first two patients remain; the second load reports two `source_contribution_conflict` issues. |
| Reload exam A with description `new` after `old`, using the same graph/default source scope | Python reference is preserved, but description remains `old` and the update conflicts. |
| Load metadata with a structurally valid EMBED path and one serialized ROI | Image ID and SOP UID both contain the full path; no ROI loads. |
| Load one ROI, then supply `ROI_coords='[]'` for that image | The old ROI remains. |
| Call `graph.patient('P').add_exam(Exam('B'))` | Patient traversal contains B; the graph exam registry does not. |

Static inspection additionally established the missing registry/link/partition
APIs and the scan patterns above. No private tables, live semantic MCP responses,
remote CI runs, or real pixel data were inspected. Registry semantics here come
from the target contract; its physical table binding remains a delivery input.

## 2. Decisions to settle before dependent implementation

Record these in a short public API specification with examples and expected
outcomes. Accept or revise the recommendations explicitly; do not let individual
implementers choose incompatible defaults. D1–D7 are release-contract decisions.
D8 addresses additional identity gaps exposed by the current code.

| ID | Proposed rule | Affected work |
|---|---|---|
| D1: conflicting exam ownership | Keep one exam per accession and an inspectable set of asserted patient IDs. A single unambiguous claim can establish ownership; contradictory claims leave ownership unresolved until an explicit caller resolver/assignment chooses it. Continue attaching accession-addressed images/procedures/pathology. Preserve the conflict after explicit resolution for optional validation. Apply the same rule across arrival orders; neither first nor last row owns the exam by accident. | W1, W2, W3, W5 |
| D2: refresh and extensions | Refresh resets adapter-managed fields of each supplied object grain to documented defaults, then applies the grouped incoming snapshot. Both absent mapped fields and explicit null reset those fields; unbound fields are outside that adapter's managed set. Preserve subclass type, consumer attributes, and consumer `metadata`. Never call `__init__` on a live object to refresh it. Identity, ownership, child collections, and source associations have separate rules. | W1, W3, W4 |
| D3: incoming conflicts and merge | Within one load, combine complementary populated values; equal values deduplicate. Conflicting populated scalar values become unknown plus a compact conflict diagnostic, unless an explicit resolver is supplied. Merge applies supplied non-null fields over existing values, preserving absent/null fields; an explicit mutation can clear a field. This differs from refresh. Simultaneous wide and narrow tables use the same per-grain grouping, with no hidden table precedence. | W3, W4, W5 |
| D4: identity mutation | Ordinary attributes are editable in place. Registered identifiers and relationship changes go through `update`/`rekey`/attach/detach operations; object convenience methods delegate to the owning graph. Expose child sequences as views so direct list edits cannot desynchronize indexes. Standalone objects use equivalent local operations. Detect key collisions before changing that operation's membership; do not implement graph-wide rollback. | W1, W2 |
| D5: image and ROI addressing | Use `image_id` for mutable toolkit identity, `source_sop_instance_uid` for original identity, and `source_paths` for location aliases. Initial source-image ID defaults to the normalized SOP UID within a graph namespace. Explicit UID wins over a conflicting path-derived UID, with a diagnostic retaining both claims; do not automatically alias a conflicting derived UID. ROI source address is `(anon_dicom_path, collection_position)`, including position 0 for singleton collections. Manual ROIs may use explicit image-local IDs. | W1, W4 |
| D6: shared descendants and boundaries | Within one graph, multiple findings/exams may reference one procedure/pathology object. Pop moves exclusive containment descendants. If an associated descendant is also needed by a retained subtree, preserve the original there and copy it for the extracted subtree, preserving semantic identity and recording the copy boundary. Linked exams never expand the extraction. Crossing relationships retain semantic endpoint references, not owning foreign objects. Make this `copy_shared` boundary rule public. | W2, W6 |
| D7: partition semantics | Default owning partitions are independent copies; the source remains intact. Copy a shared object once per output graph, never share mutable instances across outputs. Lower-level outputs include copied ancestor context shells with only selected branches. Offer non-owning selection separately. Destructive extraction is handled by pop/register, so a second destructive partition mode is unnecessary for the initial contract. | W6, W7 |
| D8: pathology and retained histories | Prefer actual supplied record IDs. Define an explicit semantic fallback for MagView pathology and an explicit rule for histories before replacing their row-addressed registries. Do not deduplicate clinical events merely because diagnosis text or other payloads are equal, and do not invent row-ordinal identities. The detailed starting proposal and unresolved cases are below. | W1, W3, W5 |

D1 needs a clear distinction between an exam's assigned owner and source IDs on
associated objects. Resolving owner P must not rewrite a registry key `(Q, id)`
into `(P, id)` or silently change a procedure's source identity. Patient-level
traversal follows the selected exam owner and may expose conflicting associated
facts; optional validation reports them. Unowned exams remain usable through the
dataset registry and can acquire ownership later.

For D5, parse the trailing `cohortN/patient/study/series/SOP.dcm` structure without
opening a DICOM. Check sufficient structure and nonempty components, keep the
full path separately, and report unparseable paths without blocking projections
that have sufficient explicit identity. A source-SOP lookup must distinguish the
original image from derivatives sharing that SOP: metadata reloads refresh the
registered source image even after its toolkit ID changes. Derivatives require
an explicit toolkit ID and an optional simple derivation reference. Rekeying must
update toolkit ROI indexes while source-path/position lookup still resolves the
current source collection. No identity inference from equal boxes is allowed.

For D8, start by evaluating a MagView pathology bundle key composed of the
clinical attachment identity and supplied report identity/documentation date;
descriptor slots belong inside that bundle. Repeated finding rows contributing
the same identified bundle update one object; descriptor order and duplicate
slot values are preserved. Validate that key against adapter fixtures before
adopting it. Missing/ambiguous discriminators must produce accessible unresolved
records or a request for an explicit record key, not guessed event equivalence.
These records must still load as useful facts without a usable DataFrame index.
For history data without an event ID, specify patient-scoped reported facts and
their refresh grain, or require a semantic key for event-level identity; do not
continue claiming that physical row identity is clinical identity. This is a
bounded schema decision, not a reason to restore an evidence ledger.

Registry entries have a settled logical key `(empi_anon, registry_id)`. The
maintainer supplied `empi_anon` and `cancer_registry_id` for initial implementation,
explicitly deferring other payload values; see the API specification. The original
W5 qualification requirement follows. W5 must
bind the physical registry key and payload columns using an authoritative schema
or supplied adapter mapping. Synthetic mappings can verify the generic adapter
first; the real EMBED binding cannot be declared complete without that evidence.

## 3. Public API shape and invariants

The following names are proposed; W0 finalizes signatures before implementation.

```python
graph = DatasetGraph()
graph.register(patient)                 # register a standalone clinical subtree
graph.update(exam, description="reviewed")
graph.rekey(image, image_id="processed-1")
detached = graph.pop(exam, boundary="copy_shared")
other.register(detached)                # original exclusive objects move membership

load_embed(magview=rows, images=metadata, into=graph)  # refresh; images + ROIs
load_embed(exams=corrections, into=graph, mode="merge")

selection = graph.select(level="exam", predicate=lambda exam: exam.exam_date is None)
parts = graph.partition(level="exam", key=lambda exam: exam.description)
result = validate(patient)              # explicit, read-only quality inspection
valid, invalid = graph.partition_by_validation(level="exam", validator=validate)
```

- One object has zero or one owning graph. Registering an object owned elsewhere
  moves it under the same boundary policy; it cannot leave a second owner.
  Registering the same instance twice is idempotent. Registering a distinct
  instance with an occupied semantic key reports a collision, leaving the object
  available for explicit refresh/merge or rekeying.
- `Patient.exams/findings/procedures/pathology`, `Exam.findings/images/procedures/
  pathology/linked_exams`, `Finding.procedures/pathology`, `Procedure.pathology`,
  and `Image.rois` expose actual objects. Shared descendant traversal deduplicates
  by graph identity. Exam registry pathology is also distinguishable directly.
  Side traversal groups findings/images without asserting correspondence.
- Attach/detach changes a relationship; pop unregisters a selected subtree.
  Removing a shared association does not delete the shared object. Document what
  remains registered when its final association is detached. An exam or image
  with a missing parent remains addressable without fabricated clinical facts.
- An explicit linked-accession reference sets an accessible link indication even
  while its target is absent. Resolved links are traversable in both directions;
  reciprocal rows deduplicate. Cycles do not affect containment or serialization.
- Refresh is grouped over the entire logical operation, not each physical row.
  A finding with two procedure rows retains both attachments. Absent child grains
  preserve descendants. Default child-grain upserts do not prune children omitted
  from a subset; pruning requires an explicit removal/collection operation.
- ROI collections are the specified replacement exception, including under
  scalar merge mode. Missing/null/unavailable ROI input preserves the collection;
  an explicit empty sequence clears it. Malformed replacement input reports a
  construction failure and leaves that image's previous collection intact.
  Other usable image metadata and other images still load. Within a load, two
  different collections for one source image are a conflict requiring resolution,
  never last-row-wins. An explicit `rois=` projection overrides automatic metadata
  ROI projection for the addressed images; document this single precedence rule.
- Individual ROI edits preserve the ROI's Python reference. Collection replacement
  unregisters removed annotations and may replace every ROI reference. Old
  collection positions are not durable references to lesions. Proposed behavior:
  replacement covers the image's entire registered collection, including manually
  added ROIs; consumers can pop/save annotations and explicitly re-register them.
  Confirm this consequence in W0 and show it in the public reload examples.
- Parsing outcomes are local and informative. No load promises atomic rollback;
  successfully constructed unrelated objects remain usable after an error.
  A small invocation report describes usable/skipped projections and construction
  issues, without claiming workflow coverage or dataset completeness.

## 4. Work packages and dependency order

Each work package has a reviewable exit gate. Packages are not single commits:
split work into coherent module/API/test changes, use selective staging and
`type(scope): subject` messages with explanatory bodies, and verify each completed
unit with `git log --oneline -3`, as required by `AGENTS.md`.

### W0 — Finalize the API decisions and acceptance map

**Depends on:** this review. **Owns:** the target/API documentation and test plan.

Resolve D1–D8, naming, refresh managed-field lists, null/absent/empty semantics,
ownership vs. source identity, key-collision behavior, shared-copy behavior, and
extension handling. Inventory every currently exported entity/value type and
state which are mutable domain objects versus replaceable immutable value/key
types. If interpretation/history/landmark objects remain domain objects, include
their updates; `frozen=True` must not silently exempt them from the target.

Map existing tests to retain, replace, move to optional validation, or retire.
Publish a small set of API examples with expected identities and relationships.
Do not mark the target implemented at this stage.

**Exit:** no dependent implementer needs to invent one of the open semantics;
pathology/history unresolved cases have an explicit representation policy and
the registry binding has a named evidence requirement.

### W1 — Define mutable entities, identities, and clinical relationships

**Depends on:** W0. **Owns:** `clinical/*`, `imaging/images.py`, `imaging/rois.py`,
focused exports, and entity-contract tests.

Make clinical entities and ROIs support in-place updates with optional diagnostic
source information. Add procedure/pathology child associations, actual registry
entry objects, linked-exam references, direct/descendant traversal, and source vs.
toolkit image identity fields. Keep history, interpretation, and pathology meanings
distinct. Remove required old locator/provenance construction paths from domain
objects; immutable key/geometry values may be replaced during an entity update.
Keep source-specific path/ROI conversion in adapters rather than domain classes.

**Exit:** construct and edit a patient → exam → finding → procedure → pathology
tree and exam → image → ROI tree without a graph or `SourceRef`; subclasses retain
custom attributes; sharing and linked cycles traverse/serialize without recursion
or duplicate descendant output. No finding–image or cross-image ROI edge appears
from shared exam/side scope.

### W2 — Replace transaction infrastructure with coherent membership operations

**Depends on:** W1. **Owns:** `core/graph.py`, small membership/index helpers if
needed, and mutation-contract tests. One implementation owner should coordinate
this shared file throughout W2–W5.

Implement register, attach/detach, update, rekey, pop, and cross-container movement.
Use semantic dictionaries, reverse parent/association indexes, and pending
references keyed by missing target. Resolve only affected endpoints. Wire entity
convenience methods to this surface so standalone and registered use agree.
Apply D1 and D6; handle collision checks locally before changing a single operation.

Retire `GraphTransaction`, `_Contribution`, observation replay, and global
membership rebuilds. The loader switches to the new API in W3; an internal
migration branch may temporarily carry both implementations, but the delivered
package must not expose two competing mutation systems or compatibility wrappers.

**Exit:** mutations and identifier changes keep traversal, parent links, indexes,
source image lookups, ROI keys, and pending references coherent. Pop/register
preserves references to exclusive descendants; shared copies and crossing edges
obey D6. A failed collision does not lose an object from its original graph.

### W3 — Rebuild semantic-grain loading and refresh/merge

**Depends on:** W2. **Owns:** `core/tables.py`, `sources/embed/loader.py`, column
maps, clinical normalizers, and loading-contract tests.

Normalize each input once, retain field-presence information, project optional
grains, group by semantic identity, and update each object once per operation.
Integrate narrow tables and wide MagView projections before resolving conflicts.
Keep optional row diagnostics separate from identity/admission. Use the W0
managed-field reset specification and preserve consumer fields and descendants.
Ensure parent identity establishment from a child row is an ensure/attach action,
not a parent refresh. Adapt retained history handling to the D8 rule.

Replace `audit`/`strict` ingestion modes with refresh/merge semantics; remove
`BuildPolicy` if no independent supported use remains. Keep a compact construction
report. Distinguish missing columns for one projection from failure of the whole
table. Retire ledger-specific tests as their replacement contract checks land.

**Exit:** rows with RangeIndex, duplicate/nonunique indexes, MultiIndex, reset
indexes, and ordinary mapping iterables yield the same semantic graph for the
same nonconflicting data. Repeated rows retain all identified children. Repeated
refreshes preserve entity references and subclasses, update old values, and do
not grow a replay ledger. Child-only loads leave parent metadata intact.

### W4 — Implement source-image normalization and ROI collection loading

**Depends on:** W3 and the W1 image contract. **Owns:** imaging adapter functions,
`columns.py`, image/ROI lookup integration, and imaging load tests.

Implement D5 path normalization, explicit-UID disagreement diagnostics, source
image/derivative lookup, and source location aliases. Project ROIs from metadata
by default, consume generators once, and support ROI-only loading before images.
Implement missing/empty/malformed collection behavior and replacement of the
current collection, maintaining source-path/position and toolkit lookup indexes.
Preserve useful source coordinates and supplied DBT frame facts without inferring
depth. Represent FFDM, DBT, and synthetic 2D; US/MRI expansion is out of scope.

**Exit:** root relocation does not duplicate an original SOP; metadata refresh
after image rekey targets the same source object; derivative IDs never overwrite
the source SOP. One ROI uses ordinal 0. Multiple equal boxes stay separate slots.
Replacing a collection removes stale registrations, leaves unaddressed images
unchanged, and differs explicitly from in-place ROI editing.

### W5 — Complete MagView clinical and registry relationships

**Depends on:** W3; W0 registry binding evidence for the source-specific adapter.
**Owns:** clinical adapter projections, registry adapter/mappings, relationship
resolution integration, and clinical relationship tests.

Attach identified procedures to findings and pathology to procedures at the
supported grain. Where an attachment is incomplete, keep accessible unresolved
facts/references and attach only at a level the source supports. Load explicit
exam links. Add a registry input whose key mapping is configurable; bind the real
table once verified. Group `cancer_outcome_registry_id` assignments by
`(MagView accession, empi_anon, registry_id)` independently of finding rows.

Resolve patient+registry ID to the actual entry and associate it with the
MagView exam. Confirmation is a property of the supplied assignment even while
an endpoint is absent. One entry can appear under multiple exams. Do not rerun
matching, create diagnoses from IDs, or require a finding. Keep assignment changes
subject to an explicit collection/update rule from W0 rather than stale-edge
accumulation. Proposed rule: grouped refresh with a populated assignment column
replaces that exam's supplied registry-assignment set; an explicitly empty/null
assignment clears it; an absent/unbound column preserves it. Merge unions supplied
assignments. Apply the analogous rule to explicit linked-accession sets. This
changes associations, not the existence or attributes of their target objects.
Document that a refresh must include all desired assignments for an addressed
exam; repeated finding rows are grouped before any replacement occurs.

**Exit:** direct traversal reaches procedures/pathology and actual registry
entries; repeated findings do not duplicate exam associations; every ordering of
exam/assignment/entry loads resolves to the same graph. Identical registry IDs for
different patients stay distinct. Patient disagreement remains inspectable and
does not suppress useful accession attachment. Missing endpoints stay pending.

### W6 — Add predicate selection and independent owning partitions

**Depends on:** W2, W4, W5. **Owns:** new `core/selection.py` or equivalent focused
module, movement boundary integration, and partition tests.

Implement non-owning `select`, copy-based `partition`, and lower-level context
shells under D7. Support patient, exam, finding, procedure, and pathology selection;
image/ROI selection may use the same mechanism where meaningful. Predicates use
object attributes and may produce multiple output keys without Pandas syntax.
Context shells are labeled as context and do not imply complete source coverage.
Use a per-output copy map so shared children remain shared within an output but
never across owning graphs. Preserve unresolved and cross-boundary references.

**Exit:** edits in one owning output cannot affect source or another output.
Selected descendants travel together; lower-level selections do not pull unrelated
siblings; linked exams stay references across a boundary. A selection view makes
its non-owning, live-object behavior explicit. Extension copy behavior is tested;
uncopyable consumer attributes produce a documented error or use a consumer hook,
not a silent shallow copy of mutable state.

### W7 — Move quality rules to optional validation and reuse partitioning

**Depends on:** W6. **Owns:** new validation module(s), constructor/adapter quality
check removal, and validation tests.

Expose manually callable validation for pathology, procedure, finding, exam, and
patient; parent validation can aggregate descendant issues. Add explicit image/
ROI rules where existing geometry/frame checks belong. Define how warnings and
missing optional data affect the selected object's valid/invalid classification;
missing optional tables alone must not make a graph invalid. Custom validators
can inspect project attributes. Validation itself is read-only; separating results
uses W6's owning-copy semantics and carries each selected object's descendants.

Audit checks in `rois.py`, `images.py`, `clinical/histories.py`,
`clinical/attributes.py`, `core/anatomy.py`, and source normalizers. Keep necessary
coordinate arity/numeric parsing, key construction, and relationship checks.
Relocate bounds, ordered/positive geometry where representable, confidence range,
clinical date/age plausibility, severity consistency, and modality/frame quality
rules. Specify representation of unknown/raw values instead of discarding them
or coercing invalid values into valid clinical claims.

**Exit:** representable but implausible input loads; explicit validation reports
its issues. Valid/invalid partitions obey the same ownership/context rules as
predicate partitioning. Ingestion never silently invokes the quality suite.

### W8 — Prove patient-independent and whole-dataset construction cost

**Depends on:** W3–W7; performance constraints apply from W2 onward.
**Owns:** `benchmarks/graph_loading.py`, integration scale tests, and measured
results in `benchmarks/README.md`.

Benchmark patient + exam + repeated finding/procedure/pathology + image/ROI data,
with registry assignments and pending references. Cover full loads, patient
subsets, many small updates into a populated graph, and references resolved later.
Record row/object/edge counts, median time, peak memory, and environment at 1x,
2x, and 4x input sizes. Separately time a fixed patient's update as unrelated
patient count grows. Keep setup and timed work separate.

Add deterministic instrumentation checks that an update visits affected objects
and pending neighbors rather than every patient/image/ROI/link. Use repeated-run
timing as supporting evidence, not a fragile single absolute CI threshold. A
provisional performance gate is less than 3x median construction time per doubling
at useful sizes, plus roughly linear object-memory growth; revise only with
recorded measurement evidence. Ensure any patient helper groups/indexes once and
does not filter the entire original table anew for every patient.

Define the grouping boundary for streaming: chunks of one logical refresh must
not refresh a repeated semantic object independently. Either assemble complete
patient groups before applying them or retain only the necessary grouped state
until finalization. Explicit separate refresh calls are distinct snapshots; they
must not accidentally act as a merge because input was chunked.

**Exit:** multi-grain cardinality and content are correct at every size; no global
rescan per patient/update; measurements and supported batching assumptions are
published. Large private-data qualification is reported separately from synthetic
scale evidence and needs representative data supplied through an authorized path.

### W9 — Qualify and document the clean public cutover

**Depends on:** W8. **Owns:** package exports, README files, installed contract
tests, test traceability, static checks, and CI configuration where needed.

Update the README governing link and examples to the mutable contract. Document
construction, identity, same-grain refresh/merge, extensions, rekeying, unresolved
references, ROI replacement, membership/movement, validation, and partitioning.
Remove claims of strict atomicity, field-level provenance, physical-index identity,
and mandatory workflow coverage. Delete unused locator/ledger/policy machinery
after import inspection; retain only optional diagnostics with real supported use.

Build/install the package and exercise the public API from outside the checkout
with no `PYTHONPATH` or private imports. Expand the wheel check beyond patient/exam
loading to clinical traversal, image/ROI loading, refresh, mutation, movement,
partitioning, and a subclass. Decouple this acceptance gate from the patch recipe;
the recipe can be retired or explicitly marked historical if incompatible.

Run the full suite, Ruff, and mypy. Expand type-check coverage from today's three
files to the changed domain, graph, adapters, selection, and validation surface;
the existing `follow_imports = "skip"` baseline is insufficient evidence for them.
Run CI on the declared Python 3.9–3.13 range, or explicitly decide/document a
support change. Do not silently introduce newer-only typing/dataclass features.

**Exit:** target acceptance cases below pass through installed public APIs, old
architecture promises are absent from current usage docs, and no workflow module
is required by the core. Record the qualifying revision/wheel version. A release
or remote publication is a separate implementation-time action, not part of this
planning task.

## 5. Acceptance coverage and legacy-test disposition

Prefer focused contract tests over private implementation snapshots. Suggested
new suites are `test_mutable_entities.py`, `test_graph_membership.py`,
`test_semantic_loading.py`, `test_image_roi_refresh.py`,
`test_registry_relationships.py`, `test_graph_partition.py`, and
`test_optional_validation.py`. Names can change; the cases cannot disappear.

| Contract family | Required cases beyond the work-package exit gates |
|---|---|
| Identity and arrival order | Shuffled nonconflicting rows; sliced/reset/duplicate indexes; numeric nullable IDs; invalid diagnostic keys with valid semantic IDs; two accessions with different patients; one accession with contradictory patients; explicit ownership resolution and subsequent updates. |
| Refresh/merge | Changed same-source row; missing vs. null vs. unbound fields; complementary repeated rows; incoming scalar conflicts; repeated procedure/pathology children; narrow+wide projections; parent untouched on child-only loads; subclass attributes and Python references retained; ROI exception under merge. |
| Relationships | Patient-descendant traversal; shared procedure/pathology deduplication; no inferred finding/image/ROI correspondence; linked-exam cycles and missing targets; registry assignment before either endpoint; duplicate assignment rows; one entry/two exams; same registry ID/two patients. |
| Imaging | Valid/invalid paths; explicit UID mismatch; relocation; source reload after toolkit rekey; derivatives sharing source SOP; ROI-only before image; missing/null/empty/malformed ROI input; singleton/multiple/equal-box collections; replacement then lookup; removal then re-registration; supplied DBT depth without inference. |
| Membership | Detached standalone edits; same-object repeat registration; distinct-object key collision; rekey of every supported entity key and dependent reference; movement into occupied keys; patient and exam pops; shared descendant copies; crossing linked-exam references; later resolution after moving both endpoints. |
| Partition/validation | All five required clinical levels; multiple predicate groups; empty output; ancestor context; independent nested metadata/subclass fields; shared child selected through two branches; custom validator; descendants included; missing optional data; implausible but representable input accepted before validation. |
| Delivery/scale | Installed wheel outside checkout; public imports only; multi-grain full/subset/batched loads; fixed-patient updates amid growing unrelated data; memory growth; no pandas runtime dependency if that existing packaging choice is retained. |

Retain useful tests in `test_magview.py`, `test_birads.py`, `test_anatomy.py`,
`test_primitives.py`, and side-traversal tests, moving quality rejection assertions
where appropriate. In `test_lightweight_framework.py`, replace strict rollback,
changed-source-address rejection, patient-conflict nonattachment, ROI evidence
replay, and automatic field-provenance assertions with the new contract cases.
Rewrite pathology/history source-row identity tests under D8. Retire governed ROI
locator and patch-workflow expectations when their obsolete APIs are removed;
preserve useful geometry math and semantic normalization checks. Do not disable
whole suites to make the replacement green without this case-level disposition.

## 6. Orchestration and later workflow recovery

The main integration order is:

```text
W0 → W1 → W2 → W3 → W4 + W5 → W6 → W7 → W8 → W9
                                                    ↓
                             separate matching and transfer repository ports
```

W4 and W5 can proceed independently once W3's grouped-loader interface and W2's
relationship hooks are stable. They both touch loader/column integration, so give
each a focused adapter module and assign shared integration to one owner. Test
fixture preparation and benchmark harness work can begin earlier against the
agreed API, but their final gates depend on the completed runtime. Avoid concurrent
rewrites of `core/graph.py` or `sources/embed/loader.py`. Each completed package
reports its decisions, commits, checks, remaining limitations, and downstream
interface changes to the orchestration agent.

Do not use the older orchestration/recovery documents as additional requirements
where they conflict with this target. Do not spend an initial phase repairing
strict rollback, preserving DataFrame indexes as identity, rebuilding attribute
provenance, or making patch extraction the proof of readiness.

After W9, recover substantive workflows with their behavior tests into separate
repositories. Their locations and package names are inputs to that later work.
The historical commits are available locally and were verified in this review:

| Port | Starting tree | Implementation and behavior tests to recover |
|---|---|---|
| Matching/localization/grouping | `a2df9bc^` = `202bb33bcf0b96b54073c817a17412003d58dd9f` | `workflows/finding_localization.py`, `roi_localization.py`, `finding_roi_matching.py`, `imaging/roi_groups.py`; corresponding unit tests plus `test_inferred_roi_matching_policies.py` and relevant `test_workflow_regressions.py` cases. |
| ROI transfer | `202bb33^` = `4030f77832a621366d4307c5965d895cda2a6e14` | `workflows/roi_transfer.py` and `tests/unit/test_roi_transfer.py`. |

Paths in that table are under the historical `unified-system/src/embed_toolkit/`
or `unified-system/tests/unit/` trees. Inspect transitive imports during each port;
recover only needed workflow-local configuration, results, processing policy,
and behavior fixtures. Replace old provenance/ROI/transaction assumptions with
the qualified public API. Do not restore shared workflow machinery to core.

Matching's gate covers localization, grouping, multifinding ambiguity,
synthetic-negative handling, and explicit downstream-derived associations.
Transfer's gate covers related-acquisition inputs, target-image ROI creation,
coordinate/frame semantics, and locally owned transforms/depth policy. Each port
must test against an installed core wheel and declare a compatible version range.
New core acquisition facts should be added only when a concrete port demonstrates
a reusable fact gap; inference and processing policy stay in that consumer.
Historical behavior preservation does not establish clinical/scientific validity.

The scaffold is complete at W9. The broader separation goal is complete only when
both later ports and their behavior suites work in their own repositories.
