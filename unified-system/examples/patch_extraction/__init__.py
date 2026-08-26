"""Self-contained image patch-extraction recipe."""

from examples.patch_extraction.extraction import (
    PatchExtractionConfig,
    PatchExtractor,
    extract_patch,
)
from examples.patch_extraction.results import (
    AuditWarning,
    Evidence,
    PatchExtractionResult,
    ResultStatus,
    WarningSeverity,
)

__all__ = [
    "AuditWarning",
    "Evidence",
    "PatchExtractionConfig",
    "PatchExtractionResult",
    "PatchExtractor",
    "ResultStatus",
    "WarningSeverity",
    "extract_patch",
]
