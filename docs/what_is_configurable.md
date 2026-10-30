# What comes from the setup, and what is fixed in the code

**Illustrative.** This is the answer to "is everything hardcoded?", written after reading the code and trying it (2026-10-16). Short version: **the numbers you would want to change are in the setup and layout files, not in the code.** What is fixed is *which kinds of thing the simulation can model*.

## 1. Read from the setup file or the layout file (change the file, the run changes)

| What | Where | Proof |
|---|---|---|
| Every target number: dissolution at least X %, hardness between A and B kP, friability at most Y %, which targets are required | setup, Targets | Changing dissolution from 70 to 95 turns 25 good trials of 30 into 0; changing the hardness band from 6-10 to 8-9 turns 24 into 11 (same recipes, different verdicts) |
| Ingredient names, ranges, recipe rules, batch size, process settings | setup | setup rules and the planner read them |
| Step times, the Reason/Adapt split, the opening hours, run length, trial count | setup, Equipment and Calendar | the planner and the calendar read them |
| Scripted and random faults (which trial, which action, what cause, whether a retry works) | setup, Faults | the executor reads them |
| Instrument scatter (noise) | setup, virtual lab | the virtual lab reads it |
| Where everything is, the arm's link lengths, reach, safe height | layout | the 3D replay, the setup rules and the physics model all read it |
| **How long the arm takes to pick, place and scan (new)** | layout, `robot.action_seconds` | was 60 s each in the code; now the layout's value, with 60 s as the default so every old run is identical (fingerprints of all three examples are unchanged) |
| Barcode label format, number of rescans, turn time | layout, `instruments.barcode` | added 2026-10-14 |

## 2. Fixed in the code, on purpose (and why)

| What | Why it is fixed |
|---|---|
| The five stages of a trial (dispense, mix, press, test, clean) and the action types (pick, place, pour, shake, ...) | they are the vocabulary of the use case; the setup says how long each takes, not what exists |
| The simulated lab produces **dissolution and hardness only** | it is a model of how a recipe turns into those two numbers; a new measured quantity needs a new model, not a setting |
| The proof of concept's engine works on exactly the **five named ingredients** | the engine and virtual lab were built for those five |
| Where in a pour a jam strikes (28 % in), how much gets delivered before a jam (36 %) | these are the stand-in executor's model of a fault, not a study setting; a real executor does not use them |
| The 60 s minimum for a named wait; how long a pour takes for a given weight | planner rules of thumb |

## 3. What happens when the setup asks for something the simulation cannot model

- **A new optional target** (for example friability, which the layout can read but the simulated lab does not model): accepted and shown as "not used" in the preview; trials carry no reading for it.
- **A new *required* target** the simulated lab cannot produce: **found and fixed on 2026-10-16.** Before, the run went ahead and showed "No result" on most trials, with no explanation. Now the setup app says, in words, "this is a required target, but the simulated lab produces dissolution and hardness only: mark it optional or remove it".
- **A different set of ingredients**: refused in words (the proof of concept models exactly five).

## 4. If you want more targets or more ingredients

That is a separate piece of work, and it needs a decision: each new response (for example content uniformity, disintegration time, friability) needs its own simulated model in the virtual lab, and the decision engine has to be taught to optimise it. The setup, planner, executor, dashboard and replay already handle any target the setup states. The honest effort is in the virtual lab and the engine, not in the files. With real data in place of the virtual lab, the models come from the data instead.
