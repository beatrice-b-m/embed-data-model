---
type: Plan
title: Parallel Unified System Implementation Orchestration Plan
description: Coordination plan for using an orchestration agent and subagents to implement the unified EMBED mammography toolkit.
tags: [mammography, embed, orchestration, parallel-implementation]
timestamp: 2026-07-03T00:00:00-04:00
kb_status: draft
---

# Parallel Unified System Implementation Orchestration Plan

## Purpose

This document summarizes the parallel implementation status of the unified
EMBED mammography toolkit described in
[`unified-system-plan.md`](unified-system-plan.md).

It is intended for an orchestration agent that will assign scoped work to
subagents, review their outputs, prevent file-ownership conflicts, and ensure
each completed unit is tested and committed independently.

## Current Starting Point

The implementation has already created:

- `unified-system/` with a `src/` package layout.
- Import smoke tests isolated from the legacy root-level `embed_toolkit/`.
- Source-neutral core primitives in `core/primitives.py`.
- Source-neutral breast anatomy axes and clock-face mapping in
  `core/anatomy.py`.
- Focused unit tests for the core, adapter, clinical, imaging, workflow,
  visualization, and audit-export modules.

The remaining work should continue inside `unified-system/`. The legacy
root-level `embed_toolkit/` and `quadrant_matching/` trees are reference-only
sources for behavior, vocabulary, and parity review. They are not runtime
dependencies of `unified-system/` and should not be imported by the new package.

## Implementation Status

The first four implementation batches have landed at a high level:

- Foundation modules: core BI-RADS/source values, MagView normalization,
  clinical domain objects, imaging domain objects, and audit result models.
- Adapters and geometry: EMBED column configuration, local alignment/breast
  geometry, and EMBED table builders.
- Localization, transfer, and extraction workflows: finding localization, ROI
  localization, ROI transfer, and patch extraction.
- Matching, visualization, and exports: finding-to-ROI matching, mammogram
  visualization helpers, and audit export helpers.

The focused final batch is now limited to parity/retirement work: verify
selected legacy behaviors against the new implementation, document intentional
behavior changes, and decide the repository policy for the root-level legacy
trees.

## Orchestration Principles

- Assign work by file ownership to minimize merge conflicts.
- Keep each subagent focused on one coherent module or workflow.
- Require tests with every implementation unit.
- Keep source-specific parsing out of core domain objects.
- Keep workflow services separate from intrinsic domain-object behavior.
- Return structured evidence/result objects from workflows instead of bare ID
  mappings or hidden mutation.
- Stage files selectively and commit after each completed logical unit.
- After every commit, verify with `git log --oneline -3`.

## First Parallel Batch: Foundation Modules

Status: implemented at a high level in `unified-system/`; retain this section
as the original ownership record.

These tasks can be started simultaneously because they touch mostly independent
modules.

### Agent A: Core BI-RADS And Source Values

Owned files:

- `unified-system/src/embed_toolkit/core/birads.py`
- `unified-system/tests/unit/test_birads.py`

Scope:

- Add normalized BI-RADS v2025 mammography descriptor enums.
- Add local or legacy source-code preservation objects.
- Represent known legacy values separately from normalized lexicon values.
- Test corrections such as `LOBULATED`, `LAYERING`,
  `COARSE_HETEROGENEOUS`, legacy `MICROLOBULATED`, legacy `DYSTROPHIC`, and
  discontinued `DEVELOPING`.

### Agent B: MagView Location Normalization

Owned files:

- `unified-system/src/embed_toolkit/adapters/magview.py`
- `unified-system/tests/unit/test_magview.py`

Scope:

- Implement MagView location, depth, and clock-code normalization.
- Use `core.anatomy` objects as outputs.
- Preserve raw source codes and warnings for unknown or conflicting values.
- Test laterality-aware clock mapping and explicit-depth precedence.

### Agent C: Clinical Domain Objects

Owned files:

- `unified-system/src/embed_toolkit/clinical/cohorts.py`
- `unified-system/src/embed_toolkit/clinical/patients.py`
- `unified-system/src/embed_toolkit/clinical/exams.py`
- `unified-system/src/embed_toolkit/clinical/findings.py`
- `unified-system/src/embed_toolkit/clinical/procedures.py`
- Matching unit tests under `unified-system/tests/unit/`

Scope:

- Implement `Cohort`, `Patient`, `Exam`, `BreastSide`, `Finding`,
  `Procedure`, and `PathologyEvent`.
- Make procedures finding-owned, with exam and breast-side aggregate views only
  where useful.
- Test finding identity, side aggregation, procedure attachment, and basic
  serialization-friendly behavior.

### Agent D: Imaging Domain Objects

Owned files:

- `unified-system/src/embed_toolkit/imaging/images.py`
- `unified-system/src/embed_toolkit/imaging/landmarks.py`
- `unified-system/src/embed_toolkit/imaging/rois.py`
- Matching unit tests under `unified-system/tests/unit/`

Scope:

- Implement `MammogramImage`, image landmarks, `BreastGeometry`, and
  `RegionOfInterest`.
- Keep intrinsic ROI geometry methods on the ROI object: centroid, area,
  resize, realign, IoU, containment ratio, and center distance.
- Preserve DBT ROI frame pairing.
- Test image identity, landmark ownership, ROI geometry, and DBT frame
  preservation.

### Agent E: Audit Evidence And Result Models

Owned files:

- `unified-system/src/embed_toolkit/audit/evidence.py`
- `unified-system/src/embed_toolkit/audit/results.py`
- `unified-system/tests/unit/test_audit.py`

Scope:

- Add reusable evidence, warning, and result containers.
- Add result shapes for localization, matching, transfer, and patch extraction.
- Keep these models serializable and independent from concrete workflow service
  implementations.
- Test serialization and evidence payload preservation.

## Second Parallel Batch: Adapters And Geometry

Status: implemented at a high level in `unified-system/`; retain this section
as the original ownership record.

### Agent F: EMBED Column Configuration

Owned files:

- `unified-system/src/embed_toolkit/config/columns.py`
- `unified-system/src/embed_toolkit/config/defaults.py`
- `unified-system/tests/unit/test_columns.py`

Scope:

- Implement `EmbedColumnConfig`.
- Include known placeholder fields for identifiers, DBT frames, ROI source,
  nipple confidence, and posterior landmarks.
- Test default and custom column-name behavior.

### Agent G: Alignment And Breast Geometry

Owned files:

- `unified-system/src/embed_toolkit/imaging/alignment.py`
- Breast geometry portions of `imaging/landmarks.py`, if needed
- Matching tests under `unified-system/tests/unit/`

Scope:

- Replace missing `hiti_preproc` behavior with local alignment semantics.
- Add coordinate and image realignment helpers.
- Implement breast geometry from nipple, posterior nipple line, and optional
  posterior/chest-wall landmarks.
- Test flips, depth thirds, and partial geometry when posterior landmarks are
  missing.

### Agent H: EMBED Table Builders

Owned files:

- `unified-system/src/embed_toolkit/adapters/embed.py`
- Adapter tests under `unified-system/tests/unit/` or
  `unified-system/tests/integration/`

Scope:

- Build patients, exams, breast sides, findings, procedures, pathology events,
  images, and ROIs from synthetic rows.
- Keep MagView clinical rows and image metadata rows separate until a workflow
  intentionally joins them.
- Test finding deduplication, procedure/pathology attachment, ROI construction,
  and side-aware joins for left, right, bilateral, and missing clinical side.

## Third Parallel Batch: Localization, Transfer, And Extraction

Status: implemented at a high level in `unified-system/`; retain this section
as the original ownership record.

### Agent I: Finding Localization

Owned files:

- `unified-system/src/embed_toolkit/workflows/localization.py`
- Finding-localization tests

Scope:

- Implement `FindingLocalizer`.
- Convert source clinical location evidence into anatomical expectations.
- Prefer clock-face when present while preserving quadrant and source evidence.
- Test clock, quadrant, depth, retroareolar, central, axillary tail,
  ambiguity, and warning behavior.

### Agent J: ROI Localization

Owned files:

- `unified-system/src/embed_toolkit/workflows/localization.py`, or a dedicated
  ROI-localization module if the orchestration agent splits it
- ROI-localization tests

Scope:

- Implement `RoiLocalizer`.
- Convert image-local ROI geometry plus `BreastGeometry` into continuous and
  discrete anatomical positions.
- Return partial positions when landmarks are missing and the requested axis is
  not observable.

### Agent K: ROI Transfer

Owned files:

- `unified-system/src/embed_toolkit/workflows/roi_transfer.py`
- ROI-transfer tests

Scope:

- Add acquisition relationship objects for FFDM, DBT, and synthetic 2D.
- Implement transfer between related same-breast, same-view acquisitions using
  alignment normalization and relative scaling.
- Preserve DBT frame or slice metadata and warnings for approximate transfers.

### Agent L: Patch Extraction

Owned files:

- `unified-system/src/embed_toolkit/workflows/patch_extraction.py`
- Patch-extraction tests

Scope:

- Implement image patch extraction from image/ROI pairs.
- Support padding behavior without placing workflow logic on ROI objects.
- Return structured extraction results with evidence.

## Fourth Parallel Batch: Matching, Visualization, And Exports

Status: implemented at a high level in `unified-system/`; retain this section
as the original ownership record.

### Agent M: Finding-To-ROI Matching

Owned files:

- `unified-system/src/embed_toolkit/workflows/finding_roi_matching.py`
- Matching tests

Scope:

- Implement `FindingRoiMatcher`.
- Score available anatomical axes only.
- Treat exact side mismatch as impossible.
- Support one-to-one assignment and unmatched finding/ROI reporting.
- Add baseline parity tests against selected legacy behavior.

### Agent N: Visualization

Owned files:

- `unified-system/src/embed_toolkit/visualization/mammogram.py`
- Visualization tests with synthetic images

Scope:

- Render mammogram pixels, ROI boxes, centroids, landmarks, posterior nipple
  line, depth thirds, finding expectations, and match evidence.
- Use workflow evidence objects as visual input.

### Agent O: Audit Export Helpers

Owned files:

- Additional helpers in `unified-system/src/embed_toolkit/audit/`
- Export tests

Scope:

- Add simple mapping/export helpers that preserve links to structured evidence.
- Ensure localization, matching, transfer, and patch extraction results can be
  serialized for review.

## Final Batch: Parity And Legacy Retirement

Status: remaining focused final-batch work. Matching, localization,
visualization, and export modules now exist under `unified-system/`, so this
batch should avoid broad feature work and concentrate on parity review,
documentation, and retirement policy.

### Agent P: Legacy Parity Review

Owned files:

- Parity fixtures and tests under `unified-system/tests/`
- Documentation updates under `docs/`

Scope:

- Add or confirm targeted parity coverage derived from `quadrant_matching/` for
  representative anatomy, alignment, localization, and matching behavior.
- Document intentional behavior changes versus legacy defects, especially where
  `unified-system/` corrects missing dependencies, import issues, or collapsed
  anatomical axes in the old implementation.
- Decide whether root-level `embed_toolkit/` and `quadrant_matching/` should be
  archived, removed, or retained as historical reference.
- Keep legacy trees reference-only during this decision. Do not introduce new
  runtime imports from those trees into `unified-system/`.

## Review Checklist For The Orchestration Agent

For each subagent output:

- Confirm it stays within assigned file ownership or clearly justifies any
  shared-file edits.
- Confirm it does not import from legacy runtime trees.
- Confirm tests cover both expected behavior and important edge cases.
- Confirm workflow code returns structured result/evidence objects.
- Confirm domain objects contain only intrinsic behavior.
- Run `python3 -m pytest` from `unified-system/`.
- Stage files selectively.
- Commit using `type(scope): subject` with an explanatory body.
- Run `git log --oneline -3` after each commit.

## Integration Passes

After each parallel batch, the orchestration agent should perform a small
integration pass:

- Reconcile package exports in `__init__.py` files.
- Normalize naming across modules.
- Remove duplicate helper types.
- Add cross-module smoke tests where imports or shared result models interact.
- Run the full `unified-system/` test suite.
- Commit integration cleanup separately from subagent feature commits.
