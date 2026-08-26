# Graph loading baseline

Run `uv run python -m benchmarks.graph_loading` from `unified-system/` to
measure a 2,000-patient load and 10,000 keyed lookups. The harness uses
`tracemalloc`; timings are diagnostic rather than pass/fail thresholds.

Initial 2026-08-26 baseline on the development Mac with Python 3.13:

| Raw policy | Load | Lookups | Current traced memory | Peak traced memory |
|---|---:|---:|---:|---:|
| `retain_raw=False` | 0.050 s | 0.023 s | 2,284,867 B | 2,467,899 B |
| `retain_raw=True` | 0.051 s | 0.023 s | 2,876,876 B | 3,059,748 B |

For these rows, retaining the otherwise unknown 512-character research field
increased current traced graph memory by about 26%. The integration test checks
the stable architectural claims—cardinality, keyed lookup, and higher retained
memory—without asserting machine-specific timing or byte totals.
