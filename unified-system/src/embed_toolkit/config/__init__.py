"""Configuration objects for source-specific ingestion."""

from embed_toolkit.config.columns import EmbedColumnConfig, default_embed_columns
from embed_toolkit.config.profile_contracts import (
    INTERNAL_V1C_CONTRACT,
    INTERNAL_V1C_FIELD_INVENTORY,
    INTERNAL_V1C_PROFILE,
    INTERNAL_V2_CONTRACT,
    INTERNAL_V2_FIELD_INVENTORY,
    INTERNAL_V2_PROFILE,
    REPOSITORY_FIELD_INVENTORY,
    ProfileContract,
    ProfileKind,
    RepositoryFieldInventory,
    profile_contract_for,
    profile_source_field_candidates,
    validate_contract_source_fields,
)

__all__ = [
    "EmbedColumnConfig",
    "INTERNAL_V1C_CONTRACT",
    "INTERNAL_V1C_FIELD_INVENTORY",
    "INTERNAL_V1C_PROFILE",
    "INTERNAL_V2_CONTRACT",
    "INTERNAL_V2_FIELD_INVENTORY",
    "INTERNAL_V2_PROFILE",
    "ProfileContract",
    "ProfileKind",
    "REPOSITORY_FIELD_INVENTORY",
    "RepositoryFieldInventory",
    "default_embed_columns",
    "profile_contract_for",
    "profile_source_field_candidates",
    "validate_contract_source_fields",
]
