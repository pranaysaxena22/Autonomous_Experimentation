# Cell POC

A simulated autonomous formulation cell (tablet recipes), with a Streamlit dashboard.
**Simulation with illustrative values** - nothing here is real client data.


All tunable numbers are in `config\settings.yaml`. The plain-English description of the scenario is
`docs\scenario.md` (generated from the settings by the checks).

## Check a stage

Each stage has a health check you can double-click. It prints a PASS/FAIL list in plain words.

| Stage | Double-click | What it covers | Time |
|---|---|---|---|
| 1 | `check_stage1.bat` | settings, scenario page, virtual lab | seconds |
| 2 | `check_stage2.bat` | the cell simulator on a fixed list | seconds |
| 3 | `check_stage3.bat` | adaptive engine, 40-campaign comparison, difficulty table | a few minutes |
| 4 | `check_stage4.bat` | closed-loop run with scripted faults, alerts, overnight summaries | under a minute |
| 5 | `check_stage5.bat` | the dashboard | a few minutes |

Run them in order the first time: Stage 4 also confirms every generated chart page works with no internet.
Outputs are written under `runs\` (not saved in git).


### The day before (once)
1. Double-click `build_demo.bat` and wait for "Done" (about a minute or two). This builds the run record the dashboard shows.
2. Double-click `run.bat`. Check the dashboard opens (details below), then close it (see "Closing down").
3. **Rehearse offline:** turn off Wi-Fi / unplug the network, then repeat step 2. It should look exactly the same.
4. Optional but recommended: double-click `check_stage5.bat` (a few minutes). It should end with **ALL GOOD**.
5. Make a backup in case the app misbehaves: the files `runs\stage4\timeline.html`, `runs\stage3\comparison.html` and
   `docs\scenario.md` open without the app (double-click the two .html files; they work offline). They exist after
   `check_stage3.bat` and `check_stage4.bat` have been run once. Copy them to a USB stick.
6. On the laptop: switch off sleep/screen lock, close other programs, and set the browser to full screen (F11) at 100% zoom.

### A suggested walk-through (about 10 minutes)
1. **The run.** Click **Next event** a few times to show the cell working through Dispense, Blend, Press, Test and Clean, with nobody in the lab. Point out the four boxes (Sense, Reason, Act, Adapt: a loop that repeats every trial) and the recipe with its "why this recipe".
2. Drag the slider to **Sat 10 Oct 09:00**: trial 4's result appears, the first recipe to be measured good.
3. Drag to **Sat 10 Oct 22:30**: trial 8's dispenser clog. The Dispense tile turns red ("Purging after binder dispenser clog"). Click Next event until **Sun 11 Oct 00:00**: it recovers by itself.
4. Drag to **Mon 12 Oct 21:30**: trial 19's retry fails and the candidate is skipped. The alert says it is **waiting for staff, queued for Tue 13 Oct 08:00**; the cell cleans and carries on. Step to Tue 08:00 and watch the alert change to "Staff arrived".
5. **Timeline.** Every trial across the run; grey shading is nobody in the lab (darker = weekend). Faults are red/amber, alerts are triangles. The phases-over-time view is open below.
6. **Overnight handovers.** Read one summary aloud: this is what the first person in on Monday or Tuesday gets.
7. **Does learning help?** The adaptive strategy against a fixed list and random recipes over 40 campaigns, and the difficulty table: the advantage is largest when good recipes are rare and disappears when they are common.
8. **Throughput.** Autonomous against manual. Type the client's own manual figure into the box and the multiple updates.
9. **What this shows.** Finish here: it states plainly what the simulation does not show.

### Closing down
Close the browser tab. Click the black window and press **Ctrl+C** (or just close the black window). Always close it before starting `run.bat` again.

### If the app will not start
| What you see | What to do |
|---|---|
| Black window flashes and closes straight away | Open a terminal in this folder and run `.venv\Scripts\python.exe -m streamlit run app.py` to see the message. If it says the file is not found or `python` is missing, the environment is missing: follow "Rebuild the environment" below, then try again. |
| Browser does not open | Open it yourself and go to http://localhost:8501 |
| "This site can't be reached" / page never loads | The black window may have closed or still be starting. Wait 20 seconds and refresh (F5). If the black window is gone, double-click `run.bat` again. |
| "Port 8501 is already in use" in the black window | An old copy is still running. Close every black window, then try again. Or use another port: `.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502` and open http://localhost:8502 |
| Page says **"There is no run record"** or **"out of date or damaged"** | Double-click `build_demo.bat`, wait for "Done", then refresh the page (F5). This always happens after the program or the settings change. |
| Windows or antivirus asks about network access | It is only talking to itself (localhost). Choose "Private networks" / allow once. Nothing leaves the computer. |
| The page looks half-drawn or buttons do nothing | Press F5 to refresh. If that fails, close the black window and start `run.bat` again. |
| Anything else | Double-click `check_stage5.bat`: it names the part that is failing in plain words. If time is short, use the backup files from the USB stick (`runs\stage4\timeline.html`, `runs\stage3\comparison.html`, `docs\scenario.md`) and present from those. |

## Add a library

    .venv\Scripts\python.exe -m pip install <package>
    .venv\Scripts\python.exe -m pip freeze > requirements.txt

## Rebuild the environment (e.g. on a new machine)

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
