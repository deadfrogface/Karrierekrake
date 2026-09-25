"""Process-group peak measurement.

Windows: one Job Object, process created suspended, assigned, then resumed.
Breakaway is not granted. Peak bytes are ``PeakJobMemoryUsed``.

Other platforms: a new session/process group plus sampled VmRSS of the tree.
That scaffold proves containment of ordinary children. It is not ship evidence
for the i3 laptop. A Windows Job Object run on the physical machine is.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.hardware_peak_gate import (
    HARD_PEAK_RSS_BYTES,
    evaluate_peak,
    verdict_for_run,
)
from devops.win_job_object import (
    PROCESS_INFORMATION,
    STARTUPINFOW,
    assign_then_resume,
    create_process_flags,
    extended_limit_info,
    kernel32,
)

_ATTEST_ENV = "KARRIEREKRAKE_PHYSICAL_I3_8GB"


@dataclass
class ContainedProcess:
    """One root process plus every child that stays in its job or process group."""

    pid: int
    platform: str
    method: str
    popen: subprocess.Popen | None = None
    pgid: int | None = None
    _peak: int = 0
    _last_sample: float = 0.0
    _closed: bool = False
    _win_job: object | None = None
    _win_process: object | None = None
    _win_thread: object | None = None
    enforce_memory_bytes: int | None = None
    breakaway_flags_set: bool = False
    notes: list[str] = field(default_factory=list)

    def poll(self) -> int | None:
        self._sample_peak()
        if self.popen is not None:
            return self.popen.poll()
        return self._win_exit_code()

    def wait(self, timeout: float | None = None) -> int:
        if self.popen is not None:
            return int(self.popen.wait(timeout=timeout))
        return self._win_wait(timeout)

    def peak_bytes(self) -> int:
        self._sample_peak()
        return int(self._peak)

    def contains_pid(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if self.platform == "win32":
            return self._win_pid_in_job(pid)
        if self.pgid is None:
            return False
        try:
            return os.getpgid(pid) == self.pgid
        except ProcessLookupError:
            return False

    def terminate(self) -> None:
        if self.platform == "win32" and self._win_job:
            k = kernel32()
            k.TerminateJobObject(self._win_job, 1)
            return
        if self.pgid is None:
            if self.popen is not None and self.popen.poll() is None:
                self.popen.terminate()
            return
        try:
            os.killpg(self.pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if self.popen is not None and self.popen.poll() is not None:
                return
            time.sleep(0.05)
        try:
            os.killpg(self.pgid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def close(self) -> None:
        if self._closed:
            return
        self._sample_peak()
        self._closed = True
        if self.platform == "win32":
            k = kernel32()
            for handle in (self._win_thread, self._win_process, self._win_job):
                if handle:
                    k.CloseHandle(handle)
            self._win_thread = None
            self._win_process = None
            self._win_job = None
            return
        if self.popen is not None:
            try:
                self.popen.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

    def _sample_peak(self) -> None:
        now = time.monotonic()
        if now - self._last_sample < 0.05 and self._peak:
            return
        self._last_sample = now
        if self.platform == "win32":
            self._peak = max(self._peak, self._query_job_peak())
            return
        if self.popen is None:
            return
        total, _pids = _posix_tree_rss(self.popen.pid)
        self._peak = max(self._peak, total)

    def _query_job_peak(self) -> int:
        if not self._win_job:
            return 0
        from devops.win_job_object import (
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            JobObjectExtendedLimitInformation,
        )

        k = kernel32()
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        ok = k.QueryInformationJobObject(
            self._win_job,
            JobObjectExtendedLimitInformation,
            ctypes_byref(info),
            ctypes_sizeof(info),
            None,
        )
        if not ok:
            return self._peak
        return int(info.PeakJobMemoryUsed)

    def _win_exit_code(self) -> int | None:
        if not self._win_process:
            return None
        k = kernel32()
        import ctypes
        from ctypes import wintypes

        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(self._win_process, ctypes.byref(code)):
            return None
        if int(code.value) == 259:  # STILL_ACTIVE
            return None
        return int(code.value)

    def _win_wait(self, timeout: float | None) -> int:
        if not self._win_process:
            raise OSError("Windows process handle is closed")
        k = kernel32()
        ms = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        k.WaitForSingleObject(self._win_process, ms)
        code = self._win_exit_code()
        if code is None:
            raise subprocess.TimeoutExpired(cmd=str(self.pid), timeout=timeout)
        return code

    def _win_pid_in_job(self, pid: int) -> bool:
        if not self._win_job:
            return False
        import ctypes
        from ctypes import wintypes

        k = kernel32()
        handle = k.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            result = wintypes.BOOL()
            ok = k.IsProcessInJob(handle, self._win_job, ctypes.byref(result))
            return bool(ok and result.value)
        finally:
            k.CloseHandle(handle)


def ctypes_byref(obj):
    import ctypes

    return ctypes.byref(obj)


def ctypes_sizeof(obj) -> int:
    import ctypes

    return ctypes.sizeof(obj)


def launch_contained(
    argv: list[str],
    *,
    cwd: str | None = None,
    console: bool = False,
    enforce_memory_bytes: int | None = None,
) -> ContainedProcess:
    """Start ``argv`` inside one job (Windows) or one process group (elsewhere)."""
    if not argv:
        raise ValueError("argv must not be empty")
    if sys.platform == "win32":
        return _launch_windows(
            argv,
            cwd=cwd,
            console=console,
            enforce_memory_bytes=enforce_memory_bytes,
        )
    return _launch_posix(argv, cwd=cwd, enforce_memory_bytes=enforce_memory_bytes)


def _launch_posix(
    argv: list[str],
    *,
    cwd: str | None,
    enforce_memory_bytes: int | None,
) -> ContainedProcess:
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )
    notes = [
        "posix_process_group",
        "not_ship_evidence",
    ]
    if enforce_memory_bytes is not None:
        notes.append("enforce_limit_ignored_on_posix")
    return ContainedProcess(
        pid=int(proc.pid),
        platform=sys.platform,
        method="process_group_vmrss",
        popen=proc,
        pgid=int(proc.pid),
        enforce_memory_bytes=enforce_memory_bytes,
        breakaway_flags_set=False,
        notes=notes,
    )


def _launch_windows(
    argv: list[str],
    *,
    cwd: str | None,
    console: bool,
    enforce_memory_bytes: int | None,
) -> ContainedProcess:
    import ctypes
    import subprocess as sp

    k = kernel32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    info = extended_limit_info(enforce_memory_bytes=enforce_memory_bytes)
    if not k.SetInformationJobObject(
        job,
        9,  # JobObjectExtendedLimitInformation
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        err = ctypes.get_last_error()
        k.CloseHandle(job)
        raise OSError(err, "SetInformationJobObject failed")

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()
    cmdline = sp.list2cmdline(argv)
    buf = ctypes.create_unicode_buffer(cmdline)
    app_name = argv[0] if (os.path.sep in argv[0] or Path(argv[0]).exists()) else None
    flags = create_process_flags(console=console)
    ok = k.CreateProcessW(
        app_name,
        buf,
        None,
        None,
        False,
        flags,
        None,
        cwd,
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    if not ok:
        err = ctypes.get_last_error()
        k.CloseHandle(job)
        raise OSError(err, "CreateProcessW failed")
    try:
        assign_then_resume(k, job, pi.hProcess, pi.hThread)
    except OSError:
        k.TerminateProcess(pi.hProcess, 1)
        k.CloseHandle(pi.hThread)
        k.CloseHandle(pi.hProcess)
        k.CloseHandle(job)
        raise
    return ContainedProcess(
        pid=int(pi.dwProcessId),
        platform="win32",
        method="windows_job_object_peak_job_memory",
        _win_job=job,
        _win_process=pi.hProcess,
        _win_thread=pi.hThread,
        enforce_memory_bytes=enforce_memory_bytes,
        breakaway_flags_set=False,
        notes=["assigned_while_suspended", "breakaway_not_granted"],
    )


def _posix_tree_rss(root: int) -> tuple[int, list[int]]:
    parent_of: dict[int, int] = {}
    proc = Path("/proc")
    if not proc.is_dir():
        return _rss_bytes(root), [root]
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rparen = stat.rfind(")")
        if rparen < 0:
            continue
        rest = stat[rparen + 2 :].split()
        if len(rest) < 2:
            continue
        try:
            parent_of[pid] = int(rest[1])
        except ValueError:
            continue
    descendants: list[int] = []

    def walk(parent: int) -> None:
        for pid, ppid in parent_of.items():
            if ppid == parent and pid not in descendants:
                descendants.append(pid)
                walk(pid)

    walk(root)
    pids = [root, *descendants]
    return sum(_rss_bytes(pid) for pid in pids), pids


def _rss_bytes(pid: int) -> int:
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return 0


@dataclass
class PeakRunReport:
    peak_bytes: int
    limit_bytes: int
    hard_fail: bool
    exit_code: int | None
    platform: str
    method: str
    ship_evidence: bool
    breakaway_flags_set: bool
    contained_pids: list[int]
    notes: list[str]
    command: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def run_contained_until_exit(
    argv: list[str],
    *,
    timeout_s: float,
    cwd: str | None = None,
    console: bool = True,
    enforce_memory_bytes: int | None = None,
    attest_physical_i3: bool = False,
) -> PeakRunReport:
    """Run ``argv`` to completion and evaluate the hard peak gate."""
    proc = launch_contained(
        argv,
        cwd=cwd,
        console=console,
        enforce_memory_bytes=enforce_memory_bytes,
    )
    killed = False
    deadline = time.monotonic() + timeout_s
    exit_code: int | None = None
    try:
        while True:
            exit_code = proc.poll()
            if exit_code is not None:
                break
            if time.monotonic() >= deadline:
                killed = True
                proc.terminate()
                try:
                    exit_code = proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    exit_code = None
                break
            time.sleep(0.05)
        peak = proc.peak_bytes()
        verdict = verdict_for_run(
            peak,
            process_exit=exit_code,
            enforce_limit=enforce_memory_bytes is not None,
            killed_by_harness=killed,
        )
        ship = bool(
            attest_physical_i3
            and proc.method == "windows_job_object_peak_job_memory"
            and os.environ.get(_ATTEST_ENV) == "1"
        )
        notes = list(proc.notes)
        if killed:
            notes.append("harness_timeout")
        if attest_physical_i3 and not ship:
            notes.append("attest_refused_not_physical_windows_job")
        return PeakRunReport(
            peak_bytes=verdict.peak_bytes,
            limit_bytes=verdict.limit_bytes,
            hard_fail=verdict.hard_fail,
            exit_code=exit_code,
            platform=proc.platform,
            method=proc.method,
            ship_evidence=ship,
            breakaway_flags_set=proc.breakaway_flags_set,
            contained_pids=[proc.pid],
            notes=notes,
            command=list(argv),
        )
    finally:
        proc.close()


_SELF_TEST_SCRIPT = """
import os, subprocess, sys, time
out = sys.argv[1]
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
with open(out, "w", encoding="utf-8") as fh:
    fh.write(str(os.getpid()) + "\\n" + str(grandchild.pid) + "\\n")
    fh.flush()
time.sleep(60)
"""


def run_self_test(*, timeout_s: float = 20.0) -> dict:
    """Spawn a child and a grandchild and require both to stay contained.

    The peak of this smoke is checked against the hard gate. The result is
    never ship evidence.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="kk-peak-self-") as tmp:
        script = Path(tmp) / "leader.py"
        pidfile = Path(tmp) / "pids.txt"
        script.write_text(_SELF_TEST_SCRIPT, encoding="utf-8")
        proc = launch_contained(
            [sys.executable, str(script), str(pidfile)],
            console=False,
        )
        try:
            deadline = time.monotonic() + timeout_s
            child_pid = grand_pid = None
            while time.monotonic() < deadline:
                if pidfile.is_file():
                    lines = [ln.strip() for ln in pidfile.read_text(encoding="utf-8").splitlines() if ln.strip()]
                    if len(lines) >= 2 and lines[0].isdigit() and lines[1].isdigit():
                        child_pid = int(lines[0])
                        grand_pid = int(lines[1])
                        if proc.contains_pid(child_pid) and proc.contains_pid(grand_pid):
                            break
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            contained = (
                child_pid is not None
                and grand_pid is not None
                and proc.contains_pid(child_pid)
                and proc.contains_pid(grand_pid)
            )
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            peak = proc.peak_bytes()
            verdict = evaluate_peak(peak)
            report = {
                "contained": contained,
                "child_pid": child_pid,
                "grandchild_pid": grand_pid,
                "peak_bytes": verdict.peak_bytes,
                "limit_bytes": verdict.limit_bytes,
                "hard_fail": verdict.hard_fail or not contained,
                "platform": proc.platform,
                "method": proc.method,
                "ship_evidence": False,
                "breakaway_flags_set": proc.breakaway_flags_set,
                "notes": list(proc.notes) + ["self_test_not_ship_evidence"],
            }
            return report
        finally:
            try:
                proc.terminate()
            except OSError:
                pass
            proc.close()


def report_exit_code(report: PeakRunReport | dict) -> int:
    hard_fail = report.hard_fail if isinstance(report, PeakRunReport) else bool(report.get("hard_fail"))
    if hard_fail:
        return 2
    return 0


def write_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
