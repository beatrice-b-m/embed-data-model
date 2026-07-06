---
type: Policy
title: Legacy Retirement Policy
description: Retired legacy policy and intentional parity decisions for the former root-level EMBED toolkit trees.
tags: [mammography, embed, legacy, parity, retirement]
timestamp: 2026-07-04T00:00:00-04:00
kb_status: draft
---

# Legacy Retirement Policy

## Decision

The root-level `embed_toolkit/` and `quadrant_matching/` trees have been
removed after acceptance of unified-system parity coverage. They are not runtime
dependencies of `unified-system/`, and new unified-system code must not import
from their former module paths.

The legacy trees were used to derive expected behavior, vocabulary, fixtures,
and parity tests. They are no longer candidates for active maintenance; fixes
for unified behavior should land under `unified-system/`.

## Parity Ownership

Current parity coverage is owned by the unified-system modules and tests that
exercise the replacement behavior:

- Source values and normalized clinical vocabulary:
  `core/birads.py`, `adapters/magview.py`, `tests/unit/test_birads.py`, and
  `tests/unit/test_magview.py`.
- Laterality, clock-face, quadrant, and depth semantics:
  `core/anatomy.py`, `workflows/finding_localization.py`,
  `tests/unit/test_anatomy.py`, and
  `tests/unit/test_finding_localization.py`.
- Alignment, landmark geometry, posterior boundary handling, and ROI
  localization: `imaging/alignment.py`, `imaging/landmarks.py`,
  `workflows/roi_localization.py`, `tests/unit/test_alignment.py`,
  `tests/unit/test_imaging.py`, and `tests/unit/test_roi_localization.py`.
- Finding-to-ROI matching and unmatched object reporting:
  `workflows/finding_roi_matching.py`,
  `tests/unit/test_finding_roi_matching.py`, and
  `tests/unit/test_legacy_parity.py`.
- ROI transfer, patch extraction, visualization, and audit exports:
  `workflows/roi_transfer.py`, `workflows/patch_extraction.py`,
  `visualization/mammogram.py`, `audit/export.py`, and their focused unit
  tests.
- Import isolation: `tests/unit/test_imports.py` proves the package is imported
  from `unified-system/src` and rejects former legacy import paths.

## Intentional Parity Decisions

These differences from the legacy code are intentional and should be documented
in parity tests or review notes when relevant:

- Missing `hiti_preproc`: `quadrant_matching/` depended on
  `hiti_preproc.alignment`, which is not present in this repository. The unified
  system replaces that dependency with local alignment and image-orientation
  semantics under `unified-system/src/embed_toolkit/imaging/alignment.py`.
- Legacy import problems: root-level legacy modules contained local or stale
  package imports, including `from quadrants import ...` and package paths such
  as `embed_toolkit.structure...` or `embed_toolkit.elements...`. The unified
  system treats those as legacy defects, not APIs to preserve.
- Enum/string mismatches: legacy comparisons sometimes use string literals such
  as `"MLO"` even when objects were constructed with enum values. Unified code
  should normalize view, laterality, modality, and orientation values at
  boundaries and test that comparisons use the normalized representation.
- Collapsed anatomical axes: the old `loc/depth` model maps location into the
  active image view for matching. That behavior is useful as a baseline matcher,
  but the unified clinical model keeps medial/lateral, superior/inferior, and
  depth as separate anatomical axes.
- Posterior-boundary assumptions: legacy geometry can infer posterior extent
  from the image edge or posterior nipple line intercept. Unified geometry
  should prefer explicit posterior breast or chest-wall landmarks when present,
  fall back to a documented approximation when absent, and return partial
  localization with evidence warnings when an axis cannot be observed.
- Unmatched ROI reporting: legacy matching behavior could drop non-selected ROI
  candidates from the final result surface. Unified matching must preserve
  unmatched finding and ROI identifiers in structured result objects so audit,
  visualization, and export code can review them.
- Legacy BI-RADS and source codes: local or discontinued values should be
  preserved losslessly as source codes while normalized clinical logic uses the
  current unified BI-RADS/source-value model.
- Source-code preservation: MagView, EMBED, and other local source values are
  evidence attached by adapters or workflow results, not core anatomy concepts.
  Unknown, conflicting, or legacy-only codes should be retained with warnings
  instead of being silently coerced or discarded.

## Reference-Only Rules

- Do not add runtime imports from former root-level `embed_toolkit/` or
  `quadrant_matching/` paths into `unified-system/`.
- Do not make new tests depend on those packages importing successfully.
- Keep parity fixtures small and synthetic; copy only the minimal behavior
  needed to assert a unified-system invariant.
- If a legacy behavior is preserved, identify the unified module and test that
  now owns it.
- If a legacy behavior is changed, identify whether it was a defect, an
  architectural correction, or a source-code normalization decision.

## Retirement Gate

The retirement gate has been accepted based on parity coverage for:

- MagView location, depth, clock-face, laterality, and bilateral expansion.
- Alignment and coordinate normalization behavior needed by localization and
  matching.
- ROI localization, finding-to-ROI matching, unmatched ROI reporting, and
  representative transfer behavior.
- Import isolation proving `unified-system/` does not depend on former
  root-level legacy packages.

With that gate met, the legacy trees were removed from the repository. Their
behavioral ownership now lives in the unified modules and tests listed above.
