# Unified app, Stage C: design note (no code written)

**Status (2026-10-14): sections 1 to 11 approved by the project owner and BUILT (step C0, then Stage C; see docs/decisions.md). Deviations from this note are listed at the end of the Stage C entry there. Illustrative: the live run is a simulation with made-up values.**
Written for the project owner, in plain language. Stage C folds the live run into the unified app. It is the first stage in which the app itself starts a long-running program, so the rules for starting, watching and stopping it are fixed here first, and the guard changes are listed for approval.

## 1. What Stage C does, and does not do

**Does:** the **Live run** menu page shows the live view (the 3D arm, the clock, results as they appear) inside the app. A **Start the live view** button starts it; a **Stop the live view** button stops it; a status line says what state it is in. The setup chooser inside the live view still lists the three examples, saved setups and the connected loop.

**Does not:** change how the simulation works. Stage C itself adds one new file to the live part and edits none; the protection of the live server's controls (section 11) is a separate, earlier step ("C0") that does edit four existing live files and, because the standalone page on 8504 uses the same server code, protects it too. The setup app's "Watch this setup run live" button keeps starting the standalone page on 8504 in its own window until Stage D reroutes it. The dashboard's chart function and the nested 3D replay header stay as logged for Stage D.

## 2. The decision: the live view runs as a separate program, not inside the app

| | Separate program (recommended) | Inside the app's own process |
|---|---|---|
| What the app must import | Almost nothing: a small supervisor that knows one fixed command | The whole live part, which reaches the lab, the engine and the connected loop |
| The guard we kept narrow | Stays narrow: the unified app still cannot reach the lab or the engine | Lost: the app could reach everything the live part does |
| Cleanup | Needs care (below), but can be made automatic and tested | Automatic, but the live view then dies and restarts with every app reload |
| Matches today | Yes: `run_live.bat` is already a separate program on its own port | No |

**Recommendation: a separate program.** It keeps Stage A's and B's promise that the unified app only shows things and hosts the setup screens.

## 3. The pieces

1. **New part `cellpoc/live_supervisor/`** (new folder): the only code that starts, watches and stops the live program. It imports **no other part of the project**. It knows only three commands (below). The shell calls it; nothing else does.
2. **New entry file `cellpoc/live/embedded_main.py`** (one new file in the existing live part; Stage C itself edits no existing file). It starts the existing `LiveServer` on a port the supervisor gives it, prints a plain "ready" line, and does **not** open a browser window (the existing `python -m cellpoc.live` does). The address it binds is not a setting: `LiveServer` binds the constant `HOST = "127.0.0.1"` and has no way to be told otherwise.
3. **A Live run page in the shell** (`shell/live_host.py`): a status line, the two buttons, and `st.iframe` pointing at `http://127.0.0.1:8514/` (a fixed, constant address built from the constant host and the supervisor's port; never from anything typed in an address bar).
4. **Port 8514** for the embedded live view, so it can run beside a standalone one on 8504.

## 4. How the app starts, watches and stops it

**Start** (only when someone presses the button; visiting the page starts nothing):
1. Refuse if one is already running (the second press does nothing new).
2. Refuse, in plain words, if port 8514 is already in use by something the app did not start. It never adopts or kills a program it did not start.
3. Create a Windows *job object* set to kill everything in it when its owner goes away, and refuse to start if that cannot be created (no unmanaged program is ever started).
4. Start the one fixed command inside the job: `python -B -m cellpoc.live.embedded_main --port 8514`. The command is a list, never a text line (no shell), and the port is a checked whole number.
5. Wait up to 60 seconds for it to start listening, then **read what the computer is really listening on for that port**. If anything other than 127.0.0.1 appears (for example `0.0.0.0` or `[::]`), the app kills the whole program tree at once, shows "refused: the live view listened on an address other than this computer's", and leaves nothing running.

**Monitor:** the status line refreshes every few seconds (a Streamlit fragment) and shows one of: *not running*, *starting*, *running on 127.0.0.1:8514, this computer only*, *stopped* (with how it ended), *refused* (above). It reads the supervisor; it works nothing out. A program that exits by itself is reported as "stopped unexpectedly (exit code N)" with its last lines of output, in words.

**Stop:** the button kills the program tree (`taskkill /PID n /T /F`, as the launcher checks already do) and then confirms the port is no longer listening. Pressing it when nothing runs does nothing and says so. A live run stopped before it finishes is not saved (as when the black window is closed today); a run that finished was already saved by the live part itself.

**Cleanup when the app goes away:** because the live program is inside the job object, Windows kills it when the app's process ends for any reason: the black window closed, Ctrl+C, a crash, the process killed. This is checked with a hard kill (below), not assumed. Browser tabs closing does not stop it (the app is shared); only Stop or the app ending does.

**Failure cases, each with a plain sentence and a test:** port in use by something else; the program exits at start; it never becomes ready in 60 seconds; a non-local listener is found; the job object cannot be created; Stop pressed twice; the app's page reloaded while the live program runs (the supervisor lives in a module-level variable, so a page reload finds the same program).

## 5. Keeping the live view on this computer only: four layers

1. **It cannot be told otherwise.** The live server binds the constant `127.0.0.1`; there is no flag, setting or address-bar value that changes it. A new static guard reads the live part's files and refuses any bind to `0.0.0.0`, `::`, an empty host, or anything but the constant `HOST`.
2. **The page only answers this computer.** The live server already refuses requests whose Host header is not `127.0.0.1`/`localhost`; unchanged.
3. **The app checks the result, every start.** The listening-address read in step 5 above runs on every start and fails closed (kills and refuses).
4. **The embed address is a constant.** The iframe address is `http://127.0.0.1:8514/`, built in the supervisor from constants.

## 6. New architecture-guard entries (for approval)

1. **New part `live_supervisor`**, allowed to import nothing from the project (an empty list), added to the no-network list (no socket, HTTP, URL or mail library; it reads the listening addresses with the operating system's `netstat`, not with a connection).
2. **`shell` may additionally import `live_supervisor`**, and only that. It still may not import `live`, `connected`, the lab, the engine or the setup rules directly; its reach becomes the Stage B reach plus `live_supervisor`, which reaches nothing. No part but `shell` may import `live_supervisor`.
3. **An allow-list for what the supervisor may start:** exactly three commands: the live program (`sys.executable -B -m cellpoc.live.embedded_main --port N`), `taskkill /PID N /T /F`, and `netstat -ano -p tcp`. A scan of the supervisor's source requires every process start to take a list (never a text line), refuses `shell=True`, `os.system`, `eval`, `exec` and any file-writing call, and refuses a first word other than the three.
4. **A bind guard on the live part:** the only address any file in `cellpoc/live/` may bind is the constant `HOST`, and `HOST` must be `127.0.0.1`.
5. **The shell's own rule is unchanged:** the shell's files still may not start a process or touch a file; they only call the supervisor and draw an iframe. The planted-violation self-tests for the shell are kept, and new ones are added for items 1 to 4.

## 7. The self-test that proves nothing it starts can end up listening on 0.0.0.0

All of these are run for real by `check_app.bat` (a Stage C section), on spare ports, and each can fail:

1. **The real thing:** the supervisor starts the real live program; the check reads what the computer is listening on (`127.0.0.1` only), asks the computer's *other* network address to connect (refused), and loads the page through 127.0.0.1 (served).
2. **A planted wrong program:** the check swaps in a small program that deliberately listens on `0.0.0.0` at the same port. **Without** the app's address check, the check first shows that this program really is reachable from the computer's other network address (so the exposure is real). **With** it, the supervisor detects the non-local listener, kills the whole tree, reports "refused", and the check confirms the port is no longer listening and nothing is left running.
3. **The static guard can fail:** planted bind lines (`("0.0.0.0", port)`, `("", port)`, `("::", port)`, a variable host) are each caught in a copy of the live part's source; the real `HOST` form is accepted.
4. **A program that starts and then changes its mind:** a planted program that first listens on 127.0.0.1 and then also opens `0.0.0.0` is caught by the supervisor's *next* status refresh (the address read is repeated while it runs, not only at start).

## 8. The other Stage C checks

- **No orphan, even on a hard kill:** the check starts the supervisor inside a throw-away Python program, kills that program with no warning (no chance to clean up), and confirms within a few seconds that the live program is gone and the port closed.
- **Stop works and is idempotent;** a second Start while running starts nothing new; a port held by a foreign program is refused and that program is left alone.
- **The Live page** draws with no error in every state; the status line matches the supervisor's real state; the illustrative sentence appears exactly once on the page (the live view inside the iframe carries its own, different "ILLUSTRATIVE live run." bar); the iframe address is the constant one and no address in the page's text or query string can change it.
- **Existing behaviour unchanged:** `check_live.bat` (the standalone live page and its 127.0.0.1 binding), the setup app's buttons, and all Stage A and B checks pass.
- Guard entries and their planted-violation self-tests (section 6).

## 9. Risks and limits, stated plainly

- **Windows only.** The job object and `taskkill`/`netstat` are Windows tools, as the rest of this project's launchers are.
- **A real gap, now to be closed (section 11):** the live page's controls (start, pause, speed, setup choice) accept a request from any web page open in the same browser, because the live server checks the Host name but not where a page came from. It was shown on the current code: a cross-site "simple" request changed a live run from *ready* to *running*. The owner asked for it to be closed in Stage C, for 8514 and for the existing 8504 page.
- **A nested header again:** the live page inside the app keeps its own dark band and green bar, so two headers stack, like the 3D replay. Proposed for the Stage D list (same fix: suppress or inherit when embedded).
- **Fixed iframe height:** the live view is tall; a fixed height with an inner scroll is used. Fitting it better is a Stage D item.
- **A run stopped part-way is not saved**, as today.
- **The other launchers are unchanged**, including the 8504 page started by the setup app, which this app does not manage.

## 10. What I need approved before any Stage C code

1. The separate-program design (section 2).
2. The new `live_supervisor` part with its empty import list, its three-command allow-list and its source scan (sections 3 and 6).
3. The one new file `cellpoc/live/embedded_main.py` (no existing live file edited) and port 8514.
4. The two new guard entries on the live part (the bind guard) and on `shell` (may import `live_supervisor`).
5. Logging "nested live header" and "live iframe height" as Stage D items.
6. ~~Whether you want the origin check in Stage C~~: **decided by the owner: yes, build it now, in Stage C, and apply it to the 8504 server too if small and contained, logged separately.** See section 11.

*Approved 2026-10-14: items 1 to 5; item 6 resolved as above.*

## 11. Protecting the live server's controls (added 2026-10-14 at the owner's request; awaiting approval)

### The gap, shown
The live server answers only requests whose Host name is this computer's (this stops a web page that tricks the browser into reaching it under another name). It does **not** check **where a request came from**. On the current code, a request that a web page on *any* site can send without permission (a plain POST with a text content type) was accepted from a made-up site (`Origin: https://evil.example`) and changed a live run from *ready* to *running* (200 answer; run status before and after shown). A request with a JSON type or a custom header is stopped by the browser's own permission step, because the server answers that step with "not implemented" (501); the plain request needs none. The controls only start, pause, change the speed, restart and pick among the known setups; nothing leaves the computer and nothing is deleted. It is still a hole: a page open in the same browser can steer the live run.

### The mechanism (simplest correct for this stack)
Three checks on **every control request** (POST to `/control`), all in the existing live server, all must pass, each with a plain refusal (403) that executes nothing:
1. **Origin must be the server's own.** The browser itself writes the `Origin` header on a POST and a web page cannot change it. The server accepts only `http://127.0.0.1:PORT` or `http://localhost:PORT` for its own port. A page from any other site, or from another local port (for example the unified app on 8510 or an attacker's page on another localhost port), is refused. A missing or `null` Origin is refused.
2. **A secret token in a custom header.** When the live server starts it makes a random token (32 random bytes, different on every start) and writes it into the page it serves; the page's own script sends it back in an `X-Live-Token` header on each control request. It is compared in constant time. A page on another origin cannot read the token (the browser forbids reading another origin's page), and cannot send a custom header without first passing the permission step the server does not grant.
3. **Host name as today** (unchanged).

Also added to every response: `Content-Security-Policy: frame-ancestors 'self' http://localhost:* http://127.0.0.1:*` (the live page may be shown in a frame only by pages on this computer, so a site cannot put the live page in a frame and trick someone into clicking Start) and `X-Content-Type-Options: nosniff`.

**Why the token lives in the page the server serves, not passed from the app.** The page and the server are the same program, so the server can make its own secret and hand it only to the page it serves. Passing a secret from the unified app (through the command line or an environment variable) would add a way for it to leak (process lists) and a second place to get wrong, and would give nothing extra: the threat being closed is a *web page in the browser*, and both the Origin and the token stop it. One mechanism then covers the embedded 8514 view and the standalone 8504 page alike, with no change to how the app starts the program.

**What it does not stop, stated plainly.** A program running on this computer as the same or another user can read the page (and so the token) and forge the Origin; the same user could also simply run anything. Nothing here is meant to stop that, and the unified app itself, like every page of this project, has no sign-in and assumes a single-user computer. The protection is against **web pages in the browser**.

### What changes (a small, separate step "C0", before any Stage C code; its own commit and log entry)
Four existing live files and one check, about forty lines in all: `server.py` (make the token, the three checks, the two headers, give the token to the page), `page.py` and `live_template.html` (a `<meta>` carrying the token), `live_part3.js` (read it and send it as `X-Live-Token` on the control request; the code copied byte for byte from the replay viewer is untouched), and `checks/live_check.py` (its legitimate control requests now send the token and the Origin a browser would; refusals added). Because `python -m cellpoc.live` (run_live.bat, 8504) and the new 8514 program build the same `LiveServer`, **one change protects both**; it is therefore the same change, not a second one, and is logged and committed on its own so it can be reviewed apart from Stage C. The standalone page keeps working when opened from a browser at `localhost:8504` or `127.0.0.1:8504`.

### Self-tests (each can fail; run for real)
In `live_check.bat`, against a real server started on a spare port, a control request is sent with each of these, and for every refused one the run's status afterwards is shown **unchanged** (the command was not executed):
1. no token, right Origin: refused;
2. a wrong token, right Origin: refused (the right token with one character changed, and an empty token);
3. the right token but no Origin, and `Origin: null`: refused;
4. the right token but `Origin: https://evil.example`: refused;
5. the right token but the Origin of another local port (for example `http://127.0.0.1:8510`): refused;
6. the right token and the server's own Origin (what the real page sends): accepted, and the command takes effect (the status changes);
7. a foreign Host name with everything else right: still refused (the existing check);
8. the token is not in `/state`, not in any refusal text, and differs between two server starts; and the plain `text/plain` request that started the run in the demonstration above now changes nothing;
9. the response to the page carries the frame-ancestors rule.

**In real Chrome, a real attack page (the end-to-end proof).** The check serves a small attack page from another local port. Its script sends, to the live server, exactly the plain POST used in the demonstration above. First against a server whose new checks are switched off for this one test (so the attack is shown to **work**: the run goes from *ready* to *running*), then against the real, protected server (the run stays *ready*). Both results are read from the server, not from the browser. This proves the attack is real and that the fix stops it, in a real browser.

**In the unified app (Stage C):** the Live page's iframe is shown in real Chrome and its `sandbox` setting (if Streamlit adds one) is read, to confirm the live page keeps its real origin inside the frame. If the frame had an opaque origin, its own control requests would be refused; that is the one thing that could make this harder than it sounds (see below).

### Is this harder to do safely than it sounds?
The server side is straightforward and low-risk. Three things need saying plainly:
1. **I cannot click a button in a real browser from here** (the browser's remote-control interface is switched off by the company's policy), so "pressing Start inside the embedded page works" is verified in two parts: requests made with the exact headers the page's script sends (test 6, which also checks the token reaches the page), and a by-eye step in the Stage C review. The attack-page test above does run in real Chrome.
2. **The embedded frame's origin.** If Streamlit's `st.iframe` puts a sandbox on the frame without `allow-same-origin`, the live page would have an opaque origin, send `Origin: null` and be refused by its own server. I will read the real frame's attributes in Chrome before relying on it; if it is a problem the fix is to embed the page another way (a plain frame element), not to loosen the Origin check. I will not accept `null` as an allowed origin.
3. **Strictness can surprise.** Opening the live page through any other address (a different host name, a proxy) is now refused, by design.

### Approvals needed for section 11
1. The three checks, the token design and the two headers as described.
2. Step "C0" as a separate commit and log entry, editing the four live files and `live_check.py`, protecting 8504 and 8514 together.
3. The self-tests above, including the real-Chrome attack page.

## 12. Addendum (2026-10-14, approved by the owner's "do what is best" and BUILT): the Live run page on the connected app (8511)

**Request.** On the app opened with the loop connected (8511), the Live run page should show the *connected-loop* live run, inside that page. Today it starts on Example 1 (the in-frame chooser can switch to a connected scenario), and both apps would use the same live port (8514), so only one could run its live view at a time.

**Proposed change (small; the approved command allow-list is widened, so it needs your approval):**
1. **Each app gets its own live port.** The shell maps the app's own server port to a live port from a fixed table (8510 to 8514, 8511 to 8515; anything else 8514). It is data, not arithmetic. `shared()` takes the port when it first makes the supervisor.
2. **The connected scenario, from the run record.** The connected run's record names its scenario in `meta.run_id` (`connected-baseline`, and so on). The page reads that, and if it starts with `connected-` and the rest is one of the four known names (`baseline`, `new_supplier`, `period_shift`, `unpredictable_dissolution`) it asks the supervisor for the connected live view; otherwise nothing changes.
3. **The command allow-list gets exactly one optional addition.** `live_command(port, connected=None)` returns the same fixed list as now, and, only when `connected` is one of the four constant names, the same list plus `--connected NAME`. Nothing else may be added. The source scan is changed to accept exactly those two forms (the fixed list; the fixed list plus `--connected` and one of the four constants); the planted-violation self-tests gain: a scenario name that is not one of the four, a scenario built from text, an extra flag, and the host flag, each caught.
4. **`embedded_main.py` accepts `--connected NAME`,** checks NAME against `cellpoc.connected.SCENARIO_NAMES` and passes it to the existing `LiveServer(port, None, connected=NAME)`. A wrong name exits with a plain message. No other live file changes; the bind guard, the control protection and the job object are untouched.
5. **Checks added.** The supervisor starts the connected live program for real (listening on 127.0.0.1 only; the page's chooser shows `connected:baseline` as the current choice); a bad scenario name is refused before anything starts; two supervisors on the two ports run side by side, each on its own port, and stopping one leaves the other running; and in real Chrome on the actual connected app and its Streamlit frame the live view loads and the run starts (the same end-to-end proof as before, for the connected scenario).

**Takes a while to start:** the connected loop reads the data and judges the models first (about a minute the first time), so the page says so while it starts, and the supervisor's wait for the program to listen is lengthened for the connected variant only (from 60 to 300 seconds).

**Not changed:** the guard entries for the shell, the supervisor's import list, the no-network rule, the three-command allow-list (the live command is still one command), the 8504 stand-alone page.