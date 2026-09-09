# Mutable EMBED scaffold: target contract

Status: maintainer-directed target; not yet implemented.
Recorded: 2026-09-09, following the scaffold assessment discussion.

This document records the maintainer's answers to review questions 1–23. It
supersedes conflicting target requirements in the August architecture recovery
record and September assessment. Those documents remain evidence about their
reviewed implementations, not obligations to preserve their architectural
choices. In particular, atomic transactions, pervasive strict ingestion,
DataFrame-index identity, immutable graph objects, mandatory attribute-level
provenance, and workflow coverage manifests are not target requirements.

## Purpose and scope

Provide small, mutable clinical and imaging objects with a stable external
interface. Build and manipulate their clinical graph from partial EMBED tables,
without embedding downstream processing workflows or a validation pipeline.

The patient is the principal working unit and the highest clinically meaningful
root. Dataset/cohort containers group independent patient graphs; cohort numbers
do not create a higher clinical entity. Whole-dataset and subset ingestion must
scale through patient-independent construction, rather than requiring repeated
whole-dataset scans for each object or update. Streaming/partitioning mechanics
and batch sizes are implementation decisions, not additional clinical concepts.

Support FFDM, DBT, and synthetic 2D. Defer ultrasound and MRI. Consumers must be
able to attach project-specific attributes without modifying the toolkit;
subclassing is an acceptable mechanism. Supporting extension attributes during
reloads needs an explicit public rule before implementation is finalized.

## Clinical structure and traversal

The graph spine is:

```text
Patient
  -> Exam
       -> Finding
            -> MagView-associated procedure
                 -> Associated pathology
       -> Image
            -> Image-local ROI
       -> Exam-associated registry pathology, where exam attribution is supplied
       <-> Explicit linked exam
```

Exam and breast laterality provide the closest currently supported common scope
for findings and images. Do not create a direct finding–image or finding–ROI
association merely from shared scope. Cross-image ROI correspondence is likewise
an explicit supplied or downstream-derived relationship, not ingestion inference.

Attach procedures and pathology at the supported clinical level so users can
traverse the actual objects. They must not be accessible only through flat side
tables or opaque edge-ledger scans. Internal indexes remain appropriate for lookup;
they do not replace clinical relationships. Parent objects should provide simple
traversal of direct children and descendants, such as a patient's exams,
findings, procedures, and pathology.

Preserve explicit linked-accession relationships and an accessible indication
that an exam is linked to another exam. A separate episode object is unnecessary.
No temporal episode inference is implied by preserving an explicit link.

An accession identifies exactly one exam and is intended to map to one patient.
Contradictory patient IDs are data-quality artifacts, not multiple legitimate
exam identities. Prioritize accession-based linkage; do not require pervasive
rejection of useful accession-level associations. Preserve enough conflicting
identity information for optional graph validation without introducing mandatory
field-level provenance. Selection of patient ownership when source IDs disagree
remains an explicit unresolved policy; do not silently introduce row-order-based
ownership as a semantic rule.

### Confirmed registry-to-exam attribution

The maintainer confirms that an internal algorithm assigned cancer-registry
entries to MagView exams using clinical/procedural factors and study date. These
are confirmed relationships based on the best available evidence. The scaffold
must preserve the existing assignment as a source-provided relationship; it must
not rerun the matching algorithm, require finding-level attribution, or demote
the assignment to an unresolved candidate merely because it originated from an
algorithm.

The MCP confirms that the MagView field `cancer_outcome_registry_id` is meaningful
jointly with `empi_anon`. Resolve that patient-scoped reference to the actual
registry entry, and attach the entry at the exam identified by the MagView
accession. Patient plus registry ID identifies the entry; the supplied MagView
assignment supplies exam attribution. Do not assume the entry can link to only
one exam, and do not manufacture a pathology diagnosis from the reference ID
alone. Repeated MagView finding rows must not duplicate the exam-level association.

If a referenced registry entry or exam has not yet been loaded, preserve the
reference for later resolution. Missing objects do not invalidate the confirmed
source assignment. The exact physical key column in the separate registry table
can be bound when that adapter is implemented.

Evidence: maintainer clarification in this review, together with
`embed-context-internal.get_context`,
`internal-v2.magview-representation-context#cancer-registry-reference`.
The catalog does not yet bind the registry table or its physical relationship;
that catalog coverage gap does not override the maintainer-confirmed assignment.

## Identity and source normalization

DataFrame indexes and row order must never determine clinical object identity or
whether a semantically identified object can be loaded. Use the applicable
patient ID, accession, finding number, procedure identity tuple, and image
identifier. Sorting or resetting a DataFrame index cannot alter these identities.
Physical source references, if retained, are optional diagnostics and cannot gate
construction merely because a DataFrame address was reused.

Original image identity is associated with its anonymized SOP Instance UID.
The EMBED path convention makes that UID recoverable without opening the DICOM:

```text
{root}/cohort{n}/{patient}/{study UID}/{series UID}/{SOP UID}.dcm
```

Keep a mutable toolkit-level image identifier separate from original source SOP
identity and location. A consumer may identify a processed derivative with a
suffix or other explicit identifier without claiming it is a newly assigned
source SOP UID. Recovery from the EMBED path belongs at the adapter boundary,
using an explicit convention and appropriate structural checks; do not store a
full path in a field claiming to contain only a SOP UID. Exact field names,
derivation references, and handling of disagreement with explicit UID columns
remain API details to settle.

EMBED currently supplies no exported ROI-level unique identifier. For the
present scaffold, the maintainer accepts `(anon_dicom_path, ROI_coords position)`
as the available image-local annotation address. The position is inside the
serialized ROI collection, never the DataFrame row index. It is not a durable
lesion identity or cross-image correspondence claim. New explicit identifiers
may be supplied by future annotation/correspondence workflows.

Toolkit image rekeying, source image addresses, and ROI lookups must remain
coherent. Document that a positional ROI address applies to the current loaded
collection; after replacement, the same ordinal need not describe the same
annotation. Do not infer identity from equal boxes.

## Loading, refreshing, and merging

All relevant input tables/subsets remain optional. Loading image metadata should
load both its images and its embedded ROI collections by default. Missing columns
for one projection must yield an informative outcome while allowing the usable
projection to load. Distinguish unavailable ROI columns from an explicitly
supplied empty ROI collection; missing input must not silently clear annotations.

Default reload behavior refreshes existing objects from supplied data at the
same object grain, in place. It is not an implicit merge with prior loaded
attributes. Offer an explicit merge operation/mode for consumers that need it.
A child-grain load must not reset its parent's attributes: an ROI load can affect
an image's ROIs without resetting its image metadata.

Interpret a refresh at the load-operation level, grouping input rows by semantic
object identity before updating objects. MagView repeats patient, exam, and
finding information across rows with different procedure/pathology attachments.
Repeated rows must not cause per-row replacement that leaves only the last
child. Nonconflicting rows should produce the same graph regardless of row order.
Handling conflicting populated fields within one incoming load remains a
specified policy to choose, not an implicit last-row-wins default.

Refreshing an object's own attributes must preserve its existing Python object
reference. It must not discard unrelated descendants solely because their
separate grain was not supplied. Exact reset behavior for absent mapped fields
and consumer-added extension attributes must be documented before the public
reload contract is finalized.

Loading a new ROI collection from a DataFrame replaces the collection registered
to each addressed image. This is intentional collection replacement and does not
require preserving references to removed annotations. Separate object mutation
methods support editing individual existing ROIs in place. Images not addressed
by the incoming ROI load retain their collections; an explicit empty collection
clears the addressed image's collection. No ROI identity matching across revised
collections is implied.

Source materialization or record provenance is useful if simple, but not a
critical requirement. Drop mandatory attribute-level provenance unless a clear,
small implementation proves useful. Do not retain a heavy contribution ledger
solely to implement immutable evidence replay when ordinary object refresh is
the intended behavior. The caller tracks inputs, coverage, and workflow progress.

## Mutation, membership, and movement

All domain objects, including ROIs, support in-place updates. Independently
constructed objects remain useful outside a graph. Users can register, detach,
pop, edit, and re-register objects. The container and its registered objects are
mutable; no compatibility wrappers are required for the current implementation.

An object belongs to at most one graph container. Moving it to another container
moves membership rather than making that same object a member of two graphs.
Popping an exam carries its descendants; popping a patient carries its entire
clinical subtree. Keep graph indexes, parent traversal, and identifiers coherent
through a small supported mutation API, including identifier changes. Avoid
transaction/rollback infrastructure or elaborate restrictions that make routine
research manipulation difficult.

Relationships are not automatically ownership. Linked exams and any shared
procedure/pathology associations require explicit rules when extracting a
subgraph: do not recursively move every reachable linked object as though it
were a containment child. Shared clinical objects and edges crossing a partition
are an API design question to resolve before subtree movement is finalized.

## Optional validation, filtering, and partitioning

Strict transaction rollback is a non-goal. Remove it as an architectural promise;
do not strengthen the current transaction framework to satisfy historical tests.

Core ingestion translates data into objects and forms graph links. It should not
require checks that every value is clinically appropriate or geometrically
possible. Retain only parsing/construction checks necessary to represent data and
establish relationships, with informative failures. Bounds checks, plausibility
checks, and similar quality rules belong in optional validation or consumers.

Expose manually callable validation at pathology, procedure, finding, exam, and
patient levels. Separate valid/invalid portions at the selected level, with each
selected object's descendants traveling with it. The user decides whether to
inspect, discard, or continue with each result.

Filtering/partitioning must also work independently of validation, using
conditions on object attributes. Support separating patients or lower-level
objects into multiple graph portions without introducing cohort-selection policy.
A clear predicate-based API is sufficient; replicating Pandas' full expression
language is not a requirement.

Partition outputs must obey single-container membership. Do not return multiple
owning graph containers sharing the same mutable objects. Exact destructive-move
versus independent-copy behavior, ancestor context for lower-level selections,
and treatment of shared descendants/cross-partition references remain open API
details. A non-owning selection view is distinct from an owning graph container.

## External contract and delivery scope

No external consumers currently require compatibility. Target a clean cutover.
Stabilize object construction, identities, traversal, mutation, registration,
removal, same-grain refresh, explicit merge, and filtering/partitioning as the
external contract before recovering substantive workflows.

The existing patch-extraction recipe is not a required milestone. Its current
failure is evidence about that consumer, not a reason to shape the core around
it. Demonstrate external API usability with focused public-contract checks,
including installed-package use, without requiring a particular toy workflow.

Recover matching/localization/grouping and transfer implementations and their
behavior tests from Git history only after the external contract is stable.
Starting references are the parents of `a2df9bc` (matching bundle removal) and
`202bb33` (transfer removal). Port them into separate repositories with their
workflow configuration, results, and inference/processing policy owned locally.
Do not restore their old shared workflow machinery to the core.

## Review disposition

The assessment's reproduction results remain historical facts. Their priority
and remedies change under this contract:

- Patient-ID disagreement is inspectable quality information; accession-first
  linkage is intentional, not automatically a rejected association.
- DataFrame-index identity must be removed, not repaired by retaining indexes.
- ROI collection-position addresses are accepted within an image collection;
  DataFrame-row identity and implied cross-image correspondence are not.
- Mutability is required. Coherent graph updates replace immutability as the goal.
- Strict atomic rollback is removed as a goal, not expanded into more machinery.
- Optional geometric/clinical validation is not an ingestion-completeness gate.
- Source-path UID extraction is intentional; normalize fields accurately and
  separate processed toolkit identity from original source identity.
- Attribute-level provenance and load manifests are not required infrastructure.
- Patient-scale operation and whole-dataset ingestion both matter; benchmark
  multi-grain construction and avoid global rescans as patient count grows.
