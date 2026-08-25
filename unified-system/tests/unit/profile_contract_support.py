"""Test-only helpers for explicit caller-supplied profile contracts."""

from __future__ import annotations

from dataclasses import replace

from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import (
    ProfileContract,
    profile_source_field_candidates,
)
from embed_toolkit.config.field_coverage import FieldCoverageDeclaration
from embed_toolkit.core.provenance import AvailabilityState


def contract_for_columns(
    base: ProfileContract,
    source_profile: str,
    columns: EmbedColumnConfig,
    *,
    additional_bound_fields: tuple[str, ...] = (),
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

    additional_declarations = tuple(
        FieldCoverageDeclaration(
            governed_field=field,
            state=AvailabilityState.BOUND,
            reason="The custom test profile explicitly binds this field.",
            source_fields=candidates[field],
        )
        for field in additional_bound_fields
        if field not in base.field_inventory.governed_fields
    )
    inventory = replace(
        base.field_inventory,
        governed_fields=(
            *base.field_inventory.governed_fields,
            *(item.governed_field for item in additional_declarations),
        ),
    )
    return replace(
        base,
        source_profile=source_profile,
        field_inventory=inventory,
        capabilities=replace(base.capabilities, source_profile=source_profile),
        field_coverage=replace(
            base.field_coverage,
            source_profile=source_profile,
            governed_fields=inventory.governed_fields,
            declarations=tuple(
                rebound(declaration)
                for declaration in (
                    *base.field_coverage.declarations,
                    *additional_declarations,
                )
            ),
        ),
    )
