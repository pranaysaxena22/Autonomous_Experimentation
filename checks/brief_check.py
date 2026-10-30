"""Health check for Stage 4-1 (the decision engine's brief): does the engine get exactly what Stage 3 concluded, no more and no less?

In plain words it checks that: the brief survives being written out and read back unchanged, an unknown status or a wrong version is refused, and only a CARRIED result is ever marked usable for decisions
(an exploratory or not-assessed result never is); the range factor is the median of the later-dates factors, never below 1 and never an average (known answers, including a single wild factor);
on made-up results a strong, a borderline and a weak result become carried, exploratory and not assessed; on the real saved Stage 3 answers the briefs match the 3b-1 decisions exactly (7 carried results,
the hard mock's dissolution exploratory, everything else not assessed with its reason), name the very model the selection rule chose, carry every data-status label and the table's exploratory or robustness label,
and say that tensile strength is one finding with hardness; the shared shape imports nothing from the project (so the engine reads it without touching the modelling part); building the briefs refits nothing and
writes nothing into the project; and the architecture guard, including the new one-direction rule for the engine, passes. Nothing uses the network.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.briefing import build_brief, range_factor, render  # noqa: E402
from cellpoc.contracts import BRIEF_VERSION, STATUS_CARRIED, STATUS_EXPLORATORY, STATUS_NOT_ASSESSED, EngineBrief, TargetBrief  # noqa: E402
from cellpoc.modelling import build_table_for_setup  # noqa: E402
from cellpoc.modelling.carry import BORDERLINE, CARRIED, decide, decide_all  # noqa: E402
from cellpoc.modelling.findings import UNIFYING_STATEMENT  # noqa: E402
from cellpoc.modelling.fixtures import NAMES, fixture_available, fixture_setup  # noqa: E402
from cellpoc.modelling.models import FULL  # noqa: E402
from cellpoc.modelling.selection import select  # noqa: E402
from cellpoc.modelling.validate import run_validation  # noqa: E402
from cellpoc.setup import PROJECT_ROOT  # noqa: E402
from checks import architecture, modelling_cases  # noqa: E402
from checks.common import Checklist  # noqa: E402
from checks.models_check import forbidden_in, project_files  # noqa: E402

CACHE = ROOT / "runs" / "modelling" / "cache_full"
BASE = {"mean": 1.0, "nearest": 1.2}


def sample_brief() -> EngineBrief:
    return EngineBrief(BRIEF_VERSION, "t", "SYNTHETIC DATA", "", (
        TargetBrief("a", "A", STATUS_CARRIED, "linear", "Linear regression (ridge)", "honest", "over-confident", 1.2, "the median of 3", "", ("x", "y")),
        TargetBrief("b", "B", STATUS_EXPLORATORY, "forest", "Random forest", "honest", None, None, "", "EXPLORATORY: borderline"),
        TargetBrief("c", "C", STATUS_NOT_ASSESSED, reason="Calibration not assessed: too weak.")), ("a caveat",))


def shape_checks(cl: Checklist) -> None:
    b = sample_brief()
    back = EngineBrief.from_json(b.to_json())
    cl.record(back == b and back.targets[0].calculated_from == ("x", "y") and isinstance(back.targets, tuple), "The brief survives being written out and read back unchanged (every field, including the lists)", "")
    raw = json.loads(b.to_json())
    wrong_version, wrong_status = {**raw, "version": 99}, {**raw, "targets": [{**raw["targets"][0], "status": "great"}]}
    refused = []
    for bad in (wrong_version, wrong_status):
        try:
            EngineBrief.from_json(json.dumps(bad))
            refused.append(False)
        except ValueError:
            refused.append(True)
    cl.record(all(refused), "A brief with an unknown version or an unknown status is refused with a plain message", str(refused))
    cl.record([t.usable_for_decisions for t in b.targets] == [True, False, False] and [t.result for t in b.usable()] == ["a"],
              "Only a CARRIED result is usable for decisions: an exploratory result and a not-assessed result never are", "")
    try:
        dataclasses.replace(b.targets[0]).__setattr__("status", STATUS_NOT_ASSESSED)
        frozen = False
    except dataclasses.FrozenInstanceError:
        frozen = True
    cl.record(frozen, "A brief cannot be altered after it is made (the engine cannot promote an exploratory result to carried)", "")
    tree = ast.parse((ROOT / "cellpoc" / "contracts" / "engine_brief.py").read_text(encoding="utf-8"))
    imported = {n.module.split(".")[0] if isinstance(n, ast.ImportFrom) and n.module else a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in getattr(n, "names", [])}
    levels = [n.level for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    cl.record(not any(levels) and imported <= {"json", "dataclasses", "__future__"}, "The brief's shape imports nothing from the project, so the engine can read it without touching the modelling part", str(sorted(imported)))


def factor_checks(cl: Checklist) -> None:
    cases = [([None, 0.8, 0.9], 1.0), ([None, 1.5, 2.0, 1.2], 1.5), ([1.0, 1.0, 5.0], 1.0), ([None], None), ([], None), ([1.3], 1.3), ([2.0, 4.0], 3.0), ([None, 1.0, 1.0, 9.0], 1.0), ([None, 1.0, 1.0, 9.0, 9.0], 5.0)]
    got = [range_factor(f) for f, _ in cases]
    cl.record(got == [e for _, e in cases], "Range factor, known answers: the median of the factors that exist (the average of the middle two when there is an even number), never below 1, never a plain average "
              "(one wild factor of 5 or 9 cannot move it), and none when there is none", str(got))


def made_up_checks(cl: Checklist) -> None:
    rows = {}
    for name, e in (("strong", 0.4), ("borderline", 0.75), ("weak", 0.9)):
        v = modelling_cases.fake_validation({"batch": {**BASE, "quadratic": e}, "date": {**BASE, "quadratic": e}})
        rows[name] = build_brief(v, [decide(v, "y")]).targets[0]
    cl.record([rows[k].status for k in ("strong", "borderline", "weak")] == [STATUS_CARRIED, STATUS_EXPLORATORY, STATUS_NOT_ASSESSED], "On made-up results an error of 0.40, 0.75 and 0.90 of the spread become carried, exploratory and not assessed (the 3b-1 rule, unchanged)",
              str([rows[k].status for k in rows]))
    s, b, w = rows["strong"], rows["borderline"], rows["weak"]
    cl.record(s.model_key == "quadratic" and s.model_label and s.range_factor is not None and s.range_factor >= 1.0 and b.model_key == "quadratic" and "EXPLORATORY" in b.reason
              and w.model_key is None and w.model_label is None and w.range_factor is None and w.reason and not w.usable_for_decisions and not b.usable_for_decisions and s.usable_for_decisions,
              "A carried result names its model and a range factor of at least 1; an exploratory one is labelled and unusable; a not-assessed one has no model, no factor and a plain reason", "")


def real_checks(cl: Checklist) -> None:
    files = len(list(CACHE.glob("*.pkl"))) if CACHE.exists() else 0
    if files < 280 or not all(fixture_available(n) for n in NAMES):
        cl.skip("The briefs on the saved Stage 3 answers", "they (or the real public data) are not on this computer: double-click run_full_validation.bat first")
        return
    validations = [run_validation(build_table_for_setup(fixture_setup(n), None, PROJECT_ROOT, n), FULL, n_jobs=1, cache=CACHE, save=False) for n in NAMES]
    decisions = decide_all(validations)
    by = {v.table.name: v for v in validations}
    briefs = {v.table.name: build_brief(v, decisions) for v in validations}
    counts = {n: [sum(t.status == s for t in b.targets) for s in (STATUS_CARRIED, STATUS_EXPLORATORY, STATUS_NOT_ASSESSED)] for n, b in briefs.items()}
    expected = {"mock_easy": [3, 0, 0], "mock_hard": [2, 1, 0], "mock_small": [0, 0, 3], "batch_production": [2, 0, 2], "batch_production_extended": [0, 0, 4], "literature": [0, 0, 3]}
    cl.record(counts == expected and sum(c[0] for c in counts.values()) == 7, "The briefs match the 3b-1 decisions exactly: 7 carried results (3 easy mock, 2 hard mock, real hardness and tensile), the hard mock's dissolution exploratory, everything else not assessed", str(counts))
    ok_models = all(t.model_key == select(by[n], t.result).chosen and t.model_label for n, b in briefs.items() for t in b.targets if t.status != STATUS_NOT_ASSESSED)
    ok_flags = all((t.status == d.status.replace("borderline", "exploratory").replace("skipped", "not_assessed")) for b in briefs.values() for t in b.targets for d in decisions if d.table == b.table and d.result == t.result)
    cl.record(ok_models and ok_flags, "Every carried or exploratory result names the very model the selection rule chose, and every status equals the carry decision's", "")
    cl.record(all(t.reason and t.model_key is None and t.range_factor is None and not t.usable_for_decisions for b in briefs.values() for t in b.targets if t.status == STATUS_NOT_ASSESSED),
              "Every not-assessed result has its plain reason and no model and no range factor", "")
    labelled = all(b.data_label == (by[b.table].table.label.short if by[b.table].table.label else "") and b.data_label in render(b) and b.data_label in "".join(l for l in render(b).splitlines() if l.startswith("#")) for b in briefs.values())
    tagged = all(b.table_tag == (by[b.table].table.tag or "") and (not b.table_tag or b.table_tag in render(b)) for b in briefs.values())
    cl.record(labelled and tagged and briefs["batch_production_extended"].table_tag and briefs["literature"].table_tag and "REAL PUBLIC DATA" in briefs["batch_production"].data_label and "SYNTHETIC" in briefs["mock_easy"].data_label,
              "Every brief carries its data-status label (in its headings too) and the exploratory or robustness-only label of its table", "")
    cl.record(all(UNIFYING_STATEMENT in b.caveats and any("depends on the table" in c for c in b.caveats) for b in briefs.values()), "Every brief carries the unifying statement and says that carried status belongs to the table it was judged on", "")
    t = briefs["batch_production"].target("tbl_tensile")
    cl.record("tbl_av_hardness" in t.calculated_from and "one finding" in render(briefs["batch_production"]), "Real tensile strength is marked as calculated from hardness (one finding, not two)", str(t.calculated_from))
    factors = [t.range_factor for b in briefs.values() for t in b.targets if t.status != STATUS_NOT_ASSESSED]
    cl.record(all(f is not None and f >= 1.0 for f in factors) and any(f > 1.0 for f in factors), "Every range factor is at least 1 (never narrower than stated), and some results really are widened", f"{min(factors):.2f} to {max(factors):.2f}")
    allowed_keys = {"version", "table", "data_label", "table_tag", "targets", "caveats"}
    allowed_target = {f.name for f in dataclasses.fields(TargetBrief)}
    shape = all(set(json.loads(b.to_json())) == allowed_keys and all(set(t) == allowed_target for t in json.loads(b.to_json())["targets"]) for b in briefs.values())
    cl.record(shape, "A brief holds only the listed fields: no measurement, no row of data and nothing from any lab", "")
    before_cache = sorted(p.name for p in CACHE.glob("*.pkl"))
    again = [build_brief(v, decisions) for v in validations]
    cl.record(again == list(briefs.values()) and sorted(p.name for p in CACHE.glob("*.pkl")) == before_cache, "Building the briefs again gives identical briefs and adds nothing to the saved answers: nothing is refitted", "")


def main() -> int:
    cl = Checklist("PLATFORM STAGE 4-1: the decision engine's brief (does the engine get exactly what Stage 3 concluded?)")
    before = project_files()
    shape_checks(cl)
    factor_checks(cl)
    made_up_checks(cl)
    real_checks(cl)
    leak = [str(p.relative_to(ROOT)) for folder in ("modelling", "decision_engine") for p in (ROOT / "cellpoc" / folder).rglob("*.py") if "briefing" in p.read_text(encoding="utf-8")]
    cl.record(not leak, "Neither the modelling part nor the decision engine imports or names the briefing piece", "; ".join(leak))
    found = forbidden_in(sorted((ROOT / "cellpoc" / "briefing").glob("*.py")))
    cl.record(not found, "The briefing code contains no random splitter or sampler", "; ".join(found[:3]))
    architecture.check(cl)
    after = project_files()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    cl.record(not changed, "Running the check wrote nothing into the project", ", ".join(changed[:3]))
    return cl.print()


if __name__ == "__main__":
    sys.exit(main())
