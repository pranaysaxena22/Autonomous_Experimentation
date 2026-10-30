# From the simulation to real instruments: the barcode and balance pipeline

**Illustrative.** Everything the project does today is a simulation with made-up values. This page says what is already built so that a real barcode scanner and a real balance can be connected later, and exactly what is still missing. Nothing here has been tried on real hardware.

## 1. The idea in plain words

The cell's **executor** is the part that carries out a plan step by step and reports what happened. Today a *stand-in* executor does this in simulated time. On real hardware, the same executor talks to the real devices through a **control computer**: an ordinary PC next to the cell, connected by cables or the network to the arm, the scanner and the balance.

The new **instruments** part (`cellpoc/instruments/`) is the layer between the executor and the devices. Each device has **one interface** and two implementations: a *simulated* one (used now) and a *serial* one (for the real device). The executor makes its decisions (right vial? stable weight?) from that interface, so the simulation already exercises the exact logic the real cell will use. Only the device behind the interface changes.

| Device | Interface | Simulated now | For real hardware | What the executor decides |
|---|---|---|---|---|
| Barcode scanner | `read()` gives `ok`, `unreadable` or `garbled` and the text | `SimulatedBarcodeScanner` (reads the vial's label; can be told to misread) | `SerialBarcodeScanner` on a transport | Right vial: carry on. Unreadable: turn the vial and read again (as many times as the layout allows). A different vial: stop, put it back, skip the candidate, alert staff. |
| Balance | `tare()` and `read()` give a weight, stable or not | `SimulatedBalance` (adds what is poured; optional seeded noise) | `SicsBalance` (the common Mettler-style text commands) on a transport | A reading counts only when stable. `dose_check` says under, over or ok against a tolerance (ready; not yet wired to stop a trial). |

## 2. How it happens in the simulation today (simple words)

- **Barcode.** The planner adds a "scan" step. The simulated scanner "reads" the label `V-` plus the trial number (for example `V-008`). It is always right unless the setup scripts a fault at the scan: then it misreads (unreadable, or another vial's label) and the executor reacts exactly as it would for a real scanner, shown on the dashboard, the 3D replay and the alerts. In the setup app, add a scripted fault with the action **scan** and a cause such as "barcode unreadable" or "wrong vial scanned".
- **Balance.** A pour onto the balance adds the planned amount to the simulated balance, and the "read the balance" step reports its total. A scripted binder jam makes the balance receive only part of the amount.

The label format (prefix, number of digits), the number of rescans and the time to turn a vial are **settings in the layout file** (`instruments.barcode`), with defaults that reproduce the old behaviour exactly. Nothing is built into the code.

## 3. What is built and proved without hardware

- The three drivers' **text handling** is tested against a pretend scanner and balance that play back what real ones say: clean reads, line endings, noise, silence, another vial, a settling balance, milligrams and kilograms, overload, busy.
- The executor makes the **same decisions with a pretend real scanner** plugged in (no scripted fault): the right label carries on, another vial's label stops the trial, a silent first read then a good one recovers by rescanning.
- All of this is in `check_instruments.bat`, together with proof that every normal run is unchanged.

## 4. Connecting a real scanner: the steps

1. **Choose a scanner.** A fixed-mount imager (2D, so it reads Data Matrix as well as Code 128) that sends text over USB-serial or RS-232. Choose labels that survive the solvents used.
2. **Install the serial package on the control computer:** `.venv\Scripts\python.exe -m pip install pyserial` (not needed for the simulation, so it is not in `requirements.txt` yet).
3. **Find the port** (for example COM4) in Windows Device Manager and the scanner's settings in its manual: baud rate, line ending, and whether it reads continuously or needs a trigger command (`trigger=` on `SerialBarcodeScanner`).
4. **Make the real scanner** in the real executor: `SerialBarcodeScanner(SerialTransport("COM4", 9600), format_from_layout(layout))`, inside an `Instruments(scanner, balance)` that is passed to the executor.
5. **Bench test** with about twenty labels, including smudged, tilted and wrong ones, before the arm is involved. Expect to tune the scan time and the turn time in the layout.
6. **With the arm:** the arm's own driver (not built; it is the other half of the real executor) moves the vial to the scanner, then the executor reads.

## 5. Connecting a real balance: the steps

1. **Choose a balance with a data port** (RS-232, USB or Ethernet) and check which command set it speaks. This driver speaks the Mettler-Toledo **SICS** style (`S` for a stable weight, replies `S S 12.3456 g` or `S D ...` while settling, `T` to tare). Other makers differ in the text; only the parsing in `SicsBalance` would change.
2. **Same steps 2 to 4 as above** with `SicsBalance(SerialTransport("COM3", 9600))`.
3. **Wire `dose_check` in** when you want the cell to stop on an out-of-tolerance pour: the function is ready and tested; deciding what recovery to run (re-pour, purge, alert) is a design decision to take once the dispenser is known.
4. **Calibrate and verify** with a certified test weight before any trial counts.

## 6. What is NOT built (so nobody is surprised)

- The **arm driver and a real executor** that moves the arm: needs the actual arm and a robotics engineer.
- Drivers for the **dispenser, press, hardness gauge and dissolution instrument**.
- A **camera**: not needed for any step above, and a barcode scanner and a balance are better sources than a picture. A vision check on top is a separate roadmap item (item 7b in `docs/platform_plan.md`).
- Any test on **real hardware**: no claim is made about real instruments, real labels or real timing.
