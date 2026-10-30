"""Starts, watches and stops the live program for the unified app, and keeps it on this computer only.

What it does, and the limits that are checked by checks/architecture.py and by check_app.bat:
- It starts exactly one program: `python -B -m cellpoc.live.embedded_main --port N` (a list, never a text line, N a checked whole number), inside a Windows job object set to kill everything in it when its owner
  (the app) ends for ANY reason, so no live program can be left behind. It refuses to start without a job object.
- It then reads what the computer is really listening on for that port. Anything but 127.0.0.1 (or ::1) means the program is killed at once and the start is refused; the same read is repeated on every status
  refresh, so a program that opens another address later is caught too. The listening program must also be inside the job object, or it is killed and refused.
- It refuses to start while the port is held by something it did not start, and never adopts or kills such a program.
- It only ever runs three commands: the live program, `taskkill /PID N /T /F` (to stop what it started) and `netstat -ano` (to read the listening addresses). No shell, no network library, no file is written.
Windows only, like the project's launchers.
"""
from __future__ import annotations

import atexit
import collections
import ctypes
import ctypes.wintypes as wintypes
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8514                                    # the unified app's live view; the stand-alone page (run_live.bat) keeps 8504
READY_SECONDS = 60
CONNECTED_READY_SECONDS = 300                  # the connected loop reads the data and judges the models before it listens (about a minute the first time)
SCENARIOS = ("baseline", "new_supplier", "period_shift", "unpredictable_dissolution")           # the only scenario names the live command may carry (the connected loop's development scenarios)
LOOPBACK = ("127.0.0.1:", "[::1]:")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_KILL_ON_CLOSE = 0x2000
JOB_EXTENDED_LIMITS = 9


def live_command(port: int, connected: str | None = None) -> list[str]:
    """The one program this part starts: the live run, on the given port, without opening a browser; with `--connected NAME` added only when NAME is one of the four constant scenario names."""
    command = [sys.executable, "-B", "-m", "cellpoc.live.embedded_main", "--port", str(port)]
    if connected in SCENARIOS:
        command += ["--connected", connected]
    return command


def listeners(port: int) -> list[tuple[str, int]]:
    """(address:port, owning process) for every socket the computer is listening on at this port, as the operating system reports it (not what any file says)."""
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        cols = line.split()
        if "LISTENING" in line and len(cols) >= 5 and cols[1].endswith(f":{port}") and cols[-1].isdigit():
            found.append((cols[1], int(cols[-1])))
    return sorted(set(found))


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


# ---- the job object: Windows kills everything in it when its owner ends
class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _kernel():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype, k.CreateJobObjectW.argtypes = wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]
    k.SetInformationJobObject.restype, k.SetInformationJobObject.argtypes = wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.AssignProcessToJobObject.restype, k.AssignProcessToJobObject.argtypes = wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]
    k.OpenProcess.restype, k.OpenProcess.argtypes = wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.IsProcessInJob.restype, k.IsProcessInJob.argtypes = wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    k.CloseHandle.restype, k.CloseHandle.argtypes = wintypes.BOOL, [wintypes.HANDLE]
    return k


def make_job():
    """A job object that kills everything inside it when its last handle closes (that is, when this app's process ends, however it ends). None if Windows would not make one."""
    try:
        k = _kernel()
        job = k.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = JOB_KILL_ON_CLOSE
        if not k.SetInformationJobObject(job, JOB_EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)):
            k.CloseHandle(job)
            return None
        return job
    except (OSError, AttributeError):
        return None


def in_job(job, pid: int) -> bool:
    k = _kernel()
    handle = k.OpenProcess(0x1000, False, pid)                       # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        inside = wintypes.BOOL(False)
        return bool(k.IsProcessInJob(handle, job, ctypes.byref(inside))) and bool(inside.value)
    finally:
        k.CloseHandle(handle)


@dataclass
class Status:
    state: str                                  # not running, starting, running, stopped, refused
    text: str                                   # one plain sentence for the page
    address: str = ""                           # where the live view answers (only while running)
    lines: list[str] = field(default_factory=list)      # the last lines the live program printed


class Supervisor:
    def __init__(self, port: int = PORT, command_for=None, connected: str | None = None):
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise ValueError("The live view's port must be a whole number from 1024 to 65535.")
        if connected is not None and connected not in SCENARIOS:
            raise ValueError("The connected scenario must be one of: " + ", ".join(SCENARIOS) + ".")
        self.port = port
        self.connected = connected
        self.ready_seconds = CONNECTED_READY_SECONDS if connected else READY_SECONDS
        self.command_for = command_for or (lambda number: live_command(number, connected))
        self.lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self.job = None
        self.output: collections.deque[str] = collections.deque(maxlen=30)
        self.state, self.text = "not running", "The live view is not running."
        self.checked_at = 0.0
        atexit.register(self.stop)

    # ---- starting
    def start(self) -> Status:
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                return self.status()                                    # already running: nothing new is started
            held = listeners(self.port)
            if held:
                return self._set("refused", f"Port {self.port} is already in use by a program this app did not start ({held[0][0]}), so the live view was not started and that program was left alone. Close it, then try again.")
            job = make_job()
            if job is None:
                return self._set("refused", "Windows would not make the safety container that guarantees the live view cannot be left running when this app closes, so it was not started.")
            self.output.clear()
            self.proc = subprocess.Popen(self.command_for(self.port), cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
            self.job = job
            _kernel().AssignProcessToJobObject(job, int(self.proc._handle))
            threading.Thread(target=self._read, args=(self.proc,), daemon=True, name="live-supervisor-reader").start()
            self.state, self.text = "starting", "Starting the live view (a few seconds)..."
            deadline = time.time() + self.ready_seconds
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    return self._ended()
                if listeners(self.port):
                    break
                time.sleep(0.4)
            else:
                self._kill()
                return self._set("stopped", f"The live view did not start listening within {self.ready_seconds} seconds, so it was stopped.")
            return self.status(force=True)

    def _read(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            self.output.append(line.rstrip())

    # ---- watching
    def status(self, force: bool = False) -> Status:
        with self.lock:
            if self.proc is None:
                return Status(self.state, self.text, lines=list(self.output))
            if self.proc.poll() is not None:
                return self._ended()
            if self.state == "refused":
                return Status(self.state, self.text, lines=list(self.output))
            if force or time.time() - self.checked_at > 1.5:               # the address read is repeated while it runs, not only at the start
                self.checked_at = time.time()
                seen = listeners(self.port)
                outside = [a for a, _ in seen if not a.startswith(LOOPBACK)]
                unmanaged = [pid for _, pid in seen if not in_job(self.job, pid)]
                if outside:
                    self._kill()
                    return self._set("refused", f"The live view listened on an address other than this computer's ({outside[0]}), so it was stopped. Nothing is left running.")
                if unmanaged:
                    self._kill()
                    return self._set("refused", "The live view could not be placed inside the safety container, so it was stopped. Nothing is left running.")
                if seen:
                    self.state, self.text = "running", f"The live view is running on {HOST}:{self.port}, this computer only."
            return Status(self.state, self.text, address=f"http://{HOST}:{self.port}/" if self.state == "running" else "", lines=list(self.output))

    def _ended(self) -> Status:
        """The program is gone. If this app ended it (a stop, a refusal) that was already reported; otherwise it ended by itself and the page says how."""
        if self.state in ("refused", "stopped"):
            return Status(self.state, self.text, lines=list(self.output))
        last = " ".join(list(self.output)[-2:])
        return self._set("stopped", f"The live view stopped on its own (exit code {self.proc.returncode})." + (f" It said: {last}" if last else ""))

    def _set(self, state: str, text: str) -> Status:
        self.state, self.text = state, text
        return Status(state, text, lines=list(self.output))

    # ---- stopping
    def _kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            kill_tree(self.proc.pid)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for _ in range(20):                                              # the port closes a moment after the program does
            if not listeners(self.port):
                break
            time.sleep(0.25)
        if self.job is not None:
            _kernel().CloseHandle(self.job)                              # closing the container also kills anything left in it
            self.job = None

    def stop(self) -> Status:
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                return Status(self.state, "The live view is not running; there was nothing to stop.", lines=list(self.output))
            self._kill()
            return self._set("stopped", "The live view was stopped. Nothing is left running.")


_shared: Supervisor | None = None


def shared(port: int = PORT, connected: str | None = None) -> Supervisor:
    """The one supervisor of this app's process (kept in this module, so a page reload finds the same live program). The port and the connected scenario are used when it is first made."""
    global _shared
    if _shared is None:
        _shared = Supervisor(port, connected=connected)
    return _shared
