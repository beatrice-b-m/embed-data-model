import pandera.pandas as pa
import pandas as pd
from pandera.typing import Series
from .general import _VARIANT_BY_CATEGORY, MedicationCategory

try:

    @pa.extensions.register_check_method(statistics=[], supported_types=(pd.DataFrame,))
    def code_matches_type(df: pd.DataFrame) -> Series[bool]:
        """`code` must be a valid variant of the enum scoped to that row's `type`.

        This is exactly the check that would have caught the "C" collision in
        the original flat enum, where CONTRACEPTIVE = "C" silently aliased
        ESTROGEN_AND_PROGESTERONE = "C". Registering it (rather than nesting it
        as a method on RawMedicationSchema) makes it a standalone, reusable,
        independently-testable unit, and lets any schema opt in by name via
        `Config`.
        """

        def _row_ok(type_value: str, code_value: str) -> bool:
            variant_cls = _VARIANT_BY_CATEGORY.get(type_value)
            if variant_cls is None:
                return False
            # UNKNOWN is a valid fallback member (via _missing_), so any code
            # round-trips to *some* member of the right enum class.
            return code_value in {v.value for v in variant_cls}

        return Series(
            [_row_ok(t, c) for t, c in zip(df["type"], df["code"])],
            index=df.index,
        )

except ValueError:
    print("Skipping, check already registered")


class TypeCodeSchema(pa.DataFrameModel):
    """Isolated schema for just the medication type/code relationship."""

    type: Series[str] = pa.Field(isin=[c.value for c in MedicationCategory])
    code: Series[str]

    class Config:
        coerce = True
        strict = False
        code_matches_type = ()  # invokes the registered check above

    @pa.parser("type", "code")
    def stringify_and_strip(cls, series: Series[str]) -> Series[str]:
        return series.astype(str).fillna("").str.strip()


class RawMedicationSchema(TypeCodeSchema):
    """Full raw-table schema. Inherits the type/code check from TypeCodeSchema
    via ordinary subclassing and adds the remaining raw columns."""

    empi_anon: Series[int]
    acc_anon: Series[int] = pa.Field(ne=999)

    continuous: Series[str] = pa.Field(isin=["Y", "N", ""], nullable=False)
    current: Series[str] = pa.Field(isin=["Y", "N", ""], nullable=False)

    duration: Series[str] = pa.Field(nullable=True)  # cleaned to int in stage 2
    first_age: Series[str] = pa.Field(nullable=True)
    mfirst: Series[str] = pa.Field(nullable=True)
    yfirst: Series[str] = pa.Field(nullable=True)
    last_age: Series[str] = pa.Field(nullable=True)
    mlast: Series[str] = pa.Field(nullable=True)
    ylast: Series[str] = pa.Field(nullable=True)

    comment: Series[str] = pa.Field(nullable=True)

    @pa.parser(
        "continuous",
        "current",
        "duration",
        "first_age",
        "mfirst",
        "yfirst",
        "last_age",
        "mlast",
        "ylast",
        "comment",
    )
    def stringify_and_strip(cls, series: Series[str]) -> Series[str]:
        return series.astype(str).fillna("").str.strip()
