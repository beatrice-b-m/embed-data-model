# EMBED Data Model contract

This document defines the library's scope and behavior. The [API reference](api.md)
specifies method, identity, and loading semantics; the [user guide](user-guide.md)
provides runnable examples.

## Scope and clinical structure

EMBED Data Model represents clinical and mammography data as mutable objects.
It supports FFDM, DBT, and synthetic 2D, with optional EMBED table adapters.
Ultrasound and MRI are outside the supported imaging scope.

The clinical containment path is patient → exam → finding → procedure → pathology.
Exams also expose images and supplied registry associations; images contain ROIs.
Objects support direct child and descendant traversal. Patients are independent
clinical roots, grouped by `DatasetGraph` for membership and lookup. Construction
and updates use patient and semantic indexes to avoid scanning unrelated objects.

Linked exams and registry assignments preserve source-supplied relationships.
A registry entry is patient-scoped and may be assigned to multiple exams. Missing
endpoints remain inspectable references and resolve when their objects arrive.
The adapter preserves assignments without rerunning matching or inferring diagnoses.

Findings and images can share exam and breast-side context without a direct
finding-to-image or finding-to-ROI association. Cohort selection, localization,
matching, cross-image correspondence, ROI transfer, pixel processing, patch
extraction, visualization, and scientific interpretation belong to consumers.

## Semantic identity and ownership

Clinical identity comes from mapped source identifiers, never DataFrame indexes
or row order. One accession identifies one exam. Conflicting source patient claims
remain in `asserted_patient_ids`; ownership stays unset until explicitly assigned
with `graph.assign_patient`. Explicit ownership persists across reloads.

Procedure identity requires patient, performed date, procedure type, and laterality.
Pathology uses an explicit patient-scoped record ID or a supported attachment and
report-date key. Insufficient or ambiguous identities remain unresolved records.
Unkeyed histories are patient-scoped reported facts, without inferred event identity.

An image's mutable `image_id` is separate from its source SOP UID and path aliases.
The adapter can recover source identity from the EMBED path convention
`cohortN/patient/study/series/SOP.dcm`. Explicit SOP UIDs take precedence over
conflicting path-derived UIDs. Derivatives have explicit IDs and `derived_from`.

An ROI has an image-local collection key. Source annotation positions are zero-based
addresses within the loaded collection, not durable lesion identities. Equal boxes
remain separate annotations. Collection replacement can change what a position denotes.

## Loading and refresh

Every supported table input is optional. One `load_embed` invocation groups rows
into a complete snapshot per addressed semantic grain and returns its graph and
issues. Callers assemble complete groups before applying streamed refreshes.

Default refresh updates existing objects in place and resets bound adapter-managed
scalar fields, including absent and explicitly null values. It preserves Python
references, subclasses, consumer attributes and metadata, unbound fields, and
unsupplied child grains. Child-only loads ensure parent objects without resetting
their scalar fields. Explicit merge applies non-null values. Complementary rows
combine; conflicting populated values become unknown with a diagnostic.

Image metadata projects ROI collections by default. Valid supplied ROI collections
replace the addressed image collection in either load mode, including manual ROIs.
Missing or null input preserves the collection; an empty collection clears it;
malformed or conflicting input preserves it with an issue. Explicit ROI input takes
precedence over automatic projection. Individual ROI updates preserve the object.

Supplied linked-accession and registry-assignment sets replace on refresh and union
on merge. Absent or unbound columns preserve the sets; explicit null clears them.
Clearing an association does not delete its target object.

## Mutation and graph membership

Domain entities are mutable and can be constructed independently of a graph.
`update` changes fields and `rekey` changes identifiers while maintaining indexes
and dependent context. Child collections are read-only views; supported membership
methods keep traversal and reverse links coherent. Source claims remain source facts.

An entity belongs to at most one graph. Registration rejects distinct objects at
occupied keys. Popping a patient or exam carries its containment subtree. Exclusive
descendants retain Python identity; shared descendants needed by the retained graph
are independently copied at the movement boundary. Linked exams are associations,
not containment children; crossing links retain semantic references.

Selections are live, non-owning views. Partitions are independent owning copies,
with copied ancestor context for lower-level selections and only the selected
branches. Consumer metadata is copied; unsupported copy operations raise an error.

## Validation and evidence

Ingestion performs the parsing and representation checks needed to construct
objects and relationships. Clinical plausibility and geometric quality checks are
explicit, read-only validation operations. Loading does not invoke validation or
promise transaction rollback. Optional source diagnostics do not govern identity.

`validate` returns a `ValidationResult`. Errors make it invalid; warnings remain
valid unless `warnings_invalid=True`. Missing optional tables alone are valid.
Consumers can inspect results, partition by validation, or select with independent
predicates without imposing a study-specific rejection policy on the library.

Synthetic tests establish software behavior. Private-data, real-pixel, and downstream
scientific qualification require their own evidence. See [qualification](qualification.md)
and [loading measurements](../benchmarks/README.md) for dated local results.
