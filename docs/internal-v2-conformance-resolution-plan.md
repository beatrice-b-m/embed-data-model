# Internal V2 conformance resolution plan

Date: 2026-08-25
Source review: `docs/internal-v2-conformance-review.md`
Implementation scope: `unified-system/`

## Assessment

The six findings in the review are reproducible in the current implementation.
The review's distinction between source-fidelity defects and intentionally
derived analytical behavior is sound, and its non-findings should remain out
of the remediation scope.

| Finding | Assessment | Planning consequence |
| --- | --- | --- |
| DBT depth-derivation provenance is lost | Confirmed, high | Add a governed, per-ROI binding for `ROI_depth_derived`; do not infer this value from the presence of frames. |
| ROI-transfer relatedness ignores acquisition group | Confirmed, high | Make matching populated acquisition groups the only profile-backed default; retain overrides only as labeled caller assertions. |
| Source construction defaults to strict | Confirmed, high | Change the public default deliberately across every implicit `BuildPolicy()` user, not only the two table builders. |
| Derived image type is collapsed into modality | Confirmed, medium | Separate the raw/open `FinalImageType` value from the normalized acquisition-kind helper before changing ROI behavior. |
| Unknown acquisition type drops usable ROI geometry | Confirmed, medium | Extend the ROI provenance contract with an unresolved-modality state and preserve coordinates without interpreting depth. |
| `birth_year` contradicts the Internal V2 contract | Confirmed, medium | Stop the built-in profile from projecting it and decouple custom-profile projection from the built-in inventory. |

The current suite is a clean baseline (`459 passed` on 2026-08-25), but several
tests encode the behavior being corrected. Those tests must be changed rather
than used as compatibility requirements.

## Resolution principles

1. Raw rows remain the lossless fallback in `SourceOccurrence`; domain objects
   preserve governed meanings without inventing semantics.
2. Profile-backed facts and caller/project assertions are distinct in both
   behavior and serialized evidence.
3. Unknown optional metadata limits dependent workflows; it does not erase
   otherwise valid identity or image-local geometry.
4. Strict validation remains available through an explicit
   `BuildPolicy(BuildMode.STRICT)` selection.
5. Each finding is implemented and committed as one coherent change, followed
   by `git log --oneline -3` as required by the repository policy.

## Work plan

### 1. Preserve derived image type independently

Introduce a `derived_image_type` semantic field bound to `FinalImageType` and a
source-preserving value on `MammogramImage`. The value should accept the known
Internal V2 values (`2D`, `3D`, `cview`, `ROI_SS`, `ROI_SSC`, and `other`) while
retaining an unrecognized populated string instead of coercing it to
`UNKNOWN`.

Keep `ImageModality` as the normalized acquisition-kind helper used by existing
workflows. Populate it from the derived image type through an explicit
normalization function for compatibility, but do not present that helper as
the source DICOM `Modality`. Update image reconciliation, attribute provenance,
serialization, column helpers, and the image profile contract so repeated rows
can fill or conflict on `derived_image_type` just like other invariant image
metadata.

Acceptance criteria:

- `ROI_SS`, `ROI_SSC`, `other`, and an unknown future value round-trip on the
  image object and in `to_dict()`.
- `2D`, `3D`/`DBT`, and `cview` still normalize to the existing workflow kinds.
- No image type is excluded by the adapter.
- Tests distinguish `derived_image_type` from normalized `modality`.

Suggested commit: `feat(images): preserve derived image type`

### 2. Preserve DBT depth-derivation provenance

Add `roi_depth_derived` to column configuration, profile candidates, the V1c
field inventory, and `_ColumnAliases`, with the built-in binding
`ROI_depth_derived`. Parse it as a collection aligned one-for-one with
`ROI_coords`, independently of `num_ROI`.

For a DBT ROI with interpreted frames, map a true flag to
`RoiDepthFrameProvenance.DERIVED` and attach one stable, documented derivation
method identifier. Map false to `SOURCE_SUPPLIED`. Empty frames remain
`UNAVAILABLE_DBT`; a true derivation flag without usable frame evidence should
produce a structured issue rather than claim a derived placement. Reject or
audit non-boolean values and populated collections whose length does not match
the coordinate collection.

Acceptance criteria:

- Mixed true/false flags on a multi-ROI row produce the corresponding
  per-ROI provenance states.
- Missing flags preserve the current source-supplied interpretation for
  backward-compatible/custom inputs, while the raw absence remains visible.
- Misalignment and invalid values follow the selected build policy.
- Derived provenance always has a non-empty method; non-derived provenance
  never has one.

Suggested commit: `fix(rois): preserve depth derivation provenance`

### 3. Represent coordinates when modality is unresolved

Add an explicit unresolved-modality depth/frame provenance state and allow
`RoiSourceProvenance` to carry `ImageModality.UNKNOWN` only with that state.
Construct the ROI geometry and source count normally, but do not interpret raw
ROI frame values as 2D- or DBT-frame semantics while modality is unknown. The
raw values remain available through the source occurrence.

Update modality-dependent workflows to reject, skip, or return a structured
limitation when they require known acquisition or depth semantics. Do not
silently treat unknown as 2D.

Acceptance criteria:

- A row with valid coordinates and unknown modality produces both an image and
  ROI without an error-severity build issue solely for unknown modality.
- The ROI reports unresolved depth/frame semantics and no interpreted frame
  indices.
- Invalid coordinates remain build issues.
- DBT and 2D provenance invariants remain unchanged.

Suggested commit: `fix(rois): retain geometry for unknown modality`

### 4. Restrict default transfer relatedness to acquisition group

Replace `_has_shared_acquisition_context()` as the default eligibility source
with equality of two populated `coordinate_frame_id` values, which the V1c
adapter sources from `acquisition_group_id`. Accession, study UID, and series
UID remain descriptive evidence only.

Preserve the caller override if it is needed by project algorithms, but add a
typed relatedness basis (for example, profile acquisition group, caller
assertion, caller denial, or unavailable) and serialize it with the evidence.
A caller assertion may override absent or different acquisition groups, but it
must never be indistinguishable from profile-guaranteed eligibility.

Acceptance criteria:

- Equal accession/study/series values with absent or different acquisition
  groups are not related by default and transfer is skipped.
- Equal populated acquisition groups can be related, subject to the existing
  patient, breast, and view preconditions.
- Blank acquisition groups never match.
- Explicit overrides are behaviorally supported and visibly labeled in the
  relationship and transfer result evidence.

Suggested commit: `fix(roi-transfer): require acquisition-group relatedness`

### 5. Make fail-soft behavior the public default

Change the default `BuildPolicy` mode to `AUDIT` and provide an obvious strict
constructor or documented explicit example. Audit every implicit-policy call
site: `build_clinical_tables`, `build_image_tables`,
`assemble_clinical_image_graph`, and `select_patient_attribute_as_of`.

Do not weaken object identity requirements. Rows lacking sufficient identity
remain unresolved source occurrences and do not manufacture domain objects.
Update tests that expect an exception to request strict mode explicitly; add
tests showing that omitted policy returns safe objects plus structured issues.

Acceptance criteria:

- Error-severity source issues do not raise when policy is omitted.
- Explicit strict mode raises at the same unsafe points as before.
- Audit results retain issues and correct `ResolutionState` values.
- Graph assembly and patient-attribute selection follow the same default
  convention as the table builders.

Suggested commit: `fix(build-policy): default public construction to audit`

### 6. Remove birth year from the built-in Internal V2 surface

Remove `birth_year` from the built-in Internal V2 field inventory, coverage
declarations, default projection, and Internal V2 adapter tests. A physical
`birth_year`-like column on an Internal V2 row must remain only in raw source
evidence.

Refactor the profile-contract boundary so a custom clinical contract can
explicitly declare and bind a birth-year observation without making that field
part of the built-in profile. Do not leave unconditional birth-year aliases in
the built-in `_ColumnAliases` path. This contract refactor is necessary to
fulfill the review's custom-profile allowance; merely keeping the field in the
shared exact inventory would preserve the contradiction.

Acceptance criteria:

- Internal V2 rows never produce `BIRTH_YEAR` observations.
- Internal V2 contract serialization contains no governed `birth_year` field.
- The raw input value is retained in `SourceOccurrence.raw_values`.
- A custom contract with an explicit binding can still produce a governed
  birth-year observation.

Suggested commit: `fix(profiles): remove internal-v2 birth-year projection`

### 7. Final conformance verification and documentation

After all six changes, update user-facing construction and image/ROI semantics
documentation. Add a compact traceability table linking each review finding to
its implementation tests and commit. Run formatting/static checks configured
by `pyproject.toml`, the targeted suites for each changed subsystem, and the
complete test suite.

Final acceptance criteria:

- All six finding-specific acceptance criteria pass.
- The full suite passes with no unreviewed expectation changes.
- Documentation identifies audit as the default and strict as opt-in.
- Documentation distinguishes raw derived image type, normalized modality,
  acquisition-group eligibility, and caller-asserted relatedness.
- The original non-findings remain unchanged: no `num_ROI` authority, no
  default image-type filtering, no removal of matching/transfer workflows, and
  no rejection of unmatched exams.

Suggested commit: `docs(conformance): record internal-v2 resolutions`

## Ordering and dependencies

Implement derived image type before unknown-modality ROI support so tests can
exercise `ROI_SS`, `ROI_SSC`, and `other` through the final domain surface.
Depth-derivation provenance and transfer relatedness are otherwise independent
and should be completed early because they can change scientific
interpretation. Make the fail-soft default change only after the finding-level
tests use explicit strict policy where required; otherwise broad expectation
changes can hide regressions. Complete the birth-year contract refactor after
the image contract extension so the generalized inventory design is changed
once and exercised by both profile kinds.

Recommended execution order: **1, 2, 3, 4, 5, 6, 7**.

## Risks and controls

- **API compatibility:** Adding serialized fields is additive, but changing the
  default policy and contract inventories is behavioral. Document both and
  retain explicit strict mode.
- **False provenance:** Do not invent a model/version for the derived-depth
  method. Use a stable generic identifier unless governed source metadata
  supplies a more specific one.
- **Contract overreach:** Custom-profile extensibility must not cause built-in
  Internal V2 to consume aliases for unavailable fields.
- **Test migration masking defects:** Change exception tests to explicit strict
  mode before changing the default, then add separate audit-default tests.
- **Workflow ambiguity:** Any permissive transfer beyond acquisition-group
  equality must be caller-asserted and visible in serialized evidence.

## Out of scope

This remediation does not make `num_ROI` authoritative, exclude ROI-derived or
unknown image types, add complete catalog coverage, remove finding-to-ROI
matching, remove ROI transfer, or reinterpret unmatched exams. Those behaviors
were correctly classified as intentional or optional in the source review.
