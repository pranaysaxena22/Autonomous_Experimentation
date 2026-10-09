"""Versions: the program's own version, and the setup format versions it can read.

A setup carries a `format_version`. Older versions are upgraded (migrated) when opened; a version newer than this
program knows is refused with a plain message. Nothing here changes a setup unless a migration is registered.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

PROGRAM_VERSION = "0.1.0"          # recorded in every saved setup
SETUP_FORMAT_VERSION = 1           # the newest setup format this program understands
OLDEST_SETUP_FORMAT = 1            # the oldest it can still open (older ones need a migration)

Migration = Callable[[dict], dict]


@dataclass(frozen=True)
class FormatSupport:
    """Which setup format versions this program can read. Tests pass a different one to prove the rules work."""
    current: int = SETUP_FORMAT_VERSION
    oldest: int = OLDEST_SETUP_FORMAT
    # migrations[n] turns a version-n setup into a version-(n+1) setup
    migrations: dict[int, Migration] = field(default_factory=dict)

    def can_upgrade(self, version: int) -> bool:
        return all(n in self.migrations for n in range(version, self.current))

    def upgrade(self, setup: dict, version: int) -> dict:
        upgraded = copy.deepcopy(setup)
        for n in range(version, self.current):
            upgraded = self.migrations[n](upgraded)
        upgraded["format_version"] = self.current
        return upgraded


DEFAULT_SUPPORT = FormatSupport()
