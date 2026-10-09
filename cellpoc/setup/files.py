"""Reading and saving setup files safely.

Safe means: YAML is read with the safe reader only; file names inside a setup are relative, inside the project and
never contain '..'; setups are saved only into the project's setups/ folder; a saved setup records when it was saved,
which program version saved it and a fingerprint of its content (never a personal name); the file has no byte-order
mark and Unix line endings.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .messages import make_problem
from .problems import Problem
from .versions import DEFAULT_SUPPORT, PROGRAM_VERSION, FormatSupport

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_EXAMPLES = Path(__file__).resolve().parents[1] / "formats" / "examples"
MAX_BYTES = 1_000_000
SETUPS_FOLDER = "setups"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")


class SetupFileError(Exception):
    """Raised with a plain-English message when a setup cannot be saved."""


def path_is_safe(reference) -> bool:
    """A file name inside a setup: relative, no drive letter, no network path, no '..', no odd characters."""
    if not isinstance(reference, str) or not reference.strip():
        return False
    if re.match(r"^[A-Za-z]:", reference) or reference.startswith(("/", "\\")) or any(c in reference for c in ':*?"<>|'):
        return False
    return ".." not in re.split(r"[/\\]", reference)


def resolve_reference(reference, base_dir: Path | None, root: Path = PROJECT_ROOT) -> Path | None:
    """Find a referenced file: relative to the project folder, then next to the setup file (both must stay inside the project),
    then in the bundled examples folder (so a saved setup still finds the example layout and example table)."""
    if not path_is_safe(reference):
        return None
    for base, limit in ((root, root), (base_dir, root), (PACKAGE_EXAMPLES, PACKAGE_EXAMPLES)):
        if base is None:
            continue
        candidate = (Path(base) / reference).resolve()
        if candidate.is_relative_to(Path(limit).resolve()) and candidate.is_file():
            return candidate
    return None


def _plain(value):
    """The same content with every key written as text, so odd keys (numbers, mixed kinds) can never stop the fingerprint."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def fingerprint(setup: dict) -> str:
    """A fingerprint of the setup's content, ignoring the 'saved' details (which contain the fingerprint itself)."""
    content = _plain({k: v for k, v in setup.items() if k != "saved"})
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class LoadResult:
    setup: dict | None
    problems: list[Problem] = field(default_factory=list)
    path: Path | None = None

    @property
    def base_dir(self) -> Path | None:
        return self.path.parent if self.path else None


def load_setup(path: Path | str, root: Path = PROJECT_ROOT, formats: FormatSupport = DEFAULT_SUPPORT) -> LoadResult:
    """Read a setup file. Problems with the file itself come back as problems, never as a crash."""
    path = Path(path)
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            return LoadResult(None, [make_problem("F03", "", ("format_version",), None, mb=f"{size / 1_000_000:.1f}")], path)
        raw = path.read_bytes()
    except OSError:
        return LoadResult(None, [make_problem("F01", "", ("format_version",), None)], path)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return LoadResult(None, [make_problem("F01", "", ("format_version",), None)], path)
    try:
        setup = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        return LoadResult(None, [make_problem("F02", "", ("format_version",), None,
                                              line=(mark.line + 1) if mark else "?", column=(mark.column + 1) if mark else "?")], path)
    return LoadResult(setup, [], path)


def _saved_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise SetupFileError("Save as: use lowercase letters, digits, '-' and '_' only, starting with a letter or digit, "
                             "up to 60 characters (for example 'tablet-study-1'). The file is saved in the setups folder.")
    return name


def save_setup(setup: dict, name: str, root: Path = PROJECT_ROOT, now: datetime | None = None,
               problems: list[Problem] | None = None) -> Path:
    """Save a setup into <root>/setups/<name>.yaml, adding when, with which program version, and the fingerprint.

    `problems` is the validator's verdict on this setup; saving is refused while it contains an error.
    """
    name = _saved_name(name)
    if problems is None:
        raise SetupFileError("Save: the setup must be checked first. Run the check on the Review screen, then save.")
    if any(p.level == "error" for p in problems):
        raise SetupFileError("Save: the setup still has errors. Fix the errors on the Review screen first (warnings do not block saving).")
    folder = Path(root) / SETUPS_FOLDER
    target = (folder / f"{name}.yaml").resolve()
    if target.parent != folder.resolve():
        raise SetupFileError("Save: files are only saved in the setups folder.")
    content = copy.deepcopy(setup)
    content.pop("saved", None)
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    content["saved"] = {"saved_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"), "program_version": PROGRAM_VERSION,
                        "content_sha256": fingerprint(content)}
    folder.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(content, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    target.write_bytes(text.encode("utf-8"))      # no byte-order mark, Unix line endings
    return target


def list_layouts(root: Path = PROJECT_ROOT) -> list[Path]:
    """The layout files the setup app offers: the bundled example(s) and any in the project's layouts/ folder."""
    found = sorted(PACKAGE_EXAMPLES.glob("*layout*.json"))
    folder = Path(root) / "layouts"
    if folder.is_dir():
        found += sorted(folder.glob("*.json"))
    return found


def example_setup_path() -> Path:
    return PACKAGE_EXAMPLES / "setup_example.yaml"
