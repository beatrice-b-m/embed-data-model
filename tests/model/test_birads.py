from __future__ import annotations

from embed_data_model.core.birads import (
    AsymmetryType,
    CalcMorphology,
    LegacyAsymmetryType,
    LegacyCalcMorphology,
    LegacyMassMargin,
    MassMargin,
    MassShape,
    normalize_asymmetry_type,
    normalize_calc_morphology,
    normalize_mass_margin,
    normalize_mass_shape,
)


def test_mass_shape_includes_v2025_lobulated() -> None:
    value = normalize_mass_shape("lobulated")

    assert MassShape.LOBULATED.value == "lobulated"
    assert value.normalized is MassShape.LOBULATED
    assert value.is_normalized
    assert not value.is_legacy


def test_mass_margin_excludes_micro_lobulated_from_normalized_enum() -> None:
    assert "MICROLOBULATED" not in MassMargin.__members__

    value = normalize_mass_margin("microlobulated", source_system="legacy")

    assert value.raw_value == "microlobulated"
    assert value.source_system == "legacy"
    assert value.legacy is LegacyMassMargin.MICROLOBULATED
    assert value.normalized is MassMargin.INDISTINCT
    assert value.is_legacy


def test_calc_morphology_includes_v2025_layering() -> None:
    value = normalize_calc_morphology("layering")

    assert CalcMorphology.LAYERING.value == "layering"
    assert value.normalized is CalcMorphology.LAYERING
    assert value.is_normalized


def test_legacy_milk_of_calcium_alias_normalizes_to_layering() -> None:
    value = normalize_calc_morphology("milk of calcium")

    assert value.legacy is LegacyCalcMorphology.MILK_OF_CALCIUM
    assert value.normalized is CalcMorphology.LAYERING
    assert value.is_legacy


def test_legacy_dystrophic_normalizes_to_coarse() -> None:
    value = normalize_calc_morphology(LegacyCalcMorphology.DYSTROPHIC)

    assert value.raw_value == "dystrophic"
    assert value.legacy is LegacyCalcMorphology.DYSTROPHIC
    assert value.normalized is CalcMorphology.COARSE
    assert value.warnings


def test_calc_morphology_uses_full_coarse_heterogeneous_spelling() -> None:
    value = normalize_calc_morphology("coarse heterogeneous")
    legacy = normalize_calc_morphology("coarse_hetero")

    assert "COARSE_HETERO" not in CalcMorphology.__members__
    assert CalcMorphology.COARSE_HETEROGENEOUS.value == "coarse_heterogeneous"
    assert value.normalized is CalcMorphology.COARSE_HETEROGENEOUS
    assert legacy.legacy is LegacyCalcMorphology.COARSE_HETERO
    assert legacy.normalized is CalcMorphology.COARSE_HETEROGENEOUS


def test_calc_morphology_uses_combined_fine_linear_descriptor() -> None:
    value = normalize_calc_morphology("fine linear or fine linear branching")
    legacy = normalize_calc_morphology("fine linear")

    assert "FINE_LINEAR" not in CalcMorphology.__members__
    assert (
        value.normalized
        is CalcMorphology.FINE_LINEAR_OR_FINE_LINEAR_BRANCHING
    )
    assert legacy.legacy is LegacyCalcMorphology.FINE_LINEAR
    assert (
        legacy.normalized
        is CalcMorphology.FINE_LINEAR_OR_FINE_LINEAR_BRANCHING
    )


def test_developing_asymmetry_is_legacy_source_only() -> None:
    value = normalize_asymmetry_type("developing asymmetry")

    assert "DEVELOPING" not in AsymmetryType.__members__
    assert value.legacy is LegacyAsymmetryType.DEVELOPING
    assert value.normalized is None
    assert value.is_legacy
    assert not value.is_unknown


def test_unknown_source_value_is_preserved_without_normalized_value() -> None:
    value = normalize_mass_margin("local experimental margin")

    assert value.raw_value == "local experimental margin"
    assert value.normalized is None
    assert value.legacy is None
    assert value.is_unknown
    assert value.warnings
