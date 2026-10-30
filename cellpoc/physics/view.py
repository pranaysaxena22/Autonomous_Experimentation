"""Builds what the app's "Physics (MuJoCo)" page shows, next to a saved run: an animated picture of a trial played with the MuJoCo arm (one with a jam and its recovery, one without), and a short text with the physics checks.

`python -m cellpoc.physics.view --run runs\\platform` (run_app.bat does this for you, the first time only). It reads the run's saved layout and executed timelines; it writes physics_view_1.webp, physics_view_2.webp (with a one-line
description each), physics_summary.md and a key file. The key is a fingerprint of everything the pictures depend on, so a run that has not changed is not drawn again. Illustrative: the layout's generic arm and made-up values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import mujoco

from .motion import MotionError, plan_motion
from .reach import reach_all, tightest
from .render import camera, render_frame
from .scene import load_cell

SIZE = (960, 540)
STRIDE = 2                  # every second frame of the 20 a second: ten pictures a second
HERE = Path(__file__).resolve().parent
VIEW_FILES = ("physics_view_1.webp", "physics_view_2.webp")
SUMMARY_FILE, KEY_FILE = "physics_summary.md", "physics_view_key.txt"


def pick(timelines: list[tuple[Path, dict]]) -> list[tuple[Path, dict, str]]:
    """The trials to show: the first one with a jam (and its recovery), then the first clean one."""
    chosen = []
    faulty = next(((p, t) for p, t in timelines if t.get("faults")), None)
    clean = next(((p, t) for p, t in timelines if not t.get("faults") and t.get("outcome") == "completed"), None)
    if faulty:
        cause = faulty[1]["faults"][0]["cause"]
        chosen.append((*faulty, f"Trial {faulty[1]['trial']}, with a fault: {cause}, and what the cell does about it."))
    if clean:
        chosen.append((*clean, f"Trial {clean[1]['trial']}, with nothing going wrong."))
    return chosen


def fingerprint(layout_text: str, chosen: list, size: tuple[int, int], stride: int) -> str:
    h = hashlib.sha256()
    h.update(layout_text.encode("utf-8"))
    for path, _, _ in chosen:
        h.update(path.read_text(encoding="utf-8").encode("utf-8"))
    for source in sorted(HERE.glob("*.py")):
        h.update(source.read_bytes())
    h.update(f"{size}{stride}".encode("utf-8"))
    return h.hexdigest()


def summary_text(layout: dict, reports: list, motions: list, notes: list[str]) -> str:
    """The physics checks as the page shows them: plain words and one small table."""
    reached = sum(1 for r in reports if r.solution.reached)
    worst = max(r.solution.error_m for r in reports)
    touching = sum(r.solution.contacts != [] for r in reports)
    tight = tightest(reports)
    frames_touching = sum(1 for m in motions for f in m.frames if f.contacts)
    lines = [
        "**MuJoCo physics model** of the same cell, playing the run's plan. The run's times and results do not come from it.",
        "",
        f"- **Reach:** the arm was asked to put its tool tip at all {len(reports)} targets (every station, bottle slot and tool holder, at working height and at the safe height). **{reached} of {len(reports)} reached**, worst miss {worst * 1000:.2f} mm.",
        f"- **Spare reach:** the tightest spot has **{tight.spare_m:.3f} m** to spare ({tight.spot}, at its {tight.level}).",
        f"- **Collisions:** the arm touched nothing at any target ({touching} touching), and in the animated trials below in {frames_touching} of {sum(len(m.frames) for m in motions)} frames.",
        "",
        "| Place | Kind | Spare reach at working height (m) | Spare reach at safe height (m) | Elbow bend at working height (degrees) |",
        "|---|---|---|---|---|",
    ]
    by_spot = {}
    for r in reports:
        by_spot.setdefault((r.spot, r.kind), {})[r.level] = r
    for (spot, kind), levels in by_spot.items():
        work, safe = levels["working height"], levels["safe height"]
        lines.append(f"| {spot} | {kind} | {work.spare_m:.3f} | {safe.spare_m:.3f} | {work.solution.elbow_bend_deg:.0f} |")
    lines += ["", "Powder and liquids are drawn from the plan, not simulated. Generic arm, no real hardware. Illustrative values."]
    lines += [""] + [f"*{n}*" for n in notes]
    return "\n".join(lines) + "\n"


def build(folder: Path, size: tuple[int, int] = SIZE, stride: int = STRIDE, force: bool = False, log=print) -> list[Path]:
    """Draw the views for the run saved in a folder (skipped when nothing they depend on has changed). Returns the files written, or [] when there is nothing to draw or nothing changed."""
    layout_file, executed = folder / "layout.json", folder / "executed"
    if not layout_file.exists() or not executed.exists():
        return []
    layout_text = layout_file.read_text(encoding="utf-8")
    layout = json.loads(layout_text)
    timelines = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(executed.glob("T*-executed.json"))]
    chosen = pick(timelines)
    if not chosen:
        return []
    key = fingerprint(layout_text, chosen, size, stride)
    if not force and (folder / KEY_FILE).exists() and (folder / KEY_FILE).read_text(encoding="utf-8").strip() == key and all((folder / n).exists() for n in VIEW_FILES[:len(chosen)]) and (folder / SUMMARY_FILE).exists():
        log("The MuJoCo view for this run is already up to date.")
        return []
    from PIL import Image
    written, motions = [], []
    reports = reach_all(load_cell(layout))
    for index, (path, timeline, description) in enumerate(chosen):
        started = time.time()
        cell = load_cell(layout, with_objects=True)
        motion = plan_motion(cell, timeline)
        motions.append(motion)
        log(f"Drawing {description.split(':')[0]} ({len(motion.frames) // stride} pictures) ...")
        renderer = mujoco.Renderer(cell.model, size[1], size[0])
        cam = camera()
        try:
            images = [render_frame(cell, renderer, motion, i, cam) for i in range(0, len(motion.frames), stride)]
        finally:
            renderer.close()
        target = folder / VIEW_FILES[index]
        images[0].save(target, save_all=True, append_images=images[1:], duration=int(1000 * stride / motion.fps), loop=0, quality=72, method=4)
        (folder / VIEW_FILES[index].replace(".webp", ".txt")).write_text(f"{description} About {motion.seconds:.0f} seconds of playback for {motion.actions} actions (a long wait is shown as a short pause).", encoding="utf-8")
        written.append(target)
        log(f"  done in {time.time() - started:.0f} s ({target.stat().st_size / 1e6:.1f} MB)")
    notes = [f"{m.problems[0]}" for m in motions if m.problems]
    (folder / SUMMARY_FILE).write_text(summary_text(layout, reports, motions, notes), encoding="utf-8")
    (folder / KEY_FILE).write_text(key, encoding="utf-8")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the MuJoCo views for a saved run.")
    parser.add_argument("--run", default=str(HERE.parents[1] / "runs" / "platform"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        written = build(Path(args.run), force=args.force)
    except (MotionError, OSError, ValueError) as error:
        print(f"The MuJoCo view could not be built: {error}")
        return 1
    if not written and not (Path(args.run) / SUMMARY_FILE).exists():
        print("There is no saved run in that folder to draw.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
