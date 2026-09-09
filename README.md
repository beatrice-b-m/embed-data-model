# WIP EMBED Toolkit

A mutable clinical and mammography scaffold for partial EMBED tables. The active
Python project lives in [`unified-system/`](unified-system/), with source, tests,
examples, benchmarks, and its lockfile. Repository documentation and CI live here.

The governing architecture is the [mutable scaffold contract](docs/mutable-scaffold-contract.md),
with [settled API semantics](docs/mutable-scaffold-api.md). The
[implementation plan](docs/mutable-scaffold-implementation-plan.md) records the
cutover scope. Earlier architecture reviews describe historical implementations.

```bash
cd unified-system
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check src/embed_toolkit tests examples benchmarks
uv run --frozen mypy
```

Install the project with `python -m pip install ./unified-system` from this root.
The distribution is `embed-toolkit-unified`; import `embed_toolkit`. It has no
runtime dependencies; DataFrames and plain row mappings are both supported.

See the [package guide](unified-system/README.md) for construction, refresh/merge,
mutation, movement, ROI collections, optional validation, and independent partitions.
The full test suite includes an installed-wheel journey outside the checkout and
multi-grain scale regressions. CI is configured for Python 3.9–3.13 and full-package
type checking. [Qualification evidence](docs/mutable-scaffold-qualification.md)
distinguishes local verification from remote CI and private-data qualification.

Matching and ROI-transfer consumers belong in separate repositories. Their later
ports, package names, and publication are outside this scaffold implementation.
