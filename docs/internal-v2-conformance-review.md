# Internal V2 dataset-profile conformance review

Date: 2026-08-24  
Reference: `embed_context_internal` MCP, profile `internal-v2`  
Scope: current runtime implementation under `unified-system/`

## Executive assessment

The toolkit is substantially conformant for its declared core clinical graph:
patient and exam identity, accession-plus-finding-number identity, repeated
wide-row evidence, synthetic contralateral-negative findings, independent
finding and biopsy laterality, procedure identity, row-grain pathology,
distinct temporal meanings, exam/image containment, and inclusive ROI geometry
are modeled with appropriate provenance and conflict handling.

It is not fully conformant to the dataset profile. Three high-severity gaps can
change the meaning or permitted use of V1c image/ROI data: cross-image ROI
transfer invents a default correspondence, DBT depth derivation is mislabeled,
and annotation-only screen captures are not gated from ordinary image use.
There are also medium-severity gaps in ROI collection validation, contract
enforcement, and representation of the V1c-versus-clinical-V2 coverage boundary.

The correct overall characterization is **strong core clinical conformance,
partial image/ROI conformance, and intentionally partial field breadth**. The
toolkit should not yet be treated as a lossless implementation of the full
`internal-v2` profile or as a safe source of default cross-image ROI
correspondence.

## Findings

### High: ROI transfer invents cross-image correspondence by default

`AcquisitionRelationship.from_images()` sets `related=True` when two images
share any populated accession, study UID, or series UID. `transfer_roi()` then
returns a successful projected ROI whenever patient, breast, and view also
match.

The MCP's `internal-v2.roi-context` states that V1c represents no ROI
correspondence across images. It also states that `acquisition_group_id` is not
an ROI-correspondence representation. The implementation is more permissive
still: it does not require the acquisition-group identifier and treats a shared
accession alone as relationship evidence.

Impact: an ROI can be transferred to another same-accession image and reported
as a successful result even though the dataset supplies no source
correspondence. The `approximate_transfer` information warning does not undo
the successful relationship assertion.

Evidence:

- `unified-system/src/embed_toolkit/workflows/roi_transfer.py:75-119`
- `unified-system/src/embed_toolkit/workflows/roi_transfer.py:158-275`
- `unified-system/src/embed_toolkit/workflows/roi_transfer.py:313-322`
- MCP claims `internal-v2.roi-context#roi-cross-image-correspondence-absent`
  and `internal-v2.v1c-metadata-context#acquisition-grouping`

Recommended resolution: require an explicit caller-supplied relationship or
explicit inference policy. Do not derive clinical ROI correspondence from
accession, study, series, or acquisition-group co-membership. If geometric
projection remains supported, label it as analyst-defined and keep its result
distinct from a relationship-backed transfer.

### High: model-derived DBT depth is mislabeled as source supplied

The profile represents `ROI_depth_derived` as a boolean collection aligned
one-for-one with `ROI_coords` and `ROI_frames`. A true flag means an in-house
model inferred the DBT z/depth coordinates after transfer of radiologist-origin
2D coordinates.

The column configuration has no depth-derivation field. During ROI construction,
every DBT ROI with frame indices receives
`RoiDepthFrameProvenance.SOURCE_SUPPLIED`; the `DERIVED` state is never selected
from V1c input.

Impact: downstream audit output reverses a clinically relevant provenance
distinction and can present model-inferred depth as source-supplied depth.

Evidence:

- `unified-system/src/embed_toolkit/config/defaults.py:12-30`
- `unified-system/src/embed_toolkit/config/columns.py:15-66`
- `unified-system/src/embed_toolkit/adapters/embed.py:2831-2934`
- `unified-system/src/embed_toolkit/imaging/roi_provenance.py:130-226`
- MCP feature `internal-v2.roi.depth_derivation_flag_collection`

Recommended resolution: bind `ROI_depth_derived`, parse it as a collection
aligned to coordinates and frames, select `DERIVED` for true entries, and
record a named derivation method such as the profile's in-house DBT depth model.

### High: annotation-only image classes can enter ordinary image workflows

The MCP distinguishes source DICOM modality, source image type, and the
pipeline-derived `FinalImageType`. `ROI_SS` and `ROI_SSC` are secondary
screen-capture artifacts retained solely to extract and transfer annotations;
they are explicitly not intended for other image analyses.

The toolkit maps `FinalImageType` into a field called `image_modality` and a
source-neutral enum containing only 2D, DBT, synthetic 2D, and unknown.
`ROI_SS`, `ROI_SSC`, and the residual `other` class therefore become unknown
`MammogramImage` instances, but are still retained and eligible for ordinary
exam containment and image-facing workflows.

Impact: annotation-transfer artifacts or non-mammographic rows can be treated
as ordinary mammograms. The model also loses the actual source `Modality`
distinction while presenting a derived acquisition class as modality.

Evidence:

- `unified-system/src/embed_toolkit/config/defaults.py:19-24`
- `unified-system/src/embed_toolkit/core/primitives.py:95-119`
- `unified-system/src/embed_toolkit/adapters/embed.py:2152-2246`
- `unified-system/src/embed_toolkit/adapters/embed.py:2411-2527`
- MCP feature `internal-v2.image.derived_image_type`
- MCP claims `internal-v2.v1c-metadata-context#image-type-distinctions` and
  `#roi-screen-capture-purpose`

Recommended resolution: represent source modality and derived image type as
separate fields. Give annotation-only classes an explicit type and exclude them
from general image analysis by default while retaining them as provenance for
ROI extraction.

### Medium: tandem ROI collection and declared-count invariants are incomplete

The profile requires `num_ROI`, `ROI_coords`, `ROI_frames`, and
`ROI_depth_derived` to agree. Empty collections represent zero ROIs. The adapter
derives the ROI count solely from parsed coordinates and validates only the
coordinate/frame relationship for DBT. It neither reads `num_ROI` nor validates
the depth-derivation collection.

Impact: malformed V1c rows can build successfully when the declared ROI count
or depth-flag length disagrees with the coordinate collection. The resulting
`RoiSourceCount` is marked as coordinate-derived even when the source provides
an explicit count.

Evidence:

- `unified-system/src/embed_toolkit/adapters/embed.py:2831-2934`
- `unified-system/src/embed_toolkit/adapters/embed.py:3012-3122`
- `unified-system/src/embed_toolkit/imaging/roi_provenance.py:102-127`
- MCP features `internal-v2.image.region_of_interest_count`,
  `internal-v2.roi.coordinate_collection`,
  `internal-v2.roi.frame_index_collection`, and
  `internal-v2.roi.depth_derivation_flag_collection`

Recommended resolution: bind all four physical columns, validate their tandem
cardinality, preserve zero explicitly, and use `SOURCE_DECLARED` count basis
when `num_ROI` is valid.

### Medium: built-in profile contracts describe states but do not gate ingestion

The built-in clinical contract marks `birth_year` unavailable because Internal
V2 exposes an anonymized birth date rather than a governed birth-year
occurrence. Nevertheless the Internal V2 builder accepts a generic `birth_year`
alias and creates a birth-year observation. More generally, built-in contracts
accept generic compatibility aliases such as `patient_id`, `AccessionNumber`,
`assessment`, and `procedure_date` even when those names are not physical
bindings in `magview_all_cohorts_PACS_v2_anon`.

Impact: data can be projected under the authoritative `internal-v2` identity
from fields that the contract marks unavailable or that are not exact profile
bindings. The serialized contract can therefore disagree with the objects in
the same build result.

Evidence:

- `unified-system/src/embed_toolkit/config/profile_contracts.py:92-252`
- `unified-system/src/embed_toolkit/config/profile_contracts.py:599-616`
- `unified-system/src/embed_toolkit/adapters/embed.py:822-860`
- `unified-system/src/embed_toolkit/adapters/embed.py:1291-1359`
- `unified-system/tests/unit/test_patient_attributes.py:148-195`
- MCP table binding `internal-v2:magview_all_cohorts_PACS_v2_anon`

Recommended resolution: use exact physical bindings for built-in profiles and
reserve aliases for explicit custom contracts. Make field-coverage state an
ingestion gate so unavailable/unmodeled fields cannot produce normalized
objects under that contract.

### Medium: unmatched clinical exams lose the V1c coverage meaning

The profile says V1c covers the EMBEDv1 exam/patient set and is narrower than
clinical V2. A clinical V2 exam without a V1c row is outside current extraction
coverage; it is not thereby an exam without images.

The graph exposes every clinical exam without a containment link as an
`unmatched_exam`, with no reason or coverage state. It does not preserve whether
the exam belongs to EMBEDv1/V1c scope, so consumers cannot distinguish an
outside-coverage exam from an in-scope reconciliation failure.

Impact: `unmatched_exam_references` is easy to misuse as a no-image cohort or
image-availability indicator, exactly the inference prohibited by the profile.

Evidence:

- `unified-system/src/embed_toolkit/adapters/embed.py:466-473`
- `unified-system/src/embed_toolkit/adapters/embed.py:643-649`
- `unified-system/src/embed_toolkit/adapters/embed.py:2529-2543`
- MCP claim `internal-v2.v1c-metadata-context#coverage-is-not-image-absence`
- MCP guardrail
  `internal-v2.guardrail.absent-image-metadata-is-not-image-absence`

Recommended resolution: replace the bare unmatched-exam collection with an
explicit reconciliation/coverage record. At minimum distinguish outside V1c
scope, expected in-scope but absent metadata, and other linkage failures, and
document that none is direct evidence of image absence.

## Conformant strengths

- Clinical V2 and image V1c are correctly treated as two kind-specific artifacts
  under one `internal-v2` profile identity.
- Patient and exam identifiers are release-scoped, and conflicting accession to
  patient associations are rejected rather than split into multiple valid exams.
- Finding identity is `(accession, finding number)`; laterality is an attribute,
  repeated physical rows preserve source evidence, and conflicts are surfaced.
- Finding number `-9` is explicitly classified as a synthetic contralateral
  negative instead of an ordinary finding.
- Null finding side projects bilaterally, while null biopsy side remains unknown.
- Complete procedures use the maintained patient/date/type/biopsy-side tuple;
  incomplete tuples remain unresolved occurrences rather than distinct resolved
  procedures.
- Pathology descriptor occurrences remain row/slot scoped; severity is limited
  to 0 through 5; invalid 6 and descriptor-without-severity states are surfaced.
- Exam, procedure, and provisional pathology-report dates remain separately
  named and are not fallback-coalesced.
- Image identity is derived from the `anon_dicom_path` filename, cross-table
  patient identity is checked, and missing image identity is an error.
- ROI coordinates are converted correctly from inclusive source maxima to
  half-open internal bounds, plural DBT frames are retained, and frame bounds
  are checked when frame count is represented.
- Finding/image joins are exposed as candidates rather than sourced attribution;
  multi-finding ROI matching is explicitly labeled inferred/ambiguous/abstained.
- Episode, report, risk, specimen, and external-catalog completeness limitations
  are declared rather than speculatively modeled.

## Verification

- Queried the MCP through `discover`, then followed profile contexts, features,
  guardrails, coverage records, physical tables, and semantic relationships.
- Inspected the runtime configuration, adapters, clinical/image/ROI objects,
  reconciliation graph, ROI transfer and finding/ROI matching workflows, and
  their unit tests.
- Ran the complete suite from `unified-system/`: **459 tests passed**.

Passing tests do not negate the findings above: the current tests encode the
implemented contract but do not cover the omitted or misclassified MCP profile
semantics identified in this review.
