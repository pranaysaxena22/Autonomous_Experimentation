# Unified app, Stage D (polish and one launcher): plan for the project owner's review (no code written)

**Status (2026-10-14): a proposal. Nothing here is built. Illustrative: everything in the app is a simulation with made-up values.**
Stage D closes the open items logged at the Stage A, B and C reviews and finishes the app as one thing you can demo. It is the last stage of the unified app. As before: checks, screenshots, then stop for your review.

## 1. What Stage D does

| # | Item | What changes for you | Existing files edited |
|---|---|---|---|
| D1 | **Nested 3D replay header** (logged for Stage D) | On the 3D replay page the replay's own dark title band is gone; the app's frame is the only header. The green "ILLUSTRATIVE replay. The arm and tools are generic stand-ins..." bar stays (it carries the stand-in caveat). The empty dark space below the replay is trimmed. The replay opened on its own (and on the old dashboards) is unchanged. | `dashboard/platform_replay.py`: `render(record, path, embedded=False)`; with `embedded=True` it adds one style rule that hides the band and sets a shorter frame height. The default output is byte-identical. |
| D2 | **Nested live header** and **live frame height** (logged) | Same for the live view in its frame: its dark band is hidden when it is shown inside the app (the live page is told with `?embedded=1` in its address, which only changes how it looks and cannot start or change anything); its green illustrative bar stays; the frame height is set to the live page's real height. | `live/live_template.html` and `live/live_part3.js` (hide the band when `?embedded=1`); `live_supervisor` (the constant address gains `?embedded=1`; no new command); `shell/live_host.py` (frame height). |
| D3 | **Setup page: the two buttons that open separate windows** | After "Save and run it" the embedded Setup page no longer offers "Open the dashboard on this run" and "Watch this setup run live" (they start unmanaged windows on 8506 and 8504, outside this app). Instead: a link to the **Live run** page with the plain instruction "choose your saved setup in the list" (the live view's chooser already lists saved setups), and one sentence on how to see the run in the other pages (double-click `run_app.bat` after dragging the saved setup file onto it). The stand-alone setup app (8502) keeps both buttons exactly as they are. | `setup_app/run_this.py` and `setup_app/app.py` (`embedded()` marks the session; `show_result` shows links instead of the buttons when it is set). |
| D4 | **One launcher** | Double-clicking `run_app.bat` with nothing after it shows a short menu (1: the platform run, 2: the loop connected, 3: both, each in its own window); `run_app.bat connected` and the existing command forms keep working. | `run_app.bat` only. |
| D5 | **Docs and start page match the app** | `docs/demo_start.html` (the page you opened, which still points at the old separate apps) is rewritten around the one app at 8510 and 8511; `docs/guides/demo_script.md` and `system_explained.md` get the unified-app demo path (menu order, what to press on Setup and Live run); the README's launcher section is shortened to "start here". | docs only |
| D6 | **Final proof** | One complete run of `check_all.bat` (every check in one table: it takes a long time and has not been run as a whole since before the unified app), a hash comparison of every `.py` file against the Stage C commit listing exactly the files above, and a screenshot of every page of both apps. | none |

## 2. Charts: recommendation is NOT to change the chart function

The dashboard's chart function draws for a light page (dark text, and some series coloured Dark Gray, which would vanish on a dark panel). Making charts truly dark means changing it and every chart's series colours (six chart pages, the Stage 5 colour rules, the Stage 8 words fingerprint) for a cosmetic gain. **Recommended: keep the charts on white cards**, which read well and are in the brand palette, and polish only with style rules in the app's own sheet (a rounder card, a thin edge, a small caption "chart"). **No change to `dashboard/style.py`'s chart function.** If you want dark charts anyway, say so and I will bring a separate proposal with the colour changes listed.

## 3. How each item is proved (all new lines go into `check_app.bat`, which stays the one check for the app)

- **D1/D2 look:** in real Chrome, a screenshot of the replay page and of the live page in the app: the band's region contains the page's own content colours and none of the band's dark colour; plus the page texts: the embedded replay HTML carries the hide rule and the default call does not (byte comparison with the Stage C output); the live page without `?embedded=1` is byte-identical to now.
- **D2 safety:** `?embedded=1` changes only the look: a planted test loads the live page with it and with `autostart` on an ordinary server and shows nothing starts; the control protection tests still pass unchanged.
- **D3:** the stand-alone setup app's fingerprints (the 11 recorded before Stage B) and `setup_run_check` still pass unchanged (the buttons are still there in the stand-alone app); in the embedded app, after a real "Save and run it", the two process-starting buttons are absent, the Live run link is present, and nothing was started (no new listener on 8504 or 8506).
- **D4:** the launcher's menu choices are read from the real file; `launchers_check` (which runs `run_app.bat` for real in both variants and reads the listening addresses) still passes, and a new line runs the menu choices with scripted input and confirms each starts only localhost listeners.
- **D5:** a check reads `demo_start.html` and the guides and fails if they name a port that is not 8510, 8511 or a documented standalone one, or leave out the menu pages.
- **D6:** `check_all` shows every row ALL GOOD.

## 4. Not changing (so you can hold me to it)

The guard's entries (nothing new is needed), the supervisor's command allow-list, the control protection, the job object, the old dashboards' behaviour and their doubled illustrative banner (the Stage 5 check requires it; the unified app shows the sentence once), the engine, the models, the simulator, `dashboard/style.py`'s chart function.

## 5. What I need from you

1. Approve D1 to D6 as above, including the small edits to the five existing files named in the table.
2. Confirm the chart decision (section 2): keep the white cards.
3. Anything you want in or out (for example, skip the full `check_all` if you would rather not wait for it).
