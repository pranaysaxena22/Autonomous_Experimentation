"""Trains the vision network (cellpoc/vision/learned.py): which pixels of a picture are background, vessel, or the contents of a vessel.

Data: the public LabPics photographs (tools/download_labpics.py fetches them: 2,187 real photographs of liquids and solids in vessels, each vessel and its filled part outlined by hand; MIT licence) plus drawn bench scenes whose labels are exact.
It starts from a network that already learned to segment everyday photographs and teaches it this one task, on the CPU, in the background. While it runs it writes data/vision_models/progress.json (the Vision page shows it) and when it ends it writes the weights and
a report of how well it does on pictures it never trained on (data/vision_models/report.json). Run:

    .venv\\Scripts\\python.exe tools\\train_vision.py [--epochs 8] [--limit 0]

--limit N uses only N real photographs (a quick trial). Nothing here is part of the running app; the app only reads the weights and the report.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cellpoc.vision import learned  # noqa: E402
from cellpoc.vision.config import COLOUR_HUES  # noqa: E402
from cellpoc.vision.synthetic import X0, Y0, HEIGHT_M, WIDTH_M, make_scene  # noqa: E402

ZIP = ROOT / "data" / "public" / "labpics" / "LabPicsV1.zip"
CACHE = ROOT / "data" / "public" / "labpics" / "prepared.npz"
PROGRESS = learned.MODEL_FOLDER / "progress.json"
SHORT = learned.SHORT_SIDE
IGNORE = 255
SEED = 20261022


def write_progress(**fields) -> None:
    learned.MODEL_FOLDER.mkdir(parents=True, exist_ok=True)
    fields["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PROGRESS.write_text(json.dumps(fields), encoding="utf-8")


def shrink(image: np.ndarray, label: np.ndarray | None = None):
    h, w = image.shape[:2]
    scale = SHORT / min(h, w)
    size = (int(round(w * scale)), int(round(h * scale)))
    small = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    return small, (None if label is None else cv2.resize(label, size, interpolation=cv2.INTER_NEAREST))


def as_mask(decoded: np.ndarray | None) -> np.ndarray | None:
    """A mask file as a plain on/off picture. LabPics stores them as three-channel pictures of 0 and 1, so they are read unchanged and any channel that is on counts (read as grey they would all come out as off)."""
    if decoded is None:
        return None
    return (decoded.max(axis=2) if decoded.ndim == 3 else decoded) > 0


def prepare_labpics(limit: int = 0, rebuild: bool = False) -> dict:
    """Read the downloaded zip once: for every photograph its picture, and a label map (0 background, 1 vessel, 2 contents of a vessel, 255 ignore), shrunk to the training size. Cached in one file."""
    if CACHE.exists() and not limit and not rebuild:
        data = np.load(CACHE, allow_pickle=True)
        return {k: list(data[k]) for k in data.files}
    if not ZIP.exists():
        raise SystemExit("The LabPics download is not there yet: run tools\\download_labpics.py first.")
    out = {"train_images": [], "train_labels": [], "test_images": [], "test_labels": []}
    with zipfile.ZipFile(ZIP) as z:
        names = set(z.namelist())
        samples = sorted({n.rsplit("/", 1)[0] for n in names if n.endswith("/Image.png") and "/Complex/" in n})
        if limit:
            random.Random(SEED).shuffle(samples)
            samples = samples[:limit]
        for k, folder in enumerate(samples):
            def read(name, flag):
                path = f"{folder}/{name}"
                return cv2.imdecode(np.frombuffer(z.read(path), np.uint8), flag) if path in names else None
            image = read("Image.png", cv2.IMREAD_COLOR)
            vessel, filled, ignore = as_mask(read("Semantic/1_Vessel.png", cv2.IMREAD_UNCHANGED)), as_mask(read("Semantic/16_Filled.png", cv2.IMREAD_UNCHANGED)), as_mask(read("Ignore.png", cv2.IMREAD_UNCHANGED))
            if image is None or vessel is None:
                continue
            label = np.zeros(image.shape[:2], np.uint8)
            label[vessel] = 1
            if filled is not None:
                label[filled & vessel] = 2
            if ignore is not None:
                label[ignore] = IGNORE
            small, small_label = shrink(image, label)
            split = "test" if "/Test/" in folder else "train"
            out[f"{split}_images"].append(small)
            out[f"{split}_labels"].append(small_label)
            if k % 200 == 0:
                write_progress(stage="preparing the photographs", done=k, total=len(samples))
    if not limit:
        np.savez(CACHE, **{k: np.array(v, dtype=object) for k, v in out.items()})
    return out


def drawn_scene(rng: random.Random, seed: int):
    """One drawn bench scene with exact labels, with the look varied (light, noise, blur, vessel shape, how many vessels, which colours, with or without the printed markers)."""
    colours = list(COLOUR_HUES)
    count = rng.randint(1, 6)
    vials = []
    for _ in range(count):
        vials.append((rng.uniform(-1.18, -0.82), rng.uniform(-0.1, 0.1), rng.choice([0.0, rng.uniform(0.05, 1.0), rng.uniform(0.05, 1.0)]), rng.choice(colours)))
    labels = np.zeros((720, 1280), np.uint8)
    image, truth = make_scene(vials, seed=seed, brightness=rng.uniform(0.6, 1.3), noise=rng.uniform(1, 10), blur=rng.choice([0, 0, 3, 5]), markers=rng.random() < 0.8, aspect=rng.uniform(3.5, 6.0), labels=labels)
    return shrink(image, labels)


def make_drawn(n: int, seed: int):
    rng = random.Random(seed)
    images, labels = [], []
    for i in range(n):
        image, label = drawn_scene(rng, seed * 1000 + i)
        images.append(image)
        labels.append(label)
    return images, labels


class Batches:
    """Random crops with flips and light/colour changes, as network inputs."""

    def __init__(self, images, labels, rng):
        self.images, self.labels, self.rng = images, labels, rng

    def sample(self, size: int = 320):
        import torch
        i = self.rng.randrange(len(self.images))
        image, label = self.images[i], self.labels[i]
        h, w = label.shape
        if h > size and w > size:
            y, x = self.rng.randrange(h - size + 1), self.rng.randrange(w - size + 1)
        else:
            y = x = 0
        crop, lab = image[y:y + size, x:x + size], label[y:y + size, x:x + size]
        pad_h, pad_w = size - crop.shape[0], size - crop.shape[1]
        if pad_h > 0 or pad_w > 0:
            crop = cv2.copyMakeBorder(crop, 0, max(pad_h, 0), 0, max(pad_w, 0), cv2.BORDER_CONSTANT, value=(114, 114, 114))
            lab = cv2.copyMakeBorder(lab, 0, max(pad_h, 0), 0, max(pad_w, 0), cv2.BORDER_CONSTANT, value=IGNORE)
        if self.rng.random() < 0.5:
            crop, lab = crop[:, ::-1], lab[:, ::-1]
        crop = np.clip(crop.astype(np.float32) * self.rng.uniform(0.75, 1.25) + self.rng.uniform(-20, 20), 0, 255)
        rgb = cv2.cvtColor(crop.astype(np.uint8), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(((rgb - learned.MEAN) / learned.STD).transpose(2, 0, 1).copy())
        return tensor, torch.from_numpy(lab.astype(np.int64).copy())

    def batch(self, n: int):
        import torch
        items = [self.sample() for _ in range(n)]
        return torch.stack([a for a, _ in items]), torch.stack([b for _, b in items])


def iou(pred: np.ndarray, truth: np.ndarray, number: int, counts: dict) -> None:
    valid = truth != IGNORE
    for c in range(number):
        p, t = (pred == c) & valid, (truth == c) & valid
        counts[c][0] += int((p & t).sum())
        counts[c][1] += int((p | t).sum())


def evaluate(images, labels) -> dict:
    """Per-class IoU (intersection over union: 1.0 is perfect) on pictures the network did not train on."""
    counts = {c: [0, 0] for c in range(len(learned.CLASSES))}
    for image, label in zip(images, labels):
        pred, _ = learned.predict(image)
        iou(pred, label, len(learned.CLASSES), counts)
    scores = {learned.CLASSES[c]: (counts[c][0] / counts[c][1] if counts[c][1] else None) for c in counts}
    scores["mean"] = float(np.mean([v for v in scores.values() if v is not None]))
    return scores


def level_error(seed: int, n: int = 60) -> dict:
    """Level reading on single-vessel drawn scenes, against the level worked out from the exact labels (contents rows over vessel rows)."""
    rng = random.Random(seed)
    errors = []
    for i in range(n):
        colour = rng.choice(list(COLOUR_HUES))
        level = rng.uniform(0.1, 1.0)
        labels = np.zeros((720, 1280), np.uint8)
        image, _ = make_scene([(rng.uniform(-1.15, -0.85), rng.uniform(-0.08, 0.08), level, colour)], seed=seed * 7 + i, brightness=rng.uniform(0.7, 1.2), noise=rng.uniform(1, 8), labels=labels, aspect=rng.uniform(3.5, 6.0))
        rows_vessel, rows_content = np.where((labels > 0).any(axis=1))[0], np.where((labels == 2).any(axis=1))[0]
        if rows_content.size == 0:
            continue
        truth = 100.0 * (rows_content[-1] - rows_content[0] + 1) / (rows_vessel[-1] - rows_vessel[0] + 1)
        small, _ = shrink(image)
        pred, sure = learned.predict(small)
        vessels, _, _, _ = learned.readings_from_masks(small, pred, sure, learned.VesselType(full_fraction=1.0), learned.Calibration())
        errors.append(abs(vessels[0].fill_pct - truth) if vessels else 100.0)
    return {"scenes": len(errors), "mean_error_points": float(np.mean(errors)), "within_10_points_pct": float(100.0 * np.mean([e <= 10 for e in errors]))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="use only this many real photographs (a quick trial)")
    parser.add_argument("--drawn", type=int, default=500)
    parser.add_argument("--rebuild", action="store_true", help="read the downloaded photographs again instead of using the cached copy")
    parser.add_argument("--steps", type=int, default=0, help="steps per epoch (0: one pass over the training pictures)")
    args = parser.parse_args()
    import torch
    torch.manual_seed(SEED)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    started = time.time()
    write_progress(stage="starting", epoch=0, epochs=args.epochs)
    real = prepare_labpics(args.limit, args.rebuild)
    write_progress(stage="drawing the bench scenes", epoch=0, epochs=args.epochs)
    drawn_train, drawn_train_labels = make_drawn(args.drawn, 1)
    drawn_test, drawn_test_labels = make_drawn(60, 2)
    train_images, train_labels = real["train_images"] + drawn_train, real["train_labels"] + drawn_train_labels
    print(f"photographs: {len(real['train_images'])} train, {len(real['test_images'])} test; drawn: {len(drawn_train)} train, {len(drawn_test)} test", flush=True)
    model = learned.build_model(pretrained=True)
    weights = torch.tensor([1.0, 1.5, 2.5])
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, ignore_index=IGNORE)
    optimiser = torch.optim.AdamW(model.parameters(), lr=6e-4, weight_decay=1e-4)
    batch = 8
    per_epoch = args.steps or max(10, len(train_images) // batch)
    total_steps = per_epoch * args.epochs
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=6e-4, total_steps=total_steps, pct_start=0.15)
    data = Batches(train_images, train_labels, random.Random(SEED))
    history, step = [], 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = []
        for _ in range(per_epoch):
            x, y = data.batch(batch)
            optimiser.zero_grad()
            loss = loss_fn(model(x)["out"], y)
            loss.backward()
            optimiser.step()
            schedule.step()
            running.append(float(loss.detach()))
            step += 1
            if step % 10 == 0:
                elapsed = time.time() - started
                write_progress(stage="training", epoch=epoch, epochs=args.epochs, step=step, steps=total_steps, loss=float(np.mean(running[-20:])), minutes_left=round(elapsed / step * (total_steps - step) / 60, 1))
        history.append(float(np.mean(running)))
        print(f"epoch {epoch}/{args.epochs}: loss {history[-1]:.3f}  ({(time.time() - started) / 60:.1f} min)", flush=True)
        learned.MODEL_FOLDER.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), learned.WEIGHTS)
    write_progress(stage="testing", epoch=args.epochs, epochs=args.epochs)
    learned._cache.clear()
    model.eval()
    photos = evaluate(real["test_images"], real["test_labels"]) if real["test_images"] else None
    drawn = evaluate(drawn_test, drawn_test_labels)
    levels = level_error(3)
    report = {"trained": datetime.now().strftime("%Y-%m-%d %H:%M"), "minutes": round((time.time() - started) / 60, 1), "epochs": args.epochs, "steps_per_epoch": per_epoch, "loss_per_epoch": history,
              "data": {"real_train": len(real["train_images"]), "real_test": len(real["test_images"]), "drawn_train": len(drawn_train), "drawn_test": len(drawn_test),
                       "source": "LabPics v1 (Sagi Eppel, Zenodo 3697452, MIT licence) plus drawn bench scenes"},
              "iou_on_unseen_photographs": photos, "iou_on_unseen_drawn_scenes": drawn, "level_reading_on_drawn_scenes": levels,
              "network": "LRASPP MobileNetV3-Large, 3 classes (background, vessel, contents), started from weights learned on everyday photographs", "torch": torch.__version__,
              "note": "IoU is the overlap of the network's mask with the hand-drawn one: 1.0 is perfect. Level reading is the contents' height over the vessel's height, in percentage points of error."}
    learned.REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    write_progress(stage="done", epoch=args.epochs, epochs=args.epochs, minutes=report["minutes"])
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
