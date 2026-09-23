"""Mutable patient aggregates and embedded reported observations."""

from __future__ import annotations

from datetime import date
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
    Union,
)

from embed_data_model.clinical.attributes import PatientAttributeObservation
from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.findings import Finding
from embed_data_model.clinical.histories import (
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_model.core.entity import MutableEntity, serialize_entity

if TYPE_CHECKING:
    from embed_data_model.clinical.pathology import CancerRegistryEntry, Pathology
    from embed_data_model.clinical.procedures import Procedure


class Patient(MutableEntity):
    """A mutable patient root containing exams and reported facts.

    Parameters
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    exams : Optional[Iterable[Exam]], optional
        Initial exams in supplied order; entities are attached by reference, not
        copied. Default: None.
    attribute_observations : Optional[Iterable[PatientAttributeObservation]], optional
        Reported attribute values per exam context. A later observation with
        the same context replaces an earlier one. Default: None.
    metadata : Optional[Mapping[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.
    history_observations : Optional[Iterable[PatientHistoryObservation]], optional
        Patient-reported facts retained by reference; explicit IDs reconcile
        matching records. Default: None.
    sex : Optional[str], optional
        Source-reported sex when every observation agrees; None means absent or
        varying over time (see ``attribute_as_of``). No inference. Default: None.
    birth_year : Optional[int], optional
        Reported calendar birth year; None means unknown. Plausibility is
        checked by validate. Default: None.
    source : Optional[object], optional
        Optional SourceRef locating the source row; evidence, not a
        clinical event. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.

    Raises
    ------
    ValueError
        Blank patient ID, child context mismatch or conflicting child identity.
    TypeError
        An initial exam/observation has an unsupported type."""

    __key_fields__ = ("patient_id",)

    sex: Optional[str]
    """Source-reported sex when all observations agree; None if absent or varying."""
    birth_year: Optional[int]
    """Reported calendar birth year; None means unknown. Plausibility is checked by validate."""
    source: Optional[object]
    """Optional SourceRef locating the source row; evidence, not a clinical event."""

    def __init__(
        self,
        patient_id: str,
        exams: Optional[Iterable[Exam]] = None,
        attribute_observations: Optional[Iterable[PatientAttributeObservation]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        history_observations: Optional[Iterable[PatientHistoryObservation]] = None,
        sex: Optional[str] = None,
        birth_year: Optional[int] = None,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.patient_id = _required_text(patient_id, "patient_id")
        self.sex = sex
        self.birth_year = birth_year
        self.source = source
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._exams: List[Exam] = []
        self._attribute_observations: List[PatientAttributeObservation] = []
        self._history_observations: List[PatientHistoryObservation] = []
        for exam in exams or ():
            self._attach_local(exam)
        for attribute_observation in attribute_observations or ():
            self.add_attribute_observation(attribute_observation)
        for history_observation in history_observations or ():
            self.add_history_observation(history_observation)
        self._finish_initialization()

    @property
    def exams(self) -> Tuple[Exam, ...]:
        """Tuple snapshot of live exams in attachment order; edits to an exam affect this patient."""

        return tuple(self._exams)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        self._metadata = dict(values)

    @property
    def attribute_observations(self) -> Tuple[PatientAttributeObservation, ...]:
        """Reported attribute values, one per exam context, in insertion order."""

        return tuple(self._attribute_observations)

    def attribute_history(self, attribute: str) -> Tuple[PatientAttributeObservation, ...]:
        """Return the observations of one attribute, dated ones first by date.

        Undated observations follow in insertion order. Values are as reported,
        including explicit nulls.
        """

        matching = [item for item in self._attribute_observations if item.attribute == attribute]
        dated = sorted(
            (item for item in matching if item.context_date is not None),
            key=lambda item: item.context_date,  # type: ignore[arg-type,return-value]
        )
        return (*dated, *(item for item in matching if item.context_date is None))

    def attribute_as_of(self, attribute: str, as_of: date) -> Any:
        """Return the latest reported value of ``attribute`` on or before ``as_of``.

        Parameters
        ----------
        attribute : str
            Attribute name, such as ``"sex"``.
        as_of : datetime.date
            Inclusive cutoff compared with each observation's ``context_date``.

        Returns
        -------
        Any
            The value from the latest dated observation that reports a value.
            None when no dated observation qualifies or when observations on
            that latest date disagree. Undated observations and explicit nulls
            are ignored, so later information never leaks into an earlier date.

        Examples
        --------
        >>> from datetime import date
        >>> patient = Patient("P1", attribute_observations=[
        ...     PatientAttributeObservation("sex", "F", "A1", date(2020, 1, 1)),
        ...     PatientAttributeObservation("sex", "U", "A2", date(2022, 1, 1)),
        ... ])
        >>> patient.attribute_as_of("sex", date(2021, 6, 1))
        'F'
        """

        eligible = [
            item
            for item in self._attribute_observations
            if item.attribute == attribute
            and item.value is not None
            and item.context_date is not None
            and item.context_date <= as_of
        ]
        if not eligible:
            return None
        latest = max(item.context_date for item in eligible if item.context_date is not None)
        values = []
        for item in eligible:
            if item.context_date == latest and item.value not in values:
                values.append(item.value)
        return values[0] if len(values) == 1 else None

    @property
    def history_observations(self) -> Tuple[PatientHistoryObservation, ...]:
        """Tuple snapshot of live reported-history observations in stored order."""

        return tuple(self._history_observations)

    @property
    def findings(self) -> Tuple[Finding, ...]:
        """Tuple of live findings in stored traversal order; aggregate traversal
        deduplicates Python identity.
        """

        result: List[Finding] = []
        seen = set()
        for exam in self._exams:
            for finding in exam.findings:
                if id(finding) not in seen:
                    seen.add(id(finding))
                    result.append(finding)
        return tuple(result)

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        """Tuple of live performed procedures in stored traversal order, deduplicated
        by Python identity where aggregated.
        """

        result: List["Procedure"] = []
        seen = set()
        for exam in self._exams:
            for procedure in exam.procedures:
                if id(procedure) not in seen:
                    seen.add(id(procedure))
                    result.append(procedure)
        return tuple(result)

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Tuple of live pathology bundles in stored traversal order, deduplicated by
        Python identity where aggregated.
        """

        result: List["Pathology"] = []
        seen = set()
        for exam in self._exams:
            for pathology in exam.pathology:
                if id(pathology) not in seen:
                    seen.add(id(pathology))
                    result.append(pathology)
        return tuple(result)

    @property
    def pathologies(self) -> Tuple["Pathology", ...]:
        """Alias for pathology, preserving live objects and collection order."""

        return self.pathology

    @property
    def registry_pathology(self) -> Tuple["CancerRegistryEntry", ...]:
        """Live registry entries reachable through supplied exam assignments; not
        contained pathology.
        """

        result: List["CancerRegistryEntry"] = []
        seen = set()
        for exam in self._exams:
            for entry in exam.registry_pathology:
                if id(entry) not in seen:
                    seen.add(id(entry))
                    result.append(entry)
        return tuple(result)

    @property
    def registry_entries(self) -> Tuple["CancerRegistryEntry", ...]:
        """Resolved live registry entries. Association resolution order is not a
        clinical or temporal ordering.
        """

        return self.registry_pathology

    @property
    def medication_history(self) -> Tuple[MedicationHistoryObservation, ...]:
        """Medication-history subset in stored order; values are live reported facts,
        not inferred events.
        """

        return tuple(
            item
            for item in self._history_observations
            if isinstance(item, MedicationHistoryObservation)
        )

    @property
    def procedure_history(self) -> Tuple[ProcedureHistoryObservation, ...]:
        """Procedure-history subset in stored order; values are reported facts, not
        verified procedures.
        """

        return tuple(
            item
            for item in self._history_observations
            if isinstance(item, ProcedureHistoryObservation)
        )

    def add_exam(self, exam: Exam) -> Exam:
        """Attach exam and return the retained live object.

        Parameters
        ----------
        exam : Exam
            Compatible object with matching parent context. Retained by reference.

        Returns
        -------
        Exam
            Attached object. Graph-backed containment delegates membership to the
            graph; embedded observations remain local values.

        Raises
        ------
        TypeError, ValueError
            Wrong object kind, incompatible parent context, or conflicting identity.
        """

        if self.graph is not None:
            result = self.graph.attach(self, exam)
            return exam if result is None else result
        return self._attach_local(exam)

    def _attach_exam_local(self, exam: Exam) -> Exam:
        if not isinstance(exam, Exam):
            raise TypeError("Patient children must be Exam entities")
        if exam.patient_id is None:
            exam.patient_id = self.patient_id
            exam._asserted_patient_ids.add(self.patient_id)
        if exam.patient_id != self.patient_id:
            raise ValueError("Exam patient_id must match Patient patient_id")
        for existing in self._exams:
            if existing is exam:
                return existing
            if existing.accession_number == exam.accession_number:
                raise ValueError(
                    "Distinct Exam objects cannot share an accession_number in a Patient"
                )
        self._exams.append(exam)
        return exam

    def add_attribute_observation(
        self,
        observation: PatientAttributeObservation,
    ) -> PatientAttributeObservation:
        """Record an attribute observation, replacing one with the same context.

        Parameters
        ----------
        observation : PatientAttributeObservation
            Value reported for this patient in one exam context.

        Returns
        -------
        PatientAttributeObservation
            The stored observation.

        Raises
        ------
        TypeError
            ``observation`` is not a PatientAttributeObservation.
        """

        if not isinstance(observation, PatientAttributeObservation):
            raise TypeError("observation must be a PatientAttributeObservation")
        for index, existing in enumerate(self._attribute_observations):
            if existing.context == observation.context:
                self._attribute_observations[index] = observation
                return observation
        self._attribute_observations.append(observation)
        return observation

    def add_history_observation(
        self,
        observation: PatientHistoryObservation,
    ) -> PatientHistoryObservation:
        """Add a reported fact or reconcile an explicitly keyed history record.

        The observation must be PatientHistoryObservation with this patient_id, or
        TypeError/ValueError is raised. Matching (concrete type, non-null record_id)
        updates and returns the existing live object; unkeyed facts append in order.
        Repeated insertion of the identical Python object returns it unchanged.
        """

        if not isinstance(observation, PatientHistoryObservation):
            raise TypeError("observation must be a PatientHistoryObservation")
        if observation.patient_id != self.patient_id:
            raise ValueError("Patient history patient_id must match Patient")
        for existing in self._history_observations:
            if existing is observation:
                return existing
            if (
                existing.record_id is not None
                and existing.record_id == observation.record_id
                and type(existing) is type(observation)
            ):
                _update_history_entity(existing, observation)
                return existing
        self._history_observations.append(observation)
        return observation

    def set_history_snapshot(
        self,
        values: Iterable[PatientHistoryObservation],
    ) -> Tuple[PatientHistoryObservation, ...]:
        """Replace the complete patient history collection and return its live tuple.

        values is consumed once in supplied order. Matching (type, record_id) retains
        and updates the existing object; unkeyed values remain distinct. Empty input
        clears the collection. TypeError rejects non-history values; ValueError rejects
        foreign patient IDs or duplicate explicit keys. Earlier keyed updates can
        remain if a later duplicate fails; this is not a transaction.
        """

        replacement = tuple(values)
        for item in replacement:
            if not isinstance(item, PatientHistoryObservation):
                raise TypeError("history snapshot must contain history observations")
            if item.patient_id != self.patient_id:
                raise ValueError("Patient history patient_id must match Patient")
        existing_by_id = {
            (type(item), item.record_id): item
            for item in self._history_observations
            if item.record_id is not None
        }
        canonical: list[PatientHistoryObservation] = []
        seen_ids = set()
        for item in replacement:
            if item.record_id is None:
                canonical.append(item)
                continue
            key = (type(item), item.record_id)
            if key in seen_ids:
                raise ValueError(f"Duplicate history record_id: {item.record_id}")
            seen_ids.add(key)
            existing = existing_by_id.get(key)
            if existing is None or existing is item:
                canonical.append(item)
            else:
                _update_history_entity(existing, item)
                canonical.append(existing)
        self._history_observations = canonical
        return tuple(canonical)

    def update_history(
        self,
        record_id: object,
        **fields: Any,
    ) -> PatientHistoryObservation:
        """Update one explicitly keyed history record in place and return it.

        record_id is normalized with str(...).strip(). **fields are forwarded to the
        observation's update method; constructor fields and consumer attributes are
        accepted. Raises KeyError for no match, ValueError for an empty/ambiguous ID,
        and propagates setter errors. Unkeyed history snapshots cannot be addressed.
        """

        normalized = str(record_id).strip()
        if not normalized:
            raise ValueError("record_id must be a non-empty value")
        matches = [
            item
            for item in self._history_observations
            if item.record_id == normalized
        ]
        if not matches:
            raise KeyError(f"Unknown history record_id: {normalized}")
        if len(matches) > 1:
            raise ValueError(f"Duplicate history record_id: {normalized}")
        matches[0].update(**fields)
        return matches[0]

    def replace_history(
        self,
        kind: Union[Type[PatientHistoryObservation], str],
        items: Iterable[PatientHistoryObservation],
    ) -> Tuple[PatientHistoryObservation, ...]:
        """Replace one history subset and return the supplied replacement tuple.

        kind is a history subclass or case-insensitive class name. Aliases are
        medication/medication_history and procedure/procedure_history/reported_procedure.
        items is consumed once; empty input clears the subset. Unmatched observations
        remain before replacements. set_history_snapshot reconciles explicit keys, so
        returned supplied objects can differ from the retained live objects. TypeError
        rejects invalid kinds/items; ValueError rejects foreign context, kind mismatches
        or duplicate explicit keys. This operation is not transactional.
        """

        replacement = tuple(items)
        for item in replacement:
            if not isinstance(item, PatientHistoryObservation):
                raise TypeError("history replacement must contain history observations")
            if item.patient_id != self.patient_id:
                raise ValueError("Patient history patient_id must match Patient")
            if not _history_matches(item, kind):
                raise ValueError("history item kind does not match replacement kind")
        replacement_values = [
            item
            for item in self._history_observations
            if not _history_matches(item, kind)
        ]
        replacement_values.extend(replacement)
        self.set_history_snapshot(replacement_values)
        return replacement

    def _children(self) -> Tuple[MutableEntity, ...]:
        # Reported observations and attributes are embedded facts, not graph
        # registry entities.  Only exams are owning containment children.
        return tuple(self._exams)

    def _attach_local(self, child: MutableEntity) -> Exam:
        if not isinstance(child, Exam):
            raise TypeError("Patient children must be Exam entities")
        return self._attach_exam_local(child)

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        for index, existing in enumerate(self._exams):
            if existing is child:
                return self._exams.pop(index)
        return child  # idempotent graph recomposition

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "sex": self.sex,
            "birth_year": self.birth_year,
            "exams": self.exams,
            "attribute_observations": self.attribute_observations,
            "history_observations": self.history_observations,
            "metadata": self._metadata,
            "source": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _history_matches(
    item: PatientHistoryObservation,
    kind: Union[Type[PatientHistoryObservation], str],
) -> bool:
    if isinstance(kind, str):
        aliases = {
            "medication": MedicationHistoryObservation,
            "medication_history": MedicationHistoryObservation,
            "procedure": ProcedureHistoryObservation,
            "procedure_history": ProcedureHistoryObservation,
            "reported_procedure": ProcedureHistoryObservation,
        }
        selected = aliases.get(kind.lower())
        if selected is not None:
            return isinstance(item, selected)
        return type(item).__name__ == kind or type(item).__name__.lower() == kind.lower()
    if not isinstance(kind, type) or not issubclass(kind, PatientHistoryObservation):
        raise TypeError("history kind must be a PatientHistoryObservation type or name")
    return isinstance(item, kind)


def _update_history_entity(
    target: PatientHistoryObservation,
    source: PatientHistoryObservation,
) -> None:
    values = {
        name: value
        for name, value in vars(source).items()
        if not name.startswith("_")
    }
    target.update(**values)
