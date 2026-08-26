# Clinical object model resolution plan

Date: 2026-08-24
Status: completed implementation contract

> **Historical contract — superseded.** The canonical graph recovery preserved
> the scientific invariants but retired this plan's builder/evidence machinery.
> See
> [lightweight-framework-architecture-review.md](lightweight-framework-architecture-review.md).

## Objective

Resolve the correctness and coverage findings in
[the evaluation](clinical-object-model-evaluation.md) with a clean API break.
The repository is private and has no external consumers, so the final
implementation must not retain deprecated aliases, compatibility properties,
legacy readers, or dual serialization formats.

The historical pre-resolution baseline was 203 passing tests on 2026-08-24.
Completion is verified by the current assessment addendum in
[the evaluation](clinical-object-model-evaluation.md).

## Governing invariants

1. A blank source identifier never creates or participates in a clinical
   identity.
2. Every input row is independently addressable as source evidence, including
   rows that cannot resolve to a clinical object.
3. Source-row multiplicity is not clinical-object multiplicity.
4. Containment and attribution are distinct. Patient-to-exam,
   exam-to-breast-side, exam-to-image, and image-to-ROI are containment;
   finding-to-procedure, pathology attribution, and finding-to-ROI are explicit
   links with provenance.
5. Temporal endpoints are named for their governed meanings and are never
   fallback-coalesced.
6. A profile declares whether each concept and field is bound, raw-only,
   unresolved, unavailable, or unsupported.
7. Generated ROI locators are scoped serialization locators, not durable source
   identities.

## Frozen foundation contracts

The source-neutral foundation uses the following concepts. Exact module layout
may change during implementation, but their semantics must not.

### SourceLocator

Identifies one physical input occurrence through:

- dataset or materialization scope;
- source profile;
- source table;
- row ordinal or supplied source record key.

Two rows with the same missing clinical identifiers still have different
source locators.

### SourceOccurrence

Carries a `SourceLocator`, raw source values, a resolution state, and related
build issues. It is evidence and must never be counted as a resolved patient,
finding, procedure, diagnosis, or other clinical object.

### BuildIssue and BuildPolicy

`BuildIssue` records a stable code, message, severity, source locator, and
structured context. `BuildPolicy` has two modes:

- `strict` is the default and raises when a governed error prevents safe object
  construction;
- `audit` retains structured issues and unresolved occurrences while omitting
  unsafe clinical objects.

Pathology validation uses this shared policy rather than an independent mode.

### Resolution and availability states

Clinical resolution and field availability are separate concerns. The shared
vocabulary must distinguish at least:

- resolved;
- unresolved;
- bound;
- raw-only;
- unavailable;
- unmodeled;
- unsupported.

Null is a bound value state and is not interchangeable with unavailable,
unmodeled, or unsupported.

### Explicit links

Association records carry source provenance and attribution status. At minimum
the target graph needs finding-to-procedure, pathology attribution, and
candidate finding-to-image projection records. Resolved procedures do not keep
a first finding reference or mutable embedded finding-reference list.

### RoiLocator

An ROI locator declares whether it is source-supplied or synthetic. A synthetic
locator includes materialization or dataset scope, image locator, and source
ordinal. Equal image/ordinal pairs in different scopes are not equal. ROI
groups require addressable scoped locators and an explicit grouping basis.

## Target result shapes

The clinical build result contains resolved patients, exams, sides, findings,
interpretations, procedures, pathology observations, pathology diagnoses,
explicit association links, all source occurrences with an explicit resolution
state, build issues, and the complete governing `ProfileContract`.

The image build result contains resolved images, image-local ROIs, all source
occurrences with an explicit resolution state, build issues, and the complete
governing `ProfileContract`.

An explicit assembly result connects clinical and image results. It owns
exam-to-image and side-to-image containment, reports unmatched objects and
cross-table identity conflicts, and exposes candidate finding-to-image
projections without asserting clinical attribution.

Serialization represents shared objects once and links them by governed object
identity or scoped locator. It must not recursively duplicate a many-to-many
graph.

## Execution phases

1. **Complete:** Implement the source/provenance and build-policy foundation.
2. **Complete:** In parallel, prepare the clinical domain contracts, ROI
   locator primitives, and capability/coverage framework without editing the
   central EMBED adapter.
3. **Complete:** Integrate the clinical adapter sequentially: identity,
   procedures, pathology, graph ownership, candidate image projection,
   interpretations and fields, then reconciliation.
4. **Complete:** Integrate ROI construction in the adapter.
5. **Complete:** Migrate workflow, audit/export, and visualization ROI
   consumers in parallel.
6. **Complete:** Complete the `ProfileContract` declarations, including exact
   profile identity, full concept capabilities, field inventory, and field
   coverage.
7. **Complete:** Remove all obsolete API, update documentation, and run final
   verification.

## Coordination and commit protocol

All agents share one worktree, Git index, and branch. Parallel work therefore
requires exclusive file leases. Agents must not stage until the coordinator
reviews their work and grants the commit token. Only one agent may stage or
commit at a time.

Each accepted vertical slice includes its implementation and contract tests in
one descriptive commit. Before accepting a commit, the coordinator verifies
the focused and adjacent tests, `git diff --check`, the staged filename list,
and the staged diff. After every commit, `git log --oneline -3` confirms the
task was recorded.

The central adapter, its tests, package export files, shared import tests, and
workflow-regression ownership always have a single owner. Full-suite tests run
at every phase boundary.

## Final removal gate

**Gate status: Complete.**

The finished source and active tests must not expose or depend on:

- `PathologyEvent`;
- `FindingImageJoin` or `join_findings_to_images`;
- procedure first-finding or mutable finding-reference fields;
- a generic pathology `event_date`;
- bare ROI strings presented as durable identities;
- legacy serialized shapes or deprecated aliases.

The historical evaluation document may retain those names when describing the
defects that motivated this work.
