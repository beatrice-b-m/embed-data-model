# Contributing to EMBED Data Model

This library supplies reusable clinical and imaging objects and EMBED table
adapters. Downstream repositories own research workflows, outcome definitions,
matching, ROI transfer, pixel processing, and scientific validation. Changes to
the core should serve that shared object model without introducing a consumer's
workflow policy.

## Development

From the repository root, with Python 3.9–3.13 and `uv` available:

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check src/embed_data_model tests examples benchmarks
uv run --frozen mypy
uv run --frozen python -m examples.researcher_journeys
uv run --frozen python -m build
```

The full suite includes a wheel built and installed into a fresh environment,
then exercised outside the checkout. Run the full suite for packaging, public
API, identity, ownership, and ingestion changes. Add regression tests that assert
observable behavior when fixing a defect. The CI workflow runs tests on each
declared Python minor version and checks the complete package with Ruff and mypy.
The library has no mandatory runtime dependencies; keep optional DataFrame
support independent of a runtime pandas dependency.

Use synthetic fixtures in examples and tests. Keep private dataset rows and
credentials out of commits and issue reports. A useful defect report includes
the package version, Python version, a minimal synthetic reproduction, expected
behavior, and observed behavior.

## Public API and compatibility

The current version is `0.1.0`, an initial integration baseline. It is not a
declaration of a stable 1.x API or a claim of package-index publication. Pin an
exact source revision or a qualified wheel when starting a downstream port, and
record that dependency in the consumer's lockfile or environment specification.

Prefer the documented exports from `embed_data_model`. Use documented specialist
modules when a type is not exported at the root. Undocumented implementation
helpers and private attributes are not supported extension points. Subclassing,
consumer attributes, and metadata follow the documented object and copy contracts.

For subsequent versions, record public behavior changes in `CHANGELOG.md` and
provide migration instructions for breaking changes. During 0.x development,
breaking API changes should increment the minor version; patch versions should
preserve documented public behavior except for identified bug fixes. Changes to
identity, table bindings, refresh behavior, ROI coordinates, and partition copying
need particular care because they can change downstream results without an import
error. Python support changes also belong in the changelog and CI matrix.

Before declaring 1.0, qualify at least one real downstream port against a pinned
dependency, resolve material migration feedback, and explicitly review the public
API and supported table mappings. Synthetic library tests establish software
behavior; consumer studies establish their own scientific validity.

## Review and commits

Follow [AGENTS.md](AGENTS.md): each logical change requires a descriptive granular
commit, selective staging, and verification that the commit was recorded. Include
the behavior being changed and the reason in the commit body. Keep public docs
and runnable examples consistent with code changes.

Repository restructuring does not rename the remote repository or publish a
release. Distribution requires a separate maintainer decision about licensing,
the destination, and release credentials. Installation instructions must continue
to distinguish available source installation from any future package-index release.
