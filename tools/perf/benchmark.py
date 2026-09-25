#!/usr/bin/env python3
"""Manual Karrierekrake performance benchmark.

Not a unit test. Not a CI check. Do not add this module to pytest paths,
GitHub Actions, or the ``unit-tests`` job. Run it by hand:

    .venv/bin/python tools/perf/benchmark.py --runs 5 --out /tmp/kk-perf

LLM parsing stays off (``KARRIEREKRAKE_LOCAL_LLM_CV_PARSING=0`` and
``guenther_enabled=False``). Numbers are for this machine only.

The process-group RSS sampler aborts a worker if the group exceeds
3_200_000_000 bytes so the run stays under the 3_300_000_000-byte gate.
That abort is a safety rail for the benchmark process, not a product limit
derived from these VM numbers.

RSS comes from ``/proc`` on Linux (limit metric: sum of VmRSS; VmHWM is
named and is not the limit). On Windows the limit metric is
``PeakJobMemoryUsed``, the same Job Object field as the peak gate.
If neither source can be read, the script exits with an error. A single
unread sample is ``None`` (shown as ``n/a``), never ``0``. A run that
finishes with no sample at all exits with status 3.

The abort kills the whole tree: ``os.killpg`` on Linux, ``TerminateJobObject``
on Windows.
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import json
import os
import pstats
import re
import signal
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
PEAK_ABORT_BYTES = 3_200_000_000
PEAK_GATE_BYTES = 3_300_000_000
DEFAULT_RUNS = 5
# Parent samples are not a continuous trace. These intervals are written into the report.
WORKER_SAMPLE_INTERVAL_S = 0.05
IMPORTTIME_SAMPLE_INTERVAL_S = 0.02
NO_SAMPLE_EXIT = 3

# Sections the parent runs. ``importtime`` is a subprocess of the parent
# (``python -X importtime``), not the worker dispatcher.
SECTIONS = ("importtime", "startup", "cv", "match", "ui")


def _ensure_root() -> None:
    os.chdir(ROOT)
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


class MemoryReadError(RuntimeError):
    """Neither ``/proc`` nor psutil can provide a process RSS."""


class NoRssSampleError(RuntimeError):
    """The run ended without a single successful RSS sample."""


def _proc_available() -> bool:
    return Path("/proc/self/status").is_file()


def _load_psutil():
    """Return the psutil module, or None when it is not installed."""
    try:
        import psutil
    except ImportError:
        return None
    return psutil


def _memory_backend() -> str:
    """``proc`` on Linux with /proc, otherwise ``psutil``.

    Raises MemoryReadError when both are missing. Callers must not substitute 0.
    """
    if _proc_available():
        return "proc"
    if _load_psutil() is not None:
        return "psutil"
    raise MemoryReadError(
        "RSS nicht lesbar: weder /proc noch psutil. "
        "Unter Windows psutil installieren (optionale Abhängigkeit, siehe tools/perf/README.md)."
    )


def _ensure_memory_reader() -> None:
    try:
        _memory_backend()
    except MemoryReadError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc


def _fmt_bytes(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _rss_delta(after: int | None, before: int | None) -> int | None:
    if after is None or before is None:
        return None
    return after - before


def _rss_pair_proc(pid: int) -> tuple[int | None, int | None]:
    """(VmRSS, VmHWM) in bytes. None for a field or a process that was not read."""
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return None, None
    rss: int | None = None
    hwm: int | None = None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            rss = int(line.split()[1]) * 1024
        elif line.startswith("VmHWM:"):
            hwm = int(line.split()[1]) * 1024
    return rss, hwm


def _peak_from_memory_info(info: Any) -> int | None:
    """Windows high-water mark: peak_wset, else peak_pagefile. Absent → None."""
    for name in ("peak_wset", "peak_pagefile"):
        value = getattr(info, name, None)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _rss_pair_psutil(pid: int) -> tuple[int | None, int | None]:
    psutil = _load_psutil()
    if psutil is None:
        raise MemoryReadError(
            "RSS nicht lesbar: psutil fehlt und /proc ist nicht verfügbar."
        )
    try:
        info = psutil.Process(pid).memory_info()
    except Exception:
        return None, None
    rss = getattr(info, "rss", None)
    if not isinstance(rss, int):
        rss = None
    return rss, _peak_from_memory_info(info)


def _rss_pair(pid: int | None = None) -> tuple[int | None, int | None]:
    """Return (current RSS, peak) in bytes for ``pid`` (default: self).

    Peak is VmHWM on Linux. On Windows it is ``peak_wset`` or, if that field
    is missing, ``peak_pagefile``. Unread values are None, never 0.
    """
    target = pid or os.getpid()
    if _memory_backend() == "proc":
        return _rss_pair_proc(target)
    return _rss_pair_psutil(target)


def _group_rss_proc(pgid: int) -> int | None:
    """Sum VmRSS of every live process in ``pgid``. None if none were read."""
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    total = 0
    saw = False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
            rparen = stat.rfind(")")
            fields = stat[rparen + 2 :].split()
            # state, ppid, pgrp — pgrp is index 2
            if int(fields[2]) != pgid:
                continue
            rss, _hwm = _rss_pair_proc(int(entry.name))
        except (OSError, IndexError, ValueError):
            continue
        if rss is None:
            continue
        saw = True
        total += rss
    return total if saw else None


def _group_rss_psutil(root_pid: int) -> int | None:
    """Sum RSS of ``root_pid`` and its children (recursive). None if unread."""
    psutil = _load_psutil()
    if psutil is None:
        raise MemoryReadError(
            "RSS nicht lesbar: psutil fehlt und /proc ist nicht verfügbar."
        )
    try:
        root = psutil.Process(root_pid)
    except Exception:
        return None
    procs = [root]
    try:
        procs.extend(root.children(recursive=True))
    except Exception:
        pass
    total = 0
    saw = False
    for proc in procs:
        try:
            info = proc.memory_info()
        except Exception:
            continue
        rss = getattr(info, "rss", None)
        if not isinstance(rss, int):
            continue
        saw = True
        total += rss
    return total if saw else None


def _group_rss(root_pid: int, pgid: int | None = None) -> int | None:
    """Process-group RSS in bytes.

    Linux uses ``/proc`` and ``pgid``. Every other platform sums the psutil
    process tree. None means the sample was not read — callers must not treat
    that as 0, and must not skip the peak abort because of it.
    """
    if _memory_backend() == "proc" and pgid is not None:
        return _group_rss_proc(pgid)
    return _group_rss_psutil(root_pid)


def _note_rss_sample(peak: int | None, sample: int | None) -> tuple[int | None, bool]:
    """Fold one group sample into the running peak.

    An unread sample (None) leaves the peak unchanged and does not abort.
    It is never stored as 0. A successful read at or above the abort line trips.
    """
    if sample is None:
        return peak, False
    new_peak = sample if peak is None else max(peak, sample)
    return new_peak, new_peak >= PEAK_ABORT_BYTES


def _process_group_id(pid: int) -> int | None:
    getpgid = getattr(os, "getpgid", None)
    if getpgid is None:
        return None
    try:
        return int(getpgid(pid))
    except OSError:
        return None


def _limit_metric_fields() -> dict[str, Any]:
    """Which number is compared with the abort line.

    Windows matches the #69 peak gate: ``PeakJobMemoryUsed`` on the job object
    (commit charge of the whole job), not the working set and not
    ``PeakProcessMemoryUsed``. Linux compares a sampled sum of ``VmRSS``.
    ``VmHWM`` is the per-process high-water mark and is not the limit metric.
    """
    if sys.platform == "win32":
        return {
            "limit_metric": "PeakJobMemoryUsed",
            "process_high_water_metric": "PeakJobMemoryUsed",
            "limit_metric_note": (
                "Stichprobe von JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakJobMemoryUsed. "
                "Dieselbe Kennzahl wie das Peak-Gate (Commit-High-Water der Job-Prozessgruppe). "
                "Nicht Working Set und nicht PeakProcessMemoryUsed."
            ),
        }
    return {
        "limit_metric": "VmRSS",
        "process_high_water_metric": "VmHWM",
        "limit_metric_note": (
            "Stichprobe. Gegen die Grenze läuft die Summe der VmRSS der Prozessgruppe. "
            "VmHWM ist der High-Water-Mark des Einzelprozesses und läuft nicht gegen die Grenze."
        ),
    }


def _memory_accounting(interval_s: float) -> dict[str, Any]:
    return {
        "peak_is_sampled": True,
        "sample_interval_ms": int(round(interval_s * 1000)),
        "limit_bytes": PEAK_ABORT_BYTES,
        "gate_bytes": PEAK_GATE_BYTES,
        **_limit_metric_fields(),
    }


def _query_peak_job_memory(job: object) -> int | None:
    """Read ``PeakJobMemoryUsed``. None when the query itself fails."""
    import ctypes

    from devops.win_job_object import (
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JobObjectExtendedLimitInformation,
        kernel32,
    )

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    ok = kernel32().QueryInformationJobObject(
        job,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
        None,
    )
    if not ok:
        return None
    return int(info.PeakJobMemoryUsed)


def _sample_against_limit(proc: Any, pgid: int | None) -> int | None:
    """Bytes compared with ``PEAK_ABORT_BYTES``. None if this sample was not read."""
    if sys.platform == "win32":
        job = getattr(proc, "job", None)
        if job is None:
            return None
        return _query_peak_job_memory(job)
    return _group_rss(proc.pid, pgid)


def _posix_killpg(pgid: int | None) -> bool:
    """SIGKILL the process group. True when that was the kill method."""
    if pgid is None or not hasattr(os, "killpg"):
        return False
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return True


def _kill_psutil_tree(root_pid: int) -> None:
    """Kill every descendant, then the root. Used when there is no job object."""
    psutil = _load_psutil()
    if psutil is None:
        raise MemoryReadError(
            "Prozessbaum nicht beendbar: psutil fehlt und killpg ist nicht verfügbar."
        )
    try:
        root = psutil.Process(root_pid)
    except Exception:
        return
    try:
        children = root.children(recursive=True)
    except Exception:
        children = []
    for child in children:
        try:
            child.kill()
        except Exception:
            continue
    try:
        root.kill()
    except Exception:
        return


def _terminate_windows_job(job: object) -> None:
    from devops.win_job_object import kernel32

    kernel32().TerminateJobObject(job, 1)


def _kill_process_tree(proc: Any, pgid: int | None) -> None:
    """Kill the benchmark child and every descendant.

    Linux: the child is started with ``start_new_session=True``, so
    ``os.killpg`` reaches the grandchild that stays in that group.
    Windows: ``TerminateJobObject`` when the #69-style job is attached
    (``KILL_ON_JOB_CLOSE`` is set on that job). Otherwise psutil kills
    ``children(recursive=True)`` and then the root.
    """
    job = getattr(proc, "job", None)
    if job is not None:
        _terminate_windows_job(job)
        return
    if _posix_killpg(pgid):
        return
    pid = getattr(proc, "pid", None)
    if isinstance(pid, int):
        _kill_psutil_tree(pid)


def _watch_process_rss(proc: Any, interval: float) -> tuple[int | None, bool]:
    """Sample the limit metric until ``proc`` exits.

    A trip kills the whole tree. If the process ends and every sample was
    unread, raise ``NoRssSampleError`` instead of reporting n/a.
    """
    peak: int | None = None
    aborted = False
    saw_sample = False
    pgid = _process_group_id(proc.pid)
    while True:
        sample = _sample_against_limit(proc, pgid)
        if sample is not None:
            saw_sample = True
        peak, trip = _note_rss_sample(peak, sample)
        if trip:
            aborted = True
            _kill_process_tree(proc, pgid)
            break
        if proc.poll() is not None:
            break
        time.sleep(interval)
    if not saw_sample:
        raise NoRssSampleError(
            "Kein RSS-Messwert gelesen: alle Stichproben waren leer "
            "(zum Beispiel AccessDenied). Der Lauf endet mit Fehler, nicht mit n/a."
        )
    return peak, aborted


class _BenchmarkProcess:
    """Popen plus the Windows job handle used for PeakJobMemoryUsed and kill."""

    def __init__(self, popen: subprocess.Popen, job: object | None = None) -> None:
        self._popen = popen
        self.job = job
        self.pid = int(popen.pid)

    def poll(self) -> int | None:
        return self._popen.poll()

    def communicate(self) -> tuple[str, str]:
        out, err = self._popen.communicate()
        return out or "", err or ""

    @property
    def returncode(self) -> int | None:
        return self._popen.returncode


def _attach_windows_job(proc: subprocess.Popen) -> object:
    """Put ``proc`` in a job with ``KILL_ON_JOB_CLOSE``, same flags as the #69 gate."""
    import ctypes

    from devops.win_job_object import (
        JobObjectExtendedLimitInformation,
        extended_limit_info,
        kernel32,
    )

    k = kernel32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise MemoryReadError("Windows Job Object konnte nicht angelegt werden.")
    info = extended_limit_info()
    if not k.SetInformationJobObject(
        job,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        k.CloseHandle(job)
        raise MemoryReadError("SetInformationJobObject für KILL_ON_JOB_CLOSE ist fehlgeschlagen.")
    # PROCESS_TERMINATE | PROCESS_SET_QUOTA, required by AssignProcessToJobObject.
    handle = k.OpenProcess(0x0001 | 0x0100, False, int(proc.pid))
    if not handle:
        k.CloseHandle(job)
        raise MemoryReadError("OpenProcess für das Job Object ist fehlgeschlagen.")
    try:
        if not k.AssignProcessToJobObject(job, handle):
            k.CloseHandle(job)
            raise MemoryReadError("AssignProcessToJobObject ist fehlgeschlagen.")
    finally:
        k.CloseHandle(handle)
    return job


def _spawn_captured(argv: list[str], env: dict[str, str]) -> _BenchmarkProcess:
    """Start ``argv`` in its own session so a later killpg covers grandchildren."""
    proc = subprocess.Popen(
        argv,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    job = _attach_windows_job(proc) if sys.platform == "win32" else None
    return _BenchmarkProcess(proc, job)


def _machine() -> dict[str, Any]:
    model = ""
    cpus: int | None = None
    mem_total: int | None = None
    try:
        counted = 0
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if line.startswith("processor"):
                counted += 1
        if counted:
            cpus = counted
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
                break
    except OSError:
        pass
    if cpus is None:
        counted = os.cpu_count()
        cpus = counted if counted else None
    if mem_total is None:
        psutil = _load_psutil()
        if psutil is not None:
            try:
                mem_total = int(psutil.virtual_memory().total)
            except Exception:
                mem_total = None
    return {
        "label": "VM, nicht i3",
        "cpu_model": model,
        "logical_cpus": cpus,
        "mem_total_bytes": mem_total,
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _dump(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _profile_top(profiler: cProfile.Profile, limit: int = 30) -> list[dict[str, Any]]:
    stats = pstats.Stats(profiler)
    rows: list[tuple[float, float, int, str]] = []
    for func, (cc, nc, tt, ct, _callers) in stats.stats.items():
        filename, line, name = func
        rows.append((ct, tt, nc, f"{filename}:{line}({name})"))
    rows.sort(key=lambda item: item[0], reverse=True)
    out = []
    for cum, tot, nc, label in rows[:limit]:
        out.append(
            {
                "function": label,
                "ncalls": nc,
                "tottime_s": round(tot, 6),
                "cumtime_s": round(cum, 6),
            }
        )
    return out


def _tracemalloc_top(limit: int = 20) -> list[dict[str, Any]]:
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")
    out = []
    for stat in stats[:limit]:
        out.append(
            {
                "site": str(stat.traceback),
                "size_bytes": stat.size,
                "count": stat.count,
            }
        )
    return out


def _base_env(appdata: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(appdata)
    env["KARRIEREKRAKE_LOCAL_LLM_CV_PARSING"] = "0"
    env["KARRIEREKRAKE_GEO_DATA_DIR"] = str(appdata / "geo")
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _apply_base_env(appdata: Path) -> None:
    os.environ.update(_base_env(appdata))


# ---------------------------------------------------------------------------
# importtime
# ---------------------------------------------------------------------------


def _parse_importtime(stderr: str) -> dict[str, Any]:
    rows: list[tuple[int, int, str]] = []
    for line in stderr.splitlines():
        match = re.match(r"import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.*)", line)
        if match:
            rows.append((int(match.group(1)), int(match.group(2)), match.group(3).strip()))
    by_self = sorted(rows, key=lambda item: item[0], reverse=True)
    top = [
        {"self_us": self_us, "cumulative_us": cum_us, "module": name}
        for self_us, cum_us, name in by_self[:25]
    ]
    total = 0
    for self_us, cum_us, name in rows:
        if name == "desktop.app":
            total = cum_us
            break
    return {
        "entry_module": "desktop.app",
        "total_import_us": total,
        "total_import_s": total / 1_000_000,
        "sum_self_us": sum(item[0] for item in rows),
        "import_rows": len(rows),
        "top25_by_self_us": top,
    }


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------


def _count_calls(obj: Any, name: str, bucket: dict[str, int]) -> None:
    orig = getattr(obj, name)

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        bucket[name] = bucket.get(name, 0) + 1
        return orig(*args, **kwargs)

    setattr(obj, name, wrapped)


def worker_startup(appdata: Path) -> dict[str, Any]:
    _apply_base_env(appdata)
    appdata.mkdir(parents=True, exist_ok=True)
    t_process = time.perf_counter()
    from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QGraphicsEffect

    from desktop.main_window import MainWindow
    from desktop.services import ConfigService

    import_done = time.perf_counter() - t_process

    fsync_n = {"n": 0}
    orig_fsync = os.fsync

    def _fsync(fd: int) -> None:
        fsync_n["n"] += 1
        return orig_fsync(fd)

    os.fsync = _fsync  # type: ignore[assignment]

    yaml_n = {"n": 0}
    import yaml

    orig_load = yaml.safe_load

    def _safe_load(*args: Any, **kwargs: Any) -> Any:
        yaml_n["n"] += 1
        return orig_load(*args, **kwargs)

    yaml.safe_load = _safe_load  # type: ignore[assignment]

    load_n = {"n": 0, "outer": 0, "outer_s": 0.0}
    save_n = {"n": 0}
    depth = {"n": 0}
    orig_cfg_load = ConfigService.load
    orig_cfg_save = ConfigService.save

    def load(self: ConfigService) -> Any:
        depth["n"] += 1
        outermost = depth["n"] == 1
        t0 = time.perf_counter() if outermost else 0.0
        load_n["n"] += 1
        try:
            return orig_cfg_load(self)
        finally:
            if outermost:
                load_n["outer"] += 1
                load_n["outer_s"] += time.perf_counter() - t0
            depth["n"] -= 1

    def save(self: ConfigService, *args: Any, **kwargs: Any) -> Any:
        save_n["n"] += 1
        return orig_cfg_save(self, *args, **kwargs)

    ConfigService.load = load  # type: ignore[method-assign]
    ConfigService.save = save  # type: ignore[method-assign]

    app = QApplication.instance() or QApplication([])
    rss_before, _ = _rss_pair()
    t0 = time.perf_counter()
    service = ConfigService()
    window = MainWindow(service)
    window.show()
    app.processEvents()
    cold_s = time.perf_counter() - t0
    visible = bool(window.isVisible())
    cold_rss, cold_hwm = _rss_pair()
    cold_counts = {
        "load_calls": load_n["n"],
        "outer_load_calls": load_n["outer"],
        "outer_load_s": load_n["outer_s"],
        "save_calls": save_n["n"],
        "fsync_calls": fsync_n["n"],
        "yaml_safe_load_calls": yaml_n["n"],
    }
    widgets = len(window.findChildren(QWidget))
    shadows = len(window.findChildren(QGraphicsDropShadowEffect))
    effects = len(window.findChildren(QGraphicsEffect))
    timers = window.findChildren(QTimer)
    timer_info = [
        {"interval_ms": t.interval(), "active": t.isActive()} for t in timers
    ]
    window.close()
    app.processEvents()

    # Warm path: migration flag is now on disk. New service + window.
    for key in ("n", "outer"):
        load_n[key] = 0
    load_n["outer_s"] = 0.0
    save_n["n"] = 0
    fsync_n["n"] = 0
    yaml_n["n"] = 0
    rss_warm_before, _ = _rss_pair()
    t0 = time.perf_counter()
    service2 = ConfigService()
    t_svc = time.perf_counter()
    loaded = service2.load()
    t_load = time.perf_counter()
    window2 = MainWindow(service2)
    window2.show()
    app.processEvents()
    warm_s = time.perf_counter() - t0
    warm_rss, warm_hwm = _rss_pair()
    from core.local_llm_cv_gate import local_llm_cv_parsing_allowed

    result = {
        "import_before_window_s": import_done,
        "cold_window_s": cold_s,
        "cold_visible": visible,
        "cold_rss_before_bytes": rss_before,
        "cold_rss_after_bytes": cold_rss,
        "cold_vmhwm_bytes": cold_hwm,
        "cold_counts": cold_counts,
        "warm_window_s": warm_s,
        "warm_configservice_ctor_s": t_svc - t0,
        "warm_load_s": t_load - t_svc,
        "warm_rss_before_bytes": rss_warm_before,
        "warm_rss_after_bytes": warm_rss,
        "warm_vmhwm_bytes": warm_hwm,
        "warm_counts": {
            "load_calls": load_n["n"],
            "outer_load_calls": load_n["outer"],
            "outer_load_s": load_n["outer_s"],
            "save_calls": save_n["n"],
            "fsync_calls": fsync_n["n"],
            "yaml_safe_load_calls": yaml_n["n"],
        },
        "widgets": widgets,
        "shadow_effects": shadows,
        "graphics_effects": effects,
        "timers": timer_info,
        "llm_parsing_allowed": bool(local_llm_cv_parsing_allowed(loaded.settings)),
        "recursion_limit": sys.getrecursionlimit(),
        "minimize_to_tray": bool(loaded.settings.minimize_to_tray),
    }
    window2.close()
    app.processEvents()
    return result


# ---------------------------------------------------------------------------
# CV
# ---------------------------------------------------------------------------


def _write_docx_from_fixture(dest: Path) -> None:
    from docx import Document

    text = (ROOT / "tests" / "fixtures" / "cv_structured_de.txt").read_text(encoding="utf-8")
    doc = Document()
    lines = text.splitlines()
    # Paragraphs carry the fixture text. A small table repeats the skill lines
    # so the DOCX table extractor is on the measured path.
    skills = [ln.lstrip("• ").strip() for ln in lines if ln.strip().startswith("•")]
    for line in lines:
        doc.add_paragraph(line)
    if skills:
        table = doc.add_table(rows=1 + len(skills[:6]), cols=1)
        table.rows[0].cells[0].text = "Kenntnisse"
        for i, skill in enumerate(skills[:6], start=1):
            table.rows[i].cells[0].text = skill
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)


def _cv_files(tmpdir: Path) -> list[Path]:
    pdfs = sorted((ROOT / "tests" / "fixtures" / "cv_corpus").glob("*.pdf"))
    docx = tmpdir / "cv_structured_de.docx"
    _write_docx_from_fixture(docx)
    return pdfs + [docx]


def _import_stages(path: Path) -> dict[str, Any]:
    from core.cv_extract import extract_text
    from core.cv_parser import parse_cv_text, parsed_to_qualifications
    from core.cv_verify_repair import apply_verify_repair_pipeline
    from desktop.services.profile_merge import filter_parsed_for_import, personal_from_parsed

    stages: dict[str, float] = {}
    t0 = time.perf_counter()
    text = extract_text(path)
    stages["extract_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    parsed = parse_cv_text(text)
    stages["parse_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    parsed = apply_verify_repair_pipeline(parsed, text or "")
    stages["verify_repair_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    filtered = filter_parsed_for_import(parsed)
    quals = parsed_to_qualifications(filtered)
    personal = personal_from_parsed(parsed)
    stages["profile_build_s"] = time.perf_counter() - t0
    stages["stages_sum_s"] = sum(stages.values())
    return {
        "stages": stages,
        "chars": len(text or ""),
        "skill_n": len(getattr(quals, "skills", []) or []),
        "personal_keys": len(personal),
    }


def worker_cv(appdata: Path) -> dict[str, Any]:
    _apply_base_env(appdata)
    appdata.mkdir(parents=True, exist_ok=True)
    from core.cv_parser import import_cv
    from core.local_llm_cv_gate import local_llm_cv_parsing_allowed

    files = _cv_files(appdata)
    rss_before, _ = _rss_pair()
    per_file = []
    t_all = time.perf_counter()
    for path in files:
        t0 = time.perf_counter()
        parsed = import_cv(path, guenther_enabled=False)
        e2e = time.perf_counter() - t0
        per_file.append(
            {
                "name": path.name,
                "suffix": path.suffix.lower(),
                "bytes": path.stat().st_size,
                "e2e_import_cv_s": e2e,
                "phi_invoked": bool(parsed.get("phi_invoked")),
                "phi_extract_call_count": int(parsed.get("phi_extract_call_count") or 0),
                "intelligence_status": parsed.get("intelligence_status"),
            }
        )
    wall = time.perf_counter() - t_all
    for item, path in zip(per_file, files):
        item.update(_import_stages(path))
    rss_after, hwm = _rss_pair()

    profiler = cProfile.Profile()
    profiler.enable()
    for path in files:
        import_cv(path, guenther_enabled=False)
    profiler.disable()

    return {
        "llm_parsing_allowed": bool(local_llm_cv_parsing_allowed(None)),
        "guenther_enabled": False,
        "file_count": len(files),
        "docx_note": (
            "Kein DOCX im Repo. cv_structured_de.docx wird je Lauf aus "
            "tests/fixtures/cv_structured_de.txt erzeugt."
        ),
        "wall_all_files_s": wall,
        "per_file": per_file,
        "profile_top30_cumulative": _profile_top(profiler, 30),
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "vmhwm_bytes": hwm,
    }


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------


def _match_config() -> Any:
    from core.config import (
        AppConfig,
        EmploymentConfig,
        FiltersConfig,
        JobsConfig,
        LocationConfig,
        SearchPreferences,
        SettingsConfig,
    )
    from core.cv_parser import import_cv, parsed_to_qualifications
    from core.search_intent import SearchIntent, Strictness
    from desktop.services.profile_merge import filter_parsed_for_import

    parsed = import_cv(
        ROOT / "tests" / "fixtures" / "cv_corpus" / "DE_01_Klassisch.pdf",
        guenther_enabled=False,
    )
    quals = parsed_to_qualifications(filter_parsed_for_import(parsed))
    intent = SearchIntent(
        target_roles=[
            "Lohnbuchhalter",
            "Sachbearbeiter",
            "Disponentin",
            "Payroll Specialist",
        ],
        mandatory_skills=["Excel"],
        preferred_skills=["SAP", "DATEV"],
        excluded_roles=["Praktikant", "Geschäftsführer"],
        excluded_keywords=["unbezahlt"],
        strictness=Strictness.BALANCED,
        countries=["DE"],
        radius_km=50,
        salary_min=36000,
        employment_types=["full_time"],
    )
    return AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(
                max_distance_km=50,
                country="DE",
                allow_remote_germany=True,
                allow_hybrid=True,
            ),
            jobs=JobsConfig(
                desired_titles=["Lohnbuchhalter", "Sachbearbeiter", "Disponent"]
            ),
            employment=EmploymentConfig(
                full_time=True,
                remote=True,
                hybrid=True,
                onsite=True,
                minimum_salary=36000,
            ),
            qualifications=quals,
            filters=FiltersConfig(desired_keywords=["Excel", "SAP", "Verwaltung"]),
            search_intent=intent,
        ),
        settings=SettingsConfig(),
    )


def _synthetic_jobs(n: int, corpus: list[dict[str, Any]]) -> list[Any]:
    from core.models import Job

    jobs = []
    for i in range(n):
        src = corpus[i % len(corpus)]
        jobs.append(
            Job(
                id=f"syn-{n}-{i}",
                source="fixture",
                source_job_id=str(i),
                title=str(src.get("title") or "Sachbearbeiter"),
                company=f"{src.get('company') or 'Nordlicht GmbH'} {i % 17}",
                description=(
                    str(src.get("description") or "Sachbearbeitung und Verwaltung")
                    + " Excel SAP Deutsch fließend 45.000 EUR DATEV Zoll"
                ),
                city=str(src.get("city") or "Hamburg"),
                postal_code="20095",
                country_code="DE",
                remote_type=str(src.get("remote_type") or "onsite"),
                employment_type="Vollzeit",
                distance_km=float(src.get("distance_km") or 8) + float(i % 40),
                salary_text="42.000 - 48.000 EUR",
                url=f"https://example.test/jobs/{n}/{i}",
                discovered_at="2026-09-01T12:00:00+00:00",
            )
        )
    return jobs


def _time_call(fn: Callable[[], Any]) -> tuple[float, Any]:
    t0 = time.perf_counter()
    value = fn()
    return time.perf_counter() - t0, value


def _scaling_row(n: int, seconds: float) -> dict[str, Any]:
    return {
        "n": n,
        "seconds": seconds,
        "seconds_per_item": seconds / n if n else None,
        "seconds_per_n2": seconds / (n * n) if n else None,
    }


def measure_has_applied(appdata: Path) -> list[dict[str, Any]]:
    """Time ``has_applied`` at 50, 200, 800, 2000 and 5000 rows.

    Setup inserts share one transaction. The clock covers only the product
    ``has_applied`` path, which opens a connection per call.
    """
    from contextlib import contextmanager

    from core.database import Database
    from core.deduplicator import company_key, title_key
    from core.models import Job, JobStatus

    applied_rows: list[dict[str, Any]] = []
    for n in (50, 200, 800, 2000, 5000):
        db_path = appdata / f"applied-{n}.db"
        if db_path.exists():
            db_path.unlink()
        db = Database(db_path)
        shared = db._connect()

        @contextmanager
        def _one_txn(conn=shared):
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise

        db.connection = _one_txn  # type: ignore[method-assign]
        for i in range(n):
            db.upsert_job(
                Job(
                    id=f"ap-{n}-{i}",
                    source="fixture",
                    title=f"Sachbearbeiter {i % 40}",
                    company=f"Firma {i % 25} GmbH",
                    url=f"https://example.test/applied/{n}/{i}",
                    status=JobStatus.APPLIED.value,
                    description="Excel",
                )
            )
        shared.commit()
        shared.close()
        del db.connection
        probes = [
            Job(
                id=f"q-{n}-{i}",
                source="fixture",
                title=f"Sachbearbeiter {i % 40}",
                company=f"Firma {i % 25} GmbH",
                url=f"https://example.test/query/{n}/{i}",
                description="Excel",
            )
            for i in range(n)
        ]
        t0 = time.perf_counter()
        hits = sum(1 for job in probes if db.has_applied(job))
        dt = time.perf_counter() - t0
        keys = {
            (company_key(f"Firma {i % 25} GmbH"), title_key(f"Sachbearbeiter {i % 40}"))
            for i in range(n)
        }
        rss_set_before, _peak_before = _rss_pair()
        t1 = time.perf_counter()
        hits_set = 0
        for job in probes:
            if (company_key(job.company), title_key(job.title)) in keys:
                hits_set += 1
        set_s = time.perf_counter() - t1
        rss_set_after, _peak_after = _rss_pair()
        print(f"has_applied n={n} {dt:.3f}s hits={hits}", file=sys.stderr)
        applied_rows.append(
            {
                **_scaling_row(n, dt),
                "hits": hits,
                "set_lookup_s": set_s,
                "set_hits": hits_set,
                "set_rss_delta_bytes": _rss_delta(rss_set_after, rss_set_before),
            }
        )
    return applied_rows


def worker_has_applied(appdata: Path) -> dict[str, Any]:
    """Only the has_applied probe, so n=2000 and n=5000 can be re-run alone."""
    _apply_base_env(appdata)
    appdata.mkdir(parents=True, exist_ok=True)
    rss_before, _ = _rss_pair()
    rows = measure_has_applied(appdata)
    rss_after, hwm = _rss_pair()
    return {
        "llm_used": False,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "vmhwm_bytes": hwm,
        "has_applied": rows,
    }


def worker_match(appdata: Path) -> dict[str, Any]:
    _apply_base_env(appdata)
    appdata.mkdir(parents=True, exist_ok=True)
    corpus = json.loads(
        (ROOT / "tests" / "fixtures" / "intent_jobs_corpus.json").read_text(encoding="utf-8")
    )["jobs"]
    cfg = _match_config()
    from core.deduplicator import deduplicate
    from core.intent_filter import filter_jobs
    from core.matcher import score_job

    sizes = (50, 500, 5000)
    built = {n: _synthetic_jobs(n, corpus) for n in sizes}
    rss_before, _ = _rss_pair()

    compile_n = {"n": 0}
    orig_compile = re.compile

    def _compile(*args: Any, **kwargs: Any) -> Any:
        compile_n["n"] += 1
        return orig_compile(*args, **kwargs)

    re.compile = _compile  # type: ignore[assignment]

    score_rows = []
    filter_rows = []
    dedup_rows = []
    excluded = {}
    for n in sizes:
        jobs = built[n]
        compile_n["n"] = 0
        dt, _ = _time_call(lambda jobs=jobs: [score_job(j, cfg) for j in jobs])
        score_rows.append({**_scaling_row(n, dt), "re_compile_calls": compile_n["n"]})
        dt, pairs = _time_call(lambda jobs=jobs: filter_jobs(jobs, cfg.profile.search_intent))
        included, excl = pairs
        filter_rows.append(
            {
                **_scaling_row(n, dt),
                "included": len(included),
                "excluded": len(excl),
            }
        )
        excluded[n] = len(excl)
        dt, _ = _time_call(lambda jobs=jobs: deduplicate(list(jobs)))
        dedup_rows.append(_scaling_row(n, dt))

    re.compile = orig_compile  # type: ignore[assignment]

    # cProfile the middle size (production path, no extra probes).
    profiler = cProfile.Profile()
    jobs500 = built[500]
    profiler.enable()
    for job in jobs500:
        score_job(job, cfg)
    filter_jobs(jobs500, cfg.profile.search_intent)
    profiler.disable()

    # SQL filter/sort at the same sizes. Fresh DB per size.
    from core.database import Database

    sql_rows = []
    for n in sizes:
        db_path = appdata / f"jobs-{n}.db"
        if db_path.exists():
            db_path.unlink()
        db = Database(db_path)
        t0 = time.perf_counter()
        for job in built[n]:
            job.match_score = (hash(job.id) % 100)
            db.upsert_job(job)
        insert_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        listed = db.list_jobs(
            min_match=10,
            max_distance=80,
            hide_duplicates=True,
            remote_types=["onsite", "hybrid", "remote"],
            title_query="buch",
            limit=n,
        )
        list_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        listed_sorted = sorted(listed, key=lambda j: int(j.match_score or 0), reverse=True)
        sort_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        all_rows = db.list_jobs(min_match=0, hide_duplicates=False, limit=n)
        list_all_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        all_sorted = sorted(all_rows, key=lambda j: int(j.match_score or 0), reverse=True)
        sort_all_s = time.perf_counter() - t0
        sql_rows.append(
            {
                "n": n,
                "insert_s": insert_s,
                "list_jobs_selective_s": list_s,
                "python_sort_selective_s": sort_s,
                "listed_selective": len(listed_sorted),
                "list_jobs_all_s": list_all_s,
                "python_sort_all_s": sort_all_s,
                "listed_all": len(all_sorted),
            }
        )

    # One transaction instead of connect/commit/close per upsert. Benchmark-only.
    batch_rows = []
    from contextlib import contextmanager

    for n in (500, 5000):
        db_path = appdata / f"jobs-batch-{n}.db"
        if db_path.exists():
            db_path.unlink()
        db = Database(db_path)
        shared = db._connect()
        rss_b0, _ = _rss_pair()

        @contextmanager
        def _one_txn():
            try:
                yield shared
            except Exception:
                shared.rollback()
                raise

        db.connection = _one_txn  # type: ignore[method-assign]
        t0 = time.perf_counter()
        for job in built[n]:
            db.upsert_job(job)
        shared.commit()
        batch_s = time.perf_counter() - t0
        rss_b1, _ = _rss_pair()
        shared.close()
        batch_rows.append(
            {
                "n": n,
                "one_transaction_upsert_s": batch_s,
                "per_call_upsert_s": next(row["insert_s"] for row in sql_rows if row["n"] == n),
                "rss_delta_bytes": _rss_delta(rss_b1, rss_b0),
            }
        )

    applied_rows = measure_has_applied(appdata)

    # Alias-loop probe on 500 jobs: production vs hoisted regex (benchmark only).
    import core.intent_aliases as aliases

    jobs_probe = built[500]
    rss_a, _ = _rss_pair()
    t0 = time.perf_counter()
    for job in jobs_probe:
        score_job(job, cfg)
    filter_jobs(jobs_probe, cfg.profile.search_intent)
    prod_s = time.perf_counter() - t0
    rss_b, _ = _rss_pair()

    hyphen_re = re.compile(r"[-_/]+")
    ws_re = re.compile(r"\s+")
    noise_re = re.compile(
        r"\b(senior|junior|m\s*w\s*d|w\s*m\s*d|all genders)\b",
        re.I,
    )

    def _norm_fast(value: str) -> str:
        text = (value or "").casefold().strip().replace("ß", "ss")
        text = hyphen_re.sub(" ", text)
        return ws_re.sub(" ", text).strip()

    def _fuzzy_fast(text: str, alias_set: frozenset[str]) -> bool:
        from rapidfuzz import fuzz

        needle = _norm_fast(text)
        if not needle or not alias_set:
            return False
        if needle in alias_set:
            return True
        compact = noise_re.sub(" ", needle)
        compact = ws_re.sub(" ", compact).strip(" ()[]")
        if compact in alias_set:
            return True
        threshold = aliases._ALIAS_FUZZY_THRESHOLD
        for alias in alias_set:
            if not alias:
                continue
            if fuzz.ratio(compact, alias) >= threshold or fuzz.ratio(needle, alias) >= threshold:
                return True
        return False

    orig_norm = aliases._norm_alias
    orig_fuzzy = aliases._fuzzy_against_aliases
    aliases._norm_alias = _norm_fast  # type: ignore[assignment]
    aliases._fuzzy_against_aliases = _fuzzy_fast  # type: ignore[assignment]
    t0 = time.perf_counter()
    for job in jobs_probe:
        score_job(job, cfg)
    filter_jobs(jobs_probe, cfg.profile.search_intent)
    hoisted_s = time.perf_counter() - t0
    rss_c, _ = _rss_pair()

    family_cache: dict[str, Any] = {}
    real_family = aliases.role_family_id_for_label

    def _family_cached(label: str) -> Any:
        if label in family_cache:
            return family_cache[label]
        value = real_family(label)
        family_cache[label] = value
        return value

    aliases.role_family_id_for_label = _family_cached  # type: ignore[assignment]
    t0 = time.perf_counter()
    for job in jobs_probe:
        score_job(job, cfg)
    filter_jobs(jobs_probe, cfg.profile.search_intent)
    cached_s = time.perf_counter() - t0
    rss_d, _ = _rss_pair()
    aliases._norm_alias = orig_norm  # type: ignore[assignment]
    aliases._fuzzy_against_aliases = orig_fuzzy  # type: ignore[assignment]
    aliases.role_family_id_for_label = real_family  # type: ignore[assignment]

    # PLZ: production resolve vs cached dataset validation.
    from core.geo_resolve import reset_pgeocode_index_for_tests, resolve_postal_pgeocode
    import core.geo_dataset as geo_dataset

    reset_pgeocode_index_for_tests()
    rss_geo0, _ = _rss_pair()
    t0 = time.perf_counter()
    first = resolve_postal_pgeocode("20095", "DE")
    first_s = time.perf_counter() - t0
    rss_geo1, _ = _rss_pair()
    t0 = time.perf_counter()
    for i in range(30):
        resolve_postal_pgeocode(str(10115 + (i % 50)), "DE")
    geo30_s = time.perf_counter() - t0
    real_validate = geo_dataset.validate_dataset
    cached_validation: dict[str, Any] = {}

    def _validate_cached(path: Path) -> Any:
        key = str(path)
        if key not in cached_validation:
            cached_validation[key] = real_validate(path)
        return cached_validation[key]

    geo_dataset.validate_dataset = _validate_cached  # type: ignore[assignment]
    t0 = time.perf_counter()
    for i in range(30):
        resolve_postal_pgeocode(str(80331 + (i % 50)), "DE")
    geo30_cached_s = time.perf_counter() - t0
    rss_geo2, _ = _rss_pair()
    geo_dataset.validate_dataset = real_validate  # type: ignore[assignment]

    rss_after, hwm = _rss_pair()
    return {
        "corpus_jobs": len(corpus),
        "llm_used": False,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "vmhwm_bytes": hwm,
        "score": score_rows,
        "filter_jobs": filter_rows,
        "deduplicate": dedup_rows,
        "sql": sql_rows,
        "upsert_one_transaction": batch_rows,
        "has_applied": applied_rows,
        "profile_top30_cumulative_n500": _profile_top(profiler, 30),
        "alias_probe_n500": {
            "production_score_and_filter_s": prod_s,
            "hoisted_regex_score_and_filter_s": hoisted_s,
            "hoisted_plus_family_cache_s": cached_s,
            "rss_before_bytes": rss_a,
            "rss_after_production_bytes": rss_b,
            "rss_after_hoist_bytes": rss_c,
            "rss_after_family_cache_bytes": rss_d,
            "family_cache_entries": len(family_cache),
        },
        "plz_probe": {
            "first_status": first.status,
            "first_reason": first.reason,
            "first_resolve_s": first_s,
            "next_30_s": geo30_s,
            "next_30_cached_validate_s": geo30_cached_s,
            "rss_before_bytes": rss_geo0,
            "rss_after_first_bytes": rss_geo1,
            "rss_after_cached_bytes": rss_geo2,
        },
    }


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def _seed_profile_yaml(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    experiences = []
    for i in range(6):
        experiences.append(
            {
                "title": f"Rolle {i}",
                "company": f"Firma {i}",
                "location": "Hamburg",
                "start_date": "2020-01",
                "end_date": "2021-06",
                "responsibilities": ["Excel", "SAP", "Disposition"],
                "source": "cv",
            }
        )
    profile = {
        "location": {
            "home_address": "",
            "max_distance_km": 30,
            "country": "DE",
            "allow_remote_germany": True,
            "allow_hybrid": True,
        },
        "jobs": {
            "desired_titles": ["Disponentin", "Sachbearbeiterin", "Lohnbuchhalterin"],
            "unwanted_titles": ["Praktikant"],
            "alternative_titles": [],
        },
        "employment": {"full_time": True, "remote": True, "hybrid": True, "onsite": True},
        "qualifications": {
            "work_experience": experiences,
            "education": [
                {
                    "qualification": "Kauffrau für Spedition",
                    "institution": "Berufsschule",
                    "completion_date": "2018-07",
                }
            ],
            "skills": [{"value": s, "source": "cv"} for s in (
                "Excel", "SAP", "Disposition", "Zoll", "Englisch", "DATEV", "Outlook", "Verhandlung"
            )],
            "software": [{"value": "SAP", "source": "cv"}],
            "languages": [{"language": "Deutsch", "level": "C2"}, {"language": "Englisch", "level": "B2"}],
            "certificates": [],
            "driving_license": [],
        },
        "filters": {"desired_keywords": ["Excel"]},
        "search_intent": {
            "schema_version": 1,
            "target_roles": ["Disponentin", "Sachbearbeiterin"],
            "excluded_roles": ["Praktikant"],
            "strictness": "balanced",
            "countries": ["DE"],
            "radius_km": 30,
        },
    }
    application = {
        "first_name": "Lena",
        "last_name": "Winterfeld",
        "street": "Hafenstraße 12",
        "postal_code": "20095",
        "city": "Hamburg",
        "country": "DE",
        "email": "lena.winterfeld@example.com",
    }
    settings = {"language": "de", "theme": "system", "minimize_to_tray": False}
    import yaml

    (config_dir / "profile.yaml").write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (config_dir / "application_profile.yaml").write_text(
        yaml.safe_dump(application, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (config_dir / "settings.yaml").write_text(
        yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def worker_ui(appdata: Path) -> dict[str, Any]:
    _apply_base_env(appdata)
    root = appdata / "Karrierekrake"
    # Pre-seed the migration flag so UI numbers are not the first-run recursion.
    (root).mkdir(parents=True, exist_ok=True)
    (root / "meta.json").write_text(
        json.dumps({"first_run_completed": True, "shutdown_fix_v1": True, "cv_variants": []}),
        encoding="utf-8",
    )
    _seed_profile_yaml(root / "config")

    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop
    from PySide6.QtWidgets import (
        QApplication,
        QGraphicsDropShadowEffect,
        QGraphicsEffect,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    class PaintApp(QApplication):
        def __init__(self, argv: list[str]) -> None:
            super().__init__(argv)
            self.paints = 0

        def notify(self, receiver: Any, event: Any) -> bool:  # type: ignore[override]
            if event.type() == QEvent.Type.Paint:
                self.paints += 1
            return super().notify(receiver, event)

    from desktop.design_system.polish import soft_shadow
    from desktop.main_window import MainWindow
    from desktop.services import ConfigService
    from core.database import Database
    from core.models import Job

    app = PaintApp.instance() or PaintApp([])
    assert isinstance(app, PaintApp)
    rss0, _ = _rss_pair()
    service = ConfigService()
    window = MainWindow(service)
    window.show()
    app.processEvents()
    rss_window, _ = _rss_pair()

    per_page = []
    for name in ("dashboard", "jobs", "profile", "inbox", "settings", "applications", "search", "logs"):
        page = getattr(window, name)
        per_page.append(
            {
                "page": name,
                "shadows": len(page.findChildren(QGraphicsDropShadowEffect)),
                "effects": len(page.findChildren(QGraphicsEffect)),
                "widgets": len(page.findChildren(QWidget)),
            }
        )

    # Shadow repaint on the live window, then with effects disabled.
    def _repaint_s(repeats: int = 20) -> float:
        app.processEvents()
        app.paints = 0
        t0 = time.perf_counter()
        for _ in range(repeats):
            window.repaint()
            app.processEvents()
        return time.perf_counter() - t0

    shadows = window.findChildren(QGraphicsDropShadowEffect)
    paint_on_s = _repaint_s()
    paints_on = app.paints
    for effect in shadows:
        effect.setEnabled(False)
    paint_off_s = _repaint_s()
    paints_off = app.paints
    for effect in shadows:
        effect.setEnabled(True)

    # Chip/card shadow microbench (not the product tree).
    host = QWidget()
    layout = QVBoxLayout(host)
    labels = [QLabel(f"Chip {i}", host) for i in range(40)]
    for label in labels:
        layout.addWidget(label)
    host.show()
    app.processEvents()
    rss_plain, _ = _rss_pair()

    def _repaint_host() -> tuple[float, int]:
        app.paints = 0
        t0 = time.perf_counter()
        for _ in range(20):
            host.repaint()
            app.processEvents()
        return time.perf_counter() - t0, app.paints

    plain_s, plain_paints = _repaint_host()
    for label in labels:
        soft_shadow(label)
    app.processEvents()
    rss_shadow, _ = _rss_pair()
    shadow_s, shadow_paints = _repaint_host()
    host.close()

    # refresh_cards: deleteLater without hide. Measure only.
    page = window.profile
    calls = {"n": 0}
    orig_refresh = page.refresh_cards

    def _counted() -> None:
        calls["n"] += 1
        orig_refresh()

    page.refresh_cards = _counted  # type: ignore[method-assign]
    # Profile must be the current page; otherwise children report isVisible() false
    # only because the stacked page is hidden, which hides the deleteLater effect.
    window.stack.setCurrentWidget(page)
    page.load_from_config()
    app.processEvents()
    widgets_settled = len(page.findChildren(QWidget))

    def _layout_widgets(layout: Any) -> list[Any]:
        found = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                found.append(widget)
        return found

    before_widgets = (
        _layout_widgets(page._exp_body)
        + _layout_widgets(page._edu_body)
        + _layout_widgets(page._lang_body)
        + _layout_widgets(page._skills_row)
        + _layout_widgets(page._wanted_row)
    )
    before_ids = {id(w) for w in before_widgets}
    app.paints = 0
    t0 = time.perf_counter()
    page.refresh_cards()
    refresh_s = time.perf_counter() - t0
    paints_during_refresh = app.paints
    import shiboken6

    alive = [w for w in before_widgets if shiboken6.isValid(w)]
    visible_before_flush = [
        w for w in alive if (not w.isHidden()) and w.isVisible()
    ]
    hidden_before_flush = [w for w in alive if w.isHidden()]
    widgets_before_flush = len(page.findChildren(QWidget))
    app.paints = 0
    page.repaint()
    # Default processEvents does not include DeferredDeletion, so deleteLater
    # objects are still alive after this call. That is the event-loop gap.
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
    paints_during_flush = app.paints
    alive_after_plain = [w for w in before_widgets if shiboken6.isValid(w)]
    visible_after_plain = [
        w for w in alive_after_plain if (not w.isHidden()) and w.isVisible()
    ]
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    alive_after = [w for w in before_widgets if shiboken6.isValid(w)]
    widgets_after_flush = len(page.findChildren(QWidget))

    # Local pattern probe: hide()+deleteLater versus deleteLater only.
    def _pattern(hide: bool) -> dict[str, Any]:
        box = QWidget()
        lay = QVBoxLayout(box)
        created = [QLabel(f"row {i}", box) for i in range(30)]
        for label in created:
            lay.addWidget(label)
        box.show()
        app.processEvents()
        app.paints = 0
        for label in created:
            if hide:
                label.hide()
            label.deleteLater()
        paints_sync = app.paints
        visible = sum(
            1
            for label in created
            if shiboken6.isValid(label) and (not label.isHidden()) and label.isVisible()
        )
        app.paints = 0
        box.repaint()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        paints_flush = app.paints
        alive_plain = sum(1 for label in created if shiboken6.isValid(label))
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        alive_n = sum(1 for label in created if shiboken6.isValid(label))
        box.close()
        app.processEvents()
        return {
            "hide_before_deleteLater": hide,
            "visible_before_plain_processEvents": visible,
            "paints_sync": paints_sync,
            "paints_during_repaint_and_plain_processEvents": paints_flush,
            "alive_after_plain_processEvents": alive_plain,
            "alive_after_deferred_deletion": alive_n,
        }

    pattern_delete = _pattern(False)
    pattern_hide = _pattern(True)

    # Job list refresh on the UI thread. JobsPage.refresh always reloads config
    # and lists at most 500 rows (the product cap).
    cfg = service.load()
    db_path = cfg.db_path
    corpus = json.loads(
        (ROOT / "tests" / "fixtures" / "intent_jobs_corpus.json").read_text(encoding="utf-8")
    )["jobs"]
    from desktop.viewmodels.job_fit import build_job_fit_viewmodel

    fit_calls = {"n": 0}
    orig_fit = build_job_fit_viewmodel

    def _fit(*args: Any, **kwargs: Any) -> Any:
        fit_calls["n"] += 1
        return orig_fit(*args, **kwargs)

    import desktop.viewmodels.job_fit as job_fit_mod
    import desktop.pages.jobs as jobs_mod

    job_fit_mod.build_job_fit_viewmodel = _fit  # type: ignore[assignment]
    jobs_mod.build_job_fit_viewmodel = _fit  # type: ignore[assignment]

    refresh_rows = []
    local_db = Database(db_path)
    inserted = 0
    for n in (50, 500):
        for i in range(inserted, n):
            src = corpus[i % len(corpus)]
            local_db.upsert_job(
                Job(
                    id=f"ui-{i}",
                    source="fixture",
                    title=str(src.get("title") or "Sachbearbeiter"),
                    company=str(src.get("company") or "ACME"),
                    description=str(src.get("description") or "Excel SAP"),
                    city=str(src.get("city") or "Hamburg"),
                    remote_type="hybrid",
                    distance_km=12.0,
                    match_score=80,
                    url=f"https://example.test/ui/{i}",
                    discovered_at="2026-09-01T12:00:00+00:00",
                )
            )
        inserted = n
        fit_calls["n"] = 0
        widgets_before = len(window.jobs.findChildren(QWidget))
        t0 = time.perf_counter()
        window.jobs.refresh()
        dt = time.perf_counter() - t0
        app.processEvents()
        refresh_rows.append(
            {
                "inserted": n,
                "refresh_s": dt,
                "fit_calls": fit_calls["n"],
                "listed_cards": window.jobs.job_list.count(),
                "table_rows": window.jobs.table.rowCount(),
                "widgets_after": len(window.jobs.findChildren(QWidget)),
                "widgets_before": widgets_before,
            }
        )

    rss_end, hwm = _rss_pair()
    window.close()
    app.processEvents()
    return {
        "llm_parsing_allowed": False,
        "migration_preseeded": True,
        "rss_before_bytes": rss0,
        "rss_after_window_bytes": rss_window,
        "rss_after_bytes": rss_end,
        "vmhwm_bytes": hwm,
        "pages": per_page,
        "window_shadows": len(shadows),
        "window_repaint_20_effects_on_s": paint_on_s,
        "window_repaint_20_effects_off_s": paint_off_s,
        "window_paints_on": paints_on,
        "window_paints_off": paints_off,
        "chip_probe_40": {
            "plain_repaint_20_s": plain_s,
            "plain_paints": plain_paints,
            "shadow_repaint_20_s": shadow_s,
            "shadow_paints": shadow_paints,
            "rss_plain_bytes": rss_plain,
            "rss_shadow_bytes": rss_shadow,
            "rss_delta_bytes": _rss_delta(rss_shadow, rss_plain),
        },
        "refresh_cards": {
            "calls_including_load_from_config": calls["n"],
            "one_refresh_s": refresh_s,
            "widgets_settled": widgets_settled,
            "replaced_widgets": len(before_ids),
            "alive_before_flush": len(alive),
            "visible_and_not_hidden_before_flush": len(visible_before_flush),
            "explicitly_hidden_before_flush": len(hidden_before_flush),
            "paints_during_refresh_call": paints_during_refresh,
            "paints_during_repaint_and_plain_processEvents": paints_during_flush,
            "alive_after_plain_processEvents": len(alive_after_plain),
            "visible_after_plain_processEvents": len(visible_after_plain),
            "alive_after_deferred_deletion": len(alive_after),
            "widgets_before_flush": widgets_before_flush,
            "widgets_after_flush": widgets_after_flush,
            "pattern_deleteLater_only": pattern_delete,
            "pattern_hide_then_deleteLater": pattern_hide,
        },
        "jobs_refresh": refresh_rows,
    }


WORKERS = {
    "startup": worker_startup,
    "cv": worker_cv,
    "match": worker_match,
    "ui": worker_ui,
    "has_applied": worker_has_applied,
}


def _worker_entry(section: str, appdata: Path) -> int:
    _ensure_root()
    try:
        if section == "cv-trace" or section == "match-trace" or section == "startup-trace":
            payload = _traced(section.replace("-trace", ""), appdata)
        else:
            payload = WORKERS[section](appdata)
        payload["section"] = section
        payload["ok"] = True
        _dump(payload)
        return 0
    except Exception as exc:  # noqa: BLE001 — worker must report, not hang
        _dump({"section": section, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1


def _traced(section: str, appdata: Path) -> dict[str, Any]:
    """One tracemalloc snapshot of a bounded slice.

    The cold ConfigService recursion and the 5000-job loop allocate too many
    Python frames to trace safely under the process-group cap. Those paths are
    timed without tracemalloc. The snapshot covers the warm window, one CV
    import pass, or 200 scored jobs.
    """
    _apply_base_env(appdata)
    appdata.mkdir(parents=True, exist_ok=True)
    note = (
        "Einzelsnapshot mit tracemalloc, nicht in den Wall-Clock-Medianen. "
        "Kalter Start und 5000er-Matching sind wegen der Frame-Menge ungetraced."
    )
    if section == "startup":
        root = appdata / "Karrierekrake"
        root.mkdir(parents=True, exist_ok=True)
        (root / "meta.json").write_text(
            json.dumps({"shutdown_fix_v1": True, "first_run_completed": True}),
            encoding="utf-8",
        )
        tracemalloc.start(25)
        from PySide6.QtWidgets import QApplication
        from desktop.main_window import MainWindow
        from desktop.services import ConfigService

        app = QApplication.instance() or QApplication([])
        service = ConfigService()
        window = MainWindow(service)
        window.show()
        app.processEvents()
        window.close()
        slice_name = "warm_mainwindow"
    elif section == "cv":
        tracemalloc.start(25)
        from core.cv_parser import import_cv

        path = ROOT / "tests" / "fixtures" / "cv_corpus" / "DE_05_Zweiseitig.pdf"
        import_cv(path, guenther_enabled=False)
        slice_name = path.name
    else:
        tracemalloc.start(25)
        corpus = json.loads(
            (ROOT / "tests" / "fixtures" / "intent_jobs_corpus.json").read_text(encoding="utf-8")
        )["jobs"]
        cfg = _match_config()
        from core.intent_filter import filter_jobs
        from core.matcher import score_job

        jobs = _synthetic_jobs(200, corpus)
        for job in jobs:
            score_job(job, cfg)
        filter_jobs(jobs, cfg.profile.search_intent)
        slice_name = "score_and_filter_n200"
    current, peak = tracemalloc.get_traced_memory()
    payload = {
        "slice": slice_name,
        "tracemalloc_current_bytes": current,
        "tracemalloc_peak_bytes": peak,
        "tracemalloc_top20": _tracemalloc_top(20),
        "tracemalloc_note": note,
    }
    tracemalloc.stop()
    return payload


def _run_worker(section: str, appdata: Path, trace: bool = False) -> dict[str, Any]:
    name = f"{section}-trace" if trace else section
    env = _base_env(appdata)
    proc = _spawn_captured(
        [sys.executable, str(Path(__file__).resolve()), "--worker", name, "--appdata", str(appdata)],
        env,
    )
    peak, aborted = _watch_process_rss(proc, WORKER_SAMPLE_INTERVAL_S)
    out, err = proc.communicate()
    payload: dict[str, Any]
    try:
        payload = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except json.JSONDecodeError:
        payload = {"ok": False, "error": "json", "stdout_tail": out[-2000:]}
    payload["sampled_group_rss_max_bytes"] = peak
    payload["sampled_limit_metric_max_bytes"] = peak
    payload["aborted_for_peak"] = aborted
    payload["memory_accounting"] = _memory_accounting(WORKER_SAMPLE_INTERVAL_S)
    payload["stderr_tail"] = err[-4000:]
    payload["returncode"] = proc.returncode
    return payload


def _numeric_summary(runs: list[dict[str, Any]], path: tuple[str, ...]) -> dict[str, Any] | None:
    values: list[float] = []
    for run in runs:
        cur: Any = run
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and isinstance(cur, (int, float)) and not isinstance(cur, bool):
            values.append(float(cur))
    if not values:
        return None
    return {"median": _median(values), "max": max(values), "n": len(values), "values": values}


def _summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    # Collect every dotted numeric path up to depth 3 that is present on all runs.
    sample = runs[0] if runs else {}

    def walk(obj: Any, prefix: tuple[str, ...], depth: int, acc: list[tuple[str, ...]]) -> None:
        if depth > 3 or not isinstance(obj, dict):
            return
        for key, value in obj.items():
            if key in {"stderr_tail", "stdout_tail", "top25_by_self_us", "profile_top30_cumulative",
                       "profile_top30_cumulative_n500", "tracemalloc_top20", "per_file", "timers",
                       "pages", "jobs_refresh", "score", "filter_jobs", "deduplicate", "sql",
                       "has_applied"}:
                continue
            nxt = prefix + (key,)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                acc.append(nxt)
            elif isinstance(value, dict):
                walk(value, nxt, depth + 1, acc)

    paths: list[tuple[str, ...]] = []
    walk(sample, (), 0, paths)
    summary = {}
    for path in paths:
        stat = _numeric_summary(runs, path)
        if stat:
            summary[".".join(path)] = stat
    return summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual Karrierekrake performance benchmark")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--out", type=Path, default=Path("/tmp/kk-perf"))
    parser.add_argument("--sections", default=",".join(SECTIONS))
    parser.add_argument("--worker", default="")
    parser.add_argument("--appdata", type=Path, default=None)
    parser.add_argument("--skip-trace", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ensure_root()
    _ensure_memory_reader()
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.worker:
        if args.appdata is None:
            print("appdata required", file=sys.stderr)
            return 2
        if args.worker.endswith("-trace"):
            return _worker_entry(args.worker, args.appdata)
        return _worker_entry(args.worker, args.appdata)
    if args.runs < DEFAULT_RUNS:
        print(f"--runs must be >= {DEFAULT_RUNS}", file=sys.stderr)
        return 2
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    sections = [s.strip() for s in args.sections.split(",") if s.strip()]
    report: dict[str, Any] = {
        "machine": _machine(),
        "runs": args.runs,
        "peak_gate_bytes": PEAK_GATE_BYTES,
        "peak_abort_bytes": PEAK_ABORT_BYTES,
        "llm": "disabled",
        "ci": "not a CI check; do not add to unit-tests or workflows",
        "memory_accounting": {
            "peak_is_sampled": True,
            "sample_interval_ms": {
                "worker": int(round(WORKER_SAMPLE_INTERVAL_S * 1000)),
                "importtime": int(round(IMPORTTIME_SAMPLE_INTERVAL_S * 1000)),
            },
            "limit_bytes": PEAK_ABORT_BYTES,
            "gate_bytes": PEAK_GATE_BYTES,
            **_limit_metric_fields(),
        },
        "sections": {},
    }
    try:
        _run_sections(report, sections, out, trace=not args.skip_trace)
    except NoRssSampleError as exc:
        print(str(exc), file=sys.stderr)
        return NO_SAMPLE_EXIT
    (out / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(str(out / "report.json"), file=sys.stderr)
    return 0


def _run_sections(report: dict[str, Any], sections: list[str], out: Path, *, trace: bool) -> None:
    for section in sections:
        print(f"== {section} x{report['runs']}", file=sys.stderr)
        runs = []
        for i in range(int(report["runs"])):
            appdata = out / f"{section}-run{i}"
            if section == "importtime":
                env_note = _run_importtime_sampled(appdata)
                runs.append(env_note)
            else:
                runs.append(_run_worker(section, appdata))
            print(
                f"  run {i} ok={runs[-1].get('ok', True)} "
                f"group_rss={_fmt_bytes(runs[-1].get('sampled_group_rss_max_bytes'))}",
                file=sys.stderr,
            )
        trace_run = None
        if section in {"startup", "cv", "match"} and trace:
            print(f"  tracemalloc {section}", file=sys.stderr)
            trace_run = _run_worker(section, out / f"{section}-trace", trace=True)
        report["sections"][section] = {
            "summary": _summarize([r for r in runs if r.get("ok", True) or section == "importtime"]),
            "runs": runs,
            "tracemalloc_run": trace_run,
        }
        (out / f"{section}.json").write_text(
            json.dumps(report["sections"][section], indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


def _run_importtime_sampled(appdata: Path) -> dict[str, Any]:
    env = _base_env(appdata)
    proc = _spawn_captured(
        [sys.executable, "-X", "importtime", "-c", "import desktop.app"],
        env,
    )
    t0 = time.perf_counter()
    peak, aborted = _watch_process_rss(proc, IMPORTTIME_SAMPLE_INTERVAL_S)
    wall = time.perf_counter() - t0
    _out, err = proc.communicate()
    parsed = _parse_importtime(err or "")
    parsed["process_wall_s"] = wall
    parsed["returncode"] = proc.returncode
    parsed["sampled_group_rss_max_bytes"] = peak
    parsed["sampled_limit_metric_max_bytes"] = peak
    parsed["aborted_for_peak"] = aborted
    parsed["memory_accounting"] = _memory_accounting(IMPORTTIME_SAMPLE_INTERVAL_S)
    parsed["ok"] = proc.returncode == 0 and parsed["total_import_us"] > 0
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
