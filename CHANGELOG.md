# Changelog

## 0.1.0 — 2026-09-09

First tagged source release, `v0.1.0`. This is an initial integration baseline
under the MIT license, with Python 3.9–3.13 qualification and no mandatory
runtime dependencies. It does not announce a package-index publication or a
stable 1.x API.

### Data model

- Provide mutable patient, exam, finding, procedure, pathology, image, and ROI
  objects, with indexed graph membership and source lookups.
- Load optional EMBED tables using semantic identities, in-place refresh,
  explicit merge, and inspectable unresolved records and relationships.
- Support consumer extensions, explicit validation, live selections,
  independent partitions, and subtree movement.

### Package identity and layout

- Rename the distribution from `embed-toolkit-unified` to `embed-data-model` and
  Python imports from `embed_toolkit` to `embed_data_model`.
- Place the Python project at the repository root instead of `unified-system/`.
- Keep the new namespace separate from the existing `embed-toolkit` library so
  downstream consumers can use both packages.

### Researcher documentation

- Provide researcher entry points and downstream migration guidance.
- Separate current API contracts from archived implementation history.
- Document development checks and compatibility expectations for initial ports.

### Migration

Install from the repository root and update imports to `embed_data_model`.
Remove references to `unified-system/` from consumer build/install commands.
The former import name is not retained as an alias because it belongs to the
separate `embed-toolkit` package. The package rename does not intentionally change
clinical or imaging behavior. See the [documentation index](docs/README.md) for
the current guides and contracts.
