"""Dependency-free image patch extraction from image-local ROI boxes."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from embed_toolkit.audit.evidence import AuditWarning, Evidence, WarningSeverity
from embed_toolkit.audit.results import PatchExtractionResult, ResultStatus
from embed_toolkit.imaging.rois import RegionOfInterest


PixelData = Any
CoordinateBox = Tuple[int, int, int, int]


@dataclass(frozen=True)
class PatchExtractionConfig:
    """Configuration for constant-padding patch extraction."""

    pad: bool = True
    pad_value: Any = 0


class PatchExtractor:
    """Extract rectangular image patches for ROI boxes without ROI-owned logic."""

    def __init__(self, *, pad: bool = True, pad_value: Any = 0) -> None:
        self.config = PatchExtractionConfig(pad=pad, pad_value=pad_value)

    def extract(
        self,
        image_data: PixelData,
        roi: RegionOfInterest,
        *,
        image: Optional[Any] = None,
        image_id: Optional[str] = None,
        patch_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> PatchExtractionResult:
        """Return a structured patch extraction result for ``image_data`` and ``roi``."""

        height, width = _infer_image_shape(image_data)
        requested_bbox = _integer_bbox(roi.coordinates)
        clipped_bbox = _clip_bbox(requested_bbox, height=height, width=width)
        padding = _padding_for(requested_bbox, height=height, width=width)
        extraction_bbox = requested_bbox if self.config.pad else clipped_bbox

        if not self.config.pad and _has_padding(padding):
            padding = _zero_padding()

        extracted = _slice_image(image_data, clipped_bbox)
        patch_data = _apply_padding(extracted, padding, self.config.pad_value)
        if not self.config.pad:
            patch_data = extracted

        evidence = [
            Evidence(
                kind="roi_bbox",
                source="patch_extractor",
                payload={
                    "requested_bbox": list(requested_bbox),
                    "clipped_bbox": list(clipped_bbox),
                    "image_shape": [height, width],
                },
            )
        ]
        warnings = _warnings_for(
            requested_bbox=requested_bbox,
            clipped_bbox=clipped_bbox,
            pad=self.config.pad,
        )
        status = ResultStatus.PARTIAL if warnings else ResultStatus.SUCCESS

        resolved_image_id = image_id or _object_attr(image, "image_id") or roi.image_id
        if resolved_image_id != roi.image_id:
            raise ValueError("Patch image_id must match ROI image ownership")
        image_source = _object_attr(image, "canonical_source")
        image_sources = _object_attr(image, "sources")
        if image_source is not None and (
            image_sources is None or roi.locator.image_locator not in image_sources
        ):
            raise ValueError("Patch image must match the ROI locator image scope")
        if image_sources is not None and any(
            source not in image_sources for source in roi.sources
        ):
            raise ValueError("ROI sources must occur in the patch image ledger")
        resolved_patch_id = patch_id or _default_patch_id(roi)
        shape = _patch_shape(patch_data)
        payload = {
            "data": patch_data,
            "padding": padding,
            "requested_bbox": list(requested_bbox),
            "clipped_bbox": list(clipped_bbox),
            "pad_value": self.config.pad_value,
            "padded": self.config.pad and _has_padding(padding),
        }

        result_metadata = dict(metadata or {})
        result_metadata.update(
            {
                "annotation_source": roi.annotation_source,
                "confidence": roi.confidence,
                "frame_indices": list(roi.frame_indices),
                "source_provenance": roi.source_provenance.to_dict(),
                "source_references": [source.to_dict() for source in roi.sources],
                "coordinate_frame_id": roi.coordinate_frame_id
                or _object_attr(image, "coordinate_frame_id"),
            }
        )

        return PatchExtractionResult(
            status=status,
            image_id=resolved_image_id,
            roi_locator=roi.locator,
            patch_id=resolved_patch_id,
            bbox=[float(value) for value in extraction_bbox],
            shape=shape,
            patch_payload=payload,
            evidence=evidence,
            warnings=warnings,
            metadata=result_metadata,
        )


def extract_patch(
    image_data: PixelData,
    roi: RegionOfInterest,
    *,
    image: Optional[Any] = None,
    image_id: Optional[str] = None,
    patch_id: Optional[str] = None,
    pad: bool = True,
    pad_value: Any = 0,
    metadata: Optional[Mapping[str, Any]] = None,
) -> PatchExtractionResult:
    """Convenience function for extracting one image patch."""

    return PatchExtractor(pad=pad, pad_value=pad_value).extract(
        image_data,
        roi,
        image=image,
        image_id=image_id,
        patch_id=patch_id,
        metadata=metadata,
    )


def _infer_image_shape(image_data: PixelData) -> Tuple[int, int]:
    shape = getattr(image_data, "shape", None)
    if shape is not None and len(shape) >= 2:
        return int(shape[0]), int(shape[1])
    height = len(image_data)
    width = 0 if height == 0 else len(image_data[0])
    return int(height), int(width)


def _integer_bbox(coordinates: Sequence[float]) -> CoordinateBox:
    y_min, x_min, y_max, x_max = coordinates
    return (
        int(math.floor(y_min)),
        int(math.floor(x_min)),
        int(math.ceil(y_max)),
        int(math.ceil(x_max)),
    )


def _clip_bbox(bbox: CoordinateBox, *, height: int, width: int) -> CoordinateBox:
    y_min, x_min, y_max, x_max = bbox
    return (
        min(max(y_min, 0), height),
        min(max(x_min, 0), width),
        min(max(y_max, 0), height),
        min(max(x_max, 0), width),
    )


def _padding_for(
    requested: CoordinateBox,
    *,
    height: int,
    width: int,
) -> Mapping[str, int]:
    y_min, x_min, y_max, x_max = requested
    requested_height = max(0, y_max - y_min)
    requested_width = max(0, x_max - x_min)
    top = min(max(0, -y_min), requested_height)
    left = min(max(0, -x_min), requested_width)
    bottom = min(max(0, y_max - height), requested_height - top)
    right = min(max(0, x_max - width), requested_width - left)
    return {
        "top": top,
        "left": left,
        "bottom": bottom,
        "right": right,
    }


def _zero_padding() -> Mapping[str, int]:
    return {"top": 0, "left": 0, "bottom": 0, "right": 0}


def _has_padding(padding: Mapping[str, int]) -> bool:
    return any(value > 0 for value in padding.values())


def _slice_image(image_data: PixelData, bbox: CoordinateBox) -> List[List[Any]]:
    y_min, x_min, y_max, x_max = bbox
    if y_max <= y_min or x_max <= x_min:
        return []

    sliced = _try_numpy_style_slice(image_data, bbox)
    if sliced is not None:
        return _to_nested_lists(sliced)

    return [_to_list(row[x_min:x_max]) for row in image_data[y_min:y_max]]


def _try_numpy_style_slice(image_data: PixelData, bbox: CoordinateBox) -> Optional[Any]:
    y_min, x_min, y_max, x_max = bbox
    try:
        return image_data[y_min:y_max, x_min:x_max]
    except (TypeError, KeyError, IndexError):
        return None


def _to_nested_lists(value: Any) -> List[List[Any]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [_to_list(row) for row in value]


def _to_list(value: Any) -> List[Any]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        return value
    return list(value)


def _apply_padding(
    data: List[List[Any]],
    padding: Mapping[str, int],
    pad_value: Any,
) -> List[List[Any]]:
    if not _has_padding(padding):
        return data

    source_width = len(data[0]) if data else 0
    width = padding["left"] + source_width + padding["right"]
    padded: List[List[Any]] = []
    for _ in range(padding["top"]):
        padded.append([pad_value] * width)
    for row in data:
        padded.append(
            ([pad_value] * padding["left"])
            + list(row)
            + ([pad_value] * padding["right"])
        )
    for _ in range(padding["bottom"]):
        padded.append([pad_value] * width)
    return padded


def _patch_shape(data: List[List[Any]]) -> List[int]:
    if not data:
        return [0, 0]
    return [len(data), len(data[0])]


def _warnings_for(
    *,
    requested_bbox: CoordinateBox,
    clipped_bbox: CoordinateBox,
    pad: bool,
) -> List[AuditWarning]:
    if requested_bbox == clipped_bbox:
        return []
    code = "patch_padded" if pad else "patch_clipped"
    message = (
        "ROI box extended outside the image and was padded"
        if pad
        else "ROI box extended outside the image and was clipped"
    )
    return [
        AuditWarning(
            code=code,
            message=message,
            severity=WarningSeverity.WARNING,
            payload={
                "requested_bbox": list(requested_bbox),
                "clipped_bbox": list(clipped_bbox),
            },
        )
    ]


def _default_patch_id(roi: RegionOfInterest) -> str:
    encoded = json.dumps(
        roi.locator.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"patch:{hashlib.sha256(encoded).hexdigest()[:20]}"


def _object_attr(obj: Optional[Any], name: str) -> Optional[Any]:
    if obj is None:
        return None
    return getattr(obj, name, None)
