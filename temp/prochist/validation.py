import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

from .general import (
    _SUBVARIANT_ENUM_BY_CATEGORY,
    _ALL_SUBVARIANT_CODES,
    _INVALID_ACC_ANON,
    ProcedureCategory,
    ProcedureResult,
)


@pa.extensions.register_check_method(statistics=[], supported_types=(pd.DataFrame,))
def pcode_matches_category(df: pd.DataFrame) -> Series[bool]:
    """`pcode` must be a valid subvariant code for that row's `type`.

    This is the analog of `code_matches_type` in the medication schema.
    There's no raw-value collision motivating it here (pcodes are unique
    across categories) -- what it actually catches is the original
    `ProcedureSubvariant.from_pcode` searching across ALL categories, so
    e.g. a hysterectomy pcode on a `type="B"` (breast) row would have
    silently validated before.
    """

    def _row_ok(category_value: str, pcode_value: str) -> bool:
        subvariant_cls = _SUBVARIANT_ENUM_BY_CATEGORY.get(category_value)
        if subvariant_cls is None:
            return False
        return pcode_value in {m.value for m in subvariant_cls}

    return Series(
        [_row_ok(t, p) for t, p in zip(df["type"], df["pcode"])],
        index=df.index,
    )


class CategoryPcodeSchema(pa.DataFrameModel):
    """Isolated schema for just the type/pcode relationship."""

    type: Series[str] = pa.Field(isin=[c.value for c in ProcedureCategory])
    pcode: Series[str] = pa.Field(isin=sorted(_ALL_SUBVARIANT_CODES))

    class Config:
        coerce = True
        strict = False
        pcode_matches_category = ()

    @pa.parser("type", "pcode")
    def strip_whitespace(cls, series: Series[str]) -> Series[str]:
        return series.str.strip()


class RawProcedureSchema(CategoryPcodeSchema):
    """Full raw-table schema. Inherits the type/pcode check via ordinary
    subclassing and adds the remaining raw columns."""

    empi_anon: Series[int]
    acc_anon: Series[int] = pa.Field(ne=_INVALID_ACC_ANON)

    result: Series[str] = pa.Field(
        isin=[r.value for r in ProcedureResult], nullable=True
    )
    # isin lists "" rather than " " -- see the ProcedureSide note above.
    side: Series[str] = pa.Field(isin=["L", "R", "B", ""], nullable=True)

    @pa.parser("result", "side")
    def strip_remaining_whitespace(cls, series: Series[str]) -> Series[str]:
        return series.str.strip()
