# Changelog

## Unreleased

### Changed

- Refresh replaces only fields whose columns the rows supply. An explicit null
  still clears a field, but a column absent from every row now leaves it
  unchanged. Previously a findings-only MagView load cleared the exam date,
  exam description and patient sex loaded earlier.
- Default column bindings now name only columns that exist in the internal
  EMBED tables. `patients.birth_year`, `images.series_instance_uid` and
  pathology `diagnosis`, `result_category` and `malignant` are unbound by
  default; bind them through `columns` if a source provides them.

### Fixed

- `mode="merge"` now detects values that contradict a populated value already
  in the graph. The field becomes unknown and the load reports
  `conflicting_<grain>_<field>`. Previously a later merge silently overwrote
  the earlier value, and only conflicts within one call were detected.
- A supplied null finding `side` now loads as bilateral and projects to both
  breast sides, matching the EMBED MagView convention. It previously loaded as
  unknown and the finding appeared on neither side.
- Coded values (assessment, recommendation, procedure type, pathology
  descriptors) are trimmed and uppercased before comparison, so formatting
  variants of one code no longer register as conflicting values. Procedure
  identities and descriptors now carry the normalized code.
- A negative finding `distance` (EMBED uses values such as -2 and -99 as
  undocumented exceptional codes) is no longer stored as a distance from the
  nipple. The raw code stays in `source_distance_codes` and the load reports
  `exceptional_finding_distance`. `validate` flags a negative or non-finite
  distance supplied directly.
- `ImagesInAcquisition` is loaded as `frame_count` only for DBT images; on other
  image types it is not a frame count. `validate` no longer rejects every DBT
  image with a frame count (it compared against the wrong modality value), and
  multiple frames on a non-DBT image is now a warning instead of an error.
- Image `height`, `width` and `frame_count` load as integers, matching their
  documented type; a fractional value is reported instead of stored.
- Unknown or conflicting location and depth codes are reported as finding
  `normalization_warnings` and load issues whether or not `source_keys` are
  supplied. Previously they were silently dropped without source keys.
  `FindingNormalizationEvidence` and `FindingNormalizationWarning` accept
  `source=None`.

## 0.1.0 — 2026-09-09

First tagged source release, `v0.1.0`, under the MIT license, with Python
3.9–3.13 qualification and no mandatory runtime dependencies.

### Data model

- Provide mutable patient, exam, finding, procedure, pathology, image, and ROI
  objects, with indexed graph membership and source lookups.
- Load optional EMBED tables using semantic identities, in-place refresh,
  explicit merge, and inspectable unresolved records and relationships.
- Support consumer extensions, explicit validation, live selections,
  independent partitions, and subtree movement.

### Packaging

- Distribute `embed-data-model` with the Python namespace `embed_data_model`.
- Include typed source, MIT license text, and wheel installation checks.
- Provide a Python project at the repository root with a locked development
  environment and tests for each supported Python minor version.

### Documentation

- Provide installation instructions, runnable researcher examples, and
  downstream integration guidance.
- Specify object and API contracts, development checks, and compatibility policy.
- Record local test qualification and synthetic loading measurements.
