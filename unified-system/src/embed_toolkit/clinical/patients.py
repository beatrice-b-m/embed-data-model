"""Mutable patient aggregates and embedded reported observations."""

from __future__ import annotations

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

from embed_toolkit.clinical.attributes import PatientAttributeObservation
from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.histories import (
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_toolkit.core.entity import MutableEntity, serialize_entity

if TYPE_CHECKING:
    from embed_toolkit.clinical.pathology import CancerRegistryEntry, Pathology
    from embed_toolkit.clinical.procedures import Procedure


class Patient(MutableEntity):
    """A mutable patient root containing exams and reported facts."""

    __key_fields__ = ("patient_id",)

    def __init__(
        self,
        patient_id: str,
        exams: Optional[Iterable[Exam]] = None,
        attribute_observations: Optional[Iterable[PatientAttributeObservation]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        history_observations: Optional[Iterable[PatientHistoryObservation]] = None,
        sex: Optional[str] = None,
        birth_year: Optional[int] = None,
        context_date: Optional[Any] = None,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.patient_id = _required_text(patient_id, "patient_id")
        self.sex = sex
        self.birth_year = birth_year
        self.context_date = context_date
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
        return tuple(self._exams)

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
        self._metadata = dict(values)

    @property
    def attribute_observations(self) -> Tuple[PatientAttributeObservation, ...]:
        return tuple(self._attribute_observations)

    @property
    def history_observations(self) -> Tuple[PatientHistoryObservation, ...]:
        return tuple(self._history_observations)

    @property
    def findings(self) -> Tuple[Finding, ...]:
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
        return self.pathology

    @property
    def registry_pathology(self) -> Tuple["CancerRegistryEntry", ...]:
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
        return self.registry_pathology

    @property
    def medication_history(self) -> Tuple[MedicationHistoryObservation, ...]:
        return tuple(
            item
            for item in self._history_observations
            if isinstance(item, MedicationHistoryObservation)
        )

    @property
    def procedure_history(self) -> Tuple[ProcedureHistoryObservation, ...]:
        return tuple(
            item
            for item in self._history_observations
            if isinstance(item, ProcedureHistoryObservation)
        )

    def add_exam(self, exam: Exam) -> Exam:
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
        if not isinstance(observation, PatientAttributeObservation):
            raise TypeError("observation must be a PatientAttributeObservation")
        if observation.patient_id != self.patient_id:
            raise ValueError("PatientAttributeObservation patient_id must match Patient")
        self._attribute_observations.append(observation)
        return observation

    def add_history_observation(
        self,
        observation: PatientHistoryObservation,
    ) -> PatientHistoryObservation:
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
        """Replace the complete embedded history snapshot for this patient."""

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
        """Update one explicitly keyed history record in place."""

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
        """Replace one unkeyed reported-fact collection, including with empty."""

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
            "context_date": self.context_date,
            "exams": self.exams,
            "attribute_observations": self.attribute_observations,
            "history_observations": self.history_observations,
            "metadata": self._metadata,
            "source": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
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
