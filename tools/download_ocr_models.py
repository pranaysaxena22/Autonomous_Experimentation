"""Downloads the two small text-reading models the cell uses to read the printed NAME on an ingredient bottle's sticker: a text finder (PP-OCRv3, English, 2.4 MB) and a text reader (CRNN, English, 34 MB).

Source: OpenCV's model collection, https://github.com/opencv/opencv_zoo (models/text_detection_ppocr and models/text_recognition_crnn; the collection is Apache-2.0 licensed). They run through OpenCV itself, so no library is added to the project.
The files go to data/vision_models/ocr (not saved in git). This is one of the few things in the project that uses the internet, and only when you run it.

    .venv\\Scripts\\python.exe tools\\download_ocr_models.py
"""
from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models/"
FILES = {
    "text_detection_en_ppocrv3_2023may.onnx": BASE + "text_detection_ppocr/text_detection_en_ppocrv3_2023may.onnx",
    "text_recognition_CRNN_EN_2021sep.onnx": BASE + "text_recognition_crnn/text_recognition_CRNN_EN_2021sep.onnx",
}
FOLDER = Path(__file__).resolve().parents[1] / "data" / "vision_models" / "ocr"


def main() -> int:
    FOLDER.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        target = FOLDER / name
        if target.exists() and target.stat().st_size > 1_000_000:
            print("Already downloaded:", name)
            continue
        part = target.with_suffix(".part")
        total = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "cell-poc-training-data/1.0"}), timeout=60).headers["Content-Length"])
        for attempt in range(20):                      # a dropped connection: carry on from where the file stopped
            have = part.stat().st_size if part.exists() else 0
            if have >= total:
                break
            request = urllib.request.Request(url, headers={"Range": f"bytes={have}-", "User-Agent": "cell-poc-training-data/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response, open(part, "ab") as out:
                    while True:
                        block = response.read(1 << 18)
                        if not block:
                            break
                        out.write(block)
            except Exception:                          # noqa: BLE001
                time.sleep(2)
        if not part.exists() or part.stat().st_size != total:
            print("Could not finish", name, "- run this again.")
            return 1
        part.replace(target)
        print("Saved:", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
