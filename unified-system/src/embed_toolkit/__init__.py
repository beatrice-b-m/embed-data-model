"""Unified EMBED mammography toolkit."""

from importlib.metadata import version

from embed_toolkit.clinical.exams import BreastSide, Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.procedures import Procedure, ProcedureIdentity
from embed_toolkit.clinical.pathology import Pathology, CancerRegistryEntry
from embed_toolkit.core.primitives import Laterality, ImageModality, ViewPosition
from embed_toolkit.core.validation import ValidationResult, validate
from embed_toolkit.core.graph import DatasetGraph
from embed_toolkit.core.source import Issue, SourceRef
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.rois import Box, RegionOfInterest
from embed_toolkit.sources.embed import LoadReport, load_embed

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

__version__ = version("embed-toolkit-unified")
