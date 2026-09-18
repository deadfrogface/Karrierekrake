#!/usr/bin/env python3
"""Generate a deterministic content_manifest.json for a release artifact.

The manifest lists normalized TOC / dist paths, policy version, and optional
SHA256 of the EXE. Used by CI for gate + diff visibility.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_policy():
    path = ROOT / "packaging" / "kk_content_policy.py"
    spec = importlib.util.spec_from_file_location("kk_content_policy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["kk_content_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


policy = _load_policy()


def git_sha() -> str:
    env = os.environ.get("GITHUB_SHA") or os.environ.get("COMMIT_SHA")
    if env:
        return env.strip()
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    out: Path,
    *,
    paths: list[str],
    hits: list | None = None,
    exe: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = sorted({p.replace("\\", "/") for p in paths})
    payload: dict[str, Any] = {
        "policy_version": policy.POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha(),
        "entry_count": len(normalized),
        "entries": [{"path": p} for p in normalized],
        "allowlist": {
            "datas": [{"src": s, "dest": d} for s, d in policy.ALLOWED_DATAS],
            "first_party_prefixes": list(policy.ALLOWED_FIRST_PARTY_PREFIXES),
            "excluded_modules": list(policy.EXCLUDED_FIRST_PARTY_MODULES),
            "collect_all_packages": list(policy.ALLOWED_COLLECT_ALL_PACKAGES),
        },
        "forbidden_path_markers": list(policy.FORBIDDEN_PATH_MARKERS),
        "gate": {
            "passed": not bool(hits),
            "hit_count": len(hits or []),
            "hits": [
                {"kind": h.kind, "path": h.path, "detail": h.detail} for h in (hits or [])
            ],
        },
    }
    if exe is not None and exe.is_file():
        payload["artifact"] = {
            "name": exe.name,
            "size": exe.stat().st_size,
            "sha256": sha256_file(exe),
        }
    if extra:
        payload.update(extra)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return payload


def dump_analysis_toc(out_json: Path) -> list[str]:
    """Run PyInstaller Analysis (same inputs as the spec) and dump TOC paths."""
    from PyInstaller.building.build_main import Analysis
    from PyInstaller.config import CONF
    from PyInstaller.utils.hooks import collect_all, collect_submodules

    root = str(ROOT)
    work = ROOT / "build" / "content_manifest_analysis" / "Karrierekrake"
    dist = ROOT / "dist"
    work.mkdir(parents=True, exist_ok=True)
    dist.mkdir(parents=True, exist_ok=True)
    spec_file = ROOT / "packaging" / "Karrierekrake.spec"
    CONF["spec"] = str(spec_file)
    CONF["specpath"] = str(spec_file.parent)
    CONF["specnm"] = "Karrierekrake"
    CONF["workpath"] = str(work)
    CONF["distpath"] = str(dist)
    CONF["warnfile"] = str(work / "warn-Karrierekrake.txt")
    CONF["dot-file"] = str(work / "graph-Karrierekrake.dot")
    CONF["xref-file"] = str(work / "xref-Karrierekrake.html")
    CONF["code_cache"] = {}
    CONF.setdefault("hiddenimports", [])
    CONF.setdefault("pathex", [])

    hidden = (
        collect_submodules("search")
        + collect_submodules("apply")
        + collect_submodules("core")
        + collect_submodules("desktop")
        + collect_submodules("guenther")
        + collect_submodules("integrations")
    )
    hidden = policy.filter_hiddenimports(hidden)
    datas = policy.build_repo_datas(root)
    binaries: list = []
    for pkg in policy.ALLOWED_COLLECT_ALL_PACKAGES:
        try:
            pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
            datas += policy.filter_collect_all_datas(pkg_datas)
            binaries += policy.filter_collect_all_binaries(pkg_binaries)
            hidden += policy.filter_hiddenimports(pkg_hidden)
        except Exception:
            pass
    hidden = policy.filter_hiddenimports(
        list(dict.fromkeys(hidden + list(policy.ALLOWED_THIRD_PARTY_HIDDEN)))
    )

    a = Analysis(
        [str(ROOT / "desktop" / "app.py")],
        pathex=[root],
        binaries=binaries,
        datas=datas,
        hiddenimports=hidden,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=list(policy.ANALYSIS_EXCLUDES),
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=None,
        noarchive=False,
    )
    paths: list[str] = []
    for collection in (a.datas, a.binaries, a.pure, a.scripts):
        for item in collection:
            if isinstance(item, (tuple, list)) and item:
                paths.append(str(item[0]))
            else:
                paths.append(str(item))
    hits = policy.scan_paths(paths)
    for item in a.pure:
        name = str(item[0]) if isinstance(item, (tuple, list)) and item else str(item)
        if (
            name == "desktop.demo_data"
            or name.startswith("desktop.demo_data.")
            or name == "benchmark"
            or name.startswith("benchmark.")
            or name.startswith("tools.cover_opt")
        ):
            hits.append(
                policy.PolicyHit(
                    kind="excluded_module",
                    path=name,
                    detail="dev module must not appear in Analysis pure",
                )
            )
    write_manifest(
        out_json,
        paths=paths,
        hits=hits,
        extra={"source": "pyinstaller_analysis"},
    )
    if hits:
        raise SystemExit(
            "Analysis content gate FAILED:\n"
            + "\n".join(f" - [{h.kind}] {h.path}: {h.detail}" for h in hits)
        )
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / "content_manifest.json",
        help="Output manifest path",
    )
    parser.add_argument(
        "--from-analysis",
        action="store_true",
        help="Build TOC via PyInstaller Analysis (pre-EXE gate)",
    )
    parser.add_argument("--exe", type=Path, help="Optional EXE to hash + TOC-scan")
    parser.add_argument("--toc-json", type=Path, help="Existing TOC list JSON")
    args = parser.parse_args()

    if args.from_analysis:
        paths = dump_analysis_toc(args.out)
        print(f"Wrote analysis manifest ({len(paths)} entries) → {args.out}")
        return 0

    paths: list[str] = []
    if args.toc_json and args.toc_json.is_file():
        data = json.loads(args.toc_json.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "entries" in data:
            paths = [e["path"] if isinstance(e, dict) else str(e) for e in data["entries"]]
        else:
            paths = [str(x) for x in data]
    if args.exe and args.exe.is_file():
        scan_path = ROOT / "scripts" / "scan_release_artifact.py"
        scan_spec = importlib.util.spec_from_file_location("kk_scan", scan_path)
        scan = importlib.util.module_from_spec(scan_spec)
        assert scan_spec.loader is not None
        scan_spec.loader.exec_module(scan)
        paths.extend(scan.list_toc_from_exe(args.exe))

    write_manifest(args.out, paths=paths, exe=args.exe)
    print(f"Wrote content manifest ({len(paths)} entries) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
