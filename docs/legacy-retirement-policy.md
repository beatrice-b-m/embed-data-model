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
- Legacy BI-RADS and source codes: local or discontinued values should be
  preserved losslessly as source codes while normalized clinical logic uses the
  current unified BI-RADS/source-value model.

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
