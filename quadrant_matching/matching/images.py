from typing import Literal, Optional, Union
import uuid
import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.axes import Axes
from utility import get_point_on_line
import numpy as np
from hiti_preproc.alignment import ViewPosition, Laterality, Alignment
import math
from findings import Finding


class Image:
    def __init__(
        self,
        dicom_path: str,
        view: Literal[ViewPosition.CC, ViewPosition.MLO],
        laterality: Literal[Laterality.LEFT, Laterality.RIGHT],
        height: int,
        width: int,
        alignment: Alignment,
        roi_coords: list[list[float]],
        nipple_coords: tuple[int, int],
        div_slope: float,
    ) -> None:
        self.hash_id: str = uuid.uuid4().hex
        self.path: str = dicom_path

        self.view: Literal[ViewPosition.CC, ViewPosition.MLO] = view
        if self.view not in [ViewPosition.CC, ViewPosition.MLO]:
            raise ValueError("Invalid view position: '{view}'")

        self.laterality: Literal[Laterality.LEFT, Laterality.RIGHT] = laterality
        if self.laterality not in [Laterality.LEFT, Laterality.RIGHT]:
            raise ValueError("Invalid laterality: '{laterality}'")

        # assess the height, width, and orientation of the image
        self.height: int = height
        self.width: int = width
        self.alignment: Alignment = alignment

        # get the parameters of the dividing line and its perpendicular slope
        self.nipple: tuple[int, int] = nipple_coords
        self.d_slope: float = div_slope
        self.d_y_intercept: float = -1 * (
            self.d_slope * self.nipple[0] - self.nipple[1]
        )
        self.p_slope: float = -1 / self.d_slope if self.d_slope != 0.0 else np.inf

        # measure the depth range as the distance from the nipple to the div y intercept
        self.depth_range: float = self.measure_depth_range()

        # measure the height range as the distance from the nipple to the bottom edge of the image
        self.height_range: float = self.measure_height_range()

        # get thresholds for posterior (always 0), middle, and anterior depths
        middle_distance, anterior_distance = self.partition_depth_range()
        self.m_distance: float = middle_distance
        self.a_distance: float = anterior_distance

        # normalize the alignment of rois and register them to the self.rois list
        roi_coords: list[list[float]] = alignment.realign_coords_list(
            coords_list=roi_coords,
            height=height,
            width=width,
        )
        self.rois: list[ImageROI] = [
            ImageROI(i, self, r) for i, r in enumerate(roi_coords)
        ]

        # initialize list of findings to populate later
        self.findings: list[ImageFinding] = []

    def __hash__(self) -> int:
        return hash(self.hash_id)

    def plot(
        self,
        ax: Optional[Axes] = None,
        dpi: int = 125,
        show_axis: bool = False,
        show_divider: bool = True,
        show_title: bool = True,
    ) -> None:
        image: np.ndarray = pydicom.pixels.pixel_array(self.path)  # type: ignore
        image: np.ndarray = self.alignment.realign_image(image=image)

        if ax is None:
            fig, _ax = plt.subplots(dpi=dpi)
        else:
            _ax = ax

        _ax.imshow(image, cmap="gray")
        if not show_axis:
            _ax.axis("off")

        if show_divider:
            _ax.scatter(
                self.nipple[0],
                self.nipple[1],
                color="xkcd:bright red",
                marker="x",
                s=16,
                zorder=2,
            )
            _ax.axline(
                self.nipple,
                slope=self.d_slope,
                color="white",
                linestyle="--",
                linewidth=2,
                zorder=1,
            )
            _ax.axline(
                self.nipple,
                slope=self.p_slope,
                color="xkcd:light red",
                linestyle="--",
                linewidth=1,
                zorder=1,
            )

            # plot middle depth divider
            m_pos: tuple[float, float] = get_point_on_line(
                self.nipple, self.d_slope, -self.m_distance
            )
            _ax.axline(
                m_pos,
                slope=self.p_slope,
                color="xkcd:light blue",
                linestyle="--",
                linewidth=1,
                zorder=0,
            )

            # plot anterior depth divider
            a_pos: tuple[float, float] = get_point_on_line(
                self.nipple, self.d_slope, -self.a_distance
            )
            _ax.axline(
                a_pos,
                slope=self.p_slope,
                color="xkcd:light blue",
                linestyle="--",
                linewidth=1,
                zorder=0,
            )

        if show_title:
            _ax.set_title(f"{self.laterality} {self.view}")

        roi_colors: list[str] = [
            "xkcd:bright green",
            "xkcd:bright red",
            "xkcd:bright pink",
            "xkcd:bright yellow",
            "xkcd:bright cyan",
            "xkcd:bright sky blue",
        ]
        roi_linestyles: list[str] = ["-", "--"]
        n_colors: int = len(roi_colors)
        for i, roi in enumerate(self.rois):
            # unpack ROI values
            y_min, x_min, y_max, x_max = roi.coords

            color: str = roi_colors[i % n_colors]
            linestyle: str = roi_linestyles[i // n_colors]

            # format the roi into a patch
            roi_patch = patches.Rectangle(
                (x_max, y_max),
                x_min - x_max,
                y_min - y_max,
                edgecolor=color,
                linestyle=linestyle,
                fc="None",
                label=f"ROI #{roi.id}",
                zorder=4,
            )
            # add the patch to the axes
            _ax.add_patch(roi_patch)

            # mark the center point of the ROI
            _ax.scatter(roi.c_x, roi.c_y, marker="x", c=color, s=8, zorder=4)

            # plot horizontal distance line
            if self.view == "MLO":
                h_dist_pos: tuple[float, float] = get_point_on_line(
                    (roi.c_x, roi.c_y), self.d_slope, roi.h_distance
                )
            else:
                h_dist_pos: tuple[float, float] = (roi.c_x + roi.h_distance, roi.c_y)

            h_dist_points: list[tuple[float, float]] = [(roi.c_x, roi.c_y), h_dist_pos]
            _ax.plot(
                [p[0] for p in h_dist_points],
                [p[1] for p in h_dist_points],
                color=color,
                alpha=0.5,
                zorder=3,
            )

            # plot vertical distance line
            if self.view == "MLO":
                v_dist_pos: tuple[float, float] = get_point_on_line(
                    (roi.c_x, roi.c_y), self.p_slope, -roi.v_distance
                )
            else:
                v_dist_pos: tuple[float, float] = (roi.c_x, roi.c_y + roi.v_distance)

            v_dist_points: list[tuple[float, float]] = [(roi.c_x, roi.c_y), v_dist_pos]
            _ax.plot(
                [p[0] for p in v_dist_points],
                [p[1] for p in v_dist_points],
                color=color,
                alpha=0.5,
                zorder=3,
            )

            # mark the distance line intersection points
            dist_inter_points: list[tuple[float, float]] = [h_dist_pos, v_dist_pos]
            _ax.scatter(
                [p[0] for p in dist_inter_points],
                [p[1] for p in dist_inter_points],
                c=color,
                zorder=4,
                marker="x",
                s=5,
            )

        _ax.legend(loc="upper right")

        if ax is None:
            plt.show()

    # def assess_pixels(self):
    #     # load the image from the dicom path and get its height and width
    #     image: np.ndarray = pydicom.pixels.pixel_array(self.path)  # type: ignore
    #     # self.height, self.width = image.shape

    #     # measure the side of the current image -- if R sided, coords should be flipped
    #     image_side: Literal["L", "R", "E"] = check_side(image)
    #     if image_side == "R":
    #         self.flipped = True

    # def normalize_roi_alignment(self, roi_coords: list[list[int]]) -> list[list[int]]:
    #     # re-align rois to the left for right-aligned images
    #     if self.flipped:
    #         roi_coords = flip_roi_coords(roi_coords, self.width)

    #     return roi_coords

    def measure_depth_range(self) -> float:
        if self.view == "MLO":
            dr_x_disp: float = float(self.nipple[0])
            dr_y_disp: float = float(self.nipple[1] - self.d_y_intercept)
            depth_range: float = math.sqrt(dr_x_disp**2 + dr_y_disp**2)

        else:  # self.view == "CC"
            depth_range: float = float(self.nipple[0])

        return depth_range

    def measure_height_range(self) -> float:
        if self.view == "MLO":
            # get the center point of the dividing line between the left edge and the nipple
            div_center: tuple[float, float] = get_point_on_line(
                self.nipple, self.p_slope, self.depth_range / 2
            )

            # extend the div center point to the bottom horizontal edge of the image
            dc_intercept: float = div_center[1] - (self.p_slope * div_center[0])

            # find the point where the dc line intercepts the y axis at dc_y (the max height)
            dc_y: float = float(self.height - 1.0)
            dc_x: float = (dc_y - dc_intercept) / self.p_slope

            displacement_x: float = abs(div_center[0] - dc_x)
            displacement_y: float = abs(div_center[1] - dc_y)
            height_range: float = math.sqrt(displacement_x**2 + displacement_y**2)

        else:  # self.view == "CC"
            height_range: float = float(self.height - 1.0 - self.nipple[1])

        return height_range

    def partition_depth_range(self) -> tuple[float, float]:
        third_depth: float = self.depth_range / 3

        middle_threshold: float = third_depth * 2
        anterior_threshold: float = third_depth

        return middle_threshold, anterior_threshold

    def register_findings(self, findings: list[Finding]) -> None:
        for f in findings:
            image_finding = ImageFinding(self, f)
            image_finding.evaluate_location()

            self.findings.append(image_finding)

    def export_matches(self) -> dict[str, Union[str, list[int]]]:
        roi_numfind_list: list[int] = []

        for roi in self.rois:
            # code -99 if the roi had no matched finding
            match_id: int = (
                roi.matched_finding.id if roi.matched_finding is not None else -99
            )
            roi_numfind_list.append(match_id)

        return {"anon_dicom_path": self.path, "ROI_numfind_matches": roi_numfind_list}


# ----------------------------------------------------------------------------------------------------------------------------


class ImageFinding:
    def __init__(self, image: Image, finding: Finding) -> None:
        self.image: Image = image
        self.finding: Finding = finding
        self.id: int = finding.id

        avg_loc, avg_depth = self.evaluate_location()
        self.loc: Optional[float] = avg_loc
        self.depth: Optional[float] = avg_depth

        self.hash_id: str = self.image.hash_id + self.finding.hash_id

        self.candidates: list[ImageROI] = []
        self.matched_rois: list[ImageROI] = []

    def __hash__(self) -> int:
        return hash(self.hash_id)

    def evaluate_location(self) -> tuple[Optional[float], Optional[float]]:
        avg_loc, avg_depth = self.finding.evaluate_quadrant(
            self.image.view, self.image.laterality
        )
        return avg_loc, avg_depth

    def __repr__(self) -> str:
        return f"ImageFinding({self.image.laterality}{self.image.view}, #{self.finding.id}, l: {self.loc}, d: {self.depth})"


# ----------------------------------------------------------------------------------------------------------------------------


class ImageROI:
    def __init__(self, roi_id: int, image: Image, coords: list[float]) -> None:
        self.hash_id: str = uuid.uuid4().hex
        self.id: int = roi_id
        self.image: Image = image
        self.coords: list[float] = coords

        # get center x/y coords of the ROI
        self.c_x: float = (self.coords[1] + self.coords[3]) / 2
        self.c_y: float = (self.coords[0] + self.coords[2]) / 2

        # calculate the vertical and horizontal distance for the ROI
        v_distance, h_distance = self.measure_distance()
        self.v_distance: float = v_distance
        self.h_distance: float = h_distance

        # normalize the
        norm_v_distance, norm_h_distance = self.normalize_distance()
        self.norm_v_distance: float = norm_v_distance
        self.norm_h_distance: float = norm_h_distance

        # pre-compute expected loc/depth based on v and h distance
        self.exp_loc: float = self.precompute_loc()
        self.exp_depth: float = self.precompute_depth()

        # initialize matched finding attr for later use
        self.candidates: list[ImageFinding] = []
        self.matched_finding: Optional[ImageFinding] = None

    def __hash__(self) -> int:
        return hash(self.hash_id)

    def __repr__(self) -> str:
        match_str: str = (
            f", match: {self.matched_finding.id}"
            if self.matched_finding is not None
            else ""
        )
        # return f"ImageROI(#{self.id}, loc: {self.exp_loc}, depth: {self.exp_depth}, (v: {self.norm_v_distance:.1f}, h: {self.norm_h_distance:.1f}){match_str})"
        return f"ImageROI(#{self.id}, loc: {self.norm_v_distance:.1f}, depth: {self.norm_h_distance:.1f}{match_str})"

    def measure_distance(self) -> tuple[float, float]:
        if self.image.view == "MLO":
            # calc the y intercept of the perpendicular line when it passes through the ROI center point
            p_y_intercept: float = -1 * (self.image.p_slope * self.c_x - self.c_y)

            # solve for the x/y coords of the intersection between the divider and perpendicular lines
            # set m1*x + b1 = m2*x + b2 and solve for x
            inter_x: float = (p_y_intercept - self.image.d_y_intercept) / (
                self.image.d_slope - self.image.p_slope
            )

            # solve for the intersection y by plugging the intersection x into either line formula
            inter_y: float = self.image.d_slope * inter_x + self.image.d_y_intercept

            # solve for the vertical displacement between the ROI center and intersection
            v_distance: float = self.point_distance(
                (self.c_x, self.c_y), (inter_x, inter_y)
            )

            # flip the sign of the vertical distance if the roi is below the divider
            if self.c_y >= inter_y:
                v_distance: float = -1 * v_distance

            # solve for the horizontal displacement between the intersection and the nipple
            h_distance: float = self.point_distance(
                (inter_x, inter_y), self.image.nipple
            )

            # flip the sign of the horizontal distance if the roi is to the right of the nipple
            if inter_x >= self.image.nipple[0]:
                h_distance: float = -1 * h_distance

        else:  # view == "CC"
            # calculate vertical distance as the nipple y coord - roi center y coord
            v_distance: float = float(self.image.nipple[1] - self.c_y)

            # calculate horizontal distance as the nipple x coord - roi center x coord
            h_distance: float = float(self.image.nipple[0] - self.c_x)

        return v_distance, h_distance

    @staticmethod
    def point_distance(
        point_a: tuple[float, float], point_b: tuple[float, float]
    ) -> float:
        return math.sqrt(
            (point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2
        )

    def normalize_distance(self) -> tuple[float, float]:
        # get the horizontal distance as a proportion of the height range
        # negative values indicate the roi is centered below the dividing line
        v_proportion: float = self.v_distance / self.image.height_range

        # scale the v proportion between +/- 2.0 (at the top/bottom edges) and 0
        norm_v_distance: float = v_proportion * 2.0

        # get the horizontal distance as a proportion of the depth range
        # negative values indicate the roi is centered to the right of the nipple
        h_proportion: float = self.h_distance / self.image.depth_range

        # scale the h proportion between 2.5 (at the left edge of the image) and -0.5 (at the nipple)
        norm_h_distance: float = (h_proportion * 3.0) - 0.5

        return norm_v_distance, norm_h_distance

    def precompute_loc(self) -> float:
        # upper/superior or outer/lateral
        if self.v_distance >= 0:
            expected_loc: float = 1.0
        # lower/inferior or inner/medial
        else:
            expected_loc: float = -1.0

        return expected_loc

    def precompute_depth(self) -> float:
        # anterior
        if self.h_distance < self.image.a_distance:
            expected_depth: float = 0.0
        # middle
        elif self.h_distance < self.image.m_distance:
            expected_depth: float = 1.0
        # posterior
        else:
            expected_depth: float = 2.0

        return expected_depth

    def evaluate_match(self):
        n_findings: int = len(self.image.findings)

        # unable to match if there are no findings
        if n_findings == 0:
            return

        # match single finding if there is only one
        elif n_findings == 1:
            self.matched_finding = self.image.findings[0]
            return

        # perform matching if there are >1 findings
        else:
            # calculate the cost of matching this roi to any of the findings
            finding_costs: list[float] = [self._cost(f) for f in self.image.findings]

            # can't match if there is no location/depth info for any findings
            if all([math.isnan(fc) for fc in finding_costs]):
                return

            # multiple potential findings, equal likelihood for all
            elif len(set(finding_costs)) == 1:
                return

            # otherwise, find the finding idx with the lowest cost
            else:
                min_idx: int = int(np.nanargmin(finding_costs))
                self.matched_finding = self.image.findings[min_idx]
                return

    def _cost(self, finding: ImageFinding) -> float:
        running_cost: float = 0.0

        # if neither loc/depth is defined, return NaN
        if finding.loc is None and finding.depth is None:
            return float("nan")

        # otherwise calculate the cost
        else:
            loc: float = finding.loc if finding.loc is not None else 0.0
            loc_cost: float = abs(self.norm_v_distance - loc) ** 2
            # loc_cost: float = abs(self.exp_loc - loc)**2
            running_cost += loc_cost

            depth: float = finding.depth if finding.depth is not None else 1.0
            depth_cost: float = abs(self.norm_h_distance - depth) ** 2
            # depth_cost: float = abs(self.exp_depth - depth)**2
            running_cost += depth_cost

            return running_cost / 2
