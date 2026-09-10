"""Mutable exam aggregates and read-only breast-side projections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple

from embed_data_model.clinical.attributes import ExamAttributeObservation
from embed_data_model.clinical.findings import Finding
from embed_data_model.core.entity import (
    MutableEntity,
    entity_reference,
    readonly_mapping,
    serialize_entity,
)
from embed_data_model.core.primitives import Laterality
from embed_data_model.imaging.images import MammogramImage

if TYPE_CHECKING:
    from embed_data_model.clinical.pathology import CancerRegistryEntry, Pathology
    from embed_data_model.clinical.procedures import Procedure


class BreastSide(MutableEntity):
    """Read-only-view helper grouping unilateral findings and images."""

    def __init__(
        self,
        accession_number: str,
        laterality: Laterality,
        findings: Optional[Iterable[Finding]] = None,
        images: Optional[Iterable[MammogramImage]] = None,
    ) -> None:
        super().__init__()
        self.accession_number = _required_text(accession_number, "accession_number")
        self.laterality = Laterality.coerce(laterality)
        if not self.laterality.is_unilateral:
            raise ValueError("BreastSide requires LEFT or RIGHT laterality")
        self._findings: List[Finding] = []
        self._images: List[MammogramImage] = []
        for finding in findings or ():
            self._attach_finding_local(finding)
        for image in images or ():
            self._attach_image_local(image)
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, Laterality]:
        return self.accession_number, self.laterality

    @property
    def findings(self) -> Tuple[Finding, ...]:
        return tuple(self._findings)

    @property
    def images(self) -> Tuple[MammogramImage, ...]:
        return tuple(self._images)

    def add_finding(self, finding: Finding) -> Finding:
        return self._attach_finding_local(finding)

    def add_image(self, image: MammogramImage) -> MammogramImage:
        return self._attach_image_local(image)

    def _attach_finding_local(self, finding: Finding) -> Finding:
        if not isinstance(finding, Finding):
            raise TypeError("BreastSide findings must be Finding entities")
        if finding.accession_number != self.accession_number:
            raise ValueError("Finding accession_number must match BreastSide")
        if self.laterality not in Laterality.coerce(finding.laterality).expand():
            raise ValueError("Finding laterality must match BreastSide laterality")
        for existing in self._findings:
            if existing.identity == finding.identity:
                if existing is finding:
                    return existing
                raise ValueError(
                    "Distinct Finding objects cannot share an identity in a BreastSide"
                )
        self._findings.append(finding)
        return finding

    def _attach_image_local(self, image: MammogramImage) -> MammogramImage:
        if image.accession_number != self.accession_number:
            raise ValueError("Image accession_number must match BreastSide")
        if image.laterality is not self.laterality:
            raise ValueError("Image laterality must match BreastSide laterality")
        for existing in self._images:
            if existing.image_id == image.image_id:
                if existing is image:
                    return existing
                raise ValueError(
                    "Distinct MammogramImage objects cannot share image_id in a BreastSide"
                )
        self._images.append(image)
        return image

    def _children(self) -> Tuple[MutableEntity, ...]:
        # Sides are projections, not additional graph containment edges.
        return ()

    def _attach_local(self, child: MutableEntity) -> MutableEntity:
        if isinstance(child, Finding):
            return self._attach_finding_local(child)
        if isinstance(child, MammogramImage):
            return self._attach_image_local(child)
        raise TypeError("BreastSide children must be Finding or MammogramImage")

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        for collection in (self._findings, self._images):
            for index, existing in enumerate(collection):
                if existing is child:
                    return collection.pop(index)
        return child

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return self.to_dict()

    def to_dict(self) -> Dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "laterality": self.laterality.value,
            "finding_references": [
                {
                    "accession_number": finding.accession_number,
                    "finding_number": finding.finding_number,
                }
                for finding in self._findings
            ],
            "image_references": [image.image_id for image in self._images],
        }


class Exam(MutableEntity):
    """A mutable clinical exam keyed by accession number."""

    __key_fields__ = ("accession_number",)

    def __init__(
        self,
        accession_number: str,
        patient_id: Optional[str] = None,
        exam_date: Optional[str] = None,
        description: Optional[str] = None,
        attribute_observations: Optional[Iterable[ExamAttributeObservation]] = None,
        findings: Optional[Iterable[Finding]] = None,
        images: Optional[Iterable[MammogramImage]] = None,
        procedures: Optional[Iterable["Procedure"]] = None,
        pathology: Optional[Iterable["Pathology"]] = None,
        registry_pathology: Optional[Iterable["CancerRegistryEntry"]] = None,
        breast_sides: Optional[Mapping[Laterality, BreastSide]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        asserted_patient_ids: Optional[Iterable[str]] = None,
        linked_accessions: Optional[Iterable[str]] = None,
        registry_references: Optional[Iterable[Tuple[str, str]]] = None,
        owner_explicit: bool = False,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.accession_number = _required_text(accession_number, "accession_number")
        self.patient_id = patient_id
        self.exam_date = exam_date
        self.description = description
        self.source = source
        self._attribute_observations: List[ExamAttributeObservation] = []
        self._findings: List[Finding] = []
        self._images: List[MammogramImage] = []
        self._procedures: List["Procedure"] = []
        self._pathology: List["Pathology"] = []
        self._breast_sides: Dict[Laterality, BreastSide] = {}
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._asserted_patient_ids = _clean_id_set(asserted_patient_ids)
        if patient_id is not None:
            self._asserted_patient_ids.add(patient_id)
        if len(self._asserted_patient_ids) == 1 and patient_id is None:
            self.patient_id = next(iter(self._asserted_patient_ids))
        if self.patient_id is not None:
            self.patient_id = _required_text(self.patient_id, "patient_id")
        self._owner_explicit = bool(owner_explicit)
        self._linked_accessions = _clean_id_set(linked_accessions)
        self._registry_references = _clean_reference_set(registry_references)
        self._linked_exams: Dict[str, Exam] = {}
        self._registry_entries: Dict[Tuple[str, str], "CancerRegistryEntry"] = {}

        for side in (breast_sides or {}).values():
            if side.accession_number != self.accession_number:
                raise ValueError("BreastSide accession_number must match Exam")
            self.ensure_side(side.laterality)
            for finding in side.findings:
                self._attach_finding_local(finding)
            for image in side.images:
                self._attach_image_local(image)
        for finding in findings or ():
            self._attach_finding_local(finding)
        for image in images or ():
            self._attach_image_local(image)
        for procedure in procedures or ():
            self._attach_procedure_local(procedure)
        for pathology_item in _items(pathology):
            self._attach_pathology_local(pathology_item)
        for entry in registry_pathology or ():
            self._attach_local(entry)
        for observation in attribute_observations or ():
            self.add_attribute_observation(observation)
        self._finish_initialization()

    @property
    def findings(self) -> Tuple[Finding, ...]:
        return tuple(self._findings)

    @property
    def images(self) -> Tuple[MammogramImage, ...]:
        return tuple(self._images)

    @property
    def breast_sides(self) -> Mapping[Laterality, BreastSide]:
        return readonly_mapping(self._breast_sides)

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
        self._metadata = dict(values)

    @property
    def attribute_observations(self) -> Tuple[ExamAttributeObservation, ...]:
        return tuple(self._attribute_observations)

    @property
    def asserted_patient_ids(self) -> set[str]:
        return self._asserted_patient_ids

    @asserted_patient_ids.setter
    def asserted_patient_ids(self, values: Iterable[str]) -> None:
        self._asserted_patient_ids = _clean_id_set(values)

    @property
    def owner_explicit(self) -> bool:
        return self._owner_explicit

    @property
    def linked_accessions(self) -> set[str]:
        return self._linked_accessions

    @linked_accessions.setter
    def linked_accessions(self, values: Iterable[str]) -> None:
        self._linked_accessions = _clean_id_set(values)

    @property
    def registry_references(self) -> set[Tuple[str, str]]:
        return self._registry_references

    @registry_references.setter
    def registry_references(self, values: Iterable[Tuple[str, str]]) -> None:
        self._registry_references = _clean_reference_set(values)

    @property
    def linked_exams(self) -> Tuple["Exam", ...]:
        return tuple(self._linked_exams.values())

    @property
    def registry_entries(self) -> Tuple["CancerRegistryEntry", ...]:
        return tuple(self._registry_entries.values())

    @property
    def registry_pathology(self) -> Tuple["CancerRegistryEntry", ...]:
        return self.registry_entries

    @property
    def finding_index(self) -> Mapping[Tuple[str, str], Finding]:
        return readonly_mapping({finding.identity: finding for finding in self._findings})

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        result: List["Procedure"] = []
        seen = set()
        for procedure in self._procedures:
            if id(procedure) not in seen:
                seen.add(id(procedure))
                result.append(procedure)
        for finding in self._findings:
            for procedure in finding.procedures:
                if id(procedure) not in seen:
                    seen.add(id(procedure))
                    result.append(procedure)
        return tuple(result)

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        result: List["Pathology"] = []
        seen = set()
        for pathology in self._pathology:
            if id(pathology) not in seen:
                seen.add(id(pathology))
                result.append(pathology)
        for procedure in self.procedures:
            for pathology in procedure.pathologies:
                if id(pathology) not in seen:
                    seen.add(id(pathology))
                    result.append(pathology)
        return tuple(result)

    @property
    def pathologies(self) -> Tuple["Pathology", ...]:
        return self.pathology

    def ensure_side(self, laterality: Laterality) -> BreastSide:
        side = Laterality.coerce(laterality)
        if not side.is_unilateral:
            raise ValueError("Exam breast sides require LEFT or RIGHT laterality")
        existing = self._breast_sides.get(side)
        if existing is not None:
            return existing
        created = BreastSide(self.accession_number, side)
        self._breast_sides[side] = created
        return created

    def add_attribute_observation(
        self,
        observation: ExamAttributeObservation,
    ) -> ExamAttributeObservation:
        if not isinstance(observation, ExamAttributeObservation):
            raise TypeError("observation must be an ExamAttributeObservation")
        if observation.accession_number != self.accession_number:
            raise ValueError("ExamAttributeObservation accession_number must match Exam")
        self._attribute_observations.append(observation)
        return observation

    def add_finding(self, finding: Finding) -> Finding:
        if self.graph is not None:
            result = self.graph.attach(self, finding)
            return finding if result is None else result
        return self._attach_finding_local(finding)

    def extend_findings(self, findings: Iterable[Finding]) -> None:
        for finding in findings:
            self.add_finding(finding)

    def _attach_finding_local(self, finding: Finding) -> Finding:
        if not isinstance(finding, Finding):
            raise TypeError("Exam children must be Finding or MammogramImage entities")
        if finding.accession_number != self.accession_number:
            raise ValueError("Finding accession_number must match Exam accession_number")
        for existing in self._findings:
            if existing.identity == finding.identity:
                if existing is finding:
                    return existing
                raise ValueError(
                    "Distinct Finding objects cannot share an identity in an Exam"
                )
        self._findings.append(finding)
        for laterality in Laterality.coerce(finding.laterality).expand():
            self.ensure_side(laterality).add_finding(finding)
        return finding

    def add_image(self, image: MammogramImage) -> MammogramImage:
        if self.graph is not None:
            result = self.graph.attach(self, image)
            return image if result is None else result
        return self._attach_image_local(image)

    def _attach_image_local(self, image: MammogramImage) -> MammogramImage:
        if image.accession_number != self.accession_number:
            raise ValueError("Image accession_number must match Exam accession_number")
        for existing in self._images:
            if existing.image_id == image.image_id:
                if existing is image:
                    return existing
                raise ValueError(
                    "Distinct MammogramImage objects cannot share image_id in an Exam"
                )
        self._images.append(image)
        if image.laterality.is_unilateral:
            self.ensure_side(image.laterality).add_image(image)
        return image

    def add_procedure(self, procedure: "Procedure") -> "Procedure":
        if self.graph is not None:
            result = self.graph.attach(self, procedure)
            return procedure if result is None else result
        return self._attach_procedure_local(procedure)

    def _attach_procedure_local(self, procedure: "Procedure") -> "Procedure":
        from embed_data_model.clinical.procedures import Procedure

        if not isinstance(procedure, Procedure):
            raise TypeError("Exam children must be Procedure entities")
        for existing in self._procedures:
            if existing.identity == procedure.identity:
                if existing is procedure:
                    return existing
                raise ValueError(
                    "Distinct Procedure objects cannot share an identity in an Exam"
                )
        self._procedures.append(procedure)
        return procedure

    def add_pathology(self, pathology: "Pathology") -> "Pathology":
        if self.graph is not None:
            result = self.graph.attach(self, pathology)
            return pathology if result is None else result
        return self._attach_pathology_local(pathology)

    def _attach_pathology_local(self, pathology: "Pathology") -> "Pathology":
        from embed_data_model.clinical.pathology import Pathology

        if not isinstance(pathology, Pathology):
            raise TypeError("Exam children must be Pathology entities")
        for existing in self._pathology:
            if existing.identity == pathology.identity:
                if existing is pathology:
                    return existing
                raise ValueError(
                    "Distinct Pathology objects cannot share an identity in an Exam"
                )
        self._pathology.append(pathology)
        return pathology

    def add_linked_accession(self, accession_number: str) -> str:
        value = _required_text(accession_number, "accession_number")
        self._linked_accessions.add(value)
        return value

    def add_registry_reference(self, patient_id: str, registry_id: str) -> Tuple[str, str]:
        reference = (_required_text(patient_id, "patient_id"), _required_text(registry_id, "registry_id"))
        self._registry_references.add(reference)
        return reference

    def set_linked_exam(self, exam: "Exam") -> "Exam":
        if not isinstance(exam, Exam):
            raise TypeError("linked exam must be an Exam")
        self.add_linked_accession(exam.accession_number)
        existing = self._linked_exams.get(exam.accession_number)
        if existing is not None and existing is not exam:
            raise ValueError("Distinct linked Exam objects cannot share an accession")
        self._linked_exams[exam.accession_number] = exam
        return exam

    def set_registry_entry(self, entry: "CancerRegistryEntry") -> "CancerRegistryEntry":
        from embed_data_model.clinical.pathology import CancerRegistryEntry

        if not isinstance(entry, CancerRegistryEntry):
            raise TypeError("registry entry must be a CancerRegistryEntry")
        self.add_registry_reference(*entry.identity)
        existing = self._registry_entries.get(entry.identity)
        if existing is not None and existing is not entry:
            raise ValueError("Distinct registry entries cannot share an identity")
        self._registry_entries[entry.identity] = entry
        return entry

    def add_registry_entry(
        self,
        entry: "CancerRegistryEntry",
    ) -> "CancerRegistryEntry":
        if self.graph is not None:
            result = self.graph.attach(self, entry)
            return entry if result is None else result
        return self.set_registry_entry(entry)

    def _children(self) -> Tuple[MutableEntity, ...]:
        children: List[MutableEntity] = []
        for candidate in (
            *self._findings,
            *self._images,
            *self._procedures,
            *self._pathology,
            *self._registry_entries.values(),
        ):
            if all(existing is not candidate for existing in children):
                children.append(candidate)
        return tuple(children)

    def _attach_local(self, child: MutableEntity) -> MutableEntity:
        if isinstance(child, Finding):
            return self._attach_finding_local(child)
        if isinstance(child, MammogramImage):
            return self._attach_image_local(child)
        from embed_data_model.clinical.pathology import CancerRegistryEntry, Pathology
        from embed_data_model.clinical.procedures import Procedure

        if isinstance(child, Procedure):
            return self._attach_procedure_local(child)
        if isinstance(child, Pathology):
            return self._attach_pathology_local(child)
        if isinstance(child, CancerRegistryEntry):
            return self.set_registry_entry(child)
        raise TypeError(
            "Exam children must be Finding, MammogramImage, Procedure, "
            "Pathology, or CancerRegistryEntry entities"
        )

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        for collection in (
            self._findings,
            self._images,
            self._procedures,
            self._pathology,
        ):
            for index, existing in enumerate(collection):
                if existing is child:
                    removed = collection.pop(index)
                    if isinstance(removed, Finding):
                        for side in self._breast_sides.values():
                            side._detach_local(removed)
                    return removed
        for identity, existing in tuple(self._registry_entries.items()):
            if existing is child:
                del self._registry_entries[identity]
                return existing
        return child

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "accession_number": self.accession_number,
            "patient_id": self.patient_id,
            "exam_date": self.exam_date,
            "description": self.description,
            "asserted_patient_ids": self.asserted_patient_ids,
            "owner_explicit": self._owner_explicit,
            "attribute_observations": self.attribute_observations,
            "findings": self.findings,
            "images": self.images,
            "breast_sides": tuple(self._breast_sides.values()),
            "linked_accessions": self.linked_accessions,
            "registry_references": self.registry_references,
            "linked_exams": [
                {"$ref": entity_reference(exam)}
                for exam in self._linked_exams.values()
            ],
            "registry_pathology": tuple(self._registry_entries.values()),
            "metadata": self._metadata,
            "source": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
        return serialize_entity(self)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _items(value: Optional[Iterable[Any]]) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, MutableEntity):
        return (value,)
    return value


def _clean_id_set(values: Optional[Iterable[str]]) -> set[str]:
    return {
        _required_text(value, "identifier")
        for value in (values or ())
    }


def _clean_reference_set(
    values: Optional[Iterable[Tuple[str, str]]],
) -> set[Tuple[str, str]]:
    return {
        (_required_text(patient_id, "patient_id"), _required_text(registry_id, "registry_id"))
        for patient_id, registry_id in (values or ())
    }
