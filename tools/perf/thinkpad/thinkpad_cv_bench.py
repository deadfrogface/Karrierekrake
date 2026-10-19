#!/usr/bin/env python3
"""Karrierekrake CV-import speed benchmark (in-process llama-cpp-python 0.3.35).

PRIMARY measurement of the speed test. It runs the repo's own CV-import code
in this process, exactly as the import child does (desktop/cv_import_child.py
-> core.cv_parser.import_cv -> core.cv_docpick_import.import_cv_docpick ->
_llm_extract -> core.cv_llm_runtime.chat_completion_inprocess). NOT llama-server.

Nothing in the product code is replaced for the baseline. The harness only
* sets the product's own env switches (KARRIEREKRAKE_CV_LLM_MODEL,
  KARRIEREKRAKE_CV_LLM_N_THREADS[_BATCH], KARRIEREKRAKE_CV_LLM_MAX_TOKENS,
  KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S, KARRIEREKRAKE_MODELS_DIR/DATA_DIR sandbox),
* forces the in-process transport (http_llm_available -> False, like a user
  machine without a developer server),
* wraps (observes, does not alter) chat_completion_inprocess,
  completion_token_budget and the Llama class (`core.cv_llm_runtime._llama_cls`)
  to take timestamps, and
* for non-baseline variants adds exactly one documented change (see VARIANTS).

Per CV: 1 uncounted warm-up + N measured runs (default 3). Per run: prompt tok/s,
generation tok/s (llama_perf_context, same source as the product's llm_step),
TTFT, wall time per CV, generated tokens, peak RSS / private bytes of this
process (psutil poll, default 25 ms), the full extract (normalised parsed JSON)
and every raw LLM answer byte-exact.

VARIANTS (one invocation = one variant)
  --threads plan|N --threads-batch plan|N   plan = resolve_cv_llm_thread_plan()
           (core/cv_llm_runtime.py:367-383); N via the product env overrides.
  --spec prompt-lookup                       llama_cpp.llama_speculative.
           LlamaPromptLookupDecoding passed as Llama(draft_model=...). 0.3.35 has
           NO draft-model (second GGUF) speculation. Forces logits_all=True.
           Qwen3.5 is a hybrid (recurrent) model: rejected draft tokens need a
           partial KV/state rollback that llama.cpp cannot do for the recurrent
           part. Box smoke (Qwen3.5-4B): llama_decode returned -1 after the 3rd draft;
           without explicit logits_all=True a 0.3.35 bug crashes the 2nd prefill block.
           Works (byte-identical, but slower) on the non-hybrid Qwen3 family.
  --prefix-cache ram                         in-process llama_cpp.LlamaRAMCache
           holding the KV/recurrent state at the end of the shared prefix
           (chat template + system prompt + "## JSON Schema ... ## Document
           Text\\n"). Disk caches are forbidden (core/security/diskcache_guard.py).
           Splits the product's 512-token prefill blocks at the prefix boundary ->
           text-changing; always diff. Product relevance: the app starts a fresh
           import child per CV and loads the model per LLM call, so a RAM cache
           could only help with a long-lived worker that does not exist today.
  --thinking on                              binds enable_thinking=true instead of
           false (core/local_chat_template.py); /no_think stays in the messages.
  --max-tokens N                             product env KARRIEREKRAKE_CV_LLM_MAX_TOKENS
           (cap of completion_token_budget). An answer longer than N ends as
           llm_output_truncated (recorded as a failed run, like the product).
  --model PATH                               model swap (Q4_K_M / Q4_0 / product GSQ).

Subcommands: run, diff, summarize, sysinfo   (see --help of each)
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import functools
import hashlib
import importlib.util
import json
import os
import platform
import re
import shlex
import statistics
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import psutil

IS_WIN = os.name == "nt"
SCHEMA = "kk-cv-speed-bench/1"
PINNED_LLAMA_CPP_PYTHON = "0.3.35"
PINNED_LLAMA_CPP_COMMIT = "4df29be4f4c3673f428170fda944a5b19f743bb8"  # vendor/llama.cpp @ v0.3.35
WIN_WHEEL = {
    "url": "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35/"
           "llama_cpp_python-0.3.35-py3-none-win_amd64.whl",
    "bytes": 7086788,
    "sha256": "31590ea000d5aff6f05f1e428048e72318a83709288159a5bd4dabec530080bb",
}
DOC_MARKER = "## Document Text\n"          # core/cv_docpick_import.py:1270-1274
# Keys of the parsed dict that depend on the machine/path, not on the model output.
VOLATILE_PARSED_KEYS = ("source_path", "peak_rss_mb_at_end")
OWN_ENV = (
    "KARRIEREKRAKE_CV_LLM_MODEL", "KARRIEREKRAKE_CV_LLM_N_THREADS", "KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH",
    "KARRIEREKRAKE_CV_LLM_MAX_TOKENS", "KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "KARRIEREKRAKE_MODELS_DIR",
    "KARRIEREKRAKE_DATA_DIR", "KARRIEREKRAKE_CV_LLM_BASE",
)


# ----------------------------------------------------------------- utilities
def now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")   # local time with UTC offset (Windows-safe)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def sha256_file(path: Path, cache: dict | None = None) -> str:
    st = path.stat()
    key = sha256_text(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}")   # no path in _sha256_cache.json
    if cache is not None and key in cache:
        return cache[key]
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 << 20), b""):
            h.update(block)
    if cache is not None:
        cache[key] = h.hexdigest()
    return h.hexdigest()


def canon_json(obj) -> str:
    """Canonical, diff-friendly JSON (sorted keys, UTF-8, LF, trailing newline)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1, default=str) + "\n"


# ------------------------------------------------------------- path scrubbing
# Kritiker rule: nothing this bench writes to disk (session/result JSON, error JSON, power log, CSV, console
# output that run_cv_matrix.ps1 tees into *.console.log) may carry the home directory, the repo checkout or
# the models directory. Only the directory prefix is replaced; basenames (model / CV / prompt file names)
# stay, the evaluation needs them. Matching uses the ACTUAL home/repo/models strings (any characters,
# e.g. a Windows profile name with spaces and umlauts), case-insensitive, with "\" or "/" separators, JSON-escaped (\\, \u005c,
# \u00fc) and URL-encoded (%5C, %2F, %20, %C3%BC) spellings. Measured values are never touched:
# only str values/keys change, numbers/bools/None pass through unchanged.
_SCRUB_ROOTS: dict[str, str] = {}          # registered at run time: absolute path -> placeholder
_SEP_RE = r"(?:\\u005c|%5c|%2f|[\\/])+"


def register_scrub_root(path, placeholder: str) -> None:
    if path:
        _SCRUB_ROOTS[str(path)] = placeholder


def _home_roots() -> list[str]:
    out = []
    for get in (lambda: os.environ.get("USERPROFILE"), lambda: os.environ.get("HOME"),
                lambda: str(Path.home()), lambda: os.path.expanduser("~")):
        try:
            v = get()
        except Exception:  # noqa: BLE001 - no home is fine
            v = None
        if v and v != "~":
            out.append(v)
    return out


def _component_re(c: str) -> str:
    from urllib.parse import quote
    alts = {c, quote(c, safe=""), json.dumps(c)[1:-1]}
    return "(?:" + "|".join(re.escape(x) for x in sorted(alts, key=len, reverse=True)) + ")"


def _root_re(root: str) -> str | None:
    parts = [x for x in re.split(r"[\\/]+", root.strip()) if x]
    if not parts or (len(parts) == 1 and parts[0].endswith(":")):
        return None                                      # never scrub "/" or a bare drive
    lead = _SEP_RE if root.strip()[:1] in "\\/" else ""
    return lead + _SEP_RE.join(_component_re(x) for x in parts)


def _scrub_rules(repo=None, models_dir=None) -> list[tuple[re.Pattern, str]]:
    roots = dict(_SCRUB_ROOTS)
    if repo:
        roots[str(repo)] = "<KK_REPO>"
    if models_dir:
        roots[str(models_dir)] = "<MODELS_DIR>"
    for h in _home_roots():
        roots.setdefault(h, "<HOME>")
    return _compile_rules(tuple(sorted(roots.items())))


@functools.lru_cache(maxsize=64)
def _compile_rules(items: tuple) -> list[tuple[re.Pattern, str]]:
    roots = dict(items)
    rules = []
    for root in sorted(roots, key=lambda r: len(r.strip().rstrip("\\/")), reverse=True):   # most specific first
        rx = _root_re(root)
        if rx:
            rules.append((re.compile(r"(?<![\w.\-])" + rx + r"(?![\w.\-])", re.I), roots[root]))
    # Safety net for a home that is not the current user's (e.g. a copied path): <drive>:<sep>Users<sep><profile>.
    rules.append((re.compile(r"(?<![\w.\-])[A-Za-z]:" + _SEP_RE + r"Users" + _SEP_RE + r"(?:(?!\\u005c|%5c|%2f)[^\\/\"'<>|*?\r\n])+", re.I),
                  "<HOME>"))
    return rules


def scrub_text(text: str, repo=None, models_dir=None, _rules=None) -> str:
    for rx, ph in (_rules if _rules is not None else _scrub_rules(repo, models_dir)):
        text = rx.sub(ph, text)
    return text


def scrub_paths(obj, repo=None, models_dir=None, _rules=None):
    """Recursively replace home / repo / models directories in every string (values and keys) of obj."""
    rules = _rules if _rules is not None else _scrub_rules(repo, models_dir)
    if isinstance(obj, str):
        return scrub_text(obj, _rules=rules)
    if isinstance(obj, dict):
        return {(scrub_text(k, _rules=rules) if isinstance(k, str) else k): scrub_paths(v, _rules=rules)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [scrub_paths(v, _rules=rules) for v in obj]
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return scrub_text(str(obj), _rules=rules)          # Path and anything json would stringify via default=str


def dump_json(obj, repo=None, models_dir=None, indent=1, **kw) -> str:
    """The one serializer for everything written to disk: scrubbed, UTF-8 (ensure_ascii=False)."""
    return json.dumps(scrub_paths(obj, repo, models_dir), ensure_ascii=False, indent=indent, **kw)


class _ScrubStream:
    """stdout/stderr wrapper: run_cv_matrix.ps1 tees console output into *.console.log / *.txt files."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        self._stream.write(scrub_text(text) if isinstance(text, str) else text)
        return len(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_output_scrubber() -> None:
    for name in ("stdout", "stderr"):
        cur = getattr(sys, name)
        if cur is not None and not isinstance(cur, _ScrubStream):
            setattr(sys, name, _ScrubStream(cur))



# ------------------------------------------------- native (fd-level) console scrubbing
# llama.cpp / ggml write straight to fd 1/2 from C (printf, fputs, write), bypassing sys.stdout. While a
# bench's main() runs, fds 1 and 2 point at pipes; one reader thread per fd reads 64 KiB chunks, cuts at
# the last newline (a partial line waits for its newline, max 64 KiB, and is flushed at the end), runs the
# same scrub_text() and writes to the saved original fd (console / Tee-Object). Children that inherit
# fd 1/2 go through it as well. Set KK_BENCH_NATIVE_SCRUB=0 to disable (debugging only).
_NATIVE_CAPTURE_ACTIVE = False
_PUMP_CHUNK = 1 << 16


@functools.lru_cache(maxsize=1)
def _c_runtimes() -> tuple:
    libs = []
    names = ("ucrtbase", "msvcrt") if IS_WIN else (None,)
    for name in names:
        with contextlib.suppress(Exception):
            lib = ctypes.CDLL(name)
            lib.fflush.argtypes = [ctypes.c_void_p]
            libs.append(lib)
    return tuple(libs)


def c_fflush_all() -> None:
    """fflush(NULL) in every C runtime we can reach, so buffered printf output lands in the current fds."""
    for lib in _c_runtimes():
        with contextlib.suppress(Exception):
            lib.fflush(None)


def _scrub_bytes(b: bytes) -> bytes:
    try:
        text, enc = b.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:                       # e.g. ANSI code page output of a Windows DLL
        import locale
        enc = locale.getpreferredencoding(False) or "utf-8"
        text = b.decode(enc, "surrogateescape")
    return scrub_text(text).encode(enc, "surrogateescape")


def _make_pipe() -> tuple[int, int]:
    """Pipe with a large buffer (1 MiB) so a writer is not throttled by a briefly busy reader."""
    if IS_WIN:
        with contextlib.suppress(Exception):
            import _winapi
            import msvcrt
            rh, wh = _winapi.CreatePipe(None, 1 << 20)
            return msvcrt.open_osfhandle(rh, os.O_RDONLY), msvcrt.open_osfhandle(wh, 0)
        return os.pipe()
    r, w = os.pipe()
    with contextlib.suppress(Exception):
        import fcntl
        fcntl.fcntl(w, 1031, 1 << 20)                # F_SETPIPE_SZ (Linux); ignored elsewhere
    return r, w


def _pump(r: int, out_fd: int) -> None:
    buf, alive = b"", True

    def emit(data: bytes) -> None:
        nonlocal alive
        data = _scrub_bytes(data)
        while alive and data:
            try:
                data = data[os.write(out_fd, data):]
            except OSError:                          # console/Tee gone: keep draining so writers never block
                alive = False
    try:
        while True:
            chunk = os.read(r, _PUMP_CHUNK)
            if not chunk:
                break
            buf += chunk
            cut = buf.rfind(b"\n") + 1
            if not cut and len(buf) >= _PUMP_CHUNK:
                cut = len(buf)
            if cut:
                emit(buf[:cut])
                buf = buf[cut:]
    except OSError:
        pass
    finally:
        if buf:
            emit(buf)
        with contextlib.suppress(OSError):
            os.close(r)


@contextlib.contextmanager
def scrub_native_output(fds=(1, 2)):
    """Route everything written to fds 1/2 (Python, C stdio, write(2), inheriting children) through scrub_text."""
    global _NATIVE_CAPTURE_ACTIVE
    if _NATIVE_CAPTURE_ACTIVE or os.environ.get("KK_BENCH_NATIVE_SCRUB", "1") == "0":
        yield
        return
    saved: list[tuple[int, int, threading.Thread]] = []

    def flush_all():
        for st in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
            with contextlib.suppress(Exception):
                st.flush()
        c_fflush_all()
    flush_all()
    try:
        for fd in fds:
            try:
                orig = os.dup(fd)
            except OSError:                          # fd not open (e.g. pythonw): nothing to capture
                continue
            r, w = _make_pipe()
            os.dup2(w, fd)
            os.close(w)
            t = threading.Thread(target=_pump, args=(r, orig), name=f"scrub-fd{fd}", daemon=True)
            t.start()
            saved.append((fd, orig, t))
        _NATIVE_CAPTURE_ACTIVE = True
        yield
    finally:
        flush_all()
        for fd, orig, _t in saved:
            os.dup2(orig, fd)                        # drops the last write end -> reader sees EOF
        for _fd, orig, t in saved:
            t.join(timeout=10)                       # bounded: a child still holding the pipe cannot hang us
            if not t.is_alive():
                os.close(orig)
        _NATIVE_CAPTURE_ACTIVE = False


def run_scrubbed(fn, *args):
    """Entry wrapper for the benches' main(): Python + native console output, the SystemExit message and an
    uncaught traceback (both printed by the interpreter AFTER main otherwise) all go through scrub_text."""
    install_output_scrubber()
    with scrub_native_output():
        try:
            return fn(*args)
        except SystemExit as exc:
            if exc.code is None or isinstance(exc.code, int):
                raise
            print(exc.code, file=sys.stderr)         # what the interpreter would print, exit status 1 as before
            raise SystemExit(1) from None
        except KeyboardInterrupt:
            traceback.print_exc()
            raise SystemExit(130) from None
        except Exception:  # noqa: BLE001 - printed scrubbed, exit status 1 as for an uncaught exception
            traceback.print_exc()
            raise SystemExit(1) from None


def cmdline_str(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd) if IS_WIN else shlex.join(cmd)


def run_capture(cmd: list[str], timeout: float = 60, cwd: str | None = None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           encoding="utf-8", errors="replace")
        return (r.stdout + r.stderr).strip()
    except Exception as exc:  # noqa: BLE001 - recorded, not fatal
        return f"ERROR: {exc!r}"


# ---------------------------------------------------------------- sysinfo
def cpu_name() -> str:
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def system_info() -> dict:
    vm = psutil.virtual_memory()
    bat = None
    try:
        b = psutil.sensors_battery()
        bat = None if b is None else {"power_plugged": b.power_plugged, "percent": b.percent,
                                       "secsleft": b.secsleft if isinstance(b.secsleft, int) else str(b.secsleft)}
    except Exception:  # noqa: BLE001
        bat = "unavailable"
    freq = None
    try:
        f = psutil.cpu_freq()
        freq = f._asdict() if f else None
    except Exception:  # noqa: BLE001
        pass
    procs = list(psutil.process_iter(["name", "pid"]))
    for p in procs:
        with contextlib.suppress(psutil.Error):
            p.cpu_percent(None)
    sys_cpu = psutil.cpu_percent(interval=1.0)
    top = []
    for p in procs:
        try:
            top.append((p.cpu_percent(None), p.info.get("name"), p.memory_info().rss))
        except psutil.Error:
            pass
    top_cpu = [{"cpu_percent": c, "name": n, "rss_bytes": r}
               for c, n, r in sorted(top, key=lambda t: t[0] or 0, reverse=True)[:8]]
    top_rss = [{"rss_bytes": r, "name": n} for c, n, r in sorted(top, key=lambda t: t[2] or 0, reverse=True)[:8]]
    info = {
        "hostname": "<HOSTNAME>", "os": platform.platform(), "os_version": platform.version(),
        "python": sys.version, "python_executable": sys.executable, "cpu": cpu_name(),
        "cores_physical": psutil.cpu_count(logical=False), "threads_logical": psutil.cpu_count(logical=True),
        "cpu_freq_mhz": freq, "ram_total_bytes": vm.total, "ram_available_bytes": vm.available,
        "swap": psutil.swap_memory()._asdict(),
        "battery_ac": bat, "system_cpu_percent_1s": sys_cpu,
        "top_processes_cpu_1s": top_cpu, "top_processes_rss": top_rss,
        "env_llama_ggml_omp": {k: v for k, v in os.environ.items() if k.startswith(("LLAMA_", "GGML_", "OMP_"))},
        "env_karrierekrake_at_start": {k: v for k, v in os.environ.items() if k.startswith("KARRIEREKRAKE_")},
    }
    if IS_WIN:
        info["powercfg_active_scheme"] = run_capture(["powercfg", "/getactivescheme"])
        info["powercfg_battery_ac_line"] = run_capture(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -ClassName Win32_Battery | Select-Object -Property BatteryStatus,"
             "EstimatedChargeRemaining | ConvertTo-Json -Compress)"], timeout=30)
    return info


# ------------------------------------------------------------- power state
# Kritiker rule: power scheme (GUID + name) and AC status are recorded with the speed numbers and must be unchanged
# across the baseline and all variants of a session; AC must be connected. This module only READS the state
# (powercfg /getactivescheme, GetSystemPowerStatus / psutil). It never changes the power plan.
POWER_EXIT = 5
_GUID_RE = r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"


def parse_powercfg_active(text: str) -> tuple:
    """'Power Scheme GUID: 381b4222-...  (Ausbalanciert)' (any UI language) -> (guid, name)."""
    import re
    m = re.search(_GUID_RE + r"\s*(?:\((.*)\))?", text or "")
    if not m:
        return None, None
    return m.group(1).lower(), (m.group(2).strip() if m.group(2) else None)


def read_power_scheme() -> dict:
    if not IS_WIN:
        return {"scheme_guid": None, "scheme_name": None, "scheme_source": "unavailable (not Windows)"}
    try:
        r = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, timeout=30)
        try:
            cp = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except Exception:  # noqa: BLE001
            cp = "cp850"
        raw = (r.stdout or b"").decode(cp, "replace").strip()
        guid, name = parse_powercfg_active(raw)
        # Windows 11 "power mode" slider = overlay scheme (read-only query; older builds do not know the switch -> None)
        o = subprocess.run(["powercfg", "/getactiveoverlayscheme"], capture_output=True, timeout=30)
        oraw = (o.stdout or b"").decode(cp, "replace").strip()
        oguid, _ = parse_powercfg_active(oraw) if o.returncode == 0 else (None, None)
        return {"scheme_guid": guid, "scheme_name": name, "overlay_guid": oguid,
                "scheme_source": "powercfg /getactivescheme + /getactiveoverlayscheme", "scheme_raw": raw,
                "overlay_raw": oraw[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"scheme_guid": None, "scheme_name": None, "scheme_source": f"ERROR {exc!r}"}


def read_ac_status() -> dict:
    if IS_WIN:
        try:
            class SPS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                            ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            st = SPS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
                ac = {0: False, 1: True}.get(st.ACLineStatus)          # 255 = unknown -> None
                pct = None if st.BatteryLifePercent == 255 else int(st.BatteryLifePercent)
                return {"ac_online": ac, "battery_percent": pct, "battery_flag": int(st.BatteryFlag),
                        "ac_source": "GetSystemPowerStatus"}
        except Exception:  # noqa: BLE001
            pass
    try:
        b = psutil.sensors_battery()
        if b is not None:
            return {"ac_online": bool(b.power_plugged) if b.power_plugged is not None else None,
                    "battery_percent": round(b.percent), "ac_source": "psutil.sensors_battery"}
    except Exception:  # noqa: BLE001
        pass
    return {"ac_online": None, "battery_percent": None, "ac_source": "unavailable"}


def power_state(readers=None) -> dict:
    """readers = (scheme_reader, ac_reader); injectable for tests."""
    rs, ra = readers or (read_power_scheme, read_ac_status)
    return {"t": now_iso(), **rs(), **ra()}


def power_problems(ref: dict, cur: dict) -> list[str]:
    """Differences that invalidate a session. Battery percent alone is NOT compared (it may drift on AC)."""
    out = []
    if cur.get("ac_online") is not True:
        out.append(f"AC not connected (ac_online={cur.get('ac_online')}, battery {cur.get('battery_percent')} %)")
    for k in ("scheme_guid", "scheme_name", "overlay_guid", "ac_online"):
        if ref.get(k) != cur.get(k):
            out.append(f"{k} changed: session start {ref.get(k)!r} -> now {cur.get(k)!r}")
    if cur.get("scheme_guid") is None:
        out.append("active power scheme could not be read")
    return out


class PowerGuard:
    """Records power samples for one variant and decides power_state_consistent.

    mode 'on' = enforce (abort on any problem), 'record' = record only (box / non-Windows: verdict None).
    """

    def __init__(self, mode: str, ref: dict | None, ref_source: str, readers=None):
        self.mode, self.readers = mode, readers
        self.ref = ref
        self.ref_source = ref_source
        self.samples: list[dict] = []
        self.problems: list[dict] = []

    def sample(self, where: str) -> list[str]:
        cur = power_state(self.readers)
        if self.ref is None:
            self.ref, self.ref_source = dict(cur), "variant start (no --power-ref)"
        probs = power_problems(self.ref, cur)
        self.samples.append({"where": where, **cur, "problems": probs})
        if probs:
            self.problems.append({"where": where, "problems": probs})
        return probs if self.mode == "on" else []

    @property
    def consistent(self):
        if self.mode != "on":
            return None
        return not self.problems

    def record(self) -> dict:
        return {"check_mode": self.mode, "reference": self.ref, "reference_source": self.ref_source,
                "power_state_consistent": self.consistent, "problems": self.problems, "samples": self.samples,
                "note": "read-only; the harness never changes the power plan"}


def load_power_ref(path) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d.get("reference", d)


def llama_info() -> dict:
    import llama_cpp
    d: dict = {"llama_cpp_python_version": llama_cpp.__version__, "module": llama_cpp.__file__}
    try:
        d["system_info"] = llama_cpp.llama_print_system_info().decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001
        d["system_info"] = f"ERROR {exc!r}"
    libdir = Path(llama_cpp.__file__).resolve().parent / "lib"
    d["lib_files"] = sorted(p.name for p in libdir.iterdir()) if libdir.is_dir() else []
    d["lib_sha256"] = {}
    for name in d["lib_files"]:
        if name.endswith((".dll", ".so", ".dylib")) or ".so." in name:
            p = libdir / name
            if p.is_file() and not p.is_symlink():
                d["lib_sha256"][name] = sha256_file(p)
    base = next((libdir / n for n in ("ggml-base.dll", "libggml-base.so", "libggml-base.dylib")
                 if (libdir / n).exists()), None)
    if base is not None:
        try:
            lib = ctypes.CDLL(str(base))
            for fn in ("ggml_commit", "ggml_version"):
                f = getattr(lib, fn)
                f.restype = ctypes.c_char_p
                d[fn] = f().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            d["ggml_commit_error"] = repr(exc)
    d["vendored_llama_cpp_commit_expected"] = PINNED_LLAMA_CPP_COMMIT
    d["vendored_llama_cpp_commit_matches"] = bool(d.get("ggml_commit", "").startswith(PINNED_LLAMA_CPP_COMMIT[:7]))
    d["llama_default_seed"] = getattr(llama_cpp, "LLAMA_DEFAULT_SEED", None)
    try:
        import importlib.metadata as md
        d["dist_versions"] = {n: md.version(n) for n in ("llama-cpp-python", "numpy", "jinja2", "diskcache",
                                                          "docpick", "pypdf", "python-docx", "psutil", "pydantic", "httpx")
                              if _has_dist(md, n)}
        files = md.distribution("llama-cpp-python").read_text("direct_url.json")
        d["direct_url"] = json.loads(files) if files else None
    except Exception as exc:  # noqa: BLE001
        d["dist_error"] = repr(exc)
    d["windows_wheel_reference"] = WIN_WHEEL
    return d


def _has_dist(md, name: str) -> bool:
    try:
        md.version(name)
        return True
    except md.PackageNotFoundError:
        return False


def repo_info(repo: Path, override: str | None) -> dict:
    d: dict = {"path": str(repo)}
    head = run_capture(["git", "rev-parse", "HEAD"], cwd=str(repo))
    if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
        d["commit"] = head
        d["commit_source"] = "git rev-parse HEAD"
        d["dirty_files"] = [ln for ln in run_capture(["git", "status", "--porcelain"], cwd=str(repo)).splitlines() if ln]
        d["branch"] = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo))
    elif (repo / "REPO_COMMIT").is_file():
        d["commit"] = (repo / "REPO_COMMIT").read_text(encoding="utf-8").split()[0]
        d["commit_source"] = "REPO_COMMIT file (git archive snapshot)"
        d["dirty_files"] = None
    if override:
        if d.get("commit") and d["commit"] != override:
            raise SystemExit(f"--repo-commit {override} != repo commit {d['commit']}")
        d.setdefault("commit", override)
        d.setdefault("commit_source", "--repo-commit")
    key_files = ["core/cv_llm_runtime.py", "core/cv_docpick_import.py", "core/local_chat_template.py",
                 "guenther/runtime/llama_cpp_provider.py", "constraints-runtime.txt",
                 "tests/fixtures/cv_corpus/expected_results.json"]
    d["key_file_sha256"] = {f: sha256_file(repo / f) for f in key_files if (repo / f).is_file()}
    return d


# ---------------------------------------------------------- memory sampler
def _linux_rss_anon() -> int:
    try:
        with open("/proc/self/status", "rb") as fh:
            for line in fh:
                if line.startswith(b"RssAnon:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


class SelfSampler:
    """Polls this process: RSS and private bytes (Windows: PagefileUsage /
    psutil 'private'; Linux: RssAnon). Reset per run."""

    def __init__(self, interval_s: float):
        self.proc = psutil.Process(os.getpid())
        self.interval = interval_s
        self._stop = threading.Event()
        self.reset()
        self._t = threading.Thread(target=self._loop, name="kk-mem-sampler", daemon=True)
        self._t.start()

    def reset(self) -> None:
        self.max_rss = 0
        self.max_private = 0
        self.samples = 0
        self.max_gap_s = 0.0
        self._last = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                mi = self.proc.memory_info()
                rss = mi.rss
                priv = getattr(mi, "private", 0) if IS_WIN else _linux_rss_anon()
            except psutil.Error:
                rss = priv = 0
            now = time.perf_counter()
            if self._last is not None:
                self.max_gap_s = max(self.max_gap_s, now - self._last)
            self._last = now
            self.max_rss = max(self.max_rss, rss)
            self.max_private = max(self.max_private, priv or 0)
            self.samples += 1
            self._stop.wait(self.interval)

    def peak_wset(self) -> int | None:
        try:
            return getattr(self.proc.memory_info(), "peak_wset", None)
        except psutil.Error:
            return None

    def cpu_seconds(self) -> float:
        t = self.proc.cpu_times()
        return t.user + t.system

    def stop(self) -> None:
        self._stop.set()
        self._t.join(timeout=2)


# ---------------------------------------------------------- pre-flight
CONCURRENT_NAME_HINTS = ("python", "pythonw", "py.exe", "llama", "karrierekrake")


def other_python_llama_processes() -> list[dict]:
    """Other python / llama.cpp / Karrierekrake processes (excluding this process and its parents,
    e.g. the launching PowerShell/py.exe). A parallel letter run would show up here."""
    me = psutil.Process(os.getpid())
    skip = {me.pid}
    with contextlib.suppress(psutil.Error):
        skip |= {p.pid for p in me.parents()}
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] in skip:
                continue
            name = (p.info.get("name") or "").lower()
            if any(h in name for h in CONCURRENT_NAME_HINTS):
                found.append({"pid": p.info["pid"], "name": p.info.get("name"),
                              "cmdline": " ".join(p.info.get("cmdline") or [])[:300]})
        except psutil.Error:
            pass
    return found


# ----------------------------------------------------------- instrumentation
class Bench:
    """Per-session state shared by the hooks. One `current_run` at a time."""

    def __init__(self, a):
        self.a = a
        self.current_run: dict | None = None
        self.prefix_cache = None              # llama_cpp.LlamaRAMCache when --prefix-cache ram
        self.prefix_stats: list[dict] = []

    def call(self) -> dict | None:
        if self.current_run is None or not self.current_run["llm_calls"]:
            return None
        return self.current_run["llm_calls"][-1]


def install_hooks(B: Bench):
    """Patch module attributes the product resolves at call time. Baseline hooks
    only observe; variant hooks are added only when the variant asks for them."""
    import llama_cpp
    from core import cv_llm_runtime as rt
    from core import local_chat_template as lct

    a = B.a
    hooks = {"observe": [], "variant": []}

    # Force in-process transport (core/cv_llm_runtime.py:737-764).
    rt.http_llm_available = lambda *args, **kw: False
    hooks["observe"].append("core.cv_llm_runtime.http_llm_available -> False (in-process transport, no server)")

    # --- observe chat_completion_inprocess (core/cv_llm_runtime.py:1069) -----
    orig_cci = rt.chat_completion_inprocess

    def cci(messages, *, model_path, temperature=0.0):
        run = B.current_run
        rec = {"index": len(run["llm_calls"]) + 1 if run else 0, "t_call0": time.perf_counter(),
               "temperature": temperature, "model_path": str(model_path),
               "messages_sha256": sha256_text(json.dumps(messages, ensure_ascii=False, sort_keys=True)),
               "kind": "primary_extract" if any(DOC_MARKER in (m.get("content") or "") for m in messages)
               else "focused_retry", "messages": messages}
        if run is not None:
            run["llm_calls"].append(rec)
        try:
            text = orig_cci(messages, model_path=model_path, temperature=temperature)
            rec["ok"] = True
            rec["raw_text"] = text
            return text
        except BaseException as exc:
            rec["ok"] = False
            rec["error"] = f"{type(exc).__name__}: {getattr(exc, 'code', '')} {exc}"
            raise
        finally:
            rec["t_call1"] = time.perf_counter()
            rec["llm_step"] = rt.last_llm_step_metrics()

    rt.chat_completion_inprocess = cci
    hooks["observe"].append("core.cv_llm_runtime.chat_completion_inprocess wrapped (timestamps, raw text)")

    orig_budget = rt.completion_token_budget

    def budget(n_ctx, n_prompt):
        v = orig_budget(n_ctx, n_prompt)
        c = B.call()
        if c is not None:
            c.update(n_ctx=int(n_ctx), n_prompt=int(n_prompt), max_tokens_budget=int(v))
        return v

    rt.completion_token_budget = budget
    hooks["observe"].append("core.cv_llm_runtime.completion_token_budget wrapped (records n_prompt/max_tokens)")

    # --- Llama subclass (core/cv_llm_runtime.py:191-194, 856-874) ----------
    Base = llama_cpp.Llama
    spec = a.spec
    lookup_cls = None
    if spec == "prompt-lookup":
        from llama_cpp.llama_speculative import LlamaPromptLookupDecoding as lookup_cls

    class CountingLookup(lookup_cls or object):  # type: ignore[misc]
        def __call__(self, input_ids, /, **kw):
            out = super().__call__(input_ids, **kw)
            c = B.call()
            if c is not None:
                c["spec_draft_calls"] = c.get("spec_draft_calls", 0) + 1
                c["spec_draft_tokens_proposed"] = c.get("spec_draft_tokens_proposed", 0) + int(len(out))
            return out

    class BenchLlama(Base):
        def __init__(self, *args, **kwargs):
            c = B.call()
            if spec == "prompt-lookup":
                kwargs["draft_model"] = CountingLookup(max_ngram_size=a.spec_ngram, num_pred_tokens=a.spec_num_pred)
                # llama-cpp-python 0.3.35 bug: draft_model forces self._logits_all=True (llama.py:351) but sizes
                # self.scores from the *argument* logits_all (llama.py:484-486) -> n_batch rows only -> ValueError
                # in eval() as soon as the prompt exceeds n_batch (512) tokens, i.e. on every CV. Passing
                # logits_all=True explicitly allocates n_ctx x n_vocab float32 (4096 x 248320 x 4 B = 4.07 GB virtual).
                if a.spec_logits_all:
                    kwargs["logits_all"] = True
            if a.seed is not None:
                kwargs["seed"] = int(a.seed)     # same value must be used for baseline and spec variant
            t0 = time.perf_counter()
            super().__init__(*args, **kwargs)
            if c is not None:
                c["t_load0"], c["t_load1"] = t0, time.perf_counter()
                c["llama_kwargs"] = {k: (v if isinstance(v, (int, float, str, bool, type(None))) else type(v).__name__)
                                     for k, v in kwargs.items()}
                c["llama_effective"] = {"n_ctx": self.n_ctx(), "n_batch": self.n_batch,
                                        "n_ubatch": self.context_params.n_ubatch,
                                        "n_threads": self.context_params.n_threads,
                                        "n_threads_batch": self.context_params.n_threads_batch,
                                        "logits_all": bool(self._logits_all), "seed": self._seed,
                                        "is_hybrid": bool(getattr(self, "_is_hybrid", False)),
                                        "is_recurrent": bool(getattr(self, "_is_recurrent", False)),
                                        "n_vocab": self.n_vocab()}

        def create_chat_completion(self, *args, **kwargs):
            c = B.call()
            if c is not None:
                c["chat_kwargs"] = {k: v for k, v in kwargs.items() if k != "messages"}
                c["t_chat0"] = time.perf_counter()
            res = super().create_chat_completion(*args, **kwargs)
            if not kwargs.get("stream"):
                return res

            def gen():
                first = True
                n = 0
                pieces = []
                for chunk in res:
                    if first and c is not None:
                        c["t_first_chunk"] = time.perf_counter()
                        first = False
                    n += 1
                    with contextlib.suppress(Exception):
                        piece = (chunk["choices"][0].get("delta") or {}).get("content")
                        if piece:
                            pieces.append(piece)
                    yield chunk
                if c is not None:
                    c["t_last_chunk"] = time.perf_counter()
                    c["stream_chunks"] = n
                    # Emitted answer tokens (same count as core/cv_llm_runtime.py:_count_answer_tokens).
                    # llama_perf n_eval is NOT the emitted count under --spec: multi-token verification
                    # batches are booked as prompt eval there.
                    with contextlib.suppress(Exception):
                        c["answer_tokens"] = len(self.tokenize("".join(pieces).encode("utf-8"),
                                                               add_bos=False, special=True))
            return gen()

    rt._llama_cls = lambda: BenchLlama
    hooks["observe"].append("core.cv_llm_runtime._llama_cls -> BenchLlama(Llama) (timestamps only)")
    if spec == "prompt-lookup":
        hooks["variant"].append(f"Llama(draft_model=LlamaPromptLookupDecoding(max_ngram_size={a.spec_ngram}, "
                                f"num_pred_tokens={a.spec_num_pred})" + (", logits_all=True" if a.spec_logits_all else "")
                                + ") (draft_model forces internal logits_all=True)")

    # --- prefill hook (core/cv_llm_runtime.py:612-654, called at 1239-1242) --
    orig_prefill = rt._prefill_prompt_blocks

    def prefill(llm, token_ids, *, origin):
        c = B.call()
        if c is not None:
            c["prompt_ids_sha256"] = sha256_text(",".join(map(str, token_ids)))
            c["t_prefill0"] = time.perf_counter()
        try:
            if B.prefix_cache is None or c is None or c.get("kind") != "primary_extract":
                return orig_prefill(llm, token_ids, origin=origin)
            return prefix_cached_prefill(B, llm, list(token_ids), origin, orig_prefill, c)
        finally:
            if c is not None:
                c["t_prefill1"] = time.perf_counter()

    rt._prefill_prompt_blocks = prefill
    hooks["observe"].append("core.cv_llm_runtime._prefill_prompt_blocks wrapped (timestamps)")
    if a.prefix_cache == "ram":
        B.prefix_cache = llama_cpp.LlamaRAMCache(capacity_bytes=int(a.cache_capacity_mb) << 20)
        hooks["variant"].append(f"prefix state cache: llama_cpp.LlamaRAMCache({a.cache_capacity_mb} MiB), "
                                "restore at end of '## Document Text\\n' prefix, in-process only")

    # --- thinking switch (core/local_chat_template.py:9-33) ----------------
    if a.thinking == "on":
        orig_cfg = lct.configure_non_thinking_chat

        def cfg_thinking_on(llm):
            metadata = getattr(llm, "metadata", None) or {}
            template = metadata.get("tokenizer.chat_template")
            if not isinstance(template, str) or "enable_thinking" not in template:
                return False
            from llama_cpp.llama_chat_format import Jinja2ChatFormatter
            template = "{% set enable_thinking = true %}" + template
            eos_id, bos_id = int(llm.token_eos()), int(llm.token_bos())
            model = llm._model
            fmt = Jinja2ChatFormatter(template=template,
                                      eos_token=model.token_get_text(eos_id) if eos_id != -1 else "",
                                      bos_token=model.token_get_text(bos_id) if bos_id != -1 else "",
                                      stop_token_ids=[eos_id])
            llm.chat_handler = fmt.to_chat_handler()
            llm.metadata = dict(metadata, **{"tokenizer.chat_template": template})
            return True

        cfg_thinking_on.__wrapped__ = orig_cfg
        lct.configure_non_thinking_chat = cfg_thinking_on
        hooks["variant"].append("core.local_chat_template.configure_non_thinking_chat -> enable_thinking=true")
    return hooks


def _prefix_len(llm, token_ids: list[int]) -> int:
    """Token count of the shared prefix (everything up to and incl. DOC_MARKER),
    minus one token so a merge across the boundary can never be reused."""
    text = llm.detokenize(token_ids, special=True).decode("utf-8", "replace")
    idx = text.find(DOC_MARKER)
    if idx < 0:
        return 0
    pre = llm.tokenize(text[: idx + len(DOC_MARKER)].encode("utf-8"), add_bos=False, special=True)
    n = 0
    for x, y in zip(pre, token_ids):
        if x != y:
            break
        n += 1
    return max(0, n - 1)


def prefix_cached_prefill(B: Bench, llm, token_ids, origin, orig_prefill, c) -> bool:
    P = _prefix_len(llm, token_ids)
    key = tuple(token_ids[:P])
    st = {"prefix_tokens": P, "prompt_tokens": len(token_ids)}
    cache = B.prefix_cache
    if P > 0 and key in cache.cache_state:
        t = time.perf_counter()
        state = cache.cache_state[key]
        cache.cache_state.move_to_end(key)
        llm.load_state(state)
        st.update(hit=True, restore_s=round(time.perf_counter() - t, 4), state_bytes=int(state.llama_state_size))
        ok = orig_prefill(llm, token_ids[P:], origin=origin) if len(token_ids) > P else True
    else:
        st["hit"] = False
        if P > 0:
            orig_prefill(llm, token_ids[:P], origin=origin)
            t = time.perf_counter()
            state = llm.save_state()
            cache[key] = state
            st.update(save_s=round(time.perf_counter() - t, 4), state_bytes=int(state.llama_state_size))
        ok = orig_prefill(llm, token_ids[P:], origin=origin)
    st["cache_entries"] = len(cache.cache_state)
    st["cache_bytes"] = int(cache.cache_size)
    c["prefix_cache"] = st
    return bool(ok)


# --------------------------------------------------------------- run
def corpus_documents(repo: Path) -> list[tuple[str, dict]]:
    exp = json.loads((repo / "tests/fixtures/cv_corpus/expected_results.json").read_text(encoding="utf-8"))
    return list(exp["documents"].items())


def load_corpus_evaluator(repo: Path):
    p = repo / "scripts" / "run_cv_corpus.py"
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location("kk_run_cv_corpus", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "evaluate_doc", None)


def normalise_parsed(parsed: dict) -> tuple[dict, dict]:
    p = dict(parsed)
    vol = {k: p.pop(k) for k in VOLATILE_PARSED_KEYS if k in p}
    if "source_path" in vol:
        p["source_path"] = str(vol["source_path"]).replace("\\", "/").rsplit("/", 1)[-1]
    return p, vol


def _r(x, n=4):
    return None if x is None else round(x, n)


def call_metrics(c: dict) -> dict:
    step = c.get("llm_step") or {}
    m = {
        "index": c.get("index"), "kind": c.get("kind"), "ok": c.get("ok"), "error": c.get("error"),
        "call_wall_s": _r(c["t_call1"] - c["t_call0"]) if "t_call1" in c else None,
        "load_s": _r(c["t_load1"] - c["t_load0"]) if "t_load1" in c else None,
        "ttft_from_call_s": _r(c["t_first_chunk"] - c["t_call0"]) if "t_first_chunk" in c else None,
        "ttft_from_loaded_s": _r(c["t_first_chunk"] - c["t_load1"]) if "t_first_chunk" in c and "t_load1" in c else None,
        "prefill_wall_s": _r(c["t_prefill1"] - c["t_prefill0"]) if "t_prefill1" in c else None,
        # n_prompt / prefill wall time (incl. a prefix-state restore). llama_perf (pp_tok_s) counts only the
        # tokens evaluated after the last state save/restore, so for --prefix-cache use this one.
        "pp_tok_s_wall": (round(c["n_prompt"] / (c["t_prefill1"] - c["t_prefill0"]), 3)
                          if c.get("n_prompt") and "t_prefill1" in c and c["t_prefill1"] > c["t_prefill0"] else None),
        "gen_wall_s": _r(c["t_last_chunk"] - c["t_first_chunk"]) if "t_last_chunk" in c and "t_first_chunk" in c else None,
        "n_prompt": c.get("n_prompt"), "n_ctx": c.get("n_ctx"), "max_tokens_budget": c.get("max_tokens_budget"),
        "prompt_tokens_evaluated": step.get("prompt_tokens"), "prompt_eval_s": step.get("prompt_eval_s"),
        "pp_tok_s": step.get("prompt_tok_per_s"),
        "gen_tokens": step.get("gen_tokens"), "gen_s": step.get("gen_s"), "tg_tok_s": step.get("gen_tok_per_s"),
        "answer_tokens": c.get("answer_tokens"),
        "tg_tok_s_wall": (round((c.get("answer_tokens") or step.get("gen_tokens") or 0) / (c["t_last_chunk"] - c["t_first_chunk"]), 3)
                          if "t_last_chunk" in c and "t_first_chunk" in c and c["t_last_chunk"] > c["t_first_chunk"] else None),
        "timing_source": step.get("timing_source"), "n_threads_step": step.get("n_threads"),
        "stream_chunks": c.get("stream_chunks"),
        "messages_sha256": c.get("messages_sha256"), "prompt_ids_sha256": c.get("prompt_ids_sha256"),
        "raw_sha256": sha256_text(c["raw_text"]) if c.get("raw_text") is not None else None,
        "llama_effective": c.get("llama_effective"), "llama_kwargs": c.get("llama_kwargs"),
        "chat_kwargs": c.get("chat_kwargs"),
    }
    for k in ("spec_draft_calls", "spec_draft_tokens_proposed", "prefix_cache"):
        if k in c:
            m[k] = c[k]
    return m


def run_one(B: Bench, a, repo: Path, cv_name: str, tag: str, sampler: SelfSampler, out: Path, evaluate_doc, expected):
    from core import cv_docpick_import as cdi
    path = repo / "tests/fixtures/cv_corpus" / cv_name
    run = {"cv": cv_name, "tag": tag, "kind": "warmup" if tag.startswith("warmup") else "measured",
           "llm_calls": [], "started": now_iso()}
    B.current_run = run
    sampler.reset()
    cpu0 = sampler.cpu_seconds()
    t0 = time.perf_counter()
    parsed = err = None
    try:
        if a.mode == "import":
            parsed = cdi.import_cv_docpick(path)
        else:   # llm: the primary extraction call only
            text = cdi.extract_cv_text(path)
            raw = cdi._llm_extract(text, transport="inprocess")
            parsed = {"_mode": "llm", "llm_json": raw}
    except BaseException as exc:  # noqa: BLE001 - recorded per run
        if isinstance(exc, KeyboardInterrupt):
            raise
        err = {"type": type(exc).__name__, "code": getattr(exc, "code", None), "message": str(exc),
               "detail": getattr(exc, "detail", None), "traceback": traceback.format_exc()[-4000:]}
    wall = time.perf_counter() - t0
    cpu1 = sampler.cpu_seconds()
    B.current_run = None
    stem = Path(cv_name).stem
    d = out / "extracts" / stem
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    for c in run["llm_calls"]:
        if c.get("raw_text") is not None:
            fn = f"{tag}.call{c['index']}.{c['kind']}.raw.txt"
            (d / fn).write_bytes(c["raw_text"].encode("utf-8"))
            files[f"call{c['index']}_raw"] = f"extracts/{stem}/{fn}"
    if parsed is not None:
        norm, vol = normalise_parsed(parsed)
        fn = f"{tag}.parsed.json"
        (d / fn).write_text(canon_json(norm), encoding="utf-8", newline="\n")
        files["parsed"] = f"extracts/{stem}/{fn}"
    else:
        vol = {}
        fn = f"{tag}.error.json"
        (d / fn).write_text(canon_json(scrub_paths(err, repo, Path(a.model).resolve().parent)), encoding="utf-8", newline="\n")
        files["error"] = f"extracts/{stem}/{fn}"
    for c in run["llm_calls"]:
        mp = d / f"_messages.{c['messages_sha256'][:16]}.json"
        if not mp.exists():
            mp.write_text(canon_json(c["messages"]), encoding="utf-8", newline="\n")
    calls = [call_metrics(c) for c in run["llm_calls"]]
    ok_calls = [c for c in calls if c.get("ok")]
    pp_tok = sum(c.get("prompt_tokens_evaluated") or 0 for c in ok_calls)
    pp_s = sum(c.get("prompt_eval_s") or 0 for c in ok_calls)
    tg_tok = sum(c.get("gen_tokens") or 0 for c in ok_calls)
    tg_s = sum(c.get("gen_s") or 0 for c in ok_calls)
    rec = {
        "cv": cv_name, "tag": tag, "kind": run["kind"], "ok": err is None, "error": err and {k: err[k] for k in ("type", "code", "message", "detail")},
        "wall_s": round(wall, 4), "n_llm_calls": len(calls),
        "ttft_s": calls[0]["ttft_from_call_s"] if calls else None,
        "ttft_from_loaded_s": calls[0]["ttft_from_loaded_s"] if calls else None,
        "load_s_total": _r(sum(c.get("load_s") or 0 for c in calls)),
        "pp_tok_s": round(pp_tok / pp_s, 3) if pp_s > 0 else None, "prompt_tokens_evaluated": pp_tok, "prompt_eval_s": _r(pp_s),
        "tg_tok_s": round(tg_tok / tg_s, 3) if tg_s > 0 else None, "gen_tokens": tg_tok, "gen_s": _r(tg_s),
        "pp_tok_s_wall": (round(sum(c.get("n_prompt") or 0 for c in ok_calls) / pw, 3)
                          if (pw := sum(c.get("prefill_wall_s") or 0 for c in ok_calls)) > 0 else None),
        "answer_tokens": sum(c.get("answer_tokens") or 0 for c in ok_calls),
        "tg_tok_s_wall": (round(sum((c.get("answer_tokens") or c.get("gen_tokens") or 0) for c in ok_calls) / gw, 3) if (gw := sum(c.get("gen_wall_s") or 0 for c in ok_calls)) > 0 else None),
        "peak_rss_bytes": sampler.max_rss, "peak_private_bytes": sampler.max_private or None,
        "mem_samples": sampler.samples, "mem_max_gap_s": round(sampler.max_gap_s, 4),
        "peak_wset_lifetime_bytes": sampler.peak_wset(),
        "product_private_commit_high_water_bytes": getattr(cdi, "_private_commit_high_water", None),
        "cpu_cores_effective": round((cpu1 - cpu0) / wall, 2) if wall > 0 else None,
        "parsed_sha256": sha256_bytes((d / f"{tag}.parsed.json").read_bytes()) if parsed is not None else None,
        "volatile": vol, "files": files, "llm_calls": calls,
    }
    if IS_WIN:
        with contextlib.suppress(Exception):
            rec["product_peak_job_memory_used_bytes"] = int(cdi.model_process_peak_job_memory_used_bytes())
    if evaluate_doc is not None and parsed is not None and a.mode == "import":
        try:
            ev = evaluate_doc(parsed, expected)
            rec["corpus_eval"] = {k: ("PASS" if v[0] else f"FAIL({v[1]})") for k, v in ev.items()}
            rec["corpus_pass"] = all(v[0] for v in ev.values())
        except Exception as exc:  # noqa: BLE001
            rec["corpus_eval_error"] = repr(exc)
    return rec


def prepare_env(a, out: Path) -> dict:
    cleared = {}
    for k in list(os.environ):
        if k.startswith("KARRIEREKRAKE_") and k not in OWN_ENV:
            cleared[k] = os.environ.pop(k)
    for k in OWN_ENV:
        os.environ.pop(k, None)
    sandbox = (out / "_sandbox").resolve()
    (sandbox / "models").mkdir(parents=True, exist_ok=True)
    (sandbox / "data").mkdir(parents=True, exist_ok=True)
    env = {
        "KARRIEREKRAKE_CV_LLM_MODEL": str(Path(a.model).resolve()),
        "KARRIEREKRAKE_MODELS_DIR": str(sandbox / "models"),   # model lock file lands here, not in the app's AppData
        "KARRIEREKRAKE_DATA_DIR": str(sandbox / "data"),
        "KARRIEREKRAKE_CV_LLM_BASE": "http://127.0.0.1:9/v1",  # discard port; transport is forced in-process anyway
    }
    if a.import_timeout_s is not None:
        env["KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S"] = str(a.import_timeout_s)
    if a.threads != "plan":
        env["KARRIEREKRAKE_CV_LLM_N_THREADS"] = str(int(a.threads))
    if a.threads_batch != "plan":
        env["KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH"] = str(int(a.threads_batch))
    if a.max_tokens is not None:
        env["KARRIEREKRAKE_CV_LLM_MAX_TOKENS"] = str(int(a.max_tokens))
    os.environ.update(env)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return {"set": env, "cleared_from_parent_env": cleared}


def text_changing(a) -> list[str]:
    t = []
    if a.spec != "off":
        t.append("spec")
    if a.prefix_cache != "off":
        t.append("prefix_cache")
    if a.thinking != "off":
        t.append("thinking")
    if a.max_tokens is not None:
        t.append("max_tokens")
    if a.threads != "plan" or a.threads_batch != "plan":
        t.append("threads (float reduction order can change)")
    t.append("model")  # model swaps always change text; recorded with sha256
    return t


def cmd_run(a) -> int:
    repo = Path(a.repo).resolve()
    out = Path(a.out).resolve() / a.label
    if out.exists() and any(out.iterdir()) and not a.overwrite:
        raise SystemExit(f"{out} exists; use --overwrite or a new --label")
    out.mkdir(parents=True, exist_ok=True)
    import llama_cpp
    if llama_cpp.__version__ != PINNED_LLAMA_CPP_PYTHON and not a.allow_other_llama:
        raise SystemExit(f"llama-cpp-python {llama_cpp.__version__} != pinned {PINNED_LLAMA_CPP_PYTHON} "
                         "(constraints-runtime.txt). Install the pinned wheel (README) or pass --allow-other-llama.")
    concurrent = other_python_llama_processes()
    if concurrent and (a.preflight == "on" or (a.preflight == "auto" and IS_WIN)):
        raise SystemExit("ABORT pre-flight: other python/llama processes are running (parallel letter run?): "
                         + json.dumps(concurrent, ensure_ascii=False) + "  (close them; --preflight off only for box tests)")
    envinfo = prepare_env(a, out)
    sys.path.insert(0, str(repo))
    rinfo = repo_info(repo, a.repo_commit)
    if not rinfo.get("commit"):
        raise SystemExit("repo commit unknown: run from a git checkout, a snapshot with REPO_COMMIT, or pass --repo-commit")
    if rinfo.get("dirty_files") and not a.allow_dirty:
        raise SystemExit(f"repo has local changes {rinfo['dirty_files'][:5]} ...; pass --allow-dirty to record them anyway")
    shacache_p = Path(a.out).resolve() / "_sha256_cache.json"
    shacache = json.loads(shacache_p.read_text()) if shacache_p.exists() else {}
    model = Path(a.model).resolve()
    register_scrub_root(repo, "<KK_REPO>")
    register_scrub_root(model.parent, "<MODELS_DIR>")
    register_scrub_root(Path(a.model).absolute().parent, "<MODELS_DIR>")
    model_sha = sha256_file(model, shacache)
    shacache_p.write_text(dump_json(shacache), encoding="utf-8")
    if a.expect_model_sha256 and a.expect_model_sha256.lower() != model_sha:
        raise SystemExit(f"model sha256 {model_sha} != expected {a.expect_model_sha256}")
    docs = corpus_documents(repo)
    if a.cvs:
        want = [s.strip() for s in a.cvs.split(",") if s.strip()]
        docs = [(n, e) for n, e in docs if any(n == w or n.startswith(w) for w in want)]
    if not docs:
        raise SystemExit("no CVs selected")
    B = Bench(a)
    hooks = install_hooks(B)
    from core import cv_llm_runtime as rt
    plan = rt.resolve_cv_llm_thread_plan()
    evaluate_doc = load_corpus_evaluator(repo)
    session = {
        "schema": SCHEMA, "label": a.label, "started": now_iso(), "repo_commit": rinfo["commit"], "repo": rinfo,
        "primary_measurement": "CV import (core/cv_llm_runtime.py in-process) - product path",
        "argv": sys.argv, "cmdline": cmdline_str([sys.executable, *sys.argv]), "cwd": os.getcwd(),
        "harness_sha256": sha256_file(Path(__file__)),
        "mode": a.mode, "variant": {
            "threads": a.threads, "threads_batch": a.threads_batch,
            "thread_plan_resolved": dict(zip(("n_threads", "n_threads_batch", "physical", "logical", "reserve"), plan)),
            "spec": a.spec, "spec_ngram": a.spec_ngram if a.spec != "off" else None,
            "spec_num_pred": a.spec_num_pred if a.spec != "off" else None,
            "prefix_cache": a.prefix_cache, "cache_capacity_mb": a.cache_capacity_mb if a.prefix_cache != "off" else None,
            "thinking": a.thinking, "max_tokens_cap": a.max_tokens,
            "is_baseline": a.spec == "off" and a.prefix_cache == "off" and a.thinking == "off" and a.max_tokens is None
            and a.threads == "plan" and a.threads_batch == "plan",
            "text_changing_axes": text_changing(a),
        },
        "model": {"path": str(model), "bytes": model.stat().st_size, "sha256": model_sha},
        "sampling": {"temperature": 0.0, "note": "product passes temperature=0.0 (core/cv_docpick_import.py:1319) -> "
                     "greedy; other create_chat_completion sampling args are llama-cpp-python defaults; "
                     "response_format json_object -> JSON grammar; seed = Llama default (see llama.llama_default_seed), "
                     "irrelevant for greedy", "harness_seed": a.seed},
        "preflight": {"mode": a.preflight, "other_python_llama_processes_at_start": concurrent},
        "env": envinfo, "hooks": hooks, "system": system_info(), "llama": llama_info(),
        "warmup": a.warmup, "runs_requested": a.runs, "cvs": [n for n, _ in docs], "notes": a.note,
        "runs": [],
    }
    if not session["llama"].get("vendored_llama_cpp_commit_matches"):
        print(f"WARNING: ggml_commit {session['llama'].get('ggml_commit')} != {PINNED_LLAMA_CPP_COMMIT[:7]}", flush=True)
    pmode = a.power_check if a.power_check != "auto" else ("on" if IS_WIN else "record")
    guard = PowerGuard(pmode, load_power_ref(a.power_ref) if a.power_ref else None,
                       str(Path(a.power_ref).resolve()) if a.power_ref else "")
    sampler = SelfSampler(a.poll_ms / 1000.0)
    sp = out / "session.json"
    power_abort = None

    def flush():
        session["power"] = guard.record()
        session["power_state_consistent"] = guard.consistent
        if power_abort:
            session["aborted"] = power_abort
        session["summary"] = summarize_session(session)
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(dump_json(session, repo, model.parent, default=str), encoding="utf-8")
        os.replace(tmp, sp)

    try:
        probs = guard.sample("variant start")
        flush()
        if probs:
            power_abort = "power state changed/AC missing at variant start - session does not count: " + "; ".join(probs)
        for cv_name, expected in docs:
            if power_abort:
                break
            if cv_name != docs[0][0]:
                probs = guard.sample(f"before {cv_name}")
                if probs:
                    power_abort = (f"power state changed/AC missing before {cv_name} - session does not count, "
                                   "remaining CVs/variants aborted: " + "; ".join(probs))
                    break
            for i in range(a.warmup + a.runs):
                tag = f"warmup{i + 1}" if i < a.warmup else f"run{i - a.warmup + 1}"
                if a.cooldown and session["runs"]:
                    time.sleep(a.cooldown)
                rec = run_one(B, a, repo, cv_name, tag, sampler, out, evaluate_doc, expected)
                session["runs"].append(rec)
                c0 = rec["llm_calls"][0] if rec["llm_calls"] else {}
                print(f"[{a.label}] {cv_name} {tag}: ok={rec['ok']} wall {rec['wall_s']} s, calls {rec['n_llm_calls']}, "
                      f"pp {rec['pp_tok_s']} tok/s ({c0.get('n_prompt')} tok), tg {rec['tg_tok_s']} tok/s "
                      f"({rec['gen_tokens']} tok), ttft {rec['ttft_s']} s, peak rss {rec['peak_rss_bytes'] / 2**30:.2f} GiB"
                      + ("" if rec["ok"] else f"  ERROR {rec['error']}"), flush=True)
                flush()
    finally:
        sampler.stop()
        probs = guard.sample("variant end")
        if probs and not power_abort:
            power_abort = "power state changed/AC missing at variant end - session does not count: " + "; ".join(probs)
        session["finished"] = now_iso()
        session["system_end"] = {"ram_available_bytes": psutil.virtual_memory().available,
                                 "battery_ac": system_info()["battery_ac"] if a.sysinfo_end else None}
        flush()
        print(f"-> {sp}")
        if power_abort:
            print(f"!! ABORT ({POWER_EXIT}): {power_abort}", flush=True)
    return POWER_EXIT if power_abort else 0


# ------------------------------------------------------------- summarize
def _med(vals):
    vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(statistics.median(vals), 3) if vals else None


METRICS = ("wall_s", "ttft_s", "pp_tok_s", "pp_tok_s_wall", "tg_tok_s", "tg_tok_s_wall", "gen_tokens", "answer_tokens", "prompt_tokens_evaluated",
           "load_s_total", "n_llm_calls", "peak_rss_bytes", "peak_private_bytes", "cpu_cores_effective")


def summarize_session(s: dict) -> dict:
    meas = [r for r in s.get("runs", []) if r.get("kind") == "measured"]
    per_cv = {}
    for cv in dict.fromkeys(r["cv"] for r in meas):
        R = [r for r in meas if r["cv"] == cv]
        okR = [r for r in R if r["ok"]]
        per_cv[cv] = {f"median_{k}": _med([r.get(k) for r in okR]) for k in METRICS}
        per_cv[cv].update(runs=len(R), ok=len(okR),
                          outputs_identical_across_runs=len({r.get("parsed_sha256") for r in R}) <= 1,
                          corpus_pass=[r.get("corpus_pass") for r in R])
    okm = [r for r in meas if r["ok"]]
    overall = {f"median_{k}": _med([r.get(k) for r in okm]) for k in METRICS}
    overall.update(measured_runs=len(meas), ok_runs=len(okm),
                   failed_runs=[(r["cv"], r["tag"], (r.get("error") or {}).get("code")) for r in meas if not r["ok"]],
                   max_peak_rss_bytes=max((r.get("peak_rss_bytes") or 0 for r in meas), default=None),
                   max_peak_private_bytes=max((r.get("peak_private_bytes") or 0 for r in meas), default=None),
                   sum_median_wall_s_10cv=round(sum(v["median_wall_s"] or 0 for v in per_cv.values()), 2),
                   cvs_with_unstable_output=[cv for cv, v in per_cv.items() if not v["outputs_identical_across_runs"]],
                   corpus_pass_runs=sum(1 for r in meas if r.get("corpus_pass")))
    return {"overall": overall, "per_cv": per_cv}


def speed_gain_status(s: dict):
    """True / False / 'unchecked' - whether a speculative variant's timings may count as a speed gain."""
    if (s.get("variant") or {}).get("spec", "off") == "off":
        return True
    chk = s.get("spec_identity_check")
    if not chk:
        return "unchecked"
    return bool(chk.get("ok"))


def cmd_summarize(a) -> int:
    rows = []
    for d in a.dirs:
        s = json.loads((Path(d) / "session.json").read_text(encoding="utf-8"))
        o = s["summary"]["overall"]
        rows.append(s)
        psc = s.get("power_state_consistent")
        if psc is False or Path(d).resolve().parent.joinpath("SESSION_INVALID.txt").exists():
            print(f"!! {s['label']}: power_state_consistent=False - session does not count "
                  f"({json.dumps((s.get('power') or {}).get('problems') or s.get('aborted') or 'SESSION_INVALID.txt', ensure_ascii=False)[:400]})")
        g = speed_gain_status(s)
        if g is not True:
            print(f"!! {s['label']}: speed_gain_counted={g} - "
                  + (SPEC_DEFECT_LABEL if g is False else "spec identity check not run (spec-check <baseline> <dir>)"))
        print(f"== {s['label']}  commit={s['repo_commit'][:10]} model={Path(s['model']['path']).name} "
              f"sha={s['model']['sha256'][:12]} llama-cpp-python={s['llama']['llama_cpp_python_version']} "
              f"ggml={s['llama'].get('ggml_commit')} variant={json.dumps({k: v for k, v in s['variant'].items() if k not in ('thread_plan_resolved', 'text_changing_axes')})}")
        print(json.dumps(o, indent=1))
        if a.per_cv:
            print(json.dumps(s["summary"]["per_cv"], indent=1))
    # cross-variant: the session-start reference must be the same for baseline and every variant
    refs = {(((s.get("power") or {}).get("reference") or {}).get("scheme_guid"),
             ((s.get("power") or {}).get("reference") or {}).get("scheme_name"),
             ((s.get("power") or {}).get("reference") or {}).get("ac_online")) for s in rows}
    across = len(refs) == 1
    if not across:
        print(f"!! power reference differs between the summarized sessions {sorted(map(str, refs))} - not comparable")
    if a.csv:
        import csv
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["label", "cv", *[f"median_{k}" for k in METRICS], "ok", "runs", "outputs_identical",
                        "speed_gain_counted", "spec_identity_cv", "power_state_consistent", "power_scheme",
                        "power_ac_online"])
            for s, d in zip(rows, a.dirs):
                g = speed_gain_status(s)
                bad = {d.get("cv") for d in (s.get("spec_identity_check") or {}).get("deviations", [])}
                for cv, v in s["summary"]["per_cv"].items():
                    is_spec = (s.get("variant") or {}).get("spec", "off") != "off"
                    ident = "" if not is_spec else ("unchecked" if g == "unchecked" else
                                                    ("DEVIATION" if (cv in bad or None in bad) else "identical"))
                    pref = (s.get("power") or {}).get("reference") or {}
                    psc = s.get("power_state_consistent")
                    if not across or Path(d).resolve().parent.joinpath("SESSION_INVALID.txt").exists():
                        psc = False
                    w.writerow(scrub_paths([s["label"], cv, *[v[f"median_{k}"] for k in METRICS], v["ok"], v["runs"],
                                v["outputs_identical_across_runs"], g, ident, psc,
                                f"{pref.get('scheme_guid')} ({pref.get('scheme_name')})", pref.get("ac_online")]))
        print(f"-> {a.csv}")
    return 0


# ------------------------------------------------------------------ diff
def json_paths_diff(x, y, path="$", out=None, limit=200):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y), key=str):
            if k not in x:
                out.append({"path": f"{path}.{k}", "a": "<missing>", "b": y[k]})
            elif k not in y:
                out.append({"path": f"{path}.{k}", "a": x[k], "b": "<missing>"})
            else:
                json_paths_diff(x[k], y[k], f"{path}.{k}", out, limit)
    elif isinstance(x, list) and isinstance(y, list):
        for i in range(max(len(x), len(y))):
            if i >= len(x):
                out.append({"path": f"{path}[{i}]", "a": "<missing>", "b": y[i]})
            elif i >= len(y):
                out.append({"path": f"{path}[{i}]", "a": x[i], "b": "<missing>"})
            else:
                json_paths_diff(x[i], y[i], f"{path}[{i}]", out, limit)
    elif x != y:
        out.append({"path": path, "a": x, "b": y})
    return out


def first_byte_diff(a: bytes, b: bytes) -> dict:
    if a == b:
        return {"identical": True, "bytes": len(a)}
    n = min(len(a), len(b))
    i = next((k for k in range(n) if a[k] != b[k]), n)
    ctx = lambda x: x[max(0, i - 60): i + 60].decode("utf-8", "replace")  # noqa: E731
    return {"identical": False, "len_a": len(a), "len_b": len(b), "first_diff_offset": i,
            "context_a": ctx(a), "context_b": ctx(b)}


def cmd_diff(a) -> int:
    A, B = Path(a.a), Path(a.b)
    sa = json.loads((A / "session.json").read_text(encoding="utf-8")) if (A / "session.json").exists() else {}
    sb = json.loads((B / "session.json").read_text(encoding="utf-8")) if (B / "session.json").exists() else {}
    report = {"a": str(A), "b": str(B), "a_label": sa.get("label"), "b_label": sb.get("label"),
              "a_repo_commit": sa.get("repo_commit"), "b_repo_commit": sb.get("repo_commit"),
              "a_llama": (sa.get("llama") or {}).get("llama_cpp_python_version"),
              "b_llama": (sb.get("llama") or {}).get("llama_cpp_python_version"),
              "a_model_sha256": (sa.get("model") or {}).get("sha256"), "b_model_sha256": (sb.get("model") or {}).get("sha256"),
              "warnings": [], "cvs": {}}
    if report["a_repo_commit"] != report["b_repo_commit"]:
        report["warnings"].append("repo commits differ - not a like-for-like comparison")
    if report["a_llama"] != report["b_llama"]:
        report["warnings"].append("llama-cpp-python versions differ - not a like-for-like comparison")
    sa_ = {p.name for p in (A / "extracts").glob("*") if p.is_dir()}
    sb_ = {p.name for p in (B / "extracts").glob("*") if p.is_dir()}
    stems = sorted(sa_ & sb_)
    report["cvs_only_in_a"] = sorted(sa_ - sb_)
    report["cvs_only_in_b"] = sorted(sb_ - sa_)
    if report["cvs_only_in_b"]:
        report["warnings"].append(f"CVs without reference in A: {report['cvs_only_in_b']}")
    n_same = n_diff = n_missing = 0
    for stem in stems:
        da, db = A / "extracts" / stem, B / "extracts" / stem
        tags_a = sorted({p.name.split(".")[0] for p in da.glob("*") if not p.name.startswith("_")}) if da.is_dir() else []
        tags_b = sorted({p.name.split(".")[0] for p in db.glob("*") if not p.name.startswith("_")}) if db.is_dir() else []
        if not a.include_warmup:
            tags_a = [t for t in tags_a if not t.startswith("warmup")]
            tags_b = [t for t in tags_b if not t.startswith("warmup")]
        ma = sorted(p.name for p in da.glob("_messages.*.json")) if da.is_dir() else []
        mb = sorted(p.name for p in db.glob("_messages.*.json")) if db.is_dir() else []
        if ma and mb and ma[0] not in mb and mb[0] not in ma:
            report["warnings"].append(f"{stem}: no common prompt messages sha (a={ma}, b={mb}) - prompts differ")
        if a.a_tag:
            pairs = [(a.a_tag, tb) for tb in tags_b]          # reference run vs every run of B
        else:
            pairs = [(t, t) for t in sorted(set(tags_a) | set(tags_b))]
        cvrep = []
        for ta, tb in pairs:
            ent = {"a_tag": ta, "b_tag": tb}
            pa, pb = da / f"{ta}.parsed.json", db / f"{tb}.parsed.json"
            if not pa.exists() or not pb.exists():
                ent["parsed"] = {"missing": [x for x, p in (("a", pa), ("b", pb)) if not p.exists()],
                                 "errors": {x: json.loads(p.read_text(encoding='utf-8')).get("code")
                                            for x, p in (("a", da / f"{ta}.error.json"), ("b", db / f"{tb}.error.json"))
                                            if p.exists()}}
                n_missing += 1
            else:
                ba, bb = pa.read_bytes(), pb.read_bytes()
                ent["parsed_bytes_identical"] = ba == bb
                if ba != bb:
                    ent["parsed_json_diff"] = json_paths_diff(json.loads(ba), json.loads(bb), limit=a.max_paths)
                    ent["parsed_json_equal"] = not ent["parsed_json_diff"]
                n_same += ba == bb
                n_diff += ba != bb
            raws = []
            for ra in sorted(da.glob(f"{ta}.call*.raw.txt")):
                suffix = ra.name[len(ta):]
                rb = db / f"{tb}{suffix}"
                if rb.exists():
                    raws.append({"file": suffix.lstrip("."), **first_byte_diff(ra.read_bytes(), rb.read_bytes())})
                else:
                    raws.append({"file": suffix.lstrip("."), "missing_in_b": True})
            ent["raw"] = raws
            cvrep.append(ent)
        report["cvs"][stem] = cvrep
    report["totals"] = {"parsed_identical": n_same, "parsed_different": n_diff, "missing_or_failed": n_missing}
    if (sb.get("variant") or {}).get("spec", "off") != "off" and (sa.get("variant") or {}).get("spec", "off") == "off":
        si = spec_identity_check(A, B, a.include_warmup)
        report["spec_identity"] = si
        if not si["ok"]:
            report["warnings"].insert(0, f"{SPEC_DEFECT_LABEL} ({len(si['deviations'])} deviation(s); "
                                         "timings of this variant must not be counted as a speed gain)")
    if a.json_out:
        Path(a.json_out).write_text(dump_json(report, default=str), encoding="utf-8")
    for w in report["warnings"]:
        print("WARNING:", w)
    for stem, ents in report["cvs"].items():
        for e in ents:
            if "parsed_bytes_identical" not in e:
                st = f"MISSING/FAILED {e['parsed']}"
            elif e["parsed_bytes_identical"]:
                st = "IDENTICAL"
            else:
                st = f"DIFFERENT ({len(e['parsed_json_diff'])} JSON paths)"
            rawst = ",".join("=" if r.get("identical") else ("?" if r.get("missing_in_b") else "≠") for r in e["raw"])
            print(f"{stem} {e['a_tag']}<->{e['b_tag']}: parsed {st}; raw [{rawst}]")
            if a.verbose and e.get("parsed_json_diff"):
                for dd in e["parsed_json_diff"][:a.max_paths]:
                    print("   ", json.dumps(dd, ensure_ascii=False, default=str)[:300])
    print(json.dumps(report["totals"]))
    return 0 if n_diff == 0 and n_missing == 0 else 1


# ------------------------------------------------------- spec identity check
SPEC_DEFECT_LABEL = "KV-rollback defect, not a speed gain, goes to Personaler"


def _calls_by_cv_tag(s: dict) -> dict:
    return {(r["cv"], r["tag"]): r for r in s.get("runs", [])}


def spec_identity_check(base_dir, spec_dir, include_warmup: bool = False) -> dict:
    """Byte-identity of a speculative variant against its non-speculative baseline.

    Required (Kritiker): same model sha256, same repo commit, same llama-cpp-python, temperature 0 in every
    LLM call of both sessions, same effective Llama seed, every baseline CV present, and per CV and run tag
    parsed.json AND every raw LLM output (callN.*.raw.txt) byte-identical. Failed spec runs count as
    deviations. Any deviation -> SPEC_DEFECT_LABEL and speed_gain_counted False.
    """
    A, B = Path(base_dir), Path(spec_dir)
    sa = json.loads((A / "session.json").read_text(encoding="utf-8"))
    sb = json.loads((B / "session.json").read_text(encoding="utf-8"))
    dev, pairs = [], 0

    def flag(cv, tag, what, **kw):
        dev.append({"cv": cv, "tag": tag, "what": what, **kw})

    if (sb.get("variant") or {}).get("spec", "off") == "off":
        flag(None, None, "variant B has no --spec")
    if (sa.get("variant") or {}).get("spec", "off") != "off":
        flag(None, None, "baseline A itself uses --spec")
    for k, ga in (("repo_commit", lambda s: s.get("repo_commit")),
                  ("model_sha256", lambda s: (s.get("model") or {}).get("sha256")),
                  ("llama_cpp_python", lambda s: (s.get("llama") or {}).get("llama_cpp_python_version")),
                  ("mode", lambda s: s.get("mode")),
                  ("max_tokens", lambda s: (s.get("variant") or {}).get("max_tokens")),
                  ("thinking", lambda s: (s.get("variant") or {}).get("thinking"))):
        if ga(sa) != ga(sb):
            flag(None, None, f"{k} differs", a=ga(sa), b=ga(sb))
    temps, seeds = {"a": set(), "b": set()}, {"a": set(), "b": set()}
    for side, s in (("a", sa), ("b", sb)):
        for r in s.get("runs", []):
            for c in r.get("llm_calls") or []:
                if c.get("chat_kwargs") is not None:          # a call that crashed before sampling has none
                    temps[side].add(c["chat_kwargs"].get("temperature"))
                if c.get("llama_effective") is not None:
                    seeds[side].add(c["llama_effective"].get("seed"))
    for side in ("a", "b"):
        if temps[side] - {0, 0.0}:
            flag(None, None, f"temperature != 0 in {side}", values=sorted(map(str, temps[side])))
    if seeds["a"] != seeds["b"] or len(seeds["a"] | seeds["b"]) != 1:
        flag(None, None, "effective Llama seed differs or is not unique", a=sorted(map(str, seeds["a"])),
             b=sorted(map(str, seeds["b"])))
    ra, rb = _calls_by_cv_tag(sa), _calls_by_cv_tag(sb)
    cvs_a = list(dict.fromkeys(cv for cv, _ in ra))
    for cv in cvs_a:
        tags = [t for (c, t), r in ra.items() if c == cv and (include_warmup or r.get("kind") == "measured")]
        for tag in tags:
            pairs += 1
            x, y = ra[(cv, tag)], rb.get((cv, tag))
            if y is None:
                flag(cv, tag, "missing in spec run")
                continue
            if not y.get("ok"):
                flag(cv, tag, "spec run failed", error=(y.get("error") or {}).get("code"),
                     message=str((y.get("error") or {}).get("message", ""))[:300])
                continue
            if not x.get("ok"):
                flag(cv, tag, "baseline run failed - no reference")
                continue
            stem = Path(cv).stem
            da, db = A / "extracts" / stem, B / "extracts" / stem
            pa, pb = da / f"{tag}.parsed.json", db / f"{tag}.parsed.json"
            if not (pa.exists() and pb.exists()):
                flag(cv, tag, "parsed.json missing", a=pa.exists(), b=pb.exists())
            elif pa.read_bytes() != pb.read_bytes():
                flag(cv, tag, "parsed.json differs", diff=json_paths_diff(json.loads(pa.read_bytes()),
                                                                          json.loads(pb.read_bytes()), limit=10))
            raws_a = sorted(p.name[len(tag):] for p in da.glob(f"{tag}.call*.raw.txt"))
            raws_b = sorted(p.name[len(tag):] for p in db.glob(f"{tag}.call*.raw.txt"))
            if raws_a != raws_b:
                flag(cv, tag, "different set of LLM calls", a=raws_a, b=raws_b)
            for suf in sorted(set(raws_a) & set(raws_b)):
                fb = first_byte_diff((da / f"{tag}{suf}").read_bytes(), (db / f"{tag}{suf}").read_bytes())
                if not fb["identical"]:
                    flag(cv, tag, f"raw LLM output differs ({suf.lstrip('.')})", **fb)
    ok = not dev
    return {"checked": now_iso(), "baseline_dir": str(A), "baseline_label": sa.get("label"),
            "spec_dir": str(B), "spec_label": sb.get("label"), "pairs_checked": pairs,
            "cvs_in_baseline": len(cvs_a), "ok": ok, "speed_gain_counted": ok,
            "verdict": "byte-identical to baseline (extracts and raw LLM outputs)" if ok else SPEC_DEFECT_LABEL,
            "label": None if ok else SPEC_DEFECT_LABEL, "deviations": dev}


def write_spec_identity(base_dir, spec_dir, include_warmup=False) -> dict:
    res = spec_identity_check(base_dir, spec_dir, include_warmup)
    B = Path(spec_dir)
    (B / f"spec_identity_vs_{Path(base_dir).name}.json").write_text(
        dump_json(res, default=str), encoding="utf-8")
    sp = B / "session.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["spec_identity_check"] = {k: v for k, v in res.items() if k != "deviations"} | {
        "n_deviations": len(res["deviations"]),
        "deviations": [{k: v for k, v in d.items() if k in ("cv", "tag", "what", "error")} for d in res["deviations"]]}
    sp.write_text(dump_json(s, default=str), encoding="utf-8")
    if res["ok"]:
        print(f"spec identity OK: {res['pairs_checked']} CV/run pairs byte-identical (extracts + raw) to {Path(base_dir).name}")
    else:
        print(f"!! {SPEC_DEFECT_LABEL}: {len(res['deviations'])} deviation(s) vs {Path(base_dir).name}")
        for d in res["deviations"][:30]:
            print("   ", json.dumps({k: d.get(k) for k in ("cv", "tag", "what", "error", "first_diff_offset")},
                                    ensure_ascii=False))
    return res


def cmd_spec_check(a) -> int:
    return 0 if write_spec_identity(a.baseline, a.spec_dir, a.include_warmup)["ok"] else 4


def cmd_power_snapshot(a) -> int:
    """Session-start reference for run_cv_matrix.ps1. Exit 5 if AC is not connected or the scheme is unreadable."""
    cur = power_state()
    probs = power_problems(cur, cur)
    doc = {"reference": cur, "written": now_iso(), "problems_at_start": probs,
           "note": "read-only snapshot; power plan is never changed by this bench"}
    Path(a.out).write_text(dump_json(doc), encoding="utf-8")
    print(json.dumps(doc, ensure_ascii=False))
    enforce = a.power_check == "on" or (a.power_check == "auto" and IS_WIN)
    if probs:
        print(("!! ABORT: " if enforce else "note (record-only, not enforced on this platform): ") + "; ".join(probs),
              flush=True)
    return POWER_EXIT if (probs and enforce) else 0


def cmd_power_check(a) -> int:
    ref = load_power_ref(a.ref)
    cur = power_state()
    probs = power_problems(ref, cur)
    rec = {"where": a.where, **cur, "problems": probs}
    if a.log:
        with open(a.log, "a", encoding="utf-8") as fh:
            fh.write(dump_json(rec, indent=None) + "\n")
    print(json.dumps(rec, ensure_ascii=False))
    enforce = a.power_check == "on" or (a.power_check == "auto" and IS_WIN)
    if probs:
        print(("!! " if enforce else "note (record-only): ") + f"power state differs from session start ({a.where}): "
              + "; ".join(probs), flush=True)
    return POWER_EXIT if (probs and enforce) else 0


def cmd_sysinfo(a) -> int:
    d = {"system": system_info()}
    try:
        d["llama"] = llama_info()
    except Exception as exc:  # noqa: BLE001
        d["llama_error"] = repr(exc)
    print(json.dumps(d, ensure_ascii=False, indent=1, default=str))
    return 0


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    return run_scrubbed(_main, argv)


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one variant over the CV corpus")
    r.add_argument("--repo", required=True, help="Karrierekrake checkout or snapshot (REPO_COMMIT file)")
    r.add_argument("--repo-commit", default=None, help="expected repo commit (checked against git/REPO_COMMIT)")
    r.add_argument("--model", required=True, help="GGUF path (product env KARRIEREKRAKE_CV_LLM_MODEL)")
    r.add_argument("--expect-model-sha256", default=None)
    r.add_argument("--out", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--note", default="")
    r.add_argument("--mode", choices=["import", "llm"], default="import",
                   help="import = full import_cv_docpick per CV (product); llm = primary extraction call only")
    r.add_argument("--cvs", default="", help="comma list of CV file names/prefixes (default: all 10 of expected_results.json)")
    r.add_argument("--warmup", type=int, default=1)
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--cooldown", type=float, default=3.0, help="seconds between runs")
    r.add_argument("--threads", default="plan", help="'plan' (product rule) or N -> KARRIEREKRAKE_CV_LLM_N_THREADS")
    r.add_argument("--threads-batch", default="plan", help="'plan' or N -> KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH")
    r.add_argument("--spec", choices=["off", "prompt-lookup"], default="off")
    r.add_argument("--spec-ngram", type=int, default=2, help="LlamaPromptLookupDecoding max_ngram_size")
    r.add_argument("--spec-num-pred", type=int, default=10, help="LlamaPromptLookupDecoding num_pred_tokens")
    r.add_argument("--no-spec-logits-all", dest="spec_logits_all", action="store_false",
                   help="do not pass logits_all=True with --spec (reproduces the 0.3.35 crash on prompts > n_batch)")
    r.add_argument("--prefix-cache", choices=["off", "ram"], default="off")
    r.add_argument("--cache-capacity-mb", type=int, default=2048)
    r.add_argument("--thinking", choices=["off", "on"], default="off")
    r.add_argument("--max-tokens", type=int, default=None, help="cap -> KARRIEREKRAKE_CV_LLM_MAX_TOKENS (product default 4096)")
    r.add_argument("--import-timeout-s", type=int, default=7200,
                   help="KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S (default 7200 so the product deadline cannot discard a "
                        "finished measurement; pass 0 to keep the product formula)")
    r.add_argument("--seed", type=int, default=None,
                   help="passed to Llama(seed=...) if given (product passes none -> LLAMA_DEFAULT_SEED); "
                        "decoding is greedy (temperature 0). Use the SAME value for a baseline and its spec variant")
    r.add_argument("--spec-baseline", default=None,
                   help="with --spec: baseline output dir (same model, no spec) to run the byte-identity check "
                        "(extracts AND raw LLM outputs, per CV and run) against at the end of the run")
    r.add_argument("--poll-ms", type=float, default=25.0)
    r.add_argument("--sysinfo-end", action="store_true", help="re-sample battery/AC at the end")
    r.add_argument("--power-ref", default=None,
                   help="session-start power snapshot (power-snapshot); default = state at variant start")
    r.add_argument("--power-check", choices=["auto", "on", "record"], default="auto",
                   help="auto = enforce on Windows (abort, exit 5, power_state_consistent=false), record elsewhere")
    r.add_argument("--overwrite", action="store_true")
    r.add_argument("--allow-dirty", action="store_true")
    r.add_argument("--allow-other-llama", action="store_true", help="do NOT use for target measurements")
    r.add_argument("--preflight", choices=["auto", "on", "off"], default="auto",
                   help="abort if other python/llama processes run (auto = on for Windows, record-only elsewhere)")
    d = sub.add_parser("diff", help="byte + JSON diff of extracts between two variant output dirs")
    d.add_argument("a", help="reference dir (e.g. results/4b-q4km-baseline)")
    d.add_argument("b", help="variant dir")
    d.add_argument("--a-tag", default=None, help="compare this tag of A (e.g. run1) against every run of B")
    d.add_argument("--include-warmup", action="store_true")
    d.add_argument("--json-out", default=None)
    d.add_argument("--max-paths", type=int, default=50)
    d.add_argument("-v", "--verbose", action="store_true")
    sc = sub.add_parser("spec-check", help="byte-identity of a --spec variant vs its baseline (extracts + raw); "
                                           "writes the verdict into the spec session.json; exit 4 on any deviation")
    sc.add_argument("baseline")
    sc.add_argument("spec_dir")
    sc.add_argument("--include-warmup", action="store_true")
    s = sub.add_parser("summarize")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--per-cv", action="store_true")
    s.add_argument("--csv", default=None)
    sub.add_parser("sysinfo", help="print system + llama-cpp-python info only (loads no model)")
    ps_ = sub.add_parser("power-snapshot", help="write the session-start power reference (scheme GUID+name, AC)")
    ps_.add_argument("--out", required=True)
    ps_.add_argument("--power-check", choices=["auto", "on", "record"], default="auto")
    pc = sub.add_parser("power-check", help="compare the current power state with the session reference; exit 5 on change")
    pc.add_argument("--ref", required=True)
    pc.add_argument("--where", default="")
    pc.add_argument("--log", default=None)
    pc.add_argument("--power-check", choices=["auto", "on", "record"], default="auto")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        if a.poll_ms > 50:
            raise SystemExit("--poll-ms must be <= 50")
        if a.import_timeout_s == 0:
            a.import_timeout_s = None
        if a.spec_baseline and a.spec == "off":
            raise SystemExit("--spec-baseline needs --spec")
        if a.spec_baseline and not (Path(a.spec_baseline) / "session.json").is_file():
            raise SystemExit(f"--spec-baseline {a.spec_baseline}: no session.json (run the baseline first)")
        rc = cmd_run(a)
        if a.spec_baseline:
            res = write_spec_identity(a.spec_baseline, Path(a.out) / a.label)
            rc = rc or (0 if res["ok"] else 4)
        return rc
    return {"diff": cmd_diff, "summarize": cmd_summarize, "sysinfo": cmd_sysinfo,
            "spec-check": cmd_spec_check, "power-snapshot": cmd_power_snapshot,
            "power-check": cmd_power_check}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
