# Patient history auxiliary-table assessment

Date: 2026-08-25  
Scope: former reference code from `temp/hormonehist/` and `temp/prochist/`,
preserved here and interpreted against the runtime under `unified-system/`

## Conclusion

`HormoneHist` and `ProcHist` are best represented as patient-owned,
source-attributed history observations. They should not be treated as exam
children merely because they carry `acc_anon`, and `ProcHist` rows should not be
inserted into the existing verified `Procedure`/pathology graph.

The safe hierarchy is:

```text
Patient
├── exams
│   └── findings ── verified Procedure / pathology associations
└── history_observations
    ├── MedicationHistoryObservation  ← HormoneHist
    └── ProcedureHistoryObservation   ← ProcHist
```

This keeps self-report, source provenance, missingness, and approximate timing
visible while leaving projects free to reconcile a reported history item to a
verified event later.

## Evidence limits

The underlying tables and data dictionary were unavailable. This assessment can
therefore establish only what the checked-in code asserts or strongly implies.
It cannot establish column prevalence, actual null representations, row
uniqueness, duration units, date semantics, or whether the vocabularies are
complete.

The reference files are prototypes, not a single internally consistent
contract:

- `temp/hormonehist/medication_history.py` accepts `U`, `NA`, and `nan` for
  boolean-like fields, while `temp/hormonehist/validation.py` accepts only `Y`,
  `N`, and an empty string.
- The monolithic medication example defines explicit `UNKNOWN` enum members;
  `temp/hormonehist/general.py` does not.
- Both histories label `acc_anon == 999` as an invalid/missing sentinel, but the
  procedure reference explicitly says this must be confirmed against the data
  dictionary.
- The procedure reference says additional year, age, and date-like columns
  exist, but it neither names nor interprets them.

Those disagreements are evidence that ingestion should remain fail-soft and
open to future source values.

## HormoneHist

### Strongly supported row surface

| Column | Inferred role | Translation |
|---|---|---|
| `empi_anon` | patient identifier | `patient_id`; required to construct an observation |
| `acc_anon` | accession/collection context | optional `context_accession`; not event identity |
| `type` | category discriminator | category-scoped normalization |
| `code` | medication/treatment code | normalized only together with `type` |
| `continuous` | reported Y/N/unknown flag | optional boolean |
| `current` | reported Y/N/unknown flag | optional boolean |
| `duration` | reported duration in an unstated unit | preserved as text |
| `first_age`, `last_age` | reported start/stop age | partial time estimates |
| `mfirst`, `yfirst` | reported start month/year | partial time estimate, not an exact date |
| `mlast`, `ylast` | reported stop month/year | partial time estimate, not an exact date |
| `comment` | free-text report | optional comment |

The likely row grain is one reported exposure/treatment item for one patient,
captured in the context of an accession. There is no demonstrated stable
record ID, so physical source location is the observation identity.

### Category and code vocabularies

The meaning of `code` is category-dependent. The collision is material: `C`
means estrogen plus progesterone for `type=H`, but combined oral contraceptive
for `type=O`.

| `type` | Meaning | Supported `code` values |
|---|---|---|
| `H` | hormone | `C`, `ESTRO`, `PH`, `PP`, `PROGES`, `R`, `RA`, `TAMOX`, `V`, `O` |
| `T` | therapy | `CH`, `ET`, `H`, `RT`, `RTC`, `RTH`, `TAXOL`, `XRT`, `O` |
| `O` | contraceptive | `C`, `ORAL`, `O` |

The named meanings in the reference are translated to readable open strings,
but unknown future codes are retained rather than rejected. Physical source
identity is always retained; complete raw rows are retained only when the
caller explicitly selects `retain_raw=True`.

### Semantics that remain unestablished

- The unit of `duration` is unknown; it must not be named or calculated as
  months without external confirmation.
- It is unknown whether `first_*`/`last_*`, `duration`, `current`, and
  `continuous` are mutually consistent or which field should win.
- Month/year pairs indicate month precision at best. Converting them to day 1,
  as the prototype does, manufactures precision.
- `acc_anon` plausibly identifies the encounter/questionnaire context, not the
  start of exposure and not a stable history-item identity.

## ProcHist

### Strongly supported row surface

| Column | Inferred role | Translation |
|---|---|---|
| `empi_anon` | patient identifier | `patient_id`; required to construct an observation |
| `acc_anon` | accession/collection context | optional `context_accession`; not procedure identity |
| `type` | `G` gynecological or `B` breast | category-scoped normalization |
| `pcode` | procedure subtype | broad procedure plus optional detail |
| `result` | reported result code | optional reported result, not verified pathology |
| `side` | `L`, `R`, `B`, or blank | shared `Laterality` value |

The likely grain is one reported prior procedure for one patient. The reference
does not provide a reviewed performed-date binding. This is incompatible with
the existing `ProcedureIdentity(patient_id, performed_date, procedure_type,
laterality)`, and gynecological rows do not naturally have breast laterality.

### Procedure vocabularies

| `type` | `pcode` values and meanings |
|---|---|
| `G` | `HYST` hysterectomy; `H` partial hysterectomy; `O` one ovary removed; `OS` ovaries removed |
| `B` | `1` core biopsy; `SB` stereotactic core biopsy; `UCB` ultrasound core biopsy; `B` MRI-guided core biopsy; `E` excisional biopsy; `NB` needle biopsy; `CA` cyst aspiration; `FNA` fine-needle aspiration; `L` lumpectomy; `M` mastectomy; `D` reduction; `MP` mammoplasty; `R` reconstruction; `EXI` implants removed; `NO` non-oncologic |

The reference result vocabulary is `ADH`, `ALH`, `BEN`, `BOT`, `DE`, `DS`,
`FA`, `FN`, `ID`, `IF`, `IL`, `LS`, `LY`, `MAL`, `PA`, `SA`, `SF`, and
`NONE`. These labels mix broad assessments, histologies, and benign entities.
They are therefore preserved as a reported-result field rather than coerced
into `PathologyDiagnosis` or `PathologySeverity`.

### Semantics that remain unestablished

- The names, formats, and meanings of the extra age/year/date-like columns are
  unknown and stay raw-only.
- It is unknown whether `result` is patient-entered, abstracted from a prior
  record, or linked to the same procedure represented by `pcode`.
- Blank side is expected for at least some rows and is not itself proof of a
  malformed record.
- A `ProcHist` breast biopsy must not be linked to a current EMBED finding
  without explicit reconciliation evidence.

## Implemented boundary

The translation is intentionally split into two layers:

- `clinical/histories.py` contains source-neutral base and concrete observation
  classes. `Patient` owns an extensible `history_observations` collection.
- `sources/embed/histories.py` contains only the EMBED code mappings and
  parsing rules. `sources/embed/loader.py` projects `HormoneHist` and
  `ProcHist` rows through `DatasetGraph.transaction()`.

`load_embed` defaults to audit/fail-soft behavior. A row needs patient,
category, and item code to create an observation. Unknown but populated codes
produce issues and remain represented; audit mode retains a safely identified
patient when a child observation is incomplete. Callers can select
`mode="strict"` to roll back the complete invocation.

These tables deliberately have no mandatory profile contract. Any future
maintainer-only catalog validation requires confirmation from the actual data
dictionary and representative source rows.

The original prototypes under `temp/hormonehist/` and `temp/prochist/` were
deleted after this document captured their supported vocabularies,
contradictions, and unresolved production-verification questions.

## Production verification gate

Before promoting this reference translation to a verified profile:

1. Confirm exact columns, types, row count, and uniqueness candidates for both
   tables.
2. Profile raw null/sentinel values and cross-tabulate `type` with `code` or
   `pcode`.
3. Confirm the meaning of `acc_anon` and whether `999` is truly a sentinel in
   each table.
4. Confirm the unit and semantics of `duration` and relationships among the
   alternate time fields.
5. Inventory and interpret every ProcHist age/year/date-like column.
6. Measure unknown-code rates before deciding whether any should be errors.
7. Determine whether repeated rows are distinct reports, corrections, or
   duplicates before adding any semantic deduplication policy.
