# EMBED scaffold assessment — 9 September 2026

Reviewed revision: `15fd8b7` (clean working tree at review start).

Subsequent maintainer decisions are recorded in the
[mutable scaffold contract](mutable-scaffold-contract.md). They supersede this
assessment's conflicting recommendations and priority judgments, including
strict rollback, immutable membership, preserved DataFrame indexes, mandatory
validation, and attribute-provenance requirements. Reproductions below remain
evidence about the reviewed revision, not the accepted target design.

Scope: active `unified-system` package, source adapters, domain objects, graph
transactions, tests, packaging, examples, architecture records, and workflow
removal history. This is a current-state assessment, not an implementation plan
already completed. Production code was not changed during the review.

**Judgment.** The codebase now has the right architectural shape for the scaffold
you describe. It provides a useful clinical object vocabulary and one incremental
graph, and it has already removed the major workflows from its installed package.
It is suitable for a controlled pilot consumer. It is **not yet a dependable
shared foundation with the guarantees its README and recovery record claim**.
Identity, mutation, attribution, and ingestion defects can change graph meaning
or lose contributions under ordinary subset-loading scenarios. Harden these
contracts before treating the API as stable across independent repositories.

A second wholesale redesign would waste the progress already made. The next
milestone should be a small, reliable graph library demonstrated by a separately
installed consumer, with workflow policy owned by that consumer.

## How completely the goal is achieved

| Goal | Assessment | Evidence and remaining gap |
|---|---|---|
| Minimal reusable clinical objects | Substantially achieved | Patient, Exam, BreastSide, Finding, interpretation, procedure, pathology, history, image, and ROI objects exist. Twelve names form the root facade. Some old provenance/ROI contracts remain alongside the new ones. |
| One canonical graph | Substantially achieved structurally | One registry owns the current graph. Parent traversal and keyed graph lookup share Patient/Exam/Finding/Image objects on ordinary loads. Public mutation and ROI replacement weaken that guarantee. |
| Construct from optional tables | Achieved for supported normalized table inputs | Ten optional inputs; patient-only, exam-only, finding-only, image-only, ROI-only, history, procedure, and pathology paths exist. Findings can establish an accession; image projections do not manufacture clinical nodes. |
| Incrementally load filtered subsets | Partially achieved | `into=`, typed source keys, replay detection, and deferred image/ROI/link resolution are implemented. RangeIndex slices and synthetic ROI source scoping have confirmed failures. Same-source partial-column enrichment is intentionally rejected as changed content. |
| Per-patient construction and traversal | Partially achieved | Patient → exams → findings/images → ROIs works. Procedures/pathology are mostly flat collections plus links; patient ownership checks and unresolved-parent coverage are incomplete. There is no patient-partitioned loader or bounded-memory iterator. |
| Translate clinical information flow faithfully | Good foundation, incomplete adapter coverage | Findings, procedures, pathology, and reported history remain distinct; exam/procedure/report dates are separately named. Episode links, acquisition groups, and several useful image facts are not projected. |
| Lightweight dependency and extension model | Strong package boundary; uneven implementation | No mandatory runtime dependencies, duck-typed DataFrame support, and a bounded transaction API. Two large modules and repeated whole-graph/pending scans make ingestion heavier than the public facade suggests. |
| Independent workflow consumers | Package isolation achieved; consumer readiness incomplete | Matching and transfer were deleted, not published elsewhere. Patch extraction is a repo-only consumer but its graph-image path currently fails. No maintained external matching/transfer consumer is demonstrated by this checkout. |

Runtime source is approximately 8.8k lines across 32 Python modules, down from
the historical review's 13.3k lines. `core/graph.py` is 1,638 lines and
`sources/embed/loader.py` is 1,540. Their combined size is a maintenance signal,
not itself a reason to split the design into more abstractions.

## Dataset-specific basis

I used `embed-context-internal.discover`, followed by `get_context` for the
Internal V2 representation, pathology, temporal, reported-history, V1c metadata,
and ROI contexts. After selecting those semantic concepts, I also retrieved the
`metadata_all_cohorts_v1c` physical table binding. These are catalog-backed
semantics, **not empirical validation against private clinical rows**.

The most consequential references are recorded below so this review can be
rechecked through the same MCP:

| MCP context / claim | Consequence for this library |
|---|---|
| `internal-v2.magview-representation-context#wide-association-grain` and `#finding-identity-scope` | One wide row is not one clinical object. Accession + finding number is the finding key; laterality is an attribute. The current finding registry gets this right. |
| `internal-v2.magview-pathology-context#procedure-pathology-attachment` | A complete patient + procedure date + type + biopsy side tuple identifies a procedure. Several procedures may attach to one finding. The current procedure key follows this model. |
| `internal-v2.magview-pathology-context#no-curated-severity-aggregates` and `#analyst-defined-severity-reduction` | Patient/side/exam outcome reduction belongs in consumers with explicit attribution and grouping. Missing pathology is not a negative outcome. The core should not choose those policies. |
| `internal-v2.magview-temporal-context#wide-colocation-not-availability` | Exam time, procedure time, report documentation, and downstream availability must remain distinct. Mere row co-location cannot establish what was known at an earlier exam. |
| `internal-v2.patient-history-context#reported-history-not-current-care` | Reported historical exposures/procedures/results must not become verified current care. Keeping separate history objects is appropriate. |
| `internal-v2.v1c-metadata-context#image-instance-identity` | The filename stem of `anon_dicom_path` is the anonymized SOP Instance UID, durable within the dataset version; the full filesystem path is a locator. Current ingestion conflates them. |
| `internal-v2.v1c-metadata-context#coverage-is-not-image-absence` | A clinical V2 accession unmatched to V1c metadata does not establish that the exam had no images. An empty loaded collection must mean “not represented in this graph,” not clinical absence. |
| `internal-v2.roi-context#roi-identity-and-provenance` | Collection position is only an address within an image-row serialization, not a durable lesion identifier. Source scope must remain part of a synthetic address. |
| `internal-v2.roi-context#roi-finding-attribution` | No explicit ROI-to-finding link is supplied. Same-side association is generally reliable only in the single-finding case; multiple findings remain ambiguous. |
| `internal-v2.roi-context#roi-cross-image-correspondence-absent` | Acquisition grouping does not supply cross-image ROI correspondence. Transfer and matching outputs are derived assertions, not dataset facts. |

The catalog also requires longitudinal candidate searches to traverse the
patient timeline: a candidate pathology accession belongs to its own exam and
need not equal the index accession. Implementing that search policy belongs in a
consumer; making patient-owned source facts traversable belongs in the core.

## Confirmed findings, in priority order

Priorities here mean P1: fix before relying on the affected shared-library
contract; P2: fix or explicitly constrain before broad consumer adoption.
References below are relative to this repository and pinned by the reviewed
revision. The companion [probe script](scaffold-assessment-probes-2026-09-09.py)
reproduces the principal cases using synthetic values only.

**1. P1 — Clinical links can cross patient boundaries.**
`core/graph.py:534–589`, `sources/embed/loader.py:980–1170`.
`_resolve_links` checks whether the target exists, not whether both endpoints
exist and agree on patient ownership. Load exam A owned by P1, then a procedure
row carrying P2 and accession A: the procedure → A edge is retained as
`source_colocated` with no issue. Pathology uses the same link-resolution path.
The public `add_link` also accepts a nonexistent image as a source when its exam
target exists. Endpoint existence is insufficient for clinical attribution.

Validate both endpoint references and known ownership before resolving an edge;
keep incompatible evidence inspectable without publishing it as a valid link.
Revalidate pending links when ownership becomes known later. Distinguish
structural resolution from attribution status. This must not impose an
index-accession equality rule on legitimate longitudinal workflows.

**2. P1 — Contiguous DataFrame subsets lose physical row identity.**
`core/tables.py:155–188`.
All RangeIndex values are discarded in favor of a new zero-based ordinal.
For a four-row DataFrame, loading `df.iloc[:2]` and then `df.iloc[2:]` into the
same graph keeps only the first two patients: the second slice's index `[2, 3]`
is changed to source addresses `[0, 1]`, and both contributions are rejected.
This directly contradicts the README promise that filtered indexes are retained.

Preserve a usable RangeIndex just as other usable indexes are preserved, and
make positional fallback explicit. Iterable chunks still need caller-provided
stable keys or separately identified materializations. Include contiguous,
stepped, overlapping, and reordered slices in regression coverage.

**3. P1 — ROI addresses collide across source scopes.**
`sources/embed/loader.py:829–833, 890–895`; `core/graph.py:435–453`.
When `roi_key` is absent, the adapter synthesizes it from `source.key` alone;
source scope and table are omitted. Loading different annotation rows at row 0
in two explicitly different scopes for the same image maps both to the same
ROI. With different boxes, the graph drops its resolved ROI and reports a
geometry conflict. Equal boxes instead conflate distinct evidence into one
identity, without evidence that they represent the same ROI.

Use a structured image + physical SourceRef + collection slot address for
unidentified source ROIs. Keep explicit consumer-assigned ROI identities a
separate supported case. Never use collection ordinal as a durable cross-image
or cross-materialization lesion key.

**4. P1 — Public objects can bypass every graph mutation invariant.**
`clinical/patients.py:20–29, 75–84`; `clinical/exams.py:108–122, 181–204`.
Root collections return tuples, but their members expose mutable IDs, lists,
and `add_*` methods. `graph.patient('P').add_exam(Exam('UNINDEXED'))` changes
patient traversal without adding the exam to `graph.exams`. Changing a node's
identifier likewise desynchronizes registry keys. Manual edits inside a strict
transaction are not staged or rolled back.

Keep lightweight manual value construction, but make graph-owned identity and
membership writable only through graph operations. Read-only collections alone
are not enough. Avoid maintaining two independent public mutation systems.
The existing read-only test verifies only that a root tuple cannot be appended.

**5. P1 — Commit-time errors can leave a strict transaction partially applied.**
`core/graph.py:623–638, 1110–1130, 1344–1483`.
The transaction checks accumulated Issues before `_commit`, but `_commit`
mutates registries before constructing and validating resolved values. In a
graph with an existing ROI, stage a new patient and an ROI enrichment with
`frame_provenance='derived'` but no method. Existing-ROI staging bypasses new-ROI
constructor validation; commit raises `ValueError` and the new patient remains.
The same problem occurs in audit mode. This is a malformed downstream-adapter
contribution, but strict atomicity is precisely the promise that should contain
it. Existing tests cover issue-driven rollback, not resolver exceptions.

Validate contributions and their projected resolved state before publishing
mutations, or implement a complete rollback mechanism. Prefer staged validation
that avoids copying the entire graph. Test failures during commit, not just
errors discovered while reading rows.

**6. P1 — Image identity is a path, and the SOP UID field contains that path.**
`sources/embed/columns.py:46–60`; `sources/embed/loader.py:713–720, 777–779`.
Loading `/old/1.2.3.dcm` sets both `image_id` and `sop_instance_uid` to that full
string. Loading the same filename under another mount creates another image.
The MCP identifies the filename stem as the version-local identity. A wrong SOP
UID is also an interoperability defect for a consumer opening DICOM files.

Separate the stable, namespace-scoped image key from file location(s), extract
the documented stem at the EMBED boundary, and preserve the locator as a fact.
Define the corresponding migration for ROI image references. Do not infer
identity across dataset versions.

**7. P2 — ROI ingestion does not enforce available image/frame semantics.**
`sources/embed/columns.py:65–76`; `sources/embed/loader.py:803–930`;
`core/graph.py:435–520`.
A DBT image with three frames accepts ROI frame 7 without an issue. A 2D image
also exposes source frame indices as meaningful `roi.frame_indices` and can
receive `frame_count`, despite the standalone image constructor rejecting a
frame count on a non-DBT image. The adapter does not bind `num_ROI`, so cannot
check count agreement; bounds are not checked when image dimensions arrive.

Retain raw source evidence separately from validated geometry/depth. Validate
count alignment at ingestion and image-dependent constraints once the image is
known, including ROI-before-image order. Non-DBT frame values must not become
informative depth. Residual coordinate clipping may remain a declared consumer
policy; the core can report the source-bound inconsistency without prescribing
pixel-processing behavior.

**8. P2 — Incremental ROI enrichment replaces previously returned objects.**
`core/graph.py:462–510`.
ROIs are immutable values, and the resolver substitutes a new object when
sources or annotation metadata change. A reference obtained before enrichment
retains stale metadata after a second source contributes to the same ROI.
This is inconsistent with the README's blanket canonical-object promise, though
ordinary later image attachment without ROI changes preserves the object.

Choose explicitly: stable graph handles with immutable value snapshots, or
stable graph-owned objects updated only by the graph. Either can be small.
Document the guarantee by object kind and make downstream result references use
stable keys rather than relying on Python object identity.

**9. P2 — The scale test misses quadratic construction paths.**
`core/graph.py:284–291, 901–925, 1026–1046, 1306–1320, 1456–1483`;
`tests/integration/test_graph_scale.py`; `core/tables.py:91–98, 151`.
Conflict detection scans all pending contributions for each exam/finding/image/
ROI upsert. Exam resolution scans all patients to remove an accession. Every
commit rebuilds image/ROI/link memberships and scans existing histories,
attributes, and procedure contributions. Thus map-backed keyed lookup does not
imply map-backed construction cost. Inputs are materialized rather than streamed.

Synthetic measurements on this machine, without tracemalloc:

| Rows per table | Patient-only load | Patient + exam load |
|---:|---:|---:|
| 250 | 0.0012 s | 0.0102 s |
| 500 | 0.0026 s | 0.0328 s |
| 1,000 | 0.0047 s | 0.1222 s |
| 2,000 | 0.0098 s | 0.4157 s |

These are diagnostic single runs, not dataset-scale forecasts. The existing
benchmark covers only patient ingestion and dictionary lookup, and asserts no
runtime growth constraint. Index pending observations by entity, maintain
reverse ownership and unresolved-target indexes, and resolve touched entities.
Benchmark multi-grain and repeated small-batch loads before claiming scale.
A patient-partition iterator can remain an adapter/helper rather than a new
framework abstraction.

**10. P2 — The retained workflow example does not consume graph objects safely.**
`examples/patch_extraction/extraction.py:88–100`.
`extract_patch(pixels, graph.rois[0], image=graph.images[0])` raises
`AttributeError: 'NoneType' object has no attribute 'image_locator'` because
current graph-loaded ROIs have a key and SourceRef but no old `RoiLocator`.
Manual images also make `canonical_source` raise. The image/ROI source-ledger
subset requirement is incompatible with separately sourced annotations.

Make this consumer validate image identity and coordinate-frame compatibility
through the current public contracts. Add one installed-consumer journey using
`load_embed` output before using this recipe as evidence of workflow readiness.

**11. P2 — Attribute provenance can identify a source that never supplied a value.**
`imaging/images.py:146–151`; `core/graph.py:361–399`.
`source_for('height')` falls back to the image's first source, while graph
loading never populates `attribute_sources`. Load image I without height from
scope `a`, then height 12 from scope `z`: the image reports 12 but
`source_for('height')` returns scope `a`. This is fabricated field attribution,
not merely incomplete metadata.

Expose actual per-field observations/source sets from the registry and make
“no field-specific evidence” explicit. Patient identity-only source evidence,
conflicting finding opinions, and rejected contributions also need a small
public inspection route; consumers should not read `_contributions` or private
observation dictionaries to explain their inputs.

## Design gaps and deliberate boundaries

**Loading source facts is not the same as implementing a workflow.**
`load_embed(images=metadata)` constructs images but does not read the serialized
ROI collections from those same physical rows. Currently the caller must pass
`rois=metadata` separately. That can be a valid explicit projection API, but the
common MagView + metadata example should say so or a metadata convenience path
should project both grains while preserving their shared physical SourceRef.
Missing ROI ingestion must not be mistaken for zero annotations.

The image adapter also omits acquisition-group ID, source ImageType, patient
orientation, spacing, and related acquisition facts. The image object has an
orientation field, but the loader/transaction cannot populate it. Unknown fields
are dropped unless raw retention is requested, and raw retention is internal
metadata rather than a supported consumer API. Column overrides can rename
existing slots; they cannot add an unmapped semantic field. Transfer consumers
would therefore reparse the original tables or reach into private state today.

Keep reusable identity, geometry, and acquisition facts accessible, either as
small typed fields or a bounded extension mechanism with provenance. Keep
eligibility decisions, registration transforms, depth inference, and ROI
correspondence algorithms outside core. `MammogramImage`/`ImageModality` are
mammography-oriented; source modality is preserved as text, but ultrasound/MRI
are not first-class image variants. Explicitly decide whether “cross-modality”
currently means FFDM/DBT/synthetic 2D, or also MG/US/MR. Do not advertise the
latter simply because arbitrary modality text can be retained.

**The graph is an aggregate model plus an edge ledger.** This is adequate; it
does not need NetworkX, a graph database, or a plugin registry. However, expose
small read APIs for links from/to a node, resolving a typed reference, and
patient-owned procedures/pathology. Today consumers must scan all links and
understand source-encoded pathology identities. `_has_target` cannot resolve
pathology kinds as targets. Missing exam → patient references are not included
in `unresolved_references` even when an accession names an absent patient;
history recording-accession references also lack the general resolution path.

Explicit same-episode `linkedaccession_anon` relationships are not loaded. A
source-asserted exam link would be useful core data; constructing episodes or
matching longitudinal lesions remains consumer policy. No general episode class
is necessary until a concrete consumer needs one.

**Incremental does not currently mean patching the same physical record.**
Replay is keyed by SourceRef + concept + slot. Adding previously absent columns
to that same contribution is treated as changed content, not compatible
refinement. This is documented architecture, not an accidental bug. Explain the
supported recipe for column projections, revised materializations, and source
versions in the quickstart. Either explicitly support compatible refinement or
state that callers must identify new evidence as a new contribution. Do not
silently change scopes just to suppress conflicts: that can duplicate evidence.

**Do not make completeness a clinical claim.** A useful optional load manifest
could state which tables/projections were supplied, whether subsets were used,
and which references remain unresolved. It must not manufacture a negative
finding, absent-image indicator, complete patient follow-up, or event timestamp.
The existing separate history/pathology/interpretation types and lack of automatic
outcome aggregation are strengths worth retaining.

**Simplification should follow actual consumers.** The old SourceLocator /
RoiLocator / RoiSourceProvenance route coexists with SourceRef / roi_key, and
`RegionOfInterest` still has a stale docstring claiming its identity is always a
structured locator. Source-specific `from_embed_coordinates` is also exposed on
a domain class. Consolidate these overlapping contracts as consumers migrate;
do not restore the deleted general audit framework. Geometry values and useful
landmarks can remain core if consumers share them, while localization scoring,
ROI grouping, and workflow reports belong together downstream.

## Separating the workflows into repositories

The extraction work has partly happened, but as deletion:

| Bundle | Current state | Recoverable baseline |
|---|---|---|
| ROI transfer | Removed, including its unit tests | Parent of `202bb33`; `workflows/roi_transfer.py`, `tests/unit/test_roi_transfer.py` |
| Finding/ROI localization, grouping, matching | Removed, including inference-policy and regression tests | Parent of `a2df9bc`; localization/matching modules, `imaging/roi_groups.py`, and associated tests |
| Patch extraction | Repo-only recipe, not installed | `unified-system/examples/patch_extraction/` |
| Shared workflow audit/results | Removed in later cleanup | Retrieve the transitive types actually used from the corresponding historical trees |

Recover the implementation **and** behavior tests into the consumer repositories;
do not restore the old installed `workflows`, `config`, and `audit` packages as
compatibility layers. The historical code imports deleted audit/result and ROI
contracts, so recovery is a port, not a direct file move. Parent revisions above
are extraction references, not claims of scientific correctness.

A sensible ownership split is:

| Repository | Owns | Depends on core for |
|---|---|---|
| EMBED toolkit | Clinical and imaging facts, identities, provenance, graph construction, source parsing, structural validation, traversal | Nothing downstream |
| Finding-to-ROI matching | Finding/ROI localization, ROI groups, candidate generation, scores, thresholds, ambiguity and abstention, result serialization and algorithm versions | Patient/exam/side/finding/image/ROI references, anatomy and source evidence |
| ROI transfer | Related-acquisition eligibility, transforms, registration, target depth policy, generated ROIs, transfer provenance and QA | Image/acquisition/coordinate facts, source ROIs, stable references |

Matching should return explicit candidate/inferred associations with algorithm,
configuration, evidence, and uncertainty. Persisted links may use a validated
core association primitive, but scores and matching policy remain downstream.
For multiple findings per side, retain ambiguity unless a validated additional
method resolves it. Keep synthetic negative findings identifiable.

Transfer should return a new target-image ROI plus a derivation record pointing
to the source ROI and transform. Acquisition grouping can establish relevant
image context; it cannot establish lesion correspondence. Keep annotation x/y
origin separate from inferred DBT depth. These outputs may be loaded back through
a small consumer adapter once reference/identity contracts are fixed.

Consumers should depend on an installed wheel and an explicit compatible version
range. Their tests should exercise the public API outside the core checkout,
without `sys.path` edits or imports from examples/private registries. Public root
imports are convenient, and stable focused submodules can expose specialist
types without enlarging the root facade. A release-local namespace must accompany
persisted cross-repository references.

## Recommended sequence and completion criteria

1. **Stabilize correctness.** Address findings 1–6 in separate coherent changes
   with regression cases. Publish the identity, graph-owned mutation, source-row
   refinement, and transaction semantics together as a short public contract.
   Gate: subset permutations preserve meaning; cross-patient edges cannot
   resolve; a strict failure leaves graph state and existing references intact.
2. **Prove the smallest consumer path.** Repair the patch example and run it as
   an independently installed consumer using a metadata-derived image and ROI.
   Gate: no old locator requirement, private imports, or source-ledger coupling.
3. **Recover matching as the first substantive consumer.** Port the historical
   algorithms and tests; keep local result/configuration/evidence types. Add only
   the minimal public traversal and fact access it demonstrably requires.
   Gate: single-finding, multifinding ambiguity, synthetic-negative, and replay
   cases run against a pinned core wheel.
4. **Recover transfer against explicit image facts.** Add the missing acquisition
   inputs and ROI/frame validation, then port transfer and its behavior tests.
   Gate: namespace, image ownership, coordinate-frame and depth provenance remain
   inspectable; unsupported relationships produce an explicit non-transfer result.
5. **Measure and qualify the shared foundation.** Replace quadratic scans, broaden
   typing to graph/adapters, and benchmark multi-grain patient/subset ingestion.
   Gate: selected internal data is checked by a maintainer, including null dtypes,
   source identity, ROI arrays, and representative scale. The semantic MCP alone
   cannot supply this empirical validation.

There is no need to implement every possible clinical entity or every EMBED
column before extracting consumers. The core is ready when those consumers can
obtain stable, attributable facts and traverse them without rebuilding the same
clinical graph or depending on internal dictionaries.

## Verification and limits

- Local Python 3.13 suite initially returned **212 passed, 1 failed**. The failure
  was the wheel test's isolated build attempting to download setuptools through
  the restricted network, not a product assertion failure.
- The wheel smoke test was rerun with permitted network access: **1 passed**,
  including installation and researcher journeys. All **213 collected tests
  therefore passed across these runs**; the whole suite was not rerun afterward.
- Ruff passed for source, tests, examples, and benchmarks. Configured mypy passed,
  but covers only three source files with imported modules skipped; it does not
  establish typing quality for graph or adapters.
- Additional synthetic probes reproduced the findings above. They are review
  diagnostics, not a replacement test suite or measurements of private data.
- CI declares Python 3.9–3.13. Only local Python 3.13 execution was verified here.
- No internal clinical rows, private patient data, remote CI results, or real
  image pixels were inspected. No matching accuracy or transfer validity is
  asserted. No consumer repositories were created as part of this assessment.

The August recovery record is useful history, but its “implemented” status should
not be read as evidence that every global acceptance criterion holds today.
This assessment identifies the remaining work against those same intended goals.
