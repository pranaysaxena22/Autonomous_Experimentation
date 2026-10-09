# Naming rules for the platform formats

> ILLUSTRATIVE / SYNTHETIC. These rules apply to the files in `docs/platform_formats/` and, once built, to everything the platform reads or writes.
> `check_formats.bat` enforces them. The proof of concept (PoC) on `main` is unchanged: its names map to the platform names through the converter (section 4).

## 1. The rules
1. **One ID per quantity, with its unit in the name.** All IDs are lowercase, use only `a-z`, `0-9` and `_`, and start with a letter.
2. **Unit suffixes:** `_pct` percent, `_g` grams, `_kp` kilopond (the unit written kP; 1 kP = 9.807 N), `_kn` kilonewtons (the unit written kN), `_min` minutes, `_s` seconds, `_h` hours, `_m` metres, `_deg` degrees.
3. **Numeric settings** carry their unit in the field name (`time_min`, `duration_h`, `purge_min`, `batch_size_g`) or have a `unit` field beside them. Counts, trial numbers, seeds and probabilities (0 to 1) need no unit.
4. **Phases are lowercase:** `act`, `sense`, `reason`, `adapt`.
5. **Things** (stations, slots, holders, objects) have lowercase IDs too: `rack`, `balance`, `slot_3`, `punch_holder`, `bottle_binder`.
6. The unit of a field is its meaning, never a hidden assumption: if a value is a percentage the ID or the `unit` field says so.

## 2. The platform IDs
| Quantity | Platform ID | Unit | Role |
|---|---|---|---|
| Drug | `drug_pct` | % | ingredient |
| Binder | `binder_pct` | % | ingredient |
| Disintegrant | `disintegrant_pct` | % | ingredient |
| Lubricant | `lubricant_pct` | % | ingredient |
| Filler | `filler_pct` | % | ingredient (the balance: 100 minus the others) |
| Compression force | `compression_force_kn` | kN | process factor |
| Blend time | `blend_time_min` | min | process factor |
| Binder supplier, filler grade, dissolution instrument | `binder_supplier`, `filler_grade`, `dissolution_instrument` | (categories) | context factors |
| Dissolution at 30 minutes | `dissolution_30min_pct` | % | result |
| Hardness | `hardness_kp` | kP | result |
| Friability | `friability_pct` | % | result |
| Mass on the balance | `mass_g` | g | instrument reading |

## 3. Fixed vocabularies
- **Steps:** `dispense`, `mix`, `press`, `test`, `clean`.
- **Phases:** `act`, `sense`, `reason`, `adapt` (act = dispense, mix, press; sense = test; reason = first part of clean; adapt = the rest of clean).
- **Action types (ten):** `move`, `pick`, `place`, `pour`, `shake`, `press`, `stir`, `scan`, `read`, `wait`.
  `shake` has a style: `mix` or `tap`. `event` does not exist in plans. Faults appear on the action they hit (a `fault` field) and as recovery actions in the executed timeline.
- **Action origin (executed timeline only):** `planned`, `recovery`. **Outcome:** `ok`, `failed`, `interrupted`.
- **Locations:** the station IDs in the layout, `slot_1` to `slot_5`, the holder IDs (`punch_holder`, `rod_holder`) and `home`.
- **Goals:** constraints use `at_least`, `at_most`, `between`; objectives use `maximise`, `minimise`.
- **`data_status`** (weakest to strongest): `synthetic`, `illustrative`, `real`, `validated`.
  **A record takes its weakest input.** Example: a setup that is `illustrative`, an experiment table that is `synthetic` and a layout that is `illustrative` give a record that is `synthetic`.

## 4. Mapping other names to the platform names
| Platform | Raw client table (as in `data/mock/`) | PoC (`config/settings.yaml`, run record) |
|---|---|---|
| `drug_pct` | `drug_pct` | `drug` |
| `filler_pct` | `filler_pct` | `filler` |
| `binder_pct` | `binder_pct` | `binder` |
| `disintegrant_pct` | `disintegrant_pct` | `disintegrant` |
| `lubricant_pct` | `lubricant_pct` | `lubricant` |
| `compression_force_kn` | `compression_force_kN` | (not in the PoC) |
| `blend_time_min` | `blend_time_min` | (not in the PoC) |
| `dissolution_30min_pct` | `dissolution_30min_pct` | `dissolution_pct` (run record), `dissolution_30min` (settings) |
| `hardness_kp` | `hardness` together with `hardness_unit` (newtons divided by 9.807) | `hardness_kp` (run record), `hardness` (settings) |
| `friability_pct` | `friability_pct` (with `friability_note` "<0.05") | (not in the PoC) |

Raw columns map to platform IDs **during ingestion**, using the `data.column_map` section of the setup file. PoC names map to platform names **through the converter**. Other renames the converter handles:

| Platform setup | PoC settings |
|---|---|
| `time_min` (step) | `duration_minutes` |
| step `mix` | step `blend` |
| `duration_h` | `duration_hours` |
| `purge_min` | `purge_minutes` |
| `reason_min` | `reason_minutes` |
| `recipe_rules` | (the PoC has no recipe rules; its ingredients are independent) |
| `targets.constraints` | `specifications` |
| `faults.scripted[].where.step` | `scripted_faults.events[].station` |
| fault cause "binder bottle jam" | the PoC settings word it "binder dispenser clog" (wording only) |
| `virtual_lab.noise` list: `{quantity: dissolution_30min_pct, sd: 2.0}` | `virtual_lab.noise.dissolution_sd` |
| `virtual_lab.noise` list: `{quantity: hardness_kp, sd: 0.35}` | `virtual_lab.noise.hardness_sd` |

## 5. Rules the plan and the executed timeline must obey
- Every action has a `step`. Within each step, the planned action durations (waits included) add up to the setup's `time_min` for that step, to within 1 second.
- Actions follow each other with no gap and no overlap; waiting is an explicit `wait` action.
- The robot holds at most one object. It picks only from where the object is, places only what it holds, and holds nothing during a wait longer than 300 seconds.
- Pour amounts equal `batch_size_g` times the recipe percentage; the `mix` shake lasts `blend_time_min`; the press force is `compression_force_kn`.
- The executed timeline contains every planned action, unchanged in what it is asked to do, plus `recovery` actions (each says which action it `recovers`). Actual times are contiguous.
- **Fault timing differs from the PoC.** The PoC's rule (a failed attempt takes the whole step, then a purge, then the whole step again) is a coarse simplification. In the platform the executed timeline decides: the fault costs what its recovery actions cost. The converter and the PoC keep the PoC's rule, so `main` is unchanged.

## 6. Files and paths
- Any file named inside a file is a **relative path, inside the project, with no `..`**, no drive letter and no leading slash.
- YAML is read with the **safe reader only** (`yaml.safe_load`).
- CSV files are read as UTF-8; a leading byte-order mark and either kind of line ending (Windows CRLF or Unix LF) are accepted. Files written by the platform use no byte-order mark and LF endings, like the mock data.
- A CSV cannot carry a version or label, so each table has a companion `<name>.meta.json`.

## 7. Layout reach policy, waits and friability
- **Reach:** the arm's spare reach at every location (at its working height and at the safe height) is checked in 3D from the shoulder. Fail if the spare reach is below 0.03 m; warn if it is below 0.10 m; otherwise fine.
- **Waits:** every `wait` action carries a `reason` that names the real process it stands for (for example "dispenser purge and reset after the binder jam"), never just "wait" or "filler".
- **Friability:** the planner includes friability steps (the friability tester station) only when the setup needs them: an objective on `friability_pct`, or a required constraint on it.
