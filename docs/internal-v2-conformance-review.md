# Internal V2 framework and dataset-profile reassessment

Date: 2026-08-25

> **Historical review — superseded.** This review remains evidence for source
> meanings migrated into the canonical graph. Current architecture and public
> boundaries are governed by
> [lightweight-framework-architecture-review.md](lightweight-framework-architecture-review.md).
Reference: `embed_context_internal` MCP, profile `internal-v2`
Scope: current runtime implementation under `unified-system/`

## Intended framework boundary

This toolkit is a minimal, lightweight object framework. It translates the
EMBED clinical and imaging hierarchy into reusable Python objects and preserves
enough source meaning for project-specific analysis to be built on top. It is
not intended to select cohorts, prescribe scientific policies, discard
unwanted-but-valid source records, or limit analysts to relationships supplied
directly by EMBED.

The appropriate review criteria are therefore:

1. **Preserve source meaning.** Core profile features and their provenance
   should not be silently lost or misclassified.
2. **Expose capability and missingness.** Objects should remain representable
   when optional workflow attributes are absent, and workflows should skip,
   abstain, or return structured limitations where possible.
3. **Keep analysis policy explicit.** Project-specific matching, transfer,
   filtering, and aggregation are legitimate extensions when labeled as
   derived behavior rather than EMBED-supplied truth.
4. **Avoid unnecessary rejection.** Redundant helper fields need not control
   construction when primary source evidence is usable.

Under these criteria, the toolkit's architecture is well aligned with its core
intention. The original review overstated several intentional analytical
extensions as dataset-conformance defects.

## Actual findings

### High: V1c DBT depth-derivation provenance is lost

The MCP represents `ROI_depth_derived` as a boolean collection aligned with
`ROI_coords` and `ROI_frames`. A true entry means an in-house model inferred
that ROI's DBT z/depth placement after radiologist-origin 2D coordinates were
transferred.

The toolkit has a suitable `RoiDepthFrameProvenance.DERIVED` state, but the
column is not configured or read. Every DBT ROI with frame indices is labeled
`SOURCE_SUPPLIED`.

This is a source-fidelity defect rather than a missing analytical policy. It
can cause scientists to treat model-derived depth as source-supplied depth.

Evidence:

- `unified-system/src/embed_toolkit/adapters/embed.py:2831-2934`
- `unified-system/src/embed_toolkit/imaging/roi_provenance.py:130-226`
- MCP feature `internal-v2.roi.depth_derivation_flag_collection`

Minimal resolution: bind `ROI_depth_derived`, preserve one aligned flag per
ROI, and select `DERIVED` with a named derivation method when true. Alignment
with the coordinate collection is necessary here because the flag changes the
meaning of each constructed ROI; this does not require making `num_ROI`
authoritative.

### High: ROI-transfer relatedness ignores the acquisition group

For Emory data, a populated matching `acquisition_group_id` is the available
metadata guarantee that two images were captured within the same acquisition
and are spatially aligned for ROI transfer. A shared accession, study UID,
series UID, protocol, view, or combination of those attributes does not
establish that relationship.

The adapter correctly maps `acquisition_group_id` into
`MammogramImage.coordinate_frame_id`, but the default relationship inference
does not inspect that attribute. Instead, `_has_shared_acquisition_context()`
returns true when any of accession number, study UID, or series UID matches.
`AcquisitionRelationship.from_images()` assigns that result to `related`, and
`can_transfer` can consequently authorize transfer between different
acquisition groups.

The unit tests encode the same overly broad rule: their image factory has no
coordinate/acquisition-group argument, supplies the same accession and study
UID by default, and asserts that the resulting images are related and
transferable.

Evidence:

- `unified-system/src/embed_toolkit/adapters/embed.py:846-859`
- `unified-system/src/embed_toolkit/adapters/embed.py:2204-2224`
- `unified-system/src/embed_toolkit/workflows/roi_transfer.py:75-119`
- `unified-system/src/embed_toolkit/workflows/roi_transfer.py:313-322`
- `unified-system/tests/unit/test_roi_transfer.py:24-59`
- `unified-system/tests/unit/test_roi_transfer.py:97-119`

Minimal resolution: infer `related=True` only when both images have the same
populated `coordinate_frame_id` sourced from `acquisition_group_id`. Patient,
breast, and view can remain additional transfer preconditions, while accession,
study, and series identifiers can remain descriptive evidence but must not
establish relatedness. If a caller-supplied override remains available for a
project-specific algorithm, label it explicitly as a caller assertion and
distinguish it from profile-guaranteed acquisition-group eligibility.

### High: source construction is strict by default rather than fail-soft

Both source builders instantiate `BuildPolicy()` when the caller supplies no
policy, and `BuildPolicy` defaults to `STRICT`. Any error-severity build issue
then raises immediately. The existing `AUDIT` path already embodies the desired
framework behavior: it retains source occurrences, records structured issues,
and constructs the safe objects it can.

This default is not an MCP mismatch, but it conflicts with the stated core
intention that incomplete or unsuitable objects fail softly and remain
available for inspection and filtering.

Evidence:

- `unified-system/src/embed_toolkit/core/build_policy.py:16-45`
- `unified-system/src/embed_toolkit/adapters/embed.py:871-969`
- `unified-system/src/embed_toolkit/adapters/embed.py:1983-2149`

Minimal resolution: make audit/fail-soft construction the public default, or
provide clearly named fail-soft entry points while reserving strict mode for
explicit validation jobs. Identity-free rows still must not manufacture domain
objects; they can remain source occurrences with issues, as audit mode already
does.

### Medium: derived image type is not preserved as its own feature

The MCP distinguishes source DICOM `Modality`, source DICOM image type, and the
pipeline-derived `FinalImageType`. The latter includes `2D`, `3D`, `cview`,
`ROI_SS`, `ROI_SSC`, and `other`.

The toolkit maps `FinalImageType` into `MammogramImage.modality`, whose enum
represents only 2D, DBT, synthetic 2D, and unknown. Consequently `ROI_SS`,
`ROI_SSC`, and `other` lose their specific type on the domain object, although
the raw row remains in `SourceOccurrence`.

The appropriate resolution is not to discard these images. Their specific
derived type should be preserved so analysts can include or filter them. Source
modality and derived acquisition/image type should remain distinct attributes.

Evidence:

- `unified-system/src/embed_toolkit/config/defaults.py:19-24`
- `unified-system/src/embed_toolkit/core/primitives.py:95-119`
- `unified-system/src/embed_toolkit/imaging/images.py:18-38`
- `unified-system/src/embed_toolkit/adapters/embed.py:2152-2246`
- MCP feature `internal-v2.image.derived_image_type`
- MCP claim `internal-v2.v1c-metadata-context#image-type-distinctions`

Minimal resolution: add a source-preserving derived-image-type attribute with
an open vocabulary or raw fallback. Keep the existing acquisition-kind helper
if workflows benefit from it. Offer predicates or ordinary filterable values;
do not embed a default exclusion policy.

### Medium: unknown acquisition type prevents otherwise usable ROI geometry

ROI geometry itself is image-local and can remain useful even when acquisition
type or DBT depth semantics are unresolved. The adapter currently returns an
error when an image has coordinates but `ImageModality.UNKNOWN`, and
`RoiSourceProvenance` rejects unknown modality entirely. Under the default
strict policy this aborts the build; under audit it retains the image and raw
row but drops the ROI object.

This is more opinionated than the intended framework boundary. Missing
modality should disable modality-dependent workflows or frame interpretation,
not necessarily prevent representation of valid coordinates.

Evidence:

- `unified-system/src/embed_toolkit/adapters/embed.py:2853-2863`
- `unified-system/src/embed_toolkit/imaging/roi_provenance.py:184-206`

Minimal resolution: permit image-local ROI geometry with unresolved modality
and unresolved/not-interpreted depth provenance. Workflows requiring known 2D,
DBT, or frame semantics should expose that requirement and skip clearly when it
is unmet.

### Medium: `birth_year` contradicts the built-in Internal V2 contract

The built-in clinical field inventory includes `birth_year` while its own
coverage declaration marks the field unavailable. The builder nevertheless
accepts a generic `birth_year` alias and creates normalized observations under
the `internal-v2` contract.

Internal V2 supplies an anonymized birth date subject to the patient-specific
date shift, not a governed birth-year feature suitable for this object surface.
This field should not be part of the built-in profile.

Evidence:

- `unified-system/src/embed_toolkit/config/profile_contracts.py:35-56`
- `unified-system/src/embed_toolkit/config/profile_contracts.py:599-616`
- `unified-system/src/embed_toolkit/adapters/embed.py:1291-1359`
- `unified-system/tests/unit/test_patient_attributes.py:148-195`

Minimal resolution: remove `birth_year` from the built-in Internal V2 field
inventory, defaults, adapter projection, and tests. Generic or project-specific
profiles may add a birth-year observation through their own explicit contract
if they genuinely supply one.

## Intentional behavior that is not a defect

### Finding-to-ROI matching

The MCP says V1c supplies no explicit ROI-to-finding link and no reliable
individual attribution when several findings exist on one accession side. It
does not prohibit project-specific inference.

`FindingRoiMatcher` appropriately treats matching as an algorithm: it scopes
inputs to one accession and unilateral side, records algorithm/configuration
versions and evidence, and returns inferred, ambiguous, or abstained states.
It does not rewrite the source clinical graph as if EMBED supplied the link.

This is a good example of the intended extensible framework design.

### ROI transfer as an extension workflow

ROI transfer is a legitimate analytical workflow for this extensible toolkit;
the framework does not need to remove it merely because EMBED does not supply a
cross-image ROI identity. The workflow also appropriately treats same patient,
breast, and view as explicit conditions and returns a structured skipped result
when its eligibility predicate is false.

That architectural legitimacy does not make every default eligibility rule
valid. The current inference of `related` from accession, study, or series
equality is the high-priority defect described above. Default relatedness must
come from the acquisition group. Any more permissive project algorithm should
be an explicit extension with its own evidence, rather than being presented as
the profile-backed guarantee.

### `num_ROI` is not authoritative

`num_ROI` is a redundant convenience/count field. The coordinate collection is
the primary evidence that an image has represented ROIs, and the adapter derives
objects from those coordinates. Rejecting useful ROI geometry because the
helper count disagrees would conflict with the framework's preservation-first
goal.

No mandatory validation or construction change is recommended. The raw value
is already retained in the source occurrence. A project that cares about data
quality can compare the helper count with constructed ROIs as an optional audit
or filtering operation.

The aligned `ROI_depth_derived` flags are different: they alter per-ROI
provenance and therefore must be read when the ROI is constructed.

### Unmatched exams are valid clinical objects

An exam without an attached V1c image row remains useful clinical data. The
graph correctly preserves such exams rather than discarding them. The name
`unmatched_exams` describes graph reconciliation state; it need not imply that
the exam had no images clinically.

No exclusion or richer coverage taxonomy is required in the minimal core. A
short documentation guardrail stating that unmatched means "no link in these
inputs" would be sufficient if misuse becomes a concern.

### Compatibility aliases and partial field breadth

Accepting configurable aliases is consistent with a reusable parent framework.
Aliases should not be restricted to exact physical column names when projects
may adapt preprocessed tables or custom profiles. The actual issue is the
specific `birth_year` contradiction under the built-in profile, not aliasing as
a general mechanism.

Similarly, the toolkit need not normalize every MCP-cataloged column. Its
repository field inventories explicitly limit their completeness claims, and
raw source occurrences preserve unmodeled input. Project-specific subclasses or
adapters can add breadth without expanding the core.

## Strengths under the revised criteria

- Clinical V2 and image V1c use distinct kind-specific contracts under one
  `internal-v2` profile identity.
- Missing identifiers do not become shared synthetic objects; audit mode keeps
  unresolvable rows as provenance-bearing source occurrences.
- Finding identity, `-9` classification, repeated-row multiplicity, and
  laterality-role distinctions conform to the profile.
- Complete and incomplete procedures, pathology descriptor occurrences,
  severity, and distinct temporal meanings are modeled without manufacturing
  specimen or outcome truth.
- Optional image attributes use `None` or explicit unknown enum states, and
  image/clinical reconciliation preserves unmatched objects.
- ROI coordinates are normalized correctly, plural DBT frame evidence is
  retained, and workflow results carry structured evidence and warnings.
- Finding/image projections are candidates, while finding/ROI attribution is
  visibly algorithmic rather than source-supplied.
- Raw source rows and build issues remain available for project-specific audits
  and filters.

## Revised priority

The minimal remediation set is:

1. Preserve and apply `ROI_depth_derived` per ROI.
2. Infer ROI-transfer relatedness only from a populated matching
   `acquisition_group_id`, with any project override explicitly identified.
3. Make fail-soft/audit construction the ordinary public path.
4. Preserve the full derived image-type value, including `ROI_SS`, `ROI_SSC`,
   and `other`, without default filtering.
5. Allow coordinate-only ROI representation when modality-dependent semantics
   are unresolved.
6. Remove `birth_year` from the built-in Internal V2 surface.

`num_ROI` enforcement, automatic image-type exclusion, mandatory V1c coverage
classification, and removal of analytical matching/transfer workflows are not
recommended. The ROI-transfer workflow should be retained with its default
relatedness inference corrected.

## Verification basis

- Queried the MCP through `discover`, then followed profile contexts, features,
  guardrails, coverage records, physical tables, and semantic relationships.
- Inspected the runtime configuration, build policy, adapters, clinical/image/ROI
  objects, reconciliation graph, ROI transfer and finding/ROI matching workflows,
  and their unit tests.
- The complete suite passed during the original review: **459 tests passed**.

This reassessment changes the review criteria and issue classification; it does
not claim that the implementation remediations above have already been made.
