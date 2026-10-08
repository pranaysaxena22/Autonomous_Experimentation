"""Saves a run record to disk and reads it back. The disk file is plain JSON."""
from __future__ import annotations

import json
import types
import typing
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

from ..contracts import RunRecord

RECORD_NAME = "record.json"


def save(record: RunRecord, folder: Path | str) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / RECORD_NAME
    path.write_text(json.dumps(asdict(record), indent=1), encoding="utf-8")
    return path


def load(folder_or_file: Path | str) -> RunRecord:
    path = Path(folder_or_file)
    if path.is_dir():
        path = path / RECORD_NAME
    return _build(RunRecord, json.loads(path.read_text(encoding="utf-8")))


def _build(tp: Any, value: Any) -> Any:
    """Turn parsed JSON back into the dataclasses it was saved from."""
    origin = typing.get_origin(tp)
    if is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        return tp(**{f.name: _build(hints[f.name], value[f.name]) for f in fields(tp)})
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        inner = [a for a in typing.get_args(tp) if a is not type(None)][0]
        return _build(inner, value)
    if origin is list:
        (item,) = typing.get_args(tp)
        return [_build(item, v) for v in value]
    return value
