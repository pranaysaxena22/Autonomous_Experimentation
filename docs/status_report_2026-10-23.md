# Status report: the autonomous formulation experiment cell (23 October 2026)

**Everything here is a prototype with made-up (illustrative) values. Nothing has been tried on real hardware or real tablets.**

## In one paragraph

A simulated robotic lab station ("cell") now makes and tests tablet formulations by itself, chooses each next recipe from its own results, recovers from faults, and hands over in plain words. It is shown in one app with a live view drawn by a physics model (MuJoCo), a charts page for a client, and, new, a **computer-vision** part: a **trained neural network** that reads a picture and says which solution is in a vessel and how full it is, and that the cell uses in the live run to check each ingredient bottle the arm picks up. What is not there: a real arm, real instruments, real data, and a vision model proven on a real camera.

## What the use case does today

| Part | State |
|---|---|
| Setup, planner, executor, decision engine, handover, reports | Built and tested (simulation) |
| One app (Overview, Vision, Results, Setup, The run, Live run, 3D replay, Physics, Data and model, Reports, About) | Built; start with `run_app.bat` |
| Live run drawn by MuJoCo (arm, vials, bottles, powder, jam and recovery) | Built |
| Barcode scanner and balance drivers | Built and tested against pretend devices only |
| Vision: reads solution (colour), level, position for the arm, and whether it can be reached | Built, two readers: colour rules and a trained model |
| **The cell's camera check of each ingredient bottle in the live run** | **New: shows the photograph, what the model read, and right bottle / wrong bottle** |
| Real arm, real camera, real instruments | **Not built** |

## The trained vision model (new, trained overnight on this computer)

- **Data:** the public LabPics photographs (2,187 real photographs of liquids in vessels, hand-outlined, MIT licence), plus 500 drawn bench scenes with exact labels.
- **Model:** a small segmentation network (MobileNetV3) that labels each pixel as background, vessel or contents; level = contents height over vessel height; solution = colour of the contents; position from four printed markers.
- **Training:** 12 passes, 54 minutes, processor only.
- **Scores on pictures it never saw** (overlap with the hand-drawn outline, 1.0 perfect): real photographs vessel 0.70, contents 0.71; drawn scenes 0.54 and 0.54. On drawn scenes its level reading is off by 3.7 points on average (97% within 10 points).
- **What it does well:** finds every vessel in the sample scenes, names the solution right, reads all five ingredient bottles, and reads the example test tube (a pale liquid the colour rules were unsure of) with high confidence.
- **What it does not:** misses very small amounts (below about 15%); reads a full vessel a few points low; has not seen your camera or glassware.
- **Honest summary:** a respectable first trained model for its size, good enough to demonstrate the idea. It needs real photographs from your own setup to be trusted, and probably a longer, larger training.

## What you will see in the live run

When the arm picks up an ingredient bottle, a **Vision check** card appears under the picture: the photograph (drawn, because the simulation has no camera), "the camera read: blue solution, 59% full", and **RIGHT BOTTLE** (or WRONG BOTTLE) against what the plan expected (drug blue, filler yellow, binder green, disintegrant orange, lubricant purple).

## Checks (all passing when last run)

Vision 40, live run 76, unified app 72, physics 41, client story 26, hardening 37.

## Blockers and decisions for your lead

1. **No hardware.** The lead said the main thing is moving the arm and understanding the item with computer vision. The vision half is now real software with a trained model; moving a real arm from what the camera sees needs an arm (even a small desktop one), a camera, and a calibration step.
2. **No real photographs.** The model's real-world performance on our own bench is unknown until we photograph real coloured liquids in real vials. Quickest test: print the four markers, use a webcam, open the Vision page, choose Camera.
3. **Scope decision.** The simulated lab models dissolution and hardness only, with five fixed ingredients; more needs new models or real data.
4. **Manual-comparison numbers are assumptions** (9 trials a week by hand): replace them with the client's.

## Suggested next steps

1. Photograph real coloured vials and test the Vision page (30 minutes); add the photographs to `data/vision_samples`.
2. Record the three-minute demo video from `docs/guides/demo_video_script.md`, now including the Vision check in the live run.
3. Decide with your lead on the arm and camera for a physical prototype.
