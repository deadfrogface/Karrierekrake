#!/usr/bin/env python3
"""Informational Peak-RSS measurement for Docling + Qwen CV import (Agent-VM).

NOT ship evidence. Ship requires Windows Job Object PeakJobMemoryUsed on the
real Intel Core i3 / 8 GB Windows laptop:
  scripts/run_docpick_job_object_peak_windows.ps1

Hard gate: ≤ 3_300_000_000 bytes (process group). Soft ≤12 GB obsolete.
NO automatic Phi fallback.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tests" / "docpick_qwen35" / "peak_rss_gate"
DEFAULT_PDF = (
    ROOT
    / "tests"
    / "docpick_qwen35"
    / "regression_known_cvs"
    / "pdfs"  # may not exist
)


def _self_rss_mb() -> float:
    # Linux: ru_maxrss is KB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _read_proc_rss_mb(pid: int) -> float | None:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            # value in kB
            return float(parts[1]) / 1024.0
    return None


def _read_proc_peak_mb(pid: int) -> float | None:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith("VmPeak:"):
            parts = line.split()
            return float(parts[1]) / 1024.0
    return None


def _find_llama_pids() -> list[int]:
    pids: list[int] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().decode("utf-8", "ignore")
        except OSError:
            continue
        if "llama_cpp.server" in cmdline or "llama-server" in cmdline:
            pids.append(int(entry.name))
    return pids


def _pick_pdf() -> Path:
    env = os.environ.get("KARRIEREKRAKE_CV_PEAK_RSS_PDF")
    if env and Path(env).is_file():
        return Path(env)
    candidates = [
        ROOT / "tests/docpick_blind_de_en_v2/phase_a_pdfs/NV3_014.pdf",
        ROOT / "tests/docpick_qwen35/regression_known_cvs/SMOKE_DE_EN_10_V1/DE_01.pdf",
    ]
    # Manifest-based fallback
    manifest = ROOT / "tests/docpick_qwen35/regression_known_cvs/EXTRACTION_MANIFEST_PDF_ONLY.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for d in data.get("documents") or []:
            p = ROOT / d["path"]
            if p.is_file():
                candidates.insert(0, p)
                break
    for c in candidates:
        if c.is_file():
            return c
    raise SystemExit("no representative PDF found for Peak-RSS measurement")


def main() -> int:
    os.environ.setdefault("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
    from core.cv_docpick_import import (
        CV_IMPORT_PEAK_RSS_BYTES_MAX,
        CV_IMPORT_PEAK_RSS_MB_MAX,
        import_cv_docpick,
    )

    pdf = _pick_pdf()
    OUT.mkdir(parents=True, exist_ok=True)

    llama_pids = _find_llama_pids()
    samples: list[dict[str, Any]] = []
    stop = threading.Event()

    def sampler() -> None:
        while not stop.is_set():
            self_rss = _self_rss_mb()
            llama_rss = 0.0
            for pid in list(llama_pids) or _find_llama_pids():
                r = _read_proc_rss_mb(pid)
                if r is not None:
                    llama_rss += r
            samples.append(
                {
                    "t": time.time(),
                    "self_rss_mb": round(self_rss, 1),
                    "llama_rss_mb": round(llama_rss, 1),
                    "combined_mb": round(self_rss + llama_rss, 1),
                }
            )
            time.sleep(0.25)

    # Baseline before import
    llama_before = sum(
        (_read_proc_rss_mb(p) or 0.0) for p in (llama_pids or _find_llama_pids())
    )
    llama_vmpeak_before = max(
        (_read_proc_peak_mb(p) or 0.0) for p in (llama_pids or [0])
    ) if llama_pids else 0.0

    thr = threading.Thread(target=sampler, daemon=True)
    thr.start()
    t0 = time.perf_counter()
    ui_froze = None  # CLI measurement — no UI exercised
    err = None
    try:
        parsed = import_cv_docpick(pdf)
        ok = bool((parsed.get("personal") or {}).get("first_name"))
    except Exception as exc:  # noqa: BLE001
        parsed = {}
        ok = False
        err = f"{type(exc).__name__}: {exc}"
    wall = time.perf_counter() - t0
    stop.set()
    thr.join(timeout=2.0)

    self_peak = max((s["self_rss_mb"] for s in samples), default=_self_rss_mb())
    # Also include ru_maxrss which tracks high-water for this process
    self_peak = max(self_peak, _self_rss_mb())
    llama_peak = max((s["llama_rss_mb"] for s in samples), default=llama_before)
    combined_peak = max((s["combined_mb"] for s in samples), default=self_peak + llama_before)

    gate_bytes = int(CV_IMPORT_PEAK_RSS_BYTES_MAX)
    gate_mb = float(CV_IMPORT_PEAK_RSS_MB_MAX)
    # Honest CV-path peak = combined import + LLM server (MiB from /proc)
    measured_mb = combined_peak
    measured_bytes = int(round(combined_peak * 1024 * 1024))
    passed = measured_bytes <= gate_bytes and ok and err is None

    result = {
        "schema_version": 1,
        "test_type": "PEAK_RSS_INFORMATIONAL_AGENT_VM",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_hardware": "Intel Core i3 (11th gen), exactly 8 GB RAM",
        "measurement_host_note": (
            "Agent-VM / Cursor cloud — NOT the target i3/8GB Windows laptop. "
            "These numbers are informational only and are NOT kill-or-ship evidence."
        ),
        "ship_evidence": False,
        "ship_measurement": (
            "Windows Job Object PeakJobMemoryUsed via "
            "scripts/run_docpick_job_object_peak_windows.ps1"
        ),
        "kill_or_ship": (
            "#62 only ships if full app flow on real i3/8GB Win laptop stays within "
            "RAM, stable, acceptable quality/wait. Unmeasured gates stay open."
        ),
        "pdf": str(pdf.relative_to(ROOT)),
        "gate_peak_rss_bytes": gate_bytes,
        "gate_peak_rss_mb": gate_mb,
        "gate_peak_rss_gb": round(gate_bytes / 1e9, 3),
        "obsolete_soft_gate_mb": 12000,
        "obsolete_soft_gate_note": "Soft ≤12 GB / ≤12000 MB is NOT success.",
        "no_phi_fallback": True,
        "measured": {
            "import_process_peak_rss_mb": round(self_peak, 1),
            "llama_server_peak_rss_mb": round(llama_peak, 1),
            "llama_server_rss_mb_before_import": round(llama_before, 1),
            "llama_server_vmpeak_mb_before_import": round(llama_vmpeak_before, 1),
            "combined_cv_path_peak_rss_mb": round(combined_peak, 1),
            "combined_cv_path_peak_rss_bytes": measured_bytes,
            "combined_cv_path_peak_rss_gb": round(combined_peak / 1024.0, 3),
            "wall_s": round(wall, 1),
            "n_samples": len(samples),
            "llama_pids": llama_pids,
        },
        "ui_froze": ui_froze,
        "ui_note": "CLI measurement only — desktop UI not exercised in this gate run.",
        "import_ok": ok,
        "error": err,
        "gate_passed": passed,
        "verdict": "GO" if passed else "NO-GO",
        "disclaimer": (
            "Informational Agent-VM Peak only. Ship gate is Job Object "
            "≤ 3_300_000_000 bytes on real i3/8GB Win laptop. Not a quality/blind claim."
        ),
    }
    out_path = OUT / "PEAK_RSS_GATE_RESULT.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    # Human-readable report
    report = OUT / "PEAK_RSS_GATE_REPORT.md"
    gb = combined_peak / 1024.0
    report.write_text(
        "\n".join(
            [
                "# Peak-RSS (informational Agent-VM — NOT ship evidence)",
                "",
                f"- **Target (ship):** Intel Core i3 (11th gen), 8 GB RAM Windows + Job Object",
                f"- **Gate:** ≤ **3_300_000_000 bytes** (hard fail above) — soft ≤12 GB is obsolete",
                f"- **PDF:** `{pdf.relative_to(ROOT)}`",
                f"- **Import process Peak RSS:** {self_peak:.1f} MiB",
                f"- **llama.cpp server Peak RSS:** {llama_peak:.1f} MiB",
                f"- **Combined CV-path Peak:** **{measured_bytes} bytes** ({combined_peak:.1f} MiB / {gb:.3f} GiB)",
                f"- **Wall:** {wall:.1f} s",
                f"- **UI froze:** {ui_froze} (CLI only — UI not exercised)",
                f"- **Verdict (informational):** **{result['verdict']}** (gate_passed={passed})",
                "",
                "Ship evidence requires `run_docpick_job_object_peak_windows.ps1` on the laptop.",
                "If over gate after optimization: kill path Step 1 (smaller local model, no Phi); "
                "then Step 2 remove local LLM CV parsing on this hardware.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2), flush=True)
    print(
        f"VERDICT={result['verdict']} combined_peak_bytes={measured_bytes} "
        f"gate_bytes={gate_bytes}",
        flush=True,
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
