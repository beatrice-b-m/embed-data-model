"""Non-owning selection and independent owning copies with ancestor context."""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Generic, Iterator, Literal, Tuple, TypeVar, overload

from embed_data_model.core.entity import MutableEntity
from embed_data_model.core.graph import DatasetGraph, key_of, kind_of, subtree


if TYPE_CHECKING:
    from embed_data_model.clinical.patients import Patient
    from embed_data_model.clinical.exams import Exam
    from embed_data_model.clinical.findings import Finding
    from embed_data_model.clinical.procedures import Procedure
    from embed_data_model.clinical.pathology import Pathology, CancerRegistryEntry
    from embed_data_model.imaging.images import MammogramImage
    from embed_data_model.imaging.rois import RegionOfInterest

_SelectedT = TypeVar("_SelectedT")


@dataclass(frozen=True)
class Selection(Generic[_SelectedT]):
    """Non-owning snapshot of live graph objects.

    Attributes
    ----------
    graph : DatasetGraph
        Source graph; editing the selected objects affects it.
    level : str
        Selected registry kind.
    objects : tuple
        Live objects in source insertion order when evaluated. Membership is
        never automatically recomputed after object or graph changes.
    owning : bool, optional
        Descriptive marker, default False; does not confer ownership.

    Notes
    -----
    Iteration yields objects; len returns the snapshot size. The container is
    frozen but its objects remain mutable.
    """
    graph: DatasetGraph
    """Source graph; editing the selected objects affects it."""
    level: str
    """Selected registry kind."""
    objects: Tuple[_SelectedT, ...]
    """Live objects in source insertion order when evaluated. Membership is never
    automatically recomputed after object or graph changes.
    """
    owning: bool = False
    """Descriptive marker, default False; does not confer ownership."""

    def __iter__(self) -> Iterator[_SelectedT]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)


@overload
def select(graph: DatasetGraph, *, level: Literal['patient'], predicate: Callable[[Patient], bool]) -> Selection[Patient]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['exam'], predicate: Callable[[Exam], bool]) -> Selection[Exam]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['finding'], predicate: Callable[[Finding], bool]) -> Selection[Finding]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['procedure'], predicate: Callable[[Procedure], bool]) -> Selection[Procedure]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['pathology'], predicate: Callable[[Pathology], bool]) -> Selection[Pathology]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['registry'], predicate: Callable[[CancerRegistryEntry], bool]) -> Selection[CancerRegistryEntry]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['image'], predicate: Callable[[MammogramImage], bool]) -> Selection[MammogramImage]:
    ...

@overload
def select(graph: DatasetGraph, *, level: Literal['roi'], predicate: Callable[[RegionOfInterest], bool]) -> Selection[RegionOfInterest]:
    ...

def select(graph: DatasetGraph, *, level: str,
           predicate: Callable[[Any], bool]) -> Selection[Any]:
    """Select live objects at one registry level.

    Parameters
    ----------
    level : {"patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi"}
        Registry to inspect in insertion order.
    predicate : callable
        Called once per object; truthy results include that object. Exceptions
        propagate. The callback should not change registry membership.

    Returns
    -------
    Selection
        Non-owning snapshot of membership with live typed objects. Later changes
        do not re-evaluate the predicate; editing an object affects the graph.

    Raises
    ------
    ValueError
        Unknown level.

    Notes
    -----
    graph is the source DatasetGraph; no ownership is transferred.
    """

    if level not in graph._registries:
        raise ValueError("Unknown selection level: " + level)
    return Selection(graph, level, tuple(obj for obj in graph._registries[level].values() if predicate(obj)))


@overload
def partition(graph: DatasetGraph, *, level: Literal['patient'], key: Callable[[Patient], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['exam'], key: Callable[[Exam], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['finding'], key: Callable[[Finding], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['procedure'], key: Callable[[Procedure], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['pathology'], key: Callable[[Pathology], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['registry'], key: Callable[[CancerRegistryEntry], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['image'], key: Callable[[MammogramImage], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: Literal['roi'], key: Callable[[RegionOfInterest], Any]) -> Dict[Any, DatasetGraph]:
    ...

@overload
def partition(graph: DatasetGraph, *, level: str, key: Callable[[Any], Any]) -> Dict[Any, DatasetGraph]:
    ...

def partition(graph: DatasetGraph, *, level: str,
              key: Callable[[Any], Any]) -> Dict[Any, DatasetGraph]:
    """Make independent owning graphs grouped by a callback.

    Parameters
    ----------
    level : {"patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi"}
        Registry to group in insertion order.
    key : callable
        Returns a hashable group key, or a list/set/frozenset of keys to include
        the object in multiple outputs. A tuple is a single key. An empty list
        omits the object. Exceptions propagate; avoid mutating membership.

    Returns
    -------
    dict of hashable to DatasetGraph
        One independent graph per group. Containment and consumer attributes are
        deep-copied, preserving subclasses and sharing within each output.
        Ancestor shells have context=True and contain only selected branches.
        Dictionary order follows first occurrence of group keys (set order is
        unspecified). Cross-boundary associations remain semantic references.

    Raises
    ------
    ValueError
        Unknown level or consumer state that cannot be independently copied.
    TypeError
        A group key is not hashable.

    Notes
    -----
    Consumer __deepcopy__ hooks are honored. Large overlapping groups multiply
    memory use; this synchronous operation has no cancellation control.

    The graph parameter supplies the source DatasetGraph.
    """
    if level not in graph._registries:
        raise ValueError("Unknown partition level: " + level)
    groups: Dict[Any, list[Any]] = {}
    for obj in graph._registries[level].values():
        result = key(obj)
        keys = result if isinstance(result, (list, set, frozenset)) else (result,)
        for group in keys:
            groups.setdefault(group, []).append(obj)
    return {group: _copy_group(graph, objects) for group, objects in groups.items()}


def _copy_group(graph: DatasetGraph, selected: list[Any]) -> DatasetGraph:
    included: Dict[int, Any] = {}
    complete: set[int] = set()
    for obj in selected:
        branch = subtree(obj)
        included.update(branch)
        complete.update(branch)
    todo = [id(obj) for obj in selected]
    while todo:
        oid = todo.pop()
        for pid in graph._parents.get(oid, ()):
            if pid not in included:
                included[pid] = graph._objects[pid]
                todo.append(pid)
    shells = {oid: copy(obj) for oid, obj in included.items()}
    omitted = object()

    transformed: Dict[int, Any] = {}

    def substitute(value: Any) -> Any:
        if isinstance(value, MutableEntity):
            if id(value) in graph._objects:
                return shells.get(id(value), omitted)
            if type(value).__name__ == "BreastSide":
                side = copy(value)
                side.__dict__ = {name: substitute(item) for name, item in value.__dict__.items() if name != "_graph"}
                object.__setattr__(side, "_graph", None)
                return side
            return value  # Embedded observations retain their own copy protocol.
        if id(value) in transformed:
            return transformed[id(value)]
        if isinstance(value, list):
            items: list[Any] = []
            transformed[id(value)] = items
            items.extend(new for item in value if (new := substitute(item)) is not omitted)
            return items
        if isinstance(value, dict):
            mapping: Dict[Any, Any] = {}
            transformed[id(value)] = mapping
            mapping.update((k, new) for k, item in value.items() if (new := substitute(item)) is not omitted)
            return mapping
        if isinstance(value, tuple):
            return tuple(new for item in value if (new := substitute(item)) is not omitted)
        if isinstance(value, set):
            return {new for item in value if (new := substitute(item)) is not omitted}
        return value

    # Create lightweight local shells before deep copying. Unselected siblings
    # never get copied, and all shells share one final deepcopy memo per output.
    for oid, source in included.items():
        shell = shells[oid]
        shell.__dict__ = {}
        for name, value in source.__dict__.items():
            if name == "_graph":
                object.__setattr__(shell, name, None)
            elif name == "_linked_exams":
                object.__setattr__(shell, name, {})
            else:
                replaced = substitute(value)
                if replaced is not omitted:
                    object.__setattr__(shell, name, replaced)
        object.__setattr__(shell, "context", oid not in complete)
    memo: Dict[int, Any] = {}
    try:
        copies = {oid: deepcopy(shell, memo) for oid, shell in shells.items()}
    except Exception as exc:
        raise ValueError("Consumer state cannot be independently copied; provide a __deepcopy__ hook") from exc
    output = DatasetGraph(identity_namespace=graph.identity_namespace, source_scope=graph.source_scope)
    roots = [oid for oid in included if not (graph._parents.get(oid, set()) & included.keys())]
    for oid in roots:
        output.register(copies[oid])
    for oid, obj in copies.items():
        if obj.graph is None:
            output.register(obj)
        source = included[oid]
        for relation in ("parent", "association", "linked", "registry"):
            address = kind_of(source), key_of(source), relation
            for target in graph._references.get(address, ()):
                output.reference(address[0], address[1], *target, relation=relation)
        for incoming in graph._incoming.get((kind_of(source), key_of(source)), ()):
            if incoming[2] in {"linked", "registry"} and output.get(incoming[0], incoming[1]) is None:
                output.reference(incoming[0], incoming[1], kind_of(source), key_of(source), relation=incoming[2])
    # Preserve unresolved payload snapshots only for selected/context identities.
    addresses = {(kind_of(obj), key_of(obj)) for obj in included.values()}
    for address, payload in graph.unresolved_records.items():
        if isinstance(address, tuple) and any(part in addresses for part in address if isinstance(part, tuple)):
            output.unresolved_records[deepcopy(address)] = deepcopy(payload)
    return output


__all__ = ["Selection", "select", "partition"]
