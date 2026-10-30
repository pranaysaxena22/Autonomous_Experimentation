"""Health check for the instruments (the barcode scanner and the balance) and the barcode pipeline through the cell, as far as it can be built and proved without hardware.

In plain words it checks that: a vial label is built and recognised the way the layout says (and a bad label format is refused in words); the serial barcode scanner driver, talking to a pretend scanner that plays back what a real one would say (a clean read, a read with
line endings and spaces, noise, a different vial, nothing at all), gives the right verdict each time; the serial balance driver (the common SICS text style) reads a stable weight, asks again while the balance is still settling, converts milligrams and kilograms, and says
plainly when the balance is overloaded, busy, silent or garbled; the dose check says under, over or ok; the simulated devices behave and repeat; with nothing scripted every run of the three examples is byte for byte what it was before this part existed; a scripted fault
at the scan (an unreadable label that a second try reads, one that stays unreadable, a wrong vial) plays out as it should (the vial is turned and read again, with no powder purge; a wrong vial is put back and the candidate skipped, with an alert that says a person must look),
the label format and the number of retries really come from the layout; a pretend REAL scanner plugged into the executor makes the same decisions on its own (right vial, a different vial, unreadable and then readable); a run with a scan fault is saved, its 3D replay is built, and the
dashboard draws all its pages and shows the alert; and the new part imports nothing from the project and touches no network. Nothing is written into the project.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

from cellpoc import run_store  # noqa: E402
from cellpoc.executor import ExecutorRefusal  # noqa: E402
from cellpoc.executor.stand_in import PythonStandInExecutor  # noqa: E402
from cellpoc.instruments import (FakeTransport, Instruments, LabelFormat, ScanResult, SerialBarcodeScanner, SicsBalance, SimulatedBalance, SimulatedBarcodeScanner,  # noqa: E402
                                 TransportError, classify, dose_check, format_from_layout)
from cellpoc.platform_runner import build_replay, load_inputs, run_platform, run_setup, save_platform_run  # noqa: E402
from cellpoc.planner import plan_trial  # noqa: E402,F401
from cellpoc.setup import example_choices  # noqa: E402
from checks import architecture  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

# Recorded on 2026-10-14 from the code BEFORE the instruments part existed: for each example, the number of trials and a fingerprint of every plan and executed timeline.
# Re-recorded on 2026-10-30 after the engine's reason sentence was corrected (the plans carry that sentence as their 'why'): with the sentence left out, every plan and executed timeline of all three examples
# is byte for byte what it was on 2026-10-14 (checked), so only the wording changed. The numbers recorded on 2026-10-14 were Example 1 24cd0a20..., Example 2 a78c8477..., Example 3 8cdbc3ac...
GOLDEN = {"Example 1": [30, "deabe6a8fa699973ca368857dbe6a940b0f8438e772d7c910e79b7dfe59cc893"], "Example 2": [42, "c6d7daa4e2710b4c7b8e049a5fe689b122231d2def90d407418ad731767f5372"],
          "Example 3": [24, "e96686ebe78e4b7c0d2a8e603cd172935755271492e0d27b2bad48cfd6b500c2"]}


def fingerprint(run) -> str:
    return hashlib.sha256(json.dumps({"executed": run.executed, "plans": run.plans}, sort_keys=True, default=str).encode()).hexdigest()


def scan_fault_run(setup, layout, settings, cause: str, retry_ok: bool, trial: int = 3):
    s = copy.deepcopy(setup)
    s["faults"]["scripted"] = [{"trial": trial, "where": {"step": "dispense", "action": "scan"}, "cause": cause, "retry_succeeds": retry_ok}]
    return run_setup(s, layout, settings)


def types(timeline: dict) -> list[str]:
    return [a["type"] + ("*" if a["origin"] == "recovery" else "") for a in timeline["actions"][:6]]


def main() -> int:
    cl = Checklist("INSTRUMENTS and the barcode pipeline: scanner and balance drivers, the scan fault through the cell, a pretend real scanner in the executor")
    before = project_files()

    # ---------------------------------------------------------------- labels
    default, custom = LabelFormat(), LabelFormat("VIAL", 4)
    refused = []
    for bad in ((" ", 3), ("V-", 0), ("V-", 99), ("way-too-long-prefix", 3), ("V!", 3)):
        try:
            LabelFormat(*bad)
        except ValueError as error:
            refused.append(len(str(error)) > 20)
    cl.record(default.label(8) == "V-008" and custom.label(3) == "VIAL0003" and default.matches("V-123") and not default.matches("V-12") and not default.matches("X-123") and not default.matches("V-123 ")
              and default.trial_of("V-042") == 42 and default.trial_of("junk") is None and len(refused) == 5 and all(refused),
              "A vial label is built from the prefix and the trial number and recognised only when it has exactly that shape (V-008, VIAL0003); a bad prefix or digit count is refused in words",
              f"{default.label(8)}, {custom.label(3)}; refused {len(refused)}/5")

    # ---------------------------------------------------------------- the serial barcode scanner against a pretend scanner
    fmt = LabelFormat()

    def scan(replies, trigger=None):
        t = FakeTransport(replies)
        return SerialBarcodeScanner(t, fmt, trigger=trigger).read(), t
    clean, _ = scan(["V-008"])
    padded, _ = scan([b"  V-008\r\n"])
    silent, _ = scan([None])
    noise, _ = scan(["\x02\x03##??"])
    other, _ = scan(["V-007"])
    empty, _ = scan([b""])
    _, triggered = scan(["V-008"], trigger=b"\x16T\r")
    verdicts = [classify(r, "V-008") for r in (clean, padded, silent, noise, other, empty)]
    cl.record(verdicts == ["ok", "ok", "unreadable", "unreadable", "wrong_vial", "unreadable"] and clean.text == "V-008" and noise.status == "garbled" and noise.raw and silent.status == "unreadable" and triggered.written == [b"\x16T\r"],
              "The serial barcode scanner driver, talking to a pretend scanner, gives the right verdict for a clean read, a read with spaces and line endings, silence, noise, an empty line and a different vial's label (and sends its trigger when it has one)", f"{verdicts}")

    # ---------------------------------------------------------------- the serial balance against a pretend balance
    def weigh(replies):
        t = FakeTransport(replies)
        return SicsBalance(t, attempts=3).read(), t
    stable, wire = weigh(["S S     12.3456 g"])
    settling, _ = weigh(["S D     12.1000 g", "S D     12.3000 g", "S S     12.3456 g"])
    never, _ = weigh(["S D 1.0 g", "S D 1.1 g", "S D 1.2 g"])
    milli, _ = weigh(["S S   4710.0 mg"])
    kilo, _ = weigh(["S S   0.5000 kg"])
    over, _ = weigh(["S +"])
    under, _ = weigh(["S -"])
    busy, _ = weigh(["S I", "S I", "S I"])
    silent_b, _ = weigh([None, None, None])
    garbled, _ = weigh(["hello", "??", "S S abc g"])
    tare_ok, tare_wire = SicsBalance(FakeTransport(["T S     0.0000 g"])).tare(), None
    tare_bad = SicsBalance(FakeTransport([None])).tare()
    statuses = [stable.status, settling.status, never.status, milli.status, kilo.status, over.status, under.status, busy.status, silent_b.status, garbled.status]
    cl.record(statuses == ["ok", "ok", "unstable", "ok", "ok", "overload", "underload", "busy", "timeout", "garbled"] and stable.grams == 12.3456 and settling.grams == 12.3456 and milli.grams == 4.71 and kilo.grams == 500.0 and wire.written == [b"S\r\n"] and tare_ok and not tare_bad,
              "The serial balance driver (SICS text style) reads a stable weight, asks again while the balance is still settling (and says so if it never settles), converts mg and kg to grams, says overload, underload, busy, silent and garbled plainly, and tares", f"{statuses}")
    cl.record([dose_check(10, v, 2) for v in (10.0, 10.19, 10.21, 9.81, 9.79, 0)] == ["ok", "ok", "over", "ok", "under", "under"] and dose_check(0, 0, 5) == "ok",
              "The dose check says ok, over or under against a percentage tolerance (2% of 10 g: 9.80 to 10.20 g are fine)", "")

    # ---------------------------------------------------------------- the simulated devices
    a, b = SimulatedBalance(noise_g=0.05, seed=1), SimulatedBalance(noise_g=0.05, seed=1)
    for g in (4.71, 6.0):
        a.add(g)
        b.add(g)
    quiet = SimulatedBalance()
    quiet.add(4.71)
    quiet.add(6.0)
    zeroed = quiet.tare()
    s1 = SimulatedBarcodeScanner("V-003", "unreadable", True)
    first, second = s1.read(), s1.read()
    s2 = SimulatedBarcodeScanner("V-003", "unreadable", False)
    s3 = SimulatedBarcodeScanner("V-003", "wrong_vial", True, "V-002")
    cl.record(a.read() == b.read() and a.read().grams != 10.71 and quiet.total == 0.0 and zeroed and first.status == "unreadable" and second.text == "V-003" and s2.read().status == "unreadable" and s2.read().status == "unreadable"
              and s3.read().text == "V-002" and s3.read().text == "V-002" and SimulatedBarcodeScanner("V-003").read().text == "V-003",
              "The simulated devices behave and repeat: a balance adds what is poured (the same seeded noise gives the same reading), tares to zero; a scanner reads right, is unreadable once then fine, stays unreadable, or reads another vial every time", "")

    # ---------------------------------------------------------------- nothing scripted: the three examples are exactly what they were
    now = {}
    for label, path in example_choices():
        run = run_platform(path)
        now[label.split(":")[0]] = [len(run.executed), fingerprint(run)]
    cl.record(now == GOLDEN, "With nothing scripted, every plan and executed timeline of all three examples (96 trials in all) is byte for byte what it was before the instruments part existed", f"{[(k, v[0]) for k, v in now.items()]}; same: {now == GOLDEN}")

    # ---------------------------------------------------------------- a scan fault through the cell
    setup, layout, settings = load_inputs()
    ok_run = scan_fault_run(setup, layout, settings, "barcode unreadable", True)
    stays = scan_fault_run(setup, layout, settings, "barcode unreadable", False)
    wrong = scan_fault_run(setup, layout, settings, "wrong vial scanned", True)
    t1, t2, t3 = ok_run.executed[2], stays.executed[2], wrong.executed[2]
    al = lambda run: [x for x in run.record.alerts if x.trial == 3]          # noqa: E731
    purge = lambda t: any(a["origin"] == "recovery" and a["type"] == "wait" and a["actual_duration_s"] >= 600 for a in t["actions"])          # noqa: E731
    cl.record(t1["outcome"] == "completed_after_recovery" and types(t1) == ["pick", "scan", "wait*", "scan*", "place", "wait"] and not purge(t1) and t1["actions"][2]["actual_duration_s"] == 5 and t1["faults"][0]["recovered"] is True
              and t1["actions"][1]["reading"] == {"quantity": "barcode", "value": "not read", "expected": "V-003"} and t1["actions"][3]["reading"] == {"quantity": "barcode", "value": "V-003"}
              and [(x.severity, "rescanned" in x.message) for x in al(ok_run)] == [("Recovered", True)] and t1["result"]["verdict"] in ("Good", "Not good"),
              "An unreadable label that a second try reads: the failed scan, then the vial turned a quarter turn (5 s, no powder purge), then the rescan; the trial carries on to a result and the alert says Recovered and 'rescanned'", f"{types(t1)}")
    cl.record(t2["outcome"] == "skipped" and types(t2)[:5] == ["pick", "scan", "wait*", "scan*", "place*"] and t2["result"]["verdict"] == "No result" and [(x.severity, x.needs_human) for x in al(stays)] == [("Needs attention", True)] and not purge(t2),
              "A label that stays unreadable: after the rescan the vial is put back, the candidate is skipped with no result and an alert for staff is queued", f"{types(t2)}")
    cl.record(t3["outcome"] == "skipped" and types(t3)[:4] == ["pick", "scan", "place*", "move"] and t3["faults"][0]["cause"] == "wrong vial scanned" and t3["actions"][1]["reading"] == {"quantity": "barcode", "value": "V-002", "expected": "V-003"}
              and "different vial" in t3["actions"][1]["fault"]["detail"] and [(x.severity, "person must check" in x.message) for x in al(wrong)] == [("Needs attention", True)] and not any(a["type"] == "pour" for a in t3["actions"]),
              "A wrong vial (the scanner reads another trial's label): no retry, the vial is put back, nothing is poured, the candidate is skipped and the alert says a person must check the rack", f"{types(t3)}")

    # ---------------------------------------------------------------- the layout decides the label format and the retries
    lay2 = copy.deepcopy(layout)
    lay2["instruments"] = {"barcode": {"prefix": "VIAL", "digits": 4, "retries": 0, "rotate_s": 9}}
    schema_ok = not list(Draft202012Validator(json.loads((ROOT / "cellpoc" / "formats" / "schemas" / "layout.schema.json").read_text(encoding="utf-8"))).iter_errors(lay2))
    normal = run_setup(setup, lay2, settings).executed[2]
    no_retry = scan_fault_run(setup, lay2, settings, "barcode unreadable", True).executed[2]
    lay3 = copy.deepcopy(layout)
    lay3["instruments"] = {"barcode": {"retries": 2, "rotate_s": 12}}
    twice = scan_fault_run(setup, lay3, settings, "barcode unreadable", False).executed[2]
    rotates = [a for a in twice["actions"] if a["id"].startswith("R") and a["type"] == "wait"]
    cl.record(schema_ok and format_from_layout(lay2) == LabelFormat("VIAL", 4) and normal["actions"][1]["reading"]["value"] == "VIAL0003" and no_retry["outcome"] == "skipped" and not any(a["type"] == "wait" and a["id"].startswith("R") for a in no_retry["actions"])
              and len(rotates) == 2 and rotates[0]["actual_duration_s"] == 12,
              "The label format, the number of retries and the turn time come from the layout (VIAL0003 on the label; no retries means an unreadable scan skips at once; two retries turn the vial twice, 12 s each); nothing is built into the code", f"label {normal['actions'][1]['reading']['value']}; turns {len(rotates)}")

    # ---------------------------------------------------------------- a pretend REAL scanner in the executor: the executor decides by itself
    executor = PythonStandInExecutor()
    layout_fmt = format_from_layout(layout)
    plan = ok_run.plans[2]

    def with_device(replies, scripted_fault=None):
        scanner = SerialBarcodeScanner(FakeTransport(replies), layout_fmt)
        return executor.execute(plan, setup, layout, scripted_fault, ok_run_readings, True, None, Instruments(scanner, SimulatedBalance()))
    from cellpoc.executor import NoReadings
    ok_run_readings = NoReadings()
    good = with_device(["V-003"])
    other = with_device(["V-009"])
    glitch = with_device([None, "V-003"])
    junk = with_device(["???", "garbage"])
    from cellpoc.executor import Fault
    try:
        with_device(["V-003"], Fault("dispense", "scan", "barcode unreadable", True))
        hardware_refusal = False
    except ExecutorRefusal as error:
        hardware_refusal = "simulated scanner" in str(error)
    cl.record(good["outcome"] == "completed" and good["actions"][1]["outcome"] == "ok" and good["actions"][1]["reading"]["value"] == "V-003"
              and other["outcome"] == "skipped" and other["faults"][0]["cause"] == "wrong vial scanned" and glitch["outcome"] == "completed_after_recovery" and glitch["faults"][0]["cause"] == "barcode unreadable"
              and junk["outcome"] == "skipped" and junk["faults"][0]["cause"] == "barcode unreadable" and hardware_refusal,
              "A pretend REAL scanner (the serial driver on a pretend cable) plugged into the executor with no scripted fault: the right label carries on, another vial's label stops the trial (wrong vial), a silent first read then a good one recovers by rescanning, noise twice skips it; and a scripted scan fault is refused when a real scanner is in use",
              f"right {good['outcome']}; other {other['outcome']}; glitch {glitch['outcome']}; junk {junk['outcome']}")

    # ---------------------------------------------------------------- a run with a scan fault: saved, replayed, opened by the dashboard
    from checks.stage8_check import render
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "run"
        from cellpoc.platform_runner import about_for, platform_info
        from cellpoc.setup import example_setup_path, load_setup
        wrong.record.platform = platform_info(wrong, load_setup(example_setup_path()).base_dir)             # what run_platform adds, so the dashboard treats it as a platform run
        wrong.record.about = about_for(wrong, wrong.record.platform)
        save_platform_run(wrong, folder)
        build_replay(wrong, folder)
        loaded = run_store.load(folder)
        app = render(folder)
        text = "\n".join(m.value for m in app.markdown) + "\n".join(c.value for c in app.caption)
        replay_text = (folder / "replay.html").read_text(encoding="utf-8") if (folder / "replay.html").exists() else ""
        cl.record(loaded.platform is not None and not app.exception and len(app.tabs) == 9 and "wrong vial" in text.lower() and "V-002" in replay_text and "different vial" in replay_text,
                  "A run with a scan fault is saved, its 3D replay is built (it carries the scanned label and the fault's detail), and the dashboard opens it: all nine pages draw with no error and the wrong-vial alert is on the page",
                  f"tabs {len(app.tabs)}; exception {[str(e.value)[:60] for e in app.exception]}")

    # ---------------------------------------------------------------- the new part is self-contained
    part = ROOT / "cellpoc" / "instruments"
    imports = [line for p in part.glob("*.py") for line in p.read_text(encoding="utf-8").splitlines() if line.startswith(("import ", "from ")) and "cellpoc" in line]
    cl.record(architecture.ALLOWED["instruments"] == set() and not imports and architecture.ALLOWED["executor"] == {"planner", "instruments"}, "The instruments part imports nothing from the project, and only the executor may use it", f"{len(list(part.glob('*.py')))} files")
    try:
        from cellpoc.instruments import SerialTransport
        SerialTransport("COM_NOT_THERE")
        port_error = None
    except TransportError as error:
        port_error = str(error)
    cl.record(port_error is not None and len(port_error) > 40 and "Traceback" not in port_error,
              "Opening a real serial port that is not there (or without the pyserial package) fails in plain words that say what to check, never with a technical trace", (port_error or "")[:110])
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    os.environ.pop("CELLPOC_RECORD", None)
    sys.exit(main())
