# Client demo script for the autonomous formulation cell

**Illustrative. Say this first and let the banners say it again:** everything you will show is a simulation with made-up values. There is no real robot, and nothing says anything about real tablets or about this client. Everything runs on this laptop and needs no internet.

## Before the client arrives (5 minutes)

- Double-click `run_app.bat` and press Enter (option 1). The first time it also draws the MuJoCo view, which takes about two minutes; after that it starts in seconds. Your browser opens the app at http://localhost:8510.
- Make the browser full screen. Click through **Overview**, **Results at a glance** and **Physics (MuJoCo)** once so everything has loaded.
- Optional: double-click `run_app.bat`, type **3**, to have the loop-connected version at http://localhost:8511 ready too.

## The demo (about 15 minutes)

| # | Minutes | Open | Say | Show |
|---|---|---|---|---|
| 1 | 2 | **Overview** | "Developing a tablet recipe is slow: a few batches a week, in working hours, each next recipe picked by judgement. This is an autonomous cell that runs trials by itself, day and night, chooses each next recipe from the data, and hands over in plain words." | The headline and the four cards. Then the loop: sense, reason, act, adapt. |
| 2 | 2 | **Vision** | "The cell also reads what is in front of it. A camera sees the bench; it tells which solution is in each vial by colour, how full each is, where each stands for the arm, and whether the arm can reach it." | Sample scene, then Camera with coloured liquids in clear vials. |
| 3 | 4 | **Results at a glance** | Go chart by chart, below. | The page, top to bottom. |
| 4 | 3 | **3D replay**, then **Physics (MuJoCo)** | "Here is the cell doing the work, including a fault. A binder bottle jams, the cell shakes it clear, puts it back, waits, retries. And here the same plan is played by an arm in a physics model, which also checks every station is reachable without collisions." | Replay: press Play, click trial 8. Physics: the animated pictures, then the reach table. |
| 5 | 2 | **Live run** | "This is it happening as it runs, drawn by the physics model: the arm, the vials and bottles, the powder, and the clock, with results appearing when their tests finish." | Press Start the live view, then Start the run, speed 600x or 1800x. |
| 6 | 2 | **Setup** | "The study is described in ten plain screens. Change a target or the run length and the whole run changes." | Pick Example 1, load it, click two screens, show a mistake beside a field. |
| 7 | 1 | **Reports** | "Everything can be taken away as a labelled report." | Report as PDF. |
| 8 | 1 | Say it | "This is a simulation. Next steps are real instruments, real data and a real arm." | Nothing on screen needed. |

### The Results page, chart by chart

1. **The four cards.** "In this run the cell did 4.5 times the experiments a person would in the same week, 83% of the run needed nobody in the lab, the first recipe that met the requirements came after 16 hours, and 24 of the 29 recipes with a result met them." Say: "The manual figure is an assumption. We want to replace it with your real number."
2. **More experiments in the same time.** "Day and night, rather than working hours only."
3. **It learns where the good recipes are.** "The first six recipes were placed evenly across the allowed ranges: one of them met the requirements. Once the engine took over, 23 of 23 recipes with a result did. The dotted line is the requirement."
4. **It works while nobody is there.** "Blue is people in the lab; the bars are the cell running. Most of the run is the cell on its own."
5. **Where the good recipes are.** "Each dot is a recipe; green met the requirements. The cell concentrated where recipes work instead of spending trials elsewhere."
6. **When something goes wrong.** "A jam on trial 8 was recovered by the cell. A second jam could not be recovered, so the recipe was skipped, an alert was queued for the first person in, and the handover says so in plain words."

## What is real and what is not (say it before they ask)

- It is a **simulation** with made-up values. There is no real robot and no real client data.
- The decision engine, the setup rules, the planner and executor, the dashboard and the reports are real software and are tested.
- The barcode scanner and balance drivers are built and tested against pretend devices, and a physics model checks the arm's reach. None of it has touched real hardware.
- The manual comparison is an assumption (nine trials a week, from the run's settings).

## Questions a client is likely to ask

- **"Would this work on our formulations?"** The setup describes ingredients, targets and the calendar, so a different study can be described and simulated. The simulated lab models dissolution and hardness only today; other measured properties need a model of how recipes produce them, or real data.
- **"Is the robot real?"** No. The arm is a generic one from the layout file; the plan is to connect a real arm and instruments through the same interface.
- **"What happens when something breaks?"** The cell recovers where it can, skips what it cannot save, and leaves an alert for the first person in. Nothing is hidden: it is all in the handover.
- **"Can we see our numbers in it?"** Yes: change the manual baseline, targets and run length in the setup and the whole run and every chart change.
- **"How long to a real pilot?"** Do not give a date. Say it depends on the hardware chosen and on getting real study data.
