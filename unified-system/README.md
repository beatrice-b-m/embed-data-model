# Unified EMBED Toolkit

This directory contains the repository's only retained runtime implementation.
The governing implementation contract is the
[clinical object model resolution plan](../docs/clinical-object-model-resolution-plan.md),
with current verification and resolution evidence in the addendum at the top
of the [clinical object model evaluation](../docs/clinical-object-model-evaluation.md).

The [unified-system plan](../docs/unified-system-plan.md) is a historical
architecture plan. It explains the system's origin but does not supersede the
completed resolution contract. The retired repository-level legacy trees have
been removed.

## Development

Install or run tools from this directory so imports resolve to
`unified-system/src/embed_toolkit`.

```bash
python -m pytest
```
