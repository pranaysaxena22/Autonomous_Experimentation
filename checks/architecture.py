"""Guards the separation of the five parts by reading which parts import which.

Each part may import only the parts listed for it. This is what keeps the dashboard free of
logic, the decision engine blind to the hidden truth, and the lab ignorant of the cell.
"""
from __future__ import annotations

import ast
from pathlib import Path

from checks.common import Checklist

PACKAGE = Path(__file__).resolve().parents[1] / "cellpoc"

# part -> the other parts it is allowed to import
ALLOWED = {
    "settings": set(),
    "contracts": {"settings"},
    "virtual_lab": {"contracts", "settings"},
    "decision_engine": {"contracts", "settings"},
    "cell_simulator": {"contracts", "settings"},
    "run_store": {"contracts"},
    "scoring": {"contracts", "settings", "virtual_lab"},       # judges results against the truth, after the fact
    "comparison": {"contracts", "settings", "virtual_lab", "decision_engine", "scoring"},
    "about_text": {"contracts", "settings"},
    "dashboard": {"run_store", "contracts"},          # it only reads the run record
    "runner": {"settings", "contracts", "virtual_lab", "decision_engine", "cell_simulator", "run_store",
               "comparison", "about_text"},
}
PARTS = set(ALLOWED)
HIDDEN = ("_truth", "oracle")  # modules only the virtual lab itself and the after-the-fact scoring may touch
MAY_SEE_TRUTH = {"virtual_lab", "scoring"}


def _imported_parts(path: Path) -> set[str]:
    """Which parts of cellpoc does this file import?"""
    folders = list(path.relative_to(PACKAGE).parts[:-1])  # the package this file sits in, below cellpoc
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
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


DASHBOARD = PACKAGE / "dashboard"
DIVISION_ALLOWED_IN = "throughput.py"   # the single documented exception: autonomous trials/week divided by the manual baseline
FORBIDDEN_CALLS = {"sum", "max", "min", "round", "sorted", "abs", "divmod", "pow"}
FORBIDDEN_METHODS = {"mean", "median", "sum", "std", "var", "groupby", "agg", "sort_values", "cumsum", "idxmax",
                     "idxmin", "quantile", "rolling", "resample", "nlargest", "nsmallest", "pct_change"}
FORBIDDEN_IMPORTS = {"random", "statistics", "math", "numpy", "scipy", "datetime", "time", "itertools", "functools"}
ALLOWED_OPS = (ast.Add,)   # joining text; every other arithmetic operator is refused


def dashboard_problems() -> tuple[list[str], int]:
    """(problems, number of files read). A problem is anything that looks like the dashboard doing its own logic."""
    problems: list[str] = []
    files = sorted(DASHBOARD.rglob("*.py")) if DASHBOARD.exists() else []
    divisions = 0
    for path in files:
        name = path.relative_to(PACKAGE).as_posix()
        text = path.read_text(encoding="utf-8")
        if "http://" in text or "https://" in text:
            problems.append(f"{name} contains a web address (the dashboard must work offline)")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.BinOp) and not isinstance(node.op, ALLOWED_OPS):
                if isinstance(node.op, ast.Div) and path.name == DIVISION_ALLOWED_IN:
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
            elif isinstance(node, ast.comprehension) and node.ifs:
                problems.append(f"{name} line {node.iter.lineno}: filters a list (an 'if' inside a comprehension)")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                           else ([node.module] if node.module and node.level == 0 else []))
                for module in modules:
                    if module and module.split(".")[0] in FORBIDDEN_IMPORTS:
                        problems.append(f"{name} line {node.lineno}: imports {module}")
    if divisions > 1:
        problems.append(f"{DIVISION_ALLOWED_IN} divides {divisions} times; only one division is allowed")
    return problems, len(files)


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
            text = path.read_text(encoding="utf-8")
            if any(f"virtual_lab.{h}" in text or f"import {h}" in text or f"from .{h}" in text for h in HIDDEN):
                breaches.append(f"{relative} reaches into the virtual lab's hidden truth")
    checklist.record(not breaches, "Each part imports only the parts it is allowed to",
                     "; ".join(breaches) if breaches else f"{scanned} source files scanned")
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
