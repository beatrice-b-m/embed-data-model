---
type: Evaluation
title: Legacy Removal Evaluation
description: Readiness review for removing root-level legacy EMBED toolkit trees.
tags: [mammography, embed, legacy, parity, retirement]
timestamp: 2026-07-06T00:00:00-04:00
kb_status: draft
---

# Legacy Removal Evaluation

The root-level `embed_toolkit/` and `quadrant_matching/` directories are no
longer runtime dependencies of the unified implementation. The retained
unified package under `unified-system/src/embed_toolkit` owns the current
implementation, parity behavior, import isolation, and tests.

## Result

Removal is mechanically feasible once the project accepts the retirement gate
in `docs/legacy-retirement-policy.md`. No blocking runtime references were
found outside the legacy trees themselves.

## Evidence

- `unified-system/pyproject.toml` packages only modules discovered from
  `unified-system/src`.
- `unified-system/tests/unit/test_imports.py` blocks imports from
  `quadrant_matching`, `hiti_preproc`, `quadrants`,
  `embed_toolkit.elements`, and `embed_toolkit.structure`.
- Unified parity coverage exists for MagView location normalization, bilateral
  and missing-side expansion, alignment, ROI localization, finding-to-ROI
  matching, unmatched ROI reporting, ROI transfer, visualization, audit export,
  and import isolation.
- The full unified-system test suite passes with `170 passed`.

## Remaining References

The remaining references to root-level `embed_toolkit/` and `quadrant_matching/`
are policy, planning, README, and import-isolation test references. They should
be updated as part of the removal commit so the repository no longer describes
deleted directories as present reference code.

Expected documentation edits:

- `docs/legacy-retirement-policy.md`: mark the retirement gate accepted and
  describe the legacy trees as removed rather than retained.
- `docs/parallel-implementation-orchestration-plan.md`: update final-batch
  notes that currently say to retain the legacy trees until parity is accepted.
- `docs/unified-system-plan.md`: update Phase 9 from a future retirement step
  to a completed retirement decision.
- `unified-system/README.md`: remove language that says root-level legacy
  directories are present reference code.

Expected test edit:

- Keep import-isolation coverage in `unified-system/tests/unit/test_imports.py`;
  only adjust wording if needed. The blocker prefixes remain useful after
  deletion because they prevent reintroducing stale dependencies.

## Recommendation

Proceed with a separate removal commit that deletes `embed_toolkit/` and
`quadrant_matching/`, updates the documentation references above, and reruns
`uv run pytest` from `unified-system/`.
