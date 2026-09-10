# EMBED Data Model qualification

Local preparation checks completed on 2026-09-09 for `embed-data-model==0.1.0`.
The packaging and namespace cutover is commit `29a5c48`; executable documentation
checks are in `0c0d388`, and the installed researcher-journey check is in
`6b716ba`. Documentation navigation and archival changes are recorded separately
in Git. This is qualification of a source-installable dependency, not a release
announcement or a declaration of a stable 1.x API.

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
actual researcher example, that test was rerun on each minor version. No runtime
semantics changed during the rename: comparison with pre-cutover source, after
normalizing package names, found only the package description changed additionally.

The Python 3.13 root environment was created with `uv sync --frozen`. Ruff passed
over source, tests, examples, and benchmarks; mypy passed over all 35 runtime
files; the lockfile consistency check passed. The checkout command
`python -m examples.researcher_journeys` completed with
`ValidationResult(issues=())`. The Python 3.9–3.12 checks used separate temporary
environments with compatible build, pytest, and pandas dependencies.

`tests/integration/test_documented_examples.py` executes all Python snippets in
the root README, user guide, and downstream migration guide in fresh namespaces.
The current 13 snippets include assertions about semantic identity, DataFrame
mapping, refresh/merge, relationships, ROI geometry, and independent partitions.
They require no private data. The wheel test also copies
`examples/researcher_journeys.py` outside the checkout and runs it using the
freshly installed wheel interpreter with `PYTHONPATH` removed.

## Distribution and coexistence

Both a source archive and wheel build successfully. The wheel contains the
`embed_data_model` namespace, `py.typed`, and MIT license text. Its metadata
declares `Name: embed-data-model`, `License-Expression: MIT`, and no mandatory
runtime dependencies. It contains no `embed_toolkit` package. The source archive
also includes the license and typed source package, without `unified-system/`.

A separate Python 3.13.11 environment installed the actual published
`embed-toolkit==0.2.14` alongside the locally built `embed-data-model==0.1.0`
wheel. Verification confirmed:

- both distribution versions and both imports resolve from site-packages;
- the distributions own disjoint installed file paths;
- the legacy pandas `.embed` accessor remains available; and
- the same synthetic DataFrame loads through `embed_data_model.load_embed`
  into the expected patient, exam, and finding objects without issues.

The published legacy toolkit imports `tqdm` without declaring it as a dependency.
The coexistence environment therefore installed `tqdm==4.70.0` explicitly after
the initial legacy import failed. This is a prerequisite of that tested legacy
release, not a new dependency of EMBED Data Model. No legacy repository was edited.

The real-package coexistence check is local evidence. The normal test suite
stays independent of a network download and permanently checks the new wheel's
namespace, metadata, license, and installed public-API journey.

## Scope of the evidence

These runs took place on local macOS. The repository configures Linux CI for
Python 3.9–3.13, but no remote CI run was triggered or verified during preparation.
No private EMBED tables, real pixels, full private-dataset scale, or downstream
scientific outcomes were qualified. The existing scale regressions passed; no
new benchmark measurements are claimed.

No package-index publication, release tag, remote repository rename, or real
downstream workflow port was performed. The package is ready for a pinned source
integration; a real consumer port remains the next validation milestone before
declaring API stability. See [CONTRIBUTING.md](../CONTRIBUTING.md) for compatibility
expectations and the [migration guide](downstream-migration.md) for adoption.
Earlier runtime qualification is preserved in the
[historical record](archive/mutable-scaffold-qualification.md).
