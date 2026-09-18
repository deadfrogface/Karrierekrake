# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Karrierekrake desktop app (onefile, no bundled Chromium).

Chromium is installed at runtime into %%LOCALAPPDATA%%\\Karrierekrake\\browsers
via desktop.services.browser_install â€” never shipped inside the EXE.
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden = (
    collect_submodules("search")
    + collect_submodules("apply")
    + collect_submodules("core")
    + collect_submodules("desktop")
    + collect_submodules("guenther")
    + collect_submodules("integrations")
)

datas = [
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "config", "profile.yaml.example"), "config"),
    (os.path.join(ROOT, "config", "application_profile.yaml.example"), "config"),
    (os.path.join(ROOT, "config", "settings.yaml.example"), "config"),
    (os.path.join(ROOT, "assets", "brand"), os.path.join("assets", "brand")),
    (os.path.join(ROOT, "NOTICE"), "."),
    (os.path.join(ROOT, "LICENSE"), "."),
]
_ICON = os.path.join(ROOT, "assets", "brand", "app.ico")
if not os.path.isfile(_ICON):
    _ICON = None
binaries = []
# python-jobspy -> tls_client ships Windows DLLs under dependencies/
# Do NOT collect Playwright browser binaries â€” only the Python driver package.
for pkg in ("tls_client", "jobspy", "playwright"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        # Drop any ms-playwright browser trees accidentally pulled in
        pkg_datas = [
            d for d in pkg_datas
            if "ms-playwright" not in str(d[0]).replace("\\", "/").lower()
            and "chromium" not in str(d[0]).replace("\\", "/").lower()
        ]
        datas += pkg_datas
        binaries += pkg_binaries
        hidden += pkg_hidden
    except Exception:
        pass

hidden += [
    "app.main",
    "browser.browser_manager",
    "playwright",
    "yaml",
    "PySide6",
    "tls_client",
    "tls_client.cffi",
    "tls_client.dependencies",
    "jobspy",
    "numpy",
    "pandas",
    "lxml",
    "bs4",
]

a = Analysis(
    [os.path.join(ROOT, "desktop", "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

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


