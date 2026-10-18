"""Pinned local models and fast, offline setup recommendations.

Only models whose download, checksum and isolated load probe succeed are
activated. RAM budgets are conservative planning values, not speed promises.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _entry(name, repo, revision, filename, size, digest, ram):
    return dict(display_name=name, source_repo=repo, filename=filename,
                approx_bytes=size, sha256=digest, ram_gb_min=ram,
                url=f"https://huggingface.co/{repo}/resolve/{revision}/{filename}",
                # approx_bytes is the audited LFS size, so resumes check it exactly.
                license="Apache-2.0", production=True, size_exact=True)


SETUP_MODEL_CATALOG = {
    "qwen3.5-4b-gsq": _entry(
        "Qwen 4B · kompakt", "ISTA-DASLab/Qwen3.5-4B-GGUF-GSQ",
        "3fd6825d7b0f014adb03d3981074a43753c0b8be", "Qwen3.5-4B-Q2_K_XL.gguf",
        1940825248, "b7d9ec51fb4d726d31e6bfd47062fb74574a974b93951da6a435b5e35185cb5a", 6.0),
    "qwen3-8b-gsq": _entry(
        "Qwen 8B · ausgewogen", "ISTA-DASLab/Qwen3-8B-GGUF-GSQ",
        "5605b36840bc26d62b34a6adb518109f55c412d2", "qwen3-8b-Q3_K_M.gguf",
        4124161376, "81894ed9b0e0245af542019a941e0aac21f3ec8b5a2386b82486db19c0170e77", 9.0),
    "qwen3.8-27b-gsq-rco": _entry(
        "Qwen 27B · leistungsstarke Geräte", "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
        "d562806dbafae37109975e970aae91b43e73b440", "Qwen3.8-27B-GSQ-RCO-IQ2_XS.gguf",
        8422841472, "f0ae5006da0ce6225935339e4e989369f94de95d2263cf969519f8420c9ae02c", 14.0),
}


@dataclass(frozen=True)
class SetupRecommendation:
    total_gib: float
    available_gib: float
    physical_cores: int
    free_disk_bytes: int
    model_id: str | None


def recommend_setup_model(*, total_gib, available_gib, physical_cores, free_disk_bytes):
    # Do not recommend 27B just because its weights fit in a laptop's RAM.
    # CPU-only inference must leave room for the app, OS and context buffers.
    order = ["qwen3.5-4b-gsq"]
    if total_gib >= 23 and physical_cores >= 4:
        order.insert(0, "qwen3-8b-gsq")
    if total_gib >= 47 and physical_cores >= 12:
        order.insert(0, "qwen3.8-27b-gsq-rco")
    model_id = next((mid for mid in order
                     if SETUP_MODEL_CATALOG[mid]["ram_gb_min"] + 2 <= available_gib
                     and SETUP_MODEL_CATALOG[mid]["approx_bytes"] + 500_000_000 <= free_disk_bytes), None)
    return SetupRecommendation(total_gib, available_gib, physical_cores, free_disk_bytes, model_id)


def inspect_setup_device() -> SetupRecommendation:
    import psutil
    from guenther.model_manager import default_models_dir

    memory = psutil.virtual_memory()
    root = default_models_dir()
    # Fresh installations may not have created the model directory yet.
    # disk_usage() requires an existing ancestor, not the future target.
    disk_root = root
    while not disk_root.exists() and disk_root != disk_root.parent:
        disk_root = disk_root.parent
    return recommend_setup_model(total_gib=memory.total / 1024**3,
                                 available_gib=memory.available / 1024**3,
                                 physical_cores=psutil.cpu_count(logical=False) or 1,
                                 free_disk_bytes=shutil.disk_usage(disk_root).free)


def selected_model_id(models_dir: Path | None = None) -> str | None:
    from guenther.model_manager import default_models_dir

    root = models_dir if models_dir is not None else default_models_dir()
    try:
        value = json.loads((root / "active-model.json").read_text(encoding="utf-8"))
        mid = value.get("model_id")
        return mid if mid in SETUP_MODEL_CATALOG else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def selected_model_path(models_dir: Path | None = None) -> Path | None:
    from guenther.model_manager import default_models_dir

    root = models_dir if models_dir is not None else default_models_dir()
    mid = selected_model_id(root)
    if mid is None:
        return None
    path = root / mid / SETUP_MODEL_CATALOG[mid]["filename"]
    # Do not follow a replaced model symlink outside the managed model store.
    if path.is_symlink() or path.parent.is_symlink():
        return None
    return path if path.is_file() else None


def activate_model(model_id: str, models_dir: Path) -> None:
    if model_id not in SETUP_MODEL_CATALOG:
        raise ValueError("unknown_model")
    target = models_dir / "active-model.json"
    fd, name = tempfile.mkstemp(prefix=".active-model-", dir=models_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"model_id": model_id}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def install_recommended_model(model_id, *, cancelled, progress):
    from guenther.model_manager import ModelManager, default_models_dir
    from core.model_probe import probe_in_subprocess
    from guenther.privacy import log_event

    manager = ModelManager(default_models_dir())
    verified = False
    if manager.is_installed(model_id):
        try:
            manager.assert_model_integrity(model_id)
            verified = True
        except ValueError:
            pass  # A damaged previous download is replaced by a verified one.
    if not verified:
        result = manager.install(model_id, allow_download=True,
                                 cancel_check=cancelled, progress_cb=progress)
        if result.status != "done":
            error = RuntimeError(result.message)
            error.download_diagnostic = result.diagnostic
            raise error
    if cancelled():
        raise RuntimeError("cancelled")
    from guenther.model_manager import DownloadProgress
    progress(DownloadProgress(model_id=model_id, status="testing"))
    probe_in_subprocess(model_id, cancelled=cancelled)
    log_event("model_probe_passed", model_id=model_id)
    if cancelled():
        raise RuntimeError("cancelled")
    activate_model(model_id, manager.models_dir)
    log_event("model_activated", model_id=model_id)
    return manager.model_path(model_id)
