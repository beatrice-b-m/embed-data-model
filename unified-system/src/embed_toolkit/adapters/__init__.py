"""Dataset and source-system adapters."""

from embed_toolkit.adapters.embed import (
    EmbedClinicalTables,
    EmbedImageTables,
    FindingImageJoin,
    build_clinical_tables,
    build_exams,
    build_image_tables,
    build_images,
    build_patients,
    build_rois,
    join_findings_to_images,
)
from embed_toolkit.adapters.magview import (
    MagViewLocationNormalization,
    MagViewNormalizationWarning,
    MagViewSourceEvidence,
    normalize_magview_location,
)

__all__ = [
    "EmbedClinicalTables",
    "EmbedImageTables",
    "FindingImageJoin",
    "MagViewLocationNormalization",
    "MagViewNormalizationWarning",
    "MagViewSourceEvidence",
    "build_clinical_tables",
    "build_exams",
    "build_image_tables",
    "build_images",
    "build_patients",
    "build_rois",
    "join_findings_to_images",
    "normalize_magview_location",
]
