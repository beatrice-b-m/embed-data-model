# WIP EMBED Toolkit

The repository’s only active Python project intentionally lives under
[`unified-system/`](unified-system/). Its `pyproject.toml`, lockfile, source,
tests, examples, and benchmarks move together; repository-level `docs/` and CI
remain outside the distributable project.

The target architecture is recorded in
[`docs/mutable-scaffold-contract.md`](docs/mutable-scaffold-contract.md).
It reflects the maintainer review and is not yet implemented. The
[earlier architecture recovery record](docs/lightweight-framework-architecture-review.md)
describes the preceding design; installation and commands below apply to the
current implementation.

## Install

For development:

```bash
cd unified-system
uv sync --frozen
```

As a local wheel/project dependency:

```bash
python -m pip install ./unified-system
```

The installed distribution is `embed-toolkit-unified`; researchers import the
small facade as `embed_toolkit`.

## Verify

```bash
cd unified-system
uv run --frozen pytest
uv run --frozen ruff check src/embed_toolkit tests examples benchmarks
uv run --frozen mypy
```

The test suite builds a wheel, executes repo examples outside the source tree,
and runs the representative graph scale/raw-retention regression. CI repeats
the suite on Python 3.9 through 3.13.

See [`unified-system/README.md`](unified-system/README.md) for the public API,
incremental loading, issue inspection, manual ROI, and extension examples.
