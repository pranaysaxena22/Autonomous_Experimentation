"""The 3D replay viewer (Stage 7): writes one self-contained HTML file that replays executed timelines. It reads data files only and imports no other part of the platform."""
from .builder import ViewerError, build_viewer

__all__ = ["ViewerError", "build_viewer"]
