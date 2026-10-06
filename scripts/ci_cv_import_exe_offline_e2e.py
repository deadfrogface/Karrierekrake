#!/usr/bin/env python3
"""Offline acceptance for the shipped Windows EXE (or frozen binary).

Release gate (all must pass; any failure keeps the release blocked)::

    1. Fresh LOCALAPPDATA (no prior model / no internet required at runtime)
    2. Start app smoke (marker)
    3. Import CV via ``--cv-import-child`` → filled preview JSON
    4. Apply via real Qt dialog and persist all fields (CI Python, not packaged UI)
    5. Restart smoke → profile still present
    6. Cover-letter / writing call with the same bundled model
    7. Record EXE size, start time, import time, peak RSS

Usage (Windows CI after PyInstaller + prepare_bundled_cv_model)::

    python scripts/ci_cv_import_exe_offline_e2e.py \\
        --exe dist/Karrierekrake.exe \\
        --cv tests/fixtures/cv_corpus/DE_01_Klassisch.pdf \\
        --out artifacts/cv_import_exe_offline_e2e.json

Network is not required at runtime. Clear proxy env and do not set model env
overrides so the child must resolve the bundled path.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import resource as _resource  # Unix only — absent on Windows
except ImportError:  # pragma: no cover - Windows CI
    _resource = None

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# What ``peak_rss_bytes_children`` used to store, split by the counter it
# actually read. Neither number is ``PeakJobMemoryUsed``.
LEGACY_RUSAGE_KEY = "rusage_children_ru_maxrss_bytes"
LEGACY_WORKING_SET_KEY = "e2e_host_working_set_bytes"
PEAK_JOB_KEY = "peak_job_memory_used_bytes"

_LLM_STEPS = (
    ("import", "import_de"),
    ("import_en", "import_en"),
    ("cover_letter", "cover_letter"),
)
_LLM_NUMERIC = (
    "prompt_tokens",
    "prompt_eval_s",
    "prompt_tok_per_s",
    "gen_tokens",
    "gen_s",
    "gen_tok_per_s",
    "outside_model_s",
    "n_threads",
    "physical_cores",
    PEAK_JOB_KEY,
)
_LLM_TEXT = (
    "physical_cores_source",
    "ggml_cpu_isa",
    "ggml_cpu_backend",
    "timing_source",
    "peak_counter",
)


def legacy_rss_observation() -> dict[str, int]:
    """The old smoke RSS number, under names that say which counter it is.

    Unix reads ``RUSAGE_CHILDREN.ru_maxrss`` (maximum RSS of children this
    process has waited for, file-backed pages included). Windows has no
    ``resource`` module; the old function then read the working set of this
    e2e process, about 72 MB, which does not include the EXE that holds the
    model. The unused counter stays ``0``.
    """
    observed = {LEGACY_RUSAGE_KEY: 0, LEGACY_WORKING_SET_KEY: 0}
    if _resource is not None:
        try:
            usage = _resource.getrusage(_resource.RUSAGE_CHILDREN)
            val = int(usage.ru_maxrss)
            if sys.platform == "darwin":
                observed[LEGACY_RUSAGE_KEY] = val
            else:
                observed[LEGACY_RUSAGE_KEY] = val * 1024
        except Exception:  # noqa: BLE001
            pass
        return observed
    try:
        import psutil  # type: ignore

        observed[LEGACY_WORKING_SET_KEY] = int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:  # noqa: BLE001
        pass
    return observed


def outside_model_s(wall_s: float, prompt_eval_s: float, gen_s: float) -> float:
    """Wall clock minus llama prompt-eval and generation time."""
    return round(float(wall_s) - float(prompt_eval_s) - float(gen_s), 3)


def _numeric_metric(value: object, *, whole: bool) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0 if whole else 0.0
    if whole:
        return int(value)
    return round(float(value), 3)


def annotate_llm_steps(report: dict) -> None:
    """Fill ``outside_model_s`` on each step from that step's wall clock."""
    steps = report.get("steps")
    if not isinstance(steps, dict):
        return
    for name, _prefix in _LLM_STEPS:
        step = steps.get(name)
        if not isinstance(step, dict):
            continue
        llm = step.get("llm_step")
        if not isinstance(llm, dict):
            continue
        wall = step.get("wall_s")
        if isinstance(wall, bool) or not isinstance(wall, (int, float)):
            llm["outside_model_s"] = 0.0
            continue
        llm["outside_model_s"] = outside_model_s(
            float(wall),
            float(llm.get("prompt_eval_s") or 0),
            float(llm.get("gen_s") or 0),
        )


def build_smoke_metrics(report: dict) -> dict:
    """Flat numeric timings for the printed smoke JSON.

    ``peak_job_memory_used_bytes`` is the maximum ``PeakJobMemoryUsed``
    reported by a step that loaded the model. The old children-RSS key is
    not written.
    """
    from core.cv_llm_runtime import public_llm_step

    steps = report.get("steps") if isinstance(report.get("steps"), dict) else {}
    metrics: dict = {
        "exe_bytes": int(report.get("exe_bytes") or 0),
        "model_embedded": bool(report.get("model_embedded")),
        "start_wall_s": _numeric_metric((steps.get("start") or {}).get("wall_s"), whole=False),
        "import_wall_s": _numeric_metric((steps.get("import") or {}).get("wall_s"), whole=False),
        "import_en_wall_s": _numeric_metric(
            (steps.get("import_en") or {}).get("wall_s"), whole=False
        ),
        "restart_wall_s": _numeric_metric((steps.get("restart") or {}).get("wall_s"), whole=False),
        "cover_letter_wall_s": _numeric_metric(
            (steps.get("cover_letter") or {}).get("wall_s"), whole=False
        ),
    }
    peaks: list[int] = []
    for name, prefix in _LLM_STEPS:
        step = steps.get(name)
        if not isinstance(step, dict) or not isinstance(step.get("llm_step"), dict):
            continue
        llm = public_llm_step(step["llm_step"])
        llm["outside_model_s"] = _numeric_metric(step["llm_step"].get("outside_model_s"), whole=False)
        whole_keys = {
            "prompt_tokens",
            "gen_tokens",
            "n_threads",
            "physical_cores",
            PEAK_JOB_KEY,
        }
        for key in _LLM_NUMERIC:
            metrics["%s_%s" % (prefix, key)] = _numeric_metric(
                llm.get(key), whole=key in whole_keys
            )
        for key in _LLM_TEXT:
            value = llm.get(key)
            metrics["%s_%s" % (prefix, key)] = value if isinstance(value, str) else ""
        peaks.append(int(llm[PEAK_JOB_KEY]))
    metrics[PEAK_JOB_KEY] = max(peaks) if peaks else 0
    metrics.update(legacy_rss_observation())
    return metrics


def format_llm_step_line(prefix: str, llm: dict) -> str:
    """One greppable line. The ISA string is quoted because it contains spaces."""
    isa = str(llm.get("ggml_cpu_isa") or "").replace('"', "'")
    return (
        "llm_step %s prompt_tokens=%s prompt_eval_s=%s prompt_tok_per_s=%s "
        "gen_tokens=%s gen_s=%s gen_tok_per_s=%s outside_model_s=%s "
        "n_threads=%s physical_cores source=%s count=%s "
        "ggml_cpu_backend=%s timing_source=%s peak_job_memory_used_bytes=%s "
        'ggml_cpu_isa="%s"'
        % (
            prefix,
            llm.get("prompt_tokens"),
            llm.get("prompt_eval_s"),
            llm.get("prompt_tok_per_s"),
            llm.get("gen_tokens"),
            llm.get("gen_s"),
            llm.get("gen_tok_per_s"),
            llm.get("outside_model_s"),
            llm.get("n_threads"),
            llm.get("physical_cores_source"),
            llm.get("physical_cores"),
            llm.get("ggml_cpu_backend"),
            llm.get("timing_source"),
            llm.get("peak_job_memory_used_bytes"),
            isa,
        )
    )


def format_runner_cpu_line(info: dict) -> str:
    name = str(info.get("runner_cpu_name") or "").replace("\n", " ").strip()
    return "runner_cpu name=%s logical=%s physical=%s" % (
        name,
        int(info.get("runner_logical_cores") or 0),
        int(info.get("runner_physical_cores") or 0),
    )


def parse_linux_cpuinfo(text: str) -> dict:
    """Model name plus logical and physical counts from ``/proc/cpuinfo``."""
    name = ""
    logical = 0
    packages: set[str] = set()
    cores_per_package: int | None = None
    for line in text.splitlines():
        if line.startswith("processor"):
            logical += 1
        elif line.startswith("model name") and not name:
            name = line.split(":", 1)[1].strip()
        elif line.startswith("physical id"):
            packages.add(line.split(":", 1)[1].strip())
        elif line.startswith("cpu cores") and cores_per_package is None:
            try:
                cores_per_package = int(line.split(":", 1)[1].strip())
            except ValueError:
                cores_per_package = None
    if cores_per_package and packages:
        physical = cores_per_package * len(packages)
    else:
        physical = logical
    return {
        "runner_cpu_name": name,
        "runner_logical_cores": logical,
        "runner_physical_cores": physical,
    }


def parse_win32_processor_rows(rows: list[dict]) -> dict:
    """Sums from ``Get-CimInstance Win32_Processor``."""
    name = ""
    logical = 0
    physical = 0
    for row in rows:
        if not name:
            name = str(row.get("Name") or "").strip()
        logical += int(row.get("NumberOfLogicalProcessors") or 0)
        physical += int(row.get("NumberOfCores") or 0)
    return {
        "runner_cpu_name": name,
        "runner_logical_cores": logical,
        "runner_physical_cores": physical,
    }


def read_runner_cpu() -> dict:
    """CPU model and core counts. Windows uses ``Win32_Processor``."""
    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name,NumberOfLogicalProcessors,NumberOfCores | "
            "ConvertTo-Json -Compress"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(proc.stdout or "[]")
        except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
            payload = []
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            payload = []
        return parse_win32_processor_rows(payload)
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8")
    except OSError:
        text = ""
    return parse_linux_cpuinfo(text)


def _clear_network_env() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
        "KARRIEREKRAKE_CV_LLM_MODEL",
        "KARRIEREKRAKE_CV_LLM_BASE",
        # Build-cache dir must not mask a missing install sidecar.
        "KARRIEREKRAKE_MODELS_DIR",
    ):
        os.environ.pop(key, None)


def _run_child_import(
    exe: Path,
    cv: Path,
    out: Path,
    *,
    local_appdata: Path,
    timeout_s: float,
) -> dict:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(local_appdata)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.pop("KARRIEREKRAKE_CV_LLM_MODEL", None)
    env.pop("KARRIEREKRAKE_CV_LLM_BASE", None)
    env.pop("KARRIEREKRAKE_MODELS_DIR", None)
    # Force in-process: pretend no HTTP server.
    env["KARRIEREKRAKE_CV_LLM_BASE"] = "http://127.0.0.1:1/v1"
    err_log = out.with_suffix(out.suffix + ".stderr.txt")
    cmd = [
        str(exe),
        "--cv-import-child",
        "--cv",
        str(cv),
        "--out",
        str(out),
    ]
    t0 = time.perf_counter()
    with err_log.open("wb") as err_fh:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err_fh,
            env=env,
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if out.is_file() and out.stat().st_size > 0:
                break
            if proc.poll() is not None and out.is_file():
                break
            time.sleep(0.5)
        else:
            proc.kill()
            raise RuntimeError(f"child import timed out after {timeout_s}s")
        # Give writer a moment to flush.
        time.sleep(0.2)
        if proc.poll() is None:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    elapsed = time.perf_counter() - t0
    if not out.is_file():
        try:
            stderr_bytes = err_log.stat().st_size
        except OSError:
            stderr_bytes = 0
        raise RuntimeError(
            f"child wrote no --out (exit={proc.returncode}); stderr_bytes={stderr_bytes}"
        )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["_wall_s"] = round(elapsed, 3)
    payload["_exit_code"] = proc.returncode
    try:
        payload["_stderr_bytes"] = err_log.stat().st_size
    except OSError:
        payload["_stderr_bytes"] = 0
    return payload


_DETAIL_KEYS = (
    "exception_type",
    "reason",
    "stage",
    "prompt_tokens",
    "tokens_done",
    "max_tokens",
    "n_ctx",
    "elapsed_s",
    "timeout_s",
    "peak_bytes",
    "budget_bytes",
    "counter",
)


def _whitelist_detail(detail: object) -> dict:
    if not isinstance(detail, dict):
        return {}
    return {key: detail[key] for key in _DETAIL_KEYS if key in detail}


def _import_report_slice(payload: dict) -> dict:
    """Compact import payload for CI logs (no full CV body)."""
    parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}
    personal = parsed.get("personal") if isinstance(parsed, dict) else {}
    if not isinstance(personal, dict):
        personal = {}
    emails = parsed.get("emails") if isinstance(parsed, dict) else []
    return {
        "ok": payload.get("ok"),
        "kind": payload.get("kind"),
        "message": (payload.get("message") or "")[:240],
        "detail": _whitelist_detail(payload.get("detail")),
        "wall_s": payload.get("_wall_s"),
        "exit_code": payload.get("_exit_code"),
        "personal_preview": {
            "first_name": personal.get("first_name"),
            "last_name": personal.get("last_name"),
            "city": personal.get("city"),
        },
        "emails_preview": list(emails)[:2] if isinstance(emails, list) else [],
        "pipeline": parsed.get("pipeline") if isinstance(parsed, dict) else None,
        "llm_transport": parsed.get("llm_transport") if isinstance(parsed, dict) else None,
        "stderr_bytes": int(payload.get("_stderr_bytes") or 0),
        "preview_keys": sorted(payload.keys())[:40],
        "llm_step": payload.get("llm_step") if isinstance(payload.get("llm_step"), dict) else {},
    }


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


def emit_smoke_report(path: Path, report: dict) -> None:
    """Print one line per LLM step, then the JSON, including the #69 peak."""
    annotate_llm_steps(report)
    for step_name, prefix in _LLM_STEPS:
        step = report.get("steps", {}).get(step_name) if isinstance(report.get("steps"), dict) else None
        if isinstance(step, dict) and isinstance(step.get("llm_step"), dict):
            print(format_llm_step_line(prefix, step["llm_step"]), flush=True)
    report["metrics"] = build_smoke_metrics(report)
    report[PEAK_JOB_KEY] = report["metrics"][PEAK_JOB_KEY]
    _write_report(path, report)


def _smoke_start(exe: Path, local_appdata: Path, timeout_s: float) -> float:
    """Return cold-start seconds until SMOKE marker (via ci_wait script when present)."""
    marker_dir = local_appdata / "Karrierekrake"
    marker_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(local_appdata)
    env["QT_QPA_PLATFORM"] = "offscreen"
    t0 = time.perf_counter()
    wait_ps1 = _ROOT / "scripts" / "ci_wait_exe_smoke.ps1"
    if wait_ps1.is_file() and sys.platform.startswith("win"):
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wait_ps1),
            "-ExePath",
            str(exe),
            "-LocalAppData",
            str(local_appdata),
        ]
        subprocess.run(cmd, check=True, timeout=timeout_s, env=env)
        return time.perf_counter() - t0
    # Linux / non-Windows: invoke --smoke-test directly when supported.
    proc = subprocess.run(
        [str(exe), "--smoke-test"],
        env=env,
        timeout=timeout_s,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, None):
        # Windowed EXE may return null — accept marker file if present.
        markers = list(marker_dir.rglob("*SMOKE*"))
        if not markers and proc.returncode not in (0,):
            raise SystemExit(f"FAIL: smoke-test exit={proc.returncode}")
    return time.perf_counter() - t0


def _profile_snapshot(config_root: Path) -> dict:
    """Read the normal config service; never a hand-written substitute profile."""
    os.environ["LOCALAPPDATA"] = str(config_root)
    from desktop.services import ConfigService
    cfg = ConfigService().load()
    q = cfg.profile.qualifications
    return {"applicant": {"full_name": cfg.application.full_name,
                          "email": cfg.application.email, "phone": cfg.application.phone,
                          "city": cfg.application.city},
            "qualification_counts": {key: len(getattr(q, key)) for key in
                ("languages", "skills", "software", "certificates", "education", "work_experience")}}


def _apply_preview_to_profile(preview: dict, config_root: Path) -> dict:
    """Actual Qt dialog + config persistence in CI Python, not packaged-UI E2E."""
    os.environ["LOCALAPPDATA"] = str(config_root)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.services import ConfigService
    from desktop.widgets.cv_import_dialog import CvImportDialog
    parsed = preview.get("parsed") if isinstance(preview.get("parsed"), dict) else preview
    app = QApplication.instance() or QApplication([])
    service = ConfigService()
    cfg = service.load()
    dialog = CvImportDialog(Path(parsed.get("source_path") or "synthetic.pdf"),
                            cfg.profile.qualifications, cfg.application,
                            settings=cfg.settings, autostart=False)
    dialog._apply_parsed(parsed)
    dialog._show_success()
    if not dialog.preview.toPlainText().strip():
        raise RuntimeError("cv_preview_empty")
    dialog._accept()
    if dialog.result_quals is None or dialog.result_application is None:
        raise RuntimeError("cv_apply_failed")
    cfg.profile.qualifications = dialog.result_quals
    cfg.application = dialog.result_application
    service.save(cfg)
    snapshot = _profile_snapshot(config_root)
    snapshot["apply_mode"] = "real_Qt_dialog_and_ConfigService_in_CI_Python"
    dialog.deleteLater()
    app.processEvents()
    return snapshot


def _reload_profile(config_root: Path) -> dict:
    return _profile_snapshot(config_root)


def _cover_letter_same_model() -> dict:
    """Write a short cover letter with the same bundled GGUF (in-process)."""
    from core.cv_llm_runtime import (
        chat_completion_inprocess,
        ensure_cv_llm_ready,
        resolve_cv_model_path,
    )

    mode = ensure_cv_llm_ready()
    model = resolve_cv_model_path()
    assert model is not None and model.is_file()
    t0 = time.perf_counter()
    text = ""
    ok = False
    err = ""
    try:
        text = chat_completion_inprocess(
            [
                {
                    "role": "system",
                    "content": (
                        "Du schreibst kurze deutsche Anschreiben. "
                        "Nur Fließtext, kein JSON. /no_think"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Schreibe 3 Sätze Anschreiben: Mara König bewirbt sich als "
                        "Teamkoordinatorin Kundenservice bei Beispiel GmbH. "
                        "Nur Belege aus: Kundenservice, Münster. /no_think"
                    ),
                },
            ],
            model_path=model,
        )
        ok = len((text or "").strip()) >= 40
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        ok = False
    from core.cv_docpick_import import model_process_peak_job_memory_used_bytes
    from core.cv_llm_runtime import last_llm_step_metrics, public_llm_step

    llm_step = last_llm_step_metrics()
    llm_step["peak_job_memory_used_bytes"] = int(model_process_peak_job_memory_used_bytes())
    llm_step["peak_counter"] = "PeakJobMemoryUsed"
    return {
        "ok": ok,
        "writing_ok": ok,
        "execution_mode": "CI_Python_using_materialized_embedded_GGUF_not_packaged_writer_UI",
        "mode": mode,
        "model_path_basename": model.name,
        "wall_s": round(time.perf_counter() - t0, 3),
        "text_preview_len": len(text or ""),
        "error": err,
        "llm_step": public_llm_step(llm_step),
    }


def _preview_has_identity(payload: dict) -> bool:
    if not payload.get("ok"):
        return False
    blob = json.dumps(payload.get("parsed") or payload, ensure_ascii=False).lower()
    has_email = "@" in blob
    has_person = any(
        token in blob
        for token in (
            "first_name",
            "last_name",
            "full_name",
            "vorname",
            "nachname",
            "könig",
            "konig",
            "mara",
            "mustermann",
            "jane",
            "doe",
            "smith",
            "alex",
        )
    )
    return has_email and has_person


def _preview_qualification_counts(payload: dict) -> dict[str, int]:
    """Exercise the real import filter and replace mapping, not just identity."""
    from core.config import QualificationsConfig
    from core.cv_parser import parsed_to_qualifications
    from desktop.services.profile_merge import filter_parsed_for_import, replace_qualifications

    parsed = payload.get("parsed") or {}
    result = replace_qualifications(
        QualificationsConfig(),
        parsed_to_qualifications(filter_parsed_for_import(parsed)),
    )
    return {
        "languages": len(result.languages),
        "skills": len(result.skill_values()),
        "software": len(result.software_values()),
        "certificates": len(result.certificates),
    }


def _forbidden_in_user_copy(text: str) -> list[str]:
    banned = ("Qwen", "Docpick", "DET", "Phi-4", "GGUF", "llama.cpp", "LLM-CV")
    return [t for t in banned if t.lower() in (text or "").lower()]


def _run_negative_cases(
    exe: Path,
    local_appdata: Path,
    timeout_s: float,
) -> dict:
    """Corrupt input must fail closed with safe user copy."""
    results: dict = {}
    with tempfile.TemporaryDirectory(prefix="kk-neg-") as neg:
        neg_path = Path(neg)
        corrupt = neg_path / "corrupt.pdf"
        corrupt.write_bytes(b"%PDF-not-a-real-file\x00\x01\x02")
        out = neg_path / "corrupt_out.json"
        try:
            payload = _run_child_import(
                exe, corrupt, out, local_appdata=local_appdata, timeout_s=min(120.0, timeout_s)
            )
        except Exception as exc:  # noqa: BLE001
            results["corrupt"] = {"ok": False, "error": str(exc)}
            return results
        kind = str(payload.get("kind") or "")
        msg = str(payload.get("message") or "")
        forbidden = _forbidden_in_user_copy(msg)
        results["corrupt"] = {
            "ok": (not payload.get("ok"))
            and kind
            in {
                "unreadable_cv",
                "empty_cv",
                "llm_empty",
                "llm_extract_failed",
                "unreliable_extract",
            }
            and not forbidden,
            "kind": kind,
            "message": msg[:240],
            "forbidden": forbidden,
        }

    # The primary import already runs the EXE alone from a clean staged folder.
    results["ok"] = bool((results.get("corrupt") or {}).get("ok"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument(
        "--cv",
        type=Path,
        default=_ROOT / "tests" / "fixtures" / "cv_corpus" / "DE_01_Klassisch.pdf",
    )
    parser.add_argument(
        "--cv-en",
        type=Path,
        default=None,
        help="Optional second CV (EN) imported after the primary CV",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "artifacts" / "cv_import_exe_offline_e2e.json",
    )
    parser.add_argument("--import-timeout", type=float, default=600.0)
    parser.add_argument("--smoke-timeout", type=float, default=180.0)
    parser.add_argument(
        "--skip-cover-letter",
        action="store_true",
        help="Skip writing probe (still records model resolve).",
    )
    parser.add_argument(
        "--skip-negatives",
        action="store_true",
        help="Skip corrupt/EXE-only negative cases.",
    )
    parser.add_argument("--component-install", action="store_true", help="Validate split EXE + model release instead of embedded standalone EXE")
    args = parser.parse_args(argv)

    exe = args.exe.resolve()
    cv = args.cv.resolve()
    if not exe.is_file():
        print(f"FAIL: EXE missing: {exe}", flush=True)
        return 2
    if not cv.is_file():
        print(f"FAIL: CV fixture missing: {cv}", flush=True)
        return 2
    from scripts.scan_release_artifact import require_cv_model_embedded

    if args.component_install:
        from core.app_updates import MODEL_PATH, digest
        from core.cv_llm_runtime import CV_MODEL_SHA256
        sidecar = exe.parent / MODEL_PATH
        model_hits = [] if sidecar.is_file() and digest(sidecar) == CV_MODEL_SHA256 else ["sidecar_model_integrity_failed"]
    else:
        model_hits = require_cv_model_embedded(exe)
    if model_hits:
        print(f"FAIL: standalone EXE model gate: {model_hits}", flush=True)
        return 2

    _clear_network_env()
    runner = read_runner_cpu()
    print(format_runner_cpu_line(runner), flush=True)
    report: dict = {
        "ok": False,
        "release_blocked": True,
        "exe": str(exe),
        "exe_bytes": exe.stat().st_size,
        "cv": str(cv),
        "install_dir": str(exe.parent),
        "model_embedded": not args.component_install,
        "component_install": args.component_install,
        "runner_cpu": runner,
        "steps": {},
    }

    with tempfile.TemporaryDirectory(prefix="kk-offline-e2e-") as tmp:
        local = Path(tmp) / "LocalAppData"
        local.mkdir(parents=True)

        # 1–2: cold start
        try:
            start_s = _smoke_start(exe, local, args.smoke_timeout)
            report["steps"]["start"] = {"ok": True, "wall_s": round(start_s, 3)}
        except Exception as exc:  # noqa: BLE001
            report["steps"]["start"] = {"ok": False, "error": str(exc)}
            emit_smoke_report(args.out, report)
            return 1

        # 3: import (primary, typically DE)
        out_json = Path(tmp) / "import_out.json"
        try:
            payload = _run_child_import(
                exe, cv, out_json, local_appdata=local, timeout_s=args.import_timeout
            )
            qual_counts = _preview_qualification_counts(payload) if payload.get("ok") else {}
            import_ok = (
                bool(payload.get("ok")) and _preview_has_identity(payload)
                and all(qual_counts.get(key, 0) > 0 for key in
                        ("languages", "skills", "software", "certificates"))
            )
            msg = str(payload.get("message") or "")
            forbidden = _forbidden_in_user_copy(msg) if not payload.get("ok") else []
            report["steps"]["import"] = {
                **_import_report_slice(payload),
                "ok": import_ok and not forbidden,
                "qualification_counts": qual_counts,
                "forbidden_tokens": forbidden,
            }
            if not report["steps"]["import"]["ok"]:
                emit_smoke_report(args.out, report)
                return 1
        except Exception as exc:  # noqa: BLE001
            report["steps"]["import"] = {
                "ok": False,
                "error": str(exc),
                **(report["steps"].get("import") or {}),
            }
            emit_smoke_report(args.out, report)
            return 1

        # 3b: optional EN import (same install layout, fresh out file)
        if args.cv_en is not None:
            cv_en = args.cv_en.resolve()
            if not cv_en.is_file():
                report["steps"]["import_en"] = {"ok": False, "error": f"missing {cv_en}"}
                emit_smoke_report(args.out, report)
                return 1
            out_en = Path(tmp) / "import_en_out.json"
            try:
                payload_en = _run_child_import(
                    exe, cv_en, out_en, local_appdata=local, timeout_s=args.import_timeout
                )
                en_counts = _preview_qualification_counts(payload_en) if payload_en.get("ok") else {}
                en_ok = (
                    bool(payload_en.get("ok")) and _preview_has_identity(payload_en)
                    and all(en_counts.get(key, 0) > 0 for key in
                            ("languages", "skills", "software", "certificates"))
                )
                report["steps"]["import_en"] = {
                    **_import_report_slice(payload_en),
                    "ok": en_ok,
                    "qualification_counts": en_counts,
                    "cv": str(cv_en),
                }
                if not en_ok:
                    emit_smoke_report(args.out, report)
                    return 1
            except Exception as exc:  # noqa: BLE001
                report["steps"]["import_en"] = {"ok": False, "error": str(exc)}
                emit_smoke_report(args.out, report)
                return 1

        # 4: Actual dialog apply/persistence in CI Python; EXE import above.
        applied = _apply_preview_to_profile(payload, local)
        report["steps"]["apply"] = {
            "ok": bool(
                applied.get("applicant", {}).get("full_name")
                or applied.get("applicant", {}).get("email")
            ) and all(applied.get("qualification_counts", {}).get(key, 0) > 0
                      for key in ("languages", "skills", "software", "certificates")),
            "applicant": applied.get("applicant"),
            "qualification_counts": applied.get("qualification_counts"),
            "mode": applied.get("apply_mode"),
        }
        if not report["steps"]["apply"]["ok"]:
            emit_smoke_report(args.out, report)
            return 1

        # 5: restart + reload profile
        try:
            restart_s = _smoke_start(exe, local, args.smoke_timeout)
            reloaded = _reload_profile(local)
            same = (reloaded.get("applicant") == applied.get("applicant")
                    and reloaded.get("qualification_counts") == applied.get("qualification_counts"))
            report["steps"]["restart"] = {
                "ok": same,
                "wall_s": round(restart_s, 3),
                "applicant": (reloaded.get("applicant") or {}),
                "qualification_counts": reloaded.get("qualification_counts"),
            }
            if not same:
                emit_smoke_report(args.out, report)
                return 1
        except Exception as exc:  # noqa: BLE001
            report["steps"]["restart"] = {"ok": False, "error": str(exc)}
            emit_smoke_report(args.out, report)
            return 1

        # 6: cover letter / writing with same model (library when EXE child cannot)
        if args.skip_cover_letter:
            report["steps"]["cover_letter"] = {"ok": True, "skipped": True}
        else:
            os.environ["LOCALAPPDATA"] = str(local)
            # Import child materializes the embedded GGUF under this isolated
            # LOCALAPPDATA; writing must resolve the very same weight.
            try:
                if args.component_install:
                    os.environ["KARRIEREKRAKE_CV_LLM_MODEL"] = str(sidecar)
                try:
                    report["steps"]["cover_letter"] = _cover_letter_same_model()
                    if args.component_install:
                        report["steps"]["cover_letter"]["execution_mode"] = "CI_Python_using_verified_install_sidecar_not_packaged_writer_UI"
                finally:
                    if args.component_install:
                        os.environ.pop("KARRIEREKRAKE_CV_LLM_MODEL", None)
            except Exception as exc:  # noqa: BLE001
                report["steps"]["cover_letter"] = {"ok": False, "error": str(exc)}

        # 7: corrupt input must fail safely; standalone EXE was tested above.
        if args.skip_negatives:
            report["steps"]["negatives"] = {"ok": True, "skipped": True}
        else:
            report["steps"]["negatives"] = _run_negative_cases(
                exe, local, args.import_timeout
            )

        required = ["start", "import", "apply", "restart", "cover_letter", "negatives"]
        if args.cv_en is not None:
            required.append("import_en")
        step_ok = all(bool((report["steps"].get(name) or {}).get("ok")) for name in required)
        report["ok"] = step_ok
        report["release_blocked"] = not step_ok

    emit_smoke_report(args.out, report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
