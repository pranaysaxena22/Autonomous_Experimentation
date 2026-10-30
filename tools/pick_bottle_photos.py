"""Cuts five real photographs out of the downloaded LabPics TEST set (photographs the vision model never trained on), one for each solution colour the cell's ingredient bottles stand for, so the demo's vision check can use a real photograph.

Each photograph shows one clearly coloured liquid in a real beaker, jar or flask; the picks were made by looking at what the trained model read as exactly one vessel of that colour and then by eye. They are cropped to the vessel and saved in data/public/labpics/demo_bottles
(not saved in git: the photographs belong to the people who made the videos they come from, and LabPics is only a dataset of them; run this tool after tools/download_labpics.py to recreate them). The app uses them when they exist and draws a photograph otherwise.

    .venv\\Scripts\\python.exe tools\\pick_bottle_photos.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.vision import analyse  # noqa: E402

ZIP = ROOT / "data" / "public" / "labpics" / "LabPicsV1.zip"
OUT = ROOT / "data" / "public" / "labpics" / "demo_bottles"
PICKS = {
    "blue": "LabPicsV1/Complex/Test/Koen2All_Chemistry experiment 29 - Copper + nitric acid fountain-screenshot (6)",
    "yellow": "LabPicsV1/Complex/Test/NileRed_How to make Chloroform-screenshot (8)",
    "green": "LabPicsV1/Complex/Test/NileRed_How to extract Silver from a Coin (or other silver containing material)-screenshot (1)",
    "orange": "LabPicsV1/Complex/Test/NileRed_How to make Glycerine (Glycerol)-screenshot (8)",
    "purple": "LabPicsV1/Complex/Test/Koen2All_Chemistry experiment 21 - Blue bottle-screenshot (2)",
}


def main() -> int:
    if not ZIP.exists():
        print("The LabPics download is not there yet: run tools\\download_labpics.py first.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["Real photographs from the LabPics v1 TEST set (Sagi Eppel, https://zenodo.org/records/3697452, MIT licence), cropped to one vessel each. The pictures belong to the makers of the videos they were taken from.", ""]
    with zipfile.ZipFile(ZIP) as z:
        for colour, folder in PICKS.items():
            image = cv2.imdecode(np.frombuffer(z.read(folder + "/Image.png"), np.uint8), cv2.IMREAD_COLOR)
            found = analyse(image, engine="model")
            if len(found.vessels) != 1:
                print(f"{colour}: expected one vessel, the model sees {len(found.vessels)}; not saved")
                continue
            x, y, w, h = found.vessels[0].box
            height, width = image.shape[:2]
            left, right = max(0, int(x - 0.7 * w)), min(width, int(x + 1.7 * w))
            top, bottom = max(0, int(y - 1.2 * h)), min(height, int(y + 1.25 * h))
            crop = image[top:bottom, left:right]
            scale = 520 / crop.shape[1]
            crop = cv2.resize(crop, (520, int(round(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(OUT / f"{colour}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            lines.append(f"{colour}.jpg: {folder.replace('LabPicsV1/Complex/Test/', '')}")
            print(f"{colour}: saved ({crop.shape[1]}x{crop.shape[0]})")
    (OUT / "SOURCES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
