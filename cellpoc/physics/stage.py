"""The MuJoCo picture of a run in progress: given a trial's executed timeline and how far into the trial the run is, a JPEG of the cell with the arm where the plan has it at that moment.

The live page asks for one picture at a time (a read-only request) and shows it in place of its own 3D scene. Each action of the timeline is played by the same arm movements the Physics page uses (cellpoc/physics/motion.py); the moment inside the action
chooses the frame of those movements, so the arm moves exactly as fast as the run's own clock does. Nothing here decides or changes anything in the run: it only draws what the timeline says.
All drawing happens on ONE worker thread. The invisible window MuJoCo draws into must be made on the program's main thread (Windows does not allow it elsewhere), so `prepare_drawing()` makes it once at start-up and the worker thread only uses it.
"""
from __future__ import annotations

import collections
import io
import threading
from concurrent.futures import ThreadPoolExecutor

import mujoco
import numpy as np

from .motion import Motion, plan_motion, rest_motion
from .render import camera, render_frame
from .scene import load_cell

SIZE = (960, 540)
JPEG_QUALITY = 78
MOTIONS_KEPT = 4          # the movements of the last few trials are kept, so a trial is planned once
PICTURES_KEPT = 48


_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mujoco-stage")          # the ONE thread that draws, for every stage in the program (a drawing window can be in use by one thread at a time)
_WINDOW = None          # the invisible window MuJoCo draws into (made once, on the main thread)
_WINDOW_LOCK = threading.Lock()


def prepare_drawing() -> None:
    """Make the invisible window MuJoCo draws into. Call it once, on the program's main thread, before the first picture is asked for. Raises if this computer cannot draw (no graphics library or display)."""
    global _WINDOW
    with _WINDOW_LOCK:
        if _WINDOW is None:
            import glfw
            if not glfw.init():
                raise RuntimeError("The graphics library could not start.")
            glfw.window_hint(glfw.VISIBLE, 0)
            window = glfw.create_window(1920, 1080, "Invisible window", None, None)
            if not window:
                raise RuntimeError("An invisible drawing window could not be made (this must happen on the main thread).")
            glfw.make_context_current(None)             # let go of it here: the drawing thread takes it
            _WINDOW = window


class _Drawer:
    """What MuJoCo's own Renderer does, on the shared window, so any one thread can draw: it has the two calls the picture code uses (`update_scene`, `render`)."""

    def __init__(self, model, width: int, height: int):
        import glfw
        if _WINDOW is None:
            prepare_drawing()                           # fails in words if this is not the main thread
        self._glfw = glfw
        glfw.make_context_current(_WINDOW)
        self.model, self.width, self.height = model, width, height
        self._context = mujoco.MjrContext(model, mujoco.mjtFontScale.mjFONTSCALE_150)
        mujoco.mjr_setBuffer(mujoco.mjtFramebuffer.mjFB_OFFSCREEN, self._context)
        glfw.make_context_current(None)
        self._scene = mujoco.MjvScene(model, maxgeom=2000)
        self._option = mujoco.MjvOption()
        self._rect = mujoco.MjrRect(0, 0, width, height)
        self._data = self._cam = None

    def update_scene(self, data, cam) -> None:
        self._data, self._cam = data, cam

    def render(self) -> np.ndarray:
        self._glfw.make_context_current(_WINDOW)
        mujoco.mjv_updateScene(self.model, self._data, self._option, None, self._cam, mujoco.mjtCatBit.mjCAT_ALL.value, self._scene)
        mujoco.mjr_render(self._rect, self._scene, self._context)
        pixels = np.empty((self.height, self.width, 3), dtype=np.uint8)
        mujoco.mjr_readPixels(pixels, None, self._rect, self._context)
        self._glfw.make_context_current(None)           # let go, so that another stage (another setup's layout) can use the window next
        return np.flipud(pixels)

    def close(self) -> None:
        self._glfw.make_context_current(_WINDOW)
        self._context.free()
        self._glfw.make_context_current(None)


def frame_for(motion: Motion, timeline: dict, seconds_into_trial: float) -> int:
    """Which frame of the movements shows the cell this many seconds into the trial: inside an action, the frame as far through the action's frames as the moment is through the action; after the last action, the last frame."""
    if seconds_into_trial <= 0 or not motion.ranges:
        return 0
    last = len(motion.frames) - 1
    for action, (_, first, after) in zip(timeline["actions"], motion.ranges):
        start, length = action["actual_start_s"], action["actual_duration_s"]
        if seconds_into_trial < start + length:
            if after <= first:                                       # an action that needed no movement (already there): the frame before it
                return max(0, first - 1)
            through = min(1.0, max(0.0, (seconds_into_trial - start) / length)) if length else 1.0
            return min(after - 1, first + int(through * (after - first)))
    return last


class Stage:
    """Draws the cell for a layout. Create one per layout; ask for pictures with `jpeg`; call `close` when done."""

    def __init__(self, layout: dict, size: tuple[int, int] = SIZE):
        self.layout, self.size = layout, size
        self._cell = self._renderer = self._cam = None
        self._motions: "collections.OrderedDict[int, Motion]" = collections.OrderedDict()
        self._pictures: "collections.OrderedDict[tuple, bytes]" = collections.OrderedDict()

    def jpeg(self, timeline: dict, seconds_into_trial: float) -> bytes:
        """The picture, as JPEG bytes (drawn on the worker thread). Raises MotionError, in words, if the plan cannot be played."""
        return _POOL.submit(self._draw, timeline, seconds_into_trial).result(timeout=60)

    def _draw(self, timeline: dict, seconds_into_trial: float) -> bytes:
        if self._cell is None:
            self._cell = load_cell(self.layout, with_objects=True)
            self._renderer = _Drawer(self._cell.model, self.size[0], self.size[1])
            self._cam = camera()
        trial = int(timeline["trial"])
        motion = self._motions.get(trial)
        if motion is None:
            motion = plan_motion(self._cell, timeline)
            self._motions[trial] = motion
            while len(self._motions) > MOTIONS_KEPT:
                self._motions.popitem(last=False)
        index = frame_for(motion, timeline, seconds_into_trial)
        key = (trial, index)
        if key in self._pictures:
            return self._pictures[key]
        image = render_frame(self._cell, self._renderer, motion, index, self._cam)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        self._pictures[key] = buffer.getvalue()
        while len(self._pictures) > PICTURES_KEPT:
            self._pictures.popitem(last=False)
        return self._pictures[key]

    def rest_jpeg(self) -> bytes:
        """The picture of the cell at rest (before any trial has started)."""
        return _POOL.submit(self._draw_rest).result(timeout=60)

    def _draw_rest(self) -> bytes:
        if self._cell is None:
            self._cell = load_cell(self.layout, with_objects=True)
            self._renderer = _Drawer(self._cell.model, self.size[0], self.size[1])
            self._cam = camera()
        key = (0, 0)
        if key not in self._pictures:
            image = render_frame(self._cell, self._renderer, rest_motion(self._cell), 0, self._cam)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
            self._pictures[key] = buffer.getvalue()
        return self._pictures[key]

    def close(self) -> None:
        def release():
            if self._renderer is not None:
                self._renderer.close()
        _POOL.submit(release).result(timeout=10)
