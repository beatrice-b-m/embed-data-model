from enum import Enum


class MedicationCategory(str, Enum):
    HORMONE = "H"
    THERAPY = "T"
    CONTRACEPTIVE = "O"


class HormoneVariant(str, Enum):
    ESTROGEN_AND_PROGESTERONE = "C"  # combined HRT
    ESTROGEN = "ESTRO"
    PREMPHASE = "PH"
    PREMPRO = "PP"
    PROGESTERONE = "PROGES"
    PREMARIN = "R"
    RALOXIFENE = "RA"
    TAMOXIFEN = "TAMOX"
    PROVERA = "V"
    OTHER = "O"


class TherapyVariant(str, Enum):
    CHEMOTHERAPY = "CH"
    ENDOCRINE_THERAPY = "ET"
    HORMONAL_THERAPY = "H"
    RADIATION_THERAPY = "RT"
    RADIATION_THERAPY_AND_CHEMOTHERAPY = "RTC"
    RADIATION_THERAPY_AND_HORMONE_THERAPY = "RTH"
    TAXOL = "TAXOL"
    XRT = "XRT"
    OTHER = "O"


class ContraceptiveVariant(str, Enum):
    COMBINED_ORAL = "C"
    ORAL_CONTRACEPTIVE = "ORAL"
    OTHER = "O"


_VARIANT_BY_CATEGORY: dict[str, type[Enum]] = {
    MedicationCategory.HORMONE.value: HormoneVariant,
    MedicationCategory.THERAPY.value: TherapyVariant,
    MedicationCategory.CONTRACEPTIVE.value: ContraceptiveVariant,
}
