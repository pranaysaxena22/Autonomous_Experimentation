"""The vision part (new, 2026-10-22): reads a picture of a bench with OpenCV: which coloured liquids are in which vessels, how full each is, and, with four printed markers in view, where each stands for the arm and whether the arm can reach it.

It imports no other part of the project and touches no network. Classic image processing, no training data. The test scenes (cellpoc/vision/synthetic.py) have a known answer, so the health check can say exactly how right the reading is.
"""
from .analyse import Analysis, Vessel, VisionError, analyse, analyse_bytes, decode
from .bottle_check import BottleCheck, check as bottle_check
from .tablet import TabletCheck, check as tablet_check
from .config import COLOUR_HUES, Calibration, VesselType, colour_name
from .learned import available as model_available, status as model_status
from .synthetic import make_scene, real_photos, scene_set

__all__ = ["Analysis", "BottleCheck", "TabletCheck", "tablet_check", "COLOUR_HUES", "bottle_check", "model_available", "model_status", "Calibration", "Vessel", "VesselType", "VisionError", "analyse", "analyse_bytes", "colour_name", "decode", "make_scene", "real_photos", "scene_set"]
