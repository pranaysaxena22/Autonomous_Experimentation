"""Builds a MuJoCo scene of the cell from the layout file, and nothing else: the same numbers the 3D replay and the setup rules use (arm link lengths, shoulder height, table, stations, bottle slots, tool holders).

The scene is written as MJCF text (MuJoCo's own file format), so the same text can be opened in MuJoCo's viewer. Nothing in it is typed in by hand except how things look: the instruments, the beaker, the bottles and the arm are
drawn with the same shapes and proportions as the 3D replay, so the two views of the cell look like the same cell. The arm is the layout's generic three-segment arm: it turns on its base (yaw), then the shoulder, the elbow and the wrist
bend in one vertical plane; the tool hangs straight down from the wrist, with two fingers either side of the tool tip, exactly as the 3D replay draws it.
Directions follow the replay: angle 0 is to the right and angles go counter-clockwise seen from above, the arm's base is at the centre of the table, heights are metres above the floor. A station's working height is the height of the
surface things stand on (2 cm above the pedestal's top); a bottle is centred on it.

What can be touched: the table, the pedestals, the instruments' solid parts, the column and the arm's links and tool. What is only drawn: glass, liquid, the objects that move, the reading screens and the highlight ring.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from xml.sax.saxutils import quoteattr

import mujoco

ARM_JOINTS = ("yaw", "shoulder", "elbow", "wrist")
PAD_CLEARANCE_M = 0.02      # the top of the pedestal a station or tool holder stands on is this far under its working height, so the tool tip never touches it
SLOT_CLEARANCE_M = 0.08     # a bottle is centred on its slot's working height and stands on a pad this far below
ELBOW_RANGE = (-2.9, 0.0)   # the elbow only bends one way (forearm down relative to the upper arm), as in the replay
SHOULDER_RANGE = (-1.6, 2.4)    # the home pose (high and close in) needs the upper arm raised past vertical
WRIST_RANGE = (-3.1, 3.1)
FINGER_OPEN_M, FINGER_CLOSED_M = 0.098, 0.048          # half the gap between the two fingers, open and closed (as in the replay)
VIAL_RADIUS_M, VIAL_HEIGHT_M = 0.015, 0.05             # the small loose vial of the settle test
GRIP_M = {"vial": 0.17, "tablet": 0.03, "bottle": 0.0, "rod": 0.33, "tool": 0.175}       # how far above an object's origin the tool tip holds it (as in the replay)
BOTTLE_COLOURS = ["0.0 0.45 0.9 1", "0.95 0.8 0.1 1", "0.3 0.75 0.2 1", "0.95 0.5 0.1 1", "0.55 0.25 0.8 1", "0.91 0.64 0.09 1", "0.85 0.16 0.11 1"]     # the five ingredient bottles are blue, yellow, green, orange, purple: the stock solutions the cell's vision check tells apart (cellpoc/vision/config.py)
HIDDEN_Z = -2.0             # an object that does not exist yet (the tablet before it is pressed) waits under the floor
FLOW_PARTICLES = 12
SILVER, BLACK, WHITE = "0.79 0.80 0.82 1", "0.08 0.09 0.10 1", "0.95 0.96 0.96 1"
GLASS, LIQUID = "0.81 0.89 0.93 0.35", "0.62 0.84 0.94 0.40"


def polar(position: dict, height: float) -> tuple[float, float, float]:
    """(x, y, z) of a layout spot: x to the right, y away, z up (the replay's y-up picture turned to MuJoCo's z-up)."""
    angle = math.radians(position["angle_deg"])
    return position["radius_m"] * math.cos(angle), position["radius_m"] * math.sin(angle), height


def spots(layout: dict) -> list[dict]:
    """Every place the arm must reach: stations, bottle slots and tool holders, each with its position and working height."""
    out = [{"id": s["id"], "kind": "station", "type": s["type"], "label": s["label"], "angle_deg": s["position"]["angle_deg"], "xyz": polar(s["position"], s["work_height_m"]), "radius_m": s["position"]["radius_m"], "height_m": s["work_height_m"]} for s in layout["stations"]]
    out += [{"id": s["id"], "kind": "bottle slot", "type": "slot", "label": s["ingredient_id"].replace("_pct", ""), "angle_deg": s["position"]["angle_deg"], "xyz": polar(s["position"], s["work_height_m"]), "radius_m": s["position"]["radius_m"], "height_m": s["work_height_m"]} for s in layout["bottle_shelf"]["slots"]]
    out += [{"id": h["id"], "kind": "tool holder", "type": "holder", "label": h["tool"], "angle_deg": h["position"]["angle_deg"], "xyz": polar(h["position"], h["work_height_m"]), "radius_m": h["position"]["radius_m"], "height_m": h["work_height_m"]} for h in layout["tool_holders"]]
    return out


def surface_z(spot: dict) -> float:
    """The height of the top of what stands under a place (the pedestal, or the slot's pad)."""
    return spot["height_m"] - (SLOT_CLEARANCE_M if spot["kind"] == "bottle slot" else PAD_CLEARANCE_M)


def grip_height(layout_object: dict) -> float:
    """How far above its origin the tool tip holds an object (a vial 17 cm up, a bottle at its middle ...)."""
    if layout_object["type"] == "tool":
        return GRIP_M["rod"] if layout_object["id"] == "rod" else GRIP_M["tool"]
    return GRIP_M.get(layout_object["type"], 0.0)


def object_size(layout_object: dict) -> tuple[float, float]:
    """(radius, height) in metres of a layout object as drawn."""
    return {"vial": (0.043, 0.23), "tablet": (0.05, 0.03), "bottle": (0.045, 0.29)}.get(layout_object["type"], (0.009, 0.34) if layout_object["id"] == "rod" else (0.05, 0.19))


def rest_position(layout: dict, layout_object: dict) -> tuple[float, float, float]:
    """Where an object's origin is when it stands at a place: a bottle's middle on the working height, anything else's base on the pedestal."""
    where = {s["id"]: s for s in spots(layout)}.get(layout_object.get("starts_at"))
    if where is None:
        return 0.0, 0.0, HIDDEN_Z
    x, y, _ = where["xyz"]
    return x, y, where["height_m"] if layout_object["type"] == "bottle" else surface_z(where)


def _object_xml(layout: dict, o: dict, index: int) -> str:
    """One moving object as a body with its parts, drawn like the replay's (the body's origin is where rest_position puts it)."""
    name = quoteattr("obj_" + o["id"])
    x, y, z = rest_position(layout, o)
    g = lambda body: f'<body name={name} mocap="true" pos="{x:.4f} {y:.4f} {z:.4f}">{body}</body>'
    flat = 'contype="0" conaffinity="0"'
    if o["type"] == "vial":
        return g(f'<geom type="cylinder" size="0.04 0.1" pos="0 0 0.1" rgba="{GLASS}" {flat}/><geom type="cylinder" size="0.043 0.015" pos="0 0 0.215" rgba="{BLACK}" {flat}/>'
                 f'<geom name="powder" type="cylinder" size="0.036 0.0005" pos="0 0 0.0035" rgba="0.98 0.98 0.98 1" {flat}/>')
    if o["type"] == "tablet":
        return g(f'<geom type="cylinder" size="0.05 0.015" pos="0 0 0.015" rgba="0.98 0.97 0.93 1" {flat}/>')
    if o["type"] == "bottle":
        colour = BOTTLE_COLOURS[index % len(BOTTLE_COLOURS)]
        return g(f'<geom type="cylinder" size="0.045 0.075" pos="0 0 0" rgba="{colour}" {flat}/><geom type="cylinder" size="0.026 0.02" pos="0 0 0.095" rgba="{colour}" {flat}/>'
                 f'<geom type="cylinder" size="0.027 0.015" pos="0 0 0.13" rgba="{WHITE}" {flat}/>')
    if o["id"] == "rod":
        return g(f'<geom type="cylinder" size="0.009 0.16" pos="0 0 0.16" rgba="{SILVER}" {flat}/><geom type="cylinder" size="0.022 0.02" pos="0 0 0.34" rgba="0.05 0.51 0.56 1" {flat}/>')
    return g(f'<geom type="cylinder" size="0.036 0.08" pos="0 0 0.08" rgba="{SILVER}" {flat}/><geom type="cylinder" size="0.05 0.015" pos="0 0 0.175" rgba="0.0 0.33 0.53 1" {flat}/>')


def _station_xml(s: dict, table_h: float) -> str:
    """A station: its pedestal and instrument, in the station's own frame (x outward from the arm, y sideways, z up from the table), drawn as the replay draws it."""
    top = s["height_m"] - table_h                              # working height above the table top
    ped = max(0.02, top - PAD_CLEARANCE_M)
    x, y, _ = s["xyz"]
    kind, sid = s["type"], s["id"]
    parts = [f'<geom name={quoteattr("pad_" + sid)} type="cylinder" size="0.17 {ped / 2:.4f}" pos="0 0 {ped / 2:.4f}" rgba="{SILVER}"/>']
    flat = 'contype="0" conaffinity="0"'
    box = lambda name, half, pos, rgba, solid=True: f'<geom {"name=" + quoteattr(name) + " " if name else ""}type="box" size="{half[0]:.4f} {half[1]:.4f} {half[2]:.4f}" pos="{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f}" rgba="{rgba}" {"" if solid else flat}/>'
    cyl = lambda half_r, half_h, pos, rgba, extra="": f'<geom type="cylinder" size="{half_r} {half_h}" pos="{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f}" rgba="{rgba}" {flat} {extra}/>'
    if kind == "vial_rack_with_scanner":
        parts.append(box(f"base_{sid}", (0.11, 0.31, 0.025), (0.34, 0, 0.025), SILVER))
        parts += [cyl(0.04, 0.1, (0.34, 0.24 - j * 0.12, 0.15), GLASS) for j in range(5)]
        parts.append(box("", (0.025, 0.03, (top + 0.0) / 2), (-0.02, -0.27, top / 2), "0.23 0.24 0.25 1", False))                # the scanner's stand
        parts.append(box(f"scanner_{sid}", (0.05, 0.05, 0.07), (-0.02, -0.27, top + 0.07), BLACK))
        parts.append(box("", (0.012, 0.03, 0.012), (-0.075, -0.27, top + 0.07), "0.85 0.16 0.11 1", False))          # the scanner's red window
    if kind in ("balance", "hardness_gauge", "friability_tester", "dissolution_vessel"):
        parts.append(box(f"display_{sid}", (0.025, 0.13, 0.08), (-0.2, 0, top + 0.08), BLACK))
        parts.append(box("", (0.03, 0.05, top / 2), (-0.2, 0, top / 2), "0.23 0.24 0.25 1", False))                        # the stand the instrument's box sits on
        parts.append(box("", (0.002, 0.12, 0.045), (-0.226, 0, top + 0.09), "0.06 0.07 0.07 1", False))                 # the reading screen
        parts.append(box("", (0.0025, 0.12, 0.004), (-0.227, 0, top + 0.135), "0.53 0.74 0.15 1", False))                # its green edge
    if kind == "balance":
        parts.append(cyl(0.1, 0.008, (0, 0, top + 0.004), SILVER, 'material="metal"'))                                   # the weighing pan
    if kind == "hand_press":
        parts.append(cyl(0.085, 0.02, (0, 0, top + 0.02), SILVER))
        parts.append(box(f"post_{sid}", (0.025, 0.025, 0.17), (0.14, 0, top + 0.17), SILVER))
        parts.append(box("", (0.09, 0.03, 0.02), (0.065, 0, top + 0.35), SILVER, False))
        parts.append(cyl(0.012, 0.05, (0, 0, top + 0.31), BLACK))
    if kind == "friability_tester":
        parts.append(box("", (0.07, 0.07, 0.03), (0, 0, top + 0.03), SILVER, False))
        parts.append(f'<geom type="cylinder" size="0.09 0.035" pos="0 0 {top + 0.1:.4f}" euler="1.5708 0 0" rgba="0.81 0.91 0.95 0.55" {flat}/>')
    if kind == "dissolution_vessel":
        parts.append(cyl(0.14, 0.015, (0, 0, top + 0.015), BLACK))
        parts.append(cyl(0.108, 0.15, (0, 0, top + 0.15), GLASS))
        parts.append(cyl(0.105, 0.11, (0, 0, top + 0.12), LIQUID))
        parts.append(cyl(0.118, 0.004, (0, 0, top + 0.3), SILVER))
    if kind == "discard_bin":
        parts.append(box("", (0.15, 0.15, 0.01), (0, 0, top + 0.01), "0.23 0.24 0.25 1", False))
        for dx, dy, hx, hy in ((0, 0.14, 0.15, 0.01), (0, -0.14, 0.15, 0.01), (0.14, 0, 0.01, 0.15), (-0.14, 0, 0.01, 0.15)):
            parts.append(box("", (hx, hy, 0.1), (dx, dy, top + 0.11), "0.23 0.24 0.25 1", False))
    angle = math.radians(s["angle_deg"])
    return f'    <body name={quoteattr("station_" + sid)} pos="{x:.4f} {y:.4f} {table_h}" euler="0 0 {angle:.5f}">' + "".join(parts) + "</body>"


def build_mjcf(layout: dict, with_vial: bool = False, with_objects: bool = False) -> str:
    """The cell as MJCF text. With a vial, one loose vial is added just above the first station's pedestal (for the settle test); with objects, every object in the layout, the highlight ring, the powder stream and the scanner's beam."""
    robot, table = layout["robot"], layout["table"]
    l1, l2, l3 = robot["links_m"]["upper_arm"], robot["links_m"]["forearm"], robot["links_m"]["wrist_to_tip"]
    shoulder_z, table_h, table_r = robot["shoulder_height_m"], table["height_m"], table["radius_m"]
    all_spots = spots(layout)
    parts: list[str] = []
    add = parts.append
    add('<mujoco model="cell">')
    add('  <compiler angle="radian" autolimits="true"/>')
    add('  <option timestep="0.002" gravity="0 0 -9.81"/>')
    add('  <visual><global offwidth="1920" offheight="1080"/><quality shadowsize="4096" offsamples="8"/><headlight ambient="0.38 0.38 0.38" diffuse="0.45 0.45 0.45" specular="0.1 0.1 0.1"/><map znear="0.02"/></visual>')
    add('  <asset>')
    add('    <texture type="skybox" builtin="gradient" rgb1="0.24 0.25 0.27" rgb2="0.03 0.03 0.04" width="512" height="512"/>')
    add('    <material name="floor" rgba="0.15 0.16 0.17 1" reflectance="0.15"/><material name="metal" rgba="0.79 0.80 0.82 1" specular="0.6" shininess="0.6"/>')
    add('  </asset>')
    add('  <worldbody>')
    add('    <light pos="2.5 -2.5 5" dir="-0.4 0.4 -1" diffuse="0.75 0.75 0.75" specular="0.25 0.25 0.25" castshadow="true"/>')
    add('    <light pos="-3 2 3" dir="0.6 -0.3 -0.7" diffuse="0.25 0.25 0.28" castshadow="false"/>')
    add('    <geom name="floor" type="plane" size="8 8 0.1" material="floor"/>')
    # the table: a collision cylinder you cannot see, with the drawn table (a dark stand, a white top, a green edge) on it
    add(f'    <geom name="table" type="cylinder" size="{table_r} {table_h / 2:.4f}" pos="0 0 {table_h / 2:.4f}" rgba="0 0 0 0"/>')
    add(f'    <geom type="cylinder" size="{table_r * 0.86:.3f} {(table_h - 0.06) / 2:.4f}" pos="0 0 {(table_h - 0.06) / 2:.4f}" rgba="0.17 0.18 0.19 1" contype="0" conaffinity="0"/>')
    add(f'    <geom type="cylinder" size="{table_r} 0.03" pos="0 0 {table_h - 0.03:.4f}" rgba="0.53 0.74 0.15 1" contype="0" conaffinity="0"/>')
    add(f'    <geom type="cylinder" size="{table_r - 0.045:.3f} 0.0305" pos="0 0 {table_h - 0.0295:.4f}" rgba="0.27 0.28 0.31 1" contype="0" conaffinity="0" material="metal"/>')
    # the arm's base and column
    add(f'    <geom type="cylinder" size="0.26 0.05" pos="0 0 {table_h + 0.05}" rgba="0.17 0.18 0.19 1" contype="0" conaffinity="0"/>')
    column_half = (shoulder_z - 0.07 - table_h) / 2          # the column stops just under the shoulder joint, so the upper arm does not sit inside it
    add(f'    <geom name="column" type="cylinder" size="0.2 {column_half:.4f}" pos="0 0 {table_h + column_half:.4f}" rgba="0.95 0.96 0.96 1" material="metal"/>')
    for spot in all_spots:
        x, y, z = spot["xyz"]
        add(f'    <site name={quoteattr("spot_" + spot["id"])} pos="{x:.4f} {y:.4f} {z:.4f}" size="0.012" rgba="0.53 0.92 0.13 0.9"/>')
        if spot["kind"] == "station":
            add(_station_xml(spot, table_h))
        elif spot["kind"] == "bottle slot":
            add(f'    <geom name={quoteattr("pad_" + spot["id"])} type="cylinder" size="0.06 0.01" pos="{x:.4f} {y:.4f} {surface_z(spot) - 0.01:.4f}" rgba="0.23 0.24 0.25 1"/>')
        else:
            add(f'    <geom name={quoteattr("pad_" + spot["id"])} type="cylinder" size="0.055 0.015" pos="{x:.4f} {y:.4f} {surface_z(spot) - 0.015:.4f}" rgba="0.23 0.24 0.25 1"/>')
    # the arm
    add(f'    <body name="shoulder_base" pos="0 0 {shoulder_z}">')
    add('      <joint name="yaw" type="hinge" axis="0 0 1" range="-3.1416 3.1416"/>')
    add('      <geom type="cylinder" size="0.1 0.09" euler="1.5708 0 0" rgba="0.17 0.18 0.19 1" contype="0" conaffinity="0"/>')
    add('      <body name="upper_arm">')
    add(f'        <joint name="shoulder" type="hinge" axis="0 -1 0" range="{SHOULDER_RANGE[0]} {SHOULDER_RANGE[1]}"/>')
    add(f'        <geom name="upper_arm" type="capsule" fromto="0 0 0 {l1} 0 0" size="0.058" rgba="0.95 0.96 0.96 1" material="metal"/>')
    add('        <geom type="cylinder" size="0.066 0.02" pos="0.14 0 0" euler="0 1.5708 0" rgba="0.53 0.74 0.15 1" contype="0" conaffinity="0"/>')
    add(f'        <body name="forearm" pos="{l1} 0 0">')
    add(f'          <joint name="elbow" type="hinge" axis="0 -1 0" range="{ELBOW_RANGE[0]} {ELBOW_RANGE[1]}"/>')
    add('          <geom type="sphere" size="0.08" rgba="0.17 0.18 0.19 1" contype="0" conaffinity="0"/>')
    add(f'          <geom name="forearm" type="capsule" fromto="0 0 0 {l2} 0 0" size="0.046" rgba="0.95 0.96 0.96 1" material="metal"/>')
    add(f'          <body name="wrist" pos="{l2} 0 0">')
    add(f'            <joint name="wrist" type="hinge" axis="0 -1 0" range="{WRIST_RANGE[0]} {WRIST_RANGE[1]}"/>')
    add('            <site name="wrist_site" size="0.01" rgba="0.53 0.92 0.13 0"/>')
    add('            <geom type="sphere" size="0.058" rgba="0.17 0.18 0.19 1" contype="0" conaffinity="0"/>')
    add('            <geom type="box" size="0.04 0.07 0.05" pos="0.06 0 0" rgba="0.17 0.18 0.19 1" contype="0" conaffinity="0"/>')
    add(f'            <geom name="tool" type="capsule" fromto="0 0 0 {l3} 0 0" size="0.014" rgba="0 0 0 0"/>')
    add(f'            <body name="finger_left" pos="0.12 {FINGER_OPEN_M} 0"><joint name="finger_left" type="slide" axis="0 1 0" range="{FINGER_CLOSED_M - FINGER_OPEN_M} 0"/>'
        '<geom type="box" size="0.075 0.009 0.011" rgba="0.95 0.96 0.96 1" contype="0" conaffinity="0"/></body>')
    add(f'            <body name="finger_right" pos="0.12 {-FINGER_OPEN_M} 0"><joint name="finger_right" type="slide" axis="0 1 0" range="0 {FINGER_OPEN_M - FINGER_CLOSED_M}"/>'
        '<geom type="box" size="0.075 0.009 0.011" rgba="0.95 0.96 0.96 1" contype="0" conaffinity="0"/></body>')
    add(f'            <site name="tip" pos="{l3} 0 0" size="0.01" rgba="0.53 0.92 0.13 0"/>')
    add('          </body>')
    add('        </body>')
    add('      </body>')
    add('    </body>')
    if with_vial:
        first = all_spots[0]
        x, y, _ = first["xyz"]
        add(f'    <body name="vial" pos="{x:.4f} {y:.4f} {surface_z(first) + VIAL_HEIGHT_M / 2 + 0.03:.4f}">')
        add('      <freejoint name="vial_free"/>')
        add(f'      <geom name="vial" type="cylinder" size="{VIAL_RADIUS_M} {VIAL_HEIGHT_M / 2}" mass="0.02" rgba="0.53 0.92 0.13 0.8" friction="0.8 0.005 0.0001"/>')
        add('    </body>')
    if with_objects:                                  # every object in the layout, as a body the playback moves (no collisions: they only follow the plan)
        bottles = 0
        for o in layout["objects"]:
            add("    " + _object_xml(layout, o, bottles))
            bottles += 1 if o["type"] == "bottle" else 0
        add(f'    <body name="ring" mocap="true" pos="0 0 {HIDDEN_Z}"><geom type="cylinder" size="0.21 0.0015" rgba="0.53 0.74 0.15 0.55" contype="0" conaffinity="0"/></body>')
        add(f'    <body name="beam" mocap="true" pos="0 0 {HIDDEN_Z}"><geom name="beam" type="cylinder" size="0.003 0.1" rgba="1 0.16 0.1 1" contype="0" conaffinity="0"/></body>')
        for i in range(FLOW_PARTICLES):
            add(f'    <body name="flow{i}" mocap="true" pos="0 0 {HIDDEN_Z}"><geom type="sphere" size="0.0115" rgba="1 1 1 1" contype="0" conaffinity="0"/></body>')
    add('  </worldbody>')
    add('  <contact><exclude body1="upper_arm" body2="wrist"/></contact>')
    add('</mujoco>')
    return "\n".join(parts)


@dataclass
class Cell:
    """A loaded scene: the layout, the MuJoCo model and its data, with the arm's joint addresses looked up by name."""
    layout: dict
    model: mujoco.MjModel
    data: mujoco.MjData
    mjcf: str

    def joint_address(self, name: str) -> int:
        return int(self.model.jnt_qposadr[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)])

    def site(self, name: str):
        return self.data.site_xpos[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, name)].copy()

    def set_arm(self, yaw: float, shoulder: float, elbow: float, wrist: float | None = None, fingers: float = 1.0) -> None:
        """Put the arm in a pose and update everything that follows from it. The wrist, if not given, is turned so the tool hangs straight down; fingers is 1 for open and 0 for closed."""
        if wrist is None:
            wrist = -math.pi / 2 - (shoulder + elbow)
        for name, value in zip(ARM_JOINTS, (yaw, shoulder, elbow, wrist)):
            self.data.qpos[self.joint_address(name)] = value
        gap = FINGER_CLOSED_M + (FINGER_OPEN_M - FINGER_CLOSED_M) * fingers
        self.data.qpos[self.joint_address("finger_left")] = gap - FINGER_OPEN_M
        self.data.qpos[self.joint_address("finger_right")] = FINGER_OPEN_M - gap
        mujoco.mj_forward(self.model, self.data)

    def arm_pose(self) -> list[float]:
        return [float(self.data.qpos[self.joint_address(n)]) for n in ARM_JOINTS]

    def arm_contacts(self) -> list[tuple[str, str]]:
        """The pairs of things touching right now, by name (the arm touching the table, a pedestal, the column ... is a collision)."""
        names = []
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            a = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, int(c.geom1)) or f"geom{int(c.geom1)}"
            b = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, int(c.geom2)) or f"geom{int(c.geom2)}"
            names.append((a, b))
        return names


def load_cell(layout: dict, with_vial: bool = False, with_objects: bool = False) -> Cell:
    """Build the scene from a layout and load it into MuJoCo. A layout MuJoCo cannot load is refused in words."""
    text = build_mjcf(layout, with_vial, with_objects)
    try:
        model = mujoco.MjModel.from_xml_string(text)
    except Exception as error:                      # MuJoCo reports its own XML errors; say which layout step failed
        raise ValueError(f"The cell scene could not be built from this layout ({str(error)[:200]}). Check the arm's link lengths, the table and the positions in the layout file.") from error
    return Cell(layout, model, mujoco.MjData(model), text)
