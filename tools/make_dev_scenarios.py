r"""The development lab's four scenarios (Stage 4-2): writes each scenario's history and shows what Stage 3 concludes about it. Output goes to runs/devlab/ (not in git).

Run:  .venv\Scripts\python.exe tools\make_dev_scenarios.py        (or double-click make_dev_scenarios.bat; about 10 minutes, because Stage 3's full comparison is run on each history)
For each scenario it: generates a history of 3,000 experiments with a fixed fresh seed, writes it as a CSV in the mock data's format, runs Stage 3 on it exactly as on any table (grouped validation, the carry rule,
calibration), and writes the engine's brief for it. The summary says what each scenario was DESIGNED to show and what Stage 3 actually concluded, and flags any mismatch. Nothing is tuned afterwards.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.briefing import build_brief, render  # noqa: E402
from cellpoc.modelling import build_table_for_setup  # noqa: E402
from cellpoc.modelling.carry import decide_all  # noqa: E402
from cellpoc.modelling.fixtures import synthetic_file_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from cellpoc.virtual_lab.dev_lab import HISTORY_EXPERIMENTS, HISTORY_SEEDS, NEW_SUPPLIER_FROM, PERIOD_STEP_FROM, SCENARIOS, DevLab  # noqa: E402

INTENT = {
    "baseline": "everything predictable and nothing shifts: all three results should be CARRIED",
    "new_supplier": "supplier and date move the recipes in the history; in the campaign an UNSEEN supplier takes over from trial %d" % NEW_SUPPLIER_FROM,
    "period_shift": "supplier and date move the recipes in the history; from campaign trial %d the product truly changes (dissolution down 6, hardness up 0.8) with no sign in the inputs" % PERIOD_STEP_FROM,
    "unpredictable_dissolution": "dissolution has a rough surface Stage 3 should NOT carry (not assessed or exploratory), while hardness and friability stay carried",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    out = ROOT / "runs" / "devlab"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    validations, briefs = [], []
    for name, scenario in SCENARIOS.items():
        history = DevLab(scenario, HISTORY_SEEDS[name]).history(HISTORY_EXPERIMENTS)
        path = out / f"dev_{name}.csv"
        history.to_csv(path, index=False, lineterminator="\n")
        setup = synthetic_file_setup(f"runs/devlab/dev_{name}.csv", "cellpoc/virtual_lab/dev_lab.py")
        table = build_table_for_setup(setup, None, PROJECT_ROOT, f"dev_{name}")
        print(f"  {name}: {len(history)} rows written; running Stage 3 on it ...", flush=True)
        validations.append(run_validation(table, FULL, n_jobs=args.jobs, cache=out / "cache_full"))
    decisions = decide_all(validations)
    lines = ["# The development lab's scenarios: what each was designed to show, and what Stage 3 concluded", "",
             "**SYNTHETIC DATA** from the development lab (`cellpoc/virtual_lab/dev_lab.py`), not the sealed acceptance lab and not real tablets. Each history has 3,000 experiments (about 3,700 rows) from a fixed fresh seed; "
             "Stage 3 was run on it exactly as on any table. Nothing was adjusted after seeing these results.", ""]
    for v in validations:
        brief = build_brief(v, decisions)
        name = brief.table.removeprefix("dev_")
        (out / f"brief_{brief.table}.json").write_bytes(brief.to_json().encode("utf-8"))
        (out / f"brief_{brief.table}.md").write_bytes(render(brief).encode("utf-8"))
        lines += [f"## {name} [SYNTHETIC DATA]", "", f"- **Designed to show:** {INTENT[name]}.", f"- History seed {HISTORY_SEEDS[name]}; file `runs/devlab/dev_{name}.csv`.", "- **What Stage 3 concluded:**"]
        for t in brief.targets:
            what = {"carried": f"CARRIED with {t.model_label}", "exploratory": f"CARRIED BUT EXPLORATORY with {t.model_label} (the engine makes no decision from it)",
                    "not_assessed": "NOT ASSESSED (no model, no probability)"}[t.status]
            factor = f"; range factor {t.range_factor:.2f}" if t.range_factor is not None else ""
            lines.append(f"  - {t.label}: {what}{factor}.")
        lines.append("")
        carried = {t.result for t in brief.targets if t.status == "carried"}
        if name == "unpredictable_dissolution":
            ok = "dissolution_30min_pct" not in carried and {"hardness_kp", "friability_pct"} <= carried
        elif name == "baseline":
            ok = carried == {"dissolution_30min_pct", "hardness_kp", "friability_pct"}
        else:
            ok = True
        lines += [f"- **As designed?** {'yes' if ok else 'NO: this does not match what the scenario was designed to show; reported as it is'}", ""]
    lines += ["## What this does not show", "", "- Anything about real tablets or a client.", "- How the engine behaves: it is not built yet (Stage 4-3). These are the worlds it will be developed against."]
    (out / "scenario_summary.md").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"\n  wrote runs\\devlab\\scenario_summary.md\n\nFinished in {time.time() - started:.0f} s. Open runs\\devlab\\scenario_summary.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
