"""Mutable semantic registry with local membership and pending-edge indexes."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Literal, Optional, Tuple, TypeVar, overload

from embed_data_model.core.source import Issue, UnresolvedReference

if TYPE_CHECKING:
    from embed_data_model.clinical.patients import Patient
    from embed_data_model.clinical.exams import Exam
    from embed_data_model.clinical.findings import Finding
    from embed_data_model.clinical.procedures import Procedure, ProcedureIdentity
    from embed_data_model.clinical.pathology import Pathology, CancerRegistryEntry
    from embed_data_model.imaging.images import MammogramImage
    from embed_data_model.imaging.rois import RegionOfInterest
    from embed_data_model.core.entity import MutableEntity
    from embed_data_model.core.selection import Selection
    from embed_data_model.core.validation import ValidationResult

_EntityT = TypeVar("_EntityT", bound="MutableEntity")

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
    """Own mutable entities and resolve their semantic relationships.

    Parameters
    ----------
    identity_namespace : str or None, optional
        Namespace label; None or an empty string uses "default". IDs are stored
        as supplied, without a namespace prefix.
    source_scope : str or None, optional
        Default physical-source label for loads; None or empty uses "in-memory".

    Attributes
    ----------
    unresolved_records : dict
        Mutable adapter payload snapshots whose clinical identity is unresolved.
        These are not registered entities or inferred events.
    operation_counts : dict of str to int
        Diagnostic operation counters, not timing measurements.
    identity_namespace, source_scope : str
        Effective labels established at construction.

    Notes
    -----
    A registered object has one graph owner. Lookups return the same live objects,
    or None when missing. Collection properties return tuples in insertion order;
    rekeying can move entries to the end. Graphs do not read files or own pixels.
    Use mutation methods to maintain indexes; modifying consumer metadata is local.

    Examples
    --------
    >>> from embed_data_model import DatasetGraph, Patient
    >>> graph = DatasetGraph()
    >>> patient = graph.register(Patient("P1"))
    >>> graph.patient("P1") is patient
    True
    """

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

    @property
    def patients(self) -> Tuple[Patient, ...]:
        """Snapshot of live patients in registry insertion order; never a copy of entities."""
        return self._values("patient")

    @property
    def exams(self) -> Tuple[Exam, ...]:
        """Snapshot of live exams in registry insertion order; never a copy of entities."""
        return self._values("exam")

    @property
    def findings(self) -> Tuple[Finding, ...]:
        """Snapshot of live findings in registry insertion order; never a copy of entities."""
        return self._values("finding")

    @property
    def procedures(self) -> Tuple[Procedure, ...]:
        """Snapshot of live procedures in registry insertion order; never a copy of entities."""
        return self._values("procedure")

    @property
    def pathology(self) -> Tuple[Pathology, ...]:
        """Snapshot of live pathology in registry insertion order; never a copy of entities."""
        return self._values("pathology")

    @property
    def registry_entries(self) -> Tuple[CancerRegistryEntry, ...]:
        """Snapshot of live registry_entries in registry insertion order; never a copy of entities."""
        return self._values("registry")

    @property
    def images(self) -> Tuple[MammogramImage, ...]:
        """Snapshot of live images in registry insertion order; never a copy of entities."""
        return self._values("image")

    @property
    def rois(self) -> Tuple[RegionOfInterest, ...]:
        """Snapshot of live rois in registry insertion order; never a copy of entities."""
        return self._values("roi")

    @property
    def issues(self) -> Tuple[Issue, ...]:
        """Graph-local diagnostics; load_embed reports invocation issues separately."""
        return tuple(self._issues)

    @overload
    def get(self, kind: Literal["patient"], key: Any) -> Optional[Patient]: ...

    @overload
    def get(self, kind: Literal["exam"], key: Any) -> Optional[Exam]: ...

    @overload
    def get(self, kind: Literal["finding"], key: Any) -> Optional[Finding]: ...

    @overload
    def get(self, kind: Literal["procedure"], key: Any) -> Optional[Procedure]: ...

    @overload
    def get(self, kind: Literal["pathology"], key: Any) -> Optional[Pathology]: ...

    @overload
    def get(self, kind: Literal["registry"], key: Any) -> Optional[CancerRegistryEntry]: ...

    @overload
    def get(self, kind: Literal["image"], key: Any) -> Optional[MammogramImage]: ...

    @overload
    def get(self, kind: Literal["roi"], key: Any) -> Optional[RegionOfInterest]: ...

    @overload
    def get(self, kind: str, key: Any) -> Any: ...

    def get(self, kind: str, key: Any) -> Any:
        """Look up a live entity by registry kind and semantic key.

        Parameters
        ----------
        kind : {"patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi"}
            Registry to query; use the named lookup methods for typed key arguments.
        key : hashable
            Exact semantic identity; no normalization is performed here.

        Returns
        -------
        MutableEntity or None
            Existing live entity, or None if the key is absent.

        Raises
        ------
        KeyError
            Unknown registry kind.
        TypeError
            The key is not hashable.
        """

        return self._registries[kind].get(key)

    def patient(self, patient_id: str) -> Optional[Patient]:
        """Look up a live object by patient_id.

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("patient", patient_id)

    def exam(self, accession: str) -> Optional[Exam]:
        """Look up a live object by accession.

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("exam", accession)

    def finding(self, accession: str, finding_number: str) -> Optional[Finding]:
        """Look up a live object by (accession, str(finding_number)).

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("finding", (accession, str(finding_number)))

    def procedure(self, identity: ProcedureIdentity) -> Optional[Procedure]:
        """Look up a live object by complete ProcedureIdentity.

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("procedure", identity)

    def image(self, image_id: str) -> Optional[MammogramImage]:
        """Look up a live object by model image_id.

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("image", image_id)

    def roi(self, image_id: str, roi_key: str) -> Optional[RegionOfInterest]:
        """Look up a live object by (image_id, str(roi_key)).

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("roi", (image_id, str(roi_key)))

    def registry_entry(self, patient_id: str, registry_id: str) -> Optional[CancerRegistryEntry]:
        """Look up a live object by (patient_id, str(registry_id)).

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self.get("registry", (patient_id, str(registry_id)))

    def source_image(self, sop_uid: str) -> Optional[MammogramImage]:
        """Look up a live object by original source SOP UID.

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self._source_images.get(sop_uid)

    def image_at_path(self, path: str) -> Optional[MammogramImage]:
        """Look up a live object by source path alias.

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self._path_images.get(path)

    def roi_at_source(self, path: str, position: int) -> Optional[RegionOfInterest]:
        """Look up a live object by (source path, zero-based collection position).

        Returns
        -------
        object or None
            The typed entity from this graph, or None when no matching key exists.
            No object is created and no file is opened.
        """

        return self._source_rois.get((path, position))

    def _check(self, values: Iterable[Any]) -> None:
        proposed: Dict[Tuple[str, Any], Any] = {}
        source_proposals = []
        for obj in values:
            address = kind_of(obj), key_of(obj)
            existing = self.get(*address)
            if existing is not None and existing is not obj:
                raise ValueError("Semantic key collision: {!r}".format(address))
            if address in proposed and proposed[address] is not obj:
                raise ValueError("Subtree semantic key collision: {!r}".format(address))
            proposed[address] = obj
            source_proposals.append((obj, obj))
        self._check_source_collisions(source_proposals)

    @staticmethod
    def _is_original_image(obj: Any) -> bool:
        return kind_of(obj) == "image" and getattr(obj, "derived_from", None) is None

    def _check_source_collisions(self, proposals: Iterable[Tuple[Any, Any]]) -> None:
        """Reject duplicate source SOP ownership before changing source indexes."""

        proposed: Dict[str, Any] = {}
        for obj, candidate in proposals:
            if not self._is_original_image(candidate):
                continue
            uid = getattr(candidate, "source_sop_instance_uid", None)
            if not uid:
                continue
            existing = self._source_images.get(uid)
            if existing is not None and existing is not obj:
                raise ValueError("Source SOP collision: " + str(uid))
            previous = proposed.get(uid)
            if previous is not None and previous is not obj:
                raise ValueError("Source SOP collision: " + str(uid))
            proposed[uid] = obj

    @staticmethod
    def _candidate_with_fields(obj: Any, fields: Dict[str, Any]) -> Any:
        candidate = object.__new__(type(obj))
        candidate.__dict__.update(obj.__dict__)
        for field, value in fields.items():
            object.__setattr__(candidate, field, value)
        return candidate

    @staticmethod
    def _embedded_context_changes(
        entity: Any,
        fields: Dict[str, Any],
    ) -> Tuple[Tuple[Any, Dict[str, Any]], ...]:
        """Plan identity-context updates for values outside graph containment.

        Patient and exam observations are embedded source facts rather than
        graph-owned registry members.  Their parent identity still needs to
        follow a registered patient or exam rekey, while their source claims
        remain independent objects and fields.
        """

        kind = kind_of(entity)
        updates = []
        if kind == "patient" and "patient_id" in fields:
            old_patient_id = getattr(entity, "patient_id", None)
            new_patient_id = fields["patient_id"]
            for observation in getattr(entity, "history_observations", ()):
                if getattr(observation, "patient_id", None) == old_patient_id:
                    updates.append((observation, {"patient_id": new_patient_id}))
        elif kind == "exam" and "accession_number" in fields:
            old_accession = getattr(entity, "accession_number", None)
            new_accession = fields["accession_number"]
            for observation in getattr(entity, "attribute_observations", ()):
                if getattr(observation, "accession_number", None) == old_accession:
                    updates.append(
                        (observation, {"accession_number": new_accession})
                    )
        return tuple(updates)

    @staticmethod
    def _detached_member_renames(
        members: Iterable[Any],
    ) -> Dict[Tuple[str, Any], Tuple[str, Any]]:
        """Collect identity changes carried by members of one detached tree."""

        current_addresses = {
            (kind_of(obj), key_of(obj)): obj for obj in members
        }
        renames: Dict[Tuple[str, Any], Tuple[str, Any]] = {}
        for obj in current_addresses.values():
            previous = getattr(obj, "_detached_address", None)
            current = kind_of(obj), key_of(obj)
            if previous is None or previous == current:
                continue
            if not isinstance(previous, tuple) or len(previous) != 2:
                continue
            existing = renames.get(previous)
            if existing is not None and existing != current:
                raise ValueError("Detached semantic key collision: {!r}".format(previous))
            other = current_addresses.get(previous)
            if other is not None and other is not obj:
                raise ValueError("Detached semantic key collision: {!r}".format(previous))
            renames[previous] = current
        return renames

    @staticmethod
    def _renamed_address(
        address: Tuple[str, Any],
        renames: Dict[Tuple[str, Any], Tuple[str, Any]],
    ) -> Tuple[str, Any]:
        return renames.get(address, address)

    @classmethod
    def _canonicalize_detached_members(
        cls,
        members: Iterable[Any],
        renames: Dict[Tuple[str, Any], Tuple[str, Any]],
    ) -> Dict[int, Dict[str, Any]]:
        """Plan bounded semantic rewrites before detached members are registered."""

        plan: Dict[int, Dict[str, Any]] = {}
        for obj in members:
            updates: Dict[str, Any] = {}
            if kind_of(obj) == "exam":
                linked = set(getattr(obj, "linked_accessions", ()))
                canonical_linked = {
                    cls._renamed_address(("exam", accession), renames)[1]
                    for accession in linked
                }
                if canonical_linked != linked:
                    updates["_linked_accessions"] = canonical_linked

                registry = set(getattr(obj, "registry_references", ()))
                canonical_registry = {
                    cls._renamed_address(("registry", reference), renames)[1]
                    for reference in registry
                }
                if canonical_registry != registry:
                    updates["_registry_references"] = canonical_registry

                linked_exams = getattr(obj, "_linked_exams", None)
                if linked_exams:
                    canonical_links: Dict[Any, Any] = {}
                    for accession, target in linked_exams.items():
                        canonical = cls._renamed_address(("exam", accession), renames)[1]
                        existing = canonical_links.get(canonical)
                        if existing is not None and existing is not target:
                            raise ValueError(
                                "Detached semantic key collision: {!r}".format(canonical)
                            )
                        canonical_links[canonical] = target
                    if canonical_links != linked_exams:
                        updates["_linked_exams"] = canonical_links

                registry_entries = getattr(obj, "_registry_entries", None)
                if registry_entries:
                    canonical_entries: Dict[Any, Any] = {}
                    for reference, entry in registry_entries.items():
                        canonical = cls._renamed_address(("registry", reference), renames)[1]
                        existing = canonical_entries.get(canonical)
                        if existing is not None and existing is not entry:
                            raise ValueError(
                                "Detached semantic key collision: {!r}".format(canonical)
                            )
                        canonical_entries[canonical] = entry
                    if canonical_entries != registry_entries:
                        updates["_registry_entries"] = canonical_entries

            detached = getattr(obj, "_detached_references", None)
            if detached:
                canonical_detached = []
                for target_kind, target_key, relation in detached:
                    target = cls._renamed_address((target_kind, target_key), renames)
                    canonical_detached.append((target[0], target[1], relation))
                canonical_detached_tuple = tuple(canonical_detached)
                if canonical_detached_tuple != tuple(detached):
                    updates["_detached_references"] = canonical_detached_tuple

            incoming = getattr(obj, "_detached_incoming_references", None)
            if incoming:
                canonical_incoming = []
                for source_kind, source_key, target_kind, target_key, relation in incoming:
                    target = cls._renamed_address((target_kind, target_key), renames)
                    canonical_incoming.append(
                        (source_kind, source_key, target[0], target[1], relation)
                    )
                canonical_incoming_tuple = tuple(canonical_incoming)
                if canonical_incoming_tuple != tuple(incoming):
                    updates["_detached_incoming_references"] = canonical_incoming_tuple

            if updates:
                plan[id(obj)] = updates
        return plan

    @staticmethod
    def _apply_detached_member_plan(
        plan: Dict[int, Dict[str, Any]],
        members: Iterable[Any],
    ) -> None:
        for obj in members:
            for field, value in plan.get(id(obj), {}).items():
                object.__setattr__(obj, field, value)

    @overload
    def register(self, entity: _EntityT, *, boundary: Literal["copy_shared"] = "copy_shared") -> _EntityT: ...

    @overload
    def register(self, entity: Any, *, boundary: Literal["copy_shared"] = "copy_shared") -> Any: ...

    def register(self, entity: Any, *, boundary: str = "copy_shared") -> Any:
        """Register an entity and its containment subtree, moving from another owner.

        Parameters
        ----------
        entity : MutableEntity
            Supported root, clinical entity, image or ROI. Subclasses are preserved.
        boundary : {"copy_shared"}, optional
            Only supported policy, default "copy_shared". Exclusive objects move by
            identity; descendants still needed by outside parents stay there and
            are deep-copied into the moved subtree. Copy hooks are honored.

        Returns
        -------
        MutableEntity
            The input root, retaining its concrete subclass. Crossing associations
            retain semantic references that can resolve in a destination graph.

        Raises
        ------
        ValueError
            Unsupported boundary, semantic/source-UID collision on registration,
            wrong ownership on pop, or inability to independently copy shared state.
        TypeError
            The entity kind is unsupported.

        Notes
        -----
        Linked exams are associations, never containment descendants.
        """

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
        member_values = tuple(members.values())
        renames = self._detached_member_renames(member_values)
        detached_plan = self._canonicalize_detached_members(member_values, renames)
        self._apply_detached_member_plan(detached_plan, member_values)
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
            detached_address = getattr(obj, "_detached_address", None)
            current_address = kind_of(obj), key_of(obj)
            for source_kind, source_key, target_kind, target_key, relation in getattr(
                obj, "_detached_incoming_references", ()
            ):
                target = target_kind, target_key
                if detached_address is not None and target == detached_address:
                    target = current_address
                self.reference(source_kind, source_key, *target, relation=relation)
            obj.__dict__.pop("_detached_references", None)
            obj.__dict__.pop("_detached_incoming_references", None)
            obj.__dict__.pop("_detached_address", None)
        return entity

    @staticmethod
    def _boundary(boundary: str) -> None:
        if boundary != "copy_shared":
            raise ValueError("Only boundary='copy_shared' is supported")

    def _index_source(self, obj: Any) -> None:
        kind = kind_of(obj)
        if kind == "image":
            uid = getattr(obj, "source_sop_instance_uid", None)
            if uid and self._is_original_image(obj):
                self._source_images[uid] = obj
                for path in getattr(obj, "source_paths", ()):
                    self._path_images[path] = obj
                    for roi in obj.rois:
                        position = getattr(roi, "collection_position", None)
                        if position is not None:
                            self._source_rois[path, position] = roi
        elif kind == "roi":
            image = self.image(obj.image_id)
            if image is not None and image.derived_from is not None:
                return
            paths = {getattr(obj, "source_path", None)}
            if image is not None:
                paths.update(image.source_paths)
            position = getattr(obj, "collection_position", None)
            for path in paths:
                if path is not None and position is not None:
                    self._source_rois[path, position] = obj

    def _resolve_member(self, obj: Any) -> None:
        kind, key = kind_of(obj), key_of(obj)
        self.operation_counts["resolved"] += 1
        if kind == "exam":
            claims = set(getattr(obj, "asserted_patient_ids", ()))
            owner_explicit = getattr(obj, "_owner_explicit", False)
            if obj.patient_id and not owner_explicit:
                claims.add(obj.patient_id)
            if owner_explicit:
                self._set_patient(obj, obj.patient_id)
            elif claims:
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
        """Record a directed semantic relationship, resolving now or when endpoints
        register. source_kind and target_kind name registries; keys are exact
        hashable identities. relation defaults to association; parent reverses
        containment, linked makes symmetric exam links, and registry assigns
        registry entries. Unsupported endpoints/relationships can raise KeyError or
        TypeError.
        """

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
        """Snapshot of missing-endpoint relationships; ordering is not guaranteed."""

        result = []
        for source, targets in self._references.items():
            for target in targets:
                if self.get(source[0], source[1]) is None or self.get(*target) is None:
                    result.append(UnresolvedReference(source[0], str(source[1]), target[0], str(target[1]), "missing endpoint"))
        return tuple(result)

    def claim_patient(self, exam: Exam, patient_ids: Iterable[str]) -> None:
        """Union source patient IDs into exam claims. A unique claim assigns the owner;
        conflicting claims clear it unless ownership was explicitly selected.
        Mutates the exam and relationship indexes.
        """

        claims = set(getattr(exam, "asserted_patient_ids", ())) | set(patient_ids)
        self.set_patient_claims(exam, claims)

    def set_patient_claims(self, exam: Exam, patient_ids: Iterable[str]) -> None:
        """Replace an exam's source patient claims and reconcile its owner.

        Parameters
        ----------
        exam : Exam
            Exam whose ``asserted_patient_ids`` are replaced.
        patient_ids : iterable of str
            The complete current set of source claims; consumed once.

        Notes
        -----
        A single claim assigns the owner and several conflicting claims leave it
        unset, unless ownership was chosen with ``assign_patient``, which
        persists. Refresh uses this so a corrected source patient ID replaces
        the earlier claim instead of accumulating beside it.
        """

        claims = set(patient_ids)
        object.__setattr__(exam, "asserted_patient_ids", claims)
        if getattr(exam, "_owner_explicit", False):
            return
        selected = next(iter(claims)) if len(claims) == 1 else None
        self._set_patient(exam, selected)

    def assign_patient(self, exam: Exam, patient_id: Optional[str]) -> None:
        """Explicitly assign a registered exam to patient_id, or None to clear
        ownership. The patient need not exist yet. Source claims survive and this
        choice persists across reload. Raises ValueError for a foreign exam.
        """

        if exam.graph is not self:
            raise ValueError("Entity does not belong to this graph")
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

    @overload
    def attach(self, parent: MutableEntity, child: _EntityT) -> _EntityT: ...

    @overload
    def attach(self, parent: Any, child: Any) -> Any: ...

    def attach(self, parent: Any, child: Any) -> Any:
        """Attach a child, registering/moving endpoints into this graph as needed.

        Parameters
        ----------
        parent, child : MutableEntity
            Compatible endpoints: patient/exam, exam/finding or image or procedure
            or pathology or registry, finding/procedure or pathology,
            procedure/pathology, or image/ROI.

        Returns
        -------
        MutableEntity
            The live child, retaining its type.

        Raises
        ------
        ValueError
            Conflicting semantic identity or incompatible ownership/context.
        TypeError
            Unsupported entity or relationship kind.
        """

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

    @overload
    def detach(self, parent: MutableEntity, child: _EntityT) -> _EntityT: ...

    @overload
    def detach(self, parent: Any, child: Any) -> Any: ...

    def detach(self, parent: Any, child: Any) -> Any:
        """Remove a containment/association edge while keeping the child registered.

        Parameters
        ----------
        parent, child : MutableEntity
            Compatible endpoints: patient/exam, exam/finding or image or procedure
            or pathology or registry, finding/procedure or pathology,
            procedure/pathology, or image/ROI.

        Returns
        -------
        MutableEntity
            The live child, retaining its type.

        Raises
        ------
        ValueError
            Conflicting semantic identity or incompatible ownership/context.
        TypeError
            Unsupported entity or relationship kind.
        """

        if parent.graph is not self or child.graph is not self:
            raise ValueError("Both endpoints must belong to this graph")
        self._detach(parent, child)
        self.remove_reference(kind_of(child), key_of(child), kind_of(parent), key_of(parent), relation="parent")
        self.remove_reference(kind_of(parent), key_of(parent), kind_of(child), key_of(child), relation="association")
        return child

    def remove_reference(self, source_kind: str, source_key: Any,
                         target_kind: str, target_key: Any, *, relation: str) -> None:
        """Remove one directed semantic reference and its pending indexes. Does not
        detach an already resolved object edge; use detach to update containment
        too.
        """

        source = source_kind, source_key, relation
        target = target_kind, target_key
        self._references[source].discard(target)
        self._incoming[target].discard(source)
        self._pending[target].discard(source)

    def _detach(self, parent: Any, child: Any) -> None:
        parent._detach_local(child)
        self._parents[id(child)].discard(id(parent))

    def clear_references(self, kind: str, key: Any, relation: str) -> None:
        """Clear stored references for (kind, key, relation), without deleting
        endpoints. This does not itself remove already resolved local edges.
        """

        source = kind, key, relation
        targets = self._references.pop(source, set())
        self._pending[(kind, key)].discard(source)
        for target in targets:
            self._pending[target].discard(source)
            self._incoming[target].discard(source)

    def set_linked_accessions(self, exam: Exam, accessions: Iterable[str], *, merge: bool = False) -> None:
        """Replace an exam's supplied linked accession set, or union when merge=True
        (default False). Empty input clears outgoing claims; incoming claims can
        keep symmetric links resolved. Missing endpoints remain pending. Targets are
        never deleted; set order is unspecified.
        """

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

    def set_registry_assignments(self, exam: Exam, keys: Iterable[Tuple[str, str]], *, merge: bool = False) -> None:
        """Replace an exam's registry references with (patient_id, registry_id) keys,
        or union when merge=True (default False). Empty input clears assignments.
        Missing endpoints remain pending; registry entities are never deleted.
        """

        values = set(keys)
        if merge:
            values.update(exam.registry_references)
        self.clear_references("exam", key_of(exam), "registry")
        for entry in tuple(exam._registry_entries.values()):
            self._detach(exam, entry)
        object.__setattr__(exam, "registry_references", values)
        for key in values:
            self.reference("exam", key_of(exam), "registry", key, relation="registry")

    @overload
    def update(self, entity: _EntityT, **fields: Any) -> _EntityT: ...

    @overload
    def update(self, entity: Any, **fields: Any) -> Any: ...

    def update(self, entity: Any, **fields: Any) -> Any:
        """Change fields in place while maintaining graph indexes and references.

        Parameters
        ----------
        entity : MutableEntity
            Entity already owned by this graph.
        **fields : Any
            Field names and replacement values. Constructor parameters describe
            ordinary fields; consumer-defined attributes remain supported. Identity
            changes propagate to dependent containment identities and references.
            Source UID/path changes remove old aliases. No implicit validation runs.

        Returns
        -------
        MutableEntity
            The same Python object, retaining its concrete type.

        Raises
        ------
        ValueError
            Wrong graph owner, semantic collision, or original-image source UID collision.
        AttributeError, TypeError
            An attribute is read-only or a replacement cannot be represented.

        Notes
        -----
        This is not a transaction for arbitrary fields. Earlier assignments can remain
        if a later setter fails. Prefer assign_patient for explicit exam ownership.
        """

        if entity.graph is not self:
            raise ValueError("Entity does not belong to this graph")
        protected = {"patient": {"patient_id"}, "exam": {"accession_number", "patient_id"},
                     "finding": {"accession_number", "finding_number"}, "procedure": {"identity"},
                     "pathology": {"identity"}, "registry": {"patient_id", "registry_id"},
                     "image": {"image_id", "accession_number"}, "roi": {"image_id", "roi_key"}}
        if set(fields) & protected[kind_of(entity)]:
            return self.rekey(entity, **fields)
        if kind_of(entity) == "image":
            candidate = self._candidate_with_fields(entity, fields)
            self._check_source_collisions(((entity, candidate),))
        self._unindex_source(entity)
        try:
            for field, value in fields.items():
                setattr(entity, field, value)
        finally:
            self._index_source(entity)
        if "laterality" in fields:
            for pid in tuple(self._parents[id(entity)]):
                parent = self._objects[pid]
                parent._detach_local(entity)
                parent._attach_local(entity)
        self.operation_counts["updated"] += 1
        return entity

    @overload
    def rekey(self, entity: _EntityT, **fields: Any) -> _EntityT: ...

    @overload
    def rekey(self, entity: Any, **fields: Any) -> Any: ...

    def rekey(self, entity: Any, **fields: Any) -> Any:
        """Change fields in place while maintaining graph indexes and references.

        Parameters
        ----------
        entity : MutableEntity
            Entity already owned by this graph.
        **fields : Any
            Field names and replacement values. Constructor parameters describe
            ordinary fields; consumer-defined attributes remain supported. Identity
            changes propagate to dependent containment identities and references.
            Source UID/path changes remove old aliases. No implicit validation runs.

        Returns
        -------
        MutableEntity
            The same Python object, retaining its concrete type.

        Raises
        ------
        ValueError
            Wrong graph owner, semantic collision, or original-image source UID collision.
        AttributeError, TypeError
            An attribute is read-only or a replacement cannot be represented.

        Notes
        -----
        This is not a transaction for arbitrary fields. Earlier assignments can remain
        if a later setter fails. Prefer assign_patient for explicit exam ownership.
        """

        if entity.graph is not self:
            raise ValueError("Entity does not belong to this graph")
        owner_supplied = kind_of(entity) == "exam" and "patient_id" in fields
        requested_owner = fields.pop("patient_id") if owner_supplied else None
        if not fields and owner_supplied:
            self.assign_patient(entity, requested_owner)
            return entity
        affected = subtree(entity)
        proposals: Dict[int, Dict[str, Any]] = {id(entity): fields}
        kind = kind_of(entity)
        if kind in {"patient", "exam", "image"}:
            name = {"patient": "patient_id", "exam": "accession_number", "image": "image_id"}[kind]
            if name in fields:
                for obj in affected.values():
                    if kind == "patient" and kind_of(obj) != "exam":
                        continue
                    if obj is not entity and getattr(obj, name, None) == getattr(entity, name):
                        proposals.setdefault(id(obj), {})[name] = fields[name]
        embedded_context = self._embedded_context_changes(entity, fields)
        staged = []
        source_proposals = []
        for oid, changes in proposals.items():
            obj = affected[oid]
            clone = self._candidate_with_fields(obj, changes)
            new = key_of(clone)
            previous = key_of(obj)
            collision = self.get(kind_of(obj), new)
            if collision is not None and collision is not obj:
                raise ValueError("Semantic key collision: {!r}".format(new))
            staged.append((obj, previous, new, changes))
            source_proposals.append((obj, clone))
        self._check_source_collisions(source_proposals)
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
            self._unindex_source(obj)
        for obj, previous, new, changes in staged:
            registry = self._registries[kind_of(obj)]
            registry.pop(previous)
            for field, value in changes.items():
                object.__setattr__(obj, field, value)
            if kind == "patient" and kind_of(obj) == "exam" and "patient_id" in changes:
                object.__setattr__(obj, "_owner_explicit", True)
            registry[new] = obj
            if kind_of(obj) == "exam" and "accession_number" in changes:
                for side in obj.breast_sides.values():
                    object.__setattr__(side, "accession_number", obj.accession_number)
            if kind_of(obj) == "finding" and obj.interpretation is not None:
                object.__setattr__(obj.interpretation, "accession_number", obj.accession_number)
                object.__setattr__(obj.interpretation, "finding_number", obj.finding_number)
        for obj, changes in embedded_context:
            for field, value in changes.items():
                object.__setattr__(obj, field, value)
        for obj, previous, new, changes in staged:
            self._rewrite_references(kind_of(obj), previous, new)
            for pid in tuple(self._parents[id(obj)]):
                parent = self._objects[pid]
                parent._detach_local(obj)
                parent._attach_local(obj)
            self._index_source(obj)
        if moved_parent and parent_field is not None and getattr(entity, parent_field) is not None:
            self.reference(kind, key_of(entity), parent_kind, getattr(entity, parent_field), relation="parent")
        if kind == "exam" and owner_supplied:
            self.assign_patient(entity, requested_owner)
        self.operation_counts["rekeyed"] += len(staged)
        return entity

    def _rewrite_references(self, kind: str, old: Any, new: Any) -> None:
        if old == new:
            return
        for relation in ("parent", "association", "registry", "linked"):
            source = kind, old, relation
            targets = tuple(self._references.get(source, ()))
            if relation == "linked":
                for target in targets:
                    endpoint = self.get(*target)
                    if endpoint is None and target == (kind, old):
                        endpoint = self.get(kind, new)
                    if endpoint is not None:
                        endpoint._linked_exams.pop(old, None)
            self.clear_references(kind, old, relation)
            for target in targets:
                if relation == "linked" and target == (kind, old):
                    target = kind, new
                    source_obj = self.get(kind, new)
                    if source_obj is not None:
                        source_obj.linked_accessions.discard(old)
                        source_obj.linked_accessions.add(new)
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

    def replace_rois(self, image: MammogramImage, rois: Iterable[RegionOfInterest]) -> None:
        """Replace an image's complete ROI collection, including manual ROIs. Consumes
        rois once. Keys must be unique and image-local or ValueError is raised. Old
        ROIs are popped and new ROIs attached; old references need not survive. Save
        manual annotations before replacement.
        """

        replacement = tuple(rois)
        keys = [key_of(roi) for roi in replacement]
        if len(set(keys)) != len(keys) or any(roi.image_id != image.image_id for roi in replacement):
            raise ValueError("Replacement requires unique image-local ROI keys")
        for old in tuple(image.rois):
            self.pop(old)
        for roi in replacement:
            self.attach(image, roi)
        self._index_source(image)

    @overload
    def pop(self, entity: _EntityT, *, boundary: Literal["copy_shared"] = "copy_shared") -> _EntityT: ...

    @overload
    def pop(self, entity: Any, *, boundary: Literal["copy_shared"] = "copy_shared") -> Any: ...

    def pop(self, entity: Any, *, boundary: str = "copy_shared") -> Any:
        """Remove an entity and its subtree, returning the detached root.

        Parameters
        ----------
        entity : MutableEntity
            Supported root, clinical entity, image or ROI. Subclasses are preserved.
        boundary : {"copy_shared"}, optional
            Only supported policy, default "copy_shared". Exclusive objects move by
            identity; descendants still needed by outside parents stay there and
            are deep-copied into the moved subtree. Copy hooks are honored.

        Returns
        -------
        MutableEntity
            The input root, retaining its concrete subclass. Crossing associations
            retain semantic references that can resolve in a destination graph.

        Raises
        ------
        ValueError
            Unsupported boundary, semantic/source-UID collision on registration,
            wrong ownership on pop, or inability to independently copy shared state.
        TypeError
            The entity kind is unsupported.

        Notes
        -----
        Linked exams are associations, never containment descendants.
        """

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
        for oid in shared_descendants:
            clone = memo[oid]
            object.__setattr__(
                clone,
                "_detached_address",
                (kind_of(selected[oid]), key_of(selected[oid])),
            )
        for oid, obj in selected.items():
            if oid not in shared_descendants:
                for child in tuple(children(obj)):
                    if id(child) in shared_descendants:
                        obj._detach_local(child)
                        clone = memo[id(child)]
                        obj._attach_local(clone)
                        self._parents[id(child)].discard(oid)
        moving = {oid: obj for oid, obj in selected.items() if oid not in shared_descendants}
        moving_addresses = {
            (kind_of(obj), key_of(obj)) for obj in moving.values()
        }
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
            incoming_carried = []
            for source in tuple(self._incoming.get(address, ())):
                if source[2] not in {"association", "registry", "linked"}:
                    continue
                source_obj = self.get(source[0], source[1])
                if (source[0], source[1]) in moving_addresses:
                    continue
                incoming_carried.append(
                    (source[0], source[1], address[0], address[1], source[2])
                )
                self._pending[address].add(source)
                if source_obj is not None and source[2] == "linked":
                    source_obj._linked_exams.pop(address[1], None)
                elif source_obj is not None and source[2] == "registry":
                    source_obj._registry_entries.pop(address[1], None)
            object.__setattr__(obj, "_detached_incoming_references", incoming_carried)
            object.__setattr__(obj, "_detached_address", address)
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

    @overload
    def select(self, *, level: Literal["patient"], predicate: Callable[[Patient], bool]) -> Selection[Patient]: ...

    @overload
    def select(self, *, level: Literal["exam"], predicate: Callable[[Exam], bool]) -> Selection[Exam]: ...

    @overload
    def select(self, *, level: Literal["finding"], predicate: Callable[[Finding], bool]) -> Selection[Finding]: ...

    @overload
    def select(self, *, level: Literal["procedure"], predicate: Callable[[Procedure], bool]) -> Selection[Procedure]: ...

    @overload
    def select(self, *, level: Literal["pathology"], predicate: Callable[[Pathology], bool]) -> Selection[Pathology]: ...

    @overload
    def select(self, *, level: Literal["registry"], predicate: Callable[[CancerRegistryEntry], bool]) -> Selection[CancerRegistryEntry]: ...

    @overload
    def select(self, *, level: Literal["image"], predicate: Callable[[MammogramImage], bool]) -> Selection[MammogramImage]: ...

    @overload
    def select(self, *, level: Literal["roi"], predicate: Callable[[RegionOfInterest], bool]) -> Selection[RegionOfInterest]: ...

    def select(self, *, level: Literal["patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi"], predicate: Callable[[Any], bool]) -> Selection[Any]:
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
        """

        from embed_data_model.core.selection import select
        return select(self, level=level, predicate=predicate)

    @overload
    def partition(self, *, level: Literal["patient"], key: Callable[[Patient], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["exam"], key: Callable[[Exam], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["finding"], key: Callable[[Finding], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["procedure"], key: Callable[[Procedure], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["pathology"], key: Callable[[Pathology], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["registry"], key: Callable[[CancerRegistryEntry], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["image"], key: Callable[[MammogramImage], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: Literal["roi"], key: Callable[[RegionOfInterest], Any]) -> Dict[Any, DatasetGraph]: ...

    @overload
    def partition(self, *, level: str, key: Callable[[Any], Any]) -> Dict[Any, DatasetGraph]: ...

    def partition(self, *, level: str, key: Callable[[Any], Any]) -> Dict[Any, DatasetGraph]:
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
        """

        from embed_data_model.core.selection import partition
        return partition(self, level=level, key=key)

    def partition_by_validation(self, *, level: str,
                                validator: Optional[Callable[[Any], ValidationResult]] = None,
                                ) -> Tuple[DatasetGraph, DatasetGraph]:
        """Partition into independent (valid, invalid) graphs.

        Parameters
        ----------
        level : str
            One of patient, exam, finding, procedure, pathology, registry, image, roi.
        validator : callable or None, optional
            Maps an object to ValidationResult. None uses validate with its default
            aggregate checks and warning policy. Exceptions propagate.

        Returns
        -------
        tuple of DatasetGraph, DatasetGraph
            Valid graph first, invalid graph second. Missing groups are empty graphs
            with default namespace/scope. Copy and error rules match partition.
        """

        from embed_data_model.core.validation import validate
        parts = self.partition(level=level, key=lambda obj: (validator or validate)(obj).valid)
        return parts.get(True, DatasetGraph()), parts.get(False, DatasetGraph())

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary of registry names to serialized entity lists in
        insertion order. Each entity serializes separately; repeated entities across
        registries can appear more than once. Namespace, diagnostics and unresolved
        records are not included. This is an export, not a graph round-trip format.
        """

        return {kind: [obj.to_dict() for obj in values.values()] for kind, values in self._registries.items()}
