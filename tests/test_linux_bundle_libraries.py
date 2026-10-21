"""T06.05.04.03: the Linux bundle ships no GTK theme stack and loads libexpat from the host."""
from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

import pytest

from scripts.linux_bundle_libraries import (
    EXCLUDED_QT_PLUGINS,
    FORBIDDEN_IN_BUNDLE,
    check_bundle,
    elf_needed,
    elf_symbols,
    prune_linux_binaries,
)

ROOT = Path(__file__).resolve().parents[1]
GTK_PLUGIN, GLIB_NETWORK_PLUGIN = EXCLUDED_QT_PLUGINS


def _elf64(needed: list[str]) -> bytes:
    """Minimal little-endian ELF64 with PT_LOAD, PT_DYNAMIC, DT_NEEDED and DT_STRTAB."""
    vaddr, phoff, phnum = 0x400000, 64, 2
    strtab = b"\0"
    offsets = []
    for name in needed:
        offsets.append(len(strtab))
        strtab += name.encode() + b"\0"
    str_off = phoff + 56 * phnum
    dyn_off = (str_off + len(strtab) + 7) & ~7
    dynamic = b"".join(struct.pack("<qQ", 1, value) for value in offsets)
    dynamic += struct.pack("<qQ", 5, vaddr + str_off) + struct.pack("<qQ", 0, 0)
    size = dyn_off + len(dynamic)
    header = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header += struct.pack("<HHIQQQIHHHHHH", 3, 62, 1, 0, phoff, 0, 0, 64, 56, phnum, 0, 0, 0)
    load = struct.pack("<IIQQQQQQ", 1, 5, 0, vaddr, vaddr, size, size, 0x1000)
    dyn = struct.pack("<IIQQQQQQ", 2, 6, dyn_off, vaddr + dyn_off, vaddr + dyn_off, len(dynamic), len(dynamic), 8)
    body = header + load + dyn + strtab
    return body + bytes(dyn_off - len(body)) + dynamic


def test_elf_needed_reads_dt_needed_through_the_load_segment(tmp_path: Path) -> None:
    path = tmp_path / "lib.so"
    path.write_bytes(_elf64(["libgtk-3.so.0", "libc.so.6"]))
    assert elf_needed(path) == ["libgtk-3.so.0", "libc.so.6"]


def test_non_elf_has_no_dependencies(tmp_path: Path) -> None:
    path = tmp_path / "script"
    path.write_text("#!/bin/sh\n")
    assert elf_needed(path) == []


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="real ELF only on Linux")
def test_elf_needed_on_a_real_system_binary() -> None:
    assert "libc.so.6" in elf_needed(shutil.which("ls"))


NEEDED = {
    "qt/libqxcb.so": ["libQt6Gui.so.6", "libX11.so.6", "libfontconfig.so.1", "libglib-2.0.so.0"],
    "qt/libqgtk3.so": ["libQt6Gui.so.6", "libgtk-3.so.0", "libX11.so.6"],
    "qt/libqglib.so": ["libQt6Network.so.6", "libgio-2.0.so.0", "libglib-2.0.so.0"],
    "sys/libgtk-3.so.0": ["libgdk-3.so.0", "libXi.so.6", "libgio-2.0.so.0", "libX11.so.6"],
    "sys/libgdk-3.so.0": ["libXi.so.6", "libXrender.so.1"],
    "sys/libfontconfig.so.1": ["libexpat.so.1", "libfreetype.so.6"],
}


def _toc() -> list[tuple[str, str, str]]:
    return [
        ("PySide6/Qt/plugins/platforms/libqxcb.so", "qt/libqxcb.so", "BINARY"),
        (GTK_PLUGIN, "qt/libqgtk3.so", "BINARY"),
        (GLIB_NETWORK_PLUGIN, "qt/libqglib.so", "BINARY"),
        ("libglib-2.0.so.0", "sys/libglib-2.0.so.0", "BINARY"),
        ("libpython3.12.so.1.0", "sys/libpython", "BINARY"),
        ("libgtk-3.so.0", "sys/libgtk-3.so.0", "BINARY"),
        ("libgdk-3.so.0", "sys/libgdk-3.so.0", "BINARY"),
        ("libXi.so.6", "sys/libXi.so.6", "BINARY"),
        ("libXrender.so.1", "sys/libXrender.so.1", "BINARY"),
        ("libgio-2.0.so.0", "sys/libgio-2.0.so.0", "BINARY"),
        ("libX11.so.6", "sys/libX11.so.6", "BINARY"),
        ("libfontconfig.so.1", "sys/libfontconfig.so.1", "BINARY"),
        ("libfreetype.so.6", "sys/libfreetype.so.6", "BINARY"),
        ("libexpat.so.1", "sys/libexpat.so.1", "BINARY"),
        ("libdlopened.so.1", "sys/libdlopened.so.1", "BINARY"),
        ("llama_cpp/lib/libggml.so", "libggml.so.0", "SYMLINK"),
    ]


def test_prune_drops_gtk_theme_its_only_dependencies_and_host_expat() -> None:
    kept, removed = prune_linux_binaries(_toc(), needed_of=lambda src: NEEDED.get(src, []))
    assert removed == sorted([GTK_PLUGIN, GLIB_NETWORK_PLUGIN, "libgtk-3.so.0", "libgdk-3.so.0", "libXi.so.6",
                              "libXrender.so.1", "libgio-2.0.so.0", "libexpat.so.1"])
    names = {item[0] for item in kept}
    # Still needed by the xcb platform plugin, or loaded via dlopen only, or a symlink entry.
    assert {"libX11.so.6", "libfontconfig.so.1", "libglib-2.0.so.0", "libfreetype.so.6", "libdlopened.so.1",
            "libpython3.12.so.1.0", "llama_cpp/lib/libggml.so"} <= names
    assert not names & FORBIDDEN_IN_BUNDLE


def test_prune_keeps_a_library_that_another_root_still_needs() -> None:
    needed = dict(NEEDED, **{"qt/libqxcb.so": NEEDED["qt/libqxcb.so"] + ["libXi.so.6"]})
    _, removed = prune_linux_binaries(_toc(), needed_of=lambda src: needed.get(src, []))
    assert "libXi.so.6" not in removed
    assert "libgtk-3.so.0" in removed


def _bundle(tmp_path: Path, extra: dict[str, list[str]]) -> Path:
    root = tmp_path / "Karrierekrake" / "_internal"
    for rel, needed in {"libfontconfig.so.1": ["libexpat.so.1"], **extra}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(_elf64(needed))
    return root.parent


def test_check_bundle_accepts_expat_from_the_host(tmp_path: Path) -> None:
    root = _bundle(tmp_path, {})
    report = check_bundle(root, ldd=lambda path, _root: {"libexpat.so.1": "/lib/x86_64-linux-gnu/libexpat.so.1"})
    assert report["ok"], report
    assert report["host_references"] == {"_internal/libfontconfig.so.1": {"libexpat.so.1": "/lib/x86_64-linux-gnu/libexpat.so.1"}}


@pytest.mark.parametrize("name", sorted(FORBIDDEN_IN_BUNDLE))
def test_check_bundle_rejects_every_forbidden_library(tmp_path: Path, name: str) -> None:
    rel = "PySide6/Qt/plugins/platformthemes/" + name if name.endswith(".so") else name
    root = _bundle(tmp_path, {rel: []})
    report = check_bundle(root, ldd=lambda path, _root: {"libexpat.so.1": "/usr/lib/libexpat.so.1"})
    assert not report["ok"]
    assert report["forbidden_shipped"] == ["_internal/" + rel]


def test_check_bundle_rejects_missing_or_bundled_resolution(tmp_path: Path) -> None:
    root = _bundle(tmp_path, {})
    missing = check_bundle(root, ldd=lambda path, _root: {"libexpat.so.1": None})
    assert missing["problems"] == ["_internal/libfontconfig.so.1: libexpat.so.1 not found on host"]
    inside = str(root / "_internal" / "elsewhere" / "libexpat.so.1")
    bundled = check_bundle(root, ldd=lambda path, _root: {"libexpat.so.1": inside})
    assert not bundled["ok"] and "resolves inside the bundle" in bundled["problems"][0]


def test_spec_prunes_linux_binaries_before_the_release_inventory() -> None:
    spec = (ROOT / "packaging" / "Karrierekrake.spec").read_text(encoding="utf-8")
    prune = spec.index("prune_linux_binaries(a.binaries)")
    assert prune < spec.index("export_release_inventory(ROOT")
    assert 'sys.platform.startswith("linux")' in spec[spec.rindex("\n\n", 0, prune):prune]


def test_linux_ci_gates_the_bundle_and_starts_on_x11() -> None:
    workflow = (ROOT / ".github" / "workflows" / "desktop-platforms.yml").read_text(encoding="utf-8")
    assert "scripts/linux_bundle_libraries.py --root" in workflow
    assert "xvfb-run -a python scripts/ci_native_gui_startup.py" in workflow and "--platform xcb" in workflow
    assert workflow.index("linux_bundle_libraries.py") < workflow.index("name: Package tested application")


def _elf64_symbols(defined: list[str], undefined: list[str]) -> bytes:
    """ELF64 with a .dynsym/.dynstr section pair (section headers only)."""
    strtab, symbols = b"\0", struct.pack("<IBBHQQ", 0, 0, 0, 0, 0, 0)
    for name, shndx in [(n, 7) for n in defined] + [(n, 0) for n in undefined]:
        symbols += struct.pack("<IBBHQQ", len(strtab), 0x12, 0, shndx, 0, 0)
        strtab += name.encode() + b"\0"
    sym_off = 64
    str_off = sym_off + len(symbols)
    shoff = (str_off + len(strtab) + 7) & ~7
    header = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header += struct.pack("<HHIQQQIHHHHHH", 3, 62, 1, 0, 0, shoff, 0, 64, 56, 0, 64, 3, 0)
    null = bytes(64)
    dynsym = struct.pack("<IIQQQQIIQQ", 0, 11, 0, 0, sym_off, len(symbols), 2, 1, 8, 24)
    dynstr = struct.pack("<IIQQQQIIQQ", 0, 3, 0, 0, str_off, len(strtab), 0, 0, 1, 0)
    body = header + symbols + strtab
    return body + bytes(shoff - len(body)) + null + dynsym + dynstr


def test_elf_symbols_splits_defined_and_imported(tmp_path: Path) -> None:
    path = tmp_path / "lib.so"
    path.write_bytes(_elf64_symbols(["g_regex_new"], ["pcre_exec", "malloc"]))
    assert elf_symbols(path) == ({"g_regex_new"}, {"pcre_exec", "malloc"})


@pytest.mark.parametrize(("rel", "defined", "undefined", "problem"), [
    ("PySide6/Qt/lib/libQt6Core.so.6", [], ["g_regex_new"], "imports g_regex_new"),
    ("libfoo.so", [], ["pcre_exec"], "imports pcre_exec"),
    ("libggml.so", ["_ZN10__gnu_pbds6detail11binary_heapIiE8erase_ifE"], [], "contains symbol"),
])
def test_check_bundle_rejects_regex_imports_and_pbds(tmp_path, rel, defined, undefined, problem) -> None:
    root = _bundle(tmp_path, {})
    target = root / "_internal" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_elf64_symbols(defined, undefined))
    report = check_bundle(root, ldd=lambda path, _root: {"libexpat.so.1": "/usr/lib/libexpat.so.1"})
    assert not report["ok"]
    assert any(problem in line for line in report["problems"]), report["problems"]


def test_check_bundle_lets_providers_import_pcre_and_reports_aligned_new(tmp_path: Path) -> None:
    root = _bundle(tmp_path, {})
    (root / "_internal" / "libglib-2.0.so.0").write_bytes(_elf64_symbols(["g_regex_new"], ["pcre_exec"]))
    (root / "_internal" / "libggml.so").write_bytes(_elf64_symbols([], ["_ZnwmSt11align_val_t"]))
    report = check_bundle(root, ldd=lambda path, _root: {"libexpat.so.1": "/usr/lib/libexpat.so.1"})
    assert report["ok"], report["problems"]
    assert report["reported_imports"] == {"_ZnwmSt11align_val_t": ["_internal/libggml.so"]}


def test_readline_is_excluded_from_the_analysis() -> None:
    sys.path.insert(0, str(ROOT / "packaging"))
    import kk_content_policy

    assert "readline" in kk_content_policy.ANALYSIS_EXCLUDES
