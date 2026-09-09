# Mutable scaffold qualification

Qualified locally on 2026-09-09 against runtime revision `90bb604` and distribution
`embed-toolkit-unified==0.1.0`. Subsequent commits update documentation only.
The [target contract](mutable-scaffold-contract.md), [API decisions](mutable-scaffold-api.md),
and [implementation plan](mutable-scaffold-implementation-plan.md) define this cutover.

## Work-package acceptance

| Work | Delivered contract and evidence |
|---|---|
| W0 | D1–D8 settled in the API specification; registry identity binding approved by the maintainer. |
| W1 | Mutable clinical and imaging entities, standalone construction, tuple child views, live extension fields, procedure/pathology descendants, cycle-safe references. `test_mutable_entities.py`, `test_mutable_imaging.py`, retained clinical suites. |
| W2 | Indexed register/attach/detach/update/rekey/pop, ownership resolution, shared-copy movement boundaries, source lookups and deferred endpoints. `test_graph_membership.py`. |
| W3 | Semantic grouping independent of indexes/diagnostic keys; in-place refresh, explicit merge, unresolved pathology and patient-kind history snapshots. `test_semantic_loading.py`, `test_patient_history.py`, `test_source_diagnostics.py`. |
| W4 | SOP/path/toolkit identity separation, default metadata ROI projection, image-local replacement, derived-image isolation, supplied frame facts. `test_image_roi_refresh.py`, retained geometry tests. |
| W5 | Mutable procedure/pathology traversal, explicit linked exams and patient-scoped registry assignments with deferred resolution. `test_registry_relationships.py`. Initial registry input binds `empi_anon` and `cancer_registry_id`; payload beyond these keys is deferred by user instruction. |
| W6 | Live non-owning selections and independent owning partitions with shared descendants, ancestor context, extensions and crossing references. `test_graph_partition.py`. |
| W7 | Explicit read-only quality validation and valid/invalid partitions; ingestion accepts representable implausible facts. `test_optional_validation.py` and retained clinical/imaging tests. |
| W8 | Multi-grain full/subset/batched/deferred loads, deterministic no-unrelated-registry-scan check, measured 1×/2×/4× growth. `test_graph_scale.py` and published benchmark results. |
| W9 | Mutable public exports/docs, retired incompatible machinery with case-level test disposition, installed wheel outside checkout, complete-package Ruff/mypy, local execution of the declared Python matrix. |

## Validation

The complete suite, including the installed-wheel acceptance test, passed on every
supported minor version. No suite is ignored in these results.

| Python | Full suite |
|---|---:|
| 3.9.6 | 214 passed |
| 3.10.20 | 214 passed |
| 3.11.14 | 214 passed |
| 3.12.12 | 214 passed |
| 3.13.11 | 214 passed |

Each run executes `python -m pytest -q` from `unified-system` in its own local
environment. Python 3.13 uses the project environment; 3.9–3.12 use temporary
virtual environments with the project and test/build dependencies installed.
The wheel test builds without network build isolation, installs into a fresh
no-dependency environment, then exercises public imports with no `PYTHONPATH`
outside the checkout. It covers subclass/reference preservation, clinical
traversal, metadata/ROI loading, rekey/source lookup, optional validation, independent
partitioning and subtree movement. The wheel includes `py.typed`.

On Python 3.13:

```bash
.venv/bin/python -m ruff check src/embed_toolkit tests examples benchmarks
.venv/bin/python -m mypy
.venv/bin/python -m pytest -q
.venv/bin/python -m benchmarks.graph_loading --base 100 --repeats 3
```

Ruff passed. Mypy passed over all 35 runtime source files with normal import
following and Python 3.9 syntax targeting. All Python code blocks in the current
package README executed together successfully through public imports.

The final synthetic benchmark used 100/200/400 patients, 600/1,200/2,400 rows,
1,200/2,400/4,800 objects, and 1,399/2,799/5,599 edges. Full-load medians were
0.1696/0.3416/0.6889 seconds (2.01× and 2.02× per doubling), below the provisional
3× gate. Peak memory grew roughly linearly; fixed-patient updates remained near
16 microseconds as unrelated objects quadrupled. See [benchmark methodology and
results](../unified-system/benchmarks/README.md).

## Review resolution and qualification boundaries

Fresh implementation/validation agents and a bounded fresh review were integrated
under the coordinate-implementation workflow. Final review regressions cover
position-aligned depth flags, stale source indexes after updates/pop, and live
interpretation identity after finding/exam rekeys. Integration also verified that
derivative metadata cannot replace original ROIs and explicit ownership clearing
cannot leave stale parent membership.

The review suggestion to discard a path conflicting with an explicit SOP was not
adopted: D5 keeps locations separate from source identity. The supplied path remains
a location alias of the explicit UID, while the conflicting parsed SOP is never
registered as an alternate source UID. This distinction is documented and tested.

The GitHub workflow retains Python 3.9–3.13 and whole-package static checks. Its
matrix was exercised locally; no remote GitHub Actions run was triggered or claimed.
These macOS runs do not independently establish Linux-specific behavior. There is
no support-range change.

Private EMBED tables, real pixels and full private-dataset scale were not qualified.
The user explicitly authorized identity-only registry binding; further registry
payload/schema work remains deferred. Synthetic fixtures establish scaffold
behavior, not clinical/scientific validity. Source diagnostics remain optional.
No release, tag, remote publication, or matching/transfer consumer port was performed.
Those ports require separate repositories and are later work in the plan.

[Legacy test disposition](mutable-scaffold-test-disposition.md) records each retired
test's replacement contract or intentional retirement. The historical transaction,
locator and patch-recipe expectations are removed rather than silently skipped.
