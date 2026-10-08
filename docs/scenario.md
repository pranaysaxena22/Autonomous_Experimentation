<!-- Generated from config/settings.yaml by checks/stage1_check.py. Edit the settings, not this page. -->
# Scenario: autonomous tablet formulation cell

> **Simulation with illustrative values.** All values are illustrative placeholders, to be replaced by a client's real design space.

## What this is
A simulated cell that designs, makes and tests tablet formulations without human help, over a
multi-day run. There is no physical robot: the cell and the lab are both simulated. The cell
decides which recipe to try next from the results it has already seen, and learns as it goes.

## The recipe space
Five ingredients are varied, each as a percentage of the tablet:

| Ingredient | Lowest | Highest |
|---|---|---|
| Drug | 10% | 30% |
| Filler | 40% | 70% |
| Binder | 2% | 6% |
| Disintegrant | 1% | 8% |
| Lubricant | 0.25% | 2% |

## What "good" means
A tablet is good when **both** hold:
- Dissolution at 30 min: at least **85%**
- Hardness: between **6** and **10 kP**

## What happens to each trial
Every trial passes through these steps, one after another:

| # | Step | Duration |
|---|---|---|
| 1 | Dispense | 30 min |
| 2 | Blend | 45 min |
| 3 | Press | 30 min |
| 4 | Test | 75 min |
| 5 | Clean | 60 min |

One trial therefore takes **4 hours** from start to finish.

## The run
- Starts **Friday 09 October 2026, 18:00** and lasts **120 hours**, ending Wednesday 14 October 2026, 18:00.
- People are in the lab only on **Monday and Tuesday, 08:00-18:00**.
- That leaves the cell **unattended for 100 of the 120 hours** of the run.
- Running one trial at a time, the cell completes 30 trials in the run.

## Faults that happen on purpose
- **Trial 8** fails at the dispense step (binder dispenser clog). The cell purges for 60 minutes, retries, and carries on.
- **Trial 19** fails at the dispense step (binder dispenser clog). The cell purges for 60 minutes and retries, but the retry also fails, so that candidate is skipped and an alert is logged.

## The headline comparison
- **Adaptive vs fixed list:** 40 repeated campaigns of 30 trials each, to show the cell's learning beats a pre-written list of experiments.
- **Trials per week vs manual work:** compared against a manual baseline of **9 trials per week** (editable in the settings).

## The five parts, kept apart
1. **Settings file** - every number above, in one place.
2. **Virtual lab** - plays the role of reality. It holds the hidden true behaviour of the tablet and returns noisy measurements.
3. **Cell simulator** - runs the clock, the steps, the faults and the event log.
4. **Decision engine** - chooses the next recipe. It sees only measurements, never the hidden truth.
5. **Dashboard** - displays what happened. It does no calculation of its own.

## Limitations
- **Ingredients are not forced to sum to 100%.** Each of the five percentages is varied independently within its own range, so a recipe's ingredients can add up to more or less than 100%. A real design space would normally fix one ingredient (often the filler) as the remainder.
- **The tablet behaviour is a made-up placeholder.** The virtual lab's hidden truth is a smooth illustrative model, not real pharmaceutical data.
- **The hidden truth is smooth,** which favours a strategy that learns a model of it. Real formulation data would be rougher, so the size of the adaptive strategy's lead here is illustrative, not a prediction.
- **One trial at a time.** The cell never works on two trials at once.
- **Measurement noise is the only random effect** in the lab. There is no instrument drift, no reagent run-out and no recalibration.

## Future extensions
- **Overlapping trials:** let a new trial start dispensing while the previous one is being tested, to raise the number of trials per run.
- Instrument drift, reagent run-outs and recalibration.
- Stop and resume, and runs longer than 120 hours.
- Running the simulation in a separate process so the dashboard can watch it live.
