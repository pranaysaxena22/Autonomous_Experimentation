"""Health check for the sealed acceptance lab: is the seal intact, and has anything used the lab that should not?

In plain words it checks that: the lab's files have not changed by a single byte since they were sealed (their fingerprints match both the manifest and the ones recorded in docs/decisions.md); nothing
outside the acceptance folder imports, opens or even names the lab (development code, tools and every other check are scanned); the ledger shows the lab was created and then sealed, and that nobody has
recorded opening it; and, on planted examples, that a changed file, a CRLF-only difference, an import of the lab, an open() of it and a ledger entry that says it was opened are each judged correctly.
The check reads bytes only: it never imports or runs the lab. Nothing is written into the project and nothing uses the network.
"""
from __future__ import annotations

import ast
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.modelling.findings import ACCEPTANCE_CAVEAT  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import project_files  # noqa: E402

FOLDER = "acceptance"
REPORTS = ROOT / "runs" / "acceptance"             # where the acceptance runner (Stage 4-5) will write its reports
SEALED_FILES = (f"{FOLDER}/sealed_lab.py", f"{FOLDER}/README.md")
MANIFEST = f"{FOLDER}/SEAL.json"
SKIP_PARTS = {".venv", ".git", "runs", "__pycache__", "chrome_profile", FOLDER, "data", "node_modules"}
SCANNED = {".py", ".bat", ".yaml", ".yml", ".json", ".toml", ".cfg", ".txt", ".ini"}
# the lab's own name in code or paths, an import of the folder, or a path into it
REFERENCE = re.compile(r"sealed_lab|(?m:^[ \t]*(?:from|import)[ \t]+acceptance\b)|acceptance[\\/]+sealed")


def fingerprint(data: bytes) -> str:
    """SHA-256 of the bytes with every CRLF turned into LF, so a Windows and a Unix copy of the same file agree."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def references_in(text: str) -> list[str]:
    return [line.strip()[:80] for line in text.splitlines() if REFERENCE.search(line)]


def recorded_fingerprints(decisions: str) -> dict[str, str]:
    return {name: digest for name, digest in re.findall(r"`(acceptance/[A-Za-z_.]+)`\s*\|\s*`([0-9a-f]{64})`", decisions)}


def ledger_problems(ledger: str) -> list[str]:
    entries = re.findall(r"(?m)^- \[(\d{4}-\d{2}-\d{2})\] ([A-Z ]+?):", ledger)
    types = [t for _, t in entries]
    found = []
    if "CREATED" not in types or "SEALED" not in types or types.index("CREATED") > types.index("SEALED"):
        found.append("the ledger must show CREATED and then SEALED")
    if "OPENED" in types:
        found.append("the ledger records that the lab was OPENED: the seal is void and a new lab must be written")
    last_violation = max((i for i, t in enumerate(types) if t == "VIOLATION"), default=None)
    if last_violation is not None and "RESEALED" not in types[last_violation + 1:]:
        found.append("the ledger records a VIOLATION that has not been followed by RESEALED: the seal has not been restored")
    return found


SEED_LINE = re.compile(r"SEALED_SEEDS = tuple\(range\(([\d_]+), ([\d_]+)\)\)")


def manifest_problems(manifest: dict, lab_text: str) -> list[str]:
    """Everything wrong with how the lab designates its acceptance seeds (empty means fine): they must be the manifest's, a block of 40, and clear of the retired seeds that were examined before the first seal."""
    found = []
    m = SEED_LINE.search(lab_text)
    if not m:
        return ["the lab file does not designate its acceptance seeds in the expected form"]
    first, stop = int(m.group(1).replace("_", "")), int(m.group(2).replace("_", ""))
    if (first, stop - 1) != (manifest.get("sealed_seed_first"), manifest.get("sealed_seed_last")):
        found.append("the seeds in the lab file differ from the ones in the manifest")
    if stop - first != 40:
        found.append("the acceptance seeds are not a block of 40")
    retired = (manifest.get("retired_seed_first"), manifest.get("retired_seed_last"))
    if retired != (7000001, 7000040):
        found.append("the manifest must record the retired seeds 7,000,001 to 7,000,040")
    elif not (stop - 1 < retired[0] or first > retired[1]):
        found.append("the acceptance seeds overlap the retired seeds (7,000,001 to 7,000,040), which were examined before the first seal")
    return found


FORBIDDEN_IMPORTS = {"acceptance", "importlib", "runpy", "subprocess", "pkgutil", "imp"}
FORBIDDEN_BUILTINS = {"exec", "eval", "__import__", "compile"}                          # plain calls that run or load code (re.compile is a method and is not one of them)
FORBIDDEN_LOADERS = {"run_path", "run_module", "import_module", "spec_from_file_location", "load_module"}      # methods that load a file or a module by name


def execution_problems(source: str) -> list[str]:
    """Everything in this source that could IMPORT OR RUN the lab (empty means it only reads bytes and text): imports of the lab's folder or of the machinery that loads code, and calls that run or load code."""
    tree = ast.parse(source)
    imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    plain = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    methods = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    return [f"imports {m}" for m in sorted(imports & FORBIDDEN_IMPORTS)] + [f"calls {c}" for c in sorted(plain & FORBIDDEN_BUILTINS)] + [f"calls {c}" for c in sorted(methods & FORBIDDEN_LOADERS)]


def has_caveat(text: str) -> bool:
    """True when the required caveat appears word for word (web pages write an apostrophe as a code, so those are turned back first)."""
    return " ".join(ACCEPTANCE_CAVEAT.split()) in " ".join(html.unescape(text).split())


def reports_without_caveat() -> list[str]:
    """Every acceptance report that exists but lacks the caveat (none exist until the first acceptance run)."""
    if not REPORTS.exists():
        return []
    return [p.name for p in sorted(REPORTS.rglob("*")) if p.is_file() and p.suffix.lower() in {".md", ".html", ".json", ".txt", ".csv"}
            and not has_caveat(p.read_text(encoding="utf-8", errors="replace"))]


def other_files() -> list[Path]:
    return [p for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in SCANNED and not (SKIP_PARTS & set(p.relative_to(ROOT).parts))
            and p.relative_to(ROOT).as_posix() != "checks/seal_check.py"]


def main() -> int:
    cl = Checklist("THE SEALED ACCEPTANCE LAB: is the seal intact and has nothing used the lab that should not?")
    before = project_files()
    manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8")) if (ROOT / MANIFEST).exists() else {}
    cl.record(manifest.get("status") == "sealed" and set(manifest.get("files", {})) == set(SEALED_FILES), "The manifest (acceptance/SEAL.json) exists, says the lab is sealed and lists the two sealed files", str(manifest.get("status")))
    actual = {f: fingerprint((ROOT / f).read_bytes()) if (ROOT / f).exists() else "missing" for f in (*SEALED_FILES, MANIFEST)}
    cl.record(all(actual[f] == manifest.get("files", {}).get(f) for f in SEALED_FILES), "Each sealed file's fingerprint equals the one in the manifest: not one byte has changed since sealing", ", ".join(f"{f.split('/')[-1]} {actual[f][:12]}" for f in SEALED_FILES))
    lab_text = (ROOT / SEALED_FILES[0]).read_text(encoding="utf-8")
    problems_now = manifest_problems(manifest, lab_text)
    cl.record(not problems_now and manifest.get("version", 1) >= 2 and manifest.get("git_tag") == "sealed-lab-v2" and manifest.get("supersedes") == "sealed-lab-v1",
              "Version 2: the acceptance seeds in the lab file are the manifest's 7,000,101 to 7,000,140, a block of 40, clear of the retired seeds 7,000,001 to 7,000,040 that were examined before the first seal", "; ".join(problems_now) or "7000101 to 7000140")
    recorded = recorded_fingerprints((ROOT / "docs" / "decisions.md").read_text(encoding="utf-8"))
    cl.record(all(recorded.get(f) == actual[f] for f in (*SEALED_FILES, MANIFEST)), "All three fingerprints (the two sealed files and the manifest) equal the ones recorded in docs/decisions.md", f"{len(recorded)} recorded")
    files = other_files()
    hits = {p.relative_to(ROOT).as_posix(): references_in(p.read_text(encoding="utf-8", errors="replace")) for p in files}
    hits = {k: v for k, v in hits.items() if v}
    cl.record(not hits, "Nothing outside the acceptance folder imports, opens or names the lab: development code, tools and every other check were scanned", f"{len(files)} files scanned; found: {list(hits.items())[:2]}")
    ledger = (ROOT / FOLDER / "LEDGER.md").read_text(encoding="utf-8") if (ROOT / FOLDER / "LEDGER.md").exists() else ""
    problems = ledger_problems(ledger)
    cl.record(not problems, "The ledger shows the lab was created and then sealed, and nobody has recorded opening it", "; ".join(problems))
    runs = len(re.findall(r"(?m)^- \[[\d-]+\] ACCEPTANCE RUN:", ledger))
    cl.headline(f"the sealed lab has been run for acceptance {runs} time(s) (recorded in acceptance/LEDGER.md)")
    # planted examples: the check must tell each of these apart
    lab = (ROOT / SEALED_FILES[0]).read_bytes()
    crlf_only = lab.replace(b"\n", b"\r\n")
    cl.record(fingerprint(crlf_only) == fingerprint(lab) and fingerprint(lab + b" ") != fingerprint(lab) and fingerprint(lab.replace(b"0.07", b"0.08", 1)) != fingerprint(lab),
              "Self-test: a Windows copy (CRLF) of the lab has the same fingerprint, but adding one space or changing one constant changes it", "")
    planted = ["from acceptance import sealed_lab", "import acceptance.sealed_lab as lab", "open('acceptance/sealed_lab.py')", "path = r'acceptance\\sealed_lab.py'", "x = 1  # sealed_lab"]
    innocent = ["acceptance testing is a stage", "import os", "# the acceptance runner", "from cellpoc import setup"]
    cl.record(all(references_in(p) for p in planted) and not any(references_in(i) for i in innocent),
              "Self-test: the scan catches an import, an open(), a path and a mention of the lab, and leaves ordinary words alone", "")
    good = "- [2026-10-11] CREATED: x\n- [2026-10-11] SEALED: y\n"
    cl.record(not ledger_problems(good) and ledger_problems(good + "- [2026-11-01] OPENED: debugging\n") and ledger_problems("- [2026-10-11] SEALED: y\n- [2026-10-11] CREATED: x\n") and ledger_problems(""),
              "Self-test: a ledger that says OPENED, or lacks CREATED then SEALED, is reported", "")
    new_text = "SEALED_SEEDS = tuple(range(7_000_101, 7_000_141))"
    old_text = "SEALED_SEEDS = tuple(range(7_000_001, 7_000_041))"
    v2 = {"version": 2, "sealed_seed_first": 7000101, "sealed_seed_last": 7000140, "retired_seed_first": 7000001, "retired_seed_last": 7000040}
    cl.record(not manifest_problems(v2, new_text) and manifest_problems(v2, old_text) and manifest_problems({**v2, "sealed_seed_first": 7000102}, new_text) and manifest_problems(v2, "SEALED_SEEDS = tuple(range(7_000_101, 7_000_140))")
              and manifest_problems({**v2, "retired_seed_first": 1}, new_text) and manifest_problems(v2, "no seeds here"),
              "Self-test: the seed rule accepts the fresh block, and refuses the old block (it overlaps the retired seeds), a lab file that disagrees with its manifest, a block that is not 40 long, a manifest that forgot the retired seeds and a lab file with no seed line", "")
    reseal = "- [2026-10-11] CREATED: x\n- [2026-10-11] SEALED: y\n- [2026-10-12] VIOLATION: z\n"
    cl.record(ledger_problems(reseal) and not ledger_problems(reseal + "- [2026-10-12] RESEALED: w\n") and ledger_problems(reseal + "- [2026-10-12] RESEALED: w\n- [2026-10-13] VIOLATION: again\n"),
              "Self-test: a VIOLATION in the ledger is reported until it is followed by RESEALED, and a later violation is reported again", "")
    own = execution_problems(Path(__file__).read_text(encoding="utf-8"))
    planted_run = ["import acceptance.sealed_lab as lab", "from acceptance import sealed_lab", "import importlib\nimportlib.import_module(\"acceptance.sealed_lab\")", "exec(open(\"x\").read())", "import runpy\nrunpy.run_path(\"p\")", "x = compile(\"1\", \"f\", \"exec\")"]
    cl.record(not own and all(execution_problems(s) for s in planted_run) and not execution_problems("import hashlib\nimport re\ntext = open(\"f\").read()\nh = hashlib.sha256(text.encode()).hexdigest()\np = re.compile(\"x\")"),
              "This check itself never imports or runs the lab (so its self-tests, which use the live seed block 7,000,101 to 7,000,140 only as text and numbers, can never have produced output from a real seed): its imports and calls are inspected, and a planted import, importlib load, exec or runpy is caught",
              "; ".join(own))
    # the permanent caveat (requested 2026-10-11): every report that shows results from the sealed lab must carry it, word for word
    missing = reports_without_caveat()
    count = len([p for p in REPORTS.rglob("*") if p.is_file()]) if REPORTS.exists() else 0
    cl.record(not missing, "Every acceptance report that exists carries the caveat 'This lab's shape constants were adjusted twice by someone aware of Stage 3's findings ... not a fully blind acceptance test', word for word",
              f"{count} report file(s) found" + (f"; without it: {missing[:3]}" if missing else ""))
    decisions_text = (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    cl.record(has_caveat(decisions_text), "docs/decisions.md states the caveat word for word", "")
    cl.record(has_caveat("<p>" + html.escape(ACCEPTANCE_CAVEAT) + "</p>") and has_caveat("x " + ACCEPTANCE_CAVEAT.replace(" ", "\n") + " y") and not has_caveat("This is not a fully blind acceptance test.")
              and not has_caveat(ACCEPTANCE_CAVEAT.replace("twice", "once")),
              "Self-test: the caveat is found inside a web page and across line breaks, and a report with a shortened or altered caveat is refused", "")
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
