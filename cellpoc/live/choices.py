"""The setups the live page offers: the three illustrative examples, the setups saved in the setups folder, and the loop connected (one choice per development scenario).

The page only ever sends the NAME of a choice; the server turns it into a file here, from this list, so a web page can never make the server open a file of its own choosing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..connected import SCENARIO_NAMES
from ..setup import PROJECT_ROOT, example_choices
from ..setup.files import PACKAGE_EXAMPLES, SETUPS_FOLDER

SAVED_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")          # the names the setup app saves under
APPROVAL_EXAMPLE = ("setup_example_4_approval.yaml", "Example 4: a wrong vial on trial 12 that needs a person to accept or reject it")


@dataclass(frozen=True)
class Choice:
    id: str                       # example:1, saved:my-study or connected:baseline
    label: str                    # what the page shows
    kind: str                     # example, saved or connected
    path: Path | None = None      # the setup file (None for the connected loop)
    scenario: str | None = None   # the development scenario of a connected choice


def choices() -> list[Choice]:
    found = [Choice(f"example:{i}", label, "example", path) for i, (label, path) in enumerate(example_choices(), 1)]
    approval = PACKAGE_EXAMPLES / APPROVAL_EXAMPLE[0]                 # the run with a wrong vial that needs a person: offered here only, so the other examples and the checks that loop over them stay as they were
    if approval.is_file():
        found.append(Choice("example:4", APPROVAL_EXAMPLE[1], "example", approval))
    folder = PROJECT_ROOT / SETUPS_FOLDER
    if folder.is_dir():
        found += [Choice(f"saved:{p.stem}", f"Your saved setup: {p.stem}", "saved", p) for p in sorted(folder.glob("*.yaml")) if SAVED_NAME.match(p.stem)]
    found += [Choice(f"connected:{s}", f"The loop connected: {s.replace('_', ' ')} (synthetic data and the Stage 4 engine; the first time it prepares the models)", "connected", None, s) for s in SCENARIO_NAMES]
    return found


def find(choice_id) -> Choice | None:
    return next((c for c in choices() if isinstance(choice_id, str) and c.id == choice_id), None)


def id_for(setup_path: Path | str | None, connected: str | None) -> str:
    """The choice that matches how the server was started (a connected scenario, a setup file, or the standard example)."""
    if connected:
        return f"connected:{connected}"
    if setup_path:
        wanted = Path(setup_path).resolve()
        for c in choices():
            if c.path is not None and c.path.resolve() == wanted:
                return c.id
        return f"file:{Path(setup_path).name}"
    return "example:1"
