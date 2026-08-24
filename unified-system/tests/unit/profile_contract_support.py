"""Test-only helpers for explicit caller-supplied profile contracts."""

from __future__ import annotations

from dataclasses import replace

from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import (
    ProfileContract,
    profile_source_field_candidates,
)
from embed_toolkit.core.provenance import AvailabilityState


def contract_for_columns(
    base: ProfileContract,
    source_profile: str,
    columns: EmbedColumnConfig,
) -> ProfileContract:
    """Bind a copied test contract to one exact configured physical surface."""

    candidates = profile_source_field_candidates(columns, base.kind)
    defaults = EmbedColumnConfig.default()

    def rebound(declaration):
        field = declaration.governed_field
        no_source_state = declaration.state in {
            AvailabilityState.UNAVAILABLE,
            AvailabilityState.UNMODELED,
            AvailabilityState.UNSUPPORTED,
        }
        explicitly_overridden = getattr(columns, field) != getattr(defaults, field)
        if no_source_state and not explicitly_overridden:
            return replace(declaration, source_fields=())
        return replace(
            declaration,
            state=AvailabilityState.BOUND if no_source_state else declaration.state,
            source_fields=candidates[field],
        )

    return replace(
        base,
        source_profile=source_profile,
        capabilities=replace(base.capabilities, source_profile=source_profile),
        field_coverage=replace(
            base.field_coverage,
            source_profile=source_profile,
            declarations=tuple(
                rebound(declaration)
                for declaration in base.field_coverage.declarations
            ),
        ),
    )
