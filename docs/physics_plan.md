# Physics with MuJoCo: what is built, what comes next, what it cannot do

**Illustrative.** Everything here uses the layout file's made-up numbers. Nothing has been tried on a real arm.

## 1. What MuJoCo is, in plain words

MuJoCo is a free physics engine (now maintained by Google DeepMind) that robotics teams use to simulate arms: joints, links, gravity, contact between solid things. It is a Python package that installs with one command, has a ready-made viewer window, and works on this Windows machine with Python 3.14. PyBullet was the other candidate; it needs a C++ compiler on Windows and has no Python 3.14 package, so it was not chosen.

## 2. What is built now (step M0 and M1)

The new **physics part** (`cellpoc/physics/`):

| File | What it does |
|---|---|
| `scene.py` | Builds a MuJoCo scene from the **layout file** only: the table, the column, the three-segment arm (turn, shoulder, elbow, wrist, tool hanging down) with the layout's link lengths and shoulder height, a pad under every station, bottle slot and tool holder at the layout's angle, radius and height. Nothing is typed in for the layout: change the layout and the scene changes. |
| `reach.py` | An inverse-kinematics solver (it works out the joint angles that put the tool tip at a target) using MuJoCo's own Jacobian, then measures the spare reach on the MuJoCo model, and lists anything the arm touches. |
| `sanity.py` | Three trust tests: a dropped ball falls the way gravity says; the same run twice gives identical numbers; a vial dropped on a pad stays there. |
| `export.py` | Writes the scene as a file MuJoCo's own viewer opens (`view_physics.bat`). |

`check_physics.bat` proves (34 checks): the scene is the layout's; gravity is right to within 1 per cent; repeatable; all 28 targets (14 places at working and safe height) are reached to under half a millimetre with the tool pointing down and nothing touched; the spare reach MuJoCo measures **equals the setup rules' formula at every target** (the tightest is about 0.08 m); and the test can fail (a slot at 1.5 m is not reached, a shorter arm reaches 18 of 28, a longer one gains exactly what was added, a tool through the table is a collision, a broken layout is refused in words).

**What this means:** the reach rule the setup app applies is now confirmed by an independent physics model, and a setup that is "reachable" really has joint angles that get there without hitting the table.

## 2b. Added 2026-10-16: the robot working in MuJoCo (a separate view)

`play_physics.bat` plays a trial of a finished run with the MuJoCo arm (`cellpoc/physics/motion.py`, `play.py`, `render.py`). It reads the run's saved timeline and the layout and, for each action, lifts to the safe height, glides over the place along an arc, goes down to the working height and does the action there: grasp (the object then hangs from the tool tip), release, tilt a bottle to pour, shake at the home pose, press, stir. MuJoCo's solver puts the arm in the right pose at every frame (20 per second) and the arm is checked against the table and pads at each one. The jam shows as a red caption with its cause and the recovery steps carry a RECOVERY tag.

- **Playback time is not run time:** each move and action is shown at about a second; a long wait is shown as a short pause (the caption carries the run's own simulated clock).
- **Proved** in `check_physics.bat` (41 checks): every action of a clean trial and a trial with a jam is played, every object ends where the timeline puts it, nothing is touched, motion is smooth, the fault and recovery show, the same trial gives the same frames, the run's 30 timelines are byte for byte unchanged, and a playback that cannot be made is refused in words.
- **What this is not:** it is not the executor. The run's times, results and trial counts still come from the stand-in executor; the playback adds no physics to them (steps M3/M5 below stay unbuilt).

## 2c. Added 2026-10-16: it is in the app, and looks like the replay

The scene is drawn with the replay's instruments, beaker, bottles and arm (see docs/decisions.md), and the app's **Physics (MuJoCo)** page shows two animated trials and the reach and collision checks. It is drawn by `cellpoc/physics/view.py` (run_app.bat does it; `make_physics_view.bat` for another run).

## 3. Nothing else has changed

No other part uses the physics part. Runs, timings, trial counts, the dashboard and every existing check are exactly as before (the check scans the project to confirm nothing imports it).

## 4. The steps still to come (not built, each needs approval)

| Step | What | Why it is separate |
|---|---|---|
| M2 | **Motion between places, as a view: BUILT (section 2b).** Using the move *times* MuJoCo works out in the run itself is not built: it would differ from the planner's pick/place times and change timings and trial counts, so it must be a decision. | |
| M3 | **A physics executor** next to the stand-in executor (a choice in the setup), so a run's arm moves come from MuJoCo. | Same reason; and it needs M2. |
| M4 | **Show the MuJoCo motion inside the unified app's pages** (today it is a separate window or a GIF). | Needs a run-record addition or a new page; separately approved. |
| M5 | **A published arm model** (for example a UR5e or Franka from MuJoCo's Menagerie) instead of the generic arm. | The layout assumes a 1.44 m reach, the UR5e reaches 0.85 m, so the layout would change. Better done once the real arm is chosen. |

## 5. What MuJoCo does not do (so nobody is surprised)

- It does **not** simulate powder, liquids, a binder jam, tablet compaction, dissolution or hardness. Those stay with the virtual lab and the executor's fault model. Powder dispensing would need a different tool and real data.
- It is **not** a model of a real arm, a real controller or real timing; it is the layout's generic arm.
- A pass here means "the layout is geometrically consistent and reachable", not "it works on hardware".

## 6. How to look at it

- `check_physics.bat`: the proof (about a minute).
- `view_physics.bat`: opens MuJoCo's own viewer on the cell (a window on this computer only). Drag the joint sliders in the right panel to move the arm.
