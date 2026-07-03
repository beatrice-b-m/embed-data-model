---
type: Plan
title: Unified EMBED Mammography Object System Plan
description: Architecture plan for reconciling the older ROI quadrant matcher, ROI transfer work, and the newer EMBED object model into one coherent toolkit.
tags: [mammography, embed, roi-matching, architecture, birads]
timestamp: 2026-07-03T00:00:00-04:00
kb_status: draft
---

# Unified EMBED Mammography Object System Plan

## Goal

Build one object-oriented mammography toolkit that represents the clinical reality
of breast imaging first, then layers dataset-specific ingestion and research
workflows on top of that core.

The core system should support:

- EMBED row and table adapters for patients, exams, findings, images, ROIs, and
  procedures.
- Breast-side anatomical localization using laterality, clock-face or quadrant
  descriptors, depth, distance from nipple, view position, image orientation,
  nipple landmark, posterior nipple line, and optional posterior boundary
  landmarks.
- Finding-to-ROI matching by comparing MagView-derived clinical anatomical
  expectations with image-derived ROI positions.
- ROI translation between related acquisitions, especially FFDM, DBT, and
  synthetic 2D images from combination acquisitions.
- Visualization and audit trails that make every localization or transfer
  decision inspectable.

Backwards compatibility with either current code path should not constrain the
design. The old implementations are references for behavior and vocabulary, not
APIs to preserve.

## Current Repository Assessment

### `quadrant_matching/`

This is the older working concept for matching clinical findings to ROIs. It
contains:

- A MagView/code lookup table mapping location, depth, and clock codes to
  view-specific positions.
- DataFrame ingestion for findings and images.
- Image geometry based on nipple position, posterior nipple line slope, ROI
  bounding boxes, dimensions, and orientation alignment.
- A nearest-neighbor matcher in normalized anatomical coordinate space.

Important behavior to preserve:

- Findings are resolved per image view and breast side.
- Bilateral findings are expanded to left and right side candidates.
- Image coordinates are normalized before geometry is measured.
- Matching output should expose unmatched ROIs rather than silently dropping
  them.

Issues to fix during migration:

- It depends on `hiti_preproc.alignment`, which is not present in this repo.
- Modules use local imports (`from quadrants import ...`) rather than package
  imports.
- Some comparisons use strings such as `"MLO"` even though construction uses
  enum values.
- The old two-axis `loc/depth` model collapses different anatomical axes into
  the active image view. That is useful for matching but should not be the
  clinical domain model.
- Image geometry assumes posterior extent from image edge/intercept rather than
  an explicit posterior breast/chest-wall landmark object.

### `embed_toolkit/`

This is the right direction for the unified system. It already separates
clinical concepts, imaging concepts, primitive enums, alignment, and ROIs.

Important behavior to preserve or complete:

- `Laterality`, `ViewPosition`, `ImageModality`, `PatientOrientation`, and
  `Alignment` should become the single source of orientation semantics.
- `Quadrant` already models the clinically correct three axes:
  medial/lateral, superior/inferior, and depth.
- `RoiPosition` already separates continuous image-derived position from
  discrete anatomical bins.
- `from_series` constructors are the right adapter shape for EMBED ingestion,
  but column names should not be hard-coded in each method.

Issues to fix during migration:

- Internal imports reference package paths that are not present in this tree
  (`embed_toolkit.structure...` and `embed_toolkit.elements...`).
- There is no project metadata, package `__init__.py` files, test harness, or
  import smoke test.
- `RegionOfInterest` imports `ImageBase`, but the checked-in base class is named
  `Mammogram`.
- Some BI-RADS descriptors in `clinical/findings.py` do not match the v2025
  mammography lexicon summary.
- Findings do not yet have dataframe constructors or a complete MagView/source
  code reconciliation path.

## EMBED Structural Reference

Public EMBED documentation should guide the target object structure, while the
checked-in code should win when current local conventions differ:

- EMBED overview:
  https://docs.hitilab.com/datasets/embed/overview
- EMBED dataset structure:
  https://docs.hitilab.com/datasets/embed/structure
- EMBED label assignment:
  https://docs.hitilab.com/datasets/embed/label-assignment
- EMBED ROIs:
  https://docs.hitilab.com/datasets/embed/rois

Structural implications:

- EMBED has two primary tabular sources: MagView clinical data and image
  metadata.
- MagView is the primary structured clinical source. Narrative reports are not a
  major current information source because most clinical fields are derived from
  MagView.
- MagView rows represent findings, with exam-level and patient-level fields
  repeated across rows for the same accession.
- Image metadata rows represent files/images and should remain separate from
  clinical rows until a workflow intentionally joins them.
- Clinical and metadata joins should be side-aware: clinical `side` maps to
  metadata `ImageLateralityFinal`, with bilateral or missing clinical side
  expanding to both image sides when appropriate.
- Procedures and pathology results are linked to findings, not directly to
  exams. A finding can have multiple linked procedures, such as biopsy followed
  by lumpectomy, and MagView rows may be duplicated with the same `numfind`
  while procedure details differ.
- `numfind` identifies a unique finding within an exam, but the stable finding
  identity should include accession and side as well.
- ROI coordinates are image-local boxes in `[y_min, x_min, y_max, x_max]`
  order. DBT ROIs can also carry `ROI_frames`, aligned by ROI index.

## ACR BI-RADS Validation

Public validation source:

- ACR BI-RADS page:
  https://www.acr.org/Clinical-Resources/Clinical-Tools-and-Reference/Reporting-and-Data-Systems/BI-RADS
- ACR BI-RADS v2025 Mammography Lexicon Summary Form:
  https://edge.sitecorecloud.io/americancoldf5f-acrorgf92a-productioncb02-3650/media/ACR/Files/RADS/BI-RADS/BI-RADS-Summary-Form-Mammography.pdf
- ACR BI-RADS v2025 Manual, What's New:
  https://edge.sitecorecloud.io/americancoldf5f-acrorgf92a-productioncb02-3650/media/ACR/Files/RADS/BI-RADS/BIRADS-v2025-Whats-New.pdf

The target model aligns with the v2025 mammography lexicon in these ways:

- Location should be laterality first, then quadrant or clock-face position,
  then depth and distance from nipple.
- Clock-face position is preferred when available, while quadrant location is
  still valid.
- Quadrant location includes upper outer, upper inner, lower outer, and lower
  inner.
- Retroareolar, central, and axillary tail should be represented as named
  location categories, not forced into a quadrant when that would lose meaning.
- Depth is anterior, middle, or posterior third.
- Distance from nipple is a separate measurement from categorical depth.

Required corrections for BI-RADS v2025 alignment:

- Add `LOBULATED` to `MassShape`.
- Move `MassMargin.MICROLOBULATED` out of the normalized v2025 mammography
  lexicon. It was removed as a margin descriptor and should be retained only as
  a legacy/local code value that normalizes to `INDISTINCT` when appropriate.
- Replace or alias `CalcMorphology.MILK_OF_CALCIUM` with `LAYERING` for the
  v2025 mammography lexicon.
- Move `CalcMorphology.DYSTROPHIC` out of the normalized v2025 mammography
  lexicon. It should be retained only as a legacy/local code value that
  normalizes to `COARSE` when appropriate.
- Fix `COARSE_HETERO` spelling to `COARSE_HETEROGENEOUS`.
- Represent `FINE_LINEAR_OR_FINE_LINEAR_BRANCHING`, not just `FINE_LINEAR`.
- Move `AsymType.DEVELOPING` out of the normalized v2025 mammography lexicon.
  It was discontinued as a descriptor and should be retained only as a
  legacy/local code value with change-over-time represented separately.
- Add missing first-class finding categories over time: lymph nodes, skin
  lesions, dilated ducts, associated features, implants/augmentation,
  mastectomy, and gynecomastia.

Design implication:

The toolkit should distinguish `BiradsLexiconValue` from `LocalSourceCode`.
Local/MagView/EMBED codes can be preserved losslessly, while normalized BI-RADS
concepts are exposed for clinical logic.

Source-code parsing should not live in core anatomy objects. MagView, EMBED, and
other local code systems should normalize through adapter or normalization
modules that produce core `Finding`, `AnatomicalPosition`, `Quadrant`, and
evidence objects.

## Target Package Shape

Recommended package layout:

```text
embed_toolkit/
  __init__.py
  config/
    __init__.py
    columns.py
    defaults.py
  core/
    __init__.py
    primitives.py
    anatomy.py
    birads.py
  clinical/
    __init__.py
    patients.py
    exams.py
    findings.py
    procedures.py
  imaging/
    __init__.py
    general.py
    alignment.py
    images.py
    landmarks.py
    rois.py
  adapters/
    __init__.py
    embed.py
    magview.py
    dicom.py
  workflows/
    __init__.py
    roi_transfer.py
    localization.py
    finding_roi_matching.py
  visualization/
    __init__.py
    mammogram.py
  audit/
    __init__.py
    evidence.py
```

Keep the old `quadrant_matching/` package temporarily as a reference until the
new `workflows/finding_roi_matching.py` has parity tests. Then remove or archive
it in a separate cleanup commit.

Phase zero should be package hygiene before domain migration:

- Add package `__init__.py` files and project metadata.
- Repair internal import paths so `embed_toolkit` imports cleanly.
- Add import smoke tests for the current clinical, imaging, and primitive
  modules.
- Establish the test harness before moving behavior out of `quadrant_matching/`.

## Core Domain Model

### Cohort

Represents an EMBED cohort when table-level builders need a top-level dataset
container. Most workflows can operate on patients, exams, or breast sides
directly, so this should be a lightweight aggregate rather than a required
parent for every object.

Suggested fields:

- `cohort_num`
- `patients`
- `metadata`

### Patient

Owns stable patient identity and stable demographics.

Suggested fields:

- `empi_anon`
- `cohort_num`
- `demographics`
- `exams`
- optional future longitudinal patient-level risk/history objects

### Exam

Represents one breast imaging encounter/study/accession. It should own
accession-level facts and provide aggregate access to side-scoped clinical and
imaging objects. Procedures are not primary exam children; they belong to the
findings that triggered or received the procedure/pathology result.

Suggested fields:

- `acc_anon`
- `date_anon`
- `exam_type`
- `description`
- `visit_type`
- `site_id`
- `breast_density`
- `patient_at_exam_demographics`
- `breast_sides`
- `findings`, as an aggregate view over side findings
- `images`, as an aggregate view over side images
- `risk_snapshots`, if present later

### BreastSide

Introduce this as an explicit side-scoped aggregate. This matches the EMBED
clinical/metadata hierarchy: MagView findings are side-indexed with `side`, and
metadata images are side-indexed with `ImageLateralityFinal`.

Suggested fields:

- `exam`
- `laterality`
- `findings`
- `images`
- `procedures`, as an aggregate view over linked finding procedures when useful
- `side_level_assessment`, if available
- `side_level_labels`, for study-specific labels such as cancer/no-cancer

### Finding

Represents one MagView clinical finding, preserving both source codes and
normalized BI-RADS concepts. A stable finding identity should include accession,
side, and `numfind`, because `numfind` is only unique within an exam and
procedure rows can duplicate the same finding.

Suggested fields:

- `finding_id`
- `acc_anon`
- `finding_number`
- `laterality`
- `assessment`
- `finding_type`
- type-specific descriptors
- `source_location_codes`
- `source_depth_codes`
- `clock_position`
- `quadrant`
- `depth`
- `distance_from_nipple_cm`
- `procedures`
- `pathology_events`, as an aggregate view over procedure pathology
- `raw_source`
- `normalization_warnings`

Do not force all findings into one subclass hierarchy immediately. Prefer a
stable base `Finding` with optional descriptor dataclasses by type. Subclasses
are useful only where behavior truly differs.

### Procedure / PathologyEvent

Represents a procedure and any linked pathology result for a specific finding.
This object is finding-owned, not exam-owned, though exams and breast sides can
expose aggregate views for convenience.

Suggested fields:

- `procedure_id`
- `finding`
- `laterality`
- `procedure_date_anon`
- `procedure_type`
- `pathology_diagnoses`
- `pathology_severity`
- `specimen_metadata`
- `raw_source`
- `normalization_warnings`

### MammogramImage

Represents one image metadata row: a DICOM-derived image or image-like object.
The image object is file-centered and should not directly embed MagView finding
rows. Clinical linkage happens through side-aware workflows and evidence.

Suggested fields:

- `sop_instance_uid` or local image id if available
- `path`
- `laterality`
- `view_position`
- `modality`
- `height`
- `width`
- `frames`
- `orientation`
- `alignment`
- `acquisition_group_id`
- `series_id`
- `landmarks`
- `rois`

The current name `Mammogram` is acceptable, but it should be the single image
base class. Avoid a mismatch between `ImageBase` and `Mammogram`.

### Landmarks

Landmarks should be first-class objects, not loose image attributes.

Suggested objects:

- `PointLandmark`: nipple, optional posterior endpoint, optional pectoralis
  anchor points.
- `LineLandmark`: posterior nipple line, pectoralis/chest-wall line if present.
- `BreastGeometry`: computed coordinate frame for a specific image.

The nipple model output is an input landmark source. It should carry provenance:
manual, model name/version, source column, confidence if available, and whether
it has been transformed by alignment.

### RegionOfInterest

Represents a spatial annotation on an image.

Suggested fields:

- `roi_id`
- `coords`, in EMBED `[y_min, x_min, y_max, x_max]` order
- `source_image`
- `frames`, including DBT frame indices from `ROI_frames` when available
- `origin_roi`
- `annotation_source`, such as screensave-derived, DICOM annotation-derived,
  model-derived, or manual
- `source_match_evidence`, for mappings from screensaves or derived images back
  to source mammograms
- `label`
- `metadata`

Keep geometry methods on the ROI for local operations such as centroid, area,
resize, realign, IoU, containment ratio, and center distance. Put breast
anatomical localization in a workflow/service because it needs image landmarks.
For DBT, preserve the pairing between each ROI coordinate box and its frame list.

### Anatomical Position

Use the newer three-axis model as the canonical domain model:

- `ml`: medial, central, lateral
- `si`: inferior, central, superior
- `depth`: anterior, middle, posterior

Use a separate continuous position object:

- `ml_value`
- `si_value`
- `depth_value`
- `observable_axes`
- `coordinate_frame_id`

This lets a CC image contribute mostly medial/lateral and depth, an MLO image
contribute superior/inferior and depth, and a fused breast-side position carry
all three axes.

## Adapter and Configuration Strategy

Column names should be configured once and passed through adapter objects.
Avoid repeating default column names in every `from_series` method.

Recommended pattern:

```python
@dataclass(frozen=True)
class EmbedColumnConfig:
    patient_id: str = "empi_anon"
    cohort_id: str = "cohort_num"
    accession: str = "acc_anon"
    study_date: str = "studydate_anon"
    image_path: str = "anon_dicom_path"
    image_laterality: str = "ImageLateralityFinal"
    image_view: str = "ViewPosition"
    image_orientation: str = "PatientOrientation"
    image_height: str = "Rows"
    image_width: str = "Columns"
    image_frames: str = "ImagesInAcquisition"
    image_modality: str = "FinalImageType"
    roi_coords: str = "ROI_coords"
    nipple_x: str = "nipple_x"
    nipple_y: str = "nipple_y"
    pnl_slope: str = "pnl_slope"
    finding_number: str = "numfind"
    finding_laterality: str = "side"
    finding_location: str = "location"
    finding_depth: str = "depth"
    finding_distance: str = "distance"
    finding_assessment: str = "asses"
    procedure_laterality: str = "bside"
    procedure_date: str = "procdate_anon"
    procedure_type: str = "type"
    pathology_severity: str = "path_severity"
    pathology_diagnosis_prefix: str = "path"
```

Known placeholders to verify with EMBED/local exports:

- Stable image identifier: `PLACEHOLDER_IMAGE_ID`
- Series identifier: `PLACEHOLDER_SERIES_ID`
- SOP Instance UID or anonymized equivalent: `PLACEHOLDER_SOP_INSTANCE_UID`
- Acquisition group identifier for FFDM/DBT/S2D pairing:
  `PLACEHOLDER_ACQUISITION_GROUP_ID`
- DBT frame index or slice range for ROIs: `PLACEHOLDER_ROI_FRAMES`
- ROI annotation source/model: `PLACEHOLDER_ROI_SOURCE`
- Nipple model confidence: `PLACEHOLDER_NIPPLE_CONFIDENCE`
- Posterior endpoint/chest-wall landmark columns:
  `PLACEHOLDER_POSTERIOR_ENDPOINT_X`, `PLACEHOLDER_POSTERIOR_ENDPOINT_Y`

`from_series` should accept `config: EmbedColumnConfig`, while table-level
builders should live in adapters:

- `EmbedCohortAdapter.from_dataframes`
- `EmbedPatientAdapter.from_dataframe`
- `EmbedExamAdapter.from_dataframes`
- `EmbedImageAdapter.from_dataframe`
- `EmbedFindingAdapter.from_dataframe`
- `EmbedProcedureAdapter.from_dataframe`
- `EmbedRoiAdapter.from_dataframe`

This keeps dataframe quirks out of core objects. Table-level builders should
keep MagView and metadata separated internally until they intentionally assemble
side-aware exam objects:

- Build patients and exams from repeated MagView and metadata identifiers.
- Deduplicate MagView rows into findings by accession, side, and `numfind`.
- Attach procedure/pathology rows to the corresponding finding.
- Build image and ROI objects from metadata rows.
- Assemble `BreastSide` objects by matching clinical `side` with metadata
  `ImageLateralityFinal`, expanding bilateral or missing clinical side where the
  workflow requires it.

## Workflow 1: Clinical Finding Localization

Input:

- `Finding`
- `Laterality`
- MagView/source location codes, clock-face code, depth code, distance from
  nipple

Output:

- `AnatomicalPosition`
- evidence describing which source values were used
- warnings for unrecognized, conflicting, or ambiguous codes

Rules:

- Prefer clock-face when present, but preserve quadrant location.
- Explicit depth code overrides depth implied by location code.
- Do not average unrelated codes silently. If multiple location codes disagree,
  preserve all evidence and assign confidence or ambiguity.
- Keep `central`, `retroareolar`, `subareolar`, and `axillary_tail` as semantic
  categories that can also map to approximate axes.

## Workflow 2: ROI Anatomical Localization

Input:

- `MammogramImage`
- `RegionOfInterest`
- `BreastGeometry`

Output:

- continuous image-view position
- discrete anatomical bin
- evidence with raw distances and normalized coordinates

Rules:

- All geometry should run in a declared reference alignment.
- BreastGeometry should own nipple, posterior axis, posterior distance, and
  tissue-height estimates.
- CC and MLO should be view projections of the same anatomical coordinate model,
  not separate clinical concepts.
- Missing landmarks should produce partial positions, not exceptions, unless the
  requested workflow requires that axis.

## Workflow 3: Finding-to-ROI Matching

Input:

- one `Exam` or `BreastSide`
- localized findings
- localized ROIs

Output:

- match candidates
- final assignments
- per-candidate costs
- unmatched findings and unmatched ROIs
- evidence suitable for visual review

Recommended matching model:

- Score on available axes only.
- Weight axes by discriminative value and source confidence.
- Treat exact side mismatch as impossible.
- Treat view mismatch as expected partial evidence, not an error.
- Use one-to-one assignment when the task requires unique pairing; otherwise
  allow one finding to have multiple ROIs when clinically plausible.
- Preserve the old nearest-neighbor behavior as a baseline matcher for parity
  tests, then add richer assignment logic.
- Parity tests should distinguish intentional legacy behavior from defects. In
  particular, old enum/string view mismatches and silent averaging of
  conflicting location codes should be documented as changed behavior when the
  unified workflow handles them differently.

## Workflow 4: ROI Transfer Across Related Acquisitions

Input:

- source ROI
- source image
- target image
- acquisition relationship metadata

Output:

- transferred ROI
- transform evidence
- warnings if transfer is approximate

Rules:

- For same-breast, same-view FFDM/S2D/DBT-derived pairs, start with alignment
  normalization and relative coordinate scaling.
- For DBT ROIs, preserve frame/slice ranges and mark whether a 2D ROI was
  depth-derived or projected.
- Keep ROI transfer separate from finding-to-ROI matching. Transfer answers
  "where is this annotation on a related image?" Matching answers "which report
  or MagView finding does this annotation correspond to?"

## Visualization and Audit

Visualization should work from the same evidence objects produced by workflows.

Minimum useful visual layers:

- mammogram pixels after reference alignment
- ROI boxes and centroids
- nipple landmark
- posterior nipple line
- depth-third dividers
- projected anatomical axes
- finding expected positions
- match candidate costs and final assignments

No workflow should return only a bare ID mapping. It should return a structured
result that can export a simple mapping when needed.

## Implementation Phases

### Phase 1: Make the package coherent

- Add package `__init__.py` files.
- Rename or align `ImageBase`/`Mammogram`.
- Fix internal imports.
- Move shared enums into one primitive/core module.
- Add project metadata and a minimal test harness.
- Add import smoke tests.

### Phase 2: Stabilize BI-RADS and source-code models

- Update BI-RADS descriptor enums against v2025 public summary.
- Add source-code preservation objects.
- Move MagView location/depth/clock mapping into `adapters/magview.py` or
  a dedicated normalization module, not core anatomy objects.
- Add tests for laterality-dependent clock-face mapping.

### Phase 3: Build configurable EMBED adapters

- Add `EmbedColumnConfig`.
- Convert current `from_series` methods to use config objects.
- Add table-level builders that assemble patients, exams, breast sides, images,
  findings, finding-linked procedures/pathology events, and ROIs.
- Keep MagView and metadata tables separate until side-aware joins are required.
- Flag missing column names with explicit `PLACEHOLDER_*` config fields.

### Phase 4: Port image geometry

- Create landmark and breast geometry objects.
- Port nipple/PNL/depth-third calculations from `quadrant_matching`.
- Replace enum/string mismatches with tests.
- Make missing posterior landmarks produce partial positions where possible.

### Phase 5: Port finding-to-ROI matching

- Implement baseline nearest-neighbor matcher with parity tests against the old
  behavior.
- Add structured match evidence.
- Add one-to-one assignment mode and unmatched object reporting.

### Phase 6: Restore ROI transfer

- Reintroduce ROI resize, realign, IoU, containment, and distance operations.
- Add acquisition relationship objects for FFDM, DBT, and synthetic 2D.
- Add transfer evidence and visualization hooks.

### Phase 7: Remove the old workflow

- Once parity tests and new adapters cover the old behavior, archive or remove
  `quadrant_matching/`.
- Keep the coordinate-system document and this plan as historical references.

## Test Strategy

Start with small deterministic tests before any real data is available:

- Import smoke tests for every public module.
- Enum coercion tests for laterality, view position, modality, orientation, and
  BI-RADS values.
- Clock-face tests for left and right breasts.
- MagView location/depth code tests.
- MagView finding deduplication and procedure/pathology attachment tests.
- Alignment flip tests with toy coordinates.
- ROI centroid, resize, realign, IoU, containment, and distance tests.
- BreastGeometry tests with synthetic nipple/PNL coordinates.
- Finding localization tests for clock, quadrant, depth, retroareolar, central,
  and axillary tail cases.
- Matcher tests for zero, one, and multiple findings; ties; missing axes; and
  unmatched ROIs.
- Adapter tests using tiny fixture DataFrames and custom column configs.
- Side-aware clinical/metadata join tests for left, right, bilateral, and
  missing clinical side cases.

## Clear Issues and Blockers

Not blockers, but must be handled explicitly:

- `hiti_preproc` is absent. Its alignment semantics should either be replaced by
  the checked-in `embed_toolkit.imaging.alignment` module or wrapped behind an
  optional compatibility adapter.
- The isolated environment does not include private EMBED data, so adapter tests
  must use synthetic rows and placeholder column names where needed.
- Posterior endpoint and pectoralis/chest-wall landmark columns are not present
  in this repo. The geometry layer should accept them if available and fall back
  to the current PNL slope/image-boundary approximation with an evidence warning.
- The public BI-RADS summary form is not the full licensed BI-RADS manual. Use
  it for public lexicon alignment, and keep a local extension layer for values
  present in historical MagView/EMBED exports.
- There are currently no tests, no package metadata, and no importable package
  boundary. Implementation should start there before domain behavior is moved.

## Immediate Next Step

The first code change should be a narrow package-coherence commit:

1. Add `__init__.py` files.
2. Fix internal imports to match the checked-in tree.
3. Resolve `ImageBase` versus `Mammogram`.
4. Add import smoke tests.

That gives the later domain refactor a runnable base and makes every subsequent
change measurable.
