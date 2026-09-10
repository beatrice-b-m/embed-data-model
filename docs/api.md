# EMBED Data Model API reference

This reference specifies the behavior defined by the [contract](contract.md).
See the [user guide](user-guide.md) for runnable examples and
[qualification](qualification.md) for dated verification evidence.

## Identity, ownership, and mutation

One accession has one `Exam`; its `asserted_patient_ids` retains all source claims. Conflicting claims leave
`patient_id` unset until `graph.assign_patient(exam, patient_id)` explicitly
chooses ownership. That choice persists on reload; source identities are unchanged.

Each mutable entity has `graph` (zero or one owner), `update(**fields)`, and
`rekey(**identifiers)`. Registered key fields must use rekey. Graph methods are
`register(entity, boundary="copy_shared")`, `attach(parent, child)`,
`detach(parent, child)`, `update(entity, **fields)`, `rekey(entity, **fields)`,
and `pop(entity, boundary="copy_shared")`. Detach leaves the child registered.
Child collections are read-only sequences; convenience add methods delegate to
the graph. Distinct objects at occupied keys raise ValueError before movement.

Standalone parent rekeys update dependent identities and embedded context within
the reachable containment subtree, preserving the same Python objects. Local
collision checks cover that subtree; standalone objects do not have a global
registry of unrelated parents or siblings. Patient rekey changes assigned exam
ownership and patient-owned observation context, while preserving asserted source
patient IDs, image patient claims, and procedure/registry source identities.

Linked exams are associations, never containment. Traversal deduplicates object identity;
serialization emits semantic references for repeated objects and linked cycles.

Pop retains exclusive Python objects. Descendants needed outside the selected
subtree remain original there and are independently copied into the popped tree.
Source UID/path and ROI-position changes use `update` so prior aliases are removed;
location sets supplied by metadata reload deliberately union old and new paths.
Crossing associations retain semantic references, including incoming links whose
source stays in the original graph. Registering a detached tree remaps stored
internal references to members rekeyed while detached; standalone rekey alone
does not visit sibling sources outside its reachable subtree. Partition independently copies
once per output, adds labeled ancestor context, and includes only selected branches.
`select(level=..., predicate=...)` is explicitly a non-owning view. Copy failures
raise an informative error; consumer `__deepcopy__` hooks are supported.

## Semantic loading

`load_embed(..., into=None, mode="refresh", columns=None)` returns a compact
report containing the graph and issues. Inputs are optional. One invocation is
one complete grouped snapshot; callers must assemble complete groups across
streaming chunks before invoking refresh. Separate calls are separate snapshots.

Refresh resets bound adapter-managed scalar fields, including absent/null fields,
and applies the combined snapshot. Unbound fields, consumer metadata/attributes,
subclass types, Python references, and unspecified descendant grains survive.
Merge applies supplied non-null fields. Complementary rows combine; conflicting
populated values become unknown with a diagnostic. Wide and narrow projections
share one grouping stage. Child rows ensure parents without refreshing them.

Managed fields by grain (bound mapped fields only): patient sex/birth_year/context_date;
exam exam_date/description; finding laterality/finding_type/interpretation/anatomy,
source anatomy codes/descriptors/record_type; image laterality/view/modality,
source modality/derived type, dimensions/frame_count, study/series IDs and coordinate
frame; procedure non-key adapter payload; pathology diagnosis/result_category,
malignant/severity/raw_severity/report_documented_date and ordered descriptors;
registry explicitly mapped payload fields. Source aliases and source identity,
source patient claims, keys, children and assignment sets have separate rules.
History snapshots replace each addressed patient's supplied history kind when no
explicit event ID is bound; merge of unkeyed history collections requires explicit
record IDs rather than guessing event equality.

## Pathology and reported facts

Prefer a supplied patient-scoped `record_id`. The fallback bundle key is the
supported attachment identity plus supplied report_documented_date: a complete
ProcedureIdentity when available, otherwise (accession, finding_number) or
accession. A documentation date is not a diagnosis/event date. Ordered descriptor
slots belong inside the bundle; duplicate values and order are preserved.
Absent discriminators produce accessible unresolved records with their payload
and supported attachment, not row ordinals or payload-derived event IDs.
Conflicting descriptor slots at a fallback key make the candidate bundles unresolved;
an explicit key is needed to distinguish them. Narrow and wide rows use the same
logical namespace. Within an addressed attachment's refresh these unresolved snapshots replace prior
unresolved snapshots; no replay ledger accumulates. Explicit record keys are
required to distinguish multiple reports at the same fallback grain.

History records with explicit record IDs are patient-scoped mutable entities.
Without IDs they are patient-scoped reported-fact snapshots, never performed
procedures and never inferred distinct clinical events. Interpretations, histories,
attribute observations, pathology observations/diagnoses, and landmarks are mutable.
Patient, Exam, BreastSide, Finding, Procedure, MammogramImage and RegionOfInterest
are mutable entities. Box, ProcedureIdentity, enums, coordinate/anatomy values,
semantic references, SourceRef, Issue and optional normalization diagnostics are
replaceable values. Frozen value types do not exempt their owning entities from
updates.

## Imaging and supplied association collections

`image_id` is model identity; `source_sop_instance_uid` is original identity;
`source_paths` stores location aliases. The adapter parses trailing
`cohortN/patient/study/series/SOP.dcm` path components. Explicit UID wins over disagreement and the
conflicting path UID is not a SOP alias; the supplied path remains a location alias
for the explicit UID. Derivatives require explicit model IDs and
`derived_from`; source reload follows the original even after model rekey.
An update or rekey that would give two original images the same source SOP raises
ValueError before changing fields or source indexes. The check uses the proposed
UID and derivation state together, including a derivative becoming an original.

Image metadata automatically projects ROI collections. Missing/null ROI input
preserves; explicit `[]` clears; malformed/conflicting input preserves with an issue.
Explicit `rois` input overrides automatic projection for addressed images. Both
refresh and merge replace the complete addressed image collection, including manual
ROIs. Save/pop manual annotations before replacement to retain them. Ordinals start
at zero, including singletons; equal boxes remain separate. Individual `roi.update`
preserves its reference, while collection replacement need not. Supplied depth flags
may be scalar or position-aligned lists; malformed/misaligned flags preserve the
previous collection with an issue. Derivative ROIs cannot replace the original
source collection or its source-address lookups.

Registry assignments group by accession, source patient and registry ID, independent
of findings. They remain confirmed when endpoints are missing. Refresh replaces
supplied assignment/link sets; explicit null clears; absent/unbound columns preserve;
merge unions. Refresh must contain all desired assignments for an addressed exam.
Targets are never deleted by clearing associations. Registry keys remain
(patient_id, registry_id), even when exam ownership differs.

Registry identity maps `patient_id` to `empi_anon` and `registry_id` to
`cancer_registry_id`. Payload fields are unbound by default and can be configured
through `columns`. Caller-supplied registry inputs do not require a physical table
name. MagView assignment IDs use `cancer_outcome_registry_id`.

## Validation

Numeric parsing, coordinate arity, and key/relationship representation checks are
part of construction. Bounds, ordered geometry, confidence, clinical age/date,
severity, and modality/frame plausibility are checked by explicit validation.
Warnings do not invalidate by default; error issues do. Missing optional tables
alone are valid. Validation is read-only and never called implicitly by loading.
