"""T03.04: install a previous Windows package with a profile, install the new one over it.

The previous package is the release zip of the last successful Windows Smoke run with
an older run id (scripts/native_upgrade_baseline.py --workflow windows-smoke.yml).
The old EXE creates the profile (config, database) in an isolated LOCALAPPDATA; a
case row and the config files are recorded; the new EXE replaces the old one in the
same install folder (the documented zip install) and must start on the same profile,
keep the recorded data and leave the database on the current schema.

Usage: python scripts/ci_windows_upgrade.py --old-zip <dir or zip> --new-exe dist/Karrierekrake/Karrierekrake.exe --out report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

CASE_ID = "kk-upgrade-probe-case"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _old_zip(source: Path) -> Path:
    if source.is_file():
        return source
    matches = sorted(source.rglob("Karrierekrake-Windows.zip"))
    if len(matches) != 1:
        raise FileNotFoundError(f"windows_upgrade_old_zip_not_found:{len(matches)}")
    return matches[0]


def _stop_all() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "Karrierekrake.exe", "/T"], capture_output=True, check=False)
    time.sleep(0.5)


def _smoke(exe: Path, local_appdata: Path, timeout: int = 240) -> str:
    """Run the windowed onefile smoke and wait for its tokenized marker (exit codes are unreliable)."""
    _stop_all()
    marker = local_appdata / "Karrierekrake" / "smoke_test_result.txt"
    marker.unlink(missing_ok=True)
    token = uuid.uuid4().hex
    env = dict(os.environ, LOCALAPPDATA=str(local_appdata), KARRIEREKRAKE_SMOKE_TEST="1",
               KARRIEREKRAKE_SMOKE_TOKEN=token, QT_QPA_PLATFORM="offscreen")
    for key in [k for k in env if k.startswith("KARRIEREKRAKE_") and k not in {"KARRIEREKRAKE_SMOKE_TEST", "KARRIEREKRAKE_SMOKE_TOKEN"}]:
        env.pop(key)
    subprocess.Popen([str(exe)], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            time.sleep(0.5)
            text = marker.read_text(encoding="utf-8", errors="replace") if marker.is_file() else ""
            if f"token={token}" not in text:
                continue
            if "FAIL:" in text:
                raise RuntimeError("windows_upgrade_smoke_failed:" + text[-500:])
            if "SMOKE_TEST_OK" in text:
                return text
        raise TimeoutError("windows_upgrade_smoke_timeout")
    finally:
        _stop_all()


def _db_path(marker_text: str) -> Path:
    line = next((ln for ln in marker_text.splitlines() if ln.startswith("db=")), "")
    if not line:
        raise ValueError("windows_upgrade_db_line_missing")
    return Path(line[3:].strip())


def run(old: Path, new_exe: Path) -> dict:
    report: dict = {"ok": False}
    with tempfile.TemporaryDirectory(prefix="kk-win-upgrade-") as folder:
        root = Path(folder)
        install, appdata = root / "install", root / "localappdata"
        install.mkdir()
        appdata.mkdir()
        with zipfile.ZipFile(_old_zip(old)) as archive:
            archive.extractall(install)
        exe = install / "Karrierekrake.exe"
        report["old_exe_sha256"] = _sha256(exe)
        old_text = _smoke(exe, appdata)
        db = _db_path(old_text)
        report["profile_db"] = str(db.relative_to(appdata)) if db.is_relative_to(appdata) else "outside_localappdata"
        if not db.is_relative_to(appdata) or not db.is_file():
            raise RuntimeError("windows_upgrade_profile_not_isolated")
        now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        with sqlite3.connect(db) as conn:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(application_cases)")]
            values = {"id": CASE_ID, "company": "Upgrade-Probe GmbH", "position": "Profilerhalt", "status": "applied",
                      "created_at": now, "updated_at": now}
            used = {k: v for k, v in values.items() if k in columns}
            conn.execute(f"INSERT INTO application_cases ({', '.join(used)}) VALUES ({', '.join('?' for _ in used)})",
                         list(used.values()))
        conn.close()
        config_dir = db.parent.parent / "config"
        configs = {p.name: _sha256(p) for p in sorted(config_dir.glob("*")) if p.is_file()} if config_dir.is_dir() else {}
        report["old_config_files"] = sorted(configs)

        # Documented zip install: the new program folder replaces the old EXE (and a previous _internal).
        shutil.rmtree(install / "_internal", ignore_errors=True)
        shutil.copytree(new_exe.parent / "_internal", install / "_internal")
        shutil.copy2(new_exe, exe)
        report["new_exe_sha256"] = _sha256(exe)
        new_text = _smoke(exe, appdata)
        with sqlite3.connect(_db_path(new_text)) as conn:
            kept = conn.execute("SELECT company FROM application_cases WHERE id = ?", (CASE_ID,)).fetchone()
            job_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        conn.close()
        changed = sorted(name for name, digest in configs.items()
                         if not (config_dir / name).is_file() or _sha256(config_dir / name) != digest)
        report.update(
            same_profile=_db_path(new_text) == db,
            case_preserved=bool(kept and kept[0] == "Upgrade-Probe GmbH"),
            config_files_missing_or_rewritten=changed,
            schema_current="run_id" in job_columns,
            exe_replaced=report["old_exe_sha256"] != report["new_exe_sha256"],
        )
    report["ok"] = all(report[k] for k in ("same_profile", "case_preserved", "schema_current", "exe_replaced"))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--old-zip", type=Path, required=True)
    parser.add_argument("--new-exe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.old_zip, args.new_exe.resolve(strict=True))
    except Exception as exc:  # noqa: BLE001 - reported, then failed
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:800]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)
    if not report["ok"] and os.environ.get("GITHUB_ACTIONS") == "true":
        print("::error title=Windows upgrade::" + json.dumps(report)[:3000].replace("%", "%25"), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
