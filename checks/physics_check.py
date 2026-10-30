"""Health check for the physics part: the MuJoCo model of the cell, built from the layout file, and the reach test asked of MuJoCo.

In plain words it checks that: the cell scene loads from the layout and its geometry is the layout's (arm length measured on the model, shoulder height, the stations and slots where the layout puts them); gravity is right (a dropped ball falls within 1 per cent
of what physics says); the same simulation run twice gives exactly the same numbers; a vial dropped on a station's pad comes to rest on it and stays put; MuJoCo's inverse-kinematics solver puts the tool tip within half a millimetre of every one of the 28 targets
(every station, bottle slot and tool holder, at the working height and at the safe height) with the tool hanging straight down and the arm touching nothing; the spare reach MuJoCo measures agrees with the setup rules' formula at every target and
for the tightest one (0.08 m); and the checks can fail: a bottle slot moved out to 1.5 m is not reached (and the formula agrees), a shorter arm loses reach, a longer arm gains exactly what was added, and a layout MuJoCo cannot load is refused in words. The
scene file for MuJoCo's own viewer is written and loads. The part imports nothing from the project, touches no network, and nothing else uses it yet. Nothing is written into the project.
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mujoco  # noqa: E402

from cellpoc.physics import build_mjcf, free_fall, load_cell, reach_all, repeatable, settle_vial, solve, spare_reach, spots, stretched_length, tightest  # noqa: E402
from cellpoc.physics.motion import MotionError, plan_motion  # noqa: E402
from cellpoc.physics.scene import rest_position  # noqa: E402
from cellpoc.platform_runner import load_inputs, run_setup, save_platform_run  # noqa: E402
from cellpoc.setup.layout_rules import reach_report  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

LAYOUT = ROOT / "cellpoc" / "formats" / "examples" / "cell_layout_example.json"


def analytic_spare(layout: dict, radius: float, height: float) -> float:
    """The setup rules' formula for one spot and one height, worked out here separately."""
    robot = layout["robot"]
    arm = robot["links_m"]["upper_arm"] + robot["links_m"]["forearm"]
    return arm - math.hypot(radius, height + robot["links_m"]["wrist_to_tip"] - robot["shoulder_height_m"])


def motion_checks(cl: Checklist, layout: dict) -> None:
    """The playback of a real run's trials with the MuJoCo arm: every action played, the right things carried to the right places, the fault shown, nothing touched, nothing in the run changed."""
    import copy
    import hashlib
    import tempfile

    setup, run_layout, settings = load_inputs()
    run = run_setup(setup, run_layout, settings)
    timelines = run.executed
    before = hashlib.sha256(json.dumps(timelines, sort_keys=True, default=str).encode()).hexdigest()
    faulty = next(tl for tl in timelines if tl["faults"])
    clean = next(tl for tl in timelines if not tl["faults"] and tl["outcome"] == "completed")
    cell = load_cell(run_layout, with_objects=True)
    played = {}
    for name, tl in (("faulty", faulty), ("clean", clean)):
        played[name] = plan_motion(cell, tl)

    def final_places(tl: dict) -> dict:
        """Where each object ends up, worked out from the timeline alone (picks and places), separately from the playback."""
        where = {o["id"]: o.get("starts_at") for o in run_layout["objects"]}
        holding = None
        for a in tl["actions"]:
            if a["type"] == "pick":
                holding = a["object"]
            elif a["type"] == "place":
                where[a["object"]] = a["to"]
                holding = None
            elif a["type"] == "press":
                where["tablet"] = a["at"]
        return where

    layout_objects = {o["id"]: o for o in run_layout["objects"]}
    problems = []
    for name, tl in (("faulty", faulty), ("clean", clean)):
        last = played[name].frames[-1].objects
        for oid, place in final_places(tl).items():
            expected = rest_position(run_layout, {**layout_objects[oid], "starts_at": place})
            got = last[oid][:3]
            if place is not None and max(abs(a - b) for a, b in zip(got, expected)) > 1e-6:
                problems.append(f"{name}: {oid} ends at {tuple(round(v, 3) for v in got)} not {tuple(round(v, 3) for v in expected)}")
    cl.record(not problems and all(m.actions == len(tl["actions"]) for m, tl in ((played["faulty"], faulty), (played["clean"], clean))),
              "MuJoCo plays every action of a real trial (a clean one and one with a jam) and every object ends where the timeline puts it (vial in the discard bin, tablet in the dissolution vessel, bottles and tools back in their places; worked out separately from the timeline)",
              f"faulty trial {faulty['trial']}: {played['faulty'].actions} actions, {len(played['faulty'].frames)} frames; clean trial {clean['trial']}: {played['clean'].actions} actions; {problems[:2]}")
    touching = {k: sum(1 for f in m.frames if f.contacts) for k, m in played.items()}
    low = min(min(f.tip[2] for f in m.frames) for m in played.values())
    steps = max(max(abs(a - b) for a, b in zip(m.frames[i].pose, m.frames[i - 1].pose)) for m in played.values() for i in range(1, len(m.frames)))
    cl.record(not any(touching.values()) and low > layout["table"]["height_m"] and steps < 0.25,
              "Throughout both playbacks the arm touches nothing (no frame with a contact), the tool tip never goes below the table top, and no joint turns more than 0.25 radian between frames (smooth, not jumping)", f"frames touching {touching}; lowest tip {low:.3f} m; largest joint step {steps:.3f} rad")
    flagged = [f for f in played["faulty"].frames if f.fault]
    recovery = [f for f in played["faulty"].frames if f.recovery]
    cause = faulty["faults"][0]["cause"]
    cl.record(flagged and recovery and all(cause in f.caption for f in flagged) and not any(f.fault or f.recovery for f in played["clean"].frames),
              "The jam shows in the playback: the failed pour is marked as a fault with its cause in the caption, the recovery actions are marked as recovery, and a clean trial has neither", f"{len(flagged)} fault frames; {len(recovery)} recovery frames; cause '{cause}'")
    again = plan_motion(load_cell(run_layout, with_objects=True), faulty)
    same = [f.pose for f in again.frames] == [f.pose for f in played["faulty"].frames] and [f.caption for f in again.frames] == [f.caption for f in played["faulty"].frames]
    cl.record(same, "Playing the same trial twice gives exactly the same arm poses frame by frame (nothing random)")
    cl.record(hashlib.sha256(json.dumps(timelines, sort_keys=True, default=str).encode()).hexdigest() == before,
              "Playing trials changes nothing in the run: the 30 executed timelines are byte for byte what they were before the playback", "")
    # refusals in words
    short = copy.deepcopy(run_layout)
    short["robot"]["links_m"]["forearm"] = 0.45
    short["robot"]["reach_m"] = 1.17
    odd = copy.deepcopy(faulty)
    odd["actions"][0] = {**odd["actions"][0], "from": "nowhere"}
    messages = []
    for label, lay, tl in (("a short arm", short, faulty), ("an unknown place", run_layout, odd), ("no actions", run_layout, {"trial": 1, "actions": []})):
        try:
            plan_motion(load_cell(lay, with_objects=True), tl)
            messages.append(f"{label}: NOT REFUSED")
        except MotionError as error:
            messages.append(str(error) if len(str(error)) > 30 and "Traceback" not in str(error) else f"{label}: not plain")
    cl.record(not any("NOT REFUSED" in m or "not plain" in m for m in messages),
              "Self-test: a playback that cannot be made is refused in plain words, not a crash: an arm too short to reach where the plan sends it, a place the plan names that is not in the layout, a timeline with no actions", " | ".join(m[:70] for m in messages))
    # pictures and the command
    try:                                 # only a computer that cannot draw at all skips this; any other error is a failure
        probe = mujoco.Renderer(cell.model, 64, 64)
        probe.close()
        can_draw = True
    except Exception as error:
        can_draw = False
        cl.skip("The command writes a picture of a trial", f"this computer cannot draw MuJoCo pictures ({str(error)[:80]})")
    if can_draw:
        from cellpoc.physics import play
        from cellpoc.physics.render import decorate
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            save_platform_run(run, Path(folder))
            out = Path(folder) / "still.png"
            code = play.main(["--run", folder, "--trial", str(faulty["trial"]), "--still", str(out)])
            missing = play.main(["--run", folder, "--trial", "999", "--still", str(Path(folder) / "x.png")])
            empty = play.main(["--run", str(Path(folder) / "empty"), "--still", str(Path(folder) / "y.png")])
            size = Image.open(out).size if out.exists() else (0, 0)
            ok = code == 0 and missing == 1 and empty == 1 and size == (1280, 720) and out.stat().st_size > 20_000
        labelled = decorate(Image.new("RGB", (640, 360)), 1, "caption", "0 min", False, False).getbbox() is not None
        cl.record(ok and labelled, "The command `python -m cellpoc.physics.play` writes a picture of a saved run's trial (1280 x 720, with the illustrative label and caption), and a trial that is not in the run, or a folder with no run, is refused with a message and no crash", f"picture {size}")


def main() -> int:
    cl = Checklist("PHYSICS (MuJoCo): the cell built from the layout, gravity, repeatability, and the reach test asked of MuJoCo")
    before = project_files()
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- the scene is the layout's
    cell = load_cell(layout)
    robot = layout["robot"]
    arm_length = stretched_length(cell)
    first_station = layout["stations"][0]
    expected = (first_station["position"]["radius_m"] * math.cos(math.radians(first_station["position"]["angle_deg"])), first_station["position"]["radius_m"] * math.sin(math.radians(first_station["position"]["angle_deg"])), first_station["work_height_m"])
    found = tuple(cell.site("spot_" + first_station["id"]))
    shoulder_z = float(cell.model.body("shoulder_base").pos[2])
    cl.record(abs(arm_length - (robot["links_m"]["upper_arm"] + robot["links_m"]["forearm"])) < 1e-9 and abs(shoulder_z - robot["shoulder_height_m"]) < 1e-9 and max(abs(a - b) for a, b in zip(found, expected)) < 1e-3,
              "The MuJoCo scene is the layout's: the arm stretched out measures upper arm + forearm (1.44 m), the shoulder is at the layout's height, and a station sits where the layout's angle and radius put it",
              f"stretched {arm_length:.4f} m; shoulder {shoulder_z:.3f} m; first station off by {max(abs(a - b) for a, b in zip(found, expected)) * 1000:.2f} mm")
    spot_list = spots(layout)
    cl.record(len(spot_list) == len(layout["stations"]) + len(layout["bottle_shelf"]["slots"]) + len(layout["tool_holders"]) == 14 and all(mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_SITE, "spot_" + s["id"]) >= 0 for s in spot_list),
              "Every station, bottle slot and tool holder in the layout (14) has its place in the scene", f"{len(spot_list)} places")

    # ---------------------------------------------------------------- physics sanity
    fell, should = free_fall()
    cl.record(abs(fell - should) / should < 0.01, "Gravity is right: a ball dropped for 0.4 s falls within 1 per cent of what physics says (g t squared over two)", f"fell {fell:.4f} m; physics says {should:.4f} m")
    cl.record(repeatable(layout), "The same simulation run twice, started the same way, ends in exactly the same state (nothing random)")
    rest = settle_vial(layout)
    cl.record(abs(rest["rest_height_m"] - rest["expected_height_m"]) < 0.002 and rest["slide_m"] < 0.005 and rest["tilt_deg"] < 1.0,
              "A vial dropped 3 cm onto a station's pad comes to rest standing on it (within 2 mm of the right height, not slid, not tilted)",
              f"rest height off by {(rest['rest_height_m'] - rest['expected_height_m']) * 1000:.2f} mm; slid {rest['slide_m'] * 1000:.2f} mm; tilt {rest['tilt_deg']:.2f} deg")

    # ---------------------------------------------------------------- the reach test
    reports = reach_all(cell)
    worst_error = max(r.solution.error_m for r in reports)
    cl.record(len(reports) == 28 and all(r.solution.reached for r in reports) and worst_error < 5e-4,
              "MuJoCo's inverse-kinematics solver puts the tool tip within half a millimetre of every target: 14 places at the working height and at the safe height (28 in all)", f"{sum(r.solution.reached for r in reports)} of {len(reports)} reached; worst error {worst_error * 1000:.3f} mm")
    cl.record(all(abs((r.solution.pose[1] + r.solution.pose[2] + r.solution.pose[3]) + math.pi / 2) < 1e-6 for r in reports),
              "At every target the tool hangs straight down (the shoulder, elbow and wrist angles add up to pointing at the floor)")
    touching = [(r.spot, r.level, r.solution.contacts[0]) for r in reports if r.solution.contacts]
    cl.record(not touching, "The arm touches nothing (table, pads, column, floor) at any of the 28 targets", f"{len(touching)} with contact" + (f"; first {touching[0]}" if touching else ""))
    by_target = {(r.spot, r.level): r for r in reports}
    worst_gap = 0.0
    for spot in spot_list:
        for level, h in (("working height", spot["height_m"]), ("safe height", robot["safe_height_m"])):
            worst_gap = max(worst_gap, abs(by_target[(spot["id"], level)].spare_m - analytic_spare(layout, spot["radius_m"], h)))
    margin, where, _ = reach_report(layout)
    t = tightest(reports)
    cl.record(worst_gap < 1e-9 and abs(t.spare_m - margin) < 1e-9, "The spare reach MuJoCo measures on its model equals the setup rules' formula at all 28 targets, and the tightest spot agrees (about 0.08 m spare)",
              f"largest difference {worst_gap:.1e} m; tightest by MuJoCo {t.spare_m:.4f} m, by the formula {margin:.4f} m (all five bottle slots are equally far, so they tie)")

    # ---------------------------------------------------------------- the checks can fail
    far = copy.deepcopy(layout)
    far["bottle_shelf"]["slots"][0]["position"]["radius_m"] = 1.5
    far_cell = load_cell(far)
    far_reports = [r for r in reach_all(far_cell) if r.spot == "slot_1"]
    cl.record(far_reports and not any(r.solution.reached for r in far_reports) and all(r.spare_m < 0 for r in far_reports) and bool(reach_report(far)[2]),
              "Self-test: a bottle slot moved out to 1.5 m is NOT reached by MuJoCo (the tip stops short), its spare reach is negative, and the setup rules' formula agrees", f"closest approach {min(r.solution.error_m for r in far_reports) * 1000:.0f} mm short" if far_reports else "")
    short, long_ = copy.deepcopy(layout), copy.deepcopy(layout)
    short["robot"]["links_m"]["forearm"] = 0.55
    long_["robot"]["links_m"]["forearm"] = 0.82
    short_reports, long_reports = reach_all(load_cell(short)), reach_all(load_cell(long_))
    cl.record(not all(r.solution.reached for r in short_reports) and all(r.solution.reached for r in long_reports) and abs(tightest(long_reports).spare_m - (margin + 0.10)) < 1e-6,
              "Self-test: a shorter forearm (0.55 m) loses places the arm can reach; a longer one (0.82 m) reaches all 28 and gains exactly the 0.10 m that was added", f"short arm reaches {sum(r.solution.reached for r in short_reports)} of 28; long arm tightest {tightest(long_reports).spare_m:.4f} m")
    broken = copy.deepcopy(layout)
    broken["table"]["radius_m"] = 0
    try:
        load_cell(broken)
        refusal = ""
    except ValueError as error:
        refusal = str(error)
    cl.record(len(refusal) > 40 and "layout" in refusal and "Traceback" not in refusal, "A layout MuJoCo cannot build a scene from (a table of zero size) is refused in plain words that point at the layout file", refusal[:120])
    into_table = solve(cell, (0.9, 0.0, 0.3))
    cl.record(into_table.reached and any("table" in pair for pair in into_table.contacts), "Self-test: a target below the table top (the arm could get there but the tool would go through the table) is reported as a collision, so the collision test can fail", f"touching: {into_table.contacts[:2]}")

    # ---------------------------------------------------------------- the playback of a real run
    motion_checks(cl, layout)

    # ---------------------------------------------------------------- the scene file for MuJoCo's viewer
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "cell.xml"
        from cellpoc.physics import export
        old_argv = sys.argv
        sys.argv = ["export", "--layout", str(LAYOUT), "--out", str(out)]
        try:
            export.main()
        finally:
            sys.argv = old_argv
        written = out.read_text(encoding="utf-8") if out.exists() else ""
        loads = False
        try:
            mujoco.MjModel.from_xml_path(str(out))
            loads = True
        except Exception:
            loads = False
    cl.record(written == build_mjcf(layout, with_vial=True) and loads, "The scene file written for MuJoCo's own viewer is exactly the scene built here, and MuJoCo loads it", f"{len(written)} characters")

    # ---------------------------------------------------------------- the part is self-contained and unused by anything else
    part = ROOT / "cellpoc" / "physics"
    imports = [line for p in part.glob("*.py") for line in p.read_text(encoding="utf-8").splitlines() if line.startswith(("import ", "from ")) and ("cellpoc" in line or line.startswith("from .."))]
    users = []
    for p in (ROOT / "cellpoc").rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "physics" not in p.parts and ("cellpoc.physics" in text or "from ..physics" in text or "from . import physics" in text):
            users.append(str(p.relative_to(ROOT)))
    cl.record(architecture.ALLOWED["physics"] == set() and not imports and [u.replace("\\", "/") for u in users] == ["cellpoc/live/server.py"], "The physics part imports nothing from the project, and the only thing in the project that uses it is the live server (to draw a picture on request): the run, its timings and trial counts cannot change", f"{len(list(part.glob('*.py')))} files; used by {users or 'nothing'}")
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    os.environ.pop("CELLPOC_RECORD", None)
    sys.exit(main())
