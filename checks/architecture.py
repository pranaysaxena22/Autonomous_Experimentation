"""Guards the separation of the five parts by reading which parts import which.

Each part may import only the parts listed for it. This is what keeps the dashboard free of
logic, the decision engine blind to the hidden truth, and the lab ignorant of the cell.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from checks.common import Checklist

PACKAGE = Path(__file__).resolve().parents[1] / "cellpoc"

# part -> the other parts it is allowed to import
ALLOWED = {
    "settings": set(),
    "contracts": {"settings"},
    "virtual_lab": {"contracts", "settings"},
    # Stage 4 (approved): the engine may import the model classes from the modelling part, one direction only. The guard below (engine_direction) narrows this to cellpoc.modelling.models alone
    # and proves that the modelling part can never reach the engine, directly or through another part.
    "decision_engine": {"contracts", "settings", "modelling"},
    "cell_simulator": {"contracts", "settings"},
    "run_store": {"contracts"},
    "scoring": {"contracts", "settings", "virtual_lab"},       # judges results against the truth, after the fact
    "comparison": {"contracts", "settings", "virtual_lab", "decision_engine", "scoring"},
    "about_text": {"contracts", "settings"},
    "dashboard": {"run_store", "contracts"},          # it only reads the run record
    "runner": {"settings", "contracts", "virtual_lab", "decision_engine", "cell_simulator", "run_store",
               "comparison", "about_text"},
    # platform parts (Stage 1): setting up a study. They share nothing with the run, the lab or the engine.
    "formats": set(),                                 # schemas and examples: data files only
    "setup": set(),                                   # reading, saving and checking a setup
    "setup_app": {"setup"},                           # the setup screens only show what setup decides
    # platform part (Stage 2): reading the client's data files. Needs only the setup's file-safety and file-header code.
    "ingest": {"setup"},
    # platform part (Stage 3): preparing tables for modelling and validating models. It reads cleaned tables (ingest) and the setup's rules; it never sees the hidden truth.
    "modelling": {"setup", "ingest"},
    # supporting piece (Stage 4-1): turns Stage 3's saved answers into the engine's brief. Neither the modelling part nor the engine imports it.
    "briefing": {"contracts", "modelling"},
    # platform parts (Stages 5 to 7; approved plan, docs/decisions.md "Stages 5 to 7"). New parts only: no existing part's list above has changed.
    "planner": set(),                                 # a recipe, the setup and the layout in; a motion plan out. It reads plain dictionaries and imports no other part.
    "executor": {"planner", "instruments"},      # (2026-10-14) the executor reads the barcode scanner and the balance through the instruments part                          # runs a plan and returns the executed timeline; it uses the planner's plan rules and nothing else
    "platform_cell": {"contracts", "settings", "cell_simulator", "planner", "executor"},   # the configurable cell simulator: the proof of concept's simulator with the plan, the executor and the setup's faults plugged in
    "viewer": set(),                                  # writes the 3D replay file from data files; it contains no logic of its own
    # Stage 8 (approved by the user's instruction to complete through Stage 8; docs/decisions.md "Stages 5 to 8"): the text the dashboard's platform tabs show is worked out here, in advance, from the data reader and the modelling table builder.
    "platform_info": {"contracts", "ingest", "modelling", "planner", "platform_cell"},
    # The connected loop (approved 2026-10-13: "connect the loop"): the experiment table, Stage 3's conclusions, the adopted engine and the cell simulator in one opt-in chain. A new part; nothing but the live run imports it, and the
    # decision engine still imports only the modelling part, so the engine can reach neither this part nor the lab.
    "connected": {"contracts", "briefing", "modelling", "decision_engine", "virtual_lab", "platform_cell", "executor", "platform_info", "platform_runner", "reports", "setup"},
    # The live run (approved 2026-10-13: "go ahead" to the plan for a live page): the platform simulation on its own thread, paced, with a local page. A new, separate part; it is not the dashboard, and nothing imports it.
    "live": {"contracts", "connected", "decision_engine", "executor", "platform_cell", "platform_info", "platform_runner", "setup", "virtual_lab", "physics", "vision"},          # (2026-10-22) the live page can show the cell's camera check of a bottle (the vision part reads a drawn photograph); and it can show the cell drawn by the MuJoCo model: a read-only picture route, drawn from the timelines the run has already published
    # Stage 9 (same instruction): the report and export files are written from the run record only, like the dashboard reads it, with no other part involved.
    "reports": {"contracts", "run_store"},
    "platform_runner": {"settings", "contracts", "virtual_lab", "decision_engine", "cell_simulator", "run_store", "setup", "planner", "executor", "platform_cell", "viewer", "platform_info", "reports", "client_story"},   # wires the platform pieces together, like runner
    # The unified app, Stage A (approved 2026-10-13): one app with a left menu that shows the dashboard's pages. Like the dashboard it only displays what the run record holds. It may import the dashboard (its page modules, style and reader),
    # the run-record reader and the shared data shapes; no part may import it. Stage B (approved 2026-10-14) adds the setup app (and so, through it, the setup part) so the setup screens can be drawn inside it. The shell's own files may never start a
    # process or touch a file (shell_check): only the setup app's own, already tested code does that. The live run (Stage C) will need its own, separately approved, entry after a design note.
    "shell": {"dashboard", "run_store", "contracts", "setup_app", "live_supervisor", "vision"},          # (2026-10-22) the Vision page shows what the vision part reads from a picture
    # Stage C (approved 2026-10-14, docs/stage_c_design_note.md): the ONLY code that starts, watches and stops the live program for the unified app. It imports no other part of the project (an empty list), uses no network library, and may run
    # exactly three commands (the live program on one port, taskkill for what it started, netstat to read the listening addresses): supervisor_check below reads its source to hold it to that. Only the shell may import it.
    "live_supervisor": set(),
    # The instruments (2026-10-14): drivers for the barcode scanner and the balance, each simulated now and serial for real hardware, behind one interface. It imports no other part and touches no network; only the executor (and the checks) use it.
    "instruments": set(),
    # The physics part (2026-10-16): a MuJoCo model of the cell built from the layout, and reach checks asked of MuJoCo. It imports no other part and touches no network; nothing uses it yet except its own check and export.
    "physics": set(),
    # The client story (2026-10-16): the run told as results a client cares about, worked out in advance from the saved run record and written next to it. It imports no other part and touches no network; only the platform runner uses it, and the dashboard only displays the file.
    "client_story": set(),
    # The vision part (2026-10-22): reads a picture of a bench with OpenCV (which coloured liquids, how full, where for the arm). It imports no other part and touches no network; only the shell's Vision page uses it.
    "vision": set(),
}
PARTS = set(ALLOWED)
NETWORK_MODULES = {"requests", "urllib", "urllib3", "http", "httpx", "socket", "ftplib", "smtplib", "aiohttp", "websocket", "websockets"}
NO_NETWORK = ("setup", "setup_app", "ingest", "modelling", "planner", "executor", "platform_cell", "viewer", "platform_info", "reports", "connected", "platform_runner", "shell", "live_supervisor", "instruments", "physics", "client_story", "vision")       # (connected and platform_runner added 2026-10-13: the live part is left out on purpose, because it serves its page with the built-in web server on 127.0.0.1 only, which check_live.bat tests) parts that handle study setups and client data never talk to the network
HIDDEN = ("_truth", "oracle", "_dev_truth", "dev_oracle")  # modules only the virtual lab itself and the after-the-fact scoring may touch (the last two are the development lab's, Stage 4-2)
MAY_SEE_TRUTH = {"virtual_lab", "scoring"}


def reaches_hidden_truth(text: str) -> bool:
    """Does this source text import any of the lab's hidden-truth modules?"""
    return any(f"virtual_lab.{h}" in text or f"import {h}" in text or f"from .{h}" in text for h in HIDDEN)


def _imported_parts(path: Path) -> set[str]:
    """Which parts of cellpoc does this file import?"""
    return parts_in_text(path.read_text(encoding="utf-8"), list(path.relative_to(PACKAGE).parts[:-1]))      # the package the file sits in, below cellpoc


def parts_in_text(text: str, folders: list[str]) -> set[str]:
    """Which parts of cellpoc does this source text import, if it sits in the package `folders` below cellpoc?"""
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[1] for a in node.names if a.name.startswith("cellpoc.")]
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split(".") if node.module else []
            if node.level == 0:
                if module[:1] == ["cellpoc"]:
                    full = module[1:]
                else:
                    continue
            else:  # level 1 = the file's own package, level 2 = one package up, ...
                full = folders[: len(folders) - (node.level - 1)] + module
            names = full[:1] or [a.name for a in node.names]
        found.update(n for n in names if n in PARTS)
    return found


ENGINE_MAY_IMPORT_FROM_MODELLING = {"models", "domain"}      # the model classes and the warning code, nothing else in the modelling part (both approved for Stage 4, one direction only)
NEVER_IMPORTED_BY_MODELLING = {"decision_engine", "briefing"}  # the modelling part must never import the engine or the piece that builds the engine's brief


def modelling_modules_in_text(text: str, folders: list[str]) -> set[str]:
    """Which modules of the modelling part does this source text import? '*' means the package itself (names imported straight from cellpoc.modelling)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            for a in node.names:
                pieces = a.name.split(".")
                if pieces[:2] == ["cellpoc", "modelling"]:
                    found.add(pieces[2] if len(pieces) > 2 else "*")
        elif isinstance(node, ast.ImportFrom):
            module = node.module.split(".") if node.module else []
            full = module[1:] if node.level == 0 and module[:1] == ["cellpoc"] else (folders[: len(folders) - (node.level - 1)] + module if node.level else [])
            if full[:1] == ["modelling"]:
                found.add(full[1] if len(full) > 1 else "*")
            elif not full and node.level and any(a.name == "modelling" for a in node.names):
                found.add("*")
    return found


def reach(graph: dict[str, set[str]], start: str) -> set[str]:
    """Every part that `start` can reach by following allowed imports, however many steps it takes."""
    seen: set[str] = set()
    todo = [start]
    while todo:
        for nxt in graph.get(todo.pop(), set()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def engine_direction(checklist: Checklist) -> None:
    """Stage 4: one direction only. The engine may import the model classes; the modelling part may never import the engine; the engine still cannot reach the hidden truth through it."""
    engine = sorted((PACKAGE / "decision_engine").rglob("*.py")) if (PACKAGE / "decision_engine").exists() else []
    wrong = [f"{p.relative_to(PACKAGE)} imports modelling.{m}" for p in engine
             for m in sorted(modelling_modules_in_text(p.read_text(encoding="utf-8"), list(p.relative_to(PACKAGE).parts[:-1])) - ENGINE_MAY_IMPORT_FROM_MODELLING)]
    checklist.record(not wrong, "The decision engine may import only the model classes and the warning code from the modelling part (cellpoc.modelling.models and cellpoc.modelling.domain) and nothing else in it",
                     "; ".join(wrong) if wrong else f"{len(engine)} engine files read")
    modelling = sorted((PACKAGE / "modelling").rglob("*.py")) if (PACKAGE / "modelling").exists() else []
    back = [f"{p.relative_to(PACKAGE)} imports {sorted(NEVER_IMPORTED_BY_MODELLING & _imported_parts(p))}" for p in modelling if NEVER_IMPORTED_BY_MODELLING & _imported_parts(p)]
    checklist.record(not back and not (NEVER_IMPORTED_BY_MODELLING & reach(ALLOWED, "modelling")),
                     "One direction only: the modelling part never imports the decision engine or the briefing piece, directly or through any other part", "; ".join(back) if back else f"{len(modelling)} modelling files read")
    checklist.record("virtual_lab" not in reach(ALLOWED, "decision_engine") and "scoring" not in reach(ALLOWED, "decision_engine"),
                     "The decision engine cannot reach the virtual lab or the scoring through any part it may import (the modelling part included)", "")
    in_engine = ["decision_engine"]
    ok_samples = ["from cellpoc.modelling.models import GaussianProcess", "from ..modelling.models import GaussianProcess, Encoder", "import cellpoc.modelling.models as m",
                  "from cellpoc.modelling.domain import fit_reference, warn", "from ..modelling.domain import warn", "import cellpoc.modelling.domain"]
    bad_samples = ["from cellpoc.modelling.carry import decide", "from cellpoc.modelling import table", "import cellpoc.modelling.splits", "from ..modelling.calibration import calibrate", "from .. import modelling",
                   "from cellpoc.modelling.validate import run_validation", "from cellpoc.modelling import domain"]
    planted = [modelling_modules_in_text(s, in_engine) - ENGINE_MAY_IMPORT_FROM_MODELLING for s in bad_samples]
    fine = [modelling_modules_in_text(s, in_engine) - ENGINE_MAY_IMPORT_FROM_MODELLING for s in ok_samples]
    back_planted = [bool(NEVER_IMPORTED_BY_MODELLING & parts_in_text(s, ["modelling"]))              # the detector sees each wording of a modelling file importing the engine or the briefing piece
                    for s in ("from cellpoc.decision_engine import AdaptiveStrategy", "from ..decision_engine.adaptive import AdaptiveStrategy", "import cellpoc.decision_engine",
                              "from cellpoc.briefing import build_brief", "from ..briefing.builder import build_brief", "import cellpoc.briefing")]
    refused_by_allowed = not (NEVER_IMPORTED_BY_MODELLING & ALLOWED["modelling"])                      # and neither is on the modelling part's list of allowed parts
    loop = {"modelling": {"ingest"}, "ingest": {"briefing"}, "briefing": {"modelling"}}
    loop_engine = {"modelling": {"ingest"}, "ingest": {"decision_engine"}, "decision_engine": {"modelling"}}
    checklist.record(all(planted) and not any(fine) and all(back_planted) and refused_by_allowed and "decision_engine" in reach(loop_engine, "modelling") and "briefing" in reach(loop, "modelling")
                     and not (NEVER_IMPORTED_BY_MODELLING & reach(ALLOWED, "modelling")),
                     "Self-test: the guard accepts an engine import of the model classes or the warning code (absolute or relative), refuses an engine import of anything else in the modelling part, refuses the modelling part "
                     "importing the engine or the briefing piece (six wordings), and finds either reached indirectly through another part", "")


DASHBOARD = PACKAGE / "dashboard"
DIVISION_ALLOWED_IN = "throughput.py"   # the single documented exception: autonomous trials/week divided by the manual baseline
FORBIDDEN_CALLS = {"sum", "max", "min", "round", "sorted", "abs", "divmod", "pow"}
FORBIDDEN_METHODS = {"mean", "median", "sum", "std", "var", "groupby", "agg", "sort_values", "cumsum", "idxmax",
                     "idxmin", "quantile", "rolling", "resample", "nlargest", "nsmallest", "pct_change"}
FORBIDDEN_IMPORTS = {"random", "statistics", "math", "numpy", "scipy", "datetime", "time", "itertools", "functools"}
ALLOWED_OPS = (ast.Add,)   # joining text; every other arithmetic operator is refused


LOCAL_HOSTS = ("localhost", "127.0.0.1")
WEB_ADDRESS = re.compile(r"https?://([A-Za-z0-9.\-]+)")


# Stage B: the unified app's OWN files may not start a process, touch a file or open a connection. (The setup app they host does, through its own tested code; that is not the shell's code.)
SHELL_NO_PROCESS_IMPORTS = {"subprocess", "os", "shutil", "socket", "tempfile", "pathlib", "multiprocessing", "threading", "signal", "ctypes"}
SHELL_NO_FILE_CALLS = {"open", "exec", "eval", "__import__"}
SHELL_NO_FILE_METHODS = {"write_text", "write_bytes", "unlink", "rmtree", "mkdir", "touch", "Popen", "system", "startfile"}


def logic_problems_in_text(name: str, text: str, division_file: bool = False, local_addresses_ok: bool = False, no_process: bool = False) -> tuple[list[str], int]:
    """(problems, divisions) for one source text: anything that looks like a display-only part doing its own logic.
    The dashboard may contain no web address at all. The unified app (local_addresses_ok) may name this computer (localhost, 127.0.0.1) but no other address, so its signposts can point at the apps on this computer."""
    problems: list[str] = []
    divisions = 0
    if local_addresses_ok:
        outside = [host for host in WEB_ADDRESS.findall(text) if host not in LOCAL_HOSTS]
        if outside:
            problems.append(f"{name} contains a web address ({outside[0]}); only localhost or 127.0.0.1 may appear (the app must work offline)")
    elif "http://" in text or "https://" in text:
        problems.append(f"{name} contains a web address (the dashboard must work offline)")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.BinOp) and not isinstance(node.op, ALLOWED_OPS):
            if isinstance(node.op, ast.Div) and division_file:
                divisions += 1
            else:
                problems.append(f"{name} line {node.lineno}: does arithmetic ({type(node.op).__name__})")
        elif isinstance(node, ast.AugAssign):
            problems.append(f"{name} line {node.lineno}: updates a running value (+= etc.)")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                problems.append(f"{name} line {node.lineno}: calls {func.id}()")
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_METHODS:
                problems.append(f"{name} line {node.lineno}: calls .{func.attr}()")
            if no_process and isinstance(func, ast.Name) and func.id in SHELL_NO_FILE_CALLS:
                problems.append(f"{name} line {node.lineno}: calls {func.id}() (the unified app's own files may not touch files or run code)")
            if no_process and isinstance(func, ast.Attribute) and func.attr in SHELL_NO_FILE_METHODS:
                problems.append(f"{name} line {node.lineno}: calls .{func.attr}() (the unified app's own files may not start a process or touch a file)")
        elif isinstance(node, ast.comprehension) and node.ifs:
            problems.append(f"{name} line {node.iter.lineno}: filters a list (an 'if' inside a comprehension)")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                       else ([node.module] if node.module and node.level == 0 else []))
            for module in modules:
                if module and module.split(".")[0] in FORBIDDEN_IMPORTS:
                    problems.append(f"{name} line {node.lineno}: imports {module}")
                if no_process and module and module.split(".")[0] in SHELL_NO_PROCESS_IMPORTS:
                    problems.append(f"{name} line {node.lineno}: imports {module} (the unified app's own files may not start a process or touch a file)")
    return problems, divisions


def dashboard_problems() -> tuple[list[str], int]:
    """(problems, number of files read). A problem is anything that looks like the dashboard doing its own logic."""
    problems: list[str] = []
    files = sorted(DASHBOARD.rglob("*.py")) if DASHBOARD.exists() else []
    divisions = 0
    for path in files:
        found, counted = logic_problems_in_text(path.relative_to(PACKAGE).as_posix(), path.read_text(encoding="utf-8"), division_file=path.name == DIVISION_ALLOWED_IN)
        problems.extend(found)
        divisions += counted
    if divisions > 1:
        problems.append(f"{DIVISION_ALLOWED_IN} divides {divisions} times; only one division is allowed")
    return problems, len(files)


SHELL = PACKAGE / "shell"


def shell_problems() -> tuple[list[str], int]:
    """(problems, number of files read) for the unified app: the same no-logic rules as the dashboard, with no division at all, and no web address except this computer's."""
    problems: list[str] = []
    files = sorted(SHELL.rglob("*.py")) if SHELL.exists() else []
    for path in files:
        found, _ = logic_problems_in_text(path.relative_to(PACKAGE).as_posix(), path.read_text(encoding="utf-8"), local_addresses_ok=True, no_process=True)
        problems.extend(found)
    return problems, len(files)


def network_problems(parts=NO_NETWORK, package: Path = PACKAGE) -> list[str]:
    """Imports of network libraries inside the parts that must never talk to the network (client data must never leave this computer).
    A part is a folder of modules OR a single module (platform_info.py, platform_runner.py): before 2026-10-13 only folders were read, so a part that is a single module was listed here but never scanned."""
    problems: list[str] = []
    for part in parts:
        folder, module = package / part, package / f"{part}.py"
        files = sorted(folder.rglob("*.py")) if folder.exists() else ([module] if module.exists() else [])
        for path in files:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                           else ([node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else []))
                for module_name in modules:
                    if module_name.split(".")[0] in NETWORK_MODULES:
                        problems.append(f"{path.relative_to(package).as_posix()} line {node.lineno}: imports {module_name}")
    return problems


def check(checklist: Checklist) -> None:
    breaches: list[str] = []
    scanned = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE)
        part = relative.parts[0] if len(relative.parts) > 1 else relative.stem
        if part not in ALLOWED:
            continue
        scanned += 1
        for other in _imported_parts(path) - {part}:
            if other not in ALLOWED[part]:
                breaches.append(f"{relative} (part '{part}') imports '{other}'")
        if part not in MAY_SEE_TRUTH:
            if reaches_hidden_truth(path.read_text(encoding="utf-8")):
                breaches.append(f"{relative} reaches into the virtual lab's hidden truth")
    checklist.record(not breaches, "Each part imports only the parts it is allowed to",
                     "; ".join(breaches) if breaches else f"{scanned} source files scanned")
    network = network_problems()
    checklist.record(not network, "The setup parts never use the network (no web, socket or mail libraries)",
                     "; ".join(network[:6]) if network else "setup and setup_app files read")
    engine_direction(checklist)
    planted = ["from cellpoc.virtual_lab.dev_oracle import is_good", "from ..virtual_lab import _dev_truth", "from .dev_oracle import true_results", "from cellpoc.virtual_lab._truth import true_hardness_kp",
               "from .oracle import good_share"]
    fine = ["from cellpoc.virtual_lab.dev_lab import DevLab", "from .dev_lab import Context", "import numpy as np"]
    checklist.record(all(reaches_hidden_truth(s) for s in planted) and not any(reaches_hidden_truth(s) for s in fine) and {"_dev_truth", "dev_oracle"} <= set(HIDDEN),
                     "Self-test: an import of the development lab's hidden truth (its truth module or its scoring helper) is caught in five wordings, while an import of the lab itself is not",
                     "only the virtual lab and the scoring may touch it")
    for part in ("decision_engine", "dashboard"):
        if (PACKAGE / part).exists():
            checklist.record("virtual_lab" not in ALLOWED[part], f"The {part.replace('_', ' ')} cannot see the virtual lab",
                             "it is not on its list of allowed parts")
        else:
            checklist.skip(f"The {part.replace('_', ' ')} cannot see the virtual lab",
                           "not built yet; this check starts guarding it when it exists")
    if DASHBOARD.exists():
        forbidden = {"virtual_lab", "decision_engine", "cell_simulator", "comparison", "scoring", "settings", "runner", "about_text"}
        checklist.record(not (ALLOWED["dashboard"] & forbidden),
                         "The dashboard may import only the run-record reader and the shared data shapes: no engine, lab, simulator, scoring or settings code",
                         f"its allowed parts: {', '.join(sorted(ALLOWED['dashboard']))}")
        problems, count = dashboard_problems()
        checklist.record(not problems,
                         "The dashboard contains no logic of its own: no arithmetic, sorting, min/max/sum, filtering or calculation libraries "
                         "(its single division, trials per week over the manual baseline, is the one documented exception)",
                         "; ".join(problems[:6]) if problems else f"{count} dashboard files read")
    if SHELL.exists():
        shell_check(checklist)
    if SUPERVISOR.exists():
        supervisor_check(checklist)
    if LIVE_PART.exists():
        live_bind_check(checklist)


# ---------------------------------------------------------------- Stage C: the live-run supervisor and the live part's bind address
SUPERVISOR = PACKAGE / "live_supervisor"
LIVE_PART = PACKAGE / "live"
SUPERVISOR_IMPORTS_OK = {"__future__", "atexit", "collections", "ctypes", "dataclasses", "pathlib", "re", "subprocess", "sys", "threading", "time", "typing"}
SUPERVISOR_CALLS_NEVER = {"eval", "exec", "__import__", "open", "compile"}
SUPERVISOR_METHODS_NEVER = {"system", "startfile", "write_text", "write_bytes", "unlink", "rmtree", "mkdir", "touch", "rename"}
PROCESS_STARTERS = {"Popen", "run", "check_output", "check_call", "call"}
EXPECTED_LIVE_BODY = ["command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]", "if connected in SCENARIOS:\n    command += ['--connected', connected]", "return command"]      # the fixed list; plus --connected and a name ONLY when the name is one of the four constants
EXPECTED_SCENARIOS = "('baseline', 'new_supplier', 'period_shift', 'unpredictable_dissolution')"
ALLOWED_COMMAND_LISTS = ("['netstat', '-ano']", "['taskkill', '/PID', str(pid), '/T', '/F']")


def supervisor_problems_in_text(name: str, text: str) -> list[str]:
    """What the live-run supervisor's source may contain: no import outside a short list (so no network, os or file library), no shell, no file writing, no eval, and every process it starts is one of THREE commands:
    the live program (from live_command, which must return exactly the fixed list), `netstat -ano`, or `taskkill /PID n /T /F`."""
    problems: list[str] = []
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.level >= 1:
                if node.level == 1 and (node.module or "") in ("supervisor", ""):
                    continue
                problems.append(f"{name} line {node.lineno}: imports another part of the project ({'.' * node.level}{node.module or ''}); the supervisor imports none")
                continue
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for module in modules:
                if module.split(".")[0] not in SUPERVISOR_IMPORTS_OK:
                    problems.append(f"{name} line {node.lineno}: imports {module}, which is not on the supervisor's short list")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in SUPERVISOR_CALLS_NEVER:
                problems.append(f"{name} line {node.lineno}: calls {func.id}()")
            if isinstance(func, ast.Attribute) and func.attr in SUPERVISOR_METHODS_NEVER:
                problems.append(f"{name} line {node.lineno}: calls .{func.attr}()")
            if isinstance(func, ast.Attribute) and func.attr in PROCESS_STARTERS and isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                first = node.args[0] if node.args else None
                is_list = isinstance(first, ast.List) and ast.unparse(first) in ALLOWED_COMMAND_LISTS
                is_injected = isinstance(first, ast.Call) and isinstance(first.func, ast.Attribute) and first.func.attr == "command_for"       # self.command_for(port): the live command, built by live_command
                if not (is_list or is_injected):
                    problems.append(f"{name} line {node.lineno}: starts a process that is not one of the three allowed commands ({ast.unparse(first) if first is not None else 'no command'})")
                for kw in node.keywords:
                    if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                        problems.append(f"{name} line {node.lineno}: runs a command through a shell (shell=...)")
    has_scenarios = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCENARIOS" for t in node.targets):
            has_scenarios = True
            if ast.unparse(node.value) != EXPECTED_SCENARIOS:
                problems.append(f"{name} line {node.lineno}: SCENARIOS must be exactly {EXPECTED_SCENARIOS}")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "live_command":
            body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
            if [ast.unparse(s) for s in body] != EXPECTED_LIVE_BODY:
                problems.append(f"{name} line {node.lineno}: live_command must be exactly the fixed list, plus '--connected' and a name only when the name is in SCENARIOS (nothing else)")
            if not has_scenarios:
                problems.append(f"{name} line {node.lineno}: live_command needs the constant SCENARIOS tuple in the same file")
    return problems


def supervisor_problems() -> tuple[list[str], int]:
    files = sorted(SUPERVISOR.rglob("*.py")) if SUPERVISOR.exists() else []
    problems: list[str] = []
    for path in files:
        problems.extend(supervisor_problems_in_text(path.relative_to(PACKAGE).as_posix(), path.read_text(encoding="utf-8")))
    return problems, len(files)


BIND_SERVERS = {"ThreadingHTTPServer", "HTTPServer", "TCPServer", "ThreadingTCPServer", "UnixStreamServer"}
NEVER_A_HOST = {"0.0.0.0", "::", "[::]", "0:0:0:0:0:0:0:0"}


def live_bind_problems_in_text(name: str, text: str) -> list[str]:
    """The only address anything in the live part may listen on is the constant HOST, and HOST must be 127.0.0.1."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
            if called in BIND_SERVERS or called == "bind":
                first = node.args[0] if node.args else None
                host = first.elts[0] if isinstance(first, ast.Tuple) and first.elts else None
                if not (isinstance(host, ast.Name) and host.id == "HOST"):
                    problems.append(f"{name} line {node.lineno}: {called}(...) listens on an address that is not the constant HOST ({ast.unparse(first) if first is not None else 'none'})")
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "HOST" for t in node.targets):
            if not (isinstance(node.value, ast.Constant) and node.value.value == "127.0.0.1"):
                problems.append(f"{name} line {node.lineno}: HOST is not the constant 127.0.0.1")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip() in NEVER_A_HOST:
            problems.append(f"{name} line {node.lineno}: names an all-addresses host ({node.value!r})")
    return problems


def live_bind_problems() -> tuple[list[str], int]:
    files = sorted(LIVE_PART.rglob("*.py")) if LIVE_PART.exists() else []
    problems: list[str] = []
    for path in files:
        problems.extend(live_bind_problems_in_text(path.relative_to(PACKAGE).as_posix(), path.read_text(encoding="utf-8")))
    return problems, len(files)


def supervisor_check(checklist: Checklist) -> None:
    problems, count = supervisor_problems()
    checklist.record(not problems, "The live-run supervisor starts nothing but the three allowed commands (the live program from the fixed list live_command returns, `netstat -ano`, `taskkill /PID n /T /F`), through no shell, imports no other part of the project and nothing outside a short list (no network, os or file library), writes no file and uses no eval",
                     "; ".join(problems[:5]) if problems else f"{count} supervisor files read")
    clean = "import subprocess\nimport sys\n\nSCENARIOS = ('baseline', 'new_supplier', 'period_shift', 'unpredictable_dissolution')\n\n\ndef live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]\n    if connected in SCENARIOS:\n        command += ['--connected', connected]\n    return command\n\n\ndef f(self, pid):\n    subprocess.run(['netstat', '-ano'], capture_output=True)\n    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)\n    subprocess.Popen(self.command_for(self.port))\n"
    planted = ["import socket", "import urllib.request", "import os", "import shutil", "import http.client", "from cellpoc.live import server", "from ..setup import x",
               "import subprocess\nsubprocess.Popen('python x.py', shell=True)", "import subprocess\nsubprocess.run(['cmd', '/c', 'dir'])", "import subprocess\nsubprocess.Popen(['python', '-m', 'x'], shell=True)",
               "import subprocess\nsubprocess.run(['netstat', '-ano', '-b'])", "import subprocess\nsubprocess.run(cmd_from_somewhere)", "import subprocess\nsubprocess.run(['taskkill', '/IM', 'python.exe', '/F'])",
               "open('f', 'w')", "p.write_text('x')", "eval('1')", "p.unlink()", "def live_command(port):\n    return [sys.executable, '-m', 'cellpoc.live', '--host', '0.0.0.0']",
               "SCENARIOS = ('baseline', 'new_supplier', 'period_shift', 'unpredictable_dissolution')\ndef live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port), '--host', '0.0.0.0']\n    if connected in SCENARIOS:\n        command += ['--connected', connected]\n    return command",
               "SCENARIOS = ('baseline', 'new_supplier', 'period_shift', 'unpredictable_dissolution')\ndef live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]\n    command += ['--connected', connected]\n    return command",
               "SCENARIOS = ('baseline', 'new_supplier', 'period_shift', 'unpredictable_dissolution')\ndef live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]\n    if connected:\n        command += ['--connected', connected]\n    return command",
               "SCENARIOS = ('baseline', 'new_supplier', 'period_shift', 'unpredictable_dissolution')\ndef live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]\n    if connected in SCENARIOS:\n        command += ['--connected', connected, '--x']\n    return command",
               "SCENARIOS = ('baseline', 'anything')\ndef live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]\n    if connected in SCENARIOS:\n        command += ['--connected', connected]\n    return command",
               "def live_command(port, connected=None):\n    command = [sys.executable, '-B', '-m', 'cellpoc.live.embedded_main', '--port', str(port)]\n    if connected in SCENARIOS:\n        command += ['--connected', connected]\n    return command"]
    caught = [bool(supervisor_problems_in_text("planted.py", s)) for s in planted]
    checklist.record(not supervisor_problems_in_text("clean.py", clean) and all(caught),
                     "Self-test: the supervisor guard accepts the real command forms and catches every planted violation: a network library, os, shutil, an import of another part, a text command line, a command through a shell, an altered netstat or taskkill, an unknown program, "
                     "a command taken from elsewhere, file writing, deleting, eval, and an altered or extended live command (a host flag, an unconditional or loosely conditional --connected, an extra flag, a changed or missing scenario list)", f"caught {sum(caught)}/{len(planted)}; clean accepted: {not supervisor_problems_in_text('clean.py', clean)}")


def live_bind_check(checklist: Checklist) -> None:
    problems, count = live_bind_problems()
    checklist.record(not problems, "The live part listens only on the constant HOST, and HOST is 127.0.0.1: no file in it binds any other address or names an all-addresses host", "; ".join(problems[:4]) if problems else f"{count} live files read")
    planted = ["from http.server import ThreadingHTTPServer\nThreadingHTTPServer(('0.0.0.0', port), H)", "from http.server import ThreadingHTTPServer\nThreadingHTTPServer(('', port), H)", "from http.server import HTTPServer\nHTTPServer((host, port), H)",
               "from http.server import ThreadingHTTPServer\nThreadingHTTPServer(('::', port), H)", "import socket\ns = socket.socket()\ns.bind(('', 1))", "HOST = '0.0.0.0'", "HOST = 'localhost'", "x = '[::]'", "from http.server import ThreadingHTTPServer\nThreadingHTTPServer(address, H)"]
    clean = ["HOST = '127.0.0.1'\nfrom http.server import ThreadingHTTPServer\nThreadingHTTPServer((HOST, port), H)", "HOST = '127.0.0.1'\ns.bind((HOST, 0))"]
    caught = [bool(live_bind_problems_in_text("planted.py", s)) for s in planted]
    fine = [not live_bind_problems_in_text("clean.py", s) for s in clean]
    checklist.record(all(caught) and all(fine), "Self-test: the bind guard catches a listen on 0.0.0.0, on an empty host, on '::', on a variable host, on a bind with an empty host, a HOST that is not 127.0.0.1 and a stray all-addresses name, and accepts the real form (HOST, port)", f"caught {sum(caught)}/{len(planted)}; clean accepted {sum(fine)}/{len(fine)}")


def shell_check(checklist: Checklist) -> None:
    """The unified app (Stage A): what it may import, that nothing imports it, that it does no logic, and a self-test with planted violations that proves each guard can fail."""
    cannot_reach = {"virtual_lab", "decision_engine", "scoring", "cell_simulator", "comparison", "runner", "ingest", "modelling", "briefing", "planner", "executor", "platform_cell",
                    "platform_info", "platform_runner", "connected", "live", "viewer", "reports", "about_text"}
    reached = reach(ALLOWED, "shell")
    imported_by = sorted(part for part, allowed in ALLOWED.items() if "shell" in allowed)
    checklist.record(ALLOWED["shell"] == {"dashboard", "run_store", "contracts", "setup_app", "live_supervisor", "vision"} and not imported_by and not (reached & cannot_reach) and "setup" in reached and ALLOWED["setup_app"] == {"setup"}
                     and ALLOWED["live_supervisor"] == set() and [p for p, allowed in ALLOWED.items() if "live_supervisor" in allowed] == ["shell"],
                     "The unified app may import only the dashboard, the run-record reader, the shared data shapes, the setup app (Stage B), the live-run supervisor (Stage C) and the vision reader (2026-10-22, for the Vision page), so it reaches the setup rules and nothing else beyond; it cannot reach the lab, the engine, the simulator, the connected loop or the live program itself through any of them; the supervisor imports no other part and only the shell imports it; and no part may import the unified app",
                     f"it reaches: {', '.join(sorted(reached))}" + (f"; imported by {imported_by}" if imported_by else ""))
    problems, count = shell_problems()
    checklist.record(not problems, "The unified app's own files contain no logic (no arithmetic, sorting, min/max/sum, filtering or calculation libraries, no division at all), never start a process, touch a file or open a connection (no subprocess, os, shutil, socket, tempfile or pathlib, no open(), exec, write or delete calls), and name no web address except this computer's",
                     "; ".join(problems[:6]) if problems else f"{count} unified-app files read")
    # a self-test: each guard is shown to catch a planted violation, and not to flag clean text
    planted_logic = ["x = a * b", "y = sorted(z)", "total += 1", "m = [a for a in b if a]", "import math", "r = a / b", "q = max(a, b)", "df.groupby('x')", 'u = "http://example.com/data"', 'u = "https://example.org"']
    clean_logic = ['u = "http://localhost:8502"', 'v = "http://127.0.0.1:8504/x"', 'label = f"{a:.1f}x"', "for n, e in enumerate(items, start=1):\n    pass", 'text = "a" + "b"', "nav.run()", "import html"]
    caught_logic = [bool(logic_problems_in_text("planted.py", s, local_addresses_ok=True, no_process=True)[0]) for s in planted_logic]
    clean_ok = [not logic_problems_in_text("clean.py", s, local_addresses_ok=True, no_process=True)[0] for s in clean_logic]
    planted_process = ["import subprocess", "import os", "from os import system", "import shutil", "import socket", "import tempfile", "from pathlib import Path", "f = open('x', 'w')", "p.write_text('x')",
                       "subprocess.Popen(['x'])", "exec('x')", "p.unlink()", "import threading"]
    caught_process = [bool(logic_problems_in_text("planted.py", s, local_addresses_ok=True, no_process=True)[0]) for s in planted_process]
    process_rule_is_the_shells_own = all(not logic_problems_in_text("dashboard_like.py", s)[0] for s in ("import subprocess", "import os"))       # the rule is switched on for the shell's files only
    dashboard_still_strict = bool(logic_problems_in_text("planted.py", 'u = "http://localhost:8502"')[0])       # the dashboard's own rule is unchanged: no web address at all
    wrong_imports = ["from cellpoc.virtual_lab import VirtualLab", "from cellpoc.decision_engine import AdaptiveStrategy", "from cellpoc.setup import load_setup", "from ..live import server",
                     "from cellpoc.connected import run", "from cellpoc.runner import run_campaign", "import cellpoc.settings.loader", "from cellpoc.platform_runner import run_platform"]
    refused = [bool(parts_in_text(s, ["shell"]) - ALLOWED["shell"]) for s in wrong_imports]
    fine_imports = ["from cellpoc.dashboard import data, style", "from cellpoc import run_store", "from cellpoc.contracts.run_record import RunRecord", "from cellpoc.shell import context", "from cellpoc.setup_app.app import embedded"]
    accepted = [not (parts_in_text(s, ["shell"]) - ALLOWED["shell"] - {"shell"}) for s in fine_imports]
    others_importing = [parts_in_text("from cellpoc.shell import app", ["dashboard"]) == {"shell"}, parts_in_text("import cellpoc.shell.app", ["live"]) == {"shell"}, "shell" not in ALLOWED["dashboard"]]
    setup_app_back = [bool(parts_in_text(s, ["setup_app"]) - ALLOWED["setup_app"]) for s in ("from cellpoc.shell import app", "from cellpoc.dashboard import style", "from ..shell import context", "import cellpoc.shell.setup_host")]
    checklist.record(all(caught_logic) and all(clean_ok) and all(caught_process) and process_rule_is_the_shells_own and dashboard_still_strict and all(refused) and all(accepted) and all(others_importing) and all(setup_app_back),
                     "Self-test: the unified-app guard catches planted arithmetic, sorting, max, division, a running total, a filtered list, a calculation library, a group-by and two outside web addresses; catches thirteen ways for the unified app's own files to start a process or touch a file "
                     "(subprocess, os, shutil, socket, tempfile, pathlib, threading, open, exec, writing, deleting, Popen); refuses imports of the lab, the engine, the setup rules directly, the live run, the connected loop, the runner and the platform runner, while accepting localhost addresses, number formatting, "
                     "counting, nav.run(), and the dashboard, reader, data-shape and setup-app imports; the dashboard's own rules are unchanged; an import of the unified app by another part is seen; and a setup-app file importing the unified app or the dashboard is refused",
                     f"logic caught {sum(caught_logic)}/{len(caught_logic)}; process/file caught {sum(caught_process)}/{len(caught_process)}; clean accepted {sum(clean_ok)}/{len(clean_ok)}; wrong imports refused {sum(refused)}/{len(refused)}; right imports accepted {sum(accepted)}/{len(accepted)}; setup app back-imports refused {sum(setup_app_back)}/{len(setup_app_back)}")
