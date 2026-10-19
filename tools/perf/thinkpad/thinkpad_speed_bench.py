#!/usr/bin/env python3
"""Karrierekrake CPU speed benchmark harness (llama.cpp llama-server, Windows-first).

Stdlib + psutil only. One invocation = one variant (one server start):
1 warmup + N measured runs (default 3) of a fixed, pre-rendered prompt file.

Per run it records: prompt-processing tok/s, generation tok/s (server timings),
time to first token (client clock, first streamed content), total wall time,
generated tokens, peak RSS / private bytes of the server process tree (psutil
poll every --poll-ms, default 25 ms) and the lifetime PeakWorkingSetSize
(Windows, psutil memory_info().peak_wset), effective CPU cores used, and the
full output text (written byte-exact to a .txt file).
Per variant: system info, exact server command line, server --version, model
(+draft) SHA-256, sampling incl. seed, the prompt file SHA-256, server log.

Subcommands
  run        run one variant                      (see --help)
  diff       byte-compare two output files
  diffdirs   byte-compare same-named run outputs of two result dirs
  summarize  median table of one or more result dirs

Prompt cache modes (--cache-mode)
  off      cache_prompt=false, --cache-ram 0: every run evaluates the full prompt.
  prefix   in-RAM slot KV reuse: --cache-ram 0, -np 1, cache_prompt=true. Each
           measured sequence erases slot 0, then sends the --prompt files in order
           (letter 1 cold, letters 2..n reuse the common prefix). Nothing on disk.
  slotfile like prefix, but after letter 1 the slot is saved to
           <out>/<label>/slots/slot0.bin (--slot-save-path), erased and restored
           before letter 2. Records save/restore time and file size. This is the
           only variant with an on-disk cache.

Nothing here touches the Karrierekrake app or its model store.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform
import shlex
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thinkpad_cv_bench import (  # noqa: E402  (one shared path scrubber for every bench)
    dump_json, install_output_scrubber, register_scrub_root, scrub_text)

IS_WIN = os.name == "nt"
SCHEMA = "kk-speed-bench/1"


# ----------------------------------------------------------------- utilities
def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path: Path, cache: dict) -> str:
    st = path.stat()
    key = hashlib.sha256(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()  # no path on disk
    if key in cache:
        return cache[key]
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 << 20), b""):
            h.update(block)
    cache[key] = h.hexdigest()
    return cache[key]


def cmdline_str(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd) if IS_WIN else shlex.join(cmd)


def run_capture(cmd: list[str], timeout: float = 60) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return (r.stdout + r.stderr).strip()
    except Exception as exc:  # noqa: BLE001 - recorded, not fatal
        return f"ERROR: {exc!r}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
        if b is not None:
            bat = {"power_plugged": b.power_plugged, "percent": b.percent}
    except Exception:  # noqa: BLE001
        bat = "unavailable"
    freq = None
    try:
        f = psutil.cpu_freq()
        freq = f._asdict() if f else None
    except Exception:  # noqa: BLE001
        pass
    # Background load: 1 s system-wide sample + top CPU processes (names only).
    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    sys_cpu = psutil.cpu_percent(interval=1.0)
    top = []
    for p in procs:
        try:
            top.append((p.cpu_percent(None), p.info.get("name")))
        except psutil.Error:
            pass
    top = [{"cpu_percent": c, "name": n} for c, n in sorted(top, key=lambda t: t[0] or 0, reverse=True)[:6]]
    info = {
        "hostname": "<HOSTNAME>", "os": platform.platform(), "os_version": platform.version(),
        "python": sys.version.split()[0], "cpu": cpu_name(),
        "cores_physical": psutil.cpu_count(logical=False), "threads_logical": psutil.cpu_count(logical=True),
        "cpu_freq_mhz": freq, "ram_total_bytes": vm.total, "ram_available_bytes": vm.available,
        "battery": bat, "system_cpu_percent_1s": sys_cpu, "top_processes_1s": top,
        "llama_env": {k: v for k, v in os.environ.items() if k.startswith(("LLAMA_", "GGML_", "OMP_"))},
    }
    if IS_WIN:
        info["power_scheme"] = run_capture(["powercfg", "/getactivescheme"])
    return info


# ---------------------------------------------------------- memory sampler
class TreeSampler:
    """Polls RSS (and Windows private bytes) of a process and its children."""

    def __init__(self, pid: int, interval_s: float):
        self.proc = psutil.Process(pid)
        self.interval = interval_s
        self._stop = threading.Event()
        self.reset()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def reset(self) -> None:
        self.max_rss = 0
        self.max_private = 0
        self.samples = 0

    def _loop(self) -> None:
        while not self._stop.is_set():
            rss = priv = 0
            try:
                for p in [self.proc, *self.proc.children(recursive=True)]:
                    try:
                        mi = p.memory_info()
                        rss += mi.rss
                        priv += getattr(mi, "private", 0) or 0
                    except psutil.Error:
                        pass
            except psutil.Error:
                pass
            self.max_rss = max(self.max_rss, rss)
            self.max_private = max(self.max_private, priv)
            self.samples += 1
            self._stop.wait(self.interval)

    def peak_wset(self) -> int | None:
        try:
            return getattr(self.proc.memory_info(), "peak_wset", None)
        except psutil.Error:
            return None

    def cpu_seconds(self) -> float:
        try:
            t = self.proc.cpu_times()
            return t.user + t.system
        except psutil.Error:
            return 0.0

    def stop(self) -> None:
        self._stop.set()
        self._t.join(timeout=2)


# --------------------------------------------------------------- server
class Server:
    def __init__(self, cmd: list[str], port: int, log_path: Path):
        self.cmd, self.port, self.log_path = cmd, port, log_path
        self.log = open(log_path, "wb")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0
        self.t_start = time.perf_counter()
        self.p = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT, creationflags=flags)

    def http(self, method: str, path: str, body: dict | None = None, timeout: float = 3600):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        data = json.dumps(body).encode() if body is not None else None
        c.request(method, path, body=data, headers={"Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw or b"null")
        except ValueError:
            return r.status, raw.decode("utf-8", "replace")

    def wait_ready(self, timeout_s: float) -> float:
        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            if self.p.poll() is not None:
                raise RuntimeError(f"server exited rc={self.p.returncode}; see {self.log_path}")
            try:
                st, _ = self.http("GET", "/health", timeout=5)
                if st == 200:
                    return time.perf_counter() - self.t_start
            except OSError:
                pass
            time.sleep(0.2)
        raise TimeoutError("server not ready")

    def stop(self) -> None:
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait(timeout=10)
        self.log.close()


def stream_completion(port: int, body: dict) -> dict:
    """POST /completion with stream=true. Client-side TTFT + server timings."""
    body = dict(body, stream=True)
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=7200)
    t0 = time.perf_counter()
    c.request("POST", "/completion", body=json.dumps(body).encode(),
              headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    r = c.getresponse()
    if r.status != 200:
        raise RuntimeError(f"/completion HTTP {r.status}: {r.read()[:500]!r}")
    parts: list[str] = []
    t_first = None
    final: dict = {}
    chunks = 0
    while True:
        line = r.readline()
        if not line:
            break
        line = line.strip()
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if payload == b"[DONE]":
            break
        ev = json.loads(payload)
        content = ev.get("content") or ""
        if content:
            if t_first is None:
                t_first = time.perf_counter()
            parts.append(content)
            chunks += 1
        if ev.get("stop"):
            final = ev
            break
    t_end = time.perf_counter()
    c.close()
    return {"text": "".join(parts), "t_send": t0, "t_first": t_first, "t_end": t_end,
            "chunks": chunks, "final": final}


# ------------------------------------------------------------------ run
def build_server_cmd(a, port: int, slot_dir: Path | None) -> list[str]:
    cmd = [a.server, "-m", a.model, "--host", "127.0.0.1", "--port", str(port),
           "-c", str(a.ctx), "-b", str(a.batch), "-ub", str(a.ubatch), "-np", "1", "--no-warmup"]
    if a.no_webui:
        cmd += ["--no-webui"]
    if a.threads is not None:
        cmd += ["-t", str(a.threads)]
    if a.threads_batch is not None:
        cmd += ["-tb", str(a.threads_batch)]
    cmd += ["--cache-ram", "0"]          # no cross-request host prompt cache in any mode
    if a.cache_mode == "off":
        cmd += ["--no-cache-prompt"]
    if slot_dir is not None:
        cmd += ["--slot-save-path", str(slot_dir)]
    if a.draft_model:
        cmd += ["-md", a.draft_model, "--spec-type", a.spec_type,
                "--spec-draft-n-max", str(a.draft_max), "--spec-draft-n-min", str(a.draft_min),
                "--spec-draft-p-min", str(a.draft_p_min)]
        if a.threads is not None:
            cmd += ["-td", str(a.threads)]
        if a.threads_batch is not None:
            cmd += ["-tbd", str(a.threads_batch)]
    cmd += a.extra or []
    return cmd


def request_body(a, prompt: str) -> dict:
    body = {"prompt": prompt, "n_predict": a.max_tokens, "temperature": a.temp,
            "top_k": a.top_k, "top_p": a.top_p, "min_p": a.min_p, "typical_p": 1.0,
            "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0,
            "seed": a.seed, "id_slot": 0, "cache_prompt": a.cache_mode != "off",
            "return_progress": False}
    if a.grammar:
        body["grammar"] = Path(a.grammar).read_text(encoding="utf-8")
    if a.ignore_eos:
        body["ignore_eos"] = True
    return body


def one_request(srv: Server, sampler: TreeSampler, a, prompt: str) -> dict:
    sampler.reset()
    cpu0 = sampler.cpu_seconds()
    res = stream_completion(srv.port, request_body(a, prompt))
    cpu1 = sampler.cpu_seconds()
    tm = res["final"].get("timings") or {}
    wall = res["t_end"] - res["t_send"]
    rec = {
        "ttft_s": round(res["t_first"] - res["t_send"], 4) if res["t_first"] else None,
        "wall_s": round(wall, 4),
        "prompt_tokens": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"),
        "pp_tok_s": tm.get("prompt_per_second"),
        "cache_n": tm.get("cache_n"),
        "gen_tokens": tm.get("predicted_n"), "gen_ms": tm.get("predicted_ms"),
        "tg_tok_s": tm.get("predicted_per_second"),
        "draft_n": tm.get("draft_n"), "draft_n_accepted": tm.get("draft_n_accepted"),
        "stop_type": res["final"].get("stop_type"),
        "stopped_eos": res["final"].get("stopped_eos"), "stopped_limit": res["final"].get("stopped_limit"),
        "truncated": res["final"].get("truncated"),
        "tokens_evaluated": res["final"].get("tokens_evaluated"),
        "stream_chunks": res["chunks"],
        "peak_rss_bytes": sampler.max_rss, "peak_private_bytes": sampler.max_private or None,
        "peak_wset_lifetime_bytes": sampler.peak_wset(), "mem_samples": sampler.samples,
        "cpu_cores_effective": round((cpu1 - cpu0) / wall, 2) if wall > 0 else None,
        "server_timings_raw": tm,
    }
    if rec["draft_n"]:
        rec["draft_accept_rate"] = round(rec["draft_n_accepted"] / rec["draft_n"], 4)
    return rec, res["text"]


def _scrub_file(p: Path) -> None:
    """Rewrite a log written by a child process (llama-server prints model/binary paths) without paths."""
    if p.is_file():
        raw = p.read_bytes().decode("utf-8", "surrogateescape")
        p.write_bytes(scrub_text(raw).encode("utf-8", "surrogateescape"))


def cmd_run(a) -> int:
    out = Path(a.out) / a.label
    if out.exists() and any(out.iterdir()) and not a.overwrite:
        raise SystemExit(f"{out} exists; use --overwrite or a new --label")
    out.mkdir(parents=True, exist_ok=True)
    prompts = [Path(p) for p in a.prompt]
    if a.cache_mode == "off" and len(prompts) != 1:
        raise SystemExit("--cache-mode off takes exactly one --prompt")
    if a.cache_mode != "off" and len(prompts) < 2:
        raise SystemExit("--cache-mode prefix/slotfile needs >= 2 --prompt files (letter 1, 2, ...)")
    texts = [p.read_bytes().decode("utf-8") for p in prompts]
    cache_path = Path(a.out) / "_sha256_cache.json"
    shacache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    models_dir = Path(a.model).resolve().parent
    register_scrub_root(models_dir, "<MODELS_DIR>")
    register_scrub_root(Path(a.model).absolute().parent, "<MODELS_DIR>")
    if a.draft_model:
        register_scrub_root(Path(a.draft_model).resolve().parent, "<MODELS_DIR>")
    files = {"model": {"path": a.model, "sha256": sha256_file(Path(a.model), shacache),
                       "bytes": Path(a.model).stat().st_size}}
    if a.draft_model:
        files["draft_model"] = {"path": a.draft_model, "sha256": sha256_file(Path(a.draft_model), shacache),
                                "bytes": Path(a.draft_model).stat().st_size}
    files["prompts"] = [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                         "bytes": p.stat().st_size} for p in prompts]
    if a.grammar:
        files["grammar"] = {"path": a.grammar, "sha256": hashlib.sha256(Path(a.grammar).read_bytes()).hexdigest()}
    cache_path.write_text(dump_json(shacache), encoding="utf-8")

    slot_dir = (out / "slots") if a.cache_mode == "slotfile" else None
    if slot_dir:
        slot_dir.mkdir(exist_ok=True)
    port = a.port or free_port()
    cmd = build_server_cmd(a, port, slot_dir)
    result = {"schema": SCHEMA, "label": a.label, "started": now_iso(),
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "system": system_info(), "server_version": run_capture([a.server, "--version"]),
              "server_cmd": cmd, "server_cmdline": cmdline_str(cmd), "files": files,
              "request_params": {k: v for k, v in request_body(a, "<prompt>").items() if k != "grammar"},
              "grammar": bool(a.grammar), "cache_mode": a.cache_mode,
              "warmup": a.warmup, "runs_requested": a.runs, "notes": a.note, "runs": []}
    srv = Server(cmd, port, out / "server.log")
    sampler = None
    try:
        result["load_s"] = round(srv.wait_ready(a.load_timeout), 3)
        sampler = TreeSampler(srv.p.pid, a.poll_ms / 1000.0)
        time.sleep(0.3)
        result["rss_after_load_bytes"] = sampler.max_rss
        st, props = srv.http("GET", "/props")
        result["server_props"] = props if st == 200 else {"http_status": st}
        total = a.warmup + a.runs
        for i in range(total):
            kind = "warmup" if i < a.warmup else "measured"
            idx = i - a.warmup + 1
            tag = f"warmup{i + 1}" if kind == "warmup" else f"run{idx}"
            if a.cooldown and i:
                time.sleep(a.cooldown)
            if a.cache_mode == "off":
                rec, text = one_request(srv, sampler, a, texts[0])
                (out / f"{tag}.txt").write_bytes(text.encode("utf-8"))
                rec.update(kind=kind, tag=tag, output_file=f"{tag}.txt",
                           output_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
                result["runs"].append(rec)
                print(f"[{a.label}] {tag}: pp {rec['pp_tok_s']} tok/s, tg {rec['tg_tok_s']} tok/s, "
                      f"ttft {rec['ttft_s']} s, n {rec['gen_tokens']}, rss {rec['peak_rss_bytes']/2**30:.2f} GiB",
                      flush=True)
                continue
            # cache sequence: erase slot, letter 1 cold, letters 2..n warm
            srv.http("POST", "/slots/0?action=erase", {})
            seq = {"kind": kind, "tag": tag, "letters": []}
            for li, text_in in enumerate(texts, 1):
                if a.cache_mode == "slotfile" and li == 2:
                    t = time.perf_counter()
                    st_s, save = srv.http("POST", "/slots/0?action=save", {"filename": "slot0.bin"})
                    seq["slot_save_s"] = round(time.perf_counter() - t, 4)
                    seq["slot_save_response"] = save
                    seq["slot_file"] = str(slot_dir / "slot0.bin")
                    seq["slot_file_bytes"] = (slot_dir / "slot0.bin").stat().st_size if (slot_dir / "slot0.bin").exists() else None
                    srv.http("POST", "/slots/0?action=erase", {})
                    t = time.perf_counter()
                    st_r, rest = srv.http("POST", "/slots/0?action=restore", {"filename": "slot0.bin"})
                    seq["slot_restore_s"] = round(time.perf_counter() - t, 4)
                    seq["slot_restore_response"] = rest
                rec, text = one_request(srv, sampler, a, text_in)
                fn = f"{tag}_letter{li}.txt"
                (out / fn).write_bytes(text.encode("utf-8"))
                rec.update(letter=li, prompt=str(prompts[li - 1]), output_file=fn,
                           output_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
                seq["letters"].append(rec)
                print(f"[{a.label}] {tag} letter{li}: ttft {rec['ttft_s']} s, prompt {rec['prompt_tokens']} "
                      f"(cache_n {rec['cache_n']}), tg {rec['tg_tok_s']} tok/s", flush=True)
            result["runs"].append(seq)
    finally:
        if sampler:
            result["peak_wset_lifetime_bytes"] = sampler.peak_wset()
            sampler.stop()
        srv.stop()
        _scrub_file(out / "server.log")
        result["finished"] = now_iso()
        result["summary"] = summarize_result(result)
        (out / "results.json").write_text(dump_json(result, models_dir=models_dir), encoding="utf-8")
        print(f"-> {out / 'results.json'}")
    return 0


# ------------------------------------------------------------- summarize
def _med(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(statistics.median(vals), 3) if vals else None


def summarize_result(r: dict) -> dict:
    meas = [x for x in r.get("runs", []) if x.get("kind") == "measured"]
    if r.get("cache_mode", "off") == "off":
        keys = ["pp_tok_s", "tg_tok_s", "ttft_s", "wall_s", "gen_tokens", "peak_rss_bytes",
                "peak_private_bytes", "cpu_cores_effective", "draft_accept_rate"]
        s = {f"median_{k}": _med([m.get(k) for m in meas]) for k in keys}
        s["min_tg_tok_s"] = min((m["tg_tok_s"] for m in meas if m.get("tg_tok_s")), default=None)
        s["max_tg_tok_s"] = max((m["tg_tok_s"] for m in meas if m.get("tg_tok_s")), default=None)
        s["outputs_identical_across_measured"] = len({m.get("output_sha256") for m in meas}) <= 1
        return s
    s = {}
    n = max((len(m["letters"]) for m in meas), default=0)
    for li in range(n):
        L = [m["letters"][li] for m in meas if len(m["letters"]) > li]
        s[f"letter{li + 1}"] = {f"median_{k}": _med([x.get(k) for x in L])
                                for k in ("ttft_s", "prompt_tokens", "cache_n", "pp_tok_s", "tg_tok_s", "wall_s")}
    return s


def cmd_summarize(a) -> int:
    for d in a.dirs:
        r = json.loads((Path(d) / "results.json").read_text(encoding="utf-8"))
        print(f"== {r['label']}  model={Path(r['files']['model']['path']).name} "
              f"draft={Path(r['files'].get('draft_model', {}).get('path', '-')).name} cache={r['cache_mode']}")
        print(json.dumps(r["summary"], indent=1))
    return 0


# ------------------------------------------------------------------ diff
def byte_diff(a: bytes, b: bytes) -> dict:
    if a == b:
        return {"identical": True, "bytes": len(a)}
    n = min(len(a), len(b))
    i = next((k for k in range(n) if a[k] != b[k]), n)
    ctx = lambda x: x[max(0, i - 60): i + 60].decode("utf-8", "replace")  # noqa: E731
    return {"identical": False, "len_a": len(a), "len_b": len(b), "first_diff_offset": i,
            "context_a": ctx(a), "context_b": ctx(b)}


def cmd_diff(a) -> int:
    r = byte_diff(Path(a.a).read_bytes(), Path(a.b).read_bytes())
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["identical"] else 1


def cmd_diffdirs(a) -> int:
    A, B = Path(a.a), Path(a.b)
    names = sorted({p.name for p in A.glob("*.txt")} | {p.name for p in B.glob("*.txt")})
    rc = 0
    for n in names:
        if n.startswith("warmup") and not a.include_warmup:
            continue
        pa, pb = A / n, B / n
        if not (pa.exists() and pb.exists()):
            print(f"{n}: missing in {'A' if not pa.exists() else 'B'}"); rc = 1; continue
        r = byte_diff(pa.read_bytes(), pb.read_bytes())
        print(f"{n}: {'IDENTICAL' if r['identical'] else 'DIFFERENT @' + str(r['first_diff_offset'])}")
        if not r["identical"]:
            rc = 1
            if a.verbose:
                print(json.dumps(r, ensure_ascii=False, indent=1))
    return rc


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    install_output_scrubber()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--server", required=True, help="path to llama-server(.exe)")
    r.add_argument("--model", required=True)
    r.add_argument("--prompt", required=True, action="append", help="rendered prompt file; repeat for cache sequences")
    r.add_argument("--out", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--note", default="")
    r.add_argument("--warmup", type=int, default=1)
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--cooldown", type=float, default=5.0, help="seconds between runs")
    r.add_argument("--threads", type=int, default=None, help="-t; omit for llama.cpp default")
    r.add_argument("--threads-batch", type=int, default=None, help="-tb; omit for llama.cpp default")
    r.add_argument("--ctx", type=int, default=4096)       # product n_ctx
    r.add_argument("--batch", type=int, default=512)      # product n_batch
    r.add_argument("--ubatch", type=int, default=512)     # llama-cpp-python n_ubatch default
    r.add_argument("--max-tokens", type=int, default=900)  # product "writing" budget
    r.add_argument("--temp", type=float, default=0.2)     # product writing temperature
    r.add_argument("--top-k", type=int, default=40)
    r.add_argument("--top-p", type=float, default=0.95)
    r.add_argument("--min-p", type=float, default=0.05)
    r.add_argument("--seed", type=int, default=1234)
    r.add_argument("--greedy", action="store_true", help="temperature 0 (greedy); required for spec equality checks")
    r.add_argument("--grammar", default=None, help="GBNF file (json_object.gbnf = product response_format)")
    r.add_argument("--ignore-eos", action="store_true", help="force exactly --max-tokens (pure tg measurement)")
    r.add_argument("--cache-mode", choices=["off", "prefix", "slotfile"], default="off")
    r.add_argument("--draft-model", default=None)
    r.add_argument("--spec-type", default="draft-simple")
    r.add_argument("--draft-max", type=int, default=8)
    r.add_argument("--draft-min", type=int, default=0)
    r.add_argument("--draft-p-min", type=float, default=0.0)
    r.add_argument("--no-webui", action="store_true", help="add --no-webui (only if the build supports it)")
    r.add_argument("--poll-ms", type=float, default=25.0)
    r.add_argument("--load-timeout", type=float, default=900.0)
    r.add_argument("--port", type=int, default=0)
    r.add_argument("--overwrite", action="store_true")
    r.add_argument("--extra", nargs=argparse.REMAINDER, help="extra raw llama-server args (must be last)")
    d = sub.add_parser("diff"); d.add_argument("a"); d.add_argument("b")
    dd = sub.add_parser("diffdirs"); dd.add_argument("a"); dd.add_argument("b")
    dd.add_argument("--include-warmup", action="store_true"); dd.add_argument("-v", "--verbose", action="store_true")
    s = sub.add_parser("summarize"); s.add_argument("dirs", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        if a.greedy:
            a.temp = 0.0
        if a.poll_ms > 50:
            raise SystemExit("--poll-ms must be <= 50")
        return cmd_run(a)
    return {"diff": cmd_diff, "diffdirs": cmd_diffdirs, "summarize": cmd_summarize}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
