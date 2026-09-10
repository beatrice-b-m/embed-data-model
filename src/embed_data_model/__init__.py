"""A Python object model for EMBED clinical and mammography data."""

from importlib.metadata import version

from embed_data_model.clinical.exams import BreastSide, Exam
from embed_data_model.clinical.findings import Finding
from embed_data_model.clinical.patients import Patient
from embed_data_model.clinical.procedures import Procedure, ProcedureIdentity
from embed_data_model.clinical.pathology import Pathology, CancerRegistryEntry
from embed_data_model.core.primitives import Laterality, ImageModality, ViewPosition
from embed_data_model.core.validation import ValidationResult, validate
from embed_data_model.core.graph import DatasetGraph
from embed_data_model.core.source import Issue, SourceRef
from embed_data_model.imaging.images import MammogramImage
from embed_data_model.imaging.rois import Box, RegionOfInterest
from embed_data_model.sources.embed import LoadReport, load_embed

__all__ = [
    "BreastSide",
    "Box",
    "DatasetGraph",
    "Exam",
    "Finding",
    "Issue",
    "LoadReport",
    "MammogramImage",
    "Patient",
    "Procedure",
    "ProcedureIdentity",
    "Pathology",
    "CancerRegistryEntry",
    "Laterality",
    "ImageModality",
    "ViewPosition",
    "ValidationResult",
    "validate",
    "RegionOfInterest",
    "SourceRef",
    "load_embed",
]

__version__ = version("embed-data-model")
