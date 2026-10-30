"""Health check for Stage 10, hardening: try to break the platform on purpose, and prove it works on a clean copy of the project, with no network, with odd folder names, and within sensible time.

In plain words it checks that: bad setup files (missing, empty, binary rubbish, not a setup at all, a layout that is not there, a setup with errors) are each refused in plain words and never crash with a technical trace;
a data file that is missing or is rubbish does not stop a platform run but is reported plainly on the data page; a setup with a long, accented, non-Latin project name in a folder whose name has spaces and accents runs end
to end and its files (page, CSV, Excel) show the name correctly; the whole chain (setup, run, record, plans, executed timelines, replay, reports) is consistent on one set of numbers (30 trials everywhere); two runs from the
same setup give identical record, plan and timeline files; a platform run, its replay and its reports are written with every network call blocked; a clean copy of the project (only the files that are saved in git or about
to be, in a folder with spaces and accents, with no run output) runs the platform and passes the planner and executor checks, using its own code and not this folder's; every double-click launcher in the project folder
is explained in the README; the guides become branded, labelled pages; every run takes less than a generous time limit (the times are shown); and nothing is written into the project.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc import run_store  # noqa: E402
from cellpoc.platform_runner import PlatformRunError, build_replay, run_platform, save_platform_run  # noqa: E402
from cellpoc.reports import brand, write_reports  # noqa: E402
from cellpoc.setup import example_setup_path  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

TECHNICAL = re.compile(r"Traceback|KeyError|TypeError|ValueError|AttributeError|NoneType|IndexError|\{|\}|<class|object at 0x")
UNICODE_NAME = "Étude Ünïcode 日本語 ταμπλέτες " + "long name " * 4        # 80 characters is the longest name the setup allows; this is 71
BUDGET = {"a platform run": 120.0, "the replay file": 30.0, "the report files (no PDF)": 40.0, "reading the record": 15.0}


def refused_plainly(setup_path: Path) -> tuple[bool, str]:
    """(True, message) when the run is refused with a plain message; (False, text) when it crashed or ran."""
    try:
        run_platform(setup_path)
    except PlatformRunError as exc:
        return (not TECHNICAL.search(str(exc)) and len(str(exc)) > 25), str(exc)
    except Exception as exc:  # noqa: BLE001 - this is what the check is looking for
        return False, f"CRASHED with {type(exc).__name__}: {str(exc)[:80]}"
    return False, "it ran"


def breaking_checks(cl: Checklist, tmp: Path) -> None:
    base = yaml.safe_load(example_setup_path().read_text(encoding="utf-8"))
    cases: dict[str, Path] = {}

    def write(name: str, content: str | bytes) -> Path:
        p = tmp / "broken" / name
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return p

    cases["a file that is not there"] = tmp / "broken" / "nope.yaml"
    cases["an empty file"] = write("empty.yaml", "")
    cases["binary rubbish"] = write("rubbish.yaml", bytes(range(256)) * 20)
    cases["text that is not a setup (a list)"] = write("list.yaml", "- one\n- two\n")
    cases["text that is not a setup (a number)"] = write("number.yaml", "42")
    cases["broken YAML"] = write("broken.yaml", "project: [unclosed\n  name: x: y: z\n")
    wrong = dict(base)
    wrong["format_version"] = 999
    cases["a setup from a future version"] = write("future.yaml", yaml.safe_dump(wrong))
    nolayout = yaml.safe_load(yaml.safe_dump(base))
    nolayout["equipment"]["layout_file"] = "no_such_layout.json"
    cases["a layout file that is not there"] = write("nolayout.yaml", yaml.safe_dump(nolayout))
    errors = yaml.safe_load(yaml.safe_dump(base))
    errors["ingredients"][0]["min"] = 400
    cases["a setup with an error in it"] = write("errors.yaml", yaml.safe_dump(errors))
    outside = yaml.safe_load(yaml.safe_dump(base))
    outside["equipment"]["layout_file"] = "..\\..\\..\\Windows\\win.ini"
    cases["a file name that points outside the project"] = write("outside.yaml", yaml.safe_dump(outside))
    results = {name: refused_plainly(path) for name, path in cases.items()}
    bad = {k: v[1][:70] for k, v in results.items() if not v[0]}
    cl.record(not bad, f"{len(cases)} deliberately bad setups (missing, empty, rubbish, not a setup, broken, future version, missing layout, an error, a path outside the project) are each refused in plain words, never a crash", "; ".join(f"{k}: {v}" for k, v in bad.items()) or f"{len(cases)} refused")

    # a data file that is missing or rubbish does not stop the run, but is said plainly on the data page
    for name, make in (("missing", None), ("rubbish", bytes(range(256)) * 50)):
        s = yaml.safe_load(yaml.safe_dump(base))
        folder = tmp / f"data_{name}"
        folder.mkdir()
        s["data"]["experiments_file"] = "experiments_here.csv"
        s["data"].pop("meta_file", None)
        if make is not None:
            (folder / "experiments_here.csv").write_bytes(make)
        (folder / "setup.yaml").write_text(yaml.safe_dump(s), encoding="utf-8")
        try:
            run = run_platform(folder / "setup.yaml")
            lines = run.record.platform.data_lines + run.record.platform.model_lines
            plain = all(not TECHNICAL.search(x) for x in lines) and len(run.record.platform.data_lines) >= 1
            cl.record(plain and len(run.record.trials) > 0, f"A data file that is {name} does not stop the platform run, and the data page says so in plain words", lines[0][:80])
        except PlatformRunError as exc:
            cl.record(not TECHNICAL.search(str(exc)), f"A data file that is {name} is refused in plain words", str(exc)[:80])
        except Exception as exc:  # noqa: BLE001
            cl.record(False, f"A data file that is {name} does not crash the platform run", f"{type(exc).__name__}: {str(exc)[:80]}")

    bad_records = {}
    for name, text in (("empty", ""), ("rubbish", "}{ not json"), ("wrong shape", '["a"]')):
        folder = tmp / f"record_{name.replace(' ', '_')}"
        folder.mkdir()
        (folder / "record.json").write_text(text, encoding="utf-8")
        try:
            run_store.load(folder)
            bad_records[name] = "it loaded"
        except Exception:  # noqa: BLE001 - any failure is fine for the store; the dashboard and the reports turn it into plain words
            try:
                write_reports(folder, tmp / "never_made")
                bad_records[name] = "reports were written"
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ != "ReportError" or TECHNICAL.search(str(exc)):
                    bad_records[name] = f"{type(exc).__name__}"
    cl.record(not bad_records, "A run record that is empty, rubbish or the wrong shape is refused by the report writer in plain words", ", ".join(f"{k}: {v}" for k, v in bad_records.items()) or "3 refused")


def unicode_and_spaces(cl: Checklist, tmp: Path) -> None:
    base = yaml.safe_load(example_setup_path().read_text(encoding="utf-8"))
    base["project"]["name"] = UNICODE_NAME
    folder = tmp / "Mappe mit Leerzeichen é ü ñ"
    folder.mkdir()
    path = folder / "setup naïve.yaml"
    path.write_text(yaml.safe_dump(base, allow_unicode=True), encoding="utf-8")
    t0 = time.perf_counter()
    run = run_platform(path)
    out = folder / "run output"
    save_platform_run(run, out)
    build_replay(run, out)
    result = write_reports(out, pdf=False)
    seconds = time.perf_counter() - t0
    page = (out / "reports" / "report.html").read_text(encoding="utf-8")
    from openpyxl import load_workbook
    wb = load_workbook(out / "reports" / "report.xlsx")
    sheet_ok = UNICODE_NAME in " ".join(str(c.value) for row in wb["Data and model"].iter_rows() for c in row if c.value)
    shown = run.record.platform.setup_name == UNICODE_NAME and UNICODE_NAME.split()[0] in page and "日本語" in page
    cl.record(len(UNICODE_NAME) <= 80 and shown and (out / "replay.html").exists() and len(result.files) == 5 and sheet_ok and (out / "platform_index.json").exists(),
              "A setup with a long, accented, non-Latin project name, in folders with spaces and accents in their names, runs end to end; the page shows the name correctly, and the files are all written", f"{len(run.record.trials)} trials in {seconds:.1f} s")
    index = json.loads((out / "platform_index.json").read_text(encoding="utf-8"))
    cl.record(all(not Path(t["plan_file"]).is_absolute() and not Path(t["executed_file"]).is_absolute() and "\\" not in t["plan_file"] for t in index["trials"]) and not Path(index["layout_file"]).is_absolute(),
              "The index of a saved run uses only relative file names with forward slashes (so a run folder can be moved or sent as a whole)")


def chain_consistency(cl: Checklist, tmp: Path) -> None:
    t0 = time.perf_counter()
    run = run_platform()
    t_run = time.perf_counter() - t0
    out = tmp / "chain"
    save_platform_run(run, out)
    t0 = time.perf_counter()
    build_replay(run, out)
    t_replay = time.perf_counter() - t0
    t0 = time.perf_counter()
    write_reports(out, pdf=False)
    t_reports = time.perf_counter() - t0
    t0 = time.perf_counter()
    record = run_store.load(out)
    t_read = time.perf_counter() - t0
    n = len(record.trials)
    page = (out / "replay.html").read_text(encoding="utf-8")
    embedded = json.loads(re.search(r'<script type="application/json" id="data-timelines">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))
    counts = {"record": n, "plans": len(list((out / "plans").glob("*.json"))), "executed": len(list((out / "executed").glob("*.json"))), "replay": len(embedded), "index": len(json.loads((out / "platform_index.json").read_text(encoding="utf-8"))["trials"]),
              "platform text": len(record.platform.trial_rows), "csv": sum(1 for _ in (out / "reports" / "trials.csv").open(encoding="utf-8")) - 1}
    cl.record(len(set(counts.values())) == 1 and n > 0, "The whole chain agrees on the number of trials: the record, the plan files, the executed timelines, the 3D replay, the index, the data page text and the CSV table", ", ".join(f"{k} {v}" for k, v in counts.items()))
    same_trials = [e["trial"] for e in embedded] == [t.trial for t in record.trials]
    outcomes = all((e["outcome"] == "skipped") == (t.status == "Skipped") for e, t in zip(embedded, record.trials))
    cl.record(same_trials and outcomes, "...and the replay's trials are the record's trials, in the same order, with the same skipped ones")
    run2 = run_platform()
    out2 = tmp / "chain2"
    save_platform_run(run2, out2)
    names = ["record.json", "platform_index.json", "layout.json"] + [f"plans/{p.name}" for p in (out / "plans").glob("*.json")] + [f"executed/{p.name}" for p in (out / "executed").glob("*.json")]
    cl.record(all((out / n_).read_bytes() == (out2 / n_).read_bytes() for n_ in names), "Two runs from the same setup give identical record, plan and executed-timeline files (the same seeds give the same run)", f"{len(names)} files compared")
    size = (out / "record.json").stat().st_size, (out / "replay.html").stat().st_size
    cl.record(t_run < BUDGET["a platform run"] and t_replay < BUDGET["the replay file"] and t_reports < BUDGET["the report files (no PDF)"] and t_read < BUDGET["reading the record"] and size[0] < 20_000_000 and size[1] < 6_000_000,
              "Every step is within a generous time and size limit", f"run {t_run:.1f} s, replay {t_replay:.1f} s, reports {t_reports:.1f} s, reading the record {t_read:.1f} s; record {size[0] // 1024} KB, replay {size[1] // 1024} KB")


NETWORK_BLOCK = '''
import socket, sys
def blocked(*a, **k):
    raise OSError("the check blocked this network call")
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked
socket.create_connection = blocked
socket.gethostbyname = blocked
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from cellpoc.platform_runner import build_replay, run_platform, save_platform_run
from cellpoc.reports import write_reports
run = run_platform()
out = Path(sys.argv[2])
save_platform_run(run, out)
build_replay(run, out)
write_reports(out, pdf=False)
print("DONE", len(run.record.trials), (out / "replay.html").exists(), (out / "reports" / "report.xlsx").exists())
'''


def no_network(cl: Checklist, tmp: Path) -> None:
    script = tmp / "block_network.py"
    script.write_text(NETWORK_BLOCK, encoding="utf-8")
    done = subprocess.run([sys.executable, "-B", str(script), str(ROOT), str(tmp / "offline")], capture_output=True, text=True, timeout=600, cwd=tmp)
    ok = done.returncode == 0 and "DONE" in done.stdout and "True True" in done.stdout
    cl.record(ok, "A platform run, its replay file and its reports are all written with every network call blocked", done.stdout.strip()[-60:] if ok else (done.stderr.strip().splitlines() or ["no output"])[-1][:120])


def clean_copy(cl: Checklist, tmp: Path) -> None:
    try:
        listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        cl.skip("A clean copy of the project runs the platform and passes its checks", "git is not available here")
        return
    if listed.returncode != 0:
        cl.skip("A clean copy of the project runs the platform and passes its checks", "git could not list the files here")
        return
    copy = tmp / "Clean copy é test"
    count = 0
    for name in listed.stdout.splitlines():
        src = ROOT / name
        if src.is_file():
            dst = copy / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1
    where = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", "import cellpoc, sys; print(cellpoc.__file__)"], cwd=copy, capture_output=True, text=True, encoding="utf-8", errors="replace")
    own = Path(where.stdout.strip()).resolve().is_relative_to(copy.resolve()) if where.stdout.strip() else False
    run = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "cellpoc.platform_runner"], cwd=copy, capture_output=True, text=True, timeout=900, encoding="utf-8", errors="replace")
    made = all((copy / "runs" / "platform" / f).exists() for f in ("record.json", "replay.html", "reports/report.html", "reports/trials.csv"))
    cl.record(own and run.returncode == 0 and made, f"A clean copy of the project ({count} files, in a folder with spaces and an accent, no run output, no old results) uses its own code and writes a platform run, its replay and its reports",
              "" if own and run.returncode == 0 and made else (run.stderr.strip().splitlines() or [where.stdout])[-1][:140])
    for module in ("checks.planner_check", "checks.executor_check"):
        done = subprocess.run([sys.executable, "-B", "-m", module], cwd=copy, capture_output=True, text=True, timeout=900, encoding="utf-8", errors="replace")
        last = [line for line in done.stdout.splitlines() if " passed, " in line]
        cl.record(done.returncode == 0 and bool(last) and " 0 failed" in last[-1], f"In the clean copy, {module.split('.')[1]} passes", last[-1].strip() if last else "no result line")


def documentation(cl: Checklist) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bats = sorted(p.name for p in ROOT.glob("*.bat"))
    missing = [b for b in bats if b not in readme]
    cl.record(not missing, f"Every double-click launcher in the project folder ({len(bats)}) is explained in the README", f"not mentioned: {missing[:5]}" if missing else f"{len(bats)} launchers")
    sys.path.insert(0, str(ROOT / "tools"))
    import make_guides
    sources = sorted(p.stem for p in (ROOT / "docs" / "guides").glob("*.md"))
    cl.record(sources == sorted(make_guides.GUIDES), "Every guide in docs/guides has a page definition, and every definition has its Markdown source", ", ".join(sources))
    with tempfile.TemporaryDirectory() as out:
        make_guides.build_all(Path(out), pdf=False)
        palette = {c.upper() for c in brand.PALETTE}
        problems = []
        for name in make_guides.GUIDES:
            page = (Path(out) / f"{name}.html").read_text(encoding="utf-8")
            colours = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", page)}
            if not colours <= palette or "ILLUSTRATIVE" not in page or re.search(r"https?://(?!localhost)", page) or "font/ttf;base64" not in page or "<h2>" not in page:
                problems.append(name)
        cl.record(not problems, "Every guide becomes a branded page: only the Deloitte palette, the illustrative label, Open Sans inside the file, nothing pointing to the internet, with headings", ", ".join(problems) or f"{len(make_guides.GUIDES)} guides")
        words = {n: len(re.sub(r"<[^>]+>", " ", (Path(out) / f"{n}.html").read_text(encoding="utf-8").split("</style>")[1]).split()) for n in make_guides.GUIDES}
        cl.record(all(w > 300 for w in words.values()), "No guide is an empty shell (each has real content)", ", ".join(f"{k}: {v} words" for k, v in words.items()))


def main() -> int:
    cl = Checklist("PLATFORM STAGE 10 (hardening): break it on purpose, clean copy, no network, odd folder names, limits, documentation")
    before = project_files()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        breaking_checks(cl, tmp)
        unicode_and_spaces(cl, tmp)
        chain_consistency(cl, tmp)
        no_network(cl, tmp)
        clean_copy(cl, tmp)
    documentation(cl)
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
