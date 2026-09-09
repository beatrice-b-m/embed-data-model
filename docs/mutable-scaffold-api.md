# Mutable scaffold API decisions

Implementation specification, 2026-09-09. The target contract governs; this
specification resolves implementation-plan D1–D8. Qualification is separate.

## Identity, ownership, and mutation

D1–D7 are accepted as proposed. One accession has one Exam; its
`asserted_patient_ids` retains all source claims. Conflicting claims leave
`patient_id` unset until `graph.assign_patient(exam, patient_id)` explicitly
chooses ownership. That choice persists on reload; source identities are unchanged.

Each mutable entity has `graph` (zero or one owner), `update(**fields)`, and
`rekey(**identifiers)`. Registered key fields must use rekey. Graph methods are
`register(entity, boundary="copy_shared")`, `attach(parent, child)`,
`detach(parent, child)`, `update(entity, **fields)`, `rekey(entity, **fields)`,
and `pop(entity, boundary="copy_shared")`. Detach leaves the child registered.
Child collections are read-only sequences; convenience add methods delegate to
the graph. Distinct objects at occupied keys raise ValueError before movement.

The shared entity implementation exposes private `_children()` containment edges,
`_attach_local(child)`, and `_detach_local(child)` for graph integration. Linked
exams are associations, never containment. Traversal deduplicates object identity;
serialization emits semantic references for repeated objects and linked cycles.

Pop retains exclusive Python objects. Descendants needed outside the selected
subtree remain original there and are independently copied into the popped tree.
Crossing associations retain semantic references. Partition independently copies
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
explicit event ID is bound; merge of unkeyed history collections requires explicit record IDs rather than guessing event equality.

## Pathology and reported facts (D8)

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
updates. Old attribution/locator/ledger types have no required public compatibility.

## Imaging and supplied association collections

`image_id` is toolkit identity; `source_sop_instance_uid` is original identity;
`source_paths` stores location aliases. Parse trailing
cohortN/patient/study/series/SOP.dcm. Explicit UID wins over disagreement and the
conflicting path UID is not an alias. Derivatives require explicit toolkit IDs and
`derived_from`; source reload follows the original even after toolkit rekey.

Image metadata automatically projects ROI collections. Missing/null ROI input
preserves; explicit [] clears; malformed/conflicting input preserves with an issue.
Explicit rois input overrides automatic projection for addressed images. Both
refresh and merge replace the complete addressed image collection, including manual
ROIs. Save/pop manual annotations before replacement to retain them. Ordinals start
at zero, including singletons; equal boxes remain separate. Individual `roi.update`
preserves its reference, while collection replacement need not.

Registry assignments group by accession, source patient and registry ID, independent
of findings. They remain confirmed when endpoints are missing. Refresh replaces
supplied assignment/link sets; explicit null clears; absent/unbound columns preserve;
merge unions. Refresh must contain all desired assignments for an addressed exam.
Targets are never deleted by clearing associations. Registry keys remain
(patient_id, registry_id), even when exam ownership differs.

The internal catalog was queried on 2026-09-09. Its
internal-v2.technical.cancer_registry_record_identifier and
internal-v2.magview-representation-context#cancer-registry-reference confirm
patient-scoped references but explicitly lack a physical registry binding.
A configurable adapter can be qualified synthetically. A real binding requires a
maintainer-supplied mapping or authoritative table schema; it must not be invented.

## Acceptance and old tests

Retain MagView normalization, BI-RADS, anatomy, primitives, side traversal and useful
geometry math. Move quality rejection cases (bounds, ordered geometry, confidence,
clinical age/date, severity and modality/frame plausibility) to explicit validation.
Keep numeric parsing, coordinate arity and key/relationship representation checks.
Warnings do not invalidate by default; error issues do. Missing optional tables
alone are valid. Validation is read-only and never called implicitly by loading.

Replace lightweight-framework strict rollback, changed-source rejection, index
identity, nonattachment on patient disagreement, provenance replay, and ROI evidence
replay with the plan's named contract families. Replace pathology/history physical
row identity with the explicit keys and unresolved/fact rules above. Retire locator
and patch-workflow expectations when their obsolete APIs are removed, documenting
case-level replacement rather than ignoring suites. W8 measurements and W9 installed
API/full-suite/static checks remain required before declaring implementation complete.
