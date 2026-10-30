# Team call demo script (5 minutes, recorded in Teams)

Everything shown is a **simulation with illustrative values**. Say so at the start and at the end.

**Order:** Intro → the problem → what we built and who it helps → live walkthrough → close.
**Length:** about 4 min 55 s if you follow the times below. If you are running late, press **Next** in the demo caption to skip the waiting.

## Before the call (2 minutes)

1. Double-click `run_console.bat`. The console opens in your browser. (Or open the replay file `runs\replay\Autonomous_Formulation_Cell_replay.html` if you want no program running.)
2. Press **F11** for full screen. Pick the look you prefer with the **Dark / Light** button (the dark look reads better on a call).
3. Close the welcome window with **Explore on my own**. Make sure the page is on **Overview**, at the top.
4. In Teams: **Share → Window** (the browser window only, not the whole screen), so no notifications show. Start the recording.
5. Decide who speaks the demo. **Recommended: you speak.** Press **Guided demo** later, then **Mute voice** in its caption bar. (Alternative: leave the voice on and tick *Include computer sound* when sharing; then speak only the intro, problem, solution and close.)

## The script

| Time | Show on screen | Say |
|---|---|---|
| **0:00–0:15** Intro | **Overview**, the top of the page (title and picture of the cell) | "Hello everyone. I'll show you the Autonomous Formulation Cell: a lab station that makes, tests and learns from tablet recipes by itself. It's a simulation with illustrative values: no real robot and no real tablets yet. Five minutes: the problem, what we built, and a live walkthrough." |
| **0:15–0:55** The problem | Scroll to **The challenge** panel (three numbered points) | "Developing a tablet recipe is slow and manual. A team can run only about nine experiments a week by hand, and that's an assumption we'd replace with the client's own number. People work set hours, so nights and weekends are lost, and good recipes wait. Every bottle and every tablet is checked by eye, so a mix-up can slip through and spoil a result. And if something goes wrong at night, the work simply stops until morning." |
| **0:55–1:45** What we built, and who it helps | Scroll to **The solution** panel; then the **loop** at the bottom (Sense, Reason, Act, Adapt) | "So we built a robotic lab station that runs experiments around the clock. An arm weighs, mixes, presses and tests the tablets. Cameras check every ingredient bottle and every pressed tablet. A decision engine chooses the next recipe from the results so far. And when something goes wrong, the cell recovers by itself, or hands over to the morning team with a clear alert. For customers and the medical industry that means more experiments per week, fewer invalid results, a faster route to a recipe that meets specification, and a record of every check. Let me show it running." |
| **1:45–1:53** Walkthrough 1 | Click **Guided demo** (top right). Click **Mute voice**. The Operator view opens on the cell picture. | "This is the cell, simulated. We start from the beginning, on a Friday evening." |
| **1:53–2:08** Walkthrough 2 | Camera panel (right): **RIGHT BOTTLE** in green | "The arm lifts the first ingredient bottle in front of the camera. It reads the barcode, the printed name and the liquid. All three agree: right bottle, green." |
| **2:08–2:24** Walkthrough 3 | Camera panel: **WRONG BOTTLE** in red | "Now I've swapped the stickers on the next bottle. The camera catches it: red, wrong bottle. Colour alone could never catch that, because two ingredients can look the same." |
| **2:24–2:47** Walkthrough 4 | Camera panel: **DEFECTIVE TABLET** with the red outline | "Back to normal bottles. The cell presses a tablet, and a trained model inspects it. It finds a chip, outlines it in red, and sends this tablet to the discard bin instead of on to testing." |
| **2:47–3:25** Walkthrough 5 | Overview: the six tiles counting up, then **Needs attention** when the jam happens | "From here nobody touches anything. Trials start, tests finish, results appear on their own. Here: a bottle jams at the dispenser. The cell doesn't stop and nobody is called. It purges the line and retries by itself." |
| **3:25–3:38** Walkthrough 6 | **Needs attention**: the recovery | "The retry worked. The faults-handled number went up and the trial carried on. No person needed." |
| **3:38–4:14** Walkthrough 7 | **Lab manager**: charts, results table, then the red **waiting for staff** card | "This is the lab manager's view: every result as its test finishes, and how the results develop over the run. This time the retry failed. The cell skipped that recipe and queued an alert for the morning team. It's red because a person is needed. Everything else carried on." |
| **4:14–4:44** Walkthrough 8 | **Overview**: the finished run and the tiles | "The run is finished: about 29 to 30 trials in five days, with nobody in the lab. The comparison with the manual rate depends on the nine-a-week assumption, so we'd replace it with the client's own figure." |
| **4:44–5:00** Close | Stay on **Overview**; the caption says **That was the demo** | "To recap: more experiments, every bottle and tablet checked, faults handled without a call-out. Everything here is simulated. Next steps are real client data and expert review, then real equipment. Happy to take questions." |

## If something goes wrong

- **The demo is too slow:** press **Next** in the caption bar. **Pause narration** stops it moving on by itself.
- **A camera check does not appear:** it still moves on after a few seconds; say "the camera check runs at every pick" and continue.
- **You need to stop:** press **Esc** or **End demo**.
- **You lose your place:** the caption bar tells you which of the 9 steps you are on.

## Words to avoid

- Don't say the cell *predicts* anything or that it works on real tablets. It does not.
- Say "about 29 to 30 trials", never a single number.
- Say the nine-a-week figure is an assumption.
