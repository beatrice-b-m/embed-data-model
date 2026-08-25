"""
Two-stage validation workflow for EMBED auxiliary procedure-history data.

Mirrors medication_history.py's structure:
    Stage 1 (pandera): bulk checks over the whole raw DataFrame.
    Stage 2 (pydantic): per-row parsing into a category-scoped domain object.

Two things are worth knowing up front, since they differ from the
medication table:

1. Unlike the medication "C" collision, `pcode` values here are already
   globally unique strings -- there's no raw-value collision forcing a
   category-scoped vocabulary. The category-scoped discriminated union
   below is included anyway, for the same type-safety reason (a breast
   procedure record literally cannot be constructed with a gynecological
   subvariant), not because the original code had a correctness bug like
   the medication one. It DOES fix a real gap, though: the original
   `ProcedureSubvariant.from_pcode` searches across ALL pcodes regardless
   of `type`, so a gynecological row carrying a breast pcode (or vice
   versa) would silently validate. The pandera cross-check below
   (`pcode_matches_category`) catches exactly that.

2. `ProcedureSide.UNKNOWN` was originally a bare space (`" "`). Our
   whitespace-stripping parser (same one used in medication_history.py)
   would collapse that to `""` before the enum ever sees it. That's fine
   -- `_missing_` still resolves `""` to UNKNOWN -- but the pandera `isin`
   list has to expect `""`, not `" "`, since it validates *after* the
   parser strips. Get this backwards and the parser silently defeats its
   own check. See the `side` field below for the fix in place.

`empi_anon`/`year`/`age`/date-ish columns exist in the real underlying
table but aren't modeled by the original ProcedureHistory class either
(its own comment flags them as "need significant review"), so they're
left out here too and simply pass through uncoerced (`strict = False`).
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stage 1: pandera schema for the raw table
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stage 2: pydantic discriminated union for row-level objects
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    raw_rows = [
        # Gynecological record, valid pcode for its category.
        dict(
            empi_anon=1,
            acc_anon=101,
            type="G",
            pcode="HYST",
            result="BEN",
            side=" ",  # bare-space "unknown" sentinel, on purpose
        ),
        # Breast record, valid pcode for its category, with stray whitespace
        # on type/pcode/result/side to exercise the strip parsers.
        dict(
            empi_anon=2,
            acc_anon=202,
            type=" B",
            pcode="SB ",
            result=" ADH",
            side="L ",
        ),
        # This row will actually be REJECTED at stage 1: `result` has an
        # isin check, so "ZZZ" never reaches pydantic's _missing_ -> NONE
        # fallback in this pipeline -- same precedence as code_matches_type
        # pre-empting HormoneVariant._missing_ in the medication schema.
        # See the standalone example after this loop for _missing_ doing
        # its job when a ProcedureResult is constructed directly.
        dict(
            empi_anon=3,
            acc_anon=303,
            type="B",
            pcode="M",
            result="ZZZ",
            side="B",
        ),
        # Malformed: pcode "HYST" (hysterectomy) is only valid for
        # type="G", but this row claims type="B". pcode_matches_category
        # should catch this -- the original from_pcode() would not have.
        dict(
            empi_anon=4,
            acc_anon=404,
            type="B",
            pcode="HYST",
            result="BEN",
            side="R",
        ),
        # Malformed: acc_anon is EMBED's sentinel for an invalid/missing
        # accession, otherwise a well-formed gynecological row.
        dict(
            empi_anon=5,
            acc_anon=999,
            type="G",
            pcode="O",
            result="BEN",
            side="L",
        ),
    ]
