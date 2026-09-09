"""Normalize supported table-like values without semantic identity leakage.

The table boundary deliberately keeps physical row information separate from
domain identity.  A requested ``key`` is useful for optional diagnostics and
source references, but it never decides whether a row is admitted.  In
particular, DataFrame indexes and row ordinals are never used as fallback
identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, Tuple, Union, cast

from embed_toolkit.core.source import CanonicalKey, canonicalize_source_key


KeyCallback = Callable[[Mapping[Any, Any]], Any]
KeySelector = Optional[Union[str, KeyCallback]]


@dataclass(frozen=True)
class TableIssue:
    """A shape-level problem that a source loader can convert to an Issue."""

    code: str
    message: str
    ordinal: int
    severity: str = "error"
    key_name: Optional[str] = None
    raw_key: Any = field(default=None, compare=False, hash=False, repr=False)


@dataclass(frozen=True)
class TableRecord:
    """One normalized mapping and an optional physical diagnostic key."""

    source_key: Optional[CanonicalKey]
    mapping: Mapping[Any, Any]
    ordinal: int
    issues: Tuple[TableIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping", MappingProxyType(dict(self.mapping)))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def row(self) -> Mapping[Any, Any]:
        """Readable alias for the normalized row mapping."""

        return self.mapping

    def __iter__(self) -> Iterator[Any]:
        """Allow ``source_key, mapping = record`` on issue-free records."""

        yield self.source_key
        yield self.mapping


class TableNormalizationError(ValueError):
    """A table-level shape error with fields suitable for an Issue."""

    def __init__(self, code: str, message: str, ordinal: Optional[int] = None) -> None:
        self.code = code
        self.ordinal = ordinal
        super().__init__(message)


def iter_records(table: Any, key: KeySelector = None) -> Iterator[TableRecord]:
    """Yield normalized records from mappings or a pandas-like DataFrame.

    Requested-key failures are attached to their row and never silently fall
    back to an index or position.  All rows are yielded so semantic loaders can
    use their own identifiers even when a physical diagnostic key is missing,
    duplicated, or malformed.
    """

    if table is None:
        return
    if key is not None and not isinstance(key, str) and not callable(key):
        raise TypeError("key must be a column name, callback, or None")

    dataframe = _dataframe_rows(table)
    if dataframe is not None:
        rows, index_values, range_index, index_unique = dataframe
        yield from _records_from_rows(
            rows,
            key,
            index_values=index_values,
            range_index=range_index,
            index_unique=index_unique,
        )
        return

    try:
        iterator = iter(table)
    except TypeError as exc:
        raise TableNormalizationError(
            "unsupported_table", "table must be an iterable of mappings"
        ) from exc
    rows = []
    for ordinal, row in enumerate(iterator):
        if not isinstance(row, Mapping):
            raise TableNormalizationError(
                "row_not_mapping", "table row must be a mapping", ordinal
            )
        rows.append(row)
    yield from _records_from_rows(rows, key)


def _dataframe_rows(
    table: Any,
) -> Optional[
    Tuple[list[Mapping[Any, Any]], list[Any], bool, Optional[bool]]
]:
    to_dict = getattr(table, "to_dict", None)
    if (
        not callable(to_dict)
        or not hasattr(table, "index")
        or not hasattr(table, "columns")
    ):
        return None
    try:
        rows = to_dict(orient="records")
    except TypeError:
        return None
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise TableNormalizationError(
            "invalid_dataframe_records",
            "DataFrame record conversion returned invalid rows",
        )
    index = table.index
    index_values = list(index)
    if len(index_values) != len(rows):
        raise TableNormalizationError(
            "invalid_dataframe_index", "DataFrame index length does not match its rows"
        )
    is_unique = getattr(index, "is_unique", None)
    if type(is_unique) is not bool:
        is_unique = None
    return (
        cast(list[Mapping[Any, Any]], rows),
        index_values,
        type(index).__name__ == "RangeIndex",
        is_unique,
    )


def _records_from_rows(
    rows: Iterable[Mapping[Any, Any]],
    key: KeySelector,
    *,
    index_values: Optional[list[Any]] = None,
    range_index: bool = False,
    index_unique: Optional[bool] = None,
) -> Iterator[TableRecord]:
    rows = list(rows)
    candidates: list[Optional[CanonicalKey]] = []
    issues: list[list[TableIssue]] = [[] for _ in rows]

    for ordinal, row in enumerate(rows):
        raw_key: Any = None
        if isinstance(key, str):
            if key not in row:
                candidates.append(None)
                issues[ordinal].append(
                    TableIssue(
                        "missing_source_key",
                        "requested source key column {!r} is absent".format(key),
                        ordinal,
                        severity="warning",
                        key_name=key,
                    )
                )
                continue
            raw_key = row[key]
        elif callable(key):
            try:
                raw_key = key(row)
            except Exception as exc:  # callback failures are row diagnostics
                candidates.append(None)
                issues[ordinal].append(
                    TableIssue(
                        "source_key_callback_failed",
                        "source key callback failed: {}".format(exc),
                        ordinal,
                        severity="warning",
                    )
                )
                continue
        else:
            # No physical source key was requested.  The DataFrame index and
            # row ordinal remain deliberately unavailable to this record.
            candidates.append(None)
            continue

        try:
            candidates.append(canonicalize_source_key(raw_key))
        except (TypeError, ValueError) as exc:
            candidates.append(None)
            issues[ordinal].append(
                TableIssue(
                    "unusable_source_key",
                    "requested source key is unusable: {}".format(exc),
                    ordinal,
                    severity="warning",
                    key_name=key if isinstance(key, str) else None,
                    raw_key=raw_key,
                )
            )

    _invalidate_duplicate_requested_keys(candidates, issues, key)

    for ordinal, row in enumerate(rows):
        yield TableRecord(candidates[ordinal], row, ordinal, tuple(issues[ordinal]))


def _invalidate_duplicate_requested_keys(
    candidates: list[Optional[CanonicalKey]],
    issues: list[list[TableIssue]],
    key: KeySelector,
) -> None:
    positions: dict[CanonicalKey, list[int]] = {}
    for ordinal, candidate in enumerate(candidates):
        if candidate is not None:
            positions.setdefault(candidate, []).append(ordinal)
    for candidate, ordinals in positions.items():
        if len(ordinals) < 2:
            continue
        for ordinal in ordinals:
            candidates[ordinal] = None
            issues[ordinal].append(
                TableIssue(
                    "duplicate_source_key",
                    "source key occurs more than once in this table",
                    ordinal,
                    severity="warning",
                    key_name=key if isinstance(key, str) else None,
                    raw_key=candidate,
                )
            )
