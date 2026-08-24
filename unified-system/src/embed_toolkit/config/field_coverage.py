"""Validated field-coverage declarations for source profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from embed_toolkit.config.capabilities import (
    ProfileDeclarationState,
    normalize_declaration_state,
)


@dataclass(frozen=True)
class FieldCoverageDeclaration:
    """Classify one governed field and retain the reason and source surface."""

    governed_field: str
    state: ProfileDeclarationState
    reason: str
    source_fields: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for attribute in ("governed_field", "reason"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        object.__setattr__(self, "state", normalize_declaration_state(self.state))
        source_fields = tuple(self.source_fields)
        if any(
            not isinstance(source_field, str) or not source_field.strip()
            for source_field in source_fields
        ):
            raise ValueError("source_fields must contain only non-empty strings")
        if len(set(source_fields)) != len(source_fields):
            raise ValueError(
                f"Duplicate source fields for {self.governed_field!r}"
            )
        object.__setattr__(self, "source_fields", tuple(sorted(source_fields)))

    def to_dict(self) -> Dict[str, Any]:
        """Return a deterministic JSON-ready declaration."""

        return {
            "governed_field": self.governed_field,
            "state": self.state.value,
            "reason": self.reason,
            "source_fields": list(self.source_fields),
        }


@dataclass(frozen=True)
class FieldCoverageManifest:
    """An exhaustive declaration set for a supplied governed-field boundary."""

    source_profile: str
    governed_fields: Tuple[str, ...]
    declarations: Tuple[FieldCoverageDeclaration, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_profile, str) or not self.source_profile.strip():
            raise ValueError("source_profile must be a non-empty string")

        governed_fields = tuple(self.governed_fields)
        _validate_nonempty_strings(governed_fields, "governed_fields")
        duplicate_governed = _duplicate_strings(governed_fields)
        if duplicate_governed:
            raise ValueError(
                f"Duplicate governed fields: {duplicate_governed}"
            )

        declarations = tuple(self.declarations)
        declaration_fields = tuple(
            declaration.governed_field for declaration in declarations
        )
        duplicate_declarations = _duplicate_strings(declaration_fields)
        if duplicate_declarations:
            raise ValueError(
                f"Duplicate field coverage declarations: {duplicate_declarations}"
            )

        governed_set = set(governed_fields)
        declaration_set = set(declaration_fields)
        missing = tuple(sorted(governed_set - declaration_set))
        unexpected = tuple(sorted(declaration_set - governed_set))
        if missing:
            raise ValueError(f"Missing field coverage declarations: {missing}")
        if unexpected:
            raise ValueError(f"Unexpected field coverage declarations: {unexpected}")

        object.__setattr__(self, "governed_fields", tuple(sorted(governed_fields)))
        object.__setattr__(
            self,
            "declarations",
            tuple(sorted(declarations, key=lambda item: item.governed_field)),
        )

    def declaration_for(self, governed_field: str) -> FieldCoverageDeclaration:
        """Return the declaration for one governed field or raise clearly."""

        for declaration in self.declarations:
            if declaration.governed_field == governed_field:
                return declaration
        raise KeyError(governed_field)

    def to_dict(self) -> Dict[str, Any]:
        """Return the governed boundary and declarations in stable field order."""

        return {
            "source_profile": self.source_profile,
            "governed_fields": list(self.governed_fields),
            "declarations": [
                declaration.to_dict() for declaration in self.declarations
            ],
        }


def _validate_nonempty_strings(values: Iterable[str], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain only non-empty strings")


def _duplicate_strings(values: Iterable[str]) -> Tuple[str, ...]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))
