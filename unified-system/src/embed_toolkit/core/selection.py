"""Non-owning selection and independent owning copies with ancestor context."""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, Tuple

from embed_toolkit.core.entity import MutableEntity
from embed_toolkit.core.graph import DatasetGraph, key_of, kind_of, subtree


@dataclass(frozen=True)
class Selection:
    """A non-owning view of live objects; edits affect the source graph.

    Membership is evaluated when the view is created. Objects remain live, but
    later predicate changes do not automatically re-evaluate the selection.
    """
    graph: DatasetGraph
    level: str
    objects: Tuple[Any, ...]
    owning: bool = False

    def __iter__(self) -> Iterator[Any]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)


def select(graph: DatasetGraph, *, level: str,
           predicate: Callable[[Any], bool]) -> Selection:
    if level not in graph._registries:
        raise ValueError("Unknown selection level: " + level)
    return Selection(graph, level, tuple(obj for obj in graph._registries[level].values() if predicate(obj)))


def partition(graph: DatasetGraph, *, level: str,
              key: Callable[[Any], Any]) -> Dict[Any, DatasetGraph]:
    """Copy groups independently; list/set keys place an object in many groups.

    Scalar keys (including tuples) identify one group. Returning an empty list
    omits an object. Ancestor shells carry ``context=True`` and only selected
    branches. A consumer copy failure raises ValueError; __deepcopy__ is honored.
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
    todo = list(included)
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
    # Preserve unresolved payload snapshots only for selected/context identities.
    addresses = {(kind_of(obj), key_of(obj)) for obj in included.values()}
    for address, payload in graph.unresolved_records.items():
        if isinstance(address, tuple) and any(part in addresses for part in address if isinstance(part, tuple)):
            output.unresolved_records[deepcopy(address)] = deepcopy(payload)
    return output


__all__ = ["Selection", "select", "partition"]
