# System architecture review

Date: 2026-08-25

> **Historical review — superseded.** Package topology, builders, workflows,
> and `temp/` references below describe the pre-recovery system. The governing
> current architecture is
> [lightweight-framework-architecture-review.md](lightweight-framework-architecture-review.md).

Editable Lucid chart:
[WIP EMBED Toolkit — System Architecture (Expanded Review)](https://lucid.app/lucidchart/5717732a-8d25-40e8-97df-fa1a657eaa6b/edit)

## Scope

The repository contains one packaged runtime implementation under
`unified-system/src/embed_toolkit`. It is a Python library rather than a
deployed service: there is no CLI, API server, persistence layer, job runner,
or infrastructure definition in the retained runtime tree. The files under
`temp/` are auxiliary reference code and are not included by the package
configuration.

The Lucid document has three pages:

1. **Runtime architecture** shows the governed data flow from source rows to
   domain graphs, research workflows, and inspectable results.
2. **Dependency topology** shows the main package-level imports and highlights
   structural concentration and boundary pressure.
3. **Source, ingestion, objects & assembly** removes workflows and downstream
   outputs to show the source surfaces, governed builders, build products,
   object graphs, evidence ledger, reconciliation decisions, and assembled
   clinical/image graph in greater detail.

## Runtime topology

The primary flow is:

1. MagView clinical rows, V1c image-metadata rows, and auxiliary history rows
   enter separate adapter paths. Pixel arrays and landmarks remain caller-owned
   runtime inputs.
2. Profile contracts, column mappings, source locators, field-coverage
   declarations, and `BuildPolicy` govern construction.
3. Builders produce separate `EmbedClinicalTables`, `EmbedImageTables`, and
   patient-history observations while retaining source occurrences and
   structured issues.
4. `assemble_clinical_image_graph` validates accession and patient identity,
   owns exam-to-image and side-to-image containment, and exposes side-aware
   finding/image candidate projections without asserting attribution.
5. Workflows localize findings and ROIs, infer finding-to-ROI matches, transfer
   ROIs between related acquisitions, extract patches, and build serializable
   mammogram render plans.
6. Workflow results carry typed status, evidence, warnings, and metadata for
   audit export and downstream inspection.

The central architectural invariant is that source-row multiplicity is evidence,
not clinical-object multiplicity. Containment and attribution are represented
separately, and unsafe or unresolved rows remain addressable through provenance
rather than being promoted into domain identities.

## Package responsibilities

| Package | Runtime LOC | Responsibility |
|---|---:|---|
| `adapters` | 4,732 | Source translation, reconciliation, and graph assembly |
| `workflows` | 1,887 | Localization, matching, ROI transfer, and patch extraction |
| `clinical` | 1,736 | Patient, exam, side, finding, interpretation, procedure, pathology, and history objects |
| `imaging` | 1,378 | Images, ROI identity/provenance, geometry, landmarks, and alignment |
| `config` | 1,312 | Column mappings, profile contracts, capabilities, and field coverage |
| `core` | 1,035 | Source-neutral primitives, anatomy, BI-RADS, provenance, and build policy |
| `audit` | 833 | Evidence, warnings, typed workflow results, and export |
| `visualization` | 399 | Serializable mammogram render plans |

The runtime source totals 13,320 lines across these packages.

## Architectural observations

### Strong boundaries

- Clinical and image ingestion produce separate governed results before an
  explicit reconciliation step.
- Provenance and build-policy contracts are centralized in `core` rather than
  reimplemented per adapter or workflow.
- Image-local ROI ownership and scoped `RoiLocator` values prevent bare ROI
  identifiers from being treated as durable cross-dataset identity.
- Workflow outputs use shared audit result contracts, which keeps warnings and
  evidence visible instead of collapsing operations to untyped values.

### Concentration and coupling

- `adapters/embed.py` contains 3,394 lines, or 25.5% of all runtime source. It
  combines clinical construction, image construction, reconciliation, graph
  assembly, pathology/procedure projection, ROI parsing, and low-level value
  helpers. This is the principal change-amplification hotspot.
- `workflows.finding_localization` imports `adapters.magview`. That places a
  source-specific normalization dependency inside the workflow layer instead
  of behind a source-neutral localization interface.
- `clinical.exams` imports `imaging.images` because an exam owns images after
  assembly. The dependency is intentional, but it means the clinical package
  is not independently reusable from the imaging package.
- The repository-level `temp/` reference trees sit beside the retained runtime.
  Although packaging excludes them, their location can make the active system
  boundary less obvious to maintainers.

### Contract documentation mismatch

`BuildPolicy` defaults to audit/fail-soft construction, which agrees with the
current README. The completed clinical object model resolution plan still says
strict construction is the default. The implementation and README are
internally consistent, but the governing-plan wording should be corrected so
future work does not infer the wrong failure behavior.

## Verification surface

Static inspection found 40 unit-test modules and 374 explicitly declared test
functions, with additional cases produced through parametrization. Coverage is
organized around contracts and behaviors—identity, provenance, adapters,
clinical/image graph assembly, workflows, visualization, regressions, and
import isolation—rather than mirroring the source tree mechanically.

These counts describe repository topology; this review did not execute the test
suite because it makes no runtime code change.
