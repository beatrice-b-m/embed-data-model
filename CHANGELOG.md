# Changelog

## Unreleased

### Fixed

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
