"""Downloads the public PharmaVision tablet-photograph dataset used to train the tablet-inspection model: 640 smartphone photographs of tablets (320 normal, 320 defective: chips, cracks, abrasion, discolouration, broken, lamination), 224 x 224 pixels.

Source: https://www.kaggle.com/datasets/tahirlee/pharmaceutical-tablets-dataset (Tahir Lee et al., 'AI-Based Quality Control of Pharmaceutical Tablets', Pharmaceutics 2026; the authors' CODE is MIT-licensed; the DATASET's own licence text was not readable to me, but the project owner confirmed on 2026-10-23 that it may be used;
it is kept out of git and not redistributed). It is a 38 MB file fetched without an account. The file goes to data/public/pharmavision.
This is the only thing, besides tools/download_labpics.py, that uses the internet, and only when you run it.

    .venv\\Scripts\\python.exe tools\\download_pharmavision.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://www.kaggle.com/api/v1/datasets/download/tahirlee/pharmaceutical-tablets-dataset"
TARGET = Path(__file__).resolve().parents[1] / "data" / "public" / "pharmavision" / "pharmavision.zip"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.exists() and TARGET.stat().st_size > 30_000_000:
        print("Already downloaded:", TARGET)
        return 0
    request = urllib.request.Request(URL, headers={"User-Agent": "cell-poc-training-data/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, open(TARGET.with_suffix(".part"), "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            print(f"\r{done / 1e6:,.0f} MB of {total / 1e6:,.0f} MB", end="", flush=True)
    TARGET.with_suffix(".part").replace(TARGET)
    print("\nSaved:", TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
