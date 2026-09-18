# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Karrierekrake desktop app (onefile, no bundled Chromium).

Chromium is installed at runtime into %%LOCALAPPDATA%%\\Karrierekrake\\browsers
via desktop.services.browser_install — never shipped inside the EXE.

Production content policy (allowlist-first): packaging/kk_content_policy.py
"""

import importlib.util
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def _load_policy():
    path = os.path.join(SPECPATH, "kk_content_policy.py")
    spec = importlib.util.spec_from_file_location("kk_content_policy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["kk_content_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


policy = _load_policy()

hidden = (
    collect_submodules("search")
    + collect_submodules("apply")
    + collect_submodules("core")
    + collect_submodules("desktop")
    + collect_submodules("guenther")
    + collect_submodules("integrations")
)
hidden = policy.filter_hiddenimports(hidden)

datas = policy.build_repo_datas(ROOT)
_ICON = os.path.join(ROOT, "assets", "brand", "app.ico")
if not os.path.isfile(_ICON):
    _ICON = None
binaries = []

# Narrow collect_all: only allowlisted packages, then filter forbidden trees.
# Do NOT collect Playwright browser binaries — only the Python driver package.
for pkg in policy.ALLOWED_COLLECT_ALL_PACKAGES:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += policy.filter_collect_all_datas(pkg_datas)
        binaries += policy.filter_collect_all_binaries(pkg_binaries)
        hidden += policy.filter_hiddenimports(pkg_hidden)
    except Exception:
        pass

hidden += list(policy.ALLOWED_THIRD_PARTY_HIDDEN)
hidden = policy.filter_hiddenimports(list(dict.fromkeys(hidden)))

# Fail the build early if any explicit datas source is outside the allowlist
# (third-party site-packages datas are filtered separately).
for src, dest in list(datas):
    src_s = str(src)
    if "site-packages" in src_s.replace("\\", "/") or "dist-packages" in src_s.replace("\\", "/"):
        continue
    if not policy.datas_entry_allowed(src_s, str(dest)):
        raise SystemExit(
            f"Production content policy: datas not on allowlist: {src_s!r} -> {dest!r}"
        )

a = Analysis(
    [os.path.join(ROOT, "desktop", "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(policy.ANALYSIS_EXCLUDES),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Post-Analysis path gate (datas + binaries TOC names)
_toc_paths = []
for collection in (a.datas, a.binaries):
    for item in collection:
        if isinstance(item, (tuple, list)) and item:
            _toc_paths.append(str(item[0]))
            if len(item) > 1:
                _toc_paths.append(str(item[1]))
_hits = policy.scan_paths(_toc_paths)
# Also ensure demo_data / benchmark never appear in pure modules
for item in a.pure:
    name = str(item[0]) if isinstance(item, (tuple, list)) and item else str(item)
    _toc_paths.append(name)
    if name == "desktop.demo_data" or name.startswith("desktop.demo_data."):
        _hits.append(
            policy.PolicyHit(
                kind="excluded_module",
                path=name,
                detail="desktop.demo_data must not ship in production",
            )
        )
    if name == "benchmark" or name.startswith("benchmark.") or name.startswith("tools.cover_opt"):
        _hits.append(
            policy.PolicyHit(
                kind="excluded_module",
                path=name,
                detail="dev/benchmark tooling must not ship",
            )
        )
_hits += policy.scan_paths(_toc_paths)
if _hits:
    for h in _hits:
        sys.stderr.write(f"CONTENT POLICY VIOLATION: [{h.kind}] {h.path}: {h.detail}\n")
    raise SystemExit("Production content policy failed — refusing to build unclean EXE")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Karrierekrake",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Production GUI app: NEVER attach a Windows console.
    # CI smoke uses SMOKE_TEST_OK file markers (exit codes may be null for windowed EXEs).
    # Opt-in console only via KARRIEREKRAKE_FORCE_CONSOLE=1/true/yes for local debugging.
    console=(os.environ.get("KARRIEREKRAKE_FORCE_CONSOLE", "").strip().lower() in {"1", "true", "yes"}),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)
