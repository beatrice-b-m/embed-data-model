"""Shared protocol for mutable clinical and imaging entities.

The graph owns membership and indexes; entities own their local state.  This
module deliberately has no imports from clinical or imaging packages so both
owners can implement the same small integration surface without a cycle.

Entity implementers provide the following hooks:

``_children()``
    Return a tuple of direct containment children.  Associations such as a
    linked exam must not be returned here.
``_attach_local(child)`` / ``_detach_local(child)``
    Mutate the private local collection using object identity for membership.

The graph may call ``_set_graph`` and ``_set_local_values`` while maintaining
membership.  Those helpers are intentionally private; callers should use
``update`` and ``rekey``.
"""

from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Dict, Iterable, Mapping, Optional, Protocol, Set, Tuple


_MISSING = object()


class EntityGraph(Protocol):
    """The graph methods used by :class:`MutableEntity`.

    The protocol is structural and intentionally does not prescribe the
    graph's registry or traversal implementation.
    """

    def attach(self, parent: "MutableEntity", child: "MutableEntity") -> Any:
        ...

    def detach(self, parent: "MutableEntity", child: "MutableEntity") -> Any:
        ...

    def update(self, entity: "MutableEntity", **fields: Any) -> Any:
        ...

    def rekey(self, entity: "MutableEntity", **identifiers: Any) -> Any:
        ...


class _SerializationState:
    """Per-call state used to make repeated objects and cycles references."""

    def __init__(self) -> None:
        self.emitted: Set[int] = set()


class MutableEntity:
    """Mixin shared by mutable clinical and imaging domain objects.

    ``graph`` is either ``None`` or the single graph owning this object.
    Standalone ``update`` and ``rekey`` apply values in place.  Once a graph
    owns an object, ``update`` and ``rekey`` delegate to that graph so its
    indexes and reverse parent records remain coherent.  Direct writes to a
    registered key field raise an :class:`AttributeError`; graph code can use
    the private local setter while it performs an indexed rekey.

    Subclasses should set ``__key_fields__`` to the field names that identify
    their graph registry entry and call ``_finish_initialization`` after
    construction.  The mixin has no opinion about scalar validation.
    """

    __key_fields__: ClassVar[Tuple[str, ...]] = ()

    def __init__(self) -> None:
        object.__setattr__(self, "_graph", None)
        object.__setattr__(self, "_entity_initialized", False)

    def __setattr__(self, name: str, value: Any) -> None:
        """Protect registered identity fields from bypassing graph indexes."""

        if (
            name in self.__key_fields__
            and getattr(self, "_entity_initialized", False)
            and getattr(self, "_graph", None) is not None
        ):
            current = getattr(self, name, _MISSING)
            if current is _MISSING or current != value:
                raise AttributeError(
                    f"registered key field {name!r} must be changed with rekey()"
                )
        object.__setattr__(self, name, value)

    @property
    def graph(self) -> Optional[EntityGraph]:
        """Return the owning graph, or ``None`` for a standalone entity."""

        return getattr(self, "_graph", None)

    def _finish_initialization(self) -> None:
        """Mark construction complete so registered key protection is active."""

        object.__setattr__(self, "_entity_initialized", True)

    def _set_graph(self, graph: Optional[EntityGraph]) -> None:
        """Set graph ownership for the graph integration layer."""

        object.__setattr__(self, "_graph", graph)

    def _set_local_values(self, values: Mapping[str, Any]) -> None:
        """Apply graph-approved values without recursively delegating.

        Graph implementations should validate collisions before calling this
        helper.  It is also useful for graph implementations that normalize a
        value before assigning it.
        """

        for name, value in values.items():
            object.__setattr__(self, name, value)

    def __deepcopy__(self, memo: Dict[int, Any]) -> "MutableEntity":
        """Copy local state while leaving graph ownership and foreign links out.

        Containment children are ordinary private values, so ``copy.deepcopy``
        copies them with the caller's memo and preserves sharing within the
        copied subtree.  Resolved linked exams and registry entries are graph
        associations rather than owned children; their semantic reference
        collections remain on the copy, while the object-valued maps are
        intentionally empty and can be resolved by the destination graph.
        Consumer attributes are copied through ``copy.deepcopy`` so their own
        ``__deepcopy__`` hooks are respected.
        """

        existing = memo.get(id(self))
        if existing is not None:
            return existing
        result = self.__class__.__new__(self.__class__)
        memo[id(self)] = result
        object.__setattr__(result, "_graph", None)
        for name, value in self.__dict__.items():
            if name == "_graph":
                continue
            if name in {"_linked_exams", "_registry_entries"}:
                object.__setattr__(result, name, {})
                continue
            object.__setattr__(result, name, copy.deepcopy(value, memo))
        if not hasattr(result, "_entity_initialized"):
            object.__setattr__(result, "_entity_initialized", True)
        return result

    def update(self, **fields: Any) -> "MutableEntity":
        """Update fields in place and preserve this Python object."""

        if self.graph is not None:
            result = self.graph.update(self, **fields)
            return self if result is None else result
        for name, value in fields.items():
            setattr(self, name, value)
        return self

    def rekey(self, **identifiers: Any) -> "MutableEntity":
        """Change identity fields in place, updating a graph when owned."""

        unknown = set(identifiers).difference(self.__key_fields__)
        if unknown:
            raise TypeError(
                "rekey() accepts only registered key fields: "
                + ", ".join(self.__key_fields__)
            )
        if self.graph is not None:
            result = self.graph.rekey(self, **identifiers)
            return self if result is None else result
        self._set_local_values(identifiers)
        return self

    def _children(self) -> Tuple["MutableEntity", ...]:
        """Return direct containment children for graph traversal."""

        return ()

    def _attach_local(self, child: "MutableEntity") -> "MutableEntity":
        """Attach a child to a private collection.

        Concrete entities override this hook.  Keeping the default explicit
        makes an accidental graph edge to a leaf fail clearly.
        """

        raise TypeError(f"{type(self).__name__} does not contain children")

    def _detach_local(self, child: "MutableEntity") -> "MutableEntity":
        """Detach a child from a private collection."""

        raise TypeError(f"{type(self).__name__} does not contain children")

    def descendants(self) -> Tuple["MutableEntity", ...]:
        """Return containment descendants once, using object identity."""

        result = []
        seen = {id(self)}
        pending = list(reversed(self._children()))
        while pending:
            child = pending.pop()
            marker = id(child)
            if marker in seen:
                continue
            seen.add(marker)
            result.append(child)
            pending.extend(reversed(child._children()))
        return tuple(result)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize through the cycle-safe entity serializer."""

        return serialize_entity(self)


def readonly_mapping(values: Optional[Mapping[Any, Any]] = None) -> Mapping[Any, Any]:
    """Return a shallow read-only mapping copy for public collection views."""

    return MappingProxyType(dict(values or {}))


def entity_reference(entity: MutableEntity) -> Dict[str, Any]:
    """Return a semantic, non-recursive reference for an entity."""

    identity = getattr(entity, "identity", _MISSING)
    if identity is _MISSING:
        identity = {
            name: getattr(entity, name)
            for name in entity.__key_fields__
            if hasattr(entity, name)
        }
    return {
        "type": type(entity).__name__,
        "identity": plain_value(identity),
    }


def serialize_entity(
    entity: MutableEntity,
    state: Optional[_SerializationState] = None,
) -> Dict[str, Any]:
    """Serialize an entity while replacing repeats and cycles with references."""

    active = state or _SerializationState()
    marker = id(entity)
    if marker in active.emitted:
        return {"$ref": entity_reference(entity)}
    active.emitted.add(marker)
    builder = getattr(entity, "_to_dict_data", None)
    if builder is None:
        data: Any = entity_reference(entity)
    else:
        data = builder(active)
    serialized = serialize_value(data, active)
    if isinstance(serialized, dict):
        return serialized
    return {"value": serialized}


def serialize_value(value: Any, state: _SerializationState) -> Any:
    """Convert nested entity/value objects to JSON-friendly structures."""

    if isinstance(value, MutableEntity):
        return serialize_entity(value, state)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            plain_value(key): serialize_value(item, state)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        items = list(value)
        if isinstance(value, (set, frozenset)):
            items.sort(key=repr)
        return [serialize_value(item, state) for item in items]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: serialize_value(getattr(value, field.name), state)
            for field in fields(value)
        }
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict) and not isinstance(value, (str, bytes)):
        try:
            return serialize_value(to_dict(), state)
        except (AttributeError, TypeError):
            pass
    return value


def plain_value(value: Any) -> Any:
    """Make an identity or scalar suitable for reference serialization."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {plain_value(key): plain_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = list(value)
        if isinstance(value, (set, frozenset)):
            items.sort(key=repr)
        return [plain_value(item) for item in items]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: plain_value(getattr(value, field.name))
            for field in fields(value)
        }
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict) and not isinstance(value, (str, bytes)):
        try:
            return plain_value(to_dict())
        except (AttributeError, TypeError):
            pass
    return value
