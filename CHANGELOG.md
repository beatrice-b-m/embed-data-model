# Changelog

## Unreleased — EMBED Data Model preparation

The project retains version `0.1.0` during preparation; this entry does not
announce a published release.

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
