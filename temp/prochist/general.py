from enum import Enum


class ProcedureCategory(str, Enum):
    GYNECOLOGICAL = "G"
    BREAST = "B"


class ProcedureVariant(str, Enum):
    HYSTERECTOMY = "hyst"
    BIOPSY = "bx"
    ASPIRATION = "asp"
    LUMPECTOMY = "lump"
    MASTECTOMY = "mast"
    OOPHORECTOMY = "ooph"
    OTHER = "other"
    UNKNOWN = "unknown"


class ProcedureResult(str, Enum):
    ATYPICAL_DUCTAL_HYPERPLASIA = "ADH"
    ATYPICAL_LOBULAR_HYPERPLASIA = "ALH"
    BENIGN = "BEN"
    IDC_AND_DCIS = "BOT"
    DUCT_ECTASIA = "DE"
    DUCTAL_CARCINOMA_IN_SITU = "DS"  # fixed typo: original had "SITUA"
    FIBROADENOMA = "FA"
    FAT_NECROSIS = "FN"
    INVASIVE_DUCTAL_CARCINOMA = "ID"
    CHRONIC_INFLAMMATORY_CHANGES = "IF"
    INVASIVE_LOBULAR_CARCINOMA = "IL"
    LOBULAR_CARCINOMA_IN_SITU = "LS"
    LYMPHOMA = "LY"
    MALIGNANT = "MAL"
    PAPILLOMA = "PA"
    SCLEROSING_ADENOSIS = "SA"
    STROMAL_FIBROSIS = "SF"
    NONE = "NONE"

    @classmethod
    def _missing_(cls, value: object) -> "ProcedureResult":
        return cls.NONE


class ProcedureSide(str, Enum):
    LEFT = "L"
    RIGHT = "R"
    BILATERAL = "B"
    # Canonicalized to "" (was " " in the original) since this pipeline
    # strips whitespace before this enum ever sees a raw value -- see the
    # module docstring. `_missing_` below means this choice doesn't
    # actually matter for correctness; it's just the value that will
    # realistically arrive after stage-1 cleaning.
    UNKNOWN = ""

    @classmethod
    def _missing_(cls, value: object) -> "ProcedureSide":
        return cls.UNKNOWN


# Subvariant vocabularies are scoped per category, the same way
# HormoneVariant/TherapyVariant/ContraceptiveVariant were scoped per
# MedicationCategory. Also fixed a typo: original had "STEROTACTIC".
class GynecologicalSubvariant(str, Enum):
    HYSTERECTOMY = "HYST"
    PARTIAL_HYSTERECTOMY = "H"
    OVARY_REMOVED = "O"
    OVARIES_REMOVED = "OS"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "GynecologicalSubvariant":
        return cls.UNKNOWN


class BreastSubvariant(str, Enum):
    CORE_BIOPSY = "1"
    STEREOTACTIC_CORE_BIOPSY = "SB"
    ULTRASOUND_CORE_BIOPSY = "UCB"
    MRI_GUIDED_CORE_BIOPSY = "B"
    EXCISIONAL_BIOPSY = "E"
    NEEDLE_BIOPSY = "NB"
    CYST_ASPIRATION = "CA"
    FINE_NEEDLE_ASPIRATION = "FNA"
    LUMPECTOMY = "L"
    MASTECTOMY = "M"
    BREAST_REDUCTION = "D"
    MAMMOPLASTY = "MP"
    RECONSTRUCTION = "R"
    IMPLANTS_REMOVED = "EXI"
    NON_ONCOLOGIC = "NO"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "BreastSubvariant":
        return cls.UNKNOWN


_SUBVARIANT_ENUM_BY_CATEGORY: dict[str, type[Enum]] = {
    ProcedureCategory.GYNECOLOGICAL.value: GynecologicalSubvariant,
    ProcedureCategory.BREAST.value: BreastSubvariant,
}

_GYN_VARIANT_BY_SUBVARIANT: dict[str, ProcedureVariant] = {
    GynecologicalSubvariant.HYSTERECTOMY.value: ProcedureVariant.HYSTERECTOMY,
    GynecologicalSubvariant.PARTIAL_HYSTERECTOMY.value: ProcedureVariant.HYSTERECTOMY,
    GynecologicalSubvariant.OVARY_REMOVED.value: ProcedureVariant.OOPHORECTOMY,
    GynecologicalSubvariant.OVARIES_REMOVED.value: ProcedureVariant.OOPHORECTOMY,
    GynecologicalSubvariant.UNKNOWN.value: ProcedureVariant.UNKNOWN,
}

_BREAST_VARIANT_BY_SUBVARIANT: dict[str, ProcedureVariant] = {
    BreastSubvariant.CORE_BIOPSY.value: ProcedureVariant.BIOPSY,
    BreastSubvariant.STEREOTACTIC_CORE_BIOPSY.value: ProcedureVariant.BIOPSY,
    BreastSubvariant.ULTRASOUND_CORE_BIOPSY.value: ProcedureVariant.BIOPSY,
    BreastSubvariant.MRI_GUIDED_CORE_BIOPSY.value: ProcedureVariant.BIOPSY,
    BreastSubvariant.EXCISIONAL_BIOPSY.value: ProcedureVariant.BIOPSY,
    BreastSubvariant.NEEDLE_BIOPSY.value: ProcedureVariant.BIOPSY,
    BreastSubvariant.CYST_ASPIRATION.value: ProcedureVariant.ASPIRATION,
    BreastSubvariant.FINE_NEEDLE_ASPIRATION.value: ProcedureVariant.ASPIRATION,
    BreastSubvariant.LUMPECTOMY.value: ProcedureVariant.LUMPECTOMY,
    BreastSubvariant.MASTECTOMY.value: ProcedureVariant.MASTECTOMY,
    BreastSubvariant.BREAST_REDUCTION.value: ProcedureVariant.OTHER,
    BreastSubvariant.MAMMOPLASTY.value: ProcedureVariant.OTHER,
    BreastSubvariant.RECONSTRUCTION.value: ProcedureVariant.OTHER,
    BreastSubvariant.IMPLANTS_REMOVED.value: ProcedureVariant.OTHER,
    BreastSubvariant.NON_ONCOLOGIC.value: ProcedureVariant.OTHER,
    BreastSubvariant.UNKNOWN.value: ProcedureVariant.UNKNOWN,
}

_VARIANT_LOOKUP_BY_CATEGORY: dict[str, dict[str, ProcedureVariant]] = {
    ProcedureCategory.GYNECOLOGICAL.value: _GYN_VARIANT_BY_SUBVARIANT,
    ProcedureCategory.BREAST.value: _BREAST_VARIANT_BY_SUBVARIANT,
}

_ALL_SUBVARIANT_CODES: set[str] = {m.value for m in GynecologicalSubvariant} | {
    m.value for m in BreastSubvariant
}

# Same EMBED sentinel used in medication_history.py. Duplicated here rather
# than imported since this is a standalone example -- centralize it in a
# shared constants module if/when you consolidate these schemas, and
# confirm with the data dictionary that it applies to this table's
# acc_anon column too rather than assuming it carries over.
_INVALID_ACC_ANON: int = 999
