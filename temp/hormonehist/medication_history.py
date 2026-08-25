"""
Two-stage validation workflow for EMBED auxiliary medication-history data.

Stage 1 (pandera) — bulk, vectorized checks over the whole raw DataFrame:
    column presence/types, allowed value sets, numeric ranges, and a
    cross-column check that `code` is a valid variant *for its category*.
    This is where you catch structural problems cheaply, before
    instantiating a single Python object.

Stage 2 (pydantic) — per-row parsing into a category-scoped domain object.
    A discriminated union picks the right variant vocabulary (Hormone vs.
    Therapy vs. Contraceptive) based on `category`, so a raw code like "C"
    can no longer collide across categories the way it did in the
    original flat MedicationVariant enum (where CONTRACEPTIVE = "C" was a
    silent alias of ESTROGEN_AND_PROGESTERONE = "C").

Run this file directly to see both stages exercised against sample rows,
including the exact "C" collision from the original enum, plus a couple
of deliberately malformed rows so you can see what each stage catches.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal, Optional, Union

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series, DataFrame
from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Enums
#
# NOTE: variants are now scoped *per category*. This is the actual fix for
# the bug in the original code: MedicationVariant.CONTRACEPTIVE = "C" was
# defined after ESTROGEN_AND_PROGESTERONE = "C" in the same flat enum, so
# it silently became an alias rather than a distinct member. Splitting the
# vocabulary by category means "C" can mean different things in different
# categories without colliding.
# ---------------------------------------------------------------------------


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
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "HormoneVariant":
        return cls.UNKNOWN


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
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "TherapyVariant":
        return cls.UNKNOWN


class ContraceptiveVariant(str, Enum):
    COMBINED_ORAL = (
        "C"  # no longer collides with HormoneVariant.ESTROGEN_AND_PROGESTERONE
    )
    ORAL_CONTRACEPTIVE = "ORAL"
    OTHER = "O"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> "ContraceptiveVariant":
        return cls.UNKNOWN


_VARIANT_BY_CATEGORY: dict[str, type[Enum]] = {
    MedicationCategory.HORMONE.value: HormoneVariant,
    MedicationCategory.THERAPY.value: TherapyVariant,
    MedicationCategory.CONTRACEPTIVE.value: ContraceptiveVariant,
}

# EMBED's sentinel for an invalid/missing accession number. Named as a
# constant (rather than a bare 999 in the Field call below) so the meaning
# is documented once and searchable if other EMBED tables use the same
# sentinel on their own accession columns.
_INVALID_ACC_ANON: int = 999


# ---------------------------------------------------------------------------
# Stage 1: pandera schema for the raw table
#
# This validates the DataFrame as a whole (vectorized), not row by row.
# It's the right place for cheap structural checks across potentially
# hundreds of thousands of rows before any Python objects get built.
#
# The type/code relationship is pulled out into its own named, registered
# check (`code_matches_type`) and its own small schema (`TypeCodeSchema`),
# so the "code is scoped by type" rule is a standalone, testable unit
# rather than a helper buried inside RawMedicationSchema. RawMedicationSchema
# then just inherits it -- ordinary Python subclassing, nothing pandera-
# specific -- and adds the rest of the raw columns.
# ---------------------------------------------------------------------------


@pa.extensions.register_check_method(statistics=[], supported_types=(DataFrame,))
def code_matches_type(df: DataFrame) -> Series[bool]:
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


class TypeCodeSchema(pa.DataFrameModel):
    """Isolated schema for just the type/code relationship.

    Kept deliberately narrow -- two columns and one check -- so the rule
    "code is only meaningful in the context of type" is visible and
    testable on its own, independent of everything else in the raw table.
    """

    type: Series[str] = pa.Field(isin=[c.value for c in MedicationCategory])
    code: Series[str]

    class Config:
        coerce = True
        strict = False
        code_matches_type = ()  # invokes the registered check above

    @pa.parser("type", "code")
    def strip_whitespace(cls, series: Series[str]) -> Series[str]:
        """Strip stray leading/trailing whitespace before `isin` and
        `code_matches_type` run, so e.g. "H " isn't wrongly flagged as an
        invalid category. `.str.strip()` leaves real NaN/None alone --
        it does not stringify missing values -- so nullable columns are
        unaffected. Runs once per named field, before any Field checks.
        """
        return series.str.strip()


class RawMedicationSchema(TypeCodeSchema):
    """Full raw-table schema. Inherits the type/code check from TypeCodeSchema
    via ordinary subclassing and adds the remaining raw columns."""

    empi_anon: Series[int]
    acc_anon: Series[int] = pa.Field(ne=_INVALID_ACC_ANON)

    continuous: Series[str] = pa.Field(isin=["Y", "N", "U", "NA", "nan"], nullable=True)
    current: Series[str] = pa.Field(isin=["Y", "N", "U", "NA", "nan"], nullable=True)

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
    def strip_remaining_whitespace(cls, series: Series[str]) -> Series[str]:
        return series.str.strip()


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


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    raw_rows = [
        # Hormone record, code "C" -> combined estrogen/progesterone HRT
        dict(
            empi_anon=1,
            acc_anon=101,
            type="H",
            code="C",
            continuous="Y  ",
            current=" Y",
            duration=36,  # stray whitespace, on purpose
            first_age="52",
            mfirst="3",
            yfirst="2018",
            last_age="55",
            mlast="3",
            ylast="2021",
            comment="self-reported combined HRT",
        ),
        # Contraceptive record, code "C" -> combined oral contraceptive.
        # Under the ORIGINAL flat enum this silently resolved to
        # ESTROGEN_AND_PROGESTERONE because CONTRACEPTIVE = "C" was
        # defined second and became a value-alias. Here it resolves
        # correctly because the two "C"s live in separate enums.
        dict(
            empi_anon=2,
            acc_anon=202,
            type="O",
            code="C",
            continuous="N",
            current="N",
            duration=60,
            first_age="22",
            mfirst="1",
            yfirst="2005",
            last_age="27",
            mlast="1",
            ylast="2010",
            comment="self-reported combined oral contraceptive",
        ),
        # Therapy record with a garbage age and a missing stop date --
        # should still parse, with those fields coming back as None.
        dict(
            empi_anon=3,
            acc_anon=303,
            type="T",
            code="ET",
            continuous="U",
            current="Y",
            duration="unk",
            first_age="not recorded",
            mfirst="",
            yfirst="",
            last_age="61.5",
            mlast="7",
            ylast="2022",
            comment="",
        ),
        # Malformed: code "ZZ" is not valid for type "H" (hormone).
        # pandera's cross-column check catches this at the bulk stage,
        # before pydantic ever sees the row.
        dict(
            empi_anon=4,
            acc_anon=404,
            type="H",
            code="ZZ",
            continuous="N",
            current="N",
            duration=12,
            first_age="40",
            mfirst="5",
            yfirst="2015",
            last_age="41",
            mlast="5",
            ylast="2016",
            comment="bad code for its category",
        ),
        # Malformed: acc_anon is EMBED's sentinel for an invalid/missing
        # accession. Otherwise a perfectly well-formed hormone row.
        dict(
            empi_anon=5,
            acc_anon=999,
            type="H",
            code="ESTRO",
            continuous="Y",
            current="N",
            duration=24,
            first_age="48",
            mfirst="9",
            yfirst="2019",
            last_age="50",
            mlast="9",
            ylast="2021",
            comment="acc_anon sentinel for invalid/missing accession",
        ),
    ]

    raw_df = pd.DataFrame(raw_rows)

    print("=== Stage 1: pandera validation of the raw table ===")
    try:
        validated_df = RawMedicationSchema.validate(raw_df, lazy=True)
        print("All rows passed pandera validation.\n")
    except pa.errors.SchemaErrors as exc:
        print("pandera caught schema-level problems:")
        print(exc.failure_cases[["column", "check", "index", "failure_case"]])
        print()
        # Use exc.data, not raw_df: exc.data is what pandera produced AFTER
        # running the strip_whitespace/strip_remaining_whitespace parsers.
        # Dropping from raw_df instead would silently discard that cleaning
        # for every surviving row -- it happened not to matter here only
        # because stage 2 re-strips continuous/current defensively on its
        # own; the procedure_history.py version of this same pipeline hits
        # a real failure from this mistake, since its whitespace-bearing
        # column feeds the pydantic discriminator directly.
        bad_indices = set(exc.failure_cases["index"].dropna().astype(int))
        validated_df = exc.data.drop(index=bad_indices).reset_index(drop=True)

    print("=== Stage 2: pydantic parsing of each row ===")
    records, errors = parse_medication_dataframe(validated_df)

    for record in records:
        print(
            f"{type(record).__name__}: category={record.category!r} "
            f"variant={record.variant!r} code_raw={record.code_raw!r} "
            f"start={record.start_date} stop={record.stop_date}"
        )

    if errors:
        print("\nRows that failed pydantic validation:")
        for err in errors:
            print(err)
