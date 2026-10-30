"""The physics part (new, 2026-10-16): a MuJoCo model of the cell built from the layout file, and checks that the arm can reach everything, asked of MuJoCo itself. It imports no other part of the project and touches no network.

It is a separate, optional layer. Nothing in the simulation, the planner, the executor or the dashboard uses it yet: runs, timings and trial counts are exactly what they were. See docs/physics_plan.md for what comes next and what MuJoCo cannot do.
"""
from .reach import Solution, SpotReport, reach_all, solve, spare_reach, stretched_length, tightest
from .sanity import free_fall, repeatable, settle_vial
from .scene import Cell, build_mjcf, load_cell, spots
from .stage import Stage, frame_for, prepare_drawing

__all__ = ["Cell", "Stage", "frame_for", "prepare_drawing", "Solution", "SpotReport", "build_mjcf", "free_fall", "load_cell", "reach_all", "repeatable", "settle_vial", "solve", "spare_reach", "spots", "stretched_length", "tightest"]
