import ast
from typing import Literal, Union, cast
import pandas as pd
from hiti_preproc.alignment import (
    Laterality,
    ViewPosition,
    PatientOrientation,
    Alignment,
)

from quadrants import QuadrantLookup
from findings import Finding
from images import Image


class Exam:
    def __init__(self, accession: int, lookup: QuadrantLookup) -> None:
        self.accession: int = accession
        self.lookup: QuadrantLookup = lookup

        # initialize dicts to store findings and images per side
        self.findings: dict[Literal["L", "R"], list[Finding]] = {"L": [], "R": []}
        self.images: dict[Literal["L", "R"], list[Image]] = {"L": [], "R": []}

    def register(self, findings: pd.DataFrame, images: pd.DataFrame) -> None:
        # register findings and images
        self._register_findings(findings)
        self._register_images(images)

        # link findings to images on the relevant sides
        self._link_findings()

    def _register_findings(self, data: pd.DataFrame) -> None:
        data: pd.DataFrame = data.drop_duplicates(
            subset=["numfind", "side", "location", "depth"]
        )

        for _, row in data.iterrows():
            num: int = int(row["numfind"])
            laterality: Laterality = Laterality(row["side"])
            if laterality is Laterality.UNKNOWN:
                raise ValueError(f"Unrecognized laterality: '{row.side}'")

            # side: Literal["L", "R", "B"] = row["side"]
            locs: list[str] = [s for s in str(row["location"]).split(",") if s != "nan"]
            depths: list[str] = [s for s in str(row["depth"]).split(",") if s != "nan"]

            if laterality == Laterality.BILATERAL:
                self.findings["L"].append(
                    Finding(num, laterality, self.lookup, locs, depths)
                )
                self.findings["R"].append(
                    Finding(num, laterality, self.lookup, locs, depths)
                )
            else:
                assert laterality in [Laterality.LEFT, Laterality.RIGHT]
                self.findings[laterality.value].append(
                    Finding(num, laterality, self.lookup, locs, depths)
                )

    def _get_view_pos(
        self, row: pd.Series
    ) -> Literal[ViewPosition.CC, ViewPosition.MLO]:
        view: ViewPosition = ViewPosition(row["ViewPosition"])
        if view not in [ViewPosition.CC, ViewPosition.MLO]:
            raise ValueError(f"Invalid view position: '{view}'")
        return cast(Literal[ViewPosition.CC, ViewPosition.MLO], view)

    def _get_laterality(
        self, row: pd.Series
    ) -> Literal[Laterality.LEFT, Laterality.RIGHT]:
        laterality: Laterality = Laterality(row["ImageLateralityFinal"])
        if laterality in [Laterality.UNKNOWN, Laterality.BILATERAL]:
            raise ValueError(f"Invalid image laterality: '{laterality}'")
        return cast(Literal[Laterality.LEFT, Laterality.RIGHT], laterality)

    def _register_images(self, data: pd.DataFrame) -> None:
        for _, row in data.iterrows():
            dicom_path: str = str(row["anon_dicom_path"])
            view: Literal[ViewPosition.CC, ViewPosition.MLO] = self._get_view_pos(row)
            laterality: Literal[Laterality.LEFT, Laterality.RIGHT] = (
                self._get_laterality(row)
            )

            # parse image dims
            height: int = int(row.Rows)
            width: int = int(row.Columns)

            # parse image attributes
            orientation: PatientOrientation = PatientOrientation(row.PatientOrientation)

            # get the image alignment from the orientation
            alignment: Alignment = orientation.alignment(laterality, view)

            # extract coords and parse them to the correct formats
            roi_coords: list[list[float]] = ast.literal_eval(str(row["ROI_coords"]))
            nipple_coords: tuple[int, int] = (int(row.nipple_x), int(row.nipple_y))
            pnl_slope: float = float(row["pnl_slope"])

            self.images[laterality.value].append(
                Image(
                    dicom_path=dicom_path,
                    view=view,
                    laterality=laterality,
                    height=height,
                    width=width,
                    alignment=alignment,
                    roi_coords=roi_coords,
                    nipple_coords=nipple_coords,
                    div_slope=pnl_slope,
                )
            )

    def _link_findings(self) -> None:
        sides: list[Literal["L", "R"]] = ["L", "R"]
        for side in sides:
            side_findings: list[Finding] = self.findings[side]

            for image in self.images[side]:
                image.register_findings(side_findings)

    def match(self) -> list[dict[str, Union[str, list[int]]]]:
        output_list: list[dict[str, Union[str, list[int]]]] = []

        # iterate over left/right sides
        for side_images in self.images.values():
            # iterate over images on either side
            for image in side_images:
                # iterate over rois for each image
                for roi in image.rois:
                    # for each roi, evaluate the best match
                    roi.evaluate_match()

                # export the matches for the image, and add them to the output list for the exam
                image_output: dict[str, Union[str, list[int]]] = image.export_matches()
                output_list.append(image_output)

        return output_list
