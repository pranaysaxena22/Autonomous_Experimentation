# Demo video script: three minutes, problem to solution

**Illustrative.** This is a working prototype, not a full solution: the cell is a simulation with made-up values, and no real hardware is involved. Say that once, early, and let the screen say it again.

**The one idea to land:** *Developing a tablet recipe is slow because people are the bottleneck. A small robotic lab station, a "cell", can run the experiments by itself, day and night, and choose each next recipe from what it has measured.*

**What a "cell" is, in one line:** one compact robotic lab station (an arm and a few instruments: a balance, a press, a hardness gauge, a dissolution test) in a single enclosed space, like a bench-scale automated lab, not a whole facility.

## The scenes

| Time | On screen | Say |
|---|---|---|
| 0:00 to 0:25 | **Overview**, the headline and the three cards | "Developing a tablet recipe is slow and manual. A scientist makes and tests a few batches a week, only in working hours, and picks each next recipe by judgement. Labs sit empty at night and at weekends, and good recipes are found late." |
| 0:25 to 0:55 | **Overview**, the loop (Sense, Reason, Act, Adapt) | "Our idea: a small robotic lab station, a cell. It reads its instruments, reasons about what to try next, makes and tests the tablets itself, and recovers from problems. People come in to a plain-language handover instead of a pile of raw data." |
| 0:55 to 2:00 | **Live run**: Start the live view, Start the run, speed 600x | "This is the cell working, as a simulation. The arm picks the vial, scans it, the ingredients are weighed and poured, the tablet is pressed and tested. Results appear when their tests finish. Here a bottle jams: the cell clears it, retries, and carries on. Nobody touched anything." |
| 2:00 to 2:40 | **Results at a glance**: the four cards, then the learning chart | "In this run the cell did 4.5 times the experiments a person would in the same week, and 83% of the run needed nobody in the lab. It found its first good recipe in 16 hours. The first six recipes were spread out and one was good; once the engine took over, almost all were. The manual figure is an assumption we would replace with yours." |
| 2:40 to 3:00 | **Overview**, the "what is real and what is not" row | "This is a prototype: the cell is simulated. Next: connect a real arm and instruments, and run it on a real study's data." |

## Before you record

- Double-click `run_app.bat` and press Enter. Wait for the Overview.
- Do one dry run of the Live run so it is loaded, then press Restart before recording.
- Record at 1080p. Keep the cursor still while you talk. Cut anything longer than three minutes: the jam and the results are the two moments that matter.

## If you are asked

- **"Is this real?"** It is a simulation with made-up values. The software (setup, decision engine, planner, handover) is real and tested; the hardware is not built.
- **"Why a cell and not a facility?"** A cell is the smallest unit that closes the loop: make, test, learn, repeat. A facility is many of them.