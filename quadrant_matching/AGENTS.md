# Mammography ROI Quadrant Parser — Architecture Reference

## System Purpose

This system matches Regions of Interest (ROIs) in mammography images to clinical findings by inferring their shared anatomical location. Given a finding's coded location/depth descriptors and an image's detected ROI bounding boxes, the system answers: *which ROI corresponds to which clinical finding?*

The pipeline operates per-exam and outputs a mapping of `(image, ROI index) → finding number`.

---

## Core Conceptual Model

### Two Coordinate Systems, One Space

The central challenge is that clinical findings are described in **code space** (anatomical location/depth codes from radiology reports) while ROIs are described in **pixel space** (bounding box coordinates in a DICOM image). The system normalizes both into a shared **anatomical coordinate space** with two axes:

- **Location axis** (`loc`): lateral/superior (+1) vs. medial/inferior (−1), centered at 0
- **Depth axis** (`depth`): anterior (0) → middle (1) → posterior (2)

Matching is then a nearest-neighbor search in this 2D normalized space.

---

## Module Breakdown

### `matching/quadrants.py` — Anatomical Reference System

Defines the vocabulary for converting codes to positions.

**`Quadrant`** is the atomic unit: a named anatomical region (e.g., `"lateral"`, `"axillary_tail"`) tagged with its applicable view (`CC`, `MLO`, or `Both`), side (`L`, `R`, or `Both`), and its canonical `loc` / `depth` integers.

**`QuadrantCode`** represents a single code string (e.g., `"OU"`, `"IN"`, `"A"`, `"12"`) and holds the list of `Quadrant` objects it maps to, along with pre-averaged `loc` and `depth` values.

**`QuadrantLookup`** is the lookup table. It indexes all `QuadrantCode` objects into nested dicts:
```
ldict[view][side][code] → QuadrantCode   # location codes
ddict[view][side][code] → QuadrantCode   # depth codes
```
The double-keying on view and side means that the same code can resolve to different positions depending on which image is being processed. Codes that apply to `"Both"` views or sides are duplicated into all applicable slots during construction.

---

### `matching/findings.py` — Clinical Finding Model

**`Finding`** stores the parsed representation of one radiological finding: its report number, laterality, and lists of location/depth code strings. It holds a reference to the shared `QuadrantLookup`.

The key method is `evaluate_quadrant(view, laterality)`, which translates the finding's code lists into a `(avg_loc, avg_depth)` position in normalized space. Each code is individually resolved through the lookup, and the results are averaged — so a finding with multiple location codes lands at their centroid.

A `Finding` with no valid codes returns `(None, None)` and will remain unmatched.

---

### `matching/images.py` — Image Geometry and Matching

This is the most geometrically complex module. It handles two distinct image types:

#### MLO (Mediolateral Oblique) geometry

The image is tilted; anatomy runs diagonally. The system defines a **dividing line** with slope `d_slope` and intercept `d_y_intercept` that separates superior from inferior regions. A **perpendicular slope** `p_slope` is used to measure depth (distance from nipple along the pectoral axis).

For each ROI center:
- `v_distance`: perpendicular distance to the dividing line (sign indicates superior/inferior)
- `h_distance`: distance along the divider from the nipple (measures depth)

#### CC (Craniocaudal) geometry

The image is top-down; anatomy is Cartesian. Distances from the nipple are simple x/y offsets:
- `v_distance`: vertical offset from nipple (lateral vs. medial)
- `h_distance`: horizontal offset from nipple (depth)

#### Normalization

Raw pixel distances are converted to the shared 0–2 scale using the image's measured ranges:
- `depth_range`: nipple-to-posterior boundary distance
- `height_range`: nipple-to-superior/inferior boundary distance

The thresholds `a_distance` and `m_distance` partition depth into three equal zones (anterior/middle/posterior).

#### Key classes

**`Image`** owns the geometry parameters, a list of `ImageROI` objects, and a list of `ImageFinding` objects (findings scoped to this image's view and side).

**`ImageROI`** represents one detected region. After `measure_distance()` and `normalize_distance()`, it holds normalized `(norm_v_distance, norm_h_distance)`. The `evaluate_match()` method selects the best-matching `ImageFinding` by minimizing `_cost()` — the squared L2 distance in normalized space.

**`ImageFinding`** is a finding scoped to one image. It stores the `(loc, depth)` expectation for this specific view/side, evaluated via `Finding.evaluate_quadrant()`.

#### Matching logic (in `ImageROI.evaluate_match`)

| # of findings registered to image | Outcome |
|---|---|
| 0 | ROI remains unmatched |
| 1 | Automatic match (no cost calculation needed) |
| > 1 | Compute cost to each; assign minimum. Tie or all-invalid → no match. |

Unmatched ROIs are reported as finding ID `−99`.

---

### `matching/exams.py` — Pipeline Orchestration

**`Exam`** is the top-level object. It is the only entry point an external caller needs.

**Registration phase** (`register(findings_df, images_df)`):
1. `_register_findings()` — iterates rows of the findings DataFrame, constructs `Finding` objects. BILATERAL findings are split into two `Finding` instances (one per side).
2. `_register_images()` — iterates rows of the images DataFrame, constructs `Image` objects with parsed ROI coordinates, nipple position, and geometry.
3. `_link_findings()` — calls `image.register_findings(findings)` for each image, which in turn creates `ImageFinding` wrappers and evaluates expected positions.

**Matching phase** (`match()`):
- Iterates over all images on both sides
- Calls `roi.evaluate_match()` for each ROI in each image
- Collects results via `image.export_matches()`
- Returns a list of dicts: `{anon_dicom_path, ROI_numfind_matches: [finding_id, ...]}`

---

### `matching/utility.py` — Geometry Utilities

`get_point_on_line(origin, slope, distance)` computes a point at a given arc length along a line. Used in `Image` for calculating the anterior/middle/posterior depth threshold points and in visualization.

---

## Data Flow Summary

```
findings_df (codes, laterality)       images_df (path, view, ROIs, nipple)
        │                                         │
_register_findings()                  _register_images()
        │                                         │
   Finding objects                           Image objects
        │                                         │
        └──────────── _link_findings() ───────────┘
                               │
                    ImageFinding (expected loc/depth)
                    ImageROI (measured loc/depth)
                               │
                      evaluate_match() per ROI
                      (L2 cost in normalized space)
                               │
                       export_matches()
                               │
                 {image_path → [finding_id per ROI]}
```

---

## Object Ownership and References

```
Exam
├── QuadrantLookup (shared reference across all Finding objects)
├── findings: {side → [Finding]}
└── images:   {side → [Image]}
                         └── findings: [ImageFinding]
                         │       └── → Finding (pointer)
                         └── rois:     [ImageROI]
                                 └── matched_finding → ImageFinding (pointer)
```

`ImageFinding` and `ImageROI` both maintain `candidates` lists that are populated bidirectionally during `register_findings()`, before matching resolves them to single assignments.

---

## View-Specific Behavior Summary

| Property | CC view | MLO view |
|---|---|---|
| Lateral/medial axis | Vertical (y offset from nipple) | Perpendicular distance to dividing line |
| Depth axis | Horizontal (x offset from nipple) | Distance along dividing line from nipple |
| `depth_range` measurement | x-distance to posterior edge | Euclidean distance to posterior edge |
| `height_range` measurement | y-distance to boundary | Euclidean distance to boundary |

---

## External Dependencies

| Dependency | Role |
|---|---|
| `hiti_preproc.alignment` | Provides `ViewPosition`, `Laterality`, `PatientOrientation`, `Alignment` — handles coordinate normalization for image orientation |
| `pandas` | DataFrame ingestion for findings and images tables |
| `numpy` | Numeric ops; `nanargmin` for cost minimization |
| `matplotlib` | `Image.plot()` visualization |

The `hiti_preproc` package is not in this repo; it is an upstream preprocessing dependency that supplies the `Alignment` object used to normalize ROI coordinates before distance calculations.
