---
type: Evaluation
title: Legacy Removal Evaluation
description: Completion record for removing root-level legacy EMBED toolkit trees.
tags: [mammography, embed, legacy, parity, retirement]
timestamp: 2026-07-06T00:00:00-04:00
kb_status: draft
---

# Legacy Removal Evaluation

> **Historical completion snapshot.** The root-tree retirement remains in
> effect, but workflow and audit parity suites named below were subsequently
> removed or isolated during the lightweight framework recovery. Current
> invariant ownership is mapped in
> [lightweight-framework-test-traceability.md](../lightweight-framework-test-traceability.md).

The root-level `embed_toolkit/` and `quadrant_matching/` directories have been
removed. The retained unified package under `unified-system/src/embed_toolkit`
owns the current implementation, parity behavior, import isolation, and tests.

## Result

Removal was mechanically feasible after the project accepted the retirement gate
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

## Updated References

References to root-level `embed_toolkit/` and `quadrant_matching/` now describe
former legacy paths, historical behavior, or import-isolation guardrails rather
than present reference code.

Completed documentation edits:

- `docs/legacy-retirement-policy.md`: marked the retirement gate accepted and
  describe the legacy trees as removed rather than retained.
- `docs/parallel-implementation-orchestration-plan.md`: updated final-batch
  notes that previously said to retain the legacy trees until parity was
  accepted.
- `docs/unified-system-plan.md`: updated Phase 9 from a future retirement step
  to a completed retirement decision.
- `unified-system/README.md`: removed language that says root-level legacy
  directories are present reference code.

Test note:

- Keep import-isolation coverage in `unified-system/tests/unit/test_imports.py`;
  only adjust wording if needed. The blocker prefixes remain useful after
  deletion because they prevent reintroducing stale dependencies.

## Outcome

The removal commit deletes `embed_toolkit/` and `quadrant_matching/`, updates
the documentation references above, and reruns `uv run pytest` from
`unified-system/`.
