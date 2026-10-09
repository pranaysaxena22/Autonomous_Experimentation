"""Layout rules shared by the setup app and the format check: how far the arm reaches, and what the layout can measure.

Reach policy (decision): a layout fails if any spot has less than 0.03 m of spare reach, warns below 0.10 m, and is
otherwise fine. Reach is worked out in 3D from the shoulder, at each spot's working height and at the safe height.
"""
from __future__ import annotations

import math

REACH_WARN_M = 0.10
REACH_FAIL_M = 0.03


def reach_policy(spare_m: float) -> str:
    """'pass' at 0.10 m of spare reach or more, 'warn' from 0.03 m up to (not including) 0.10 m, 'fail' below 0.03 m."""
    return "fail" if spare_m < REACH_FAIL_M else ("warn" if spare_m < REACH_WARN_M else "pass")


def reach_report(layout: dict) -> tuple[float, str, list[str]]:
    """(tightest spare reach in metres, where that is, any spots that are out of reach)."""
    robot = layout["robot"]
    arm = robot["links_m"]["upper_arm"] + robot["links_m"]["forearm"]
    spots = ([(s["id"], s["position"]["radius_m"], s["work_height_m"]) for s in layout["stations"]]
             + [(s["id"], s["position"]["radius_m"], s["work_height_m"]) for s in layout["bottle_shelf"]["slots"]]
             + [(h["id"], h["position"]["radius_m"], h["work_height_m"]) for h in layout["tool_holders"]])
    worst, where, out_of_reach = 1e9, "", []
    for name, radius, height in spots:
        for label, h in (("working height", height), ("safe height", robot["safe_height_m"])):
            distance = math.hypot(radius, h + robot["links_m"]["wrist_to_tip"] - robot["shoulder_height_m"])
            spare = arm - distance
            if spare < worst:
                worst, where = spare, f"{name} at {label} (distance {distance:.3f} m of {arm:.2f} m)"
            if spare < 0:
                out_of_reach.append(f"{name} at {label} is {-spare:.3f} m beyond the arm's reach")
    return worst, where, out_of_reach


def station_ids(layout: dict) -> list[str]:
    """Everything a step can use: the stations, plus the bottle shelf."""
    return [s["id"] for s in layout["stations"]] + [layout["bottle_shelf"]["id"]]


def measurable(layout: dict) -> set[str]:
    """The quantities some station in the layout can read (the barcode is not a result)."""
    return {s["instrument"]["reads"] for s in layout["stations"] if "instrument" in s and s["instrument"]["reads"] != "barcode"}
