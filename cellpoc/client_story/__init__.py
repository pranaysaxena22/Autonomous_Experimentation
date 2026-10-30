"""The client story (new part, 2026-10-16): the run told as results a client cares about, worked out in advance from the saved run record and written next to it.

It imports no other part of the project and touches no network. The dashboard's Results page and the Overview's headline cards display what it writes; they calculate nothing.
"""
from .story import LABEL, STORY_FILE, build

__all__ = ["LABEL", "STORY_FILE", "build"]
