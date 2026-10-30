"""Stage 4-1: the bridge that turns Stage 3's saved answers into the decision engine's brief. Neither the modelling part nor the engine imports it."""
from .builder import build_brief, range_factor
from .text import render

__all__ = ["build_brief", "range_factor", "render"]
