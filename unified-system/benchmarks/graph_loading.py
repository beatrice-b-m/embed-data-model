"""Representative DatasetGraph loading and raw-retention measurements."""

from __future__ import annotations

import gc
import json
import tracemalloc
from dataclasses import asdict, dataclass
from time import perf_counter

from embed_toolkit import load_embed


@dataclass(frozen=True)
class LoadBenchmark:
    row_count: int
    retain_raw: bool
    load_seconds: float
    lookup_seconds: float
    current_bytes: int
    peak_bytes: int


def measure_graph_load(
    *,
    row_count: int = 2_000,
    lookup_count: int = 10_000,
    retain_raw: bool = False,
) -> LoadBenchmark:
    """Measure a patient-grain load with a realistic unknown research column."""

    rows = [
        {
            "empi_anon": f"P-{index:06d}",
            "unknown_research_field": f"row-{index:06d}-" + ("x" * 512),
        }
        for index in range(row_count)
    ]
    gc.collect()
    tracemalloc.start()
    load_started = perf_counter()
    report = load_embed(
        patients=rows,
        source_scope="benchmark",
        identity_namespace="benchmark-release",
        retain_raw=retain_raw,
    )
    load_seconds = perf_counter() - load_started

    lookup_started = perf_counter()
    for index in range(lookup_count):
        patient = report.graph.patient(f"P-{index % row_count:06d}")
        if patient is None:
            raise AssertionError("benchmark lookup lost a loaded patient")
    lookup_seconds = perf_counter() - lookup_started
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    if len(report.graph.patients) != row_count or report.issues:
        raise AssertionError("benchmark load did not preserve its input cardinality")
    return LoadBenchmark(
        row_count=row_count,
        retain_raw=retain_raw,
        load_seconds=load_seconds,
        lookup_seconds=lookup_seconds,
        current_bytes=current_bytes,
        peak_bytes=peak_bytes,
    )


if __name__ == "__main__":
    print(json.dumps(asdict(measure_graph_load()), indent=2, sort_keys=True))
    print(
        json.dumps(
            asdict(measure_graph_load(retain_raw=True)),
            indent=2,
            sort_keys=True,
        )
    )
