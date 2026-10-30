"""Plays a trial of a finished run with the MuJoCo arm: `python -m cellpoc.physics.play` (or double-click play_physics.bat).

  --run FOLDER   the run to play (default runs/platform: the run `run_app.bat` builds)
  --trial N      which trial (default: the first trial with a fault, else trial 1)
  --gif FILE     write an animated GIF instead of opening the viewer (also --still FILE for one picture)
  --speed X      viewer speed (1 = the playback pace; 2 = twice as fast)

The playback is a separate view: it reads the run's saved timeline and layout and changes nothing in the run. Illustrative: the layout's generic arm, made-up values, no real hardware.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mujoco

from .motion import MotionError, apply_frame, plan_motion
from .scene import load_cell

ROOT = Path(__file__).resolve().parents[2]


def pick_trial(folder: Path, wanted: int | None) -> Path:
    files = sorted((folder / "executed").glob("T*-executed.json"))
    if not files:
        raise MotionError(f"There is no saved run in {folder}. Double-click run_app.bat once to build one, or give another folder with --run.")
    if wanted is not None:
        for f in files:
            if int(f.name[1:4]) == wanted:
                return f
        raise MotionError(f"Trial {wanted} is not in this run (it has trials {int(files[0].name[1:4])} to {int(files[-1].name[1:4])}).")
    for f in files:
        if json.loads(f.read_text(encoding="utf-8")).get("faults"):
            return f
    return files[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a trial with the MuJoCo arm.")
    parser.add_argument("--run", default=str(ROOT / "runs" / "platform"))
    parser.add_argument("--trial", type=int)
    parser.add_argument("--gif")
    parser.add_argument("--still")
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args(argv)
    folder = Path(args.run)
    try:
        timeline_file = pick_trial(folder, args.trial)
        layout = json.loads((folder / "layout.json").read_text(encoding="utf-8"))
        timeline = json.loads(timeline_file.read_text(encoding="utf-8"))
        cell = load_cell(layout, with_objects=True)
        motion = plan_motion(cell, timeline)
    except (MotionError, OSError, ValueError) as error:
        print(f"\nCannot play this: {error}")
        return 1
    print(f"Trial {motion.trial}: {motion.actions} actions, {len(motion.frames)} frames, {motion.seconds:.0f} s of playback. Illustrative: the layout's generic arm and made-up values.")
    if motion.problems:
        print("Note:", "; ".join(motion.problems))
    if args.gif or args.still:
        from .render import save_gif, save_still
        if args.still:
            print("Wrote", save_still(cell, motion, len(motion.frames) // 2, Path(args.still)))
        if args.gif:
            print("Wrote", save_gif(cell, motion, Path(args.gif)))
        return 0
    import mujoco.viewer
    shown = ""
    with mujoco.viewer.launch_passive(cell.model, cell.data) as viewer:
        viewer.cam.lookat[:] = [0.0, 0.55, 0.72]
        viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 3.0, 90.0, -30.0
        print("The viewer is open. Rotate with the left mouse button, zoom with the wheel. Close the window to stop.\n")
        while viewer.is_running():
            started = time.time()
            for frame in motion.frames:
                if not viewer.is_running():
                    break
                if frame.caption != shown:
                    shown = frame.caption
                    print(f"[{frame.clock}] {shown}", flush=True)
                with viewer.lock():
                    apply_frame(cell, frame)
                viewer.sync()
                wait = started + frame.time_s / max(args.speed, 0.1) - time.time()
                if wait > 0:
                    time.sleep(wait)
            time.sleep(1.5)
            shown = ""
    return 0


if __name__ == "__main__":
    sys.exit(main())
