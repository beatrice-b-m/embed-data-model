import uuid
from typing import Optional, Literal
from quadrants import QuadrantLookup, QuadrantCode
from hiti_preproc.alignment import ViewPosition, Laterality


class Finding:
    def __init__(
        self,
        id: int,
        laterality: Laterality,
        lookup: QuadrantLookup,
        loc_codes: list[str] = [],
        depth_codes: list[str] = [],
    ):
        self.hash_id: str = uuid.uuid4().hex
        self.id: int = id
        self.laterality: Laterality = laterality

        self.lookup: QuadrantLookup = lookup

        self.loc_codes: list[str] = loc_codes
        self.depth_codes: list[str] = depth_codes

    def __repr__(self) -> str:
        return f"Finding({self.id}, side: {self.laterality.value}, locs: {self.loc_codes}, depths: {self.depth_codes})"

    def evaluate_quadrant(
        self,
        view: Literal[ViewPosition.CC, ViewPosition.MLO],
        laterality: Literal[Laterality.LEFT, Laterality.RIGHT],
    ) -> tuple[Optional[float], Optional[float]]:
        locs: list[float] = []
        depths: list[float] = []

        # iterate over location and depth codes and query the expected quadrant of the finding for that view type and side
        for loc_code in self.loc_codes:
            quadrant_code: Optional[QuadrantCode] = self.lookup.query_loc_code(
                loc_code, view.value, laterality.value
            )
            if quadrant_code is not None:
                if quadrant_code.loc is not None:
                    locs.append(quadrant_code.loc)
                if quadrant_code.depth is not None:
                    depths.append(quadrant_code.depth)

        for depth_code in self.depth_codes:
            quadrant_code: Optional[QuadrantCode] = self.lookup.query_depth_code(
                depth_code, view.value, laterality.value
            )
            if quadrant_code is not None:
                if quadrant_code.loc is not None:
                    locs.append(quadrant_code.loc)
                if quadrant_code.depth is not None:
                    depths.append(quadrant_code.depth)

        n_locs = len(locs)
        avg_loc: Optional[float] = None if n_locs < 1 else sum(locs) / n_locs

        n_depths = len(depths)
        avg_depth: Optional[float] = None if n_depths < 1 else sum(depths) / n_depths

        return avg_loc, avg_depth

    def __hash__(self) -> int:
        return hash(self.hash_id)
