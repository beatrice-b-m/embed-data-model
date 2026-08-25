from typing import Annotated, Literal, Optional, Union

import pandas as pd

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from .general import (
    ProcedureResult,
    ProcedureSide,
    GynecologicalSubvariant,
    ProcedureVariant,
    _GYN_VARIANT_BY_SUBVARIANT,
    BreastSubvariant,
    _BREAST_VARIANT_BY_SUBVARIANT,
)


class _ProcedureRecordBase(BaseModel):
    empi_anon: int
    acc_anon: int

    pcode_raw: str  # preserved verbatim for auditability, alongside `subvariant`

    result: ProcedureResult
    side: ProcedureSide

    @field_validator("result", "side", mode="before")
    @classmethod
    def _clean_str(cls, value: object) -> Optional[str]:
        # Defensive cleaning independent of stage 1, in case this model is
        # ever constructed without going through the pandera schema first.
        if value is None:
            return None
        return str(value).strip()


class GynecologicalProcedureRecord(_ProcedureRecordBase):
    category: Literal["G"] = "G"
    subvariant: GynecologicalSubvariant
    variant: ProcedureVariant

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: dict) -> dict:
        data = dict(data)
        data["pcode_raw"] = str(data.get("pcode", "")).strip()
        data["subvariant"] = data["pcode_raw"]
        data["variant"] = _GYN_VARIANT_BY_SUBVARIANT.get(
            data["pcode_raw"], ProcedureVariant.UNKNOWN
        )
        return data


class BreastProcedureRecord(_ProcedureRecordBase):
    category: Literal["B"] = "B"
    subvariant: BreastSubvariant
    variant: ProcedureVariant

    @model_validator(mode="before")
    @classmethod
    def _prepare(cls, data: dict) -> dict:
        data = dict(data)
        data["pcode_raw"] = str(data.get("pcode", "")).strip()
        data["subvariant"] = data["pcode_raw"]
        data["variant"] = _BREAST_VARIANT_BY_SUBVARIANT.get(
            data["pcode_raw"], ProcedureVariant.UNKNOWN
        )
        return data


ProcedureRecord = Annotated[
    Union[GynecologicalProcedureRecord, BreastProcedureRecord],
    Field(discriminator="category"),
]

_procedure_record_adapter: TypeAdapter = TypeAdapter(ProcedureRecord)


def parse_procedure_row(
    row: dict,
) -> Union[GynecologicalProcedureRecord, BreastProcedureRecord]:
    """Parse one raw row (dict) into the correct category-scoped record.

    `category` is what the discriminated union dispatches on; the raw
    table calls this column `type`, so we alias it here.
    """
    row = dict(row)
    row["category"] = row.get("type")
    return _procedure_record_adapter.validate_python(row)


def parse_procedure_dataframe(
    df: pd.DataFrame,
) -> tuple[
    list[Union[GynecologicalProcedureRecord, BreastProcedureRecord]], list[dict]
]:
    """Parse every row of an already pandera-validated DataFrame.

    Returns (records, errors) instead of raising on the first bad row.
    """
    records: list[Union[GynecologicalProcedureRecord, BreastProcedureRecord]] = []
    errors: list[dict] = []

    for idx, row in df.iterrows():
        try:
            records.append(parse_procedure_row(row.to_dict()))
        except ValidationError as exc:
            errors.append({"row": idx, "errors": exc.errors()})

    return records, errors
