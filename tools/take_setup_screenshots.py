r"""Takes a screenshot of each of the ten setup screens, with the example loaded and with a setup that has mistakes in it.

Run:  .venv\Scripts\python.exe tools\take_setup_screenshots.py
Needs Google Chrome (Edge's headless mode is blocked by the company's policy). Pictures go to docs/screenshots/ (not committed).
Starts the setup app on a spare local port for a few minutes and stops it again; nothing leaves this computer.
A temporary setup with mistakes is written to setups/ (never committed) and deleted afterwards.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.setup import SCREENS, example_setup_path, load_setup  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PORT = 8612
OUT = ROOT / "docs" / "screenshots"
BROKEN_NAME = "zz-screenshot-mistakes"
HEIGHTS = {9: 4200, 8: 4800, 1: 3000, 6: 3200}          # screen number -> taller window for the long screens; others use 2400
MIN_BYTES = 30_000                              # a page that never drew is a small, empty-looking file


def broken_setup() -> dict:
    """The example with a handful of typical mistakes (all illustrative)."""
    setup = load_setup(example_setup_path()).setup
    setup["project"]["name"] = ""
    setup["display"]["accent_colour"] = "green"
    setup["ingredients"][0]["min"], setup["ingredients"][0]["max"] = 40, 30
    setup["ingredients"][1]["id"] = setup["ingredients"][0]["id"]
    setup["process_factors"][0]["unit"] = "N"
    setup["targets"]["constraints"][1].update(low=12, high=10)
    setup["equipment"]["steps"][0]["stations"].append("teleporter")
    setup["equipment"]["phases"]["reason_min"] = 60
    setup["calendar"].update(staffed_from="18:00", staffed_until="08:00")
    setup["faults"]["scripted"][0]["trial"] = 99
    setup["baseline"]["manual_trials_per_week"] = 0
    setup["data"]["column_map"]["no_such_column"] = "drug_pct"
    setup["data"]["hardness"]["conversions"].pop("kP")
    return setup


def wait_for_server() -> bool:
    for _ in range(60):
        try:
            if urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2).read() == b"ok":
                return True
        except OSError:
            time.sleep(1)
    return False


def shoot(url: str, target: Path, height: int, profile: Path) -> str:
    """Take one picture. The browser sometimes photographs the page before it has drawn, so try again (fresh browser profile each time).
    The picture is made in a temporary folder and copied in, because OneDrive may briefly hold a file in the project folder."""
    outcome = "not tried"
    for attempt in range(6):
        work = Path(tempfile.mkdtemp(prefix="shot_work_"))
        try:
            outcome = shoot_once(url, work / "shot.png", height, work / "profile")
            if outcome == "ok":
                for _ in range(10):
                    try:
                        shutil.copyfile(work / "shot.png", target)
                        return "ok"
                    except OSError:
                        time.sleep(1)
                return "the picture was taken but could not be saved into docs/screenshots (the file is locked)"
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return outcome


def shoot_once(url: str, target: Path, height: int, profile: Path) -> str:
    command = [str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
               f"--window-size=1500,{height}", "--virtual-time-budget=600000", f"--screenshot={target}", url]
    try:
        subprocess.run(command, timeout=180, capture_output=True)
    except subprocess.TimeoutExpired:
        return "timed out"
    if not target.exists():
        return "no picture was written"
    if target.stat().st_size < MIN_BYTES:
        return f"the picture is only {target.stat().st_size} bytes: the page probably did not draw"
    return "ok"


def main() -> int:
    import yaml

    if not CHROME.exists():
        print("Google Chrome was not found at", CHROME, "- cannot take screenshots.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    setups = ROOT / "setups"
    made_folder = not setups.exists()
    setups.mkdir(exist_ok=True)
    broken = setups / f"{BROKEN_NAME}.yaml"
    broken.write_bytes(yaml.safe_dump(broken_setup(), sort_keys=False, allow_unicode=True).encode("utf-8"))
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "setup_app.py", "--server.port", str(PORT), "--server.headless", "true",
                               "--browser.gatherUsageStats", "false"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results: list[tuple[str, str]] = []
    profile = Path(tempfile.mkdtemp(prefix="setup_shots_"))
    try:
        if not wait_for_server():
            print("The setup app did not start in time.")
            return 1
        for state, query in (("example", "start=example"), ("mistakes", f"open={BROKEN_NAME}")):
            for number, name in enumerate(SCREENS, start=1):
                file = OUT / f"{number:02d}_{name.lower().replace(' ', '_')}_{state}.png"
                outcome = shoot(f"http://localhost:{PORT}/?{query}&screen={number}", file, HEIGHTS.get(number - 1, 2400), profile)
                results.append((file.name, outcome))
                print(f"{file.name}: {outcome}", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        broken.unlink(missing_ok=True)
        try:
            if made_folder and not any(setups.iterdir()):
                setups.rmdir()
        except OSError:
            pass                       # OneDrive can hold the folder for a moment; an empty folder is harmless
        shutil.rmtree(profile, ignore_errors=True)
    failed = [name for name, outcome in results if outcome != "ok"]
    print(f"\n{len(results) - len(failed)} of {len(results)} screenshots taken, saved in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
