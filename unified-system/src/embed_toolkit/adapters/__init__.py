"""Dataset and source-system adapters."""

from embed_toolkit.adapters.embed import (
    EmbedClinicalImageGraph,
    EmbedClinicalTables,
    EmbedImageTables,
    FindingImageCandidateProjection,
    assemble_clinical_image_graph,
    build_clinical_tables,
    build_image_tables,
    project_finding_image_candidates,
)
from embed_toolkit.adapters.magview import (
    MagViewLocationNormalization,
    MagViewNormalizationWarning,
    MagViewSourceEvidence,
    normalize_magview_location,
)
from embed_toolkit.adapters.embed_history import (
    EmbedPatientHistoryTables,
    build_patient_history_tables,
)
from embed_toolkit.adapters.reconciliation import (
    ExamImageContainmentLink,
    FindingImageCandidate,
    PatientIdentityCheckStatus,
    UnmatchedImage,
    UnmatchedImageReason,
)

__all__ = [
    "EmbedClinicalImageGraph",
    "EmbedClinicalTables",
    "EmbedImageTables",
    "EmbedPatientHistoryTables",
    "ExamImageContainmentLink",
    "FindingImageCandidate",
    "FindingImageCandidateProjection",
    "MagViewLocationNormalization",
    "MagViewNormalizationWarning",
    "MagViewSourceEvidence",
    "PatientIdentityCheckStatus",
    "UnmatchedImage",
    "UnmatchedImageReason",
    "assemble_clinical_image_graph",
    "build_clinical_tables",
    "build_image_tables",
    "build_patient_history_tables",
    "project_finding_image_candidates",
    "normalize_magview_location",
]
