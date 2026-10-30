"""Small physics tests that say whether the MuJoCo set-up can be trusted at all: a dropped object falls the way gravity says, the same simulation run twice gives the same numbers, and a vial dropped on a station's pad comes to rest on it."""
from __future__ import annotations

import math

import mujoco
import numpy as np

from .scene import VIAL_HEIGHT_M, load_cell, spots, surface_z

GRAVITY = 9.81
FALL_XML = """<mujoco><option timestep="0.001" gravity="0 0 -9.81"/><worldbody>
<body name="ball" pos="0 0 1.0"><freejoint/><geom type="sphere" size="0.02" mass="0.1"/></body></worldbody></mujoco>"""


def free_fall(seconds: float = 0.4) -> tuple[float, float]:
    """(how far a ball dropped in empty space fell in MuJoCo, how far gravity says it should: g t squared over two)."""
    model = mujoco.MjModel.from_xml_string(FALL_XML)
    data = mujoco.MjData(model)
    for _ in range(int(round(seconds / model.opt.timestep))):
        mujoco.mj_step(model, data)
    return 1.0 - float(data.qpos[2]), 0.5 * GRAVITY * seconds ** 2


def settle_vial(layout: dict, seconds: float = 1.5) -> dict:
    """Drop a vial 3 cm above the first station's pad, run the physics, and report where it ends up: its height against the pad top, how far it slid, and how much it is tilted."""
    cell = load_cell(layout, with_vial=True)
    first = spots(layout)[0]
    x, y, z = first["xyz"]
    pad_top = surface_z(first)
    address = cell.joint_address("vial_free")
    for _ in range(int(round(seconds / cell.model.opt.timestep))):
        mujoco.mj_step(cell.model, cell.data)
    position = cell.data.qpos[address:address + 3]
    w, qx, qy, qz = cell.data.qpos[address + 3:address + 7]
    tilt_deg = math.degrees(2 * math.asin(min(1.0, math.hypot(qx, qy))))
    return {"rest_height_m": float(position[2]), "expected_height_m": pad_top + VIAL_HEIGHT_M / 2, "slide_m": float(math.hypot(position[0] - x, position[1] - y)), "tilt_deg": tilt_deg}


def repeatable(layout: dict, seconds: float = 0.5) -> bool:
    """The same scene, started the same way and run twice, ends in exactly the same state."""
    ends = []
    for _ in range(2):
        cell = load_cell(layout, with_vial=True)
        cell.set_arm(0.4, 0.5, -1.2)
        for _ in range(int(round(seconds / cell.model.opt.timestep))):
            mujoco.mj_step(cell.model, cell.data)
        ends.append(np.array(cell.data.qpos))
    return bool(np.array_equal(ends[0], ends[1]))
