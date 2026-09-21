"""Model catalog + download manager (checksum, resumable, atomic, disk check).

NEXT-02: Production catalog is Phi-only. Historical Qwen metadata is retained for
benchmarks and must not be used as a production runtime path.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
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

# Sole production LLM (tournament/shootout pin — do not substitute another Phi artifact).
PRODUCTION_MODEL_ID = "phi4-mini"

# No weights in git — catalog metadata only.
# SHA256 values are Hugging Face LFS content OIDs (x-linked-etag), verified 2026-09-15.
MODEL_CATALOG: dict[str, dict] = {
    PRODUCTION_MODEL_ID: {
        "display_name": "Günther (Phi-4-mini)",
        "license": "MIT",
        "approx_bytes": 2_491_874_688,
        "ram_gb_min": 5.0,
        "tier": "standard",
        # Exact tournament provenance (PR #19 megapass D) — bartowski GGUF of Microsoft MIT upstream.
        "filename": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF/resolve/main/"
            "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
        ),
        "sha256": "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        "source_repo": "bartowski/microsoft_Phi-4-mini-instruct-GGUF",
        "base_model": "microsoft/Phi-4-mini-instruct",
        "upstream_license": "MIT",
        "quant": "Q4_K_M",
        "notes": (
            "SOLE production Günther model (NEXT-02). MIT upstream microsoft/Phi-4-mini-instruct. "
            "No Qwen production fallback."
        ),
        "role": "primary",
        "deferred": False,
        "production": True,
    },
}

# Historical / benchmark-only — NOT production runtime. Not installable via ModelManager.
HISTORICAL_MODEL_CATALOG: dict[str, dict] = {
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
        "notes": "HISTORICAL only — removed from production runtime (NEXT-02)",
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
        "notes": "HISTORICAL only — removed from production runtime (NEXT-02)",
        "role": "historical",
        "production": False,
    },
}


def is_production_model(model_id: str) -> bool:
    return model_id == PRODUCTION_MODEL_ID


@dataclass
class DownloadProgress:
    model_id: str
    bytes_done: int = 0
    bytes_total: int = 0
    status: str = "idle"  # idle|checking|downloading|verifying|done|error|cancelled
    message: str = ""


@dataclass
class ModelManager:
    models_dir: Path
    catalog: dict[str, dict] = field(default_factory=lambda: dict(MODEL_CATALOG))

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
        if not path.is_file():
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
        need = int(meta.get("approx_bytes") or 0) + 500_000_000  # headroom
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
        part_path = final_path.with_suffix(final_path.suffix + ".part")

        prog.status = "downloading"
        prog.bytes_total = int(meta.get("approx_bytes") or 0)
        if progress_cb:
            progress_cb(prog)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake-Guenther/1.0"})
            # Resume support
            headers = {}
            mode = "wb"
            existing = 0
            if part_path.is_file():
                existing = part_path.stat().st_size
                headers["Range"] = f"bytes={existing}-"
                mode = "ab"
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=60) as resp, part_path.open(mode) as out:
                total = resp.headers.get("Content-Length")
                if total and not headers:
                    prog.bytes_total = int(total)
                prog.bytes_done = existing
                while True:
                    if cancel_check and cancel_check():
                        prog.status = "cancelled"
                        prog.message = "cancelled"
                        return prog
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    prog.bytes_done += len(chunk)
                    if progress_cb:
                        progress_cb(prog)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            prog.status = "error"
            prog.message = "download_failed"
            log_event("model_download_failed", model_id=model_id, err=type(exc).__name__)
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
