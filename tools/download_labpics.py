"""Downloads the public LabPics (version 1) dataset used to train the vision model: 2,187 photographs of liquids and solids in vessels, with each vessel and each material region outlined by hand.

Source: https://zenodo.org/records/3697452 (Sagi Eppel, 'LabPics', MIT licence). It is a 3 GB file; one connection is slow, so it is fetched in pieces on several connections at once and can be resumed by running it again.
The file goes to data/public/labpics (not saved in git). This is the only thing in the project that uses the internet, and only when you run it.

    .venv\\Scripts\\python.exe tools\\download_labpics.py
"""
from __future__ import annotations

import sys
import threading
import time
import urllib.request
from pathlib import Path

URL = "https://zenodo.org/records/3697452/files/LabPicsV1.zip?download=1"
TARGET = Path(__file__).resolve().parents[1] / "data" / "public" / "labpics" / "LabPicsV1.zip"
PIECES = 24
CONNECTIONS = 8


def size() -> int:
    request = urllib.request.Request(URL, method="HEAD", headers={"User-Agent": "cell-poc-training-data/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.headers["Content-Length"])


def fetch(index: int, start: int, end: int, state: dict) -> None:
    done_marker = TARGET.with_suffix(f".part{index}")
    while True:
        have = done_marker.stat().st_size if done_marker.exists() else 0
        if start + have > end:
            return
        request = urllib.request.Request(URL, headers={"Range": f"bytes={start + have}-{end}", "User-Agent": "cell-poc-training-data/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(done_marker, "ab") as out:
                while True:
                    block = response.read(1 << 20)
                    if not block:
                        break
                    out.write(block)
                    with state["lock"]:
                        state["bytes"] += len(block)
        except Exception:                      # a dropped connection: wait a moment and carry on from where the piece stopped
            time.sleep(3)


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.exists() and TARGET.stat().st_size > 2_900_000_000:
        print("Already downloaded:", TARGET)
        return 0
    total = size()
    step = -(-total // PIECES)
    ranges = [(i, i * step, min(total - 1, (i + 1) * step - 1)) for i in range(PIECES)]
    state = {"lock": threading.Lock(), "bytes": sum(TARGET.with_suffix(f".part{i}").stat().st_size for i, _, _ in ranges if TARGET.with_suffix(f".part{i}").exists())}
    queue = list(ranges)
    queue_lock = threading.Lock()

    def worker():
        while True:
            with queue_lock:
                if not queue:
                    return
                index, start, end = queue.pop(0)
            fetch(index, start, end, state)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(CONNECTIONS)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        print(f"\r{state['bytes'] / 1e6:,.0f} MB of {total / 1e6:,.0f} MB", end="", flush=True)
        time.sleep(5)
    print()
    with open(TARGET, "wb") as out:
        for i, _, _ in ranges:
            part = TARGET.with_suffix(f".part{i}")
            with open(part, "rb") as source:
                while True:
                    block = source.read(1 << 22)
                    if not block:
                        break
                    out.write(block)
            part.unlink()
    print("Saved:", TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
