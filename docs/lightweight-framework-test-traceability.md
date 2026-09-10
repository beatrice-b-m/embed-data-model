# Lightweight framework test traceability

Date: 2026-08-26

This matrix records where the scientific and construction invariants retained
from the former builder architecture are verified after migration to
`DatasetGraph`. It is the companion to the historical
[`lightweight-framework-architecture-review.md`](archive/lightweight-framework-architecture-review.md);
deleted tests are not a second
supported API contract.

## Replacement matrix

| Retired coverage area | Preserved invariant | Canonical replacement tests |
|---|---|---|
| Clinical identity and source ledger | Nullable values never manufacture identities; typed row keys survive DataFrame conversion; replay and conflicting evidence have deterministic outcomes. | `test_nullable_identifiers_never_manufacture_domain_identity`, `test_numeric_identifiers_are_deliberate_and_boolean_ids_are_invalid`, `test_source_keys_are_typed_and_round_trip`, `test_dataframe_index_and_numpy_scalars_become_canonical_keys`, `test_replay_is_idempotent_and_changed_same_address_conflicts`, and `test_distinct_conflicting_observations_leave_exam_field_unresolved` in `tests/unit/test_lightweight_framework.py` |
| Patient/exam construction and graph assembly | Patient-only and exam-only inputs are valid; repeated loads enrich the same canonical objects; root collections are read-only; strict and audit transactions have distinct atomicity rules. | `test_patient_and_exam_tables_load_independently`, `test_incremental_order_resolves_to_the_same_canonical_objects`, `test_graph_root_collections_are_read_only_views`, and `test_audit_commits_safe_rows_and_strict_rolls_back_invocation` in `tests/unit/test_lightweight_framework.py` |
| Finding identity, interpretation, and anatomy | Finding identity is independent of mutable interpretation/anatomy; source-specific anatomy codes normalize consistently; conflicting observations remain visible and unresolved. | `test_finding_identity_does_not_depend_on_side_or_interpretation`, `test_finding_conflicts_are_order_independent_and_leave_field_unresolved`, `test_finding_anatomy_normalizes_magview_codes_and_distance`, `test_repeated_finding_anatomy_rows_merge_only_compatible_values`, and `test_invalid_finding_distance_is_a_transactional_issue` in `tests/unit/test_lightweight_framework.py`; MagView location tests in `tests/unit/test_magview.py`; `test_interpretation_tracks_field_availability_independently` in `tests/unit/test_clinical_domain_contracts.py` |
| Clinical/image reconciliation and image source ledger | Image-only input creates no clinical nodes; qualifying later clinical evidence resolves edges onto the same graph; conflicting parent evidence remains unattached and inspectable. | `test_image_table_loads_alone_without_manufacturing_clinical_nodes`, `test_clinical_load_resolves_image_edges_onto_same_canonical_graph`, and `test_image_patient_conflict_remains_unresolved_and_unattached` in `tests/unit/test_lightweight_framework.py` |
| ROI identity, geometry, and provenance | ROI identity is image-scoped; delayed image resolution preserves object identity; conflicts do not overwrite resolved convenience state; coordinate and DBT-frame semantics remain governed. | ROI graph tests in `tests/unit/test_lightweight_framework.py`, including `test_multi_roi_rows_preserve_image_scope_frames_and_derivation`; geometry tests in `tests/unit/test_imaging.py`; locator/provenance tests in `tests/unit/test_roi_locators.py` |
| Patient histories | Partial temporal precision and source identity remain explicit; history-only loads compose onto the canonical patient; invalid children obey transaction mode. | `test_auxiliary_histories_load_onto_one_canonical_patient`, `test_history_then_exam_enriches_same_patient_identity`, `test_invalid_history_child_rolls_back_safe_parent_in_strict_mode`, and `test_audit_history_retains_safe_patient_when_child_is_incomplete` in `tests/unit/test_lightweight_framework.py`; `tests/unit/test_patient_history.py` |
| Procedures and pathology | Procedure identity is governed; pathology row and slot evidence remain distinct; unresolved attribution is retained and can resolve incrementally without evidence loss. | Procedure/pathology tests in `tests/unit/test_lightweight_framework.py`, from `test_verified_procedure_table_uses_governed_identity_and_patient` through `test_pathology_attribution_resolves_incrementally_without_losing_evidence`; `tests/unit/test_clinical_domain_contracts.py` |
| Patient and exam attributes | Source and temporal context are retained; absent and explicit-null observations differ; invalid observations follow strict/audit safety rules. | `test_patient_attributes_preserve_source_and_temporal_context`, the patient-attribute transaction tests, and `test_exam_observations_distinguish_absent_from_explicit_null` in `tests/unit/test_lightweight_framework.py` |
| Wide MagView projection | One wide source row can contribute every supported grain without requiring optional child values or reiterating a one-shot input; explicit and wide tables remain distinct evidence. | `test_wide_magview_projects_supported_grains_through_one_graph`, `test_wide_magview_does_not_require_child_grains_or_reiterate_input`, and `test_explicit_and_wide_tables_contribute_distinct_source_evidence` in `tests/unit/test_lightweight_framework.py` |
| Profile contracts and column inventories | Ordinary loading accepts partial renames and explicit optional-field unbinding; namespace incompatibility fails before input consumption. Exhaustive profile validation is intentionally not retained as a runtime invariant. | `test_partial_column_maps_allow_renames_and_optional_unbinding` and `test_namespace_mismatch_fails_before_consuming_input` in `tests/unit/test_lightweight_framework.py` |
| Package and import boundary | The installed wheel exposes the framework facade and loads outside the source tree; removed adapter/config products are no longer import targets. | `tests/integration/test_wheel_smoke.py` and `tests/unit/test_imports.py` |

## Retention rule

Future removals or rewrites must update this matrix in the same commit. A test
may move or be consolidated only when its replacement still verifies the
scientific meaning, identity rule, transaction behavior, or package boundary
listed here. Tests that merely asserted the shape of a retired build product,
profile inventory, clone assembly, or duplicate flat collection are not
retained invariants.
