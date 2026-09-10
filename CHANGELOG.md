# Changelog

## 0.1.0 — 2026-09-09

First tagged source release, `v0.1.0`, under the MIT license, with Python
3.9–3.13 qualification and no mandatory runtime dependencies.

### Data model

- Provide mutable patient, exam, finding, procedure, pathology, image, and ROI
  objects, with indexed graph membership and source lookups.
- Load optional EMBED tables using semantic identities, in-place refresh,
  explicit merge, and inspectable unresolved records and relationships.
- Support consumer extensions, explicit validation, live selections,
  independent partitions, and subtree movement.

### Packaging

- Distribute `embed-data-model` with the Python namespace `embed_data_model`.
- Include typed source, MIT license text, and wheel installation checks.
- Provide a Python project at the repository root with a locked development
  environment and tests for each supported Python minor version.

### Documentation

- Provide installation instructions, runnable researcher examples, and
  downstream integration guidance.
- Specify object and API contracts, development checks, and compatibility policy.
- Record local test qualification and synthetic loading measurements.
