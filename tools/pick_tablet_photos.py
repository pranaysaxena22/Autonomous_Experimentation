"""Cuts demonstration photographs out of the downloaded PharmaVision TEST set (photographs the tablet network never saw in training or in choosing its best pass): the first six NORMAL and the first six DEFECTIVE ones, in file-name order,
that the trained network reads correctly. They go to data/public/pharmavision/demo_tablets (not saved in git: the photographs are not ours to republish) and the live run's tablet check shows them as stand-ins for the cell's camera.

The rule is plain on purpose: file-name order, correctly read. The photographs are therefore neither the hardest nor the easiest of the ones it reads right; the scores for ALL test photographs are in data/vision_models/tablet_report.json.

    .venv\\Scripts\\python.exe tools\\pick_tablet_photos.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.vision import tablet  # noqa: E402

ZIP = ROOT / "data" / "public" / "pharmavision" / "pharmavision.zip"
PER_KIND = 6


def main() -> int:
    if not ZIP.exists() or not tablet.available():
        print("Run tools\\download_pharmavision.py and tools\\train_tablet.py first.")
        return 1
    tablet.DEMO_FOLDER.mkdir(parents=True, exist_ok=True)
    for old in tablet.DEMO_FOLDER.glob("*.jpg"):
        old.unlink()
    lines = ["Real photographs from the PharmaVision TEST set (Tahir Lee et al., Pharmaceutics 2026; Kaggle tahirlee/pharmaceutical-tablets-dataset; use confirmed by the project owner 2026-10-23; not for republishing). The first six of each kind, in file-name order, that the network reads correctly.", ""]
    with zipfile.ZipFile(ZIP) as z:
        names = sorted(n for n in z.namelist() if "/test/" in n and n.lower().endswith((".jpg", ".jpeg", ".png")))
        for kind in ("normal", "defective"):
            taken = 0
            for name in (n for n in names if f"/test/{kind}/" in n):
                image = cv2.imdecode(np.frombuffer(z.read(name), np.uint8), cv2.IMREAD_COLOR)
                if image is None or tablet.inspect(image).label != kind:
                    continue
                taken += 1
                cv2.imwrite(str(tablet.DEMO_FOLDER / f"{kind}_{taken}.jpg"), cv2.resize(tablet.square(image), (480, 480), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 92])
                lines.append(f"{kind}_{taken}.jpg: {name.split('/')[-1]}")
                if taken == PER_KIND:
                    break
            print(f"{kind}: {taken} saved")
    (tablet.DEMO_FOLDER / "SOURCES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
