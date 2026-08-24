"""Test-only helpers for explicit caller-supplied profile contracts."""

from __future__ import annotations

from dataclasses import replace

from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import (
    ProfileContract,
    profile_source_field_candidates,
)


def contract_for_columns(
    base: ProfileContract,
    source_profile: str,
    columns: EmbedColumnConfig,
) -> ProfileContract:
    """Bind a copied test contract to one exact configured physical surface."""

    candidates = profile_source_field_candidates(columns, base.kind)
    return replace(
        base,
        source_profile=source_profile,
        capabilities=replace(base.capabilities, source_profile=source_profile),
        field_coverage=replace(
            base.field_coverage,
            source_profile=source_profile,
            declarations=tuple(
                replace(
                    declaration,
                    source_fields=candidates[declaration.governed_field],
                )
                for declaration in base.field_coverage.declarations
            ),
        ),
    )
