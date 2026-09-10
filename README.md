# EMBED Data Model

EMBED Data Model is a small Python library for representing clinical and
mammography data as mutable objects. It can load any supported subset of EMBED
tables, retain the relationships that the rows actually establish, and leave
project-specific analysis to downstream code.

The package is version `0.1.0`. Its distribution name is `embed-data-model` and
its Python namespace is `embed_data_model`. The namespace is deliberately
separate from the existing `embed-toolkit` package; the old `embed_toolkit`
import is not an alias for this project.

## Install from the checkout

The repository is the source of the package while this project is being
prepared. From a clone, install the development environment at the repository
root:

```bash
git clone ssh://git@github.com/beatrice-b-m/wip-embed-toolkit.git
cd wip-embed-toolkit
uv sync --frozen
uv run --frozen python -m examples.researcher_journeys
```

For a local consumer that needs an editable install, use:

```bash
python -m pip install -e /path/to/wip-embed-toolkit
```

For a reproducible source install from the repository, pin the exact revision
you qualified:

```bash
python -m pip install \
  "git+ssh://git@github.com/beatrice-b-m/wip-embed-toolkit.git@<commit-sha>"
```

The placeholder is intentional: a downstream lockfile should name the actual
commit it uses. These instructions do not claim that a package-index release
exists. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and versioning
expectations and [LICENSE](LICENSE) for the MIT license.

## Quickstart

This complete synthetic example uses only the public root facade. It creates a
graph from one MagView-like row, edits the live exam, and makes an independent
partition for a downstream analysis. It does not require private EMBED data.

```python
from embed_data_model import DatasetGraph, Laterality, load_embed, validate


graph = DatasetGraph()
report = load_embed(
    magview=[
        {
            "empi_anon": "P-001",
            "acc_anon": "A-001",
            "numfind": 1,
            "side": "L",
            "desc": "screening",
            "asses": "4",
            "recc": "biopsy",
            "location": "UOQ",
            "depth": "P",
        }
    ],
    into=graph,
)

patient = graph.patient("P-001")
exam = graph.exam("A-001")
finding = graph.finding("A-001", "1")
assert patient is not None and exam is not None and finding is not None
assert finding.laterality is Laterality.LEFT
assert finding.interpretation.assessment == "4"
assert not report.issues

exam.update(description="reviewed")
assert graph.exam("A-001") is exam
assert validate(exam).valid

partitions = graph.partition(level="exam", key=lambda item: item.description)
reviewed_graph = partitions["reviewed"]
assert reviewed_graph.exam("A-001") is not exam
assert reviewed_graph.exam("A-001").description == "reviewed"
```

The [researcher journeys](examples/researcher_journeys.py) file contains a
small command-line runnable version of the same public surface. The longer
[user guide](unified-system/README.md) covers source mappings, relationships,
images, ROIs, validation, and movement. The [documentation index](docs/README.md)
points to current contracts and the downstream migration guide.

## What the library owns

The object graph is intentionally narrow:

```text
Patient -> Exam -> Finding -> Procedure -> Pathology
                  Exam -> Image -> ROI
                  Exam <-> linked Exam
                  Exam -> patient-scoped registry entry
```

`DatasetGraph` owns membership and indexes. `Patient`, `Exam`, `Finding`,
`Procedure`, `Pathology`, `CancerRegistryEntry`, `MammogramImage`, and
`RegionOfInterest` are mutable entities that can also be constructed without a
graph. `load_embed` accepts mappings, generators, or DataFrame-like tables and
returns a `LoadReport` containing the graph and issues from that invocation.

The loader groups rows by semantic identity before applying them. Patient,
exam, and finding IDs come from their mapped source fields; image identity is
separate from source SOP identity and source paths; ROI identity is scoped to
an image and an explicit collection key. DataFrame indexes and row order are
diagnostic details, never fallback clinical identity.

Refresh is the default load mode. It resets bound adapter-managed scalar fields
for each addressed grain, including an explicitly supplied null or an absent
field in a complete snapshot. It keeps object references, subclasses,
consumer-added attributes and metadata, unbound fields, and child grains that
were not supplied. `mode="merge"` applies supplied non-null scalar values and
reports conflicting populated values as issues. A single invocation is one
snapshot, so callers assembling streamed data must group complete semantic
objects before calling refresh.

Validation is explicit and read-only. `validate(entity)` returns a
`ValidationResult`; errors make it invalid, while warnings remain usable unless
`warnings_invalid=True` is requested. Selection views are non-owning. Graph
partitions are independent owning copies with copied ancestor context, so a
partition can be handed to a consumer without sharing mutable objects with the
source graph.

## Scope boundaries

The core translates source rows and preserves supplied relationships. It does
not read pixel files, infer clinical diagnoses, choose a cohort definition, or
provide a mandatory validation pipeline. Finding localization, finding-to-ROI
matching, ROI transfer, patch extraction, and visualization policy belong in
downstream repositories or consumer code. The package does not claim private
dataset qualification, real-pixel qualification, remote CI results, or a
published release from the synthetic checks in this repository.

Start with the [documentation index](docs/README.md). The [mutable scaffold
contract](docs/mutable-scaffold-contract.md) and [API decisions](docs/mutable-scaffold-api.md)
govern current behavior; historical plans, assessments, and reviews are kept
under [docs/archive](docs/archive/).
