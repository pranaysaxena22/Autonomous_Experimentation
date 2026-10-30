"""The live-run supervisor (Stage C of the unified app): the ONLY code that starts, watches and stops the live program for the unified app.

It imports no other part of the project; it knows one fixed command (the live program on one port), reads the addresses the computer is really listening on, and kills what it started. See docs/stage_c_design_note.md.
"""
from .supervisor import HOST, PORT, SCENARIOS, Status, Supervisor, live_command, shared

__all__ = ["HOST", "PORT", "SCENARIOS", "Status", "Supervisor", "live_command", "shared"]
