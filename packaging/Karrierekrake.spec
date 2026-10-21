# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Karrierekrake desktop app (onedir on every platform, no bundled Chromium).

Onedir keeps Qt (LGPL-3.0) and the other libraries as separate files next to the program, so a user can replace
them with an interface-compatible build (LGPL-3.0 section 4 d 1); see docs/legal/LIZENZENTSCHEIDUNGEN_PR144.md.

Chromium is installed at runtime into %%LOCALAPPDATA%%\\Karrierekrake\\browsers
via desktop.services.browser_install — never shipped inside the EXE.

Production content policy (allowlist-first): packaging/kk_content_policy.py
"""

import importlib.util
import os
import sys
import sysconfig

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from core.release_identity import VERSION


def _load_policy():
    path = os.path.join(SPECPATH, "kk_content_policy.py")
    spec = importlib.util.spec_from_file_location("kk_content_policy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["kk_content_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


policy = _load_policy()

# Fail release builds early when the offline CV model must ship in the EXE.
_bundled_model = policy.require_bundled_cv_model(ROOT)
if _bundled_model:
    sys.stderr.write(f"Bundled CV model OK: {_bundled_model}\n")

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
_ICON = (os.path.join(ROOT, "assets", "brand", "app.ico") if sys.platform == "win32"
         else os.path.join(SPECPATH, "native-app.icns") if sys.platform == "darwin" else None)
if _ICON is not None and not os.path.isfile(_ICON):
    _ICON = None
binaries = []

# Narrow collect_all: only allowlisted packages, then filter forbidden trees.
# Do NOT collect Playwright browser binaries — only the Python driver package.
# llama_cpp is allowlisted so libllama / ggml native libs ship in the EXE.
for pkg in policy.ALLOWED_COLLECT_ALL_PACKAGES:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += policy.filter_collect_all_datas(pkg_datas)
        binaries += policy.filter_collect_all_binaries(pkg_binaries)
        hidden += policy.filter_hiddenimports(pkg_hidden)
    except Exception:
        pass

# llama-cpp loads ggml/llama by path (llama_cpp/lib), not by import.
# --report-llm-load in build-and-exe-smoke needs those DLLs in the EXE.
try:
    binaries += policy.filter_collect_all_binaries(collect_dynamic_libs("llama_cpp"))
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
    runtime_hooks=[os.path.join(SPECPATH, "runtime_security.py")],
    excludes=list(policy.ANALYSIS_EXCLUDES),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Keep a complete OpenSSL 3 pair. Removing these breaks stdlib _ssl;
# mixing Python's libssl with Homebrew's libcrypto breaks native wheels.
if sys.platform == "win32":
    from scripts.windows_runtime_collection import coherent_windows_runtime
    a.binaries = type(a.binaries)(coherent_windows_runtime(a.binaries, sys.base_prefix))
    # The llama/ggml DLLs import Microsoft's OpenMP runtime; ship it next to the other runtime DLLs.
    from scripts.windows_runtime_collection import find_openmp_runtime
    if not any(str(row[0]).replace("\\", "/").rsplit("/", 1)[-1].casefold() == "vcomp140.dll" for row in a.binaries):
        a.binaries = type(a.binaries)(list(a.binaries) + [("vcomp140.dll", find_openmp_runtime(), "BINARY")])

if sys.platform == "darwin":
    from scripts.macos_openssl import coherent_openssl
    a.binaries = type(a.binaries)(coherent_openssl(a.binaries, secure_only=True,
        static_runtime=os.path.join(sys.base_prefix, "lib", sysconfig.get_config_var("LDLIBRARY") or ""),
        extra_dirs=(
        os.path.join(sys.base_prefix, "lib"),
        "/opt/homebrew/opt/openssl@3/lib", "/usr/local/opt/openssl@3/lib",
    )))

# Linux: no GTK3 theme (GTK/GDK/GIO/libXi/libXrender only came with it) and the
# host's libexpat, so distribution security updates apply (scripts/linux_bundle_libraries.py).
if sys.platform.startswith("linux"):
    from scripts.linux_bundle_libraries import prune_linux_binaries
    _kept_binaries, _removed_binaries = prune_linux_binaries(a.binaries)
    a.binaries = type(a.binaries)(_kept_binaries)
    sys.stderr.write("Linux bundle removed: " + ", ".join(_removed_binaries) + "\n")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::notice title=Linux bundle removed::" + ", ".join(_removed_binaries))

# Hooks may add all Google service schemas; keep the two used offline.
a.datas = type(a.datas)(item for item in a.datas if policy.release_data_allowed(str(item[0])))

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

# Build compliance artifacts from the actual resolved inputs, not the dev environment.
from scripts.export_release_sbom import export_release_inventory
export_release_inventory(ROOT, os.path.join(ROOT, "build", "release-compliance"), a.binaries, a.pure, a.datas, require_python_runtime=True)
# The notices of exactly these inputs (distro copyright files, common licenses, Python
# distribution licenses) ship inside the package too, not only next to it (T08.05.01).
a.datas = type(a.datas)(list(a.datas) + [
    ("THIRD_PARTY_NOTICES.txt", os.path.join(ROOT, "build", "release-compliance", "THIRD_PARTY_NOTICES.txt"), "DATA")])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_NATIVE = True  # onedir everywhere; the name is kept for the branches below
exe = EXE(
    pyz,
    a.scripts,
    *([] if _NATIVE else [a.binaries, a.zipfiles, a.datas]),
    [],
    exclude_binaries=_NATIVE,
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

if _NATIVE:
    collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Karrierekrake")
    if sys.platform == "darwin":
        app = BUNDLE(collection, name="Karrierekrake.app", icon=_ICON,
                     bundle_identifier="com.karrierekrake.desktop",
                     info_plist={"CFBundleDisplayName": "Karrierekrake",
                                 "CFBundleShortVersionString": VERSION.split("-")[0],
                                 "CFBundleVersion": VERSION.split("-")[0],
                                 "NSHighResolutionCapable": True})
