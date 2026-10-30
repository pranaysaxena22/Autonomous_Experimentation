"""Plays one trial's executed timeline with the MuJoCo arm: where the arm goes for each action, what it carries, and what it does there.

This is a separate view of a run that already happened. It reads the executed timeline (the list of actions the executor recorded) and the layout, and turns each action into arm movements: lift, swing in close to the arm's column and
round to the place (so a carried vial or bottle never passes through an instrument), go down to the place, and do the action there (open and close the fingers, tilt a bottle so powder runs out, shake, press, stir, hold a vial to the scanner's beam).
A carried object hangs from the tool tip exactly as in the 3D replay; the vial fills as ingredients are poured in. At every frame MuJoCo's solver puts the arm in the pose that puts the tool tip there, and the arm is checked
against the table, the pedestals and the instruments. Nothing here changes the run: no time, result or trial count comes from this part.

Playback time is not run time. Moves and actions are shown at a watchable pace (about a second each) and a long wait is shown as a short pause with its real length in the caption. The simulated clock in the caption is the run's.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import mujoco
import numpy as np

from .reach import solve
from .scene import FLOW_PARTICLES, HIDDEN_Z, Cell, grip_height, rest_position, spots, surface_z

TIP_SPEED_M_S = 1.5         # how fast the tool tip travels between places in the playback
MIN_MOVE_S = 0.35
DWELL_S = {"pick": 0.5, "place": 0.5, "scan": 0.9, "read": 0.5, "wait": 0.6, "pour": 1.8, "shake": 1.4, "press": 1.2, "stir": 1.6}
TILT_POUR_DEG = 75.0
POUR_HEIGHT_M = 0.34        # the tool tip is this far above a station's working height while pouring or scanning (as in the replay)
SWING_RADIUS_M = 0.62       # a carried object swings round at this distance from the column, inside every instrument
SWING_MIN_DEGREES = 8.0     # a move shorter than this (neighbouring slots) goes straight across
HOME = "home"


class MotionError(Exception):
    """The playback cannot be made. The message says what, in plain words."""


@dataclass
class Frame:
    time_s: float                          # seconds into the playback
    pose: list[float]                      # yaw, shoulder, elbow, wrist
    fingers: float                         # 1 open, 0 closed
    tip: tuple[float, float, float]
    objects: dict                          # object id -> (x, y, z, tilt in radians about the horizontal axis across the arm)
    fill: float                            # how full of powder the vial is, 0 to 1
    flow: list | None                      # the powder stream's particles, or None
    beam: tuple | None                     # the scanner's beam (from, to), or None
    ring: tuple | None                     # where the active station's highlight ring is, or None
    caption: str
    clock: str                             # the run's own simulated clock, for the caption
    fault: bool = False
    recovery: bool = False
    contacts: int = 0


@dataclass
class Motion:
    trial: int
    frames: list[Frame]
    fps: int
    actions: int
    problems: list[str] = field(default_factory=list)
    ranges: list = field(default_factory=list)          # for each action: (its id, the first frame that belongs to it, the frame after its last)

    @property
    def seconds(self) -> float:
        return len(self.frames) / self.fps


def _clock(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min {rest:02d} s" if hours else f"{minutes} min {rest:02d} s"


def _smooth(x: float) -> float:
    return x * x * (3 - 2 * x)


def _rotate(vector: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """The vector turned about a unit axis by an angle (Rodrigues' rule)."""
    return vector * math.cos(angle) + np.cross(axis, vector) * math.sin(angle) + axis * float(np.dot(axis, vector)) * (1 - math.cos(angle))


def _across(x: float, y: float) -> np.ndarray:
    """The horizontal direction across the arm at a place (tipping about it leans an object's top outward)."""
    radial = math.atan2(y, x) if (x or y) else 0.0
    return np.array([-math.sin(radial), math.cos(radial), 0.0])


class _Player:
    """Walks through the actions, keeping the tip's position and what it holds, and records one frame per tick."""

    def __init__(self, cell: Cell, timeline: dict, fps: int):
        self.cell, self.timeline, self.fps = cell, timeline, fps
        layout = cell.layout
        self.layout = layout
        self.safe = layout["robot"]["safe_height_m"]
        self.place = {s["id"]: s for s in spots(layout)}
        home = layout["robot"]["home"]
        angle = math.radians(home["angle_deg"])
        self.place[HOME] = {"id": HOME, "kind": "home", "xyz": (home["radius_m"] * math.cos(angle), home["radius_m"] * math.sin(angle), home["height_m"]), "height_m": home["height_m"]}
        self.objects = {o["id"]: o for o in layout["objects"]}
        self.rest = {oid: np.array(rest_position(layout, o)) for oid, o in self.objects.items()}
        self.pos = {oid: self.rest[oid].copy() for oid in self.objects}
        self.tilt = {oid: 0.0 for oid in self.objects}
        self.tip = np.array(self.place[HOME]["xyz"], dtype=float)
        self.held: str | None = None
        self.fingers = 1.0
        self.fill, self.pours = 0.0, 0
        self.slots = max(1, len(layout["bottle_shelf"]["slots"]))
        self.flow: list | None = None
        self.beam: tuple | None = None
        self.ring: tuple | None = None
        self.frames: list[Frame] = []
        self.pose = [0.0, 0.3, -1.0, 0.0]
        self.caption, self.clock, self.fault, self.recovery = "", "", False, False
        self.faults = {f["action_id"]: f for f in timeline.get("faults", [])}
        self.t = 0.0
        self.record(0.0)

    # ------------------------------------------------------------------ frames
    def held_origin(self, tip: np.ndarray) -> np.ndarray:
        """Where the held object's origin is: it hangs from the tool tip (a vial 17 cm below it ...), turning with the tilt."""
        grip = grip_height(self.objects[self.held])
        return tip - _rotate(np.array([0.0, 0.0, grip]), _across(tip[0], tip[1]), self.tilt[self.held])

    def record(self, dt: float) -> None:
        self.t += dt
        tip = (float(self.tip[0]), float(self.tip[1]), float(self.tip[2]))
        found = solve(self.cell, tip, self.pose)
        if not found.reached:
            raise MotionError(f"The arm cannot reach where the plan sends it ({self.caption or 'start'}): the tool tip stops {found.error_m * 1000:.0f} mm short. Check the layout's arm length and positions.")
        self.pose = found.pose
        if self.held:
            self.pos[self.held] = self.held_origin(self.tip)
        arm_touching = [c for c in found.contacts if not any(name.startswith("floor") for name in c)]
        self.frames.append(Frame(self.t, list(found.pose), self.fingers, tip, {oid: (*map(float, self.pos[oid]), float(self.tilt[oid])) for oid in self.objects}, self.fill, self.flow, self.beam, self.ring,
                                 self.caption, self.clock, self.fault, self.recovery, len(arm_touching)))

    def glide(self, target: np.ndarray, seconds: float | None = None, polar: bool = True) -> None:
        """Move the tip to a target in a smooth line (or, along a circle round the column: angle and radius change evenly)."""
        start = self.tip.copy()
        a0, r0 = math.atan2(start[1], start[0]), math.hypot(start[0], start[1])
        a1, r1 = math.atan2(target[1], target[0]), math.hypot(target[0], target[1])
        distance = float(np.linalg.norm(target - start)) if not polar else math.hypot(abs(a1 - a0) * (r0 + r1) / 2, abs(r1 - r0), abs(target[2] - start[2]))
        if distance < 1e-6:
            return
        seconds = seconds if seconds is not None else max(MIN_MOVE_S, distance / TIP_SPEED_M_S)
        steps = max(2, int(round(seconds * self.fps)))
        for i in range(1, steps + 1):
            f = _smooth(i / steps)
            if polar:
                angle, radius = a0 + (a1 - a0) * f, r0 + (r1 - r0) * f
                self.tip = np.array([radius * math.cos(angle), radius * math.sin(angle), start[2] + (target[2] - start[2]) * f])
            else:
                self.tip = start + (target - start) * f
            self.record(1.0 / self.fps)

    def hold(self, seconds: float, wobble: str | None = None, amp: float = 0.0, tilt_to: float = 0.0, fingers_to: float | None = None, pour: tuple | None = None, beam: tuple | None = None) -> None:
        """Stay at the place for a while, doing something there. wobble: shake (up and down), stir (round), press (down and up). pour: (target point, trickle): the powder stream between 50 and 85 per cent of the time."""
        steps = max(1, int(round(seconds * self.fps)))
        centre, tilt0, fingers0 = self.tip.copy(), (self.tilt[self.held] if self.held else 0.0), self.fingers
        for i in range(1, steps + 1):
            f = i / steps
            if wobble == "shake":
                self.tip = centre + np.array([0.0, 0.0, amp * math.sin(2 * math.pi * 3 * f)])
            elif wobble == "stir":
                self.tip = centre + np.array([amp * math.cos(2 * math.pi * 2 * f) - amp, amp * math.sin(2 * math.pi * 2 * f), 0.0])
            elif wobble == "press":
                self.tip = centre + np.array([0.0, 0.0, -amp * math.sin(math.pi * f)])
            if self.held and tilt_to:
                self.tilt[self.held] = tilt0 + tilt_to * (_smooth(min(1.0, f / 0.3)) if f < 0.5 else 1.0 - _smooth(min(1.0, (f - 0.7) / 0.3)) if f > 0.7 else 1.0)
            if fingers_to is not None:
                self.fingers = fingers0 + (fingers_to - fingers0) * _smooth(min(1.0, f / 0.7))
            self.flow = None
            if pour and self.held and 0.5 <= f < 0.85:
                target, trickle = pour
                mouth = self.held_origin(self.tip) + _rotate(np.array([0.0, 0.0, 0.145]), _across(self.tip[0], self.tip[1]), self.tilt[self.held])
                self.flow = []
                for k in range(FLOW_PARTICLES):
                    along = ((self.t * 2.5) + k / FLOW_PARTICLES) % 1.0
                    self.flow.append(tuple(float(v) for v in mouth + (np.array(target) - mouth) * (along * (0.5 if trickle else 1.0))))
            self.beam = beam if (beam and 0.2 <= f < 0.85) else None
            self.record(1.0 / self.fps)
        self.flow, self.beam = None, None
        self.tip = centre
        if self.held:
            self.tilt[self.held] = tilt0
            self.pos[self.held] = self.held_origin(self.tip)
        if fingers_to is not None:
            self.fingers = fingers_to

    def goto(self, name: str, z: float | None = None) -> None:
        """Go to a place: lift, swing in close to the column and round (a short step between neighbouring places goes straight across), then go down to the height wanted (the tool-tip height at that place)."""
        if name not in self.place:
            raise MotionError(f"The plan names a place, '{name}', that is not in the layout.")
        x, y, work = self.place[name]["xyz"]
        target = np.array([x, y, work if z is None else z])
        self.ring = (x, y, work - 0.006) if name != HOME else None
        sideways = float(np.hypot(*(target[:2] - self.tip[:2])))
        if sideways > 0.02:
            travel = max(self.safe, target[2] + 0.05)
            if self.tip[2] < travel - 0.01:
                self.glide(np.array([self.tip[0], self.tip[1], travel]), polar=False)
            a0, r0 = math.atan2(self.tip[1], self.tip[0]), math.hypot(self.tip[0], self.tip[1])
            a1, r1 = math.atan2(y, x), math.hypot(x, y)
            if abs(math.degrees(a1 - a0)) > SWING_MIN_DEGREES:
                inner = max(0.45, min(r0, r1, SWING_RADIUS_M))
                self.glide(np.array([inner * math.cos(a0), inner * math.sin(a0), travel]))
                self.glide(np.array([inner * math.cos(a1), inner * math.sin(a1), travel]))
            self.glide(np.array([x, y, travel]))
        self.glide(target, polar=False)

    def grip_z(self, place: str, object_id: str) -> float:
        """The tool-tip height for holding an object that stands at a place."""
        return self.rest_at(object_id, place)[2] + grip_height(self.objects[object_id])

    def rest_at(self, object_id: str, place: str) -> np.ndarray:
        """Where an object's origin is when it stands at a place."""
        if place not in self.place:
            raise MotionError(f"The plan names a place, '{place}', that is not in the layout.")
        found = self.place[place]
        x, y, _ = found["xyz"]
        return np.array([x, y, found["height_m"] if self.objects[object_id]["type"] == "bottle" else surface_z(found)])

    # ------------------------------------------------------------------ one action
    def act(self, a: dict) -> None:
        kind = a["type"]
        self.recovery = a["origin"] == "recovery"
        self.fault = a["outcome"] == "failed"
        self.clock = _clock(a["actual_start_s"])
        prefix = "RECOVERY: " if self.recovery else ""
        said = a.get("caption") or f"{kind} {a.get('object') or ''}".strip()
        if self.fault:
            cause = self.faults.get(a["id"], {}).get("cause", "a fault")
            self.caption = said if "FAULT" in said else f"FAULT: {cause} ({said})"
        else:
            self.caption = f"{prefix}{said}"
        if kind == "move":
            self.goto(a["to"] if a["to"] in self.place else HOME, None)
            self.ring = None
            return
        if kind == "pick":
            self.goto(a["from"], self.grip_z(a["from"], a["object"]))
            self.hold(DWELL_S["pick"], fingers_to=0.0)
            self.held = a["object"]
            return
        if kind == "place":
            self.goto(a["to"], self.grip_z(a["to"], a["object"]))
            self.hold(DWELL_S["place"], fingers_to=1.0)
            if self.held:
                self.tilt[self.held] = 0.0
                self.pos[self.held] = self.rest_at(self.held, a["to"])
            self.held = None
            return
        if kind == "pour":
            x, y, work = self.place[a["at"]]["xyz"]
            self.goto(a["at"], work + POUR_HEIGHT_M)
            self.hold(DWELL_S["pour"] * (0.5 if self.fault else 1.0), tilt_to=math.radians(TILT_POUR_DEG) * (0.4 if self.fault else 1.0), pour=((x, y, work + 0.08), self.fault))
            if not self.fault and a.get("into") == "vial":
                self.pours += 1
                self.fill = min(1.0, self.pours / self.slots)
            return
        if kind == "shake":
            lifted = np.array([self.tip[0], self.tip[1], max(self.tip[2], 1.0)])
            self.glide(lifted, polar=False)
            self.hold(DWELL_S["shake"], wobble="shake", amp=0.03)
            return
        if kind == "press":
            self.goto(a["at"], self.grip_z(a["at"], a["object"]) + 0.14)
            self.hold(DWELL_S["press"], wobble="press", amp=0.14)
            tablet = next((oid for oid, o in self.objects.items() if o["type"] == "tablet"), None)
            if tablet:
                self.pos[tablet] = self.rest_at(tablet, a["at"])
            return
        if kind == "stir":
            self.goto(a["at"], self.grip_z(a["at"], a["object"]) + 0.1)
            self.glide(self.tip + np.array([0.0, 0.0, -0.3]), polar=False)
            self.hold(DWELL_S["stir"], wobble="stir", amp=0.025)
            self.glide(self.tip + np.array([0.0, 0.0, 0.3]), polar=False)
            return
        if kind == "scan":
            x, y, work = self.place[a["at"]]["xyz"]
            self.goto(a["at"], work + POUR_HEIGHT_M)
            angle = math.radians(self.place[a["at"]]["angle_deg"])
            local = np.array([-0.075, -0.27, 0.0])                                  # the scanner's window, in the station's own frame
            window = np.array([x + local[0] * math.cos(angle) - local[1] * math.sin(angle), y + local[0] * math.sin(angle) + local[1] * math.cos(angle), self.place[a["at"]]["height_m"] + 0.04])
            vial = self.tip - np.array([0.0, 0.0, 0.085])
            self.hold(DWELL_S["scan"], beam=(tuple(float(v) for v in window), tuple(float(v) for v in vial)))
            return
        self.hold(DWELL_S.get(kind, 0.5))             # read, wait: the arm stays where it is


def rest_motion(cell: Cell) -> Motion:
    """The cell at rest: the arm at its home pose and every object where it starts (what is shown before a run begins)."""
    return Motion(0, _Player(cell, {"faults": []}, 20).frames[:1], 20, 0)


def plan_motion(cell: Cell, timeline: dict, fps: int = 20) -> Motion:
    """The arm's playback of one executed timeline. Needs a cell built with `with_objects=True`. Raises MotionError, in words, when the arm cannot reach a place the plan names."""
    if "actions" not in timeline or not timeline["actions"]:
        raise MotionError("This timeline has no actions to play.")
    player = _Player(cell, timeline, fps)
    ranges = []
    for a in timeline["actions"]:
        first = len(player.frames)
        player.act(a)
        ranges.append((a["id"], first, len(player.frames)))
    player.fault = player.recovery = False
    player.caption = "Trial finished: the arm is back at its home pose."
    player.goto(HOME, None)
    player.ring = None
    player.hold(0.8)
    touching = sum(1 for f in player.frames if f.contacts)
    problems = [f"the arm touched something in {touching} frames"] if touching else []
    return Motion(int(timeline.get("trial", 0)), player.frames, fps, len(timeline["actions"]), problems, ranges)


def _quat_z_to(direction: np.ndarray) -> np.ndarray:
    """The rotation (as a quaternion) that turns the z axis to point along a direction."""
    d = direction / max(np.linalg.norm(direction), 1e-9)
    axis = np.cross([0.0, 0.0, 1.0], d)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0]) if d[2] > 0 else np.array([0.0, 1.0, 0.0, 0.0])
    angle = math.acos(max(-1.0, min(1.0, d[2])))
    return np.array([math.cos(angle / 2), *(axis / norm * math.sin(angle / 2))])


def _body_index(cell: Cell, name: str) -> int:
    return int(cell.model.body_mocapid[mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_BODY, name)])


def apply_frame(cell: Cell, frame: Frame) -> None:
    """Put the scene in a frame's state: the arm's pose and fingers, every object's place and tilt, the vial's powder, the highlight ring, the powder stream and the scanner's beam."""
    cell.set_arm(*frame.pose, fingers=frame.fingers)
    for oid, (x, y, z, tilt) in frame.objects.items():
        index = _body_index(cell, "obj_" + oid)
        cell.data.mocap_pos[index] = (x, y, z)
        axis = _across(x, y)
        cell.data.mocap_quat[index] = (math.cos(tilt / 2), *(axis * math.sin(tilt / 2)))
    powder = mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_GEOM, "powder")
    if powder >= 0:
        half = 0.0005 + 0.08 * frame.fill
        cell.model.geom_size[powder][1] = half
        cell.model.geom_pos[powder][2] = 0.0035 + half
    ring = _body_index(cell, "ring")
    cell.data.mocap_pos[ring] = frame.ring if frame.ring else (0.0, 0.0, HIDDEN_Z)
    beam = _body_index(cell, "beam")
    beam_geom = mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_GEOM, "beam")
    if frame.beam:
        a, b = np.array(frame.beam[0]), np.array(frame.beam[1])
        cell.data.mocap_pos[beam] = (a + b) / 2
        cell.data.mocap_quat[beam] = _quat_z_to(b - a)
        cell.model.geom_size[beam_geom][1] = float(np.linalg.norm(b - a)) / 2
    else:
        cell.data.mocap_pos[beam] = (0.0, 0.0, HIDDEN_Z)
    for i in range(FLOW_PARTICLES):
        cell.data.mocap_pos[_body_index(cell, f"flow{i}")] = frame.flow[i] if frame.flow else (0.0, 0.0, HIDDEN_Z)
    mujoco.mj_forward(cell.model, cell.data)
