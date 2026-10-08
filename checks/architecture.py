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
    "dashboard": {"run_store", "contracts", "settings"},
    "runner": {"settings", "contracts", "virtual_lab", "decision_engine", "cell_simulator", "run_store",
               "comparison"},
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
