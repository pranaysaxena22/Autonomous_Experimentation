"""The cell's inspection of a pressed tablet: a photograph of the tablet in, 'normal' or 'defective' (chipped, cracked, worn, discoloured, broken) and how sure the network is out, plus an outline of where it looked when it calls a tablet defective.

The network is a MobileNetV3-Large classifier fine-tuned by tools/train_tablet.py on the public PharmaVision photographs (640 smartphone photographs of tablets). Its weights live in data/vision_models (not saved in git). When they are absent the program says so
and the cell makes no tablet check. The camera in the cell sees ONE tablet at a time (the arm holds it up), so this is a classifier and not an object detector: a detector such as YOLO is for finding many objects in one picture.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

import cv2
import numpy as np

MODEL_FOLDER = Path(__file__).resolve().parents[2] / "data" / "vision_models"
WEIGHTS = MODEL_FOLDER / "tablet.pt"
REPORT = MODEL_FOLDER / "tablet_report.json"
CLASSES = ("normal", "defective")
SIZE = 224
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
THRESHOLD = 0.5                  # the probability of 'defective' at or above which a tablet is called defective
OUTLINE_LEVEL = 0.55             # the part of the map (0 to 1) that is outlined as 'where it looked'
_cache: dict = {}


@dataclass
class TabletReading:
    label: str                   # "normal" or "defective"
    defect_probability: float    # 0 to 1
    picture: np.ndarray          # the photograph (BGR) with the area it looked at outlined when the tablet is called defective


def available() -> bool:
    """True when the trained weights exist and PyTorch can be loaded."""
    return WEIGHTS.exists() and find_spec("torch") is not None and find_spec("torchvision") is not None


def build_model(pretrained: bool = False):
    """MobileNetV3-Large with a two-way answer. `pretrained` starts from weights learned on everyday photographs (for training)."""
    from torch import nn
    from torchvision.models import MobileNet_V3_Large_Weights, mobilenet_v3_large
    model = mobilenet_v3_large(weights=MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, len(CLASSES))
    return model


def _model():
    if "model" not in _cache:
        import torch
        model = build_model(False)
        model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=True))
        model.eval()
        _cache["model"] = model
    return _cache["model"]


def square(image_bgr: np.ndarray) -> np.ndarray:
    """The photograph padded (never stretched) to a square with its own edge colour, so a long tablet keeps its shape."""
    h, w = image_bgr.shape[:2]
    side = max(h, w)
    top, left = (side - h) // 2, (side - w) // 2
    return cv2.copyMakeBorder(image_bgr, top, side - h - top, left, side - w - left, cv2.BORDER_REPLICATE)


def to_tensor(image_bgr: np.ndarray):
    """A photograph as the network's input: padded square, resized, colours normalised."""
    import torch
    small = cv2.resize(cv2.cvtColor(square(image_bgr), cv2.COLOR_BGR2RGB), (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    return torch.from_numpy(((small - MEAN) / STD).transpose(2, 0, 1)).unsqueeze(0)


def _where_it_looked(model, tensor, size: tuple[int, int]) -> np.ndarray:
    """A map (0 to 1, at `size` = height, width of the padded square) of which parts of the photograph pushed the answer towards 'defective' (Grad-CAM on the network's last picture layer)."""
    import torch
    feature = {}
    handle = model.features.register_forward_hook(lambda m, i, o: feature.update(out=o))
    try:
        with torch.enable_grad():
            x = tensor.clone().requires_grad_(True)
            logits = model(x)
            grad = torch.autograd.grad(logits[0, 1], feature["out"])[0]
    finally:
        handle.remove()
    weights = grad.mean(dim=(2, 3), keepdim=True)
    cam = torch.relu((weights * feature["out"].detach()).sum(dim=1))[0].numpy()
    cam = cv2.resize(cam, size[::-1], interpolation=cv2.INTER_CUBIC)
    cam -= cam.min()
    return cam / cam.max() if cam.max() > 0 else cam


def probability(image_bgr: np.ndarray) -> float:
    """How likely the network finds the tablet in the photograph defective, 0 to 1."""
    import torch
    with torch.no_grad():
        return float(torch.softmax(_model()(to_tensor(image_bgr)), dim=1)[0, 1])


def inspect(image_bgr: np.ndarray) -> TabletReading:
    """Read one photograph of one tablet."""
    score = probability(image_bgr)
    label = CLASSES[1] if score >= THRESHOLD else CLASSES[0]
    picture = square(image_bgr)
    if picture.shape[0] > 480:
        picture = cv2.resize(picture, (480, 480), interpolation=cv2.INTER_AREA)
    if label == "defective":
        cam = _where_it_looked(_model(), to_tensor(image_bgr), picture.shape[:2])
        contours, _ = cv2.findContours((cam >= OUTLINE_LEVEL).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(picture, contours, -1, (28, 41, 218), 3, cv2.LINE_AA)           # Deloitte-palette red (BGR), the area the network looked at
    return TabletReading(label, score, picture)


DEMO_FOLDER = Path(__file__).resolve().parents[2] / "data" / "public" / "pharmavision" / "demo_tablets"       # real test photographs, made by tools/pick_tablet_photos.py
DEMO_CASES = ("", "defective")   # what a presenter can show the camera: a tablet as the run has it (a normal one), or a defective one


@dataclass
class TabletCheck:
    label: str                   # "normal" or "defective", as the network read the photograph
    defect_probability: float
    verdict: str                 # "tablet ok" or "defective tablet"
    action: str                  # what the cell does next
    photo: str                   # which photograph was shown
    source: str                  # "real photograph"
    jpeg: bytes


def demo_photos(kind: str) -> list[Path]:
    return sorted(DEMO_FOLDER.glob(f"{kind}_*.jpg")) if DEMO_FOLDER.exists() else []


def check(trial: int, demo: str = "") -> TabletCheck | None:
    """The cell's inspection of the tablet the arm has just lifted out of the press. The simulation makes no real tablet, so the photograph is a real one (from the public PharmaVision set) standing in for the cell's camera: a normal tablet,
    different from trial to trial, or - when a presenter asks (`demo` = "defective") - a defective one. The network reads it as it would read any photograph. None when the demonstration photographs or the weights are not on this computer."""
    photos = demo_photos("defective" if demo == "defective" else "normal")
    if not photos or not available():
        return None
    path = photos[(trial - 1) % len(photos)]
    image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    found = inspect(image)
    ok, data = cv2.imencode(".jpg", found.picture, [cv2.IMWRITE_JPEG_QUALITY, 88])
    defective = found.label == "defective"
    return TabletCheck(found.label, found.defect_probability, "defective tablet" if defective else "tablet ok",
                       "Would be sent to the discard bin: this tablet does not go on to the hardness gauge." if defective else "Goes on to the hardness gauge.", path.stem, "real photograph", data.tobytes() if ok else b"")


def report() -> dict | None:
    """The training record and the scores on photographs the network never saw, or None if there is none."""
    try:
        return json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
