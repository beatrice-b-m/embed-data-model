from typing import Optional
import pydicom
import numpy as np
from scipy.stats import linregress


def get_pixel_spacing(dicom: pydicom.FileDataset) -> float:
    """Determine the PixelSpacing of the DICOM

    Raises:
        KeyError: Raises a KeyError if neither the PixelSpacing or ImagerPixelSpacing
        attributes exist.

    Returns:
        float: The DICOM PixelSpacing as a float (assumes square pixel spacing)
    """
    # determine the image pixel spacing (mms per pixel)
    pixel_spacing: Optional[list[str]] = dicom.get("PixelSpacing", None)

    if pixel_spacing is None:
        pixel_spacing: Optional[list[str]] = dicom.get("ImagerPixelSpacing", None)

    if pixel_spacing is None:
        raise KeyError("Could not determine DICOM pixel spacing")

    return float(pixel_spacing[0])


def get_view_position(dicom: pydicom.FileDataset) -> str:
    return str(dicom.get("ViewPosition", dicom.SeriesDescription))


def get_boundary(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = mask.shape

    # create a boolean mask for rows that contain at least one non-zero value
    rows_with_data = np.any(mask > 0, axis=1)

    # initialize the boundary array with nans
    boundary = np.full(height, np.nan, dtype=np.float32)

    if np.any(rows_with_data):
        # find the index of the first non-zero value in each horizontally reversed row
        mask_subset = mask[rows_with_data, ::-1]
        indices_in_reversed = np.argmax(mask_subset > 0, axis=1)

        # convert these indices back to the original (non-reversed) coordinate system.
        indices_in_original = width - 1 - indices_in_reversed

        # place the calculated indices into the correct positions in the boundary array.
        boundary[rows_with_data] = indices_in_original

    b_indices = np.arange(boundary.shape[0])

    return boundary, b_indices


def get_dividing_line(
    coords: tuple[int, int],
    view_position: str,
    boundary: np.ndarray,
    pixel_spacing: float,
    search_mms: int = 30,
) -> float:
    if "CC" in view_position:
        # dividing line slope in CC images is always 0.0
        return 0.0

    elif "ML" in view_position:
        height: int = boundary.shape[0]

        # get the points adjacent to the coords on the boundary
        coords_x, coords_y = coords
        half_search_space: int = int(search_mms / pixel_spacing) // 2
        start_y = max(0, coords_y - half_search_space)
        end_y = min(height, coords_y + half_search_space + 1)
        y_search_indices = np.arange(start_y, end_y)
        x_search_coords = boundary[y_search_indices]

        # filter out any rows in the search space where x is NaN
        valid_points_mask = ~np.isnan(x_search_coords)
        y_search_indices = y_search_indices[valid_points_mask]
        x_search_coords = x_search_coords[valid_points_mask]

        if len(y_search_indices) < 2:
            raise ValueError(
                "Not enough border points near the nipple to fit a tangent line."
            )

        # fit a tangent line to the local edge and get its slope
        tangent_slope_dxdy, _, _, _, _ = linregress(y_search_indices, x_search_coords)

        # calculate the slope of the perpendicular line
        m_dividing: float = np.clip(-tangent_slope_dxdy, 0.2, 0.8)  # type: ignore

        return m_dividing

    else:
        raise ValueError("Unrecognized ViewPosition: {view_position}")
