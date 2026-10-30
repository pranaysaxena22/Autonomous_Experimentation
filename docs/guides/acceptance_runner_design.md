# Stage 4-5: the acceptance runner and the one acceptance run — DESIGN PROPOSAL

**STATUS: PROPOSED FOR YOUR REVIEW. NOT APPROVED. NOTHING BUILT. NOTHING RUN.** Written 2026-10-13. **SYNTHETIC.** Everything in this document concerns a synthetic lab; nothing here says anything about real tablets or a client.

This document is the design review that the plan says must happen before the sealed acceptance run, "never skipped". It exists so that you can read it, change it and approve it (or not) in writing. **No part of the sealed lab was opened, imported or run to write it:** it is based only on `acceptance/README.md`, `acceptance/LEDGER.md`, `acceptance/SEAL.json` and `docs/decisions.md`. Where the design needs something that only the lab's code can tell us, it says so and asks you (decision D2 below).

---

## 1. The question the acceptance run answers, in plain words

During development the decision engine and the development lab were built and tuned together, on four scenarios. So a good result there cannot show that the engine is not merely good at that one lab. The sealed lab is a **second, different synthetic lab** (different formulas, different noise, supplier and batch effects) that nobody tuned against. The acceptance run asks:

> **On a lab the engine was never developed against, does the adopted engine still choose clearly better recipes than random recipes, and how does it compare with the same models used without governance?**

It is a check for *overfitting to the development lab*. It is not a test of real-world performance, and it cannot be one: the sealed lab is still a computer program, and — as the permanent caveat says — its shape constants were adjusted twice by someone who knew Stage 3's findings.

**Permanent caveat, to appear word for word in every acceptance report:** *This lab's shape constants were adjusted twice by someone aware of Stage 3's findings, though no Stage 3 model or code was consulted. This is not a fully blind acceptance test.*

## 2. What is already known (so that nobody is surprised by the run)

From the Stage 4 Acceptance Readiness Summary, measured in the development lab:
- the adopted engine **beats random recipes in all four scenarios**, by a wide margin (+4.5 to +28.0 truly good recipes per 30-trial campaign);
- it **loses to the same models with no governance in all four scenarios** (-0.4, -1.6, -1.6, -3.2), nearly all of that cost in rules 3 and 4 (exploratory picks and bridging trials), by design;
- ten limitations are open (false-alarm rate, intermediate stated chances not reliably honest, reshaping shifts untested, and so on).

So the run is **not expected to show the adopted engine is better than the ungoverned one**, and the design does not pretend otherwise. What it can show is whether the *pattern* seen in development (far better than random; a small, explained cost against ungoverned) carries over to a different lab, or whether it was an accident of the development lab.

## 3. What would be run

| Item | Proposal |
|---|---|
| Strategies (three arms, as in 4-4R) | the adopted engine (`RecalibratedStrategy`, R), the same models without governance (ungoverned), random recipes |
| Campaigns | 40 paired campaigns, one per sealed seed 7,000,101 to 7,000,140; each arm sees the identical lab day per seed |
| Trials per campaign | 30 (the same as 4-4 and 4-4R) |
| Starting data per campaign | the lab's own generated history in the 21-column format, read by Stage 2's reader, prepared by Stage 3's modelling table, turned into the engine's brief by Stage 4-1: the real chain, as it would run on a client's file |
| Scenario | the lab's ordinary day (no event) unless the lab's own design provides events (decision D2) |
| Scoring | on the sealed lab's noise-free truth, in each trial's own context, after the campaign (never visible to any arm) |
| Measures | exactly 4-4R's: truly good recipes per 30-trial campaign; paired difference, adopted minus other arm, per campaign; paired bootstrap 95% interval (2,000 resamples, the fixed 4-4 bootstrap seed 20261014); stated-chance reliability and Brier tables; the automatic "things that do not look good" section; "what this does not show" |
| Platform cell simulator | **not used.** The acceptance run tests the decision engine on a lab, not the robot cell. |

## 4. How the result would be read — fixed in advance

I propose that the verdict wording is **fixed now**, before any result exists, in the same descriptive style as 4-4 and 4-4R, with no pass/fail bar (decision D3). For each of the two comparisons (adopted vs random; adopted vs ungoverned), "better" only if the whole 95% interval is above 0, "worse" only if wholly below, otherwise "no clear difference". The report then states which of three readings applies, using this table, written before the run:

| Reading | Defined as | What the report says |
|---|---|---|
| **Pattern carries over** | adopted engine better than random (interval wholly above 0) **and** its gap to ungoverned is no more than twice the largest gap seen in 4-4R in a comparable scenario (that is, no worse than about -6.4 in the lab's units; this bound is stated in advance only so the reading is not chosen after the fact) | "The development pattern was seen again on a lab the engine had not met." |
| **Partly** | better than random but the gap to ungoverned is larger than that bound, or the interval against random is not wholly above 0 in some part of the report | "The engine beat random in some respects only / cost more than in development; development results should not be relied on beyond the development lab." |
| **Does not carry over** | adopted engine not better than random, or worse than random | "The development results did not carry over to this lab. They were most likely specific to the development lab." |

Whichever reading applies is reported in full, with every figure, including everything that looks bad. **Nothing is tuned after the run** (see section 6).

## 5. The run day, step by step (each step recorded in `acceptance/LEDGER.md`)

0. **Preconditions, checked by the runner itself and refusing to start otherwise:** the full health-check suite is green; the working tree is clean and the commit is recorded; the sealed lab's fingerprints match `SEAL.json` and `docs/decisions.md` (`check_seal.bat`); the three engine files' fingerprints match the engine lock; the seed guard is active; the ledger has no earlier `ACCEPTANCE RUN` entry for this block; no `OPENED` entry exists.
1. **Dry run on the development lab, never on the sealed lab.** The runner takes the lab as a parameter. The identical code path is run end to end on the development lab with a *new* block of development seeds (proposal: 12000 to 12039, to be checked against the seed log at build time and reserved then). This proves the pipeline, the scoring, the report and the refusals work, without touching a sealed seed.
2. **Ledger entry written first:** "ACCEPTANCE RUN started", with date, commit, fingerprints verified, the design version approved.
3. **The run, once.** 120 campaigns (40 seeds × 3 arms). Estimated computing time about 10 minutes (4-4R's 480 campaigns took 27 minutes).
4. **The report is written by code** into `runs/acceptance/`, carrying the permanent caveat in every file (the check refuses a file without it), the label SYNTHETIC, and the reading from section 4.
5. **Ledger entry written after:** "ACCEPTANCE RUN completed", with the result's file fingerprint.
6. **Commit the report.** Nothing about the engine, its constants, the lab or the runner changes afterwards for the purpose of "improving" this result.

## 6. Rules that make the run honest (each would be tested by planted failures, like every other guard)

1. **One run only.** A second run on seeds 7,000,101 to 7,000,140 is refused by the runner (it reads the ledger). A different lab version needs new seeds and a new design review.
2. **No change after the result.** No engine constant, engine file, lab file or scoring rule may be changed in response to the result. If a flaw in the runner is found, the run stops and is reported (never patched in place), as with 4-4.
3. **The runner lives inside `acceptance/`.** It is the only code allowed to import the sealed lab (the seal check already scans for any other import).
4. **Fixed in advance:** arms, seeds, number of trials, measures, bootstrap seed, section 4's reading table, and the report template. None can change after the run starts.
5. **A crash.** If the runner crashes **before** the first call into the sealed lab, it may be repaired and run again (the ledger records the attempt). If it crashes **after** the first call into the sealed lab, I propose that the run is **void and the seeds are spent** (decision D5), because looking at partial output and then repairing the code is exactly a "choice made after looking at a result". The dry run in step 1 is the protection against that.
6. **The result is reported even if it is bad,** in the same detail as a good one.

## 7. What this run would NOT establish (to be stated in the report)

- Nothing about real tablets, real data or any client. The sealed lab is a program.
- Not a fully blind test (the permanent caveat). The engine's design and the development lab were produced together, and the sealed lab's shape was adjusted twice by someone aware of Stage 3's findings.
- It does not resolve any of the ten limitations carried forward in the Stage 4 summary; a good result would not make the false-alarm rate, the unexplained late rise in not-good trials or the untested reshaping shifts go away.
- It does not say the cost of governance (the gap to the ungoverned engine) is worth paying; that is a judgement for you, informed by the numbers.
- It is a single run of 40 campaigns on one lab: it cannot show how much the result depends on the lab.

## 8. Decisions I need from you before anything is built

Each has a recommendation. If you write "approved as recommended", all of the recommendations apply.

- **D1. Arms.** Adopted engine, ungoverned engine, random recipes (recommended), or the adopted engine alone (cheaper, but then the run cannot say whether the pattern from 4-4R repeats).
- **D2. May the runner's author read the sealed lab's list of public functions and its docstrings (not its formulas)?** The runner must call the lab correctly, and that is not fully documented in the README (for example, whether the lab has scenarios with events, and the exact way to ask for a history). Recommended: **yes, as a recorded ledger entry of a new type `INTERFACE LISTED`** (not `OPENED`), made by a tool that lists function names and docstrings without running anything and without printing numeric constants; if that is not acceptable, the alternative is that you supply the interface description.
- **D3. Verdict style.** Descriptive with the three-reading table in section 4 (recommended), or a numeric pass/fail bar (which I would not recommend: the engine is already known to lose to ungoverned, and a bar chosen now would be arbitrary).
- **D4. Engine constants before the run.** The Stage 4 summary lists five provisional constants (the exploratory cap of 1 in 5, 3 bridging trials, the top-20% share, the refit interval, the candidate count) that are revisitable only "after the 4-4 comparison and before 4-5". Once 4-5 runs they are frozen for good. Recommended: **leave them as they are**: a run on the engine as adopted is the cleanest reading; if you do want to revisit rules 3 or 4, do it first on a new, pre-registered development block (12100 to 12239, say) and write the new engine into the engine lock before the run. This document does not change them.
- **D5. A crash after the first sealed call.** Void and spent (recommended), or resume from the next seed with a ledger entry (more forgiving, but it lets the code change after looking at partial output).
- **D6. The "second acceptance run in Stage 10".** The sealed lab has one block of 40 live seeds. A second run on those seeds would not be blind. Recommended: **Stage 10 does not run a second acceptance; if one is wanted, a new lab version with new seeds is written and reviewed first.**
- **D7. Who runs it.** Recommended: the run is started by you with a double-click (`run_acceptance.bat`, which would ask you to type the word `RUN` after showing the preconditions), not by me.

## 9. What would be built after your written approval, and how you would check it without reading code

| Step | What | Your check |
|---|---|---|
| 4-5a | The runner inside `acceptance/`, the ledger and fingerprint preconditions, the report template with the caveat, the refusal of a second run, the dry run on the development lab with the new block | `check_acceptance.bat`: planted failures are refused in plain words (a changed lab file, a second run, a sealed seed outside the block, a report without the caveat, a missing precondition, a crash handling case); the dry-run report is readable |
| 4-5b | Your sign-off on the dry-run report | You read it |
| 4-5c | The run itself, started by you | `runs/acceptance/` has the report; the ledger has the two entries; `check_seal.bat` still passes |

**Nothing in this document is started.** Please reply with the changes you want and, when satisfied, an explicit written approval of the design (including the answers to D1 to D7).
