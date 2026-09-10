# EMBED Data Model qualification

Local checks completed on 2026-09-09 for `embed-data-model==0.1.0`.
The checked package is recorded in commit `29a5c48`, executable documentation
checks in `0c0d388`, and the installed researcher-journey check in `6b716ba`.
Results below describe those revisions and environments. The source release is
identified by tag `v0.1.0`; installation instructions are in the [README](../README.md).

## Tests and development environment

| Python | Full suite |
| --- | ---: |
| 3.9.6 | 242 passed |
| 3.10.20 | 242 passed |
| 3.11.14 | 242 passed |
| 3.12.12 | 242 passed |
| 3.13.11 | 242 passed |

Each minor version ran the complete suite from the repository root, including
semantic loading, mutation, graph membership, scale regressions, installed-wheel
acceptance, and documentation examples. After extending the wheel test to run the
actual researcher example, that test was rerun on each minor version.

The Python 3.13 root environment was created with `uv sync --frozen`. Ruff passed
over source, tests, examples, and benchmarks; mypy passed over all 35 runtime
files; the lockfile consistency check passed. The checkout command
`python -m examples.researcher_journeys` completed with
`ValidationResult(issues=())`. The Python 3.9–3.12 checks used separate temporary
environments with compatible build, pytest, and pandas dependencies.

`tests/integration/test_documented_examples.py` executes all Python snippets in
the root README, user guide, and downstream integration guide in fresh namespaces.
The 13 snippets at the checked revisions included assertions about semantic
identity, DataFrame mapping, refresh/merge, relationships, ROI geometry, and independent partitions.
They require no private data. The wheel test also copies
`examples/researcher_journeys.py` outside the checkout and runs it using the
freshly installed wheel interpreter with `PYTHONPATH` removed.

## Distribution

Both a source archive and wheel built successfully. The wheel contains the
`embed_data_model` namespace, `py.typed`, and MIT license text. Its metadata
declares `Name: embed-data-model`, `License-Expression: MIT`, and no mandatory
runtime dependencies. The source archive also includes the license and typed
source package.

The wheel smoke test verifies package metadata, license text, import boundaries,
and the installed public-API journey outside the source checkout.

## Scope of the evidence

These runs took place on local macOS. The repository configures Linux CI for
Python 3.9–3.13; these local results do not establish a remote CI result.
No private EMBED tables, real pixels, full private-dataset scale, or downstream
scientific outcomes were qualified by these checks. The scale regressions passed;
[benchmark results](../benchmarks/README.md) are recorded separately with their
measurement revision and environment.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for compatibility expectations and the
[integration guide](downstream-integration.md) for consumer acceptance checks.
