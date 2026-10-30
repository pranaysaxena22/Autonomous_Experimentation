r"""4-4R: the development comparison for the ADOPTED (recalibrated) engine, designed exactly like the original 4-4 (docs/decisions.md, "4-4R"): the four scenarios, 40 paired campaigns each (seeds 11500 to 11539),
three strategies (the adopted engine, the same models without governance, random recipes), the same measures, the same verdict rule, the same report. Descriptive: no pass or fail bar.

Run:  .venv\Scripts\python.exe tools\run_dev_comparison_r.py        (about 30 minutes on 6 cores; each campaign is saved as it finishes, so a stopped run carries on)
It needs the scenario briefs from make_dev_scenarios.bat. Writes runs\devcomparison_r\ (summary.md, campaigns.csv, cache). Synthetic data only; the sealed acceptance lab is never touched.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.comparison.dev_comparison import SCENARIO_NAMES, run_all  # noqa: E402
from cellpoc.comparison.dev_comparison_report import after_event, build_report, first_good, headline  # noqa: E402

SEEDS = tuple(range(11500, 11540))                                         # reserved for 4-4R in docs/decisions.md; checked against every spent, reserved and sealed range
STRATEGIES = ("recalibrated", "ungoverned", "random")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    briefs = {}
    for s in SCENARIO_NAMES:
        path = ROOT / "runs" / "devlab" / f"brief_dev_{s}.json"
        if not path.exists():
            print(f"The brief for the '{s}' scenario is missing ({path.name}). Double-click make_dev_scenarios.bat first.")
            return 1
        briefs[s] = path.read_text(encoding="utf-8")
    out = ROOT / "runs" / "devcomparison_r"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    records = run_all(briefs, str(out / "cache"), args.jobs, seeds=SEEDS, strategies=STRATEGIES, progress=lambda done, total: print(f"  {done} of {total} campaigns done ({(time.time() - started) / 60:.1f} min)", flush=True))
    seconds = time.time() - started
    (out / "summary.md").write_bytes(build_report(records, seconds, engine="recalibrated", seeds=SEEDS).encode("utf-8"))
    rows = ["scenario,strategy,seed,truly_good_of_30,first_truly_good_trial,truly_good_after_event,measured_passes"]
    for r in sorted(records, key=lambda r: (r.scenario, r.strategy, r.seed)):
        rows.append(f"{r.scenario},{r.strategy},{r.seed},{headline(r)},{first_good(r) or ''},{after_event(r)},{sum(r.measured_pass)}")
    (out / "campaigns.csv").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
    print(f"\n  wrote runs\\devcomparison_r\\summary.md and campaigns.csv ({len(records)} campaigns, seeds {SEEDS[0]} to {SEEDS[-1]})\n\nFinished in {seconds / 60:.0f} minutes. Open runs\\devcomparison_r\\summary.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
