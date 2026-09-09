# Mutable scaffold loading measurements

Measured 2026-09-09 against `90bb604` (wheel version `0.1.0`).
Python 3.13.11, macOS-26.5.1-arm64-arm-64bit-Mach-O.

```bash
uv run --frozen python -m benchmarks.graph_loading --base 100 --repeats 3
```

Each patient contributes six input rows: four repeated finding/procedure MagView
rows, one image row containing two equal ROI slots, and one registry entry.
Expected objects per patient: one patient, one exam, two findings, two procedures,
two pathology bundles, one image, two ROIs, and one registry entry (12 total).
Edges count actual parent associations once, including exam/registry edges, plus
each reciprocal linked-exam pair once. The last exam has no linked successor.

| Patients | Rows | Objects | Edges | Full load (s) | Peak bytes | Retained bytes |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 600 | 1200 | 1399 | 0.1696 | 3,406,849 | 2,803,382 |
| 200 | 1200 | 2400 | 2799 | 0.3416 | 6,610,054 | 5,411,034 |
| 400 | 2400 | 4800 | 5599 | 0.6889 | 13,188,302 | 10,602,370 |

| Patients | Fixed-patient update (µs) | One-patient subset (ms) | Batched load (s) | Late registry resolution (ms) |
|---:|---:|---:|---:|---:|
| 100 | 16.00 | 0.434 | 0.0297 | 0.764 |
| 200 | 15.81 | 0.442 | 0.0598 | 1.620 |
| 400 | 15.79 | 0.470 | 0.1190 | 3.138 |

All values are medians of three repetitions. Full loads use `tracemalloc`; input
fixture construction is excluded from both time and memory. Retained memory is
measured after loading; peak includes transient load allocations. Other operations
are timed without tracing, so their absolute timings are not directly comparable
to the traced full-load column. Fixed updates average 50 same-patient refreshes per
repetition; subset setup uses prebuilt slices. Deferred resolution excludes graph
construction and times only the later registry input.

Full-load doubling ratios were 2.01× and 2.02×, below the provisional 3× gate.
Peak and retained object memory grew roughly linearly. Fixed-patient update time
stayed near 16 µs as unrelated data quadrupled. These measurements support the
deterministic regression that prohibits iteration of unrelated registry dictionaries
during a fixed update; timing is diagnostic, not a fragile absolute CI threshold.

Batches contain 25 complete patient groups. A refresh invocation is one snapshot:
callers must assemble all rows for a repeated semantic grain before applying it.
Arbitrarily splitting one object across refresh calls changes the snapshot and is
not a streaming merge. Full and batched cardinalities are checked at every size.

These are synthetic scale results, not qualification on the full private EMBED
dataset, real pixels, or every source schema. Representative private-data testing
requires data supplied through an authorized path. Registry payload beyond the
approved patient/registry-ID mapping is deferred.
