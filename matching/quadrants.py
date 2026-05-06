from typing import Literal, Optional
import numpy as np
from dataclasses import dataclass, field


@dataclass
class Quadrant:
    name: str
    view: Literal["MLO", "CC", "Both"] = "Both"
    side: Literal["L", "R", "Both"] = "Both"
    loc: Optional[int] = None
    depth: Optional[int] = None
    lcodes: list[str] = field(default_factory=list)
    dcodes: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        out_string: str = (
            "Quadrant({name}{viewpos}{loc}{depth}{lcodes}{dcodes})".format(
                name=self.name,
                viewpos=(
                    ""
                    if (self.view == "Both") & (self.side == "Both")
                    else f", view: {'' if self.side == 'Both' else self.side}{'' if self.view == 'Both' else self.view}"
                ),
                loc="" if self.loc is None else f", l: {self.loc}",
                depth="" if self.depth is None else f", d: {self.depth}",
                lcodes=f", lcodes: {self.lcodes}",
                dcodes=f", dcodes: {self.dcodes}",
            )
        )
        return out_string


class QuadrantCode:
    def __init__(self, code: str):
        self.code: str = code

        # initialize internal lists
        self.quadrants: list[Quadrant] = []
        self.loc: Optional[float] = None
        self._locs: list[int] = []
        self.depth: Optional[float] = None
        self._depths: list[int] = []

    def register(self, quadrant: Quadrant):
        self.quadrants.append(quadrant)
        if quadrant.loc is not None:
            self._locs.append(quadrant.loc)
            self.loc = sum(self._locs) / len(self._locs)
        if quadrant.depth is not None:
            self._depths.append(quadrant.depth)
            self.depth = sum(self._depths) / len(self._depths)

    def __repr__(self) -> str:
        return f"QuadrantCode(code: {self.code}, quadrants: {[q.name for q in self.quadrants]}, loc: {self.loc}, depth: {self.depth})"


class QuadrantLookup:
    quadrants: list[Quadrant] = [
        # CC-Only Quadrants --------------------------------------------------
        Quadrant(
            name="lateral",
            view="CC",
            side="L",
            loc=1,
            lcodes=["OU", "L", "Y", "W", "1", "2", "3", "4", "5"],
        ),
        Quadrant(
            name="lateral",
            view="CC",
            side="R",
            loc=1,
            lcodes=["OU", "L", "Y", "W", "7", "8", "9", "10", "11"],
        ),
        Quadrant(name="central", view="CC", loc=0, lcodes=["C", "6", "12"]),
        Quadrant(
            name="medial",
            view="CC",
            side="L",
            loc=-1,
            lcodes=["IN", "D", "Z", "X", "7", "8", "9", "10", "11"],
        ),
        Quadrant(
            name="medial",
            view="CC",
            side="R",
            loc=-1,
            lcodes=["IN", "D", "Z", "X", "1", "2", "3", "4", "5"],
        ),
        # MLO-Only Quadrants -------------------------------------------------
        Quadrant(
            name="axillary_tail",
            view="MLO",
            loc=1,
            depth=2,
            lcodes=["A", "T"],
        ),
        Quadrant(
            name="superior",
            view="MLO",
            loc=1,
            lcodes=["UP", "U", "W", "X", "10", "11", "12", "1", "2"],
        ),
        Quadrant(name="central", view="MLO", loc=0, lcodes=["C", "3", "9"]),
        Quadrant(
            name="inferior",
            view="MLO",
            loc=-1,
            lcodes=["LO", "I", "Y", "Z", "4", "5", "6", "7", "8"],
        ),
        # All View Quadrants -------------------------------------------------
        Quadrant(name="subareolar", loc=0, depth=0, lcodes=["S"]),
        Quadrant(name="anterior", depth=0, lcodes=["AN"], dcodes=["A"]),
        Quadrant(name="middle", depth=1, lcodes=["MD"], dcodes=["M"]),
        Quadrant(name="posterior", depth=2, dcodes=["P"]),
    ]

    def __init__(self):
        # init dictionary for location codes
        self.ldict = {
            "CC": {"L": dict(), "R": dict()},
            "MLO": {"L": dict(), "R": dict()},
        }
        # init dictionary for depth codes
        self.ddict = {
            "CC": {"L": dict(), "R": dict()},
            "MLO": {"L": dict(), "R": dict()},
        }

        # iterate over all dicts and assign the relevant codes to each slice of both dicts
        for quadrant in self.quadrants:
            update_views: list[str] = (
                ["CC", "MLO"] if quadrant.view == "Both" else [quadrant.view]
            )
            update_sides: list[str] = (
                ["L", "R"] if quadrant.side == "Both" else [quadrant.side]
            )
            for view in update_views:
                for side in update_sides:
                    for lcode in quadrant.lcodes:
                        self.ldict[view][side].setdefault(
                            lcode, QuadrantCode(lcode)
                        ).register(quadrant)
                    for dcode in quadrant.dcodes:
                        self.ddict[view][side].setdefault(
                            dcode, QuadrantCode(dcode)
                        ).register(quadrant)

    def query_loc_code(
        self, code: str, view: Literal["CC", "MLO"], side: Literal["L", "R"]
    ) -> Optional[QuadrantCode]:
        # queries a location code from Magview to output the implied quadrant
        return self.ldict[view][side].get(code, None)

    def query_depth_code(
        self, code: str, view: Literal["CC", "MLO"], side: Literal["L", "R"]
    ) -> Optional[QuadrantCode]:
        # queries a depth code from Magview to output the implied depth region
        return self.ddict[view][side].get(code, None)
