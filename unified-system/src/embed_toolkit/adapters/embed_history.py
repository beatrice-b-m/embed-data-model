"""Fail-soft adapters for EMBED HormoneHist and ProcHist reference rows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Iterable, Mapping, Optional, Tuple

from embed_toolkit.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.procedures import _to_plain
from embed_toolkit.core.build_policy import BuildPolicy
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import (
    BuildIssue,
    IssueSeverity,
    ResolutionState,
    SourceLocator,
    SourceOccurrence,
    SourceScopeKind,
)


Row = Mapping[str, Any]


_MEDICATION_CATEGORIES = {
    "H": "hormone",
    "T": "therapy",
    "O": "contraceptive",
}

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

_UNKNOWN_FLAG_VALUES = {"", "U", "NA", "N/A", "NAN", "UNKNOWN"}


@dataclass(frozen=True)
class EmbedPatientHistoryTables:
    """Patient-owned history observations plus their complete source ledger."""

    patients: Tuple[Patient, ...]
    medication_history: Tuple[MedicationHistoryObservation, ...]
    procedure_history: Tuple[ProcedureHistoryObservation, ...]
    source_occurrences: Tuple[SourceOccurrence, ...]
    build_issues: Tuple[BuildIssue, ...]

    def __post_init__(self) -> None:
        for attribute in (
            "patients",
            "medication_history",
            "procedure_history",
            "source_occurrences",
            "build_issues",
        ):
            object.__setattr__(self, attribute, tuple(getattr(self, attribute)))
        ledger = {item.locator for item in self.source_occurrences}
        observations = (*self.medication_history, *self.procedure_history)
        if any(item.source not in ledger for item in observations):
            raise ValueError("Every history observation source must be in the ledger")
        nested = tuple(
            item for patient in self.patients for item in patient.history_observations
        )
        if len(nested) != len(observations) or sorted(map(id, nested)) != sorted(
            map(id, observations)
        ):
            raise ValueError(
                "Patients must own the same history objects as the tables"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "patients": [
                {
                    "patient_id": patient.patient_id,
                    "history_observation_references": [
                        item.reference_dict()
                        for item in patient.history_observations
                    ],
                    "metadata": _to_plain(patient.metadata),
                }
                for patient in self.patients
            ],
            "medication_history": [
                item.to_dict() for item in self.medication_history
            ],
            "procedure_history": [item.to_dict() for item in self.procedure_history],
            "source_occurrences": [
                item.to_dict() for item in self.source_occurrences
            ],
            "build_issues": [item.to_dict() for item in self.build_issues],
        }


def _text(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            if math.isnan(float(value)):
                return None
        except (TypeError, ValueError, OverflowError):
            pass
    text = str(value).strip()
    return text or None


def _identifier(value: object) -> Optional[str]:
    text = _text(value)
    if text is None:
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric) and numeric.is_integer():
            return str(int(numeric))
    return text


def _issue(
    issues: list[BuildIssue],
    policy: BuildPolicy,
    locator: SourceLocator,
    *,
    code: str,
    message: str,
    severity: IssueSeverity,
    **context: object,
) -> None:
    issue = BuildIssue(
        code=code,
        message=message,
        severity=severity,
        source=locator,
        context=context,
    )
    policy.handle_issue(issue)
    issues.append(issue)


def _flag(
    value: object,
    *,
    field: str,
    issues: list[BuildIssue],
    policy: BuildPolicy,
    locator: SourceLocator,
) -> Optional[bool]:
    text = (_text(value) or "").upper()
    if text == "Y":
        return True
    if text == "N":
        return False
    if text in _UNKNOWN_FLAG_VALUES:
        return None
    _issue(
        issues,
        policy,
        locator,
        code="unrecognized_history_flag",
        message="A patient-history boolean flag was not recognized.",
        severity=IssueSeverity.WARNING,
        field=field,
        value=text,
    )
    return None


def _number(
    value: object,
    *,
    field: str,
    integer: bool,
    minimum: float,
    maximum: float,
    issues: list[BuildIssue],
    policy: BuildPolicy,
    locator: SourceLocator,
) -> Optional[float]:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        parsed = math.nan
    valid = math.isfinite(parsed) and minimum <= parsed <= maximum
    if integer:
        valid = valid and parsed.is_integer()
    if not valid:
        _issue(
            issues,
            policy,
            locator,
            code="invalid_history_time_component",
            message="A patient-history time component could not be normalized.",
            severity=IssueSeverity.WARNING,
            field=field,
            value=text,
        )
        return None
    return parsed


def _time_estimate(
    row: Row,
    *,
    age_field: str,
    month_field: str,
    year_field: str,
    issues: list[BuildIssue],
    policy: BuildPolicy,
    locator: SourceLocator,
) -> Optional[HistoryTimeEstimate]:
    age = _number(
        row.get(age_field),
        field=age_field,
        integer=False,
        minimum=0,
        maximum=150,
        issues=issues,
        policy=policy,
        locator=locator,
    )
    month_value = _number(
        row.get(month_field),
        field=month_field,
        integer=True,
        minimum=1,
        maximum=12,
        issues=issues,
        policy=policy,
        locator=locator,
    )
    year_value = _number(
        row.get(year_field),
        field=year_field,
        integer=True,
        minimum=1,
        maximum=9999,
        issues=issues,
        policy=policy,
        locator=locator,
    )
    estimate = HistoryTimeEstimate(
        age=age,
        month=int(month_value) if month_value is not None else None,
        year=int(year_value) if year_value is not None else None,
    )
    return None if estimate.is_empty else estimate


def build_patient_history_tables(
    *,
    hormone_rows: Iterable[Row] = (),
    procedure_rows: Iterable[Row] = (),
    source_scope: str,
    source_profile: str = "embed-auxiliary-reference",
    scope_kind: SourceScopeKind = SourceScopeKind.MATERIALIZATION,
    build_policy: Optional[BuildPolicy] = None,
) -> EmbedPatientHistoryTables:
    """Translate available auxiliary rows without asserting a verified profile."""

    if not isinstance(source_scope, str) or not source_scope.strip():
        raise ValueError("source_scope must be a non-empty string")
    if not isinstance(source_profile, str) or not source_profile.strip():
        raise ValueError("source_profile must be a non-empty string")
    policy = build_policy or BuildPolicy()
    if not isinstance(policy, BuildPolicy):
        raise TypeError("build_policy must be a BuildPolicy")
    scope_kind = SourceScopeKind(scope_kind)

    patients: dict[str, Patient] = {}
    medication_history: list[MedicationHistoryObservation] = []
    procedure_history: list[ProcedureHistoryObservation] = []
    occurrences: list[SourceOccurrence] = []
    build_issues: list[BuildIssue] = []

    def patient_for(patient_id: str) -> Patient:
        if patient_id not in patients:
            patients[patient_id] = Patient(patient_id)
        return patients[patient_id]

    for row_ordinal, source_row in enumerate(hormone_rows):
        row = dict(source_row)
        locator = SourceLocator(
            scope=source_scope,
            scope_kind=scope_kind,
            source_profile=source_profile,
            source_table="HormoneHist",
            row_ordinal=row_ordinal,
        )
        row_issues: list[BuildIssue] = []
        patient_id = _identifier(row.get("empi_anon"))
        raw_category = (_text(row.get("type")) or "").upper()
        raw_code = (_text(row.get("code")) or "").upper()
        missing = [
            name
            for name, value in (
                ("empi_anon", patient_id),
                ("type", raw_category),
                ("code", raw_code),
            )
            if not value
        ]
        if missing:
            _issue(
                row_issues,
                policy,
                locator,
                code="incomplete_medication_history_identity",
                message="Medication history requires patient, category, and code.",
                severity=IssueSeverity.ERROR,
                missing_fields=missing,
            )
        else:
            category = _MEDICATION_CATEGORIES.get(raw_category, raw_category)
            medication = _MEDICATIONS.get((raw_category, raw_code), raw_code)
            if raw_category not in _MEDICATION_CATEGORIES:
                _issue(
                    row_issues,
                    policy,
                    locator,
                    code="unknown_medication_history_category",
                    message="Medication history category is not in the reference vocabulary.",
                    severity=IssueSeverity.WARNING,
                    category=raw_category,
                )
            if (raw_category, raw_code) not in _MEDICATIONS:
                _issue(
                    row_issues,
                    policy,
                    locator,
                    code="unknown_medication_history_code",
                    message="Medication history code is not valid for its reference category.",
                    severity=IssueSeverity.WARNING,
                    category=raw_category,
                    code_value=raw_code,
                )
            observation = MedicationHistoryObservation(
                patient_id=patient_id,
                source=locator,
                category=category,
                medication=medication,
                context_accession=_identifier(row.get("acc_anon")),
                continuous=_flag(
                    row.get("continuous"),
                    field="continuous",
                    issues=row_issues,
                    policy=policy,
                    locator=locator,
                ),
                current=_flag(
                    row.get("current"),
                    field="current",
                    issues=row_issues,
                    policy=policy,
                    locator=locator,
                ),
                reported_duration=_text(row.get("duration")),
                started=_time_estimate(
                    row,
                    age_field="first_age",
                    month_field="mfirst",
                    year_field="yfirst",
                    issues=row_issues,
                    policy=policy,
                    locator=locator,
                ),
                stopped=_time_estimate(
                    row,
                    age_field="last_age",
                    month_field="mlast",
                    year_field="ylast",
                    issues=row_issues,
                    policy=policy,
                    locator=locator,
                ),
                comment=_text(row.get("comment")),
            )
            patient_for(patient_id).add_history_observation(observation)
            medication_history.append(observation)
        occurrences.append(
            SourceOccurrence(
                locator=locator,
                raw_values=row,
                resolution_state=(
                    ResolutionState.UNRESOLVED
                    if missing
                    else ResolutionState.RESOLVED
                ),
                issues=tuple(row_issues),
            )
        )
        build_issues.extend(row_issues)

    for row_ordinal, source_row in enumerate(procedure_rows):
        row = dict(source_row)
        locator = SourceLocator(
            scope=source_scope,
            scope_kind=scope_kind,
            source_profile=source_profile,
            source_table="ProcHist",
            row_ordinal=row_ordinal,
        )
        row_issues = []
        patient_id = _identifier(row.get("empi_anon"))
        raw_category = (_text(row.get("type")) or "").upper()
        raw_code = (_text(row.get("pcode")) or "").upper()
        missing = [
            name
            for name, value in (
                ("empi_anon", patient_id),
                ("type", raw_category),
                ("pcode", raw_code),
            )
            if not value
        ]
        if missing:
            _issue(
                row_issues,
                policy,
                locator,
                code="incomplete_procedure_history_identity",
                message="Procedure history requires patient, category, and code.",
                severity=IssueSeverity.ERROR,
                missing_fields=missing,
            )
        else:
            category = _PROCEDURE_CATEGORIES.get(raw_category, raw_category)
            procedure, detail = _PROCEDURES.get(
                (raw_category, raw_code),
                (raw_code, None),
            )
            if raw_category not in _PROCEDURE_CATEGORIES:
                _issue(
                    row_issues,
                    policy,
                    locator,
                    code="unknown_procedure_history_category",
                    message="Procedure history category is not in the reference vocabulary.",
                    severity=IssueSeverity.WARNING,
                    category=raw_category,
                )
            if (raw_category, raw_code) not in _PROCEDURES:
                _issue(
                    row_issues,
                    policy,
                    locator,
                    code="unknown_procedure_history_code",
                    message="Procedure history code is not valid for its reference category.",
                    severity=IssueSeverity.WARNING,
                    category=raw_category,
                    code_value=raw_code,
                )
            raw_result = (_text(row.get("result")) or "").upper()
            reported_result = _PROCEDURE_RESULTS.get(raw_result, raw_result or None)
            if raw_result == "NONE":
                reported_result = None
            elif raw_result and raw_result not in _PROCEDURE_RESULTS:
                _issue(
                    row_issues,
                    policy,
                    locator,
                    code="unknown_procedure_history_result",
                    message="Procedure history result is not in the reference vocabulary.",
                    severity=IssueSeverity.WARNING,
                    result=raw_result,
                )
            observation = ProcedureHistoryObservation(
                patient_id=patient_id,
                source=locator,
                category=category,
                procedure=procedure,
                detail=detail,
                context_accession=_identifier(row.get("acc_anon")),
                laterality=Laterality.coerce(row.get("side")),
                reported_result=reported_result,
            )
            patient_for(patient_id).add_history_observation(observation)
            procedure_history.append(observation)
        occurrences.append(
            SourceOccurrence(
                locator=locator,
                raw_values=row,
                resolution_state=(
                    ResolutionState.UNRESOLVED
                    if missing
                    else ResolutionState.RESOLVED
                ),
                issues=tuple(row_issues),
            )
        )
        build_issues.extend(row_issues)

    return EmbedPatientHistoryTables(
        patients=tuple(patients.values()),
        medication_history=tuple(medication_history),
        procedure_history=tuple(procedure_history),
        source_occurrences=tuple(occurrences),
        build_issues=tuple(build_issues),
    )
