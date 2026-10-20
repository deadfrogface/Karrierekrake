"""Linux bundle: drop the Qt GTK3 theme and use the host's libexpat.

PyInstaller collects Qt's ``platformthemes/libqgtk3.so`` and with it GTK 3,
GDK, cairo, pango, gdk-pixbuf, GIO, libXi and libXrender from the build host
(Ubuntu 22.04). Ubuntu ships no fix for several of their advisories
(docs/security/NATIVE_LINUX_CANDIDATE_DISPOSITION_2026-10-20.json). Qt's own
widget dialogs replace the GTK file chooser, so the plugin and every library
that only it pulled in are removed, together with Qt's unused GLib/GIO
network-information backend. ``libexpat.so.1`` (needed by the bundled
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

EXCLUDED_QT_PLUGINS = (
    "PySide6/Qt/plugins/platformthemes/libqgtk3.so",
    # GLib/GIO backend of QNetworkInformation; unused, NetworkManager backend stays.
    "PySide6/Qt/plugins/networkinformation/libqglib.so",
)
HOST_PROVIDED = frozenset({"libexpat.so.1"})
# Must not exist anywhere in the bundle; a reference to them must resolve on the host.
FORBIDDEN_IN_BUNDLE = frozenset({
    "libqgtk3.so", "libqglib.so", "libgtk-3.so.0", "libgdk-3.so.0", "libXi.so.6", "libXrender.so.1",
    "libgio-2.0.so.0", "libexpat.so.1",
    # Came only with the GTK theme; open Linux candidates in the disposition depend on their absence.
    "libcairo.so.2", "libcairo-gobject.so.2", "libpixman-1.so.0", "libgdk_pixbuf-2.0.so.0",
    "libpcre2-8.so.0",
    # Python's readline module is excluded (GUI app); it was the only consumer of these.
    "libreadline.so.8", "libtinfo.so.6",
})
# Imports no bundled ELF may have except their providers: GRegex/PCRE1
# (CVE-2017-11164 in libpcre.so.3 is reachable only through them).
FORBIDDEN_IMPORT_PREFIXES = ("g_regex_", "g_match_info_", "pcre_")
IMPORT_PROVIDERS = frozenset({"libglib-2.0.so.0", "libpcre.so.3"})
# Symbol fragments that must not occur at all: libstdc++'s header-only policy-based
# binary heap (__gnu_pbds; CVE-2026-102010 is in its erase_if).
FORBIDDEN_SYMBOL_FRAGMENTS = ("__gnu_pbds",)
# Reported, not gated: callers of libstdc++'s aligned operator new (CVE-2026-95619).
REPORTED_IMPORTS = frozenset({
    "_ZnwmSt11align_val_t", "_ZnamSt11align_val_t",
    "_ZnwmSt11align_val_tRKSt9nothrow_t", "_ZnamSt11align_val_tRKSt9nothrow_t",
})

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB = 0, 1, 5
SHT_SYMTAB, SHT_DYNSYM = 2, 11


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


def elf_symbols(path: str | os.PathLike) -> tuple[set[str], set[str]]:
    """(defined, undefined) symbol names from .dynsym and, if present, .symtab."""
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF":
        return set(), set()
    is64 = {1: False, 2: True}[data[4]]
    end = {1: "<", 2: ">"}[data[5]]
    if is64:
        shoff, = struct.unpack_from(end + "Q", data, 0x28)
        shentsize, shnum = struct.unpack_from(end + "HH", data, 0x3A)
        sh_fmt, sym_fmt = end + "IIQQQQIIQQ", end + "IBBHQQ"
    else:
        shoff, = struct.unpack_from(end + "I", data, 0x20)
        shentsize, shnum = struct.unpack_from(end + "HH", data, 0x2E)
        sh_fmt, sym_fmt = end + "IIIIIIIIII", end + "IIIBBH"
    sections = [struct.unpack_from(sh_fmt, data, shoff + index * shentsize) for index in range(shnum)]
    defined, undefined = set(), set()
    for _name, sh_type, _flags, _addr, offset, size, link, _info, _align, entsize in sections:
        if sh_type not in (SHT_SYMTAB, SHT_DYNSYM) or not entsize:
            continue
        strings = sections[link][4]
        for position in range(offset + entsize, offset + size, entsize):  # entry 0 is the null symbol
            fields = struct.unpack_from(sym_fmt, data, position)
            name_index, shndx = fields[0], (fields[3] if is64 else fields[5])
            if not name_index:
                continue
            start = strings + name_index
            name = data[start:data.index(b"\0", start)].decode(errors="replace")
            (undefined if shndx == 0 else defined).add(name)
    return defined, undefined


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


def check_bundle(root: Path, ldd: Callable[[Path, Path], dict[str, str | None]] | None = None,
                 symbols: Callable[[Path], tuple[set[str], set[str]]] | None = None) -> dict:
    """Fail if a forbidden library ships, a reference to it resolves into the bundle,
    or a bundled ELF imports or contains a forbidden symbol."""
    root = root.resolve(strict=True)
    files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
    shipped = sorted(str(path.relative_to(root)).replace("\\", "/") for path in files
                     if path.name in FORBIDDEN_IN_BUNDLE)
    references, problems, needed_by, reported = {}, [], {}, {}
    for path in files:
        if not _is_elf(path):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        defined, undefined = (symbols or elf_symbols)(path)
        if path.name not in IMPORT_PROVIDERS:
            problems += [f"{rel}: imports {name}" for name in sorted(undefined)
                         if name.startswith(FORBIDDEN_IMPORT_PREFIXES)]
        problems += [f"{rel}: contains symbol {name}" for name in sorted(defined | undefined)
                     if any(fragment in name for fragment in FORBIDDEN_SYMBOL_FRAGMENTS)]
        for name in sorted(undefined & REPORTED_IMPORTS):
            reported.setdefault(name, []).append(rel)
        wanted = sorted(set(elf_needed(path)) & FORBIDDEN_IN_BUNDLE)
        for name in wanted:
            needed_by.setdefault(name, []).append(rel)
        if not wanted:
            continue
        resolved = (ldd or _ldd)(path, root)
        references[rel] = {name: resolved.get(name) for name in wanted}
        for name in wanted:
            target = resolved.get(name)
            if target is None:
                problems.append(f"{rel}: {name} not found on host")
            elif Path(target).resolve().is_relative_to(root):
                problems.append(f"{rel}: {name} resolves inside the bundle ({target})")
    return {"ok": not shipped and not problems, "root": str(root), "forbidden_shipped": shipped,
            "host_references": references, "problems": problems, "needed_by": needed_by,
            "reported_imports": reported,
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
    try:
        report = check_bundle(arguments.root)
    except Exception as error:
        _annotate(f"linux_bundle_check_crashed: {type(error).__name__}: {error}")
        raise
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    for rel in report["forbidden_shipped"]:
        users = report["needed_by"].get(Path(rel).name, [])
        _annotate(f"shipped {rel}; DT_NEEDED by: {', '.join(users) or 'nothing'}")
    for problem in report["problems"]:
        _annotate(problem)
    for name, users in sorted(report["reported_imports"].items()):
        _annotate(f"{name} imported by: {', '.join(users)}", level="notice")
    return 0 if report["ok"] else 1


def _annotate(message: str, level: str = "error") -> None:
    """GitHub Actions annotation; public on the check run, unlike the job log."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level} title=Linux bundle libraries::" + message.replace("%", "%25").replace("\n", "%0A"))


if __name__ == "__main__":
    sys.exit(main())
