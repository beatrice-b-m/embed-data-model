# Documentation

Use the repository [README](../README.md) for installation and the short
quickstart. The longer [user guide](user-guide.md) explains the
public objects and source adapter. The [downstream migration
guide](downstream-migration.md) is the checklist for people and coding agents
porting a consumer to `embed_data_model`.

## Current contracts and references

- [Mutable scaffold contract](mutable-scaffold-contract.md) — governing
  behavior for graph ownership, semantic loading, refresh/merge, movement,
  validation, and scope.
- [Mutable scaffold API decisions](mutable-scaffold-api.md) — settled public
  method and field semantics that implement the contract.
- [Current qualification](qualification.md) — repository-level checks for the
  current root project and coexistence with the separate `embed-toolkit`
  package. It should state exactly which revision and environment were tested.
- [Mammography breast coordinate system](mammography-breast-coordinate-system.md)
  — reference vocabulary for laterality, location, depth, and image-coordinate
  consumers.
- [Mutable scaffold test disposition](mutable-scaffold-test-disposition.md) —
  current ownership and replacement status for retired assertions.

The contract and API decisions define behavior. Qualification records describe
what was tested at a particular revision; they do not expand the API, qualify
private data or real pixels, or announce a release. The archived qualification
record is [available for historical context](archive/mutable-scaffold-qualification.md).

## Historical records

Superseded plans, assessments, reviews, and the probe used for the 2026-09-09
assessment live in [archive](archive/). They preserve the reasoning and source
observations behind the current contract. Their code paths, counts, package
names, and recommendations describe their reviewed revisions; they are not
current implementation instructions.

The archive includes:

- earlier clinical-model evaluations and resolution plans;
- internal-v2 conformance reviews and plans;
- the legacy retirement record and orchestration plans;
- lightweight/system architecture reviews;
- mutable scaffold implementation/review/qualification records;
- patient-history and September scaffold assessments; and
- the historical assessment probe script.

When an archived document links to another archived document, the link points
within `archive/`. Links back to active contracts point to the parent `docs/`
directory. This keeps historical evidence readable without presenting it as a
live work queue.
