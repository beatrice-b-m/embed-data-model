"""Mutable semantic registry with local membership and pending-edge indexes."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from embed_toolkit.core.source import Issue, UnresolvedReference

_NAMES = {"Patient": "patient", "Exam": "exam", "Finding": "finding",
          "Procedure": "procedure", "Pathology": "pathology",
          "CancerRegistryEntry": "registry", "MammogramImage": "image",
          "RegionOfInterest": "roi"}


def kind_of(entity: Any) -> str:
    for cls in type(entity).__mro__:
        if cls.__name__ in _NAMES:
            return _NAMES[cls.__name__]
    raise TypeError("Unsupported registered entity: " + type(entity).__name__)


def key_of(entity: Any) -> Any:
    kind = kind_of(entity)
    field = {"patient": "patient_id", "exam": "accession_number", "image": "image_id"}.get(kind, "identity")
    return getattr(entity, field)


def children(entity: Any) -> Tuple[Any, ...]:
    return tuple(entity._children())


def subtree(entity: Any) -> Dict[int, Any]:
    found: Dict[int, Any] = {}
    todo = [entity]
    while todo:
        current = todo.pop()
        if id(current) not in found:
            found[id(current)] = current
            todo.extend(children(current))
    return found


class DatasetGraph:
    """One owning registry. Changes visit affected objects and pending neighbors."""

    def __init__(self, identity_namespace: Optional[str] = None,
                 source_scope: Optional[str] = None) -> None:
        self.identity_namespace = identity_namespace or "default"
        self.source_scope = source_scope or "in-memory"
        self._registries: Dict[str, Dict[Any, Any]] = {kind: {} for kind in _NAMES.values()}
        self._objects: Dict[int, Any] = {}
        self._parents: Dict[int, set[int]] = defaultdict(set)
        self._pending: Dict[Tuple[str, Any], set[Tuple[str, Any, str]]] = defaultdict(set)
        self._references: Dict[Tuple[str, Any, str], set[Tuple[str, Any]]] = defaultdict(set)
        self._incoming: Dict[Tuple[str, Any], set[Tuple[str, Any, str]]] = defaultdict(set)
        self._source_images: Dict[str, Any] = {}
        self._path_images: Dict[str, Any] = {}
        self._source_rois: Dict[Tuple[str, int], Any] = {}
        self._issues: list[Issue] = []
        self.unresolved_records: Dict[Any, Any] = {}
        self.operation_counts: Dict[str, int] = defaultdict(int)

    def _values(self, kind: str) -> Tuple[Any, ...]:
        return tuple(self._registries[kind].values())

    patients = property(lambda self: self._values("patient"))
    exams = property(lambda self: self._values("exam"))
    findings = property(lambda self: self._values("finding"))
    procedures = property(lambda self: self._values("procedure"))
    pathology = property(lambda self: self._values("pathology"))
    registry_entries = property(lambda self: self._values("registry"))
    images = property(lambda self: self._values("image"))
    rois = property(lambda self: self._values("roi"))
    issues = property(lambda self: tuple(self._issues))

    def get(self, kind: str, key: Any) -> Any:
        return self._registries[kind].get(key)

    def patient(self, patient_id: str) -> Any:
        return self.get("patient", patient_id)

    def exam(self, accession: str) -> Any:
        return self.get("exam", accession)

    def finding(self, accession: str, finding_number: str) -> Any:
        return self.get("finding", (accession, str(finding_number)))

    def procedure(self, identity: Any) -> Any:
        return self.get("procedure", identity)

    def image(self, image_id: str) -> Any:
        return self.get("image", image_id)

    def roi(self, image_id: str, roi_key: str) -> Any:
        return self.get("roi", (image_id, str(roi_key)))

    def registry_entry(self, patient_id: str, registry_id: str) -> Any:
        return self.get("registry", (patient_id, str(registry_id)))

    def source_image(self, sop_uid: str) -> Any:
        return self._source_images.get(sop_uid)

    def image_at_path(self, path: str) -> Any:
        return self._path_images.get(path)

    def roi_at_source(self, path: str, position: int) -> Any:
        return self._source_rois.get((path, position))

    def _check(self, values: Iterable[Any]) -> None:
        proposed: Dict[Tuple[str, Any], Any] = {}
        for obj in values:
            address = kind_of(obj), key_of(obj)
            existing = self.get(*address)
            if existing is not None and existing is not obj:
                raise ValueError("Semantic key collision: {!r}".format(address))
            if address in proposed and proposed[address] is not obj:
                raise ValueError("Subtree semantic key collision: {!r}".format(address))
            proposed[address] = obj
            if address[0] == "image" and not getattr(obj, "derived_from", None):
                uid = getattr(obj, "source_sop_instance_uid", None)
                other = self._source_images.get(uid) if uid else None
                if other is not None and other is not obj:
                    raise ValueError("Source SOP collision: " + str(uid))

    def register(self, entity: Any, *, boundary: str = "copy_shared") -> Any:
        self._boundary(boundary)
        if getattr(entity, "graph", None) is self:
            self._index_source(entity)
            return entity
        members = subtree(entity)
        self._check(members.values())
        owner = getattr(entity, "graph", None)
        if owner is not None:
            entity = owner.pop(entity, boundary=boundary)
            members = subtree(entity)
        for obj in members.values():
            other = getattr(obj, "graph", None)
            if other is not None and other is not self:
                raise ValueError("Subtree contains a foreign owning object")
        for obj in members.values():
            kind, key = kind_of(obj), key_of(obj)
            self._registries[kind][key] = obj
            self._objects[id(obj)] = obj
            object.__setattr__(obj, "_graph", self)
            self.operation_counts["registered"] += 1
        for obj in members.values():
            for child in children(obj):
                self._parents[id(child)].add(id(obj))
            self._index_source(obj)
            self._resolve_member(obj)
            for target_kind, target_key, relation in getattr(obj, "_detached_references", ()):
                self.reference(kind_of(obj), key_of(obj), target_kind, target_key, relation=relation)
            obj.__dict__.pop("_detached_references", None)
        return entity

    @staticmethod
    def _boundary(boundary: str) -> None:
        if boundary != "copy_shared":
            raise ValueError("Only boundary='copy_shared' is supported")

    def _index_source(self, obj: Any) -> None:
        kind = kind_of(obj)
        if kind == "image":
            uid = getattr(obj, "source_sop_instance_uid", None)
            if uid and not getattr(obj, "derived_from", None):
                self._source_images[uid] = obj
                for path in getattr(obj, "source_paths", ()):
                    self._path_images[path] = obj
                    for roi in obj.rois:
                        position = getattr(roi, "collection_position", None)
                        if position is not None:
                            self._source_rois[path, position] = roi
        elif kind == "roi":
            path = getattr(obj, "source_path", None)
            position = getattr(obj, "collection_position", None)
            if path is not None and position is not None:
                self._source_rois[path, position] = obj

    def _resolve_member(self, obj: Any) -> None:
        kind, key = kind_of(obj), key_of(obj)
        self.operation_counts["resolved"] += 1
        if kind == "exam":
            claims = set(getattr(obj, "asserted_patient_ids", ()))
            if obj.patient_id:
                claims.add(obj.patient_id)
            if claims:
                self.claim_patient(obj, claims)
        elif kind in {"finding", "image"} and getattr(obj, "accession_number", None):
            self.reference(kind, key, "exam", obj.accession_number, relation="parent")
        elif kind == "roi":
            self.reference(kind, key, "image", obj.image_id, relation="parent")
        if kind == "exam":
            for accession in getattr(obj, "linked_accessions", ()):
                self.reference("exam", key, "exam", accession, relation="linked")
            for registry_key in getattr(obj, "registry_references", ()):
                self.reference("exam", key, "registry", registry_key, relation="registry")
        for source in tuple(self._pending.pop((kind, key), ())):
            for target in tuple(self._references.get(source, ())):
                self._resolve_reference(source, target)

    def reference(self, source_kind: str, source_key: Any, target_kind: str,
                  target_key: Any, *, relation: str = "association") -> None:
        source = source_kind, source_key, relation
        target = target_kind, target_key
        self._references[source].add(target)
        self._incoming[target].add(source)
        self._resolve_reference(source, target)

    def _resolve_reference(self, source: Tuple[str, Any, str], target: Tuple[str, Any]) -> None:
        obj = self.get(source[0], source[1])
        endpoint = self.get(*target)
        if obj is None:
            self._pending[(source[0], source[1])].add(source)
        if endpoint is None:
            self._pending[target].add(source)
        if obj is None or endpoint is None:
            return
        self._pending[(source[0], source[1])].discard(source)
        self._pending[target].discard(source)
        relation = source[2]
        if relation == "parent":
            self._attach(endpoint, obj)
        elif relation == "linked":
            obj._linked_exams[key_of(endpoint)] = endpoint
            endpoint._linked_exams[key_of(obj)] = obj
        elif relation == "registry":
            self._attach(obj, endpoint)
        else:
            self._attach(obj, endpoint)

    @property
    def unresolved_references(self) -> Tuple[UnresolvedReference, ...]:
        result = []
        for source, targets in self._references.items():
            for target in targets:
                if self.get(source[0], source[1]) is None or self.get(*target) is None:
                    result.append(UnresolvedReference(source[0], str(source[1]), target[0], str(target[1]), "missing endpoint"))
        return tuple(result)

    def claim_patient(self, exam: Any, patient_ids: Iterable[str]) -> None:
        claims = set(getattr(exam, "asserted_patient_ids", ())) | set(patient_ids)
        object.__setattr__(exam, "asserted_patient_ids", claims)
        if getattr(exam, "_owner_explicit", False):
            return
        selected = next(iter(claims)) if len(claims) == 1 else None
        self._set_patient(exam, selected)

    def assign_patient(self, exam: Any, patient_id: str) -> None:
        object.__setattr__(exam, "_owner_explicit", True)
        self._set_patient(exam, patient_id)

    def _set_patient(self, exam: Any, patient_id: Optional[str]) -> None:
        old = exam.patient_id
        if old != patient_id:
            parent = self.patient(old) if old else None
            if parent is not None:
                self._detach(parent, exam)
            self.clear_references("exam", key_of(exam), "parent")
        object.__setattr__(exam, "patient_id", patient_id)
        if patient_id:
            self.reference("exam", key_of(exam), "patient", patient_id, relation="parent")

    def attach(self, parent: Any, child: Any) -> Any:
        self._check((*subtree(parent).values(), *subtree(child).values()))
        parent_kind, child_kind = kind_of(parent), kind_of(child)
        allowed = {"patient": {"exam"}, "exam": {"finding", "image", "procedure", "pathology", "registry"},
                   "finding": {"procedure", "pathology"}, "procedure": {"pathology"}, "image": {"roi"}}
        if child_kind not in allowed.get(parent_kind, set()):
            raise TypeError("Unsupported containment relationship")
        if parent_kind == "exam" and child_kind in {"finding", "image"}:
            accession = getattr(child, "accession_number", None)
            if accession is not None and accession != parent.accession_number:
                raise ValueError("Child accession must match Exam")
            if accession is None:
                object.__setattr__(child, "accession_number", parent.accession_number)
        if parent_kind == "image" and child.image_id != parent.image_id:
            raise ValueError("ROI image_id must match MammogramImage")
        self.register(parent)
        self.register(child)
        self._attach(parent, child)
        return child

    def _attach(self, parent: Any, child: Any) -> None:
        parent._attach_local(child)
        self._parents[id(child)].add(id(parent))

    def detach(self, parent: Any, child: Any) -> Any:
        if parent.graph is not self or child.graph is not self:
            raise ValueError("Both endpoints must belong to this graph")
        self._detach(parent, child)
        self.remove_reference(kind_of(child), key_of(child), kind_of(parent), key_of(parent), relation="parent")
        self.remove_reference(kind_of(parent), key_of(parent), kind_of(child), key_of(child), relation="association")
        return child

    def remove_reference(self, source_kind: str, source_key: Any,
                         target_kind: str, target_key: Any, *, relation: str) -> None:
        source = source_kind, source_key, relation
        target = target_kind, target_key
        self._references[source].discard(target)
        self._incoming[target].discard(source)
        self._pending[target].discard(source)

    def _detach(self, parent: Any, child: Any) -> None:
        parent._detach_local(child)
        self._parents[id(child)].discard(id(parent))

    def clear_references(self, kind: str, key: Any, relation: str) -> None:
        source = kind, key, relation
        targets = self._references.pop(source, set())
        self._pending[(kind, key)].discard(source)
        for target in targets:
            self._pending[target].discard(source)
            self._incoming[target].discard(source)

    def set_linked_accessions(self, exam: Any, accessions: Iterable[str], *, merge: bool = False) -> None:
        values = set(accessions)
        if merge:
            values.update(exam.linked_accessions)
        self.clear_references("exam", key_of(exam), "linked")
        for other in tuple(exam._linked_exams.values()):
            other._linked_exams.pop(key_of(exam), None)
        exam._linked_exams.clear()
        object.__setattr__(exam, "linked_accessions", values)
        for accession in values:
            self.reference("exam", key_of(exam), "exam", accession, relation="linked")
        for incoming in tuple(self._incoming.get(("exam", key_of(exam)), ())):
            if incoming[2] == "linked":
                self._resolve_reference(incoming, ("exam", key_of(exam)))

    def set_registry_assignments(self, exam: Any, keys: Iterable[Tuple[str, str]], *, merge: bool = False) -> None:
        values = set(keys)
        if merge:
            values.update(exam.registry_references)
        self.clear_references("exam", key_of(exam), "registry")
        for entry in tuple(exam._registry_entries.values()):
            self._detach(exam, entry)
        object.__setattr__(exam, "registry_references", values)
        for key in values:
            self.reference("exam", key_of(exam), "registry", key, relation="registry")

    def update(self, entity: Any, **fields: Any) -> Any:
        if entity.graph is not self:
            raise ValueError("Entity does not belong to this graph")
        protected = {"patient": {"patient_id"}, "exam": {"accession_number", "patient_id"},
                     "finding": {"accession_number", "finding_number"}, "procedure": {"identity"},
                     "pathology": {"identity"}, "registry": {"patient_id", "registry_id"},
                     "image": {"image_id", "accession_number"}, "roi": {"image_id", "roi_key"}}
        if set(fields) & protected[kind_of(entity)]:
            return self.rekey(entity, **fields)
        for field, value in fields.items():
            setattr(entity, field, value)
        if "laterality" in fields:
            for pid in tuple(self._parents[id(entity)]):
                parent = self._objects[pid]
                parent._detach_local(entity)
                parent._attach_local(entity)
        self._index_source(entity)
        self.operation_counts["updated"] += 1
        return entity

    def rekey(self, entity: Any, **fields: Any) -> Any:
        if entity.graph is not self:
            raise ValueError("Entity does not belong to this graph")
        requested_owner = fields.pop("patient_id", None) if kind_of(entity) == "exam" and "patient_id" in fields else None
        if not fields and requested_owner is not None:
            self.assign_patient(entity, requested_owner)
            return entity
        affected = subtree(entity)
        proposals: Dict[int, Dict[str, Any]] = {id(entity): fields}
        kind = kind_of(entity)
        if kind in {"patient", "exam", "image"}:
            name = {"patient": "patient_id", "exam": "accession_number", "image": "image_id"}[kind]
            if name in fields:
                for obj in affected.values():
                    if obj is not entity and getattr(obj, name, None) == getattr(entity, name):
                        proposals.setdefault(id(obj), {})[name] = fields[name]
        staged = []
        for oid, changes in proposals.items():
            obj = affected[oid]
            clone = object.__new__(type(obj))
            clone.__dict__.update(obj.__dict__)
            for field, value in changes.items():
                object.__setattr__(clone, field, value)
            new = key_of(clone)
            previous = key_of(obj)
            collision = self.get(kind_of(obj), new)
            if collision is not None and collision is not obj:
                raise ValueError("Semantic key collision: {!r}".format(new))
            staged.append((obj, previous, new, changes))
        parent_field = {"finding": "accession_number", "image": "accession_number", "roi": "image_id"}.get(kind)
        parent_kind = "image" if kind == "roi" else "exam"
        moved_parent = parent_field is not None and parent_field in fields
        if moved_parent:
            for pid in tuple(self._parents[id(entity)]):
                parent = self._objects[pid]
                if kind_of(parent) == parent_kind:
                    self._detach(parent, entity)
            self.clear_references(kind, key_of(entity), "parent")
        for obj, previous, new, changes in staged:
            registry = self._registries[kind_of(obj)]
            registry.pop(previous)
            for field, value in changes.items():
                object.__setattr__(obj, field, value)
            registry[new] = obj
            if kind_of(obj) == "exam" and "accession_number" in changes:
                for side in obj.breast_sides.values():
                    object.__setattr__(side, "accession_number", obj.accession_number)
            if kind_of(obj) == "image" and "image_id" in changes:
                for landmark in obj.landmarks:
                    object.__setattr__(landmark, "image_id", obj.image_id)
        for obj, previous, new, changes in staged:
            self._rewrite_references(kind_of(obj), previous, new)
            for pid in tuple(self._parents[id(obj)]):
                parent = self._objects[pid]
                parent._detach_local(obj)
                parent._attach_local(obj)
            self._index_source(obj)
        if moved_parent and parent_field is not None and getattr(entity, parent_field) is not None:
            self.reference(kind, key_of(entity), parent_kind, getattr(entity, parent_field), relation="parent")
        if kind == "exam" and requested_owner is not None:
            self.assign_patient(entity, requested_owner)
        self.operation_counts["rekeyed"] += len(staged)
        return entity

    def _rewrite_references(self, kind: str, old: Any, new: Any) -> None:
        if old == new:
            return
        for relation in ("parent", "association", "registry", "linked"):
            source = kind, old, relation
            targets = tuple(self._references.get(source, ()))
            self.clear_references(kind, old, relation)
            for target in targets:
                self.reference(kind, new, *target, relation=relation)
        for source in tuple(self._incoming.pop((kind, old), ())):
            incoming_targets = self._references[source]
            incoming_targets.discard((kind, old))
            incoming_targets.add((kind, new))
            self._incoming[(kind, new)].add(source)
            self._pending[(kind, old)].discard(source)
            obj = self.get(source[0], source[1])
            if obj is not None and source[2] == "linked":
                obj.linked_accessions.discard(old)
                obj.linked_accessions.add(new)
                obj._linked_exams.pop(old, None)
            if obj is not None and source[2] == "registry":
                obj.registry_references.discard(old)
                obj.registry_references.add(new)
                obj._registry_entries.pop(old, None)
            self._resolve_reference(source, (kind, new))

    def replace_rois(self, image: Any, rois: Iterable[Any]) -> None:
        replacement = tuple(rois)
        keys = [key_of(roi) for roi in replacement]
        if len(set(keys)) != len(keys) or any(roi.image_id != image.image_id for roi in replacement):
            raise ValueError("Replacement requires unique image-local ROI keys")
        for old in tuple(image.rois):
            self.pop(old)
        for roi in replacement:
            self.attach(image, roi)
        self._index_source(image)

    def pop(self, entity: Any, *, boundary: str = "copy_shared") -> Any:
        self._boundary(boundary)
        if entity.graph is not self:
            raise ValueError("Entity does not belong to this graph")
        selected = subtree(entity)
        shared = {oid for oid in selected if self._parents[oid] - selected.keys() and oid != id(entity)}
        shared_descendants: Dict[int, Any] = {}
        for oid in shared:
            shared_descendants.update(subtree(selected[oid]))
        memo: Dict[int, Any] = {id(self): None}
        for oid in shared_descendants:
            try:
                deepcopy(selected[oid], memo)
            except Exception as exc:
                raise ValueError("Consumer attributes cannot be independently copied; provide __deepcopy__") from exc
        for oid, obj in selected.items():
            if oid not in shared_descendants:
                for child in tuple(children(obj)):
                    if id(child) in shared_descendants:
                        obj._detach_local(child)
                        clone = memo[id(child)]
                        obj._attach_local(clone)
                        self._parents[id(child)].discard(oid)
        moving = {oid: obj for oid, obj in selected.items() if oid not in shared_descendants}
        for oid, obj in moving.items():
            address = kind_of(obj), key_of(obj)
            carried = []
            for relation in ("parent", "association", "registry", "linked"):
                source = address[0], address[1], relation
                for target in self._references.get(source, ()):
                    carried.append((target[0], target[1], relation))
                    self._pending[address].add(source)
                    endpoint = self.get(*target)
                    if endpoint is not None and relation == "linked":
                        endpoint._linked_exams.pop(address[1], None)
            object.__setattr__(obj, "_detached_references", carried)
            for source in self._incoming.get(address, ()):
                self._pending[address].add(source)
                source_obj = self.get(source[0], source[1])
                if source_obj is not None and source[2] == "linked":
                    source_obj._linked_exams.pop(address[1], None)
                elif source_obj is not None and source[2] == "registry":
                    source_obj._registry_entries.pop(address[1], None)
            if kind_of(obj) == "exam":
                obj._linked_exams.clear()
            for pid in tuple(self._parents[oid]):
                if pid not in moving:
                    self._detach(self._objects[pid], obj)
            self._registries[kind_of(obj)].pop(key_of(obj))
            self._objects.pop(oid)
            self._parents.pop(oid, None)
            object.__setattr__(obj, "_graph", None)
            self._unindex_source(obj)
        for obj in subtree(entity).values():
            object.__setattr__(obj, "_graph", None)
        return entity

    def _unindex_source(self, obj: Any) -> None:
        if kind_of(obj) == "image":
            uid = getattr(obj, "source_sop_instance_uid", None)
            if uid is not None and self._source_images.get(uid) is obj:
                self._source_images.pop(uid, None)
            for path in getattr(obj, "source_paths", ()):
                if self._path_images.get(path) is obj:
                    self._path_images.pop(path, None)
                for roi in obj.rois:
                    position = getattr(roi, "collection_position", None)
                    if position is None:
                        continue
                    address = path, position
                    if self._source_rois.get(address) is roi:
                        self._source_rois.pop(address, None)
        if kind_of(obj) == "roi":
            paths = {getattr(obj, "source_path", None)}
            image = self.image(obj.image_id)
            if image:
                paths.update(getattr(image, "source_paths", ()))
            for path in paths:
                position = getattr(obj, "collection_position", None)
                if path is None or position is None:
                    continue
                address = path, position
                if self._source_rois.get(address) is obj:
                    self._source_rois.pop(address, None)

    def select(self, *, level: str, predicate: Callable[[Any], bool]) -> Any:
        from embed_toolkit.core.selection import select
        return select(self, level=level, predicate=predicate)

    def partition(self, *, level: str, key: Callable[[Any], Any]) -> Any:
        from embed_toolkit.core.selection import partition
        return partition(self, level=level, key=key)

    def partition_by_validation(self, *, level: str, validator: Any = None) -> Any:
        from embed_toolkit.core.validation import validate
        parts = self.partition(level=level, key=lambda obj: (validator or validate)(obj).valid)
        return parts.get(True, DatasetGraph()), parts.get(False, DatasetGraph())

    def to_dict(self) -> Dict[str, Any]:
        return {kind: [obj.to_dict() for obj in values.values()] for kind, values in self._registries.items()}
