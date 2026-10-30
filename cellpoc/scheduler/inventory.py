"""The shelf: how much of each ingredient there is. A MOCK for now: plain numbers in grams that go down as batches are weighed out and come back up when someone restocks.

A batch can only be made if every ingredient it needs is on the shelf. If one is short, `take` says so and takes nothing, and the job that asked stops and is marked blocked: it never fails silently.
Nothing here reads a real stock system. The real rules (what is bought, what is reserved for whom, expiry) are not decided yet.
"""
from __future__ import annotations

import threading

from ..contracts import IngredientMissing, SupplyRecord

LABELS = {"drug_pct": "Drug (active)", "filler_pct": "Filler", "binder_pct": "Binder", "disintegrant_pct": "Disintegrant", "lubricant_pct": "Lubricant"}
# Grams on the shelf at the start of the demonstration, and what a restock brings each back to. The binder is short on purpose: a full run of Example 1 weighs out about 18 g of it and a run of
# Example 3 about 17 g, so after the first job there is not enough left for the second to finish, and the demonstration shows a job that is blocked part-way through.
DEMO_START_G = {"drug_pct": 250.0, "filler_pct": 1600.0, "binder_pct": 26.0, "disintegrant_pct": 500.0, "lubricant_pct": 40.0}
DEMO_FULL_G = {"drug_pct": 400.0, "filler_pct": 2000.0, "binder_pct": 120.0, "disintegrant_pct": 600.0, "lubricant_pct": 60.0}


class Inventory:
    def __init__(self, start_g: dict[str, float], full_g: dict[str, float], labels: dict[str, str] | None = None):
        self._start, self._full = dict(start_g), dict(full_g)
        self._left = dict(start_g)
        self._labels = dict(labels or LABELS)
        self._lock = threading.Lock()

    @classmethod
    def demo(cls) -> "Inventory":
        return cls(DEMO_START_G, DEMO_FULL_G)

    def _short(self, needs: dict[str, float]) -> IngredientMissing | None:
        """The ingredient that is furthest short of what is asked, or None if the shelf covers it all (the caller holds the lock)."""
        worst = None
        for ingredient, grams in needs.items():
            left = self._left.get(ingredient, 0.0)
            if grams > left + 1e-9 and (worst is None or grams - left > worst[1] - worst[2]):
                worst = (ingredient, grams, left)
        return None if worst is None else IngredientMissing(worst[0], self._labels.get(worst[0], worst[0]), worst[1], worst[2])

    def take(self, needs: dict[str, float]) -> None:
        """Weigh out a batch: all of it or nothing. Raises IngredientMissing, with the shelf untouched, if any ingredient cannot cover its part."""
        with self._lock:
            short = self._short(needs)
            if short is not None:
                raise short
            for ingredient, grams in needs.items():
                self._left[ingredient] = self._left.get(ingredient, 0.0) - grams

    def preflight(self, needs: dict[str, float]) -> IngredientMissing | None:
        """Could a batch of at least this size be made at all? Looks only; takes nothing."""
        with self._lock:
            return self._short(needs)

    def restock(self) -> None:
        with self._lock:
            self._left = dict(self._full)

    def reset(self) -> None:
        with self._lock:
            self._left = dict(self._start)

    def levels(self) -> list[SupplyRecord]:
        with self._lock:
            return [SupplyRecord(i, self._labels.get(i, i), round(self._left.get(i, 0.0), 2), self._full[i]) for i in self._full]
