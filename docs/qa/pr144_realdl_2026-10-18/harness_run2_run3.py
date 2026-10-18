#!/usr/bin/env python3
"""Single approved real-download resume test for the Karrierekrake 4B GSQ model.

Runs the REAL app path ``guenther.setup_models.install_recommended_model`` ->
``guenther.model_manager.ModelManager.install`` in a child process whose urllib
goes through a local CONNECT-only TCP proxy (via HTTPS_PROXY). The proxy never
terminates or inspects TLS: it pipes raw bytes, counts them per tunnel and cuts
the FIRST tunnel to the CDN host (the host after the huggingface.co redirect)
after exactly N server->client bytes. That reproduces the mid-stream TLS EOF.

PRIMARY evidence = the app's own log (logger ``karrierekrake``), written to a
file by a logging FileHandler in the child. Secondary evidence (clearly
labelled): proxy per-tunnel byte counts, filesystem observation of .part size,
final size, independent SHA-256, active-model.json presence.

Modes:
  --dry-run   no network: local plain-HTTP "origin" (127.0.0.1) that 302-redirects
              to a local "CDN" (localhost) with Range support, fake catalog entry
              injected in-memory, model probe stubbed (labelled). Proxy runs the
              same raw pipe in absolute-form HTTP forwarding mode, plus a CONNECT
              tunnel self-test.
  --real      real Hugging Face download (~1.94 GB). Requires env
              CONFIRM_REAL_DOWNLOAD=1. CONNECT only; real probe; real catalog.
Cleanup (always, also on failure): model file, .part, .tmp, model dir, tmp HOME.
Only small JSON/log evidence is kept. The proxy logs no payload.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = Path("/workspace/kk144-dl")
EXPECTED_HEAD = "856768c6f01f302a9b408b24817a9c9ed32c2cd0"  # computed-SHA log on top of f8dd578 (restart truncate) / 795a971
EXPECTED_BRANCH = "perf/pr144-download-resume"
REAL_MODEL_ID = "qwen3.5-4b-gsq"
DEFAULT_CUT_REAL = 472_695_563
DEFAULT_CUT_DRY = 3_000_001
DRY_SIZE = 8 * 1024 * 1024 + 4099
APP_CHUNK = 1024 * 1024  # resp.read(1024 * 1024) in ModelManager.install
ORIGIN_HOST_REAL = "huggingface.co"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# --------------------------------------------------------------------------
# CONNECT / raw-forward proxy (no TLS termination, no payload logging)
# --------------------------------------------------------------------------
class CutProxy:
    def __init__(self, cut_at: int, origin_host: str, cut_host: str | None,
                 allow_forward: bool):
        self.cut_at = cut_at
        self.origin_host = origin_host.lower()
        self.cut_host = cut_host.lower() if cut_host else None
        self.allow_forward = allow_forward
        self.tunnels: list[dict] = []
        self.lock = threading.Lock()
        self.cut_done = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass

    def _eligible(self, host: str) -> bool:
        host = host.lower()
        if self.cut_host:
            return host == self.cut_host
        return host != self.origin_host  # the CDN host after the redirect

    def _accept(self):
        while not self._stop:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client: socket.socket):
        rec = {"id": None, "mode": None, "target": None, "bytes_client_to_server": 0,
               "bytes_server_to_client": 0, "cut": False, "cut_at": None,
               "opened": now(), "closed": None, "error": None}
        with self.lock:
            rec["id"] = len(self.tunnels) + 1
            self.tunnels.append(rec)
        upstream = None
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                data = client.recv(65536)
                if not data:
                    return
                head += data
                if len(head) > 65536:
                    raise ValueError("request head too large")
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target, _ = line.split(" ", 2)
            if method.upper() == "CONNECT":
                host, _, port = target.rpartition(":")
                host = host.strip("[]")
                rec["mode"], rec["target"] = "CONNECT", f"{host}:{port}"
                upstream = socket.create_connection((host, int(port)), timeout=60)
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                pending = head.split(b"\r\n\r\n", 1)[1]
            else:
                if not self.allow_forward:
                    client.sendall(b"HTTP/1.1 405 CONNECT only\r\nContent-Length: 0\r\n\r\n")
                    rec["mode"], rec["error"] = "rejected_non_connect", "405"
                    return
                parts = urllib.parse.urlsplit(target)
                host, port = parts.hostname or "", parts.port or 80
                rec["mode"], rec["target"] = "FORWARD(dry-run)", f"{host}:{port}"
                upstream = socket.create_connection((host, port), timeout=60)
                pending = head  # forwarded unchanged; never logged
            with self.lock:
                # Armed for every eligible tunnel until one actually reaches N;
                # a tunnel the network drops before N must not use up the cut.
                cut_this = (not self.cut_done) and self._eligible(host)
            if pending:
                upstream.sendall(pending)
                rec["bytes_client_to_server"] += len(pending)
            self._pipe(client, upstream, rec, cut_this)
        except Exception as exc:  # noqa: BLE001 - recorded as type only
            rec["error"] = type(exc).__name__
        finally:
            rec["closed"] = now()
            for s in (client, upstream):
                if s is not None:
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    s.close()

    def _pipe(self, client, upstream, rec, cut_this):
        done = threading.Event()

        def c2s():
            try:
                while not done.is_set():
                    data = client.recv(65536)
                    if not data:
                        break
                    upstream.sendall(data)
                    rec["bytes_client_to_server"] += len(data)
            except OSError:
                pass
            finally:
                done.set()

        t = threading.Thread(target=c2s, daemon=True)
        t.start()
        try:
            while not done.is_set():
                data = upstream.recv(65536)
                if not data:
                    break
                if cut_this:
                    with self.lock:
                        if self.cut_done:
                            cut_this = False
                if cut_this:
                    room = self.cut_at - rec["bytes_server_to_client"]
                    if len(data) >= room:
                        with self.lock:
                            self.cut_done = True
                        client.sendall(data[:room])
                        rec["bytes_server_to_client"] += room
                        rec["cut"], rec["cut_at"] = True, self.cut_at
                        break  # abrupt TCP close mid TLS record / mid body
                client.sendall(data)
                rec["bytes_server_to_client"] += len(data)
        except OSError:
            pass
        finally:
            done.set()


# --------------------------------------------------------------------------
# Dry-run local servers (plain HTTP, Range support, redirect origin -> CDN)
# --------------------------------------------------------------------------
def start_dry_servers(blob: Path, size: int, seen: list):
    class CDN(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            rng = self.headers.get("Range")
            seen.append({"server": "cdn", "range": rng})
            start = 0
            m = re.fullmatch(r"bytes=(\d+)-", rng or "")
            if m:
                start = int(m.group(1))
                if start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(size - start))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                with blob.open("rb") as f:
                    f.seek(start)
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

    cdn = ThreadingHTTPServer(("127.0.0.1", 0), CDN)
    cdn_port = cdn.server_address[1]

    class Origin(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append({"server": "origin", "range": self.headers.get("Range")})
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{cdn_port}/xet-blob?X-Amz-Signature="
                             f"{secrets.token_hex(8)}&Expires=9")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

    origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    for s in (cdn, origin):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    return origin, cdn


def connect_selftest() -> dict:
    """CONNECT tunnel path (used by the real run) against a local plain server."""
    import http.client
    blob = Path(tempfile.mkstemp(prefix="selftest-", dir=HERE / "data")[1])
    try:
        size = 300_001
        blob.write_bytes(os.urandom(size))
        seen: list = []
        origin, cdn = start_dry_servers(blob, size, seen)
        n = 100_003
        proxy = CutProxy(n, origin_host="127.0.0.1", cut_host="localhost", allow_forward=False)
        conn = http.client.HTTPConnection("127.0.0.1", proxy.port, timeout=10)
        conn.set_tunnel("localhost", cdn.server_address[1])
        conn.request("GET", "/x", headers={"Range": "bytes=5-"})
        resp = conn.getresponse()
        status, cr = resp.status, resp.getheader("Content-Range")
        got, err = b"", None
        try:
            got = resp.read()
        except http.client.IncompleteRead as exc:
            got, err = exc.partial, "IncompleteRead"
        conn.close()
        # a non-CONNECT request must be rejected in real (CONNECT-only) mode
        c2 = http.client.HTTPConnection("127.0.0.1", proxy.port, timeout=10)
        c2.request("GET", f"http://localhost:{cdn.server_address[1]}/x")
        rejected = c2.getresponse().status
        c2.close()
        time.sleep(0.2)
        proxy.stop(); origin.shutdown(); cdn.shutdown()
        t = proxy.tunnels[0]
        ok = (status == 206 and cr == f"bytes 5-{size - 1}/{size}" and err == "IncompleteRead"
              and t["cut"] and t["bytes_server_to_client"] == n and t["mode"] == "CONNECT"
              and rejected == 405 and blob.read_bytes()[5:5 + len(got)] == got)
        return {"ok": ok, "status": status, "content_range": cr, "cut_at": n,
                "tunnel": t, "client_error": err, "non_connect_rejected_status": rejected}
    finally:
        blob.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Child: run the real app path with app logging to a file
# --------------------------------------------------------------------------
def child_main(cfg_path: str) -> int:
    import logging
    cfg = json.loads(Path(cfg_path).read_text())
    sys.path.insert(0, cfg["repo"])
    handler = logging.FileHandler(cfg["app_log"], encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("karrierekrake")
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    import core.model_probe as probe
    from guenther import model_manager as models
    from guenther import setup_models as setup

    secondary = {"label": "SECONDARY (harness observation, not app log)", "progress_events": []}
    model_id = cfg["model_id"]
    if cfg["mode"] == "dry-run":
        entry = dict(setup.SETUP_MODEL_CATALOG[REAL_MODEL_ID], **cfg["fake_entry"])
        setup.SETUP_MODEL_CATALOG[model_id] = entry  # in-memory only
        models.DOWNLOAD_RETRY_DELAY = 0.1  # dry-run speed only

        def fake_probe(mid, *, cancelled, timeout_seconds=180):
            secondary["probe"] = "STUBBED in dry-run (random bytes cannot be loaded)"
        probe.probe_in_subprocess = fake_probe
    entry = setup.SETUP_MODEL_CATALOG[model_id]
    models_dir = Path(os.environ["KARRIEREKRAKE_MODELS_DIR"])
    final = models_dir / model_id / entry["filename"]
    part = final.with_suffix(final.suffix + ".part")
    last = {"status": None}

    def progress(p):
        if p.status != last["status"]:
            last["status"] = p.status
            secondary["progress_events"].append({
                "t": now(), "status": p.status, "message": p.message,
                "bytes_done": p.bytes_done,
                "part_size_on_disk": part.stat().st_size if part.is_file() else None,
                "active_model_json_exists": (models_dir / "active-model.json").exists()})

    result = {"ok": False}
    try:
        path = setup.install_recommended_model(model_id, cancelled=lambda: False, progress=progress)
        result["ok"] = True
        result["installed_path_is_expected"] = Path(path) == final
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["diagnostic"] = getattr(exc, "download_diagnostic", "")
    secondary["final_size_on_disk"] = final.stat().st_size if final.is_file() else None
    if final.is_file():
        h = hashlib.sha256()
        with final.open("rb") as f:
            while chunk := f.read(8 * 1024 * 1024):
                h.update(chunk)
        secondary["independent_sha256_of_file_on_disk"] = h.hexdigest()
    am = models_dir / "active-model.json"
    secondary["active_model_json"] = json.loads(am.read_text()) if am.is_file() else None
    secondary["leftover_part_exists"] = part.exists()
    result["secondary"] = secondary
    result["catalog"] = {"url_host": urllib.parse.urlsplit(entry["url"]).hostname,
                         "approx_bytes": entry["approx_bytes"], "sha256": entry["sha256"],
                         "size_exact": entry.get("size_exact")}
    Path(cfg["child_result"]).write_text(json.dumps(result, indent=2))
    handler.flush()
    return 0 if result["ok"] else 1


# --------------------------------------------------------------------------
# Evidence from the app log
# --------------------------------------------------------------------------
LINE = re.compile(r"guenther\.(\w+) (\{.*\})\s*$")


def parse_app_log(path: Path) -> list[dict]:
    events = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = LINE.search(raw)
        if m:
            try:
                events.append({"event": m.group(1), **ast.literal_eval(m.group(2))})
            except (ValueError, SyntaxError):
                events.append({"event": m.group(1), "unparsed": True})
    return events


def evaluate(events, catalog, origin_host, cut_at, tunnels, child) -> dict:
    checks = {}
    size, sha = catalog["approx_bytes"], catalog["sha256"]
    idx = {i: e for i, e in enumerate(events)}
    retry = next((i for i, e in idx.items() if e["event"] == "model_download_retry"
                  and e.get("reason") == "connection_interrupted"), None)
    part_at_abort = events[retry].get("part_bytes") if retry is not None else None
    checks["abort_logged_with_part_bytes"] = bool(retry is not None and part_at_abort
                                                  and 0 < part_at_abort < size)
    checks["part_bytes_below_N_(tls/header_overhead)"] = bool(part_at_abort and part_at_abort < cut_at)
    req = next((i for i, e in idx.items() if retry is not None and i > retry
                and e["event"] == "model_download_request"), None)
    checks["range_header_equals_part_size"] = bool(
        req is not None and events[req].get("range") == f"bytes={part_at_abort}-"
        and events[req].get("part_bytes") == part_at_abort)
    resp = next((i for i, e in idx.items() if req is not None and i > req
                 and e["event"] == "model_download_response"), None)
    r = events[resp] if resp is not None else {}
    m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", str(r.get("content_range", "")))
    checks["resume_status_206"] = r.get("status") == 206
    checks["content_range_start_equals_part_size"] = bool(m and int(m.group(1)) == part_at_abort)
    checks["content_range_end_is_total_minus_1_and_total_is_size_exact"] = bool(
        m and int(m.group(2)) == size - 1 and int(m.group(3)) == size)
    checks["resume_response_host_is_after_redirect"] = bool(
        r.get("final_host") and r.get("final_host") != origin_host)
    cut = [t for t in tunnels if t["cut"]]
    checks["secondary_proxy_cut_one_cdn_tunnel_at_N"] = bool(
        len(cut) == 1 and cut[0]["bytes_server_to_client"] == cut_at
        and cut[0]["target"].rsplit(":", 1)[0].lower() == str(r.get("final_host", "")).lower())
    ver = next((i for i, e in idx.items() if e["event"] == "model_download_verified"), None)
    v = events[ver] if ver is not None else {}
    checks["final_size_equals_size_exact"] = v.get("size") == size and v.get("expected_size") == size
    # Since 856768c the app logs sha256 = digest it computed over the full file on
    # disk and expected_sha256 = catalog value; both must equal the catalog SHA.
    checks["sha256_computed_by_app_matches_catalog"] = v.get("sha256") == sha
    checks["expected_sha256_logged_is_catalog"] = v.get("expected_sha256") == sha
    sec_sha = child.get("secondary", {}).get("independent_sha256_of_file_on_disk")
    checks["app_computed_sha256_equals_independent_fs_sha256"] = bool(sec_sha) and v.get("sha256") == sec_sha
    pos = {name: next((i for i, e in idx.items() if e["event"] == name), None)
           for name in ("model_download_verified", "model_probe_passed", "model_activated")}
    checks["activation_only_after_sha_and_probe"] = (
        None not in pos.values()
        and pos["model_download_verified"] < pos["model_probe_passed"] < pos["model_activated"])
    sec = child.get("secondary", {})
    checks["secondary_fs_final_size"] = sec.get("final_size_on_disk") == size
    checks["secondary_fs_independent_sha256"] = sec.get("independent_sha256_of_file_on_disk") == sha
    checks["secondary_active_model_json"] = (sec.get("active_model_json") or {}).get("model_id") is not None
    checks["secondary_no_active_model_json_before_done"] = all(
        not e["active_model_json_exists"] for e in sec.get("progress_events", []))
    return {"checks": checks, "part_bytes_at_abort": part_at_abort,
            "resume_response": r, "verified": v, "passed": all(checks.values())}


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def git(repo: Path, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def mem_available_kb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def read_real_catalog(repo: Path, python: str) -> dict:
    code = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
            "from guenther.setup_models import SETUP_MODEL_CATALOG as C;"
            f"print(json.dumps(C[{REAL_MODEL_ID!r}]))")
    out = subprocess.run([python, "-c", code, str(repo)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--real", action="store_true")
    g.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--cut-at", type=int, default=None, help="server->client bytes in CDN tunnel before cut")
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--python", default="/workspace/kk-144-venv/bin/python")
    ap.add_argument("--expect-head", default=EXPECTED_HEAD)
    ap.add_argument("--cut-host", default=None, help="cut only tunnels to this host (default: any host != origin)")
    ap.add_argument("--evidence", default=None)
    a = ap.parse_args()
    if a.child:
        return child_main(a.child)

    mode = "real" if a.real else "dry-run"
    repo = Path(a.repo)
    if a.real and os.environ.get("CONFIRM_REAL_DOWNLOAD") != "1":
        print("refusing --real without CONFIRM_REAL_DOWNLOAD=1", file=sys.stderr)
        return 2
    evidence_path = Path(a.evidence or HERE / ("real_evidence.json" if a.real else "dryrun_evidence.json"))
    data = HERE / "data"
    data.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{mode}-", dir=data))
    app_log = HERE / ("real_app.log" if a.real else "dryrun_app.log")
    app_log.unlink(missing_ok=True)
    ev: dict = {"mode": mode, "started": now(), "harness": str(Path(__file__).resolve())}

    head = git(repo, "rev-parse", "HEAD")
    dirty = git(repo, "status", "--porcelain")
    ev["tested_commit"] = head
    ev["tested_branch"] = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    ev["tree_clean"] = dirty == ""
    ev["expected_head"] = a.expect_head
    ev["expected_branch"] = EXPECTED_BRANCH
    if (dirty or ev["tested_branch"] != EXPECTED_BRANCH
            or (a.expect_head and head != a.expect_head)):
        ev["result"] = "ABORT: repo not clean, branch != expected or HEAD != expected"
        evidence_path.write_text(json.dumps(ev, indent=2))
        print(ev["result"], file=sys.stderr)
        return 3

    if a.real:
        cat = read_real_catalog(repo, a.python)
        model_id, size, origin_host = REAL_MODEL_ID, int(cat["approx_bytes"]), ORIGIN_HOST_REAL
        cut_at = a.cut_at if a.cut_at is not None else DEFAULT_CUT_REAL
        ev["catalog"] = {k: cat[k] for k in ("url", "approx_bytes", "sha256", "size_exact", "filename")}
    else:
        model_id, size, origin_host = "dryrun-fake", DRY_SIZE, "127.0.0.1"
        cut_at = a.cut_at if a.cut_at is not None else DEFAULT_CUT_DRY

    # N sanity: odd, mid-file, not on the app's 1 MiB read boundary
    ev["N"] = cut_at
    n_ok = cut_at % 2 == 1 and 0 < cut_at < size and cut_at % APP_CHUNK != 0
    ev["N_checks"] = {"odd": cut_at % 2 == 1, "mid_file": 0 < cut_at < size,
                      "not_multiple_of_app_chunk_1MiB": cut_at % APP_CHUNK != 0,
                      "N_mod_1MiB": cut_at % APP_CHUNK}
    free = shutil.disk_usage(data).free
    mem = mem_available_kb()
    ev["preflight"] = {"free_disk_bytes": free, "required_free_bytes": 2 * size,
                       "mem_available_kb": mem, "app_python": a.python}
    if not n_ok or free < 2 * size or mem is None:
        ev["result"] = "ABORT: preflight failed (N / disk >= 2x model / MemAvailable)"
        evidence_path.write_text(json.dumps(ev, indent=2))
        shutil.rmtree(run_dir, ignore_errors=True)
        print(ev["result"], file=sys.stderr)
        return 4

    origin = cdn = None
    seen: list = []
    blob = run_dir / "served-blob.bin"
    try:
        if not a.real:
            ev["connect_selftest"] = connect_selftest()
            with blob.open("wb") as f:
                f.write(os.urandom(size))
            sha = hashlib.sha256(blob.read_bytes()).hexdigest()
            origin, cdn = start_dry_servers(blob, size, seen)
            fake_url = f"http://127.0.0.1:{origin.server_address[1]}/ISTA/fake/resolve/rev/dry.gguf"
            fake_entry = {"url": fake_url, "approx_bytes": size, "sha256": sha,
                          "filename": "dry.gguf", "size_exact": True}
            ev["catalog"] = dict(fake_entry, note="FAKE dry-run entry injected in-memory")
        else:
            fake_entry = None
        proxy = CutProxy(cut_at, origin_host=origin_host, cut_host=a.cut_host, allow_forward=not a.real)
        home = run_dir / "home"
        (home / ".config").mkdir(parents=True)
        models_dir = run_dir / "models"
        env = {k: v for k, v in os.environ.items()
               if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy",
                                    "requests_ca_bundle", "ssl_cert_file", "curl_ca_bundle"}}
        proxy_url = f"http://127.0.0.1:{proxy.port}"
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   KARRIEREKRAKE_MODELS_DIR=str(models_dir), PYTHONPATH=str(repo),
                   PYTHONDONTWRITEBYTECODE="1", HTTPS_PROXY=proxy_url, https_proxy=proxy_url)
        if not a.real:
            env.update(HTTP_PROXY=proxy_url, http_proxy=proxy_url)
        cfg = {"repo": str(repo), "mode": mode, "model_id": model_id, "app_log": str(app_log),
               "child_result": str(run_dir / "child.json"), "fake_entry": fake_entry}
        (run_dir / "cfg.json").write_text(json.dumps(cfg))
        t0 = time.time()
        proc = subprocess.run([a.python, str(Path(__file__).resolve()), "--child", str(run_dir / "cfg.json")],
                              env=env, cwd=str(repo), timeout=4 * 3600, check=False)
        ev["child_exit_code"] = proc.returncode
        ev["elapsed_s"] = round(time.time() - t0, 1)
        time.sleep(0.3)
        proxy.stop()
        child = json.loads((run_dir / "child.json").read_text()) if (run_dir / "child.json").is_file() else {}
        ev["child"] = child
        ev["proxy_tunnels_SECONDARY"] = proxy.tunnels
        if seen:
            ev["dry_server_requests_SECONDARY"] = seen
        events = parse_app_log(app_log)
        ev["app_log_file"] = str(app_log)
        ev["app_log_events_PRIMARY"] = events
        ev["evaluation"] = evaluate(events, ev["catalog"], origin_host, cut_at, proxy.tunnels, child)
        if not a.real:
            ev["evaluation"]["checks"]["connect_selftest"] = ev["connect_selftest"]["ok"]
            ev["evaluation"]["passed"] = all(ev["evaluation"]["checks"].values())
        ev["result"] = "PASS" if ev["evaluation"]["passed"] and child.get("ok") else "FAIL"
    finally:
        for s in (origin, cdn):
            if s is not None:
                s.shutdown()
        # Mandatory cleanup: model file, .part, .tmp, served blob, tmp HOME.
        removed = [str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()]
        shutil.rmtree(run_dir, ignore_errors=True)
        ev["cleanup"] = {"removed_run_dir": str(run_dir), "removed_files": removed,
                         "run_dir_exists_after": run_dir.exists(),
                         "kept": [str(evidence_path), str(app_log)]}
        ev["finished"] = now()
        evidence_path.write_text(json.dumps(ev, indent=2, default=str))
    print(json.dumps({"result": ev.get("result"), "tested_commit": head, "N": cut_at,
                      "checks": ev.get("evaluation", {}).get("checks")}, indent=2))
    return 0 if ev.get("result") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
