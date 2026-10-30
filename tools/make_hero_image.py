"""Makes the picture at the top of the app's front page: a still of the simulated cell from the MuJoCo model, with the arm holding an ingredient bottle in front of the camera. It is saved as static/cell_hero.jpg (the app serves the static folder).

    .venv\\Scripts\\python.exe tools\\make_hero_image.py [seconds into trial 1, default 330]

The picture is a simulation: the app's front page says so under it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.live.pace import Pacer  # noqa: E402
from cellpoc.live.run import LiveRun  # noqa: E402
from cellpoc.physics import Stage, prepare_drawing  # noqa: E402

OUT = ROOT / "static" / "cell_hero.jpg"


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 330.0
    prepare_drawing()
    run = LiveRun(pacer=Pacer(300), save_to=None)
    run.fast_forward(seconds + 60, 300)
    stage = Stage(run.layout)
    OUT.write_bytes(stage.jpeg(run.feed.timelines[0], seconds))
    stage.close()
    print("Saved", OUT, OUT.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
