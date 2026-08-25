from typing import Literal, Annotated, Optional, Union
from datetime import date
from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
import pandas as pd

from .general import HormoneVariant, TherapyVariant, ContraceptiveVariant

# ---------------------------------------------------------------------------
# Stage 2: pydantic discriminated union for row-level objects
# ---------------------------------------------------------------------------


def _clean_date(month_value: object, year_value: object) -> Optional[date]:
    def _clean_month(value: object) -> Optional[int]:
        try:
            parsed = int(str(value).strip())
            return parsed if 1 <= parsed <= 12 else None
        except (TypeError, ValueError):
            return None

    def _clean_year(value: object) -> Optional[int]:
        try:
            text = str(value).strip()
            if (text.startswith("20") or text.startswith("19")) and len(text) == 4:
                return int(text)
            return None
        except (TypeError, ValueError):
            return None

    month, year = _clean_month(month_value), _clean_year(year_value)
    if month is None or year is None:
        return None
    return date(year=year, month=month, day=1)


def _prepare_common_fields(data: dict) -> dict:
    """Map raw EMBED column names onto this model's field names.

    Plain function rather than an inherited pydantic validator, so each
    leaf class below can call it explicitly and layer on its own
    category-specific handling without relying on base/subclass
    "before"-validator ordering.
    """
    data = dict(data)
    data["code_raw"] = str(data.get("code", "")).strip()
    data["start_age"] = data.get("first_age")
    data["stop_age"] = data.get("last_age")
    data["start_date"] = _clean_date(data.get("mfirst"), data.get("yfirst"))
    data["stop_date"] = _clean_date(data.get("mlast"), data.get("ylast"))
    return data


class _MedicationRecordBase(BaseModel):
    empi_anon: int
    acc_anon: int

    code_raw: str  # preserved verbatim for auditability, alongside the parsed `variant`

    continuous: Optional[bool] = None
    current: Optional[bool] = None

    duration: Optional[int] = None
    start_age: Optional[float] = None
    start_date: Optional[date] = None
    stop_age: Optional[float] = None
    stop_date: Optional[date] = None

    comment: Optional[str] = None

    @field_validator("continuous", "current", mode="before")
    @classmethod
    def _binarize(cls, value: object) -> Optional[bool]:
        if value is None:
            return None
        cleaned = str(value).strip().upper()
        if cleaned == "Y":
            return True
        if cleaned == "N":
            return False
        return None

    @field_validator("start_age", "stop_age", mode="before")
    @classmethod
    def _clean_age(cls, value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    @field_validator("duration", mode="before")
    @classmethod
    def _clean_duration(cls, value: object) -> Optional[int]:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None


class HormoneRecord(_MedicationRecordBase):
    category: Literal["H"] = "H"
    variant: HormoneVariant

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: dict) -> dict:
        data = _prepare_common_fields(data)
        data["variant"] = data["code_raw"]
        return data


class TherapyRecord(_MedicationRecordBase):
    category: Literal["T"] = "T"
    variant: TherapyVariant

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: dict) -> dict:
        data = _prepare_common_fields(data)
        data["variant"] = data["code_raw"]
        return data


class ContraceptiveRecord(_MedicationRecordBase):
    category: Literal["O"] = "O"
    variant: ContraceptiveVariant

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: dict) -> dict:
        data = _prepare_common_fields(data)
        data["variant"] = data["code_raw"]
        return data


MedicationRecord = Annotated[
    Union[HormoneRecord, TherapyRecord, ContraceptiveRecord],
    Field(discriminator="category"),
]

_medication_record_adapter: TypeAdapter = TypeAdapter(MedicationRecord)


def parse_medication_row(
    row: dict,
) -> Union[HormoneRecord, TherapyRecord, ContraceptiveRecord]:
    """Parse one raw row (dict) into the correct category-scoped record.

    `category` is what the discriminated union dispatches on; the raw
    table calls this column `type`, so we alias it here.
    """
    row = dict(row)
    row["category"] = row.get("type")
    return _medication_record_adapter.validate_python(row)


def parse_medication_dataframe(
    df: pd.DataFrame,
) -> tuple[list[Union[HormoneRecord, TherapyRecord, ContraceptiveRecord]], list[dict]]:
    """Parse every row of an already pandera-validated DataFrame.

    Returns (records, errors) instead of raising on the first bad row --
    useful when auditing messy self-reported data, where you want to know
    about every problem row in a batch, not just the first one.
    """
    records: list[Union[HormoneRecord, TherapyRecord, ContraceptiveRecord]] = []
    errors: list[dict] = []

    for idx, row in df.iterrows():
        try:
            records.append(parse_medication_row(row.to_dict()))
        except ValidationError as exc:
            errors.append({"row": idx, "errors": exc.errors()})

    return records, errors
