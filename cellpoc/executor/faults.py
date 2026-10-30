"""Which fault, if any, a trial suffers: the setup's scripted faults (they happen on purpose, on the named trial) and its random faults (they may happen on any trial, by chance).

A scripted fault on a trial wins over a random one. Random faults are drawn from a stream that depends only on (seed, trial, which random fault), so a trial always gets the same luck whatever order trials are run in.
`chance_per_trial` and `retry_succeeds_chance` are probabilities from 0 to 1 and are used only for random faults; scripted faults use `retry_succeeds` (true or false).
"""
from __future__ import annotations

import random

from .interface import Fault


def _fault(where: dict, cause: str, retry_succeeds: bool, source: str) -> Fault:
    return Fault(where["step"], where["action"], cause, retry_succeeds, where.get("ingredient"), source)


def fault_for_trial(setup: dict, trial: int, seed: int) -> Fault | None:
    faults = setup.get("faults", {})
    for f in faults.get("scripted", []):
        if f["trial"] == trial:
            return _fault(f["where"], f["cause"], bool(f["retry_succeeds"]), "scripted")
    for index, f in enumerate(faults.get("random", [])):
        draw = random.Random(f"platform-fault:{seed}:{trial}:{index}")
        if draw.random() < f["chance_per_trial"]:
            return _fault(f["where"], f["cause"], draw.random() < f["retry_succeeds_chance"], "random")
    return None
