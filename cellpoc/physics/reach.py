"""Can the arm reach every place in the layout? Asked of MuJoCo instead of a formula.

For each station, bottle slot and tool holder, at the working height and at the safe height, the arm is moved by a numerical inverse-kinematics solver (damped least squares on the wrist, using MuJoCo's own Jacobian) until the tool tip is
where the layout says it must be. The answer is a pose of the joints, how close the tip got, how much the elbow is bent and what, if anything, the arm touches there. The "spare reach" is measured on the MuJoCo model itself (the arm
stretched straight, minus the distance to the target), which is an independent number from the formula the setup rules use; the check compares the two.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import mujoco
import numpy as np

from .scene import ARM_JOINTS, ELBOW_RANGE, SHOULDER_RANGE, Cell, spots

TOLERANCE_M = 1e-4          # the tool tip must land within a tenth of a millimetre
MAX_ITERATIONS = 300
DAMPING = 0.02


@dataclass
class Solution:
    """What the solver found for one target."""
    reached: bool
    error_m: float
    pose: list[float]
    iterations: int
    elbow_bend_deg: float
    contacts: list[tuple[str, str]] = field(default_factory=list)


def stretched_length(cell: Cell) -> float:
    """How far the wrist is from the shoulder with the elbow straight, measured on the MuJoCo model (it should equal upper arm + forearm)."""
    cell.set_arm(0.0, 0.0, 0.0)
    return float(np.linalg.norm(cell.site("wrist_site") - np.array([0.0, 0.0, cell.layout["robot"]["shoulder_height_m"]])))


def spare_reach(cell: Cell, tip_target: tuple[float, float, float]) -> float:
    """Spare reach for a tool-tip target: the arm's stretched length minus the distance from the shoulder to where the wrist has to be (the tool hangs straight down, so the wrist is the tool's length above the tip)."""
    l3 = cell.layout["robot"]["links_m"]["wrist_to_tip"]
    wrist = np.array([tip_target[0], tip_target[1], tip_target[2] + l3])
    shoulder = np.array([0.0, 0.0, cell.layout["robot"]["shoulder_height_m"]])
    return stretched_length(cell) - float(np.linalg.norm(wrist - shoulder))


def solve(cell: Cell, tip_target: tuple[float, float, float], start: list[float] | None = None) -> Solution:
    """Move the arm so the tool tip is at the target, the tool hanging straight down. Three joints (turn, shoulder, elbow) place the wrist; the wrist joint is then set to keep the tool vertical."""
    model, data = cell.model, cell.data
    l3 = cell.layout["robot"]["links_m"]["wrist_to_tip"]
    wrist_target = np.array([tip_target[0], tip_target[1], tip_target[2] + l3])
    yaw = math.atan2(tip_target[1], tip_target[0])
    shoulder_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "wrist_site")
    addresses = [cell.joint_address(n) for n in ARM_JOINTS[:3]]
    dofs = [int(model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n)]) for n in ARM_JOINTS[:3]]
    q = np.array([yaw, 0.3, -1.0]) if start is None else np.array([yaw, start[1], start[2]])          # the usual elbow-up bend, or the pose just before (so a path stays smooth); always facing the target
    lower = np.array([-math.pi, SHOULDER_RANGE[0], ELBOW_RANGE[0]])
    upper = np.array([math.pi, SHOULDER_RANGE[1], ELBOW_RANGE[1]])
    jacobian = np.zeros((3, model.nv))
    error = float("inf")
    used = 0
    for used in range(1, MAX_ITERATIONS + 1):
        cell.set_arm(q[0], q[1], q[2])
        error_vector = wrist_target - data.site_xpos[shoulder_id]
        error = float(np.linalg.norm(error_vector))
        if error < TOLERANCE_M:
            break
        mujoco.mj_jacSite(model, data, jacobian, None, shoulder_id)
        j = jacobian[:, dofs]
        step = j.T @ np.linalg.solve(j @ j.T + (DAMPING ** 2) * np.eye(3), error_vector)
        q = np.clip(q + np.clip(step, -0.3, 0.3), lower, upper)
    cell.set_arm(q[0], q[1], q[2])
    tip_error = float(np.linalg.norm(cell.site("tip") - np.array(tip_target)))
    contacts = cell.arm_contacts()
    reached = tip_error < TOLERANCE_M * 5
    return Solution(reached, tip_error, [float(x) for x in cell.arm_pose()], used, math.degrees(-q[2]), contacts)


@dataclass
class SpotReport:
    spot: str
    kind: str
    level: str                      # "working height" or "safe height"
    solution: Solution
    spare_m: float                  # measured on the MuJoCo model


def reach_all(cell: Cell) -> list[SpotReport]:
    """Every spot at its working height and at the safe height, solved and measured."""
    safe = cell.layout["robot"]["safe_height_m"]
    out = []
    for spot in spots(cell.layout):
        x, y, z = spot["xyz"]
        for level, height in (("working height", z), ("safe height", safe)):
            target = (x, y, height)
            out.append(SpotReport(spot["id"], spot["kind"], level, solve(cell, target), spare_reach(cell, target)))
    return out


def tightest(reports: list[SpotReport]) -> SpotReport:
    return min(reports, key=lambda r: r.spare_m)
