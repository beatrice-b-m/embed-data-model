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
from typing import Any, ClassVar, Dict, Mapping, Optional, Protocol, Set, Tuple


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
            if name == "_linked_exams":
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

        # A standalone tree has no graph to maintain its semantic indexes.  Use
        # the same local rekey planner as ``rekey`` for identity and ownership
        # context fields, then apply ordinary attributes as before.  This keeps
        # ``image.update(image_id=...)`` and the graph-backed spelling of the
        # operation equivalent without creating a temporary graph owner.
        identifier_fields = _standalone_identifier_fields(self)
        rekey_fields = {
            name: value for name, value in fields.items() if name in identifier_fields
        }
        if rekey_fields:
            _standalone_rekey(self, rekey_fields)
        for name, value in fields.items():
            if name in rekey_fields:
                continue
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
        _standalone_rekey(self, identifiers)
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


_STANDALONE_CONTEXT_FIELDS = {
    "patient": ("patient_id",),
    # ``patient_id`` is an assigned owner for an Exam.  It is accepted here so
    # standalone ``update``/``rekey`` has the same local owner semantics as the
    # graph operation; source claims remain a separate set on the Exam.
    "exam": ("accession_number", "patient_id"),
    # An image's accession is parent context rather than toolkit identity, but
    # it is still an identifier-bearing field accepted by graph.update.
    "image": ("image_id", "accession_number"),
}

_ENTITY_ROLES = {
    "Patient": "patient",
    "Exam": "exam",
    "Finding": "finding",
    "Procedure": "procedure",
    "Pathology": "pathology",
    "CancerRegistryEntry": "registry",
    "MammogramImage": "image",
    "RegionOfInterest": "roi",
    "BreastSide": "breast_side",
    "ImagingInterpretation": "interpretation",
    "ExamAttributeObservation": "exam_attribute",
    "PatientAttributeObservation": "patient_attribute",
    "PatientHistoryObservation": "patient_history",
    "ImageLandmark": "image_landmark",
}


def _entity_role(entity: MutableEntity) -> Optional[str]:
    """Return a role for an entity without importing domain modules.

    The shared entity module is deliberately dependency-free.  Looking up a
    role through the MRO preserves the behavior for consumer subclasses while
    keeping the standalone propagation rules in this module.
    """

    for cls in type(entity).__mro__:
        role = _ENTITY_ROLES.get(cls.__name__)
        if role is not None:
            return role
    return None


def _standalone_identifier_fields(entity: MutableEntity) -> Tuple[str, ...]:
    """Return direct identity and owner fields supported without a graph."""

    role = _entity_role(entity)
    if role in _STANDALONE_CONTEXT_FIELDS:
        fields_for_role = _STANDALONE_CONTEXT_FIELDS[role]
        # Keep any domain or consumer additions to ``__key_fields__``.  The
        # tuple order is stable for the error message and for callers that
        # inspect the private contract while the set is used for membership.
        return tuple(dict.fromkeys((*fields_for_role, *entity.__key_fields__)))
    return entity.__key_fields__


def _embedded_entities(entity: MutableEntity) -> Tuple[MutableEntity, ...]:
    """Return embedded mutable values that carry parent identity context.

    These values intentionally are not graph containment edges.  They still
    need the selected standalone tree's identity context rewritten, while
    linked entities and source associations must remain untouched.
    """

    role = _entity_role(entity)
    candidates: list[Any] = []
    if role == "patient":
        candidates.extend(getattr(entity, "attribute_observations", ()))
        candidates.extend(getattr(entity, "history_observations", ()))
    elif role == "exam":
        candidates.extend(getattr(entity, "attribute_observations", ()))
        sides = getattr(entity, "breast_sides", {})
        candidates.extend(getattr(sides, "values", lambda: ())())
    elif role == "finding":
        interpretation = getattr(entity, "interpretation", None)
        if interpretation is not None:
            candidates.append(interpretation)
    elif role == "image":
        candidates.extend(getattr(entity, "landmarks", ()))
    return tuple(candidate for candidate in candidates if isinstance(candidate, MutableEntity))


def _standalone_related(entity: MutableEntity) -> Tuple[MutableEntity, ...]:
    """Traverse containment plus the explicitly supported embedded values."""

    result: list[MutableEntity] = []
    seen: Set[int] = set()
    pending = [entity]
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(current)
        pending.extend(reversed(tuple(current._children())))
        pending.extend(reversed(_embedded_entities(current)))
    return tuple(result)


def _standalone_containment(entity: MutableEntity) -> Tuple[MutableEntity, ...]:
    """Traverse only graph-registration containment edges once by identity."""

    result: list[MutableEntity] = []
    seen: Set[int] = set()
    pending = [entity]
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(current)
        pending.extend(reversed(tuple(current._children())))
    return tuple(result)


def _standalone_rekey(entity: MutableEntity, identifiers: Mapping[str, Any]) -> None:
    """Apply an identity change to a standalone tree after local preflight.

    The plan is deliberately explicit about owner context versus source
    identity.  In particular, patient rekey updates contained Exam ownership
    and patient-owned observations, but leaves image patient claims, exam
    assertion sets, registry keys, and procedure identities alone.  The
    operation only mutates objects already reachable from ``entity`` and never
    registers them in a temporary graph.
    """

    changes: Dict[int, Dict[str, Any]] = {
        id(entity): dict(identifiers),
    }
    related = _standalone_related(entity)
    owner_explicit: Set[int] = set()
    role = _entity_role(entity)

    if role == "patient" and "patient_id" in identifiers:
        old_patient_id = getattr(entity, "patient_id", _MISSING)
        new_patient_id = identifiers["patient_id"]
        if old_patient_id != new_patient_id:
            for candidate in related:
                candidate_role = _entity_role(candidate)
                if (
                    candidate_role == "exam"
                    and candidate is not entity
                    and getattr(candidate, "patient_id", _MISSING) == old_patient_id
                ):
                    _add_standalone_change(candidate, "patient_id", new_patient_id, changes)
                    owner_explicit.add(id(candidate))
                elif candidate_role in {"patient_attribute", "patient_history"}:
                    if getattr(candidate, "patient_id", _MISSING) == old_patient_id:
                        _add_standalone_change(
                            candidate, "patient_id", new_patient_id, changes
                        )

    elif role == "exam" and "accession_number" in identifiers:
        old_accession = getattr(entity, "accession_number", _MISSING)
        new_accession = identifiers["accession_number"]
        if old_accession != new_accession:
            for candidate in related:
                candidate_role = _entity_role(candidate)
                if candidate_role in {
                    "finding",
                    "image",
                    "breast_side",
                    "interpretation",
                    "exam_attribute",
                } and getattr(candidate, "accession_number", _MISSING) == old_accession:
                    _add_standalone_change(
                        candidate, "accession_number", new_accession, changes
                    )

    elif role == "finding":
        interpretation = getattr(entity, "interpretation", None)
        if isinstance(interpretation, MutableEntity):
            if "accession_number" in identifiers:
                _add_standalone_change(
                    interpretation,
                    "accession_number",
                    identifiers["accession_number"],
                    changes,
                )
            if "finding_number" in identifiers:
                _add_standalone_change(
                    interpretation,
                    "finding_number",
                    identifiers["finding_number"],
                    changes,
                )

    elif role == "image" and "image_id" in identifiers:
        old_image_id = getattr(entity, "image_id", _MISSING)
        new_image_id = identifiers["image_id"]
        if old_image_id != new_image_id:
            for candidate in related:
                candidate_role = _entity_role(candidate)
                if candidate_role in {"roi", "image_landmark"}:
                    if getattr(candidate, "image_id", _MISSING) == old_image_id:
                        _add_standalone_change(
                            candidate, "image_id", new_image_id, changes
                        )

    # Explicit owner changes on an Exam use the same marker graph.assign_patient
    # uses.  It is not a source claim and therefore must not alter the
    # ``asserted_patient_ids`` set.
    if role == "exam" and "patient_id" in identifiers:
        owner_explicit.add(id(entity))

    containment = _standalone_containment(entity)
    for candidate in related:
        if changes.get(id(candidate)) and candidate.graph is not None:
            raise ValueError(
                "Standalone rekey cannot mutate a graph-owned descendant"
            )
    _preflight_standalone_collisions(containment, changes)

    renames = _standalone_identity_renames(containment, changes)
    detached_rewrites = _detached_reference_rewrites(containment, renames)
    semantic_rewrites = _standalone_semantic_rewrites(related, renames)

    # All collision-sensitive writes happen only after the complete plan has
    # passed preflight.  ``setattr`` preserves consumer subclass coercion and
    # leaves extension attributes and object identity intact.
    for candidate in related:
        candidate_changes = changes.get(id(candidate))
        if candidate_changes:
            for name, value in candidate_changes.items():
                setattr(candidate, name, value)
    for marker in owner_explicit:
        for candidate in related:
            if id(candidate) == marker and _entity_role(candidate) == "exam":
                object.__setattr__(candidate, "_owner_explicit", True)
                break
    for marker, values in semantic_rewrites.items():
        for candidate in related:
            if id(candidate) == marker:
                for field, value in values.items():
                    object.__setattr__(candidate, field, value)
                break
    for marker, references in detached_rewrites.items():
        for candidate in related:
            if id(candidate) == marker:
                object.__setattr__(candidate, "_detached_references", references)
                break


def _add_standalone_change(
    entity: MutableEntity,
    field: str,
    value: Any,
    changes: Dict[int, Dict[str, Any]],
) -> None:
    """Add a propagated field change while retaining a single final value."""

    changes.setdefault(id(entity), {})[field] = value


def _standalone_semantic_address(
    entity: MutableEntity,
    changes: Mapping[int, Mapping[str, Any]],
) -> Optional[Tuple[str, Any]]:
    """Return the graph address an entity would occupy after ``changes``."""

    role = _entity_role(entity)
    if role not in {
        "patient",
        "exam",
        "finding",
        "procedure",
        "pathology",
        "registry",
        "image",
        "roi",
    }:
        return None
    proposed = changes.get(id(entity), {})

    def value(name: str) -> Any:
        return proposed.get(name, getattr(entity, name))

    if role == "patient":
        return role, value("patient_id")
    if role == "exam":
        return role, value("accession_number")
    if role == "finding":
        return role, (value("accession_number"), value("finding_number"))
    if role == "image":
        return role, value("image_id")
    if role == "roi":
        return role, (value("image_id"), value("roi_key"))
    if role in {"procedure", "pathology"}:
        return role, value("identity")
    if role == "registry":
        return role, (value("patient_id"), value("registry_id"))
    return None


def _standalone_identity_renames(
    members: Tuple[MutableEntity, ...],
    changes: Mapping[int, Mapping[str, Any]],
) -> Dict[Tuple[str, Any], Tuple[str, Any]]:
    """Return semantic identity changes for members in this subtree."""

    renames: Dict[Tuple[str, Any], Tuple[str, Any]] = {}
    for member in members:
        old = _standalone_semantic_address(member, {})
        new = _standalone_semantic_address(member, changes)
        if old is None or new is None or old == new:
            continue
        renames[old] = new
    return renames


def _detached_reference_rewrites(
    members: Tuple[MutableEntity, ...],
    renames: Mapping[Tuple[str, Any], Tuple[str, Any]],
) -> Dict[int, Tuple[Tuple[str, Any, str], ...]]:
    """Rewrite carried target identities for keys changed in this subtree."""

    rewritten: Dict[int, Tuple[Tuple[str, Any, str], ...]] = {}
    if not renames:
        return rewritten
    for member in members:
        carried = getattr(member, "_detached_references", None)
        if not carried:
            continue
        values = []
        for target_kind, target_key, relation in carried:
            target = renames.get((target_kind, target_key))
            if target is None:
                values.append((target_kind, target_key, relation))
            else:
                values.append((target[0], target[1], relation))
        rewritten[id(member)] = tuple(values)
    return rewritten


def _standalone_semantic_rewrites(
    members: Tuple[MutableEntity, ...],
    renames: Mapping[Tuple[str, Any], Tuple[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Rewrite semantic collections whose endpoints changed locally."""

    rewritten: Dict[int, Dict[str, Any]] = {}
    for member in members:
        if _entity_role(member) != "exam":
            continue
        linked = getattr(member, "linked_accessions", None)
        registry = getattr(member, "registry_references", None)
        if linked is not None:
            values = set(linked)
            for (kind, old), (_, new) in renames.items():
                if kind == "exam" and old in values:
                    values.discard(old)
                    values.add(new)
            if values != set(linked):
                rewritten.setdefault(id(member), {})["_linked_accessions"] = values
        if registry is not None:
            values = set(registry)
            for (kind, old), (_, new) in renames.items():
                if kind == "registry" and old in values:
                    values.discard(old)
                    values.add(new)
            if values != set(registry):
                rewritten.setdefault(id(member), {})["_registry_references"] = values
        resolved_links = getattr(member, "_linked_exams", None)
        if resolved_links:
            resolved_values = {}
            for old, target in resolved_links.items():
                replacement = renames.get(("exam", old))
                resolved_values[
                    replacement[1] if replacement is not None else old
                ] = target
            if resolved_values != resolved_links:
                rewritten.setdefault(id(member), {})["_linked_exams"] = resolved_values
    return rewritten


def _preflight_standalone_collisions(
    members: Tuple[MutableEntity, ...],
    changes: Mapping[int, Mapping[str, Any]],
) -> None:
    """Reject duplicate graph keys before changing a standalone tree."""

    occupied: Dict[Tuple[str, Any], MutableEntity] = {}
    for member in members:
        address = _standalone_semantic_address(member, changes)
        if address is None:
            continue
        try:
            previous = occupied.get(address)
        except TypeError as exc:
            raise ValueError(
                "Semantic key must be hashable: {!r}".format(address)
            ) from exc
        if previous is not None and previous is not member:
            raise ValueError("Semantic key collision: {!r}".format(address))
        occupied[address] = member


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
