# Completed mutable scaffold review

Status: all four findings resolved and requalified on 2026-09-09 against runtime
`664b4e2`. The original findings and reproductions below are historical.
See [qualification results](mutable-scaffold-qualification.md) for the full
Python 3.9–3.13 matrix, installed-wheel checks, static checks, and scale results.

Reviewed on 2026-09-09 at `f6fdeaa`, whose qualifying runtime is `90bb604`.
Scope: the completed implementation plan, API decisions, qualification evidence,
and implementation, with additional public-API probes of membership boundaries.

At the reviewed revision, the W1/W2/W4 completion gates had correctness gaps.
The existing 214 tests passed, including the installed-wheel test; Ruff and mypy
also passed over all 35 runtime files. Those checks did not cover the four
failures below. The initial review changed no runtime code and did not repeat
the full Python-version matrix, benchmark, or private-data qualification.

## Resolution

| Finding | Primary fix | Regression coverage |
|---|---|---|
| 1: source-SOP collisions | `dbd296d` | Original/derivative final-state checks, mixed rekey preflight, and installed metadata reload. |
| 2: reverse links after rekey | `726c21a` | One-sided and self-link rekey/clear; reciprocal and pending-link review probes. |
| 3: incoming crossing references | `b774bf6`, `2ec27bd` | Incoming linked/registry endpoints survive movement; internal edges are not duplicated. |
| 4: standalone rekey | `0ad9583`, `9836f09`, `b50154e` | Descendants, embedded context, carried references, semantic collections, and unhashable subclasses. |

Integration fixes preserve explicit ownership/source claims (`76187c7`, `0eb92da`),
propagate registered embedded context (`b100f07`), and reconcile rekeyed detached
children and copied shared descendants (`b2db363`, `664b4e2`). Rewrite application
uses an object-ID lookup rather than repeated subtree scans (`a3e02a1`).
Focused coverage is in `test_graph_review_regressions.py` and
`test_standalone_rekey.py`; the installed-wheel journey covers all four original
findings (`8c6a4c2`). Independent review and root integration checks found no
remaining issues in these fixes. All 239 tests pass on each supported Python
minor version; private-data and scientific qualification remain outside scope.

## 1. [P1] Reject source-SOP collisions before updating an image

Location: `unified-system/src/embed_toolkit/core/graph.py:359–364`.

`update` removes source indexes and writes the new source UID without checking
whether another original image owns it. `_index_source` then overwrites that
image's lookup. This violates the collision invariant enforced by registration
and can silently direct a subsequent metadata/ROI reload to the wrong image.
Preflight the proposed source identity before removing any existing aliases,
including when changing a derivative into an original.

Public-API reproduction:

```python
from embed_toolkit import DatasetGraph, MammogramImage, load_embed

graph = DatasetGraph()
first = graph.register(MammogramImage("I", source_sop_instance_uid="S1"))
second = graph.register(MammogramImage("J", source_sop_instance_uid="S2"))
first.update(source_sop_instance_uid="S2")  # Should reject the collision.
report = load_embed(
    images=[{"uid": "S2", "height": 123}],
    columns={"images": {"source_sop_instance_uid": "uid", "height": "height"}},
    into=graph,
)
print(first.height, second.height, report.issues)
# Observed: 123.0 None ()
```

## 2. [P2] Remove the old reverse link when rekeying a link source

Location: `unified-system/src/embed_toolkit/core/graph.py:446–451`.

For a one-sided supplied link A → B, rekeying A recreates the link under its new
key but leaves B's resolved reverse entry under A's old key. B consequently
returns the same exam twice. Clearing A's link removes only the new entry, so B
continues to expose a relationship that no supplied link supports. Remove the
old reverse entry as part of rewriting outgoing linked references; checking only
incoming supplied references misses this case.

```python
from embed_toolkit import DatasetGraph, Exam

graph = DatasetGraph()
a, b = graph.register(Exam("A")), graph.register(Exam("B"))
graph.set_linked_accessions(a, ["B"])
a.rekey(accession_number="C")
print([exam.accession_number for exam in b.linked_exams])
# Observed: ['C', 'C']; expected: ['C'].
graph.set_linked_accessions(a, [])
print([exam.accession_number for exam in b.linked_exams])
# Observed: ['C']; expected: [].
```

## 3. [P2] Carry incoming crossing links when moving their target

Location: `unified-system/src/embed_toolkit/core/graph.py:515–524`.

Pop carries outgoing references but leaves incoming references only in the source
graph, then clears the moving exam's resolved links. Moving B from A → B therefore
erases all evidence of A in B's destination. The accepted boundary rule requires
crossing associations to remain semantic references. Partition already preserves
this incoming case, but pop/register does not. Carry the incoming semantic edge
without carrying an owning A object, so it can resolve in the destination later.

```python
from embed_toolkit import DatasetGraph, Exam

source, target = DatasetGraph(), DatasetGraph()
a, b = source.register(Exam("A")), source.register(Exam("B"))
source.set_linked_accessions(a, ["B"])
target.register(b)
print(target.unresolved_references)
# Observed: (); expected: a pending semantic A → B link.
target.register(Exam("A"))
print(target.exam("A").linked_exams)
# Observed: (); expected: (b,).
```

## 4. [P2] Keep standalone descendants coherent during rekey

Location: `unified-system/src/embed_toolkit/core/entity.py:171–175`.

The standalone rekey path changes only the selected object's fields. Rekeying an
exam containing findings leaves their accession at the old value; registering the
tree accepts that inconsistency and creates a missing-parent reference. The same
problem applies to an image containing ROIs. W1/W2 require standalone operations
to agree with graph-backed operations. Propagate dependent identities and embedded
context using equivalent local collision checks before registering the subtree.

```python
from embed_toolkit import DatasetGraph, Exam, Finding, Laterality, Patient

patient = Patient("P")
exam = patient.add_exam(Exam("A"))
finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
exam.rekey(accession_number="B")
graph = DatasetGraph()
graph.register(patient)
print(finding.accession_number, graph.finding("B", "1"))
# Observed: A None; expected: B and the same finding object.
print(len(graph.unresolved_references))
# Observed: 1; expected: 0.
```

The affected gates have now been requalified with regression coverage for these
cases and their movement/rekey interactions, as recorded above.
