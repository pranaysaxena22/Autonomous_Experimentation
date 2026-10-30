r"""Writes docs/ingest_messages.md: each data reader message, its test and the message the test produced.

Run:  .venv\Scripts\python.exe tools\make_ingest_messages.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks.ingest_messages_doc import write_doc  # noqa: E402

if __name__ == "__main__":
    print("Wrote", write_doc())
