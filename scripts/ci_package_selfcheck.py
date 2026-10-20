"""Run ``--package-selfcheck`` in the actual built package with an isolated profile.

Usage: python scripts/ci_package_selfcheck.py --exe <built executable> --checks a,b --out report.json
Failures are printed as GitHub annotations (public on the check run; job logs need a login).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(exe: Path, checks: str, out: Path, timeout: int) -> dict:
    exe = exe.resolve(strict=True)
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kk-selfcheck-") as folder:
        root = Path(folder)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("KARRIEREKRAKE_", "QT_"))}
        env.update(KARRIEREKRAKE_DATA_DIR=str(root / "data"), KARRIEREKRAKE_MODELS_DIR=str(root / "models"),
                   QT_QPA_PLATFORM="offscreen", PYINSTALLER_RESET_ENVIRONMENT="1")
        if sys.platform == "win32":
            env["LOCALAPPDATA"] = str(root / "localappdata")
        completed = subprocess.run([str(exe), "--package-selfcheck", "--out", str(out), "--checks", checks],
                                   env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=timeout, check=False)
    print(completed.stdout[-20000:], flush=True)
    print(completed.stderr[-20000:], file=sys.stderr, flush=True)
    if not out.is_file():
        _annotate(f"package selfcheck wrote no report (exit {completed.returncode}): {completed.stderr[-800:]}")
        raise SystemExit(1)
    report = json.loads(out.read_text(encoding="utf-8"))
    for name, result in report["checks"].items():
        if result.get("ok") is not True:
            _annotate(f"{name}: {json.dumps(result, ensure_ascii=False)[:3000]}")
    if not report.get("frozen"):
        _annotate("package selfcheck did not run frozen")
        raise SystemExit(1)
    return report


def _annotate(message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::error title=Package selfcheck::" + message.replace("%", "%25").replace("\r", "").replace("\n", "%0A"),
              flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--checks", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)
    report = run(args.exe, args.checks, args.out, args.timeout)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
