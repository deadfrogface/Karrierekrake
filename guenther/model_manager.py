"""Model catalog + download manager (checksum, resumable, atomic, disk check).

One active local model serves CV extraction and writing. Setup adds pinned
device-dependent choices; Phi-4-mini remains a historical benchmark only.
"""

from __future__ import annotations

import json
import errno
import http.client
import os
import re
import shutil
import socket
import ssl
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse

import certifi
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.security.model_integrity import (
    ModelIntegrityError,
    require_sha256,
    sha256_file,
    verify_file_sha256,
)
from guenther.privacy import log_event

DOWNLOAD_TIMEOUT = 60
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_RETRY_DELAY = 1.0


def download_ssl_context() -> ssl.SSLContext:
    """Trust OS roots (including Windows enterprise roots) plus bundled public CAs."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def download_diagnostic(exc: Exception, url: str) -> str:
    """Preserve useful TLS metadata without signed URLs, paths or credentials."""
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    fields = [f"host={urllib.parse.urlsplit(url).hostname}",
              f"exception={type(reason).__name__}"]
    for key in ("library", "reason", "verify_code"):
        value = str(getattr(reason, key, ""))
        if re.fullmatch(r"[A-Za-z0-9_]+", value):
            fields.append(f"{key}={value}")
    return " ".join(fields)


def download_failure_code(exc: Exception) -> str:
    """Expose only a fixed diagnostic code, never paths or signed URLs."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLError):
        return "tls_failed"
    if isinstance(reason, TimeoutError):
        return "connection_timeout"
    if isinstance(reason, socket.gaierror):
        return "dns_failed"
    if isinstance(reason, PermissionError):
        return "write_permission_denied"
    if isinstance(reason, OSError) and reason.errno == errno.ENOSPC:
        return "insufficient_disk"
    if isinstance(reason, (http.client.IncompleteRead, ConnectionError)):
        return "connection_interrupted"
    if isinstance(exc, ValueError):
        return "invalid_download_response"
    return "download_failed"


def _retryable_download_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 429, 500, 502, 503, 504}
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return (not isinstance(reason, ssl.SSLError)
            and isinstance(reason, (TimeoutError, ConnectionError,
                                    socket.gaierror, http.client.IncompleteRead)))

# Legacy default; setup selection takes precedence for both runtime paths.
PRODUCTION_MODEL_ID = "qwen3.5-4b"

# No weights in git — catalog metadata only.
MODEL_CATALOG: dict[str, dict] = {
    PRODUCTION_MODEL_ID: {
        "display_name": "Karrierekrake lokal (Qwen3.5-4B)",
        "license": "Apache-2.0",
        "approx_bytes": 2_741_000_000,
        "ram_gb_min": 5.0,
        "tier": "standard",
        "filename": "Qwen3.5-4B-Q4_K_M.gguf",
        # Official Qwen/Qwen3.5-4B-GGUF resolve often returns 401 unauthenticated.
        # Unsloth mirror is public and pins the same LFS oid / SHA-256.
        "url": (
            "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/"
            "Qwen3.5-4B-Q4_K_M.gguf"
        ),
        "sha256": "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
        "source_repo": "unsloth/Qwen3.5-4B-GGUF",
        "base_model": "Qwen/Qwen3.5-4B",
        "upstream_license": "Apache-2.0",
        "quant": "Q4_K_M",
        "notes": (
            "SOLE production model for CV extract + Anschreiben (one-model dual-use). "
            "No second local weight. No DET. No cloud. "
            "Weights mirrored from Qwen3.5-4B-GGUF (same SHA-256)."
        ),
        "role": "primary",
        "deferred": False,
        "production": True,
    },
}

# Historical / benchmark-only — NOT production runtime. Not installable via ModelManager.
HISTORICAL_MODEL_CATALOG: dict[str, dict] = {
    "phi4-mini": {
        "display_name": "Phi-4-mini (historical — not production)",
        "license": "MIT",
        "approx_bytes": 2_491_874_688,
        "ram_gb_min": 5.0,
        "tier": "standard",
        "filename": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF/resolve/main/"
            "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
        ),
        "sha256": "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        "source_repo": "bartowski/microsoft_Phi-4-mini-instruct-GGUF",
        "base_model": "microsoft/Phi-4-mini-instruct",
        "notes": "HISTORICAL writing/extract bakeoff only — superseded by qwen3.5-4b dual-use",
        "role": "historical",
        "production": False,
    },
    "qwen3-1.7b": {
        "display_name": "Qwen3 1.7B (historical — not production)",
        "license": "Apache-2.0",
        "approx_bytes": 1_282_439_584,
        "ram_gb_min": 3.0,
        "tier": "light",
        "filename": "Qwen_Qwen3-1.7B-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/"
            "Qwen_Qwen3-1.7B-Q4_K_M.gguf"
        ),
        "sha256": "72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb",
        "source_repo": "bartowski/Qwen_Qwen3-1.7B-GGUF",
        "base_model": "Qwen/Qwen3-1.7B",
        "hf_commit": "dcb19155b962dbb6389f4691a982043a8e651022",
        "notes": "HISTORICAL only",
        "role": "historical",
        "production": False,
    },
    "qwen3-4b": {
        "display_name": "Qwen3 4B (historical — not production)",
        "license": "Apache-2.0",
        "approx_bytes": 2_497_280_256,
        "ram_gb_min": 5.0,
        "tier": "standard",
        "filename": "Qwen3-4B-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/"
            "Qwen3-4B-Q4_K_M.gguf"
        ),
        "sha256": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
        "source_repo": "Qwen/Qwen3-4B-GGUF",
        "base_model": "Qwen/Qwen3-4B",
        "notes": "HISTORICAL only — different from Qwen3.5-4B production",
        "role": "historical",
        "production": False,
    },
}


def is_production_model(model_id: str) -> bool:
    from guenther.setup_models import SETUP_MODEL_CATALOG
    return model_id == PRODUCTION_MODEL_ID or model_id in SETUP_MODEL_CATALOG


def installable_catalog() -> dict[str, dict]:
    from guenther.setup_models import SETUP_MODEL_CATALOG
    return {**MODEL_CATALOG, **SETUP_MODEL_CATALOG}


@dataclass
class DownloadProgress:
    model_id: str
    bytes_done: int = 0
    bytes_total: int = 0
    status: str = "idle"  # idle|checking|downloading|verifying|done|error|cancelled
    message: str = ""
    diagnostic: str = ""


@dataclass
class ModelManager:
    models_dir: Path
    catalog: dict[str, dict] = field(default_factory=installable_catalog)

    def __post_init__(self) -> None:
        self.models_dir = Path(self.models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self.models_dir / "installed.json"

    def list_catalog(self) -> list[dict]:
        out = []
        for mid, meta in self.catalog.items():
            row = {"id": mid, **meta, "installed": self.is_installed(mid)}
            out.append(row)
        return out

    def model_path(self, model_id: str) -> Path:
        meta = self.catalog[model_id]
        return self.models_dir / model_id / meta["filename"]

    def is_installed(self, model_id: str) -> bool:
        if model_id not in self.catalog:
            return False
        path = self.model_path(model_id)
        if path.is_symlink() or path.parent.is_symlink():
            return False
        if not (path.is_file() and path.stat().st_size > 1_000_000):
            return False
        # Catalog must declare a SHA-256; empty digest ⇒ not considered installed.
        try:
            require_sha256(str(self.catalog[model_id].get("sha256") or ""))
        except ModelIntegrityError:
            return False
        return True

    def assert_model_integrity(self, model_id: str) -> str:
        """Verify on-disk model matches catalog SHA-256 (fail closed)."""
        meta = self.catalog.get(model_id)
        if not meta:
            raise ModelIntegrityError("unknown_model")
        path = self.model_path(model_id)
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ModelIntegrityError("model_missing")
        return verify_file_sha256(path, str(meta.get("sha256") or ""))

    def disk_free_bytes(self) -> int:
        usage = shutil.disk_usage(self.models_dir)
        return int(usage.free)

    def can_install(self, model_id: str) -> tuple[bool, str]:
        if model_id in HISTORICAL_MODEL_CATALOG and model_id not in self.catalog:
            return False, "historical_model_forbidden"
        meta = self.catalog.get(model_id)
        if not meta:
            return False, "unknown_model"
        if not is_production_model(model_id):
            return False, "not_a_production_model"
        # A resumed download only needs room for its missing bytes. Requiring
        # the entire model size again makes a nearly complete .part unusable.
        expected = int(meta.get("approx_bytes") or 0)
        partial = self.model_path(model_id).with_suffix(
            self.model_path(model_id).suffix + ".part"
        )
        # Never trust a symlinked partial file or a symlinked model directory.
        if partial.is_symlink() or partial.parent.is_symlink():
            return False, "invalid_download_response"
        saved = partial.stat().st_size if partial.is_file() else 0
        if saved > expected:
            saved = 0  # A stale/oversized partial cannot be trusted.
        need = max(0, expected - saved) + 500_000_000
        free = self.disk_free_bytes()
        if free < need:
            return False, "insufficient_disk"
        return True, "ok"

    def _load_state(self) -> dict:
        if not self._state_path.is_file():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict) -> None:
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._state_path)

    def uninstall(self, model_id: str) -> bool:
        root = self.models_dir / model_id
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        state = self._load_state()
        state.pop(model_id, None)
        self._save_state(state)
        log_event("model_uninstalled", model_id=model_id)
        return True

    def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Require a real SHA-256; empty digest is a hard fail (no silent skip)."""
        try:
            require_sha256(expected_sha256)
            return sha256_file(path) == expected_sha256.strip().lower()
        except ModelIntegrityError:
            return False

    def install(
        self,
        model_id: str,
        *,
        progress_cb: Callable[[DownloadProgress], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        allow_download: bool = False,
    ) -> DownloadProgress:
        """Download only when allow_download=True and URL configured — never silent."""
        prog = DownloadProgress(model_id=model_id, status="checking")
        meta = self.catalog.get(model_id)
        if not meta:
            prog.status = "error"
            prog.message = "unknown_model"
            return prog
        ok, reason = self.can_install(model_id)
        if not ok:
            prog.status = "error"
            prog.message = reason
            return prog
        if not allow_download:
            prog.status = "error"
            prog.message = "download_not_confirmed"
            return prog
        url = str(meta.get("url") or "")
        if not url:
            prog.status = "error"
            prog.message = "url_not_configured"
            log_event("model_install_blocked", model_id=model_id, reason="no_url")
            return prog

        dest_dir = self.models_dir / model_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.model_path(model_id)
        if dest_dir.is_symlink() or final_path.is_symlink():
            prog.status, prog.message = "error", "invalid_download_response"
            return prog
        part_path = final_path.with_suffix(final_path.suffix + ".part")
        if part_path.is_symlink():
            prog.status, prog.message = "error", "invalid_download_response"
            return prog

        prog.status = "downloading"
        prog.bytes_total = int(meta.get("approx_bytes") or 0)
        if progress_cb:
            progress_cb(prog)

        context = download_ssl_context()
        for attempt in range(DOWNLOAD_ATTEMPTS):
            if cancel_check and cancel_check():
                prog.status, prog.message = "cancelled", "cancelled"
                return prog
            try:
                existing = part_path.stat().st_size if part_path.is_file() else 0
                req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake-Guenther/1.0"})
                if existing:
                    req.add_header("Range", f"bytes={existing}-")
                try:
                    response = urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT, context=context)
                except urllib.error.HTTPError as exc:
                    # A complete/stale partial file may be outside the server's range.
                    if not existing or exc.code != 416:
                        raise
                    exc.close()
                    existing = 0
                    req.remove_header("Range")
                    response = urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT, context=context)
                with response as resp:
                    status = resp.status
                    if status == 206:
                        match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)",
                                             resp.headers.get("Content-Range", ""))
                        if not match or int(match[1]) != existing:
                            raise ValueError("invalid_download_range")
                        start_byte, end_byte, total_bytes = map(int, match.groups())
                        if not start_byte <= end_byte < total_bytes:
                            raise ValueError("invalid_download_range")
                        prog.bytes_total = total_bytes
                    elif status == 200:
                        # Ignoring Range means a full file: truncate, never append.
                        existing = 0
                        total = resp.headers.get("Content-Length")
                        if total:
                            prog.bytes_total = int(total)
                    else:
                        raise ValueError("invalid_download_response")
                    prog.bytes_done = existing
                    with part_path.open("ab" if existing else "wb") as out:
                        while True:
                            if cancel_check and cancel_check():
                                prog.status = "cancelled"
                                prog.message = "cancelled"
                                return prog
                            chunk = resp.read(1024 * 1024)
                            if not chunk:
                                if prog.bytes_done < prog.bytes_total:
                                    raise http.client.IncompleteRead(b"", prog.bytes_total - prog.bytes_done)
                                break
                            out.write(chunk)
                            prog.bytes_done += len(chunk)
                            if progress_cb:
                                progress_cb(prog)
                break
            except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
                code = download_failure_code(exc)
                if attempt + 1 < DOWNLOAD_ATTEMPTS and _retryable_download_error(exc):
                    log_event("model_download_retry", model_id=model_id, reason=code,
                              attempt=attempt + 1, bytes_saved=prog.bytes_done)
                    prog.status, prog.message = "retrying", code
                    if progress_cb:
                        progress_cb(prog)
                    # Cancellable backoff; the next request resumes from the .part file.
                    deadline = time.monotonic() + DOWNLOAD_RETRY_DELAY * (attempt + 1)
                    while time.monotonic() < deadline:
                        if cancel_check and cancel_check():
                            prog.status, prog.message = "cancelled", "cancelled"
                            return prog
                        time.sleep(min(.1, max(0, deadline - time.monotonic())))
                    prog.status, prog.message = "downloading", ""
                    continue
                prog.status, prog.message = "error", code
                prog.diagnostic = download_diagnostic(exc, url)
                log_event("model_download_failed", model_id=model_id, reason=code,
                          diagnostic=prog.diagnostic)
                return prog

        prog.status = "verifying"
        if progress_cb:
            progress_cb(prog)
        if not self.verify_checksum(part_path, str(meta.get("sha256") or "")):
            prog.status = "error"
            prog.message = "checksum_mismatch"
            part_path.unlink(missing_ok=True)
            return prog

        # Atomic replace
        tmp_final = final_path.with_suffix(".tmp")
        part_path.replace(tmp_final)
        tmp_final.replace(final_path)
        state = self._load_state()
        state[model_id] = {
            "path": str(final_path),
            "license": meta.get("license"),
            "filename": meta.get("filename"),
        }
        self._save_state(state)
        prog.status = "done"
        prog.message = "installed"
        log_event("model_installed", model_id=model_id)
        if progress_cb:
            progress_cb(prog)
        return prog


def default_models_dir() -> Path:
    """Resolve AppData models dir without importing desktop at module import time."""
    override = os.environ.get("KARRIEREKRAKE_MODELS_DIR")
    if override:
        return Path(override)
    try:
        from desktop.paths import ensure_app_dirs

        dirs = ensure_app_dirs()
        path = dirs["root"] / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        path = Path(tempfile.gettempdir()) / "Karrierekrake" / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path
