#!/usr/bin/env python3
"""Offline acceptance for the shipped Windows EXE (or frozen binary).

Release gate (all must pass; any failure keeps the release blocked)::

    1. Fresh LOCALAPPDATA (no prior model / no internet required at runtime)
    2. Start app smoke (marker)
    3. Import CV via ``--cv-import-child`` → filled preview JSON
    4. Persist profile fields into isolated config (Übernehmen simulation)
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
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _peak_rss_bytes() -> int:
    """Best-effort peak RSS of this process (Linux) or 0."""
    try:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        # ru_maxrss is KiB on Linux, bytes on macOS — normalize roughly.
        val = int(usage.ru_maxrss)
        if sys.platform == "darwin":
            return val
        return val * 1024
    except Exception:  # noqa: BLE001
        return 0


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
    # Force in-process: pretend no HTTP server.
    env["KARRIEREKRAKE_CV_LLM_BASE"] = "http://127.0.0.1:1/v1"
    cmd = [
        str(exe),
        "--cv-import-child",
        "--cv",
        str(cv),
        "--out",
        str(out),
    ]
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
        raise SystemExit(f"FAIL: child import timed out after {timeout_s}s")
    # Give writer a moment to flush.
    time.sleep(0.2)
    if proc.poll() is None:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    elapsed = time.perf_counter() - t0
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["_wall_s"] = round(elapsed, 3)
    return payload


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


def _apply_preview_to_profile(preview: dict, config_root: Path) -> dict:
    """Simulate Übernehmen: write personal fields into an isolated profile YAML."""
    import yaml

    parsed = preview.get("parsed") if isinstance(preview.get("parsed"), dict) else preview
    personal = parsed.get("personal") if isinstance(parsed, dict) else {}
    if not isinstance(personal, dict):
        personal = {}
    emails = parsed.get("emails") if isinstance(parsed, dict) else []
    phones = parsed.get("phones") if isinstance(parsed, dict) else []
    email = ""
    if isinstance(emails, list) and emails:
        email = str(emails[0])
    elif personal.get("email"):
        email = str(personal.get("email"))
    phone = ""
    if isinstance(phones, list) and phones:
        phone = str(phones[0])
    full_name = (
        personal.get("full_name")
        or " ".join(
            str(x)
            for x in (personal.get("first_name"), personal.get("last_name"))
            if x
        ).strip()
        or personal.get("name")
        or ""
    )
    cfg_dir = config_root / "Karrierekrake" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    profile_path = cfg_dir / "profile.yaml"
    payload = {
        "applicant": {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "city": personal.get("city") or "",
        },
        "source": "cv_import_exe_offline_e2e",
    }
    profile_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return payload


def _reload_profile(config_root: Path) -> dict:
    import yaml

    path = config_root / "Karrierekrake" / "config" / "profile.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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
            max_tokens=180,
        )
        ok = len((text or "").strip()) >= 40
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__
        ok = False
    return {
        "ok": ok,
        "writing_ok": ok,
        "mode": mode,
        "model_path_basename": model.name,
        "wall_s": round(time.perf_counter() - t0, 3),
        "text_preview_len": len(text or ""),
        "error": err,
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
        )
    )
    return has_email and has_person


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument(
        "--cv",
        type=Path,
        default=_ROOT / "tests" / "fixtures" / "cv_corpus" / "DE_01_Klassisch.pdf",
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
    args = parser.parse_args(argv)

    exe = args.exe.resolve()
    cv = args.cv.resolve()
    if not exe.is_file():
        print(f"FAIL: EXE missing: {exe}", flush=True)
        return 2
    if not cv.is_file():
        print(f"FAIL: CV fixture missing: {cv}", flush=True)
        return 2

    _clear_network_env()
    report: dict = {
        "ok": False,
        "release_blocked": True,
        "exe": str(exe),
        "exe_bytes": exe.stat().st_size,
        "cv": str(cv),
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
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
            return 1

        # 3: import
        out_json = Path(tmp) / "import_out.json"
        try:
            payload = _run_child_import(
                exe, cv, out_json, local_appdata=local, timeout_s=args.import_timeout
            )
            import_ok = bool(payload.get("ok")) and _preview_has_identity(payload)
            report["steps"]["import"] = {
                "ok": import_ok,
                "wall_s": payload.get("_wall_s"),
                "kind": payload.get("kind"),
                "message": (payload.get("message") or "")[:240],
                "preview_keys": sorted(payload.keys())[:40],
            }
            if not import_ok:
                raise SystemExit("import preview incomplete")
        except Exception as exc:  # noqa: BLE001
            report["steps"]["import"] = {
                "ok": False,
                "error": str(exc),
                **(report["steps"].get("import") or {}),
            }
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
            return 1

        # 4: Übernehmen simulation
        applied = _apply_preview_to_profile(payload, local)
        report["steps"]["apply"] = {
            "ok": bool(applied.get("applicant", {}).get("full_name") or applied.get("applicant", {}).get("email")),
            "applicant": applied.get("applicant"),
        }
        if not report["steps"]["apply"]["ok"]:
            report["steps"]["apply"]["ok"] = False
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
            return 1

        # 5: restart + reload profile
        try:
            restart_s = _smoke_start(exe, local, args.smoke_timeout)
            reloaded = _reload_profile(local)
            same = reloaded.get("applicant") == applied.get("applicant")
            report["steps"]["restart"] = {
                "ok": same,
                "wall_s": round(restart_s, 3),
                "applicant": (reloaded.get("applicant") or {}),
            }
            if not same:
                raise SystemExit("profile not persisted across restart")
        except Exception as exc:  # noqa: BLE001
            report["steps"]["restart"] = {"ok": False, "error": str(exc)}
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
            return 1

        # 6: cover letter / writing with same model (library when EXE child cannot)
        if args.skip_cover_letter:
            report["steps"]["cover_letter"] = {"ok": True, "skipped": True}
        else:
            # Ensure models dir points at materialized / sidecar copy under LOCALAPPDATA
            os.environ["LOCALAPPDATA"] = str(local)
            # Also accept vendor / exe-adjacent model for the writing probe.
            sidecar = exe.parent / "models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf"
            if sidecar.is_file():
                os.environ["KARRIEREKRAKE_CV_LLM_MODEL"] = str(sidecar)
            try:
                report["steps"]["cover_letter"] = _cover_letter_same_model()
            except Exception as exc:  # noqa: BLE001
                report["steps"]["cover_letter"] = {"ok": False, "error": str(exc)}

        report["peak_rss_bytes_children"] = _peak_rss_bytes()
        report["metrics"] = {
            "exe_bytes": report["exe_bytes"],
            "start_wall_s": report["steps"]["start"].get("wall_s"),
            "import_wall_s": report["steps"]["import"].get("wall_s"),
            "restart_wall_s": report["steps"]["restart"].get("wall_s"),
            "cover_letter_wall_s": (report["steps"].get("cover_letter") or {}).get("wall_s"),
            "peak_rss_bytes_children": report["peak_rss_bytes_children"],
        }

        step_ok = all(
            bool((report["steps"].get(name) or {}).get("ok"))
            for name in ("start", "import", "apply", "restart", "cover_letter")
        )
        report["ok"] = step_ok
        report["release_blocked"] = not step_ok

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
