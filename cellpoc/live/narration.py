"""The words the guided demo speaks, read out of the console's script, so the voice recordings are made from exactly what the page says.

The recordings are looked up by a short fingerprint of the sentence (`hash_text`, the same arithmetic as in the page), so a sentence that is
reworded simply has no recording and the page falls back to the computer's own voice until the recordings are made again.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).with_name("console_part3.js")
FINISH = re.compile(r"done: \(\) => '([^']*)' \+ \(S\.summary \? S\.summary\.headline \+ '([^']*)' \+ S\.summary\.attempts_text \+ '([^']*)' : '([^']*)'\) \+ '([^']*)'")
STRING = r"'((?:[^'\\]|\\.)*)'"


class NarrationError(Exception):
    pass


def hash_text(text: str) -> str:
    """FNV-1a over the sentence's UTF-16 code units, as 8 hex digits: the same as `hashText` in the console's script."""
    h = 2166136261
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h = ((h ^ (data[i] | (data[i + 1] << 8))) * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


def _unquote(s: str) -> str:
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def _steps_source() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.find("const DSTEPS = [")
    end = source.find("\n];", start)
    if start < 0 or end < 0:
        raise NarrationError("The console's script no longer has the guided demo's list of steps where the voice maker looks for it.")
    return source[start:end]


def lines(summary: dict | None = None) -> list[str]:
    """Every sentence the demo speaks, in order: for each step the one said while the simulation runs and the one said when it has paused.
    `summary` is the finished run's {'headline', 'attempts_text'} (the last step reads it out); without it that step says its plain wording."""
    body = _steps_source()
    blocks = re.split(r"\n  \{ title:", body)[1:]
    if len(blocks) < 5:
        raise NarrationError("The guided demo's steps could not be read from the console's script.")
    spoken: list[str] = []
    for block in blocks:
        block = "title:" + block

        def field(name: str):
            found = re.search(rf"(?<![A-Za-z]){name}: {STRING}", block)
            return _unquote(found.group(1)) if found else None

        title, text, done_title, done = field("title"), field("text"), field("doneTitle"), field("done")
        if done is None:
            finish = FINISH.search(block)
            if finish:
                p1, p2, p3, p4, p5 = (_unquote(x) for x in finish.groups())
                done = p1 + (summary["headline"] + p2 + summary["attempts_text"] + p3 if summary else p4) + p5
        if title is None or (text is None and done is None):
            raise NarrationError("A step of the guided demo could not be read from the console's script.")
        if "stopWhen:" in block:
            spoken.append(f"{title}. {text}")
            spoken.append(f"{done_title or title}. {done if done is not None else text}")
        else:
            spoken.append(f"{done_title or title}. {done if done is not None else text}")
    return spoken
