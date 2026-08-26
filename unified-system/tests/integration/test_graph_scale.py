from benchmarks.graph_loading import measure_graph_load


def test_representative_scale_and_raw_retention_baseline() -> None:
    compact = measure_graph_load(row_count=1_000, lookup_count=5_000)
    retained = measure_graph_load(
        row_count=1_000,
        lookup_count=5_000,
        retain_raw=True,
    )

    assert compact.row_count == retained.row_count == 1_000
    assert compact.load_seconds > 0
    assert compact.lookup_seconds > 0
    assert retained.current_bytes > compact.current_bytes
    assert retained.peak_bytes > compact.peak_bytes
