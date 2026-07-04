---
type: Policy
title: Legacy Retirement Policy
description: Reference-only policy and intentional parity decisions for the root-level EMBED toolkit trees.
tags: [mammography, embed, legacy, parity, retirement]
timestamp: 2026-07-04T00:00:00-04:00
kb_status: draft
---

# Legacy Retirement Policy

## Decision

The root-level `embed_toolkit/` and `quadrant_matching/` trees are retained as
historical reference only until unified-system parity coverage is accepted. They
are not runtime dependencies of `unified-system/`, and new unified-system code
must not import from them.

The legacy trees may be used to derive expected behavior, vocabulary, fixtures,
and parity tests. They should not be repaired as a prerequisite for the unified
implementation, and fixes for unified behavior should land under
`unified-system/`, not in the root-level legacy packages.

The accepted final-batch decision is to keep both root-level legacy trees in the
repository as read-only historical references until the retirement gate below is
accepted. They are not candidates for active maintenance during parity work.

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
- Import isolation: `tests/unit/test_imports.py` proves the new package is
  imported from `unified-system/src` rather than the root-level legacy package.

## Intentional Parity Decisions

These differences from the legacy code are intentional and should be documented
in parity tests or review notes when relevant:

- Missing `hiti_preproc`: `quadrant_matching/` depends on
  `hiti_preproc.alignment`, which is not present in this repository. The unified
  system replaces that dependency with local alignment and image-orientation
  semantics under `unified-system/src/embed_toolkit/imaging/alignment.py`.
- Legacy import problems: root-level legacy modules contain local or stale
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

- Do not add runtime imports from root-level `embed_toolkit/` or
  `quadrant_matching/` into `unified-system/`.
- Do not make new tests depend on those packages importing successfully.
- Keep parity fixtures small and synthetic; copy only the minimal behavior
  needed to assert a unified-system invariant.
- If a legacy behavior is preserved, identify the unified module and test that
  now owns it.
- If a legacy behavior is changed, identify whether it was a defect, an
  architectural correction, or a source-code normalization decision.

## Retirement Gate

The root-level legacy trees can be archived or removed only after the
orchestration agent accepts parity coverage for:

- MagView location, depth, clock-face, laterality, and bilateral expansion.
- Alignment and coordinate normalization behavior needed by localization and
  matching.
- ROI localization, finding-to-ROI matching, unmatched ROI reporting, and
  representative transfer behavior.
- Import isolation proving `unified-system/` does not depend on root-level
  legacy packages.

Until that gate is met, keep the trees in place as read-only references for
review and fixture derivation.
