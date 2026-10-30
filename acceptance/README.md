# The sealed acceptance lab

**SYNTHETIC. It says nothing about real tablets.** This folder holds a second virtual lab, `sealed_lab.py`, whose hidden truth is structurally different from the development lab
(`cellpoc/virtual_lab/_truth.py`) and from the mock data generator (`tools/make_mock_data.py`). It exists for one purpose: at the end of a stage (the end of Stage 4, and again in Stage 10) to show
that a model or decision engine was not tuned to the lab it was developed against. A result on this lab is only worth anything if nobody could have tuned to it, so it is sealed.

## What "sealed" means, precisely

**What is locked** (byte for byte; line endings are normalised before fingerprinting so Windows and Unix copies agree):
1. `acceptance/sealed_lab.py`: the whole truth (every formula and constant), the noise, the batch and supplier effects, the targets (dissolution at least 85, hardness 6 to 10 kP, friability at most 1.0),
   the history generator, and the 40 sealed acceptance seeds (7,000,101 to 7,000,140; see "Version 2" below for why they are not 7,000,001 to 7,000,040).
2. `acceptance/README.md`: this definition.
3. `acceptance/SEAL.json`: the manifest listing the fingerprints of the files above.

**What is recorded:**
- the SHA-256 fingerprint of each of the three files, in `acceptance/SEAL.json` (for the first two) and in `docs/decisions.md` (all three);
- a git tag, `sealed-lab-v1`, on the commit that sealed it;
- `acceptance/LEDGER.md`: an append-only list of every time the lab was created, sealed, run or opened. Every acceptance run is entered there (date, purpose, and that the fingerprints were verified first).

**What is allowed after sealing:**
- reading the fingerprints, and running `check_seal.bat` (it reads bytes and never imports or runs the lab);
- running the lab ONLY through the dedicated acceptance runner (written in Stage 4, inside this folder), at the designated times, with the 40 sealed seeds, after the fingerprints have been verified,
  and recording the run in `LEDGER.md`.

**What counts as a violation (any one of these breaks the seal; the response is to write a new lab, never to repair this one):**
1. any change to a sealed file after sealing (a different fingerprint), including a "harmless" fix or a comment edit;
2. any file outside this folder that imports, opens, reads, copies from or names the lab (`sealed_lab`, or `import acceptance`): development code, tools, other checks and the engine included;
3. any run of the lab that is not an entry in the ledger as a designated acceptance run, for any reason (debugging, curiosity, "just to see");
4. any model, setting, threshold or engine choice made after looking at a result from this lab;
5. a ledger entry of type `OPENED` (someone looked inside to debug): the seal is then void and `check_seal.bat` fails until a new lab is written and sealed.

**What the seal does not do (stated so it is not over-read):** it is a process seal, not a technical lock. Anyone with access to the folder can open the file; what the seal guarantees is that
tampering is detectable (the fingerprints), that outside use is detectable (the scan in `check_seal.bat`), and that every legitimate run is on the record. Running the lab outside the runner leaves no technical
trace, so rule 3 depends on honesty and the ledger.

## How it was made (pre-seal development, recorded honestly)
- It was written on 2026-10-11, **after** Stages 3a and 3b were finished (the plan was to write it before modelling began; that timing was not kept). No model, engine or Stage 3 result ever touched it, because
  it did not exist; but it was written by the same assistant that knew the Stage 3 findings, and its design properties below were fixed before it was tested.
- Properties fixed in advance and met before sealing (none involved a model or engine): deterministic and independent of call order; every effect in a physically sensible direction; a random recipe passes
  all three targets between 3% and 12% of the time (a lab where passing is rare, as in the development lab); dissolution, hardness and friability each pass between 15% and 60%, 20% and 60%, 55% and 95%;
  in the history it can generate, some input drifts with the date by a rank correlation of at least 0.25 and the supplier explains at least 15% of some input's spread (the development mocks have 0.03 and 0.2%).
- Two rounds of adjusting shape constants (the dissolution time scale, its porosity sensitivity, a friability threshold and the campaign centres and spreads of the history) were needed to meet those properties.
  They are listed in `LEDGER.md`.

## Why a lab and not a fixed test table
A decision engine chooses its own experiments, so it must be able to ask for any recipe. A fixed table cannot answer a recipe it does not contain. The lab answers any recipe in the allowed ranges with a noisy
measurement, and can also generate a history of past experiments (observations only) in the 21-column format of the mock data, so the engine starts from data exactly as it would from a client's.
The truth and the "is this recipe really good" test are for scoring after the fact only.

## Version 2 (2026-10-12): the acceptance seeds were moved, and why
**What happened.** The first seal (version 1, tag `sealed-lab-v1`, 2026-10-11) designated the seeds 7,000,001 to 7,000,040. Before sealing, two of them were used in the property-testing rounds that led to the
two shape-constant adjustments (three runs of the same throwaway test script, always with the same two seeds): **7,000,001** generated the 3,000-experiment history (twice per run) and 2,000 measurements at one
recipe, whose aggregate statistics (date drift, how much the supplier moves the recipes, replicates per experiment, noise sizes) informed the adjustments; **7,000,002** produced one measurement, to confirm that a
different seed gives different noise. They were two deliberate, convenient choices (the first two numbers of the range), not a loop over the range and not an accident of a wider pool, and the version 1 README and
ledger did not name them. By rule 4 above ("any model, setting, threshold or engine choice made after looking at a result from it"), the project owner treated this as a violation as written.

**What changed.** Nothing but the one line of `sealed_lab.py` that designates the acceptance seeds, which now reads 7,000,101 to 7,000,140: every formula, constant, the noise, the batch and supplier effects, the
targets and the history generator are unchanged byte for byte. The new block had never been generated, run or examined in any form before this point (checked against every file in the project, every scratch
script and the whole conversation record). The manifest, the fingerprints (here and in `docs/decisions.md`), the git tag (`sealed-lab-v2`) and the ledger record the change.

**The retired seeds.** 7,000,001 to 7,000,040 are RETIRED: never to be used for acceptance. They remain only as disclosed, already-seen development reference points. `check_seal.bat` fails if the lab file's
seeds overlap them.

**Two more ledger types exist from version 2:** `VIOLATION` (something broke a rule above; it must be followed by `RESEALED`) and `RESEALED` (a new seal after a violation, with what changed). An `OPENED` entry
still voids the seal.

**What was NOT repaired.** The shape constants were still adjusted twice by someone aware of Stage 3's findings, so version 2 is blind to its seeds but it is still not a fully blind acceptance test: the permanent
caveat on every acceptance report stays exactly as written.
