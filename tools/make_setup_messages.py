r"""Writes docs/setup_messages.md: each setup rule, its test and its message.

Run:  .venv\Scripts\python.exe tools\make_setup_messages.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks.setup_messages_doc import write_doc  # noqa: E402

if __name__ == "__main__":
    print("Wrote", write_doc())
