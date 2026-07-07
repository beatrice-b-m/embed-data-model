---
type: Reference
title: Mammography Breast Coordinate System
description: Summary of the mammographic quadrant and depth coordinate system used to localize breast findings across CC and MLO views.
tags: [mammography, breast-imaging, localization, breast-quadrants]
timestamp: 2026-07-03T00:00:00-04:00
kb_status: seed
aliases: []
resource:
---

# Mammography Breast Coordinate System

Source: raw transcript by Beatrice Brown-Mulry, supplied 2026-07-03.

## Summary

Screening mammography commonly uses paired craniocaudal (CC) and mediolateral oblique (MLO) views to localize findings in a projected 3D breast volume. Together, these views provide complementary axes for assigning a finding to a breast quadrant and to an anterior, middle, or posterior depth region.

The clinical reporting frame is laterality first, then clock-face or quadrant location, then lesion depth and distance from the nipple. ACR BI-RADS v2025 lists quadrant options as upper outer, upper inner, lower outer, and lower inner, and depth as anterior, middle, or posterior third.

## View Axes

The MLO view is an oblique lateral projection rather than a perfectly vertical mediolateral projection. Its obliquity helps include posterior tissue, the axillary tail, and sometimes axillary lymph nodes. A true mediolateral or lateromedial view can help with localization when a stricter lateral projection is needed.

For quadrant assignment, the MLO view primarily contributes the superior-inferior axis:

- `superior` / `upper`: above the nipple reference line.
- `inferior` / `lower`: below the nipple reference line.

The CC view primarily contributes the medial-lateral axis:

- `medial` / `inner`: toward the sternum.
- `lateral` / `outer`: toward the axilla.

Correction to the transcript: medial and lateral should not be treated as globally fixed to the upper or lower half of a displayed CC image. Apparent image top/bottom depends on breast laterality, image orientation, and hanging/display convention. Algorithmically, resolve this from laterality and image-orientation metadata rather than from raw screen position alone.

## Posterior Nipple Line

The posterior nipple line (PNL) is the working reference from the nipple back toward the posterior image edge after alignment. In an MLO image it often appears oblique because the projection itself is oblique. Its exact angle varies with patient anatomy, positioning, and image display.

For a quadrant/depth algorithm, the PNL can be treated as a nipple-to-posterior reference axis:

- It provides a practical divider for upper versus lower regions on the MLO projection.
- It anchors depth segmentation from the nipple/anterior breast toward the posterior breast.
- Its image-edge point is derived from the nipple position and PNL slope at `x=0` when the posterior breast is aligned to the left image edge, or at `x=x_max` when aligned to the right image edge.

## Depth Regions

Depth adds a third localization axis from the nipple/anterior breast toward the posterior breast. Segment the nipple-to-PNL-edge reference distance into thirds:

- `anterior`: closest to the nipple.
- `middle`: central third.
- `posterior`: closest to the posterior image-edge point on the PNL.

Combining the four quadrants with three depth regions yields twelve coarse 3D localization bins:

- upper outer anterior, middle, posterior
- upper inner anterior, middle, posterior
- lower outer anterior, middle, posterior
- lower inner anterior, middle, posterior

These bins are useful for algorithmic localization, ROI assignment, toy mammogram generation, and comparing image-derived regions with report-derived finding locations.

## Implementation Notes

- Prefer clock-face position when report text provides it, while preserving quadrant and depth when available.
- Treat `inner` and `outer` as laterality-dependent anatomical terms, not display-position terms.
- Keep CC and MLO localization logic separate until they are fused into a breast-side coordinate assignment.
- Store enough metadata to reconstruct how a quadrant/depth assignment was made: laterality, view, image orientation or alignment, nipple point, PNL slope, image dimensions, and which image edge was used for the derived PNL point.

## References

- [ACR BI-RADS v2025 Mammography Lexicon Summary Form](https://edge.sitecorecloud.io/americancoldf5f-acrorgf92a-productioncb02-3650/media/ACR/Files/RADS/BI-RADS/BI-RADS-Summary-Form-Mammography.pdf)
- [ACR BI-RADS](https://www.acr.org/Clinical-Resources/Clinical-Tools-and-Reference/Reporting-and-Data-Systems/BI-RADS)
