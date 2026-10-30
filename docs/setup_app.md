# The setup app

> Everything it shows is **illustrative**. It validates, saves and previews a study setup; it calculates no results.

## Start it

Double-click `run.bat` and type **2** (or **3** to open the dashboard too), then open http://localhost:8502 if the browser does not open. `run.bat setup` starts it directly. If it says the port is already in use, it is already running in another black window: close that one or just use it.
Everything stays on this computer; nothing is fetched from the internet.

## What it does

- **Start blank** or **Load example** (or open a setup you saved before), in the panel on the left.
- Ten screens: Project, Ingredients, Process and context, Targets, Equipment, Calendar, Faults, Baseline and engine, Data, Review and save.
  The left panel shows how many screens have no errors or warnings, and each screen's own count of errors and warnings, in words.
- Every problem appears as text with a label (**Error**, **Warning** or **Note**), directly under the field it belongs to, and again
  on the Review screen, grouped by screen. The wording is listed in `docs/setup_messages.md`.
- **Save** is switched off while any error remains. Warnings do not stop you. Saved files go only into the `setups/` folder
  (never committed to git). Each records when it was saved, the program version and a fingerprint of its content, and no names.
- The Review screen also has a **preview** of the settings the proof of concept would use. It is shown on the page only. It never
  replaces `config/settings.yaml`.
- **Save and run it** (Review screen, from Stage 11): saves the setup and simulates a run of the saved file in a few seconds (a platform run: plan, executor, stand-in lab, the calendar and faults you set), then offers **Open the dashboard on this run** (http://localhost:8506) and **Watch this setup run live** (http://localhost:8504). It is switched off, with the reason in words, while the setup has errors or cannot be simulated yet (the proof of concept needs an 'at least' dissolution target and a 'between' hardness target, and its five ingredients). The app itself still calculates nothing: it starts the platform's own programs and shows what they print. The run goes in uns/setup_run/ (generated, not in git). Checked by `check_setup_run.bat`.
- Accent colour, font and the "illustrative" banner come from `config/settings.yaml`. The bundled Open Sans font is used; nothing
  is loaded from the web.

Web addresses that open a particular place (handy for bookmarks): `?start=example`, `?start=blank`, `?open=my-study`, `?screen=3`.

## What the automated test cannot check

The test (part of `check_platform1.bat`) uses Streamlit's own test harness. It can click, type, read the messages and look at what was
written to disk. It **cannot see the page**, so it cannot tell you about:

- colours, contrast and whether green is used sensibly; whether the banner looks like a banner;
- whether the font shown is really Open Sans (and not Arial);
- spacing, alignment, text cut off or overlapping, very long messages;
- how it looks in a small or very wide window;
- whether it *feels* clear to someone who has never seen it.

## By-eye checklist (about five minutes)

1. Double-click `run.bat`, type **2**. Click **Load example**. The green banner "Simulation with illustrative values" is at the top.
2. Click through all ten screens in the left list. Each shows the banner, "Screen n of 10", and a count under its name.
3. Equipment shows **one warning** (spare reach 0.080 m). The label **Warning** is written in words, not just coloured.
4. On Ingredients, change Drug's **Lowest value** to 40. A red-edged box starting **Error:** appears right under that field, the left list says
   "1 error", and Review lists it again under Ingredients.
5. On Review, **Save setup** is greyed out and the page says why. Put the value back to 10: Save becomes available.
6. Press Save (name it `try-1`). It says it saved into `setups/`. Open the preview: it starts with "PREVIEW ONLY".
7. Click **Start blank**: every screen should show what is still to do; none should show a red technical error box.
8. Nothing looks cut off, overlapped or unreadable (check the long Data screen and the Review lists).

To get pictures of every screen (example and a setup with mistakes) without clicking, run
`.venv\Scripts\python.exe tools\take_setup_screenshots.py`. They are saved in `docs/screenshots/` (not committed). It uses Google Chrome in
headless mode; if Chrome is missing or blocked, the tool says so.
