"""Health check for Stage 1 of the platform (setup, validation): the shared setup logic.

Checks, in plain words: the example setup is accepted; every rule has a test and every test passes; the messages are plain
English; a broken setup never crashes the validator (200 random mutations); older setups load and newer ones are refused;
a saved setup records when, with which program version and a fingerprint, and never a personal name; YAML is read safely;
the list of units lives in one place; the message document is up to date; the parts stay separate.
Nothing here needs the setup app screens (those are checked in a later sub-step).
"""
from __future__ import annotations

import getpass
import os
import platform
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.setup import (CATALOGUE, PROGRAM_VERSION, FormatSupport, Problem, SetupFileError, allowed_symbols, fingerprint,  # noqa: E402
                           has_errors, load_setup, save_setup, to_poc_settings, validate)
from cellpoc.setup import rules as rules_module  # noqa: E402
from cellpoc.setup import units as units_module  # noqa: E402
from cellpoc.setup.messages import render, rule_for  # noqa: E402
from checks import architecture, setup_app_tests, setup_cases, setup_mutation  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.setup_messages_doc import DOC_PATH, build_text  # noqa: E402

SETUP_PACKAGE = ROOT / "cellpoc" / "setup"


def example_loads_clean(cl: Checklist) -> None:
    loaded = load_setup(setup_cases.EXAMPLES / "setup_example.yaml")
    problems = validate(loaded.setup, base_dir=loaded.base_dir, strict=True)
    errors = [p.message for p in problems if p.level == "error"]
    cl.record(not loaded.problems and not errors, "The example setup is read and accepted with no errors",
              "; ".join(errors[:3]) if errors else f"{len(problems)} message(s): " + ", ".join(sorted({p.rule + ' ' + p.level for p in problems})))


def rule_tests(cl: Checklist, results: list[setup_cases.CaseResult]) -> None:
    failed = [r for r in results if not r.passed]
    cl.record(not failed, f"Each of the {len(results)} rule tests produces the right message at the right level, in plain English",
              "; ".join(f"{r.case.rule} {r.case.variant}: {' / '.join(r.notes)[:200]}" for r in failed[:3]) if failed else
              f"{len(CATALOGUE)} messages in the catalogue")
    missing = setup_cases.uncovered()
    cl.record(not missing, "Every rule in the message catalogue has at least one test",
              "no test for: " + ", ".join(f"{a} {b}".strip() for a, b in missing) if missing else f"{len(CATALOGUE)} of {len(CATALOGUE)} covered")
    # the coverage check must itself be able to fail
    CATALOGUE[("R99", "")] = rule_for("R05")
    try:
        caught = ("R99", "") in setup_cases.uncovered()
    finally:
        del CATALOGUE[("R99", "")]
    cl.record(caught, "Self-test: a rule added without a test is caught by the coverage check", "")


def wording_checks(cl: Checklist) -> None:
    def fake(text: str) -> Problem:
        return Problem("R99", "", "error", "Project", "Name", "project.name", text)

    bad = ["the schema is wrong", "value is null", "Traceback (most recent call last)", "got None", "KeyError: 'x'", "{unfilled}"]
    caught = [t for t in bad if setup_cases.wording_problems(fake(t))]
    cl.record(len(caught) == len(bad), "Self-test: the plain-English check catches technical wording (schema, null, None, traceback, key errors, unfilled blanks)",
              f"caught {len(caught)} of {len(bad)}")
    cl.record(not setup_cases.wording_problems(fake("you wrote 'null' here, which needs a number"))
              and bool(setup_cases.wording_problems(fake("this is null, which needs a number"))),
              "Self-test: words the person typed (quoted back to them) are not judged, the program's own wording is", "")


def mutation_test(cl: Checklist) -> None:
    report = setup_mutation.run(200)
    cl.record(report.runs == 200 and not report.crashes, "200 random mutations of the example setup (fields deleted, values swapped for other kinds, junk written): the validator never crashes",
              "; ".join(report.crashes[:2]) if report.crashes else f"{report.messages} messages produced; {report.with_errors} of 200 broken setups reported errors")
    cl.record(not report.unplain, "In all 200 mutations every message is plain English with its screen name (no schema, null, traceback and similar wording)",
              "; ".join(report.unplain[:2]) if report.unplain else "no technical wording found")
    cl.record(not report.unexpected_failures, "In all 200 mutations every rule coped: no rule gave up on a strange setup",
              "; ".join(report.unexpected_failures[:2]) if report.unexpected_failures else "0 rules gave up")
    # the harness must be able to see a crash
    original = setup_mutation.check

    def crashing(setup, **kwargs):
        raise RuntimeError("simulated crash")

    setup_mutation.check = crashing
    try:
        crashed = setup_mutation.run(3)
    finally:
        setup_mutation.check = original
    cl.record(len(crashed.crashes) >= 3, "Self-test: the mutation test notices when the validator crashes", f"{len(crashed.crashes)} crashes noticed in 3 runs")

    def faulty(context):
        raise RuntimeError("simulated rule failure")
        yield

    rules_module.SEMANTIC_RULES.append(faulty)
    try:
        try:
            validate(setup_cases.fresh(), base_dir=setup_cases.EXAMPLES, strict=True)
            strict_raises = False
        except RuntimeError:
            strict_raises = True
        quiet = [p.rule for p in validate(setup_cases.fresh(), base_dir=setup_cases.EXAMPLES)]
    finally:
        rules_module.SEMANTIC_RULES.remove(faulty)
    cl.record(strict_raises and "X99" in quiet, "Self-test: a failing rule is exposed in strict mode, and in normal use becomes a plain message instead of a crash", "")


def version_checks(cl: Checklist) -> None:
    newer = validate({**setup_cases.fresh(), "format_version": 2}, base_dir=setup_cases.EXAMPLES)
    cl.record(len(newer) == 1 and newer[0].rule == "V03" and newer[0].level == "error" and "newer" in newer[0].text,
              "A setup with a newer format version than the program knows is refused with one plain message (and nothing else is checked)", newer[0].message if newer else "")
    marker: list[bool] = []

    def migrate(old: dict) -> dict:
        marker.append(True)
        return {k: v for k, v in old.items() if k != "baseline"}

    older = validate(setup_cases.fresh(), base_dir=setup_cases.EXAMPLES, formats=FormatSupport(current=2, oldest=1, migrations={1: migrate}))
    cl.record(bool(marker) and any(p.rule == "V04" for p in older) and any(p.rule == "S01" for p in older),
              "An older setup is brought up to date when it is opened, and the updated version is the one that is checked (simulated with a version-2 program)",
              ", ".join(sorted({p.rule for p in older})))
    plain_old = validate(setup_cases.fresh(), base_dir=setup_cases.EXAMPLES, formats=FormatSupport(current=2, oldest=1, migrations={1: lambda s: s}))
    cl.record(not has_errors(plain_old) and any(p.rule == "V04" for p in plain_old), "An older setup with a harmless update loads with a note and no errors", "")


def save_checks(cl: Checklist) -> None:
    moment = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder).resolve()
        for source in setup_cases.EXAMPLES.iterdir():
            if source.is_file():
                (root / source.name).write_bytes(source.read_bytes())
        setup = setup_cases.fresh()
        problems = validate(setup, base_dir=root, root=root)
        path = save_setup(setup, "my-study", root=root, now=moment, problems=problems)
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        loaded = load_setup(path, root=root)
        saved = loaded.setup.get("saved", {})
        content = {k: v for k, v in loaded.setup.items() if k != "saved"}
        cl.record(path.parent.name == "setups" and path.suffix == ".yaml" and not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw,
                  "A setup is saved into the setups folder as a plain text file (no byte-order mark, Unix line endings)", str(path.relative_to(root)))
        cl.record(set(saved) == {"saved_at", "program_version", "content_sha256"} and saved["saved_at"] == "2026-10-09T10:00:00Z"
                  and saved["program_version"] == PROGRAM_VERSION and saved["content_sha256"] == fingerprint(content),
                  "A saved setup records when it was saved (in UTC), which program version saved it, and a fingerprint of its content: nothing else",
                  f"saved at {saved.get('saved_at')}, program {saved.get('program_version')}, fingerprint {str(saved.get('content_sha256'))[:12]}...")
        names = {getpass.getuser(), os.environ.get("USERNAME", ""), platform.node(), os.environ.get("COMPUTERNAME", "")} - {""}
        leaked = [n for n in names if len(n) > 2 and re.search(re.escape(n), text, re.IGNORECASE)]
        cl.record(not leaked, "The saved file contains no personal name (not the user name and not the computer name)", "checked against this computer's user and computer names" if not leaked else "found: " + ", ".join(leaked))
        again = validate(loaded.setup, base_dir=path.parent, root=root)
        cl.record(content == setup and not has_errors(again) and not any(p.rule == "V05" for p in again),
                  "A saved setup reads back exactly as saved, passes the checks, and its fingerprint matches", "")
        twice = save_setup(loaded.setup, "my-study-2", root=root, now=moment, problems=again).read_bytes()
        cl.record(twice == raw, "Saving the same content again at the same moment gives the identical file (the fingerprint ignores the saved details)", "")
        refusals = []
        for label, call in (("with errors", lambda: save_setup(setup, "bad", root=root, problems=[Problem("R99", "", "error", "Project", "", "", "x")])),
                            ("without a check", lambda: save_setup(setup, "bad", root=root)),
                            ("outside the folder", lambda: save_setup(setup, "../escape", root=root, problems=[])),
                            ("with spaces", lambda: save_setup(setup, "My Study", root=root, problems=[]))):
            try:
                call()
                refusals.append(f"{label}: SAVED")
            except SetupFileError:
                pass
        cl.record(not refusals and not (root / "bad.yaml").exists() and not (root.parent / "escape.yaml").exists(),
                  "Saving is refused while the setup has errors, when it was not checked, or when the name could leave the setups folder", "; ".join(refusals))
        warned = save_setup(setup, "with-warning", root=root, problems=[Problem("R24", "tight", "warning", "Equipment", "", "", "x")])
        cl.record(warned.exists(), "A setup with only warnings can still be saved", "")
    with tempfile.TemporaryDirectory() as folder:
        evil = Path(folder) / "evil.yaml"
        evil.write_bytes(b"format_version: !!python/object/apply:os.getcwd []\n")
        result = load_setup(evil)
        cl.record(result.setup is None and any(p.rule == "F02" for p in result.problems),
                  "YAML is read with the safe reader only: a file that tries to run code is refused with a plain message", result.problems[0].message if result.problems else "")


def unit_checks(cl: Checklist) -> None:
    levels = {v: rule_for(r, v).level for r in ("R12", "R19") for v in ("conflict", "unknown_unit", "no_suffix", "case")}
    cl.record(all(rule_for(r, "conflict").level == "error" and all(rule_for(r, v).level == "warning" for v in ("unknown_unit", "no_suffix", "case")) for r in ("R12", "R19")),
              "Unit rules (R12, R19): an error only when the units clearly conflict; an unknown unit, a missing unit ending or a capital-letter difference is only a warning", str(levels)[:120])
    outside = []
    for path in sorted(SETUP_PACKAGE.glob("*.py")):
        if path.name == "units.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # a list of units written out again: an ID ending, or two or more unit symbols on one line
            endings = re.findall(r"[\"'](_pct|_kn|_kp|_min|_deg)[\"']", line)
            symbols = set(re.findall(r"[\"'](kN|kP|deg|min|%)[\"']", line))
            if endings or len(symbols) >= 2:
                outside.append(f"{path.name} line {number}")
    cl.record(not outside, "The allowed units are written in one place only (cellpoc/setup/units.py); no other file lists them", "; ".join(outside) if outside else allowed_symbols())
    original = units_module.UNITS
    units_module.UNITS = original + (units_module.Unit("rpm", "speed", "_rpm", "revolutions per minute"),)
    try:
        setup = setup_cases.fresh()
        setup["process_factors"][0]["unit"] = "furlong"
        message = next((p.text for p in validate(setup, base_dir=setup_cases.EXAMPLES) if p.rule == "R12"), "")
        accepted = not any(p.rule == "R12" for p in validate({**setup_cases.fresh(), "process_factors": [
            {"id": "stir_speed_rpm", "label": "Stir speed", "unit": "rpm", "min": 1, "max": 2}]}, base_dir=setup_cases.EXAMPLES))
    finally:
        units_module.UNITS = original
    cl.record("rpm" in message and accepted, "Self-test: adding one unit to the list changes what is accepted and what the messages say, with no other edit", message[-60:])


def message_checks(cl: Checklist) -> None:
    for variant in ("real", "validated"):
        text = render("R04", variant)
        cl.record("data-handling policy" in text and "approved" in text and rule_for("R04", variant).level == "warning",
                  f"Choosing '{variant}' as the data status warns that the client's data-handling policy must be approved before real data is used", text[:90] + "...")
    expected = build_text()
    saved = DOC_PATH.read_bytes().decode("utf-8") if DOC_PATH.exists() else ""
    cl.record(saved == expected, f"docs/setup_messages.md lists every rule with its test and message, and is up to date ({len(CATALOGUE)} messages)",
              str(DOC_PATH.relative_to(ROOT)) if saved == expected else "out of date: run  .venv\\Scripts\\python.exe tools\\make_setup_messages.py")
    cl.record(bool(re.search(r", 0 without a test\.", expected)) and "NONE: this rule has no test yet" not in expected,
              "The message document states that no rule is without a test", "")


def convert_checks(cl: Checklist) -> None:
    import ast
    import hashlib
    import random

    from cellpoc.settings import settings_from_dict

    poc_file = ROOT / "config" / "settings.yaml"
    before = hashlib.sha256(poc_file.read_bytes()).hexdigest()
    setup = setup_cases.fresh()
    problems = validate(setup, base_dir=setup_cases.EXAMPLES)
    conv = to_poc_settings(setup, problems)
    accepted, why = False, ""
    try:
        poc = settings_from_dict(conv.settings)
        accepted = [s.name for s in poc.cell.steps][1] == "blend" and len(poc.design_space.ingredients) == 5
    except Exception as error:   # noqa: BLE001
        why = str(error)[:200]
    cl.record(conv.ok and accepted, "The example setup converts to settings that the proof of concept's own settings checker accepts ('mix' becomes 'blend', five ingredients)",
              why or f"{len(conv.notes)} note(s) about what the proof of concept leaves out")
    cl.record(bool(conv.yaml_text()) and conv.yaml_text().startswith("# PREVIEW ONLY") and "illustrative" in conv.yaml_text(),
              "The preview text is labelled as a preview and as illustrative", "")
    tree = ast.parse((SETUP_PACKAGE / "convert.py").read_text(encoding="utf-8"))
    writes = [n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
              and (isinstance(n.func, ast.Attribute) and n.func.attr in {"write", "write_text", "write_bytes", "dump", "mkdir", "unlink", "rename", "replace", "open"}
                   or isinstance(n.func, ast.Name) and n.func.id in {"open"})]
    # yaml.safe_dump with no stream returns text; only a second argument (a stream) would write
    safe = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "safe_dump" and len(n.args) > 1]
    cl.record(not writes and not safe and "config" not in (SETUP_PACKAGE / "convert.py").read_text(encoding="utf-8").replace("config/settings.yaml", ""),
              "The converter cannot write any file (it only builds text), and config/settings.yaml is not named as a target", ", ".join(writes) if writes else "no file calls found")
    after = hashlib.sha256(poc_file.read_bytes()).hexdigest()
    cl.record(before == after, "config/settings.yaml is byte-for-byte unchanged after converting", "")
    broken = setup_cases.fresh()
    broken["batch_size_g"] = 0
    refused = to_poc_settings(broken, validate(broken, base_dir=setup_cases.EXAMPLES))
    cl.record(not refused.ok and "Fix the errors first" in refused.notes[0].text, "While the setup has errors nothing is converted, and the preview says so", "")

    def extra_ingredient(s):
        s["ingredients"].append({"id": "glidant_pct", "label": "Glidant", "role": "other", "unit": "%", "min": 0, "max": 1})

    def fault_in_last_step(s):
        s["faults"]["scripted"][0]["where"] = {"step": "clean", "action": "wait"}

    def no_hardness(s):
        s["targets"]["constraints"].pop(1)

    def no_noise(s):
        s["virtual_lab"]["noise"].pop(1)

    blocked = []
    for label, change in (("an extra ingredient", extra_ingredient), ("a fault in the last step", fault_in_last_step),
                          ("no hardness target", no_hardness), ("no hardness noise", no_noise)):
        variant = setup_cases.fresh()
        change(variant)
        result = to_poc_settings(variant, validate(variant, base_dir=setup_cases.EXAMPLES))
        if result.ok or not any(n.level == "blocking" for n in result.notes):
            blocked.append(label)
    cl.record(not blocked, "A setup the proof of concept cannot represent (extra ingredient, fault in the last step, no hardness target, no hardness noise) is refused with a plain note",
              "not refused: " + ", ".join(blocked) if blocked else "4 of 4 refused")

    # the converter must never say 'fine' when the PoC's own checker would refuse
    def wider_filler(s):
        s["ingredients"][4].update(min=40, max=70)

    def slower_press(s):
        s["equipment"]["steps"][2]["time_min"] = 40
        s["equipment"]["phases"]["reason_min"] = 20

    def one_fault(s):
        s["faults"]["scripted"] = s["faults"]["scripted"][:1]

    def no_faults(s):
        s["faults"]["scripted"] = []

    def mid_week(s):
        s["calendar"].update(staffed_days=["Wed", "Thu", "Fri"], staffed_from="09:00", staffed_until="17:30")

    def dissolution_over_100(s):
        s["targets"]["constraints"][0]["value"] = 120

    rng = random.Random(77)
    candidates = []
    for change in (wider_filler, slower_press, one_fault, no_faults, mid_week, dissolution_over_100):
        variant = setup_cases.fresh()
        change(variant)
        candidates.append(variant)
    for _ in range(300):
        variant = setup_cases.fresh()
        for _ in range(rng.choice([1, 2])):
            setup_mutation.mutate_once(variant, rng)
        candidates.append(variant)
    converted = refused_ok = 0
    disagreements = []
    for index, variant in enumerate(candidates):
        verdict = validate(variant, base_dir=setup_cases.EXAMPLES)
        result = to_poc_settings(variant, verdict)
        if has_errors(verdict) or not result.ok:
            refused_ok += 1
            continue
        converted += 1
        try:
            settings_from_dict(result.settings)
        except Exception as error:   # noqa: BLE001
            disagreements.append(f"#{index}: {str(error)[:120]}")
    damaged = {k: v for k, v in conv.settings.items() if k != "run"}
    try:
        settings_from_dict(damaged)
        agreement_can_fail = False
    except Exception:   # noqa: BLE001
        agreement_can_fail = True
    cl.record(agreement_can_fail, "Self-test: the proof of concept's checker does refuse converted settings that are damaged (so the agreement check above can fail)", "")
    cl.record(not disagreements and converted >= 3, f"Whenever a setup passes the checks and converts, the proof of concept's own checker agrees ({converted} setups converted, {refused_ok} refused, out of {len(candidates)})",
              "; ".join(disagreements[:2]))


def housekeeping_checks(cl: Checklist) -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    cl.record("setups/" in ignore and "data/client/" in ignore, "Saved setups and client data are kept out of git (setups/ and data/client/ are ignored)", "")
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8") if (ROOT / ".gitattributes").exists() else ""
    cl.record(all(f"*.{ext}" in attributes and "eol=lf" in attributes for ext in ("csv", "json", "yaml")), "Data and format files are pinned to Unix line endings so fingerprints agree on every computer", "")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 1: setup and validation (shared logic)")
    results = setup_cases.run_all()
    example_loads_clean(cl)
    rule_tests(cl, results)
    wording_checks(cl)
    mutation_test(cl)
    version_checks(cl)
    save_checks(cl)
    unit_checks(cl)
    convert_checks(cl)
    message_checks(cl)
    housekeeping_checks(cl)
    setup_app_tests.run(cl)
    architecture.check(cl)
    cl.headline("Setup rules: illustrative example values only; no client data is used by this check.")
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
