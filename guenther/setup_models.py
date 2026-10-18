"""Pinned local models and fast, offline setup recommendations.

Only models whose download, checksum and isolated load probe succeed are
activated. RAM budgets are conservative planning values, not speed promises.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from guenther.model_budgets import (
    CLASS_4B,
    CLASS_8B,
    CLASS_27B,
    CLASS_RAM_MIN_GIB,
    DISK_RESERVE_BYTES,
    RECOMMEND_8B_MIN_CORES,
    RECOMMEND_8B_MIN_TOTAL_GIB,
    RECOMMEND_27B_MIN_CORES,
    RECOMMEND_27B_MIN_TOTAL_GIB,
    class_gate_passes,
    installed_ram_fits,
    low_free_ram,
    usable_ram_fits,
)


def _entry(name, repo, revision, filename, size, digest, model_class):
    # ram_gb_min is read from the shared class budget (guenther.model_budgets)
    # so device_check and the setup wizard always use the same number.
    return dict(display_name=name, source_repo=repo, filename=filename,
                approx_bytes=size, sha256=digest, model_class=model_class,
                ram_gb_min=CLASS_RAM_MIN_GIB[model_class],
                url=f"https://huggingface.co/{repo}/resolve/{revision}/{filename}",
                # approx_bytes is the audited LFS size, so resumes check it exactly.
                license="Apache-2.0", production=True, size_exact=True)


SETUP_MODEL_CATALOG = {
    "qwen3.5-4b-gsq": _entry(
        "Qwen 4B · kompakt", "ISTA-DASLab/Qwen3.5-4B-GGUF-GSQ",
        "3fd6825d7b0f014adb03d3981074a43753c0b8be", "Qwen3.5-4B-Q2_K_XL.gguf",
        1940825248, "b7d9ec51fb4d726d31e6bfd47062fb74574a974b93951da6a435b5e35185cb5a", CLASS_4B),
    "qwen3-8b-gsq": _entry(
        "Qwen 8B · ausgewogen", "ISTA-DASLab/Qwen3-8B-GGUF-GSQ",
        "5605b36840bc26d62b34a6adb518109f55c412d2", "qwen3-8b-Q3_K_M.gguf",
        4124161376, "81894ed9b0e0245af542019a941e0aac21f3ec8b5a2386b82486db19c0170e77", CLASS_8B),
    "qwen3.8-27b-gsq-rco": _entry(
        "Qwen 27B · leistungsstarke Geräte", "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
        "d562806dbafae37109975e970aae91b43e73b440", "Qwen3.8-27B-GSQ-RCO-IQ2_XS.gguf",
        8422841472, "f0ae5006da0ce6225935339e4e989369f94de95d2263cf969519f8420c9ae02c", CLASS_27B),
}


# Per-model peak-memory attestation. A value is a ship-evidence record as
# written by ``scripts/run_i3_peak_job_benchmark.py --attest-physical-i3`` on
# the physical Intel Core i3 / 8 GB laptop, extended with provenance fields
# (commit, measurement and model hashes, device). Nothing has been measured
# there yet, so every model is unattested (None). Only a complete record (see
# ``peak_unverified``) turns a model's ``peak_unverified`` to False.
PEAK_ATTESTATION: dict[str, dict | None] = {mid: None for mid in SETUP_MODEL_CATALOG}

_ATTESTED_METHOD = "windows_job_object_peak_job_memory"
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _gate_int(value, limit) -> bool:
    return (not isinstance(value, bool) and isinstance(value, int)
            and 0 <= value <= limit)


def peak_unverified(model_id: str, attestation: dict | None = None) -> bool:
    """True unless a complete physical-i3 record for exactly this artifact exists.

    A record clears the flag only if it is a dict with ALL of:

    * ``commit``: str, full 40-character lowercase hex git SHA (no short SHAs)
    * ``measurement_sha256``: str, 64 lowercase hex characters (hash of the
      benchmark JSON report)
    * ``device``: non-empty str (the physical i3 / 8 GB laptop)
    * ``model_sha256``: equal to ``SETUP_MODEL_CATALOG[model_id]["sha256"]``,
      so a record cannot be reused for a swapped artifact
    * ``peak_private_bytes``: int (not bool), 0..3_300_000_000
    * ``peak_bytes``: int (not bool), 0..3_300_000_000 (Job Object peak)
    * ``method == "windows_job_object_peak_job_memory"``
    * ``ship_evidence is True`` and ``hard_fail is False`` (real bools)

    Anything missing, of the wrong type, a hash mismatch, True, None or a
    non-dict keeps the model unverified (fail closed).
    """
    from core.hardware_peak_gate import HARD_PEAK_RSS_BYTES

    table = PEAK_ATTESTATION if attestation is None else attestation
    record = table.get(model_id) if isinstance(table, dict) else None
    entry = SETUP_MODEL_CATALOG.get(model_id)
    if not isinstance(record, dict) or entry is None:
        return True
    commit, measurement = record.get("commit"), record.get("measurement_sha256")
    device, model_sha = record.get("device"), record.get("model_sha256")
    checks = (
        isinstance(commit, str) and _COMMIT_RE.fullmatch(commit) is not None,
        isinstance(measurement, str) and _SHA256_RE.fullmatch(measurement) is not None,
        isinstance(device, str) and device.strip() != "",
        isinstance(model_sha, str) and model_sha == entry.get("sha256"),
        _gate_int(record.get("peak_private_bytes"), HARD_PEAK_RSS_BYTES),
        _gate_int(record.get("peak_bytes"), HARD_PEAK_RSS_BYTES),
        record.get("method") == _ATTESTED_METHOD,
        record.get("ship_evidence") is True,
        record.get("hard_fail") is False,
    )
    return not all(checks)


# Reason codes when model_id is None.
REASON_RAM_TOO_SMALL = "ram_too_small"
REASON_DISK_TOO_SMALL = "disk_too_small"
# Device-level warnings.
WARNING_LOW_FREE_RAM = "low_free_ram"
WARNING_SLOW_CPU = "slow_cpu"


@dataclass(frozen=True)
class SetupRecommendation:
    total_gib: float
    available_gib: float
    physical_cores: int
    free_disk_bytes: int
    model_id: str | None
    # Added fields have defaults so positional construction stays valid.
    # reason: None | "ram_too_small" | "disk_too_small" (only when model_id is None)
    reason: str | None = None
    # warnings: subset of ("low_free_ram", "slow_cpu"), device level
    warnings: tuple[str, ...] = ()
    # Other models with fits True (not the recommendation), best first.
    alternatives: tuple[str, ...] = ()
    # fits[model_id]: model_budgets.usable_ram_fits (4B: class gate on total
    # RAM >= 7.0 GiB; 8B/27B: class gate, budget + 2 GiB OS reserve <= total
    # AND <= current free RAM) AND file + 500 MB on disk. The same rule as the
    # device report and the setup panel. Never a release, quality or speed
    # statement. Low free RAM for 4B is reported via low_free_ram.
    fits: dict[str, bool] = field(default_factory=dict)
    # peak_unverified[model_id]: True until PEAK_ATTESTATION holds a complete
    # physical-i3 record for that model.
    peak_unverified: dict[str, bool] = field(default_factory=dict)


def _disk_ok(mid, free_disk_bytes):
    return SETUP_MODEL_CATALOG[mid]["approx_bytes"] + DISK_RESERVE_BYTES <= free_disk_bytes


def recommend_setup_model(*, total_gib, available_gib, physical_cores, free_disk_bytes,
                          attestation=None):
    """Offline recommendation; classifies by TOTAL RAM so 8 GB devices are no dead end.

    * 4B: recommended whenever total >= 7.0 GiB and its file fits on disk.
      ``low_free_ram`` is set when free RAM is below the reachable 4B warn
      threshold (~3.57 GiB, UNSICHER until T05.06); 4B stays recommended (the
      old rule returned None and left 8 GB laptops without any model).
    * Attestation duty for EVERY class above 4B (8B and 27B): a model of
      those classes is recommended only with a complete peak attestation for
      exactly that artifact (``peak_unverified(mid) is False``, i.e.
      ``model_sha256`` equals that model's catalog sha256). Without it the
      recommendation is at most 4B; 8B/27B stay selectable ``alternatives``
      when they pass ``usable_ram_fits`` and the disk check. An 8B attestation never unlocks 27B.
    * 8B: fits/alternative from 15.0 GiB total when its budget fits the
      current free RAM (``usable_ram_fits``). Recommendation gate unchanged
      (>= 23.0 GiB total, >= 4 physical cores, free RAM ok) plus attestation.
      Below 4 cores with 8B fitting, ``slow_cpu`` is set. UNSICHER: 8B speed
      on a 2-core i3 is not measured.
    * 27B: recommended only on >= 47 GiB total and >= 12 physical cores, when
      its 14.0 GiB budget fits the current free RAM (unchanged) plus
      attestation. UNSICHER: the attestation peak bound is the i3 / 8 GB gate
      (3.3e9 bytes) for every class; per-class gates are only a proposal.
    * None only with reason ``ram_too_small`` (total below 7.0 GiB) or
      ``disk_too_small`` (no class-eligible file fits on disk).
    """
    order = list(SETUP_MODEL_CATALOG)
    by_class = {SETUP_MODEL_CATALOG[mid].get("model_class"): mid for mid in order}
    unverified = {mid: peak_unverified(mid, attestation) for mid in order}
    # installed: device check on the INSTALLED device (class gate + headroom
    # on total RAM, disk). Only used for the device-level slow_cpu warning.
    installed = {mid: installed_ram_fits(SETUP_MODEL_CATALOG[mid].get("model_class", CLASS_4B), total_gib,
                                         SETUP_MODEL_CATALOG[mid]["ram_gb_min"])
                      and _disk_ok(mid, free_disk_bytes)
                 for mid in order}
    # The ONE RAM rule shared with guenther.device_check and the setup panel
    # (model_budgets.usable_ram_fits): 4B by installed RAM, 8B/27B by
    # min(total, free) - 2 GiB. fits, alternatives and the recommendation all
    # derive from it, so no consumer is offered a model the app cannot load now.
    free_ram_ok = {mid: usable_ram_fits(SETUP_MODEL_CATALOG[mid].get("model_class", CLASS_4B),
                                        total_gib=total_gib, available_gib=available_gib,
                                        own_gib=SETUP_MODEL_CATALOG[mid]["ram_gb_min"])
                   for mid in order}
    fits = {mid: free_ram_ok[mid] and _disk_ok(mid, free_disk_bytes) for mid in order}
    eligible = [mid for mid in order if fits[mid]]

    preference = []
    big, mid8, small = by_class.get(CLASS_27B), by_class.get(CLASS_8B), by_class.get(CLASS_4B)
    # 27B: unchanged 47 GiB / 12-core gate, plus a complete peak attestation
    # for exactly the 27B artifact (attestation duty for all classes above 4B).
    if (big in eligible and free_ram_ok[big] and not unverified[big]
            and total_gib >= RECOMMEND_27B_MIN_TOTAL_GIB
            and physical_cores >= RECOMMEND_27B_MIN_CORES):
        preference.append(big)
    # 8B: unchanged 23 GiB / 4-core gate, plus a complete peak attestation.
    if (mid8 in eligible and free_ram_ok[mid8] and not unverified[mid8]
            and total_gib >= RECOMMEND_8B_MIN_TOTAL_GIB
            and physical_cores >= RECOMMEND_8B_MIN_CORES):
        preference.append(mid8)
    if small in eligible and free_ram_ok[small]:
        preference.append(small)
    model_id = preference[0] if preference else None

    warnings = []
    # Reachable per-class threshold (model_budgets.LOW_FREE_RAM_WARN_GIB),
    # not the stricter device_check budget (6.0 + 2.0 GiB never fits 7.7 GiB).
    if model_id is not None and low_free_ram(
            SETUP_MODEL_CATALOG[model_id].get("model_class", CLASS_4B), available_gib):
        warnings.append(WARNING_LOW_FREE_RAM)
    if mid8 is not None and installed[mid8] and physical_cores < RECOMMEND_8B_MIN_CORES:
        warnings.append(WARNING_SLOW_CPU)
    # Best first: larger classes before smaller ones among the rest; only
    # models that pass usable_ram_fits and the disk check (see fits).
    alternatives = tuple(mid for mid in reversed(order) if fits[mid] and mid != model_id)

    reason = None
    if model_id is None:
        reason = (REASON_RAM_TOO_SMALL if small is None
                  or not class_gate_passes(CLASS_4B, total_gib) else REASON_DISK_TOO_SMALL)
    return SetupRecommendation(total_gib, available_gib, physical_cores, free_disk_bytes,
                               model_id, reason=reason, warnings=tuple(warnings),
                               alternatives=alternatives, fits=fits,
                               peak_unverified=unverified)


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
    if cancelled():
        raise RuntimeError("cancelled")
    activate_model(model_id, manager.models_dir)
    return manager.model_path(model_id)
