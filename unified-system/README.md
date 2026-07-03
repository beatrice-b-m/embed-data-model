# Unified EMBED Toolkit

This directory contains the greenfield implementation described in
`../docs/unified-system-plan.md`.

The repository-level `embed_toolkit/` and `quadrant_matching/` directories are
reference code for behavior, vocabulary, and future parity tests. They are not
runtime dependencies of this package.

## Development

Install or run tools from this directory so imports resolve to
`unified-system/src/embed_toolkit` instead of the legacy package at the
repository root.

```bash
python -m pytest
```

