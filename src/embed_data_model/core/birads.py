"""Source-neutral BI-RADS mammography descriptor values.

This module models normalized BI-RADS v2025 mammography lexicon values
separately from raw or legacy source-system values. Adapter modules can preserve
local source codes here without importing MagView-specific parsing into core.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Generic, Mapping, Optional, Tuple, Type, TypeVar


class MassShape(Enum):
    """Normalized BI-RADS v2025 mammography mass shape descriptors.

    Members
    -------
    OVAL='oval', ROUND='round', IRREGULAR='irregular', LOBULATED='lobulated'.
    """

    OVAL = "oval"
    ROUND = "round"
    IRREGULAR = "irregular"
    LOBULATED = "lobulated"


class MassMargin(Enum):
    """Normalized BI-RADS v2025 mammography mass margin descriptors.

    Members
    -------
    CIRCUMSCRIBED='circumscribed', INDISTINCT='indistinct', OBSCURED='obscured',
    SPICULATED='spiculated'.
    """

    CIRCUMSCRIBED = "circumscribed"
    INDISTINCT = "indistinct"
    OBSCURED = "obscured"
    SPICULATED = "spiculated"


class CalcMorphology(Enum):
    """Normalized BI-RADS v2025 mammography calcification morphology.

    Members
    -------
    SKIN='skin', VASCULAR='vascular', COARSE='coarse',
    LARGE_ROD_LIKE='large_rod_like', ROUND='round', RIM='rim',
    LUCENT_CENTERED='lucent_centered', LAYERING='layering', SUTURE='suture',
    AMORPHOUS='amorphous', COARSE_HETEROGENEOUS='coarse_heterogeneous',
    FINE_PLEOMORPHIC='fine_pleomorphic',
    FINE_LINEAR_OR_FINE_LINEAR_BRANCHING='fine_linear_or_fine_linear_branching'.
    """

    SKIN = "skin"
    VASCULAR = "vascular"
    COARSE = "coarse"
    LARGE_ROD_LIKE = "large_rod_like"
    ROUND = "round"
    RIM = "rim"
    LUCENT_CENTERED = "lucent_centered"
    LAYERING = "layering"
    SUTURE = "suture"
    AMORPHOUS = "amorphous"
    COARSE_HETEROGENEOUS = "coarse_heterogeneous"
    FINE_PLEOMORPHIC = "fine_pleomorphic"
    FINE_LINEAR_OR_FINE_LINEAR_BRANCHING = "fine_linear_or_fine_linear_branching"


class AsymmetryType(Enum):
    """Normalized BI-RADS v2025 mammography asymmetry descriptors.

    Members
    -------
    ASYMMETRY='asymmetry', GLOBAL_ASYMMETRY='global_asymmetry',
    FOCAL_ASYMMETRY='focal_asymmetry'.
    """

    ASYMMETRY = "asymmetry"
    GLOBAL_ASYMMETRY = "global_asymmetry"
    FOCAL_ASYMMETRY = "focal_asymmetry"


class LegacyMassMargin(Enum):
    """Known non-v2025 mass margin values retained for source preservation.

    Members
    -------
    MICROLOBULATED='microlobulated'.
    """

    MICROLOBULATED = "microlobulated"


class LegacyCalcMorphology(Enum):
    """Known non-v2025 calcification morphology values retained for sources.

    Members
    -------
    MILK_OF_CALCIUM='milk_of_calcium', DYSTROPHIC='dystrophic',
    COARSE_HETERO='coarse_hetero', FINE_LINEAR='fine_linear'.
    """

    MILK_OF_CALCIUM = "milk_of_calcium"
    DYSTROPHIC = "dystrophic"
    COARSE_HETERO = "coarse_hetero"
    FINE_LINEAR = "fine_linear"


class LegacyAsymmetryType(Enum):
    """Known discontinued asymmetry descriptors retained for source values.

    Members
    -------
    DEVELOPING='developing'.
    """

    DEVELOPING = "developing"


NormalizedT = TypeVar("NormalizedT", bound=Enum)
LegacyT = TypeVar("LegacyT", bound=Enum)


@dataclass(frozen=True)
class SourceLexiconValue(Generic[NormalizedT, LegacyT]):
    """Lossless source value plus its normalized BI-RADS interpretation.

    ``normalized`` is the v2025 lexicon value to use for clinical logic.
    ``legacy`` is populated when the source value is a known discontinued or
    local value rather than a normalized lexicon member.

    Attributes
    ----------
    raw_value : Any
        Original unnormalized value retained as source evidence; not a semantic
        identity.
    source_system : Optional[str]
        Optional source vocabulary label, retained without choosing
        normalization policy. Default: None.
    normalized : Optional[NormalizedT]
        Recognized normalized enum value, or None when not normalized. Default:
        None.
    legacy : Optional[LegacyT]
        Recognized legacy enum value, or None. Legacy values are preserved
        rather than silently reclassified. Default: None.
    warnings : Tuple[str, ...]
        Diagnostic messages/records in emission order; empty means none emitted.
        Default: ().
    """

    raw_value: Any
    """Original unnormalized value retained as source evidence; not a semantic identity."""
    source_system: Optional[str] = None
    """Optional source vocabulary label, retained without choosing normalization
    policy. Default: None.
    """
    normalized: Optional[NormalizedT] = None
    """Recognized normalized enum value, or None when not normalized. Default: None."""
    legacy: Optional[LegacyT] = None
    """Recognized legacy enum value, or None. Legacy values are preserved rather
    than silently reclassified. Default: None.
    """
    warnings: Tuple[str, ...] = ()
    """Diagnostic messages/records in emission order; empty means none emitted. Default: ()."""

    @property
    def is_normalized(self) -> bool:
        """True when a normalized value is present."""

        return self.normalized is not None and self.legacy is None

    @property
    def is_legacy(self) -> bool:
        """True when a preserved legacy value is present."""

        return self.legacy is not None

    @property
    def is_unknown(self) -> bool:
        """True when neither normalized nor legacy is present; raw evidence remains available."""

        return self.normalized is None and self.legacy is None


def normalize_mass_shape(
    value: Any,
    *,
    source_system: Optional[str] = None,
) -> SourceLexiconValue[MassShape, Enum]:
    """Normalize a source mass shape into the v2025 lexicon.

    Parameters
    ----------
    value : object
        Source code, enum or text. Recognized aliases normalize; missing/unknown
        values remain represented as raw evidence without inventing a category.
    source_system : str or None, optional
        Optional provenance label, default None; does not change mapping policy.

    Returns
    -------
    SourceLexiconValue
        Original value, optional normalized/legacy enum, and warning strings.
        Legacy categories are preserved rather than mapped to a modern category.
    """

    return _normalize_source_value(
        value,
        MassShape,
        _MASS_SHAPE_ALIASES,
        {},
        source_system=source_system,
    )


def normalize_mass_margin(
    value: Any,
    *,
    source_system: Optional[str] = None,
) -> SourceLexiconValue[MassMargin, LegacyMassMargin]:
    """Normalize a source mass margin while preserving legacy values.

    Parameters
    ----------
    value : object
        Source code, enum or text. Recognized aliases normalize; missing/unknown
        values remain represented as raw evidence without inventing a category.
    source_system : str or None, optional
        Optional provenance label, default None; does not change mapping policy.

    Returns
    -------
    SourceLexiconValue
        Original value, optional normalized/legacy enum, and warning strings.
        Legacy categories are preserved rather than mapped to a modern category.
    """

    return _normalize_source_value(
        value,
        MassMargin,
        _MASS_MARGIN_ALIASES,
        _LEGACY_MASS_MARGIN_ALIASES,
        source_system=source_system,
    )


def normalize_calc_morphology(
    value: Any,
    *,
    source_system: Optional[str] = None,
) -> SourceLexiconValue[CalcMorphology, LegacyCalcMorphology]:
    """Normalize a source calcification morphology value.

    Parameters
    ----------
    value : object
        Source code, enum or text. Recognized aliases normalize; missing/unknown
        values remain represented as raw evidence without inventing a category.
    source_system : str or None, optional
        Optional provenance label, default None; does not change mapping policy.

    Returns
    -------
    SourceLexiconValue
        Original value, optional normalized/legacy enum, and warning strings.
        Legacy categories are preserved rather than mapped to a modern category.
    """

    return _normalize_source_value(
        value,
        CalcMorphology,
        _CALC_MORPHOLOGY_ALIASES,
        _LEGACY_CALC_MORPHOLOGY_ALIASES,
        source_system=source_system,
    )


def normalize_asymmetry_type(
    value: Any,
    *,
    source_system: Optional[str] = None,
) -> SourceLexiconValue[AsymmetryType, LegacyAsymmetryType]:
    """Normalize a source asymmetry descriptor.

    Parameters
    ----------
    value : object
        Source code, enum or text. Recognized aliases normalize; missing/unknown
        values remain represented as raw evidence without inventing a category.
    source_system : str or None, optional
        Optional provenance label, default None; does not change mapping policy.

    Returns
    -------
    SourceLexiconValue
        Original value, optional normalized/legacy enum, and warning strings.
        Legacy categories are preserved rather than mapped to a modern category.
    """

    return _normalize_source_value(
        value,
        AsymmetryType,
        _ASYMMETRY_TYPE_ALIASES,
        _LEGACY_ASYMMETRY_TYPE_ALIASES,
        source_system=source_system,
    )


def _normalize_source_value(
    value: Any,
    normalized_type: Type[NormalizedT],
    normalized_aliases: Mapping[str, NormalizedT],
    legacy_aliases: Mapping[str, Tuple[LegacyT, Optional[NormalizedT]]],
    *,
    source_system: Optional[str],
) -> SourceLexiconValue[NormalizedT, LegacyT]:
    if isinstance(value, normalized_type):
        return SourceLexiconValue(
            raw_value=value.value,
            source_system=source_system,
            normalized=value,
        )

    for legacy_value, normalized_value in legacy_aliases.values():
        if value is legacy_value:
            return SourceLexiconValue(
                raw_value=value.value,
                source_system=source_system,
                normalized=normalized_value,
                legacy=legacy_value,
                warnings=_legacy_warning(legacy_value, normalized_value),
            )

    key = _source_key(value)
    if key in normalized_aliases:
        return SourceLexiconValue(
            raw_value=value,
            source_system=source_system,
            normalized=normalized_aliases[key],
        )

    if key in legacy_aliases:
        legacy_value, normalized_value = legacy_aliases[key]
        return SourceLexiconValue(
            raw_value=value,
            source_system=source_system,
            normalized=normalized_value,
            legacy=legacy_value,
            warnings=_legacy_warning(legacy_value, normalized_value),
        )

    return SourceLexiconValue(
        raw_value=value,
        source_system=source_system,
        warnings=(f"Unknown {normalized_type.__name__} source value: {value!r}",),
    )


def _source_key(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    text = "" if value is None else str(value).strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    return text.strip("_")


def _legacy_warning(
    legacy_value: LegacyT,
    normalized_value: Optional[NormalizedT],
) -> Tuple[str, ...]:
    if normalized_value is None:
        return (
            f"{legacy_value.__class__.__name__}.{legacy_value.name} is a legacy "
            "source value with no v2025 descriptor equivalent",
        )
    return (
        f"{legacy_value.__class__.__name__}.{legacy_value.name} is a legacy "
        f"source value normalized to {normalized_value.__class__.__name__}."
        f"{normalized_value.name}",
    )


def _enum_aliases(enum_type: Type[NormalizedT]) -> Dict[str, NormalizedT]:
    aliases: Dict[str, NormalizedT] = {}
    for member in enum_type:
        aliases[_source_key(member.name)] = member
        aliases[_source_key(member.value)] = member
    return aliases


_MASS_SHAPE_ALIASES = _enum_aliases(MassShape)

_MASS_MARGIN_ALIASES = _enum_aliases(MassMargin)
_LEGACY_MASS_MARGIN_ALIASES = {
    "MICROLOBULATED": (LegacyMassMargin.MICROLOBULATED, MassMargin.INDISTINCT),
    "MICRO_LOBULATED": (LegacyMassMargin.MICROLOBULATED, MassMargin.INDISTINCT),
}

_CALC_MORPHOLOGY_ALIASES = _enum_aliases(CalcMorphology)
_CALC_MORPHOLOGY_ALIASES.update(
    {
        "LARGE_RODLIKE": CalcMorphology.LARGE_ROD_LIKE,
        "LARGE_ROD_LIKE": CalcMorphology.LARGE_ROD_LIKE,
        "LUCENTCENTERED": CalcMorphology.LUCENT_CENTERED,
        "LUCENT_CENTERED": CalcMorphology.LUCENT_CENTERED,
        "COARSE_HETERO_GENOUS": CalcMorphology.COARSE_HETEROGENEOUS,
        "FINE_LINEAR_BRANCHING": CalcMorphology.FINE_LINEAR_OR_FINE_LINEAR_BRANCHING,
        "FINE_LINEAR_OR_BRANCHING": CalcMorphology.FINE_LINEAR_OR_FINE_LINEAR_BRANCHING,
    }
)
_LEGACY_CALC_MORPHOLOGY_ALIASES = {
    "MILK_OF_CALCIUM": (LegacyCalcMorphology.MILK_OF_CALCIUM, CalcMorphology.LAYERING),
    "MILK_CALCIUM": (LegacyCalcMorphology.MILK_OF_CALCIUM, CalcMorphology.LAYERING),
    "DYSTROPHIC": (LegacyCalcMorphology.DYSTROPHIC, CalcMorphology.COARSE),
    "COARSE_HETERO": (
        LegacyCalcMorphology.COARSE_HETERO,
        CalcMorphology.COARSE_HETEROGENEOUS,
    ),
    "FINE_LINEAR": (
        LegacyCalcMorphology.FINE_LINEAR,
        CalcMorphology.FINE_LINEAR_OR_FINE_LINEAR_BRANCHING,
    ),
}

_ASYMMETRY_TYPE_ALIASES = _enum_aliases(AsymmetryType)
_LEGACY_ASYMMETRY_TYPE_ALIASES = {
    "DEVELOPING": (LegacyAsymmetryType.DEVELOPING, None),
    "DEVELOPING_ASYMMETRY": (LegacyAsymmetryType.DEVELOPING, None),
}
