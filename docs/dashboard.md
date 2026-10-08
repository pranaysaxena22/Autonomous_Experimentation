# The dashboard

**Simulation with illustrative values.** Every page of the dashboard says so.

## How to run it
Double-click `run.bat`. If the run record does not exist yet it is built first (about two minutes);
after that the dashboard opens in your browser. It runs entirely on this computer and needs no internet.
To rebuild the record after changing `config\settings.yaml`, double-click `build_demo.bat`.

## The rule: the dashboard only reads
The dashboard reads one file, `runs\demo\record.json` (the run record), and displays it. It imports no
decision-engine, virtual-lab, simulator, scoring or settings code; only the code that reads the run record and
the shared data shapes. Everything it shows at a given moment (each station's status, who is in the lab, which
phase is active, whether a result is known yet, the overnight summaries, the comparison figures and the
plain-language notes) was worked out in advance and is stored in the record.

An automated check (`check_stage5.bat`) reads the dashboard's source and fails if it finds arithmetic, sorting,
min/max/sum, list filtering, calculation libraries or web addresses.

### The single exception
The Throughput page divides the autonomous trials per week (from the run record) by the manual baseline (a number
the user can edit on that page; its default comes from the run record). That one division, in
`cellpoc/dashboard/throughput.py`, produces the "x times manual" figure. It is the only calculation the dashboard
performs, and the check allows exactly one division in exactly that file.

## The pages
1. **The run** - a time slider with Previous event and Next event buttons. At the chosen moment: each station's
   status, whether anyone is in the lab, the current trial's recipe and why-text, which of Sense / Reason / Act /
   Adapt is active (shown in that order, a loop that repeats every trial), and the result once it is known (never before).
2. **Timeline** - every trial across the run, night and weekend shading, faults and skips marked. The
   Sense / Reason / Act / Adapt-over-time view is open by default; the station-by-station view is collapsed.
3. **Overnight handovers** - the ready-made summaries of what happened while nobody was in the lab, and the event log.
4. **Does learning help?** - the multi-campaign comparison (with or without the scripted faults) and the difficulty
   table. Every percentage-point gap names the baseline it is measured against (the better of the other two strategies at that difficulty).
5. **Throughput** - autonomous against a manual baseline you can edit.
6. **What this shows** - what the simulation shows and does not show (the same text as the scenario page's Limitations).

## Look and fonts
Deloitte green (#86BC25) and Open Sans with an Arial fallback. The Open Sans font file is bundled in `static\`
(SIL Open Font License, licence text alongside), so it appears even with no internet.
