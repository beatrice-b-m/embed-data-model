"""Optional patch-extraction workflow service."""

from embed_toolkit.workflows.patch_extraction import (
    PatchExtractionConfig,
    PatchExtractor,
    extract_patch,
)

__all__ = [
    "PatchExtractionConfig",
    "PatchExtractor",
    "extract_patch",
]
