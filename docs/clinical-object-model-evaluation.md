# Clinical object model evaluation

> **Current resolution status (2026-08-24): Resolved.** The evaluation below is
> retained as the historical baseline that motivated the implementation. This
> addendum and the
> [resolution plan](clinical-object-model-resolution-plan.md) describe the
> governing current state.

## Resolution addendum: current assessment

All implementation defects enumerated in the historical evaluation have been
resolved. The current model establishes the following behavior:

- **Missing clinical identifiers:** blank patient, accession, and finding
  identifiers never become shared sentinels. Strict builds reject unsafe
  identity; audit builds retain distinct `SourceOccurrence` evidence without
  manufacturing clinical objects.
- **Independent pathology:** `PathologyObservation` and
  `PathologyDiagnosis` are distinct grains. Pathology survives without a
  resolved procedure and uses explicit, provenance-bearing attribution links.
- **Imaging interpretation:** `ImagingInterpretation` is a distinct
  finding-owned grain. Assessment and recommendation retain independent
  availability state and source provenance instead of collapsing into a bare
  finding attribute.
- **Incomplete procedures:** incomplete procedure surfaces remain unresolved
  source evidence and cannot inflate resolved procedure multiplicity. Complete
  procedures use governed identity and explicit finding links.
- **Exam-side ownership:** each `BreastSide` is a persistent,
  accession-scoped child of an exam. Findings and images attach independently;
  bilateral findings project to both unilateral sides.
- **Clinical/image hierarchy:** assembly owns exam-to-image and side-to-image
  containment, validates cross-table patient evidence, and exposes
  finding-to-image results only as candidate projections.
- **Pathology meaning and time:** descriptor occurrences, diagnosis state,
  procedure occurrence date, and pathology report documentation date are
  separate. Temporal endpoints are not fallback-coalesced.
- **Field coverage:** every configured repository field has an explicit state
  and physical-source boundary in a `ProfileContract`; repository coverage
  makes no claim of external-catalog completeness.
- **Finding anatomy:** configured location, depth, and distance values are
  normalized into finding anatomy while raw source evidence is retained;
  unknown or conflicting values remain reviewable through structured warnings.
- **Patient/exam reconciliation:** exam invariants use conflict-aware,
  source-attributed reconciliation. Patient observations retain changing
  values, and selection requires an explicit dated policy rather than first-row
  retention.
- **ROI identity:** built-in V1c ingestion creates synthetic `RoiLocator`
  values scoped to an image plus an explicit dataset or materialization source
  scope. These are serialization locators, not durable source identities;
  plural DBT frame evidence remains preserved.

Breadth that the configured sources cannot establish is intentionally gated by
the full `ProfileContract`, rather than represented speculatively. For the
clinical `internal-v2` contract, imaging episode and risk-assessment semantics
are unresolved, radiology reports are unavailable, pathology specimens are
unsupported, and external-catalog completeness remains unresolved. Custom
profiles must supply their own exact contract.

The only runtime dataset profile is `internal-v2`. Clinical V2 and the paired
V1c image-metadata artifact use distinct kind-specific contracts under that
shared profile identity; V1c names the image artifact version, not a profile.

Current verification on 2026-08-24:

- 143 focused resolution tests passed across identity/source ledgers,
  procedures, pathology, graph ownership and assembly, reconciliation, field
  coverage, ROI locators, and profile contracts.
- The complete suite passed: 456 tests.

---

## Historical baseline (preserved evaluation)

The remainder of this document records the pre-resolution assessment. Its
external catalog counts and 203-test result are historical evidence, not claims
about the current repository.

Date: 2026-08-24  
Reference profile: `embed_context_internal` / `internal-v2`

## Executive assessment

The toolkit has a sound core for the narrow path
`Patient -> Exam -> Finding <-> Procedure -> PathologyEvent` and separately
`Image -> RegionOfInterest`. It correctly uses accession-plus-finding-number
identity, preserves the synthetic `-9` finding sentinel, keeps finding and biopsy
laterality distinct, supports multiple procedures per finding, validates the
internal 0-through-5 pathology severity domain, and records ROI matching as an
inference rather than ground truth.

It is not yet a complete representation of the internal-v2 clinical model. The
largest limitations are structural rather than cosmetic:

1. Missing patient and finding identifiers are converted into shared synthetic
   identities, which can merge unrelated clinical records.
2. Pathology can only exist beneath a recognized procedure, even though the
   semantic model permits pathology attribution when procedure identity is
   absent or incomplete.
3. `BreastSide` is not identified within an exam and is reconstructed only from
   findings.
4. Imaging episode, interpretation, report, risk-assessment, pathology
   observation, and pathology diagnosis grains are absent or collapsed.
5. Exam-to-image hierarchy is replaced by a direct side-aware finding-to-image
   projection, which is stronger than the supported clinical relationship.
6. The generic object classes expose only a small fraction of the governed
   fields, and the default adapter populates fewer still.

The model is therefore **usable for carefully scoped finding/ROI workflows, but
not yet safe as a lossless or general-purpose clinical graph**.

## Semantic reference model

The MCP catalog exposes 14 clinical objects:

| Object | Semantic grain | Internal-v2 status |
|---|---|---|
| Patient | one patient | Complete MagView identity through `empi_anon`; longitudinal only within represented data |
| Breast-imaging episode | one clinical imaging episode | Unresolved; optional same-episode accession links do not define complete episode boundaries |
| Imaging exam | one exam/accession | Complete MagView identity through `acc_anon` |
| Breast side | one unilateral side within an exam | Partial; `(acc_anon, side)` with bilateral/null finding-side projection to both unilateral sides |
| Imaging finding | one represented finding | Supported, partial binding; identity is `(acc_anon, numfind)`, with side as an attribute |
| Imaging interpretation | one finding-level interpretation | Partial; assessment and recommendation are co-located and have no independent identity/time |
| Radiology report | one represented report version | Concept only in internal-v2; no profile binding |
| Image | one acquired image instance | Supported for internal V1c, which is narrower than clinical V2 |
| Region of interest | one region on exactly one image | Geometry supported; no durable ROI identity or cross-image correspondence |
| Procedure | one represented procedure association | Supported when `(patient, procedure date, type, biopsy side)` is complete |
| Pathology specimen | one putative specimen association | Unresolved and explicitly unsuitable for current specimen-level operations |
| Pathology observation | one descriptor occurrence | Partial; represented in `path1` through `path10`, without independent identity |
| Pathology diagnosis | one represented diagnosis state | Partial; row-level inverse severity derived from descriptor slots |
| Risk assessment | one represented risk row | Concept only; output scale, model version, horizon, and probability semantics are unresolved |

The core hierarchy and adjacent associations are:

```text
Patient
├── Breast-imaging episode (optional/incomplete)
│   └── Imaging exam (one or more)
└── Imaging exam (zero or more)
    ├── Breast side (one or more)
    │   └── Imaging finding (zero or more; bilateral projection allowed)
    │       ├── Imaging interpretation (zero or one)
    │       └── Procedure (zero or more, many-to-many attribution)
    │           └── Pathology observation (zero or more)
    │               └── Pathology diagnosis state (derived)
    ├── Image (profile-specific cardinality)
    │   └── Region of interest (zero or more; exactly one source image)
    ├── Radiology report version (zero or more)
    └── Risk assessment (zero or more)
```

This is not a strict tree. Finding-to-procedure and finding-to-pathology
attribution are optional and many-to-many. Most internal-v2 physical bindings
are repeated co-location in one wide MagView table, not foreign-key edges. The
MCP guardrails consequently require explicit grouping, multiplicity,
attribution, and time policies whenever moving among finding, side, exam,
episode, and patient grains.

## Toolkit coverage by object

| Object | Toolkit representation | Assessment |
|---|---|---|
| Patient | `Patient` with ID, exams, sex, birth year, metadata | **Partial.** Correct parent ownership, but few governed demographics and no as-of policy for varying patient attributes. |
| Imaging episode | None | **Absent.** `linkedaccession_anon` and same-episode semantics are not represented. |
| Imaging exam | `Exam` with accession, patient, date, description, findings | **Partial.** Correct identity and finding containment; most exam fields, images, reports, risk, and episode membership are absent. |
| Breast side | Derived `BreastSide(laterality, findings)` | **Weak.** It lacks accession/exam identity, images, and independent side facts, and exists only when findings generate it. |
| Imaging finding | `Finding` | **Moderate/strong class, partial adapter.** Identity and repeated-row conflict handling are correct; most modality descriptors and governed location fields are not populated by the builder. |
| Imaging interpretation | `Finding.assessment` only | **Weak.** Recommendation, independent grain, and documentation/availability semantics are absent. |
| Radiology report | None | **Absent**, but the internal-v2 catalog also has no physical binding. |
| Image | `MammogramImage` | **Partial.** Core geometry and identity fields exist, but only a subset of V1c metadata is modeled and images are not children of exams/sides. |
| Region of interest | `RegionOfInterest` and analyst-defined `RoiGroup` | **Partial.** Geometry normalization is strong; source count/depth-derivation invariants and non-durable identity semantics are incomplete. |
| Procedure | `Procedure` | **Moderate/strong.** The governed identity and plural finding references are present; incomplete rows and first-reference fields remain problematic. |
| Pathology specimen | None | **Appropriately absent** until the source specimen surface is validated. |
| Pathology observation | Collapsed into `PathologyEvent.descriptors` | **Weak.** Descriptor occurrence and diagnosis state cannot be addressed independently. |
| Pathology diagnosis | Collapsed into `PathologyEvent.severity` and generic diagnosis fields | **Partial.** Severity governance is good, but diagnosis grain, derivation, and time meanings are conflated. |
| Risk assessment | None | **Absent**, consistent with the lack of a validated internal-v2 binding but incomplete as a portable clinical model. |
| Cohort | `Cohort` | Useful analytic container, but not a clinical object in the MCP model. |

## Priority findings

### Critical: missing identifiers create false identities

The builder maps every blank patient identifier to `"UNKNOWN_PATIENT"` and
every blank finding number to `"0"` in
`unified-system/src/embed_toolkit/adapters/embed.py`. Multiple unrelated rows
therefore become one patient or one finding. This also lets the procedure
registry merge unrelated procedures under the synthetic patient when date,
type, and side happen to agree.

This conflicts with the catalog's complete patient identity binding and its
accession-scoped finding identity. Only `-9` is a governed synthetic finding
number. Missing identity should remain unresolvable, be rejected, or be carried
as an explicitly non-mergeable row occurrence; it should not become a shared
clinical identity.

### High: pathology is dropped unless a procedure is recognized

`_procedure_from_row` returns before `_pathology_from_row` when procedure ID,
type, and date are all absent. A row with populated `path1`-`path10` or
`path_severity` but no recognized procedure surface therefore loses its
pathology representation.

The semantic model has independent exam-, side-, finding-, patient-, and
procedure-to-pathology-observation relations. Procedure attribution is optional,
and physical co-location does not prove procedure identity. Pathology
observations need an independent representation before optional attribution to
a procedure.

### High: repeated incomplete procedure rows are promoted to distinct procedures

Complete procedures are correctly interned by patient, procedure date, type,
and biopsy side. Incomplete procedures are instantiated once per physical row,
even when repeated rows are identical. The existing test suite explicitly
expects two identical incomplete rows to produce two procedures.

The MCP model says an incomplete tuple cannot establish procedure identity; it
does not say that each repeated wide row is a distinct procedure. Since wide-row
multiplicity is not clinical multiplicity, incomplete occurrences should remain
unresolved occurrences or use an explicit reconciliation policy rather than
being counted as distinct procedures.

### High: breast-side grain has no exam identity or independent existence

`BreastSide` contains only laterality and findings. `Exam.breast_sides` creates
new objects on demand and drops sides without findings. This cannot represent
the governed `(accession, unilateral side)` grain, side-level images, or a side
with no explicit finding row. Two left sides from different exams have no direct
identity except through their contained findings.

`BreastSide` should be an owned exam child with accession/exam identity and
separate collections for findings and images. Bilateral finding occurrences
should project to both unilateral side objects without creating a third
bilateral identity.

### High: direct finding-to-image join overstates the supported edge

The catalog supports `ImagingExam -> Image` through accession. It explicitly
states that image laterality is not automatically finding or procedure
laterality. `join_findings_to_images` instead returns all same-accession,
compatible-side images as a `FindingImageJoin`.

That result is useful as a candidate image set, but it is not a sourced clinical
finding-to-image attribution. Rename or type it as a candidate projection, keep
the exam-to-image hierarchy explicit, apply the patient identifier as a
cross-table consistency check, and retain the V1c-versus-V2 coverage boundary.

### High: pathology observation, diagnosis, and time semantics are conflated

`PathologyEvent` combines descriptor occurrences, a diagnosis string, severity,
malignancy, and one generic `event_date`. The internal-v2 model separates:

- procedure occurrence time (`procdate_anon`, verified),
- pathology-report documentation time (`pdate_anon`, provisional),
- specimen collection time (unsupported), and
- downstream availability time (unsupported).

The default adapter does not bind `pdate_anon`, and a generic event date cannot
express which temporal endpoint it represents. Distinct `PathologyObservation`
and `PathologyDiagnosis` types plus explicitly named temporal fields would
preserve the source semantics without inventing a universal diagnosis date.

### Medium: adapter coverage is much narrower than the object vocabulary

The MCP model relates 12 patient features, 25 exam features, 50 finding
features, 13 procedure features, 33 image features, and substantial pathology
characterization fields. The builder currently populates only a core subset.
Notably, configured finding location, depth, and distance columns are not mapped
into `Finding.anatomical_position`, `source_location_codes`, or
`source_depth_codes`; they remain available only inside `raw_source_fields`.

This preserves raw evidence but does not provide a complete normalized clinical
object. Coverage should be explicit per field so consumers can distinguish
unmodeled, unresolved, unavailable, and null values.

### Medium: repeated patient and exam attributes lack governed reconciliation

The builder retains values from the first row used to construct a patient or
exam. It does not flag later exam-level conflicts, even though internal-v2 says
exam-level attributes must be invariant and conflicts are data-quality errors.
For patient attributes, variation may be real or erroneous and any current/latest
selection requires an explicit as-of time. Arbitrary first-row retention is not
a governed policy.

### Medium: generated ROI identifiers look more durable than the source permits

Internal V1c has no per-ROI identifier; position in aligned per-image
collections is only a serialization locator. The adapter generates
`{image_id}:roi:{index}` and downstream `RoiGroup` APIs describe required IDs as
stable. These locators are useful within one materialization, but should be
typed or labeled as dataset-version-scoped synthetic locators rather than
source identities. Cross-image groups are acceptable only as explicit external
or inferred assertions, which `grouping_basis` already helps record.

## Important strengths

- `Finding.identity` correctly uses accession plus finding number, with side as
  an attribute, and conflicting repeated side values are surfaced.
- The `-9` synthetic contralateral-negative finding is preserved as a governed
  record type rather than treated as an ordinary observation.
- Procedure laterality remains independent from finding laterality.
- Complete procedure identity matches the maintained internal-v2 tuple and can
  be shared across multiple finding references.
- Pathology severity rejects code 6, retains raw values and descriptor evidence,
  and does not silently turn null pathology into benign disease.
- ROI coordinates are correctly normalized from inclusive source maxima to
  half-open internal boxes, and plural DBT frames are retained.
- Finding-to-ROI matching is scoped to one accession and unilateral side,
  records algorithm/configuration provenance, distinguishes inferred,
  ambiguous, and abstained states, and does not label inferred attribution as
  validated ground truth.

## Recommended target shape

Preserve a normalized graph with explicit object identity and optional edges:

1. Make `Patient`, `ImagingEpisode`, `Exam`, `BreastSide`, `Finding`,
   `Interpretation`, `Procedure`, `PathologyObservation`, `PathologyDiagnosis`,
   `Image`, and `RegionOfInterest` distinct grains.
2. Represent source rows as evidence/occurrences, not as clinical object
   identity. Never merge missing identifiers into a shared sentinel.
3. Keep many-to-many edges in explicit link records with provenance,
   confidence/status, and optional source locators.
4. Separate containment (`patient-exam`, `exam-side`, `exam-image`) from
   attribution (`finding-procedure`, `finding-pathology`, inferred
   finding-ROI).
5. Name temporal endpoints by meaning and never fallback-coalesce them.
6. Expose aggregation results only with a declared policy. For inverse pathology
   severity, the minimum represented valid severity is most severe, but
   side/exam/patient reductions are analyst-defined and null remains unknown.
7. Treat episode, specimen, report, risk, and longitudinal outcome support as
   capability-gated. Their concepts can exist without pretending that the
   internal-v2 profile supplies complete instances or linkages.

## Verification performed

- Queried all 14 MCP clinical objects, their 24 semantic relationships, object
  and relationship bindings, temporal semantics, pathology aggregations,
  coverage records, guardrails, and the main MagView/V1c/ROI provenance
  contexts.
- Inspected the clinical, image, ROI, adapter, configuration, and matching
  implementations and their unit tests.
- Ran 47 focused unit tests covering clinical objects, EMBED adapters, images,
  and ROI groups, followed by the complete 203-test suite; all passed.
- Reproduced the four critical representation behaviors directly: shared
  `UNKNOWN_PATIENT`, shared finding `0`, dropped pathology without a procedure,
  and duplicated incomplete procedures.
