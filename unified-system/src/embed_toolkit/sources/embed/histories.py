"""EMBED auxiliary-history vocabularies and row normalization."""

from __future__ import annotations

from math import isfinite
from numbers import Real
from typing import Any, Mapping, Optional

from embed_toolkit.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.source import Issue, SourceRef


_MEDICATION_CATEGORIES = {"H": "hormone", "T": "therapy", "O": "contraceptive"}
_MEDICATIONS = {
    ("H", "C"): "estrogen_and_progesterone",
    ("H", "ESTRO"): "estrogen",
    ("H", "PH"): "premphase",
    ("H", "PP"): "prempro",
    ("H", "PROGES"): "progesterone",
    ("H", "R"): "premarin",
    ("H", "RA"): "raloxifene",
    ("H", "TAMOX"): "tamoxifen",
    ("H", "V"): "provera",
    ("H", "O"): "other",
    ("T", "CH"): "chemotherapy",
    ("T", "ET"): "endocrine_therapy",
    ("T", "H"): "hormonal_therapy",
    ("T", "RT"): "radiation_therapy",
    ("T", "RTC"): "radiation_and_chemotherapy",
    ("T", "RTH"): "radiation_and_hormone_therapy",
    ("T", "TAXOL"): "taxol",
    ("T", "XRT"): "xrt",
    ("T", "O"): "other",
    ("O", "C"): "combined_oral_contraceptive",
    ("O", "ORAL"): "oral_contraceptive",
    ("O", "O"): "other",
}
_PROCEDURE_CATEGORIES = {"G": "gynecological", "B": "breast"}
_PROCEDURES = {
    ("G", "HYST"): ("hysterectomy", "hysterectomy"),
    ("G", "H"): ("hysterectomy", "partial_hysterectomy"),
    ("G", "O"): ("oophorectomy", "one_ovary_removed"),
    ("G", "OS"): ("oophorectomy", "ovaries_removed"),
    ("B", "1"): ("biopsy", "core_biopsy"),
    ("B", "SB"): ("biopsy", "stereotactic_core_biopsy"),
    ("B", "UCB"): ("biopsy", "ultrasound_core_biopsy"),
    ("B", "B"): ("biopsy", "mri_guided_core_biopsy"),
    ("B", "E"): ("biopsy", "excisional_biopsy"),
    ("B", "NB"): ("biopsy", "needle_biopsy"),
    ("B", "CA"): ("aspiration", "cyst_aspiration"),
    ("B", "FNA"): ("aspiration", "fine_needle_aspiration"),
    ("B", "L"): ("lumpectomy", "lumpectomy"),
    ("B", "M"): ("mastectomy", "mastectomy"),
    ("B", "D"): ("other", "breast_reduction"),
    ("B", "MP"): ("other", "mammoplasty"),
    ("B", "R"): ("other", "reconstruction"),
    ("B", "EXI"): ("other", "implants_removed"),
    ("B", "NO"): ("other", "non_oncologic"),
}
_PROCEDURE_RESULTS = {
    "ADH": "atypical_ductal_hyperplasia",
    "ALH": "atypical_lobular_hyperplasia",
    "BEN": "benign",
    "BOT": "invasive_ductal_carcinoma_and_dcis",
    "DE": "duct_ectasia",
    "DS": "ductal_carcinoma_in_situ",
    "FA": "fibroadenoma",
    "FN": "fat_necrosis",
    "ID": "invasive_ductal_carcinoma",
    "IF": "chronic_inflammatory_changes",
    "IL": "invasive_lobular_carcinoma",
    "LS": "lobular_carcinoma_in_situ",
    "LY": "lymphoma",
    "MAL": "malignant",
    "PA": "papilloma",
    "SA": "sclerosing_adenosis",
    "SF": "stromal_fibrosis",
}
_UNKNOWN_FLAGS = {"", "U", "NA", "N/A", "NAN", "UNKNOWN"}


def normalize_medication_history(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
    patient_id: str,
    record_id: Optional[str] = None,
) -> tuple[Optional[MedicationHistoryObservation], tuple[Issue, ...]]:
    issues: list[Issue] = []
    raw_category = _upper(row, columns["category"])
    raw_code = _upper(row, columns["medication"])
    if not raw_category or not raw_code:
        return None, (
            Issue(
                code="incomplete_medication_history_identity",
                message="medication history requires category and medication code",
                source=source,
            ),
        )
    category = _MEDICATION_CATEGORIES.get(raw_category, raw_category)
    medication = _MEDICATIONS.get((raw_category, raw_code), raw_code)
    if raw_category not in _MEDICATION_CATEGORIES:
        issues.append(
            Issue(
                code="unknown_medication_history_category",
                message="medication history category is not in the EMBED vocabulary",
                severity="warning",
                source=source,
                context={"category": raw_category},
            )
        )
    if (raw_category, raw_code) not in _MEDICATIONS:
        issues.append(
            Issue(
                code="unknown_medication_history_code",
                message="medication history code is not in the EMBED vocabulary",
                severity="warning",
                source=source,
                context={"category": raw_category, "code": raw_code},
            )
        )
    observation = MedicationHistoryObservation(
        patient_id=patient_id,
        source=source,
        category=category,
        medication=medication,
        context_accession=_text(row, columns["accession"]),
        continuous=_flag(row, columns["continuous"], source, "continuous", issues),
        current=_flag(row, columns["current"], source, "current", issues),
        reported_duration=_text(row, columns["duration"]),
        started=_time_estimate(
            row,
            columns,
            source,
            issues,
            prefix="start",
        ),
        stopped=_time_estimate(
            row,
            columns,
            source,
            issues,
            prefix="stop",
        ),
        comment=_text(row, columns["comment"]),
    )
    _set_record_id(
        observation,
        record_id if record_id is not None else _text(row, columns.get("record_id")),
    )
    return observation, tuple(issues)


def normalize_procedure_history(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
    patient_id: str,
    record_id: Optional[str] = None,
) -> tuple[Optional[ProcedureHistoryObservation], tuple[Issue, ...]]:
    issues: list[Issue] = []
    raw_category = _upper(row, columns["category"])
    raw_code = _upper(row, columns["procedure"])
    if not raw_category or not raw_code:
        return None, (
            Issue(
                code="incomplete_procedure_history_identity",
                message="procedure history requires category and procedure code",
                source=source,
            ),
        )
    category = _PROCEDURE_CATEGORIES.get(raw_category, raw_category)
    procedure, detail = _PROCEDURES.get((raw_category, raw_code), (raw_code, None))
    if raw_category not in _PROCEDURE_CATEGORIES:
        issues.append(
            Issue(
                code="unknown_procedure_history_category",
                message="procedure history category is not in the EMBED vocabulary",
                severity="warning",
                source=source,
                context={"category": raw_category},
            )
        )
    if (raw_category, raw_code) not in _PROCEDURES:
        issues.append(
            Issue(
                code="unknown_procedure_history_code",
                message="procedure history code is not in the EMBED vocabulary",
                severity="warning",
                source=source,
                context={"category": raw_category, "code": raw_code},
            )
        )
    raw_result = _upper(row, columns["result"])
    result = _PROCEDURE_RESULTS.get(raw_result, raw_result or None)
    if raw_result == "NONE":
        result = None
    elif raw_result and raw_result not in _PROCEDURE_RESULTS:
        issues.append(
            Issue(
                code="unknown_procedure_history_result",
                message="procedure history result is not in the EMBED vocabulary",
                severity="warning",
                source=source,
                context={"result": raw_result},
            )
        )
    observation = ProcedureHistoryObservation(
            patient_id=patient_id,
            source=source,
            category=category,
            procedure=procedure,
            detail=detail,
            context_accession=_text(row, columns["accession"]),
            laterality=Laterality.coerce(_text(row, columns["laterality"])),
            reported_result=result,
        )
    _set_record_id(
        observation,
        record_id if record_id is not None else _text(row, columns.get("record_id")),
    )
    return observation, tuple(issues)


def _text(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    if column is None:
        return None
    value = row.get(column)
    if value is None or type(value).__name__ in {"NAType", "NaTType"}:
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            if not isfinite(float(value)):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    text = str(value).strip()
    return text or None


def _upper(row: Mapping[str, Any], column: Optional[str]) -> str:
    return (_text(row, column) or "").upper()


def _flag(
    row: Mapping[str, Any],
    column: Optional[str],
    source: SourceRef,
    semantic: str,
    issues: list[Issue],
) -> Optional[bool]:
    value = _upper(row, column)
    if value == "Y":
        return True
    if value == "N":
        return False
    if value in _UNKNOWN_FLAGS:
        return None
    issues.append(
        Issue(
            code="unrecognized_history_flag",
            message="patient-history boolean flag was not recognized",
            severity="warning",
            source=source,
            context={"field": semantic, "value": value},
        )
    )
    return None


def _number(
    row: Mapping[str, Any],
    column: Optional[str],
    source: SourceRef,
    semantic: str,
    issues: list[Issue],
    *,
    minimum: float,
    maximum: float,
    integer: bool,
) -> Optional[float]:
    """Parse a numeric fact without applying clinical plausibility rules.

    ``minimum``, ``maximum``, and ``integer`` remain in the private signature
    for callers from the pre-validation adapter, but range and integral checks
    belong to W7 validation.  A finite numeric value is retained even when it
    is clinically implausible.
    """

    text = _text(row, column)
    if text is None:
        return None
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    if not isfinite(value):
        issues.append(
            Issue(
                code="invalid_history_time_component",
                message="patient-history time component could not be normalized",
                severity="warning",
                source=source,
                context={"field": semantic, "value": text},
            )
        )
        return None
    if integer and value.is_integer():
        return int(value)
    return value


def _time_estimate(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: SourceRef,
    issues: list[Issue],
    *,
    prefix: str,
) -> Optional[HistoryTimeEstimate]:
    age = _number(
        row,
        columns[f"{prefix}_age"],
        source,
        f"{prefix}_age",
        issues,
        minimum=0,
        maximum=150,
        integer=False,
    )
    month = _number(
        row,
        columns[f"{prefix}_month"],
        source,
        f"{prefix}_month",
        issues,
        minimum=1,
        maximum=12,
        integer=True,
    )
    year = _number(
        row,
        columns[f"{prefix}_year"],
        source,
        f"{prefix}_year",
        issues,
        minimum=1,
        maximum=9999,
        integer=True,
    )
    estimate = HistoryTimeEstimate(
        age=age,
        month=month if month is not None else None,
        year=year if year is not None else None,
    )
    return None if estimate.is_empty else estimate


def _set_record_id(observation: Any, record_id: Optional[str]) -> None:
    """Attach an explicit semantic record identifier when the domain supports it."""

    if record_id is None:
        return
    normalized = str(record_id).strip()
    if not normalized:
        return
    # The mutable history domain is being updated alongside this adapter.  The
    # object-level fallback keeps this normalizer usable during that cutover
    # without deriving an event identity from a source row or ordinal.
    object.__setattr__(observation, "record_id", normalized)


__all__ = ["normalize_medication_history", "normalize_procedure_history"]
