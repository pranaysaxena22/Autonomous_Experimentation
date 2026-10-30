"""Pictures of the MuJoCo playback: a still image or an animated GIF with a caption bar (what the arm is doing, the run's simulated clock, and the label that this is an illustration). Offline, nothing leaves the computer."""
from __future__ import annotations

from pathlib import Path

import mujoco
from PIL import Image, ImageDraw, ImageFont

from .motion import Motion, apply_frame
from .scene import Cell, spots

FONT = Path(__file__).resolve().parents[2] / "static" / "OpenSans.ttf"
GREEN, DARK, BLACK, WHITE, SOFT, RED = (134, 188, 37), (40, 39, 40), (0, 0, 0), (255, 255, 255), (230, 230, 230), (218, 41, 28)


def camera() -> mujoco.MjvCamera:
    """The default view: from the front, a little above, the whole table in frame."""
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [0.0, 0.5, 0.68]
    cam.distance, cam.azimuth, cam.elevation = 3.0, 90.0, -44.0
    return cam


def project(cam: mujoco.MjvCamera, point, size: tuple[int, int], fovy_deg: float = 45.0):
    """Where a point in the scene appears in a picture taken with a free camera (pixel x, pixel y), or None if it is behind the camera."""
    import math
    import numpy as np
    az, el = math.radians(cam.azimuth), math.radians(cam.elevation)
    forward = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    position = np.array(cam.lookat) - cam.distance * forward
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    d = np.array(point, dtype=float) - position
    depth = float(np.dot(d, forward))
    if depth <= 0.05:
        return None
    f = (size[1] / 2) / math.tan(math.radians(fovy_deg) / 2)
    return size[0] / 2 + f * float(np.dot(d, right)) / depth, size[1] / 2 - f * float(np.dot(d, up)) / depth


def _labels(draw: ImageDraw.ImageDraw, layout: dict, cam: mujoco.MjvCamera, size: tuple[int, int]) -> None:
    """The name of every station, bottle slot and tool holder, as small white tags with a green edge (like the 3D replay's)."""
    font = _font(max(10, size[1] // 52), True)
    slot_count = 0
    for spot in spots(layout):
        x, y, z = spot["xyz"]
        if spot["kind"] == "bottle slot":                                  # neighbouring slots are close together: stagger their tags
            slot_count += 1
        lift = {"station": 0.66, "bottle slot": 0.2 + 0.09 * (slot_count % 3), "tool holder": 0.5}[spot["kind"]]
        found = project(cam, (x, y, z + lift), size)
        if not found:
            continue
        text = spot["label"]
        w, h = draw.textlength(text, font=font) + 14, size[1] // 30
        left, top = found[0] - w / 2, found[1] - h / 2
        draw.rounded_rectangle((left, top, left + w, top + h), radius=5, fill=(255, 255, 255, 235), outline=GREEN, width=2)
        draw.text((left + 7, top + h * 0.12), text, font=font, fill=DARK)


def _font(size: int, bold: bool = False):
    try:
        font = ImageFont.truetype(str(FONT), size)
        if bold:
            try:
                font.set_variation_by_name("Bold")
            except Exception:           # the bundled font is a variable font; if the weight cannot be set the regular one is used
                pass
        return font
    except OSError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def decorate(image: Image.Image, trial: int, caption: str, clock: str, fault: bool, recovery: bool, layout: dict | None = None, cam: mujoco.MjvCamera | None = None) -> Image.Image:
    """Add the station names, the label badge, the trial and clock, and the caption bar to a rendered frame."""
    image = image.convert("RGB")
    w, h = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    if layout is not None and cam is not None:
        _labels(draw, layout, cam, (w, h))
    small, mid = _font(max(11, h // 36), True), _font(max(13, h // 28))
    draw.rounded_rectangle((16, 14, 16 + draw.textlength("ILLUSTRATIVE SIMULATION", font=small) + 24, 14 + h // 20), radius=h // 40, fill=GREEN)
    draw.text((28, 14 + h // 100), "ILLUSTRATIVE SIMULATION", font=small, fill=BLACK)
    right = "Cell at rest" if trial == 0 else f"Trial {trial}   |   run clock {clock}"            # trial 0 is the picture of the cell before any trial has started
    draw.text((w - 16 - draw.textlength(right, font=small), 14 + h // 100), right, font=small, fill=WHITE)
    lines = _wrap(draw, caption, mid, w - 48)[:2]
    bar_h = 22 + len(lines) * (h // 22)
    colour = (120, 20, 15, 235) if fault else (40, 39, 40, 235)
    draw.rectangle((0, h - bar_h, w, h), fill=colour)
    draw.rectangle((0, h - bar_h, w, h - bar_h + 3), fill=RED if fault else GREEN)
    for i, line in enumerate(lines):
        draw.text((24, h - bar_h + 12 + i * (h // 22)), line, font=mid, fill=WHITE)
    if recovery:
        tag = "RECOVERY"
        draw.rounded_rectangle((w - 24 - draw.textlength(tag, font=small) - 24, h - bar_h - h // 16, w - 16, h - bar_h - 8), radius=8, fill=GREEN)
        draw.text((w - 24 - draw.textlength(tag, font=small) - 12, h - bar_h - h // 16 + 4), tag, font=small, fill=BLACK)
    return image


def render_frame(cell: Cell, renderer: mujoco.Renderer, motion: Motion, index: int, cam: mujoco.MjvCamera) -> Image.Image:
    frame = motion.frames[index]
    apply_frame(cell, frame)
    renderer.update_scene(cell.data, cam)
    return decorate(Image.fromarray(renderer.render()), motion.trial, frame.caption, frame.clock, frame.fault, frame.recovery, cell.layout, cam)


def save_still(cell: Cell, motion: Motion, index: int, path: Path, size: tuple[int, int] = (1280, 720)) -> Path:
    renderer = mujoco.Renderer(cell.model, size[1], size[0])
    try:
        render_frame(cell, renderer, motion, index, camera()).save(path)
    finally:
        renderer.close()
    return path


def save_gif(cell: Cell, motion: Motion, path: Path, size: tuple[int, int] = (720, 405), stride: int = 2) -> Path:
    """The whole playback as an animated GIF (every `stride`th frame)."""
    renderer = mujoco.Renderer(cell.model, size[1], size[0])
    cam = camera()
    try:
        images = [render_frame(cell, renderer, motion, i, cam).quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for i in range(0, len(motion.frames), stride)]
    finally:
        renderer.close()
    images[0].save(path, save_all=True, append_images=images[1:], duration=int(1000 * stride / motion.fps), loop=0, optimize=False)
    return path
