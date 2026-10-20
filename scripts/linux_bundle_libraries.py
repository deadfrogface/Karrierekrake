"""Linux bundle: drop the Qt GTK3 theme and use the host's libexpat.

PyInstaller collects Qt's ``platformthemes/libqgtk3.so`` and with it GTK 3,
GDK, cairo, pango, gdk-pixbuf, GIO, libXi and libXrender from the build host
(Ubuntu 22.04). Ubuntu ships no fix for several of their advisories
(docs/security/NATIVE_LINUX_CANDIDATE_DISPOSITION_2026-10-20.json). Qt's own
widget dialogs replace the GTK file chooser, so the plugin and every library
that only it pulled in are removed. ``libexpat.so.1`` (needed by the bundled
fontconfig) is loaded from the host instead, where distribution security
updates apply; its ABI is stable across expat 2.x.

The build prunes ``a.binaries`` via :func:`prune_linux_binaries`; CI checks the
finished bundle with ``python scripts/linux_bundle_libraries.py --root ...``.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

EXCLUDED_QT_PLUGINS = ("PySide6/Qt/plugins/platformthemes/libqgtk3.so",)
HOST_PROVIDED = frozenset({"libexpat.so.1"})
# Must not exist anywhere in the bundle; a reference to them must resolve on the host.
FORBIDDEN_IN_BUNDLE = frozenset({
    "libqgtk3.so", "libgtk-3.so.0", "libgdk-3.so.0", "libXi.so.6", "libXrender.so.1",
    "libgio-2.0.so.0", "libexpat.so.1",
})

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB = 0, 1, 5


def elf_needed(path: str | os.PathLike) -> list[str]:
    """DT_NEEDED entries of an ELF file, read via its program headers."""
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF":
        return []
    is64 = {1: False, 2: True}[data[4]]
    end = {1: "<", 2: ">"}[data[5]]
    if is64:
        phoff, = struct.unpack_from(end + "Q", data, 0x20)
        phentsize, phnum = struct.unpack_from(end + "HH", data, 0x36)
        ph_fmt, dyn_fmt = end + "IIQQQQQQ", end + "qQ"
    else:
        phoff, = struct.unpack_from(end + "I", data, 0x1C)
        phentsize, phnum = struct.unpack_from(end + "HH", data, 0x2A)
        ph_fmt, dyn_fmt = end + "IIIIIIII", end + "iI"
    loads, dynamic = [], None
    for index in range(phnum):
        fields = struct.unpack_from(ph_fmt, data, phoff + index * phentsize)
        if is64:
            p_type, _flags, offset, vaddr, _paddr, filesz = fields[:6]
        else:
            p_type, offset, vaddr, _paddr, filesz = fields[:5]
        if p_type == PT_LOAD:
            loads.append((vaddr, offset, filesz))
        elif p_type == PT_DYNAMIC:
            dynamic = (offset, filesz)
    if dynamic is None:
        return []
    entries, strtab = [], None
    size = struct.calcsize(dyn_fmt)
    for position in range(dynamic[0], dynamic[0] + dynamic[1] - size + 1, size):
        tag, value = struct.unpack_from(dyn_fmt, data, position)
        if tag == DT_NULL:
            break
        if tag == DT_NEEDED:
            entries.append(value)
        elif tag == DT_STRTAB:
            strtab = value
    if strtab is None:
        raise ValueError(f"elf_without_strtab: {path}")
    base = next((offset + strtab - vaddr for vaddr, offset, filesz in loads
                 if vaddr <= strtab < vaddr + filesz), None)
    if base is None:
        raise ValueError(f"elf_strtab_unmapped: {path}")
    return [data[base + value:data.index(b"\0", base + value)].decode() for value in entries]


def _dest(item) -> str:
    return str(item[0]).replace("\\", "/")


def _closure(roots: Iterable, top_level: dict[str, list], needed_of: Callable) -> set[str]:
    reached: set[str] = set()
    stack = list(roots)
    while stack:
        item = stack.pop()
        if len(item) > 2 and item[2] not in ("BINARY", "EXTENSION"):
            continue  # SYMLINK entries point at another TOC entry, not at a file
        for name in needed_of(str(item[1])):
            for dependency in top_level.get(name, ()):
                if _dest(dependency) not in reached:
                    reached.add(_dest(dependency))
                    stack.append(dependency)
    return reached


def prune_linux_binaries(binaries: list, needed_of: Callable = elf_needed) -> tuple[list, list[str]]:
    """Remove the GTK3 theme, libraries only it needed, and host-provided libraries.

    ``binaries`` are PyInstaller TOC entries ``(dest, src, typecode)``. Package
    files (dest with a directory) and libpython are roots; top-level libraries are
    dependencies. A top-level library is removed only if it was reachable before
    and is not reachable once the plugins are gone, so libraries loaded via
    dlopen (never reachable through DT_NEEDED) stay untouched.
    """
    items = list(binaries)
    top_level: dict[str, list] = {}
    for item in items:
        if "/" not in _dest(item) and not _dest(item).startswith("libpython"):
            top_level.setdefault(_dest(item), []).append(item)
    roots = [item for item in items if "/" in _dest(item) or _dest(item).startswith("libpython")]
    kept_roots = [item for item in roots if _dest(item) not in EXCLUDED_QT_PLUGINS]
    before = _closure(roots, top_level, needed_of)
    after = _closure(kept_roots, top_level, needed_of)
    removed = (set(EXCLUDED_QT_PLUGINS) & {_dest(item) for item in roots}) | (before - after)
    removed |= {_dest(item) for item in items if Path(_dest(item)).name in HOST_PROVIDED}
    return [item for item in items if _dest(item) not in removed], sorted(removed)


def _is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def check_bundle(root: Path, ldd: Callable[[Path, Path], dict[str, str | None]] | None = None) -> dict:
    """Fail if a forbidden library ships or a reference to it resolves into the bundle."""
    root = root.resolve(strict=True)
    files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
    shipped = sorted(str(path.relative_to(root)).replace("\\", "/") for path in files
                     if path.name in FORBIDDEN_IN_BUNDLE)
    references, problems = {}, []
    for path in files:
        if not _is_elf(path):
            continue
        wanted = sorted(set(elf_needed(path)) & FORBIDDEN_IN_BUNDLE)
        if not wanted:
            continue
        resolved = (ldd or _ldd)(path, root)
        rel = str(path.relative_to(root)).replace("\\", "/")
        references[rel] = {name: resolved.get(name) for name in wanted}
        for name in wanted:
            target = resolved.get(name)
            if target is None:
                problems.append(f"{rel}: {name} not found on host")
            elif Path(target).resolve().is_relative_to(root):
                problems.append(f"{rel}: {name} resolves inside the bundle ({target})")
    return {"ok": not shipped and not problems, "root": str(root), "forbidden_shipped": shipped,
            "host_references": references, "problems": problems,
            "forbidden": sorted(FORBIDDEN_IN_BUNDLE)}


def _ldd(path: Path, root: Path) -> dict[str, str | None]:
    library_dirs = sorted({str(p.parent) for p in root.rglob("*.so*")})
    env = dict(os.environ, LD_LIBRARY_PATH=os.pathsep.join(library_dirs))
    output = subprocess.run(["ldd", str(path)], env=env, capture_output=True, text=True, check=False).stdout
    resolved: dict[str, str | None] = {}
    for line in output.splitlines():
        name, _, rest = line.strip().partition(" => ")
        if rest:
            target = rest.split(" (", 1)[0].strip()
            resolved[name] = None if target == "not found" else target
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True, help="bundle directory (dist/Karrierekrake)")
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    report = check_bundle(arguments.root)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
