"""Prevent PyInstaller dependency search from substituting older Windows DLLs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def coherent_windows_runtime(binaries, prefix, *, expected=None):
    if expected is None:
        config = json.loads((ROOT / 'packaging/ci_python_runtimes.json').read_text())
        expected = config['runtimes']['x86_64-pc-windows-msvc']['files']
    sources = {}
    for relative, digest in expected.items():
        source = Path(prefix) / relative
        try:
            with source.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        except OSError as exc:
            raise ValueError('windows_runtime_source_missing') from exc
        if actual != digest:
            raise ValueError('windows_runtime_source_hash_mismatch')
        sources[source.name.casefold()] = source
    required, collected, result = set(sources), set(), []
    for row in binaries:
        name = str(row[0]).replace('\\', '/').rsplit('/', 1)[-1].casefold()
        if name in sources:
            # Preserve every destination (including Qt plugin paths), while
            # requiring every copy of the same runtime DLL to share provenance.
            result.append((row[0], str(sources[name]), row[2]))
            collected.add(name)
        else:
            result.append(row)
    if collected != required:
        raise ValueError('windows_runtime_collection_incomplete')
    return result


def find_openmp_runtime(system_root=None, program_files=None):
    """vcomp140.dll (Microsoft's OpenMP runtime) that the llama/ggml DLLs import but PyInstaller does not collect.

    Searched in the Windows system folder first, then in the Visual C++ redistributable folders of an installed
    Visual Studio. A missing runtime stops the build: without it the local model cannot start on a PC that has no
    Visual C++ runtime installed.
    """
    import glob
    import os

    system_root = system_root or os.environ.get('SystemRoot', r'C:\Windows')
    program_files = program_files or [os.environ.get('ProgramFiles', r'C:\Program Files'),
                                      os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')]
    candidates = [os.path.join(system_root, 'System32', 'vcomp140.dll')]
    for base in program_files:
        pattern = os.path.join(base, 'Microsoft Visual Studio', '*', '*', 'VC', 'Redist', 'MSVC', '*', 'x64',
                               'Microsoft.VC*.OpenMP', 'vcomp140.dll')
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise ValueError('windows_openmp_runtime_missing')


# The llama/ggml DLLs import these. Windows resolves a DLL's own imports next to it, so they must lie in that folder;
# a copy that only sits in another package's folder (PySide6 ships its own) is not found, and a PC without the
# Visual C++ runtime cannot load the local model.
LLAMA_RUNTIME_DLLS = ("vcomp140.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
LLAMA_RUNTIME_DIR = "llama_cpp/lib/"


def llama_runtime_entries(binaries, system_root=None, program_files=None):
    """PyInstaller binary entries that put the runtime DLLs next to llama.dll (only those not already there)."""
    import os

    present = {str(row[0]).replace("\\", "/").casefold() for row in binaries}
    by_name = {}
    for row in binaries:
        by_name.setdefault(str(row[0]).replace("\\", "/").rsplit("/", 1)[-1].casefold(), row[1])
    system_root = system_root or os.environ.get("SystemRoot", r"C:\Windows")
    entries = []
    for name in LLAMA_RUNTIME_DLLS:
        if (LLAMA_RUNTIME_DIR + name) in present:
            continue
        source = by_name.get(name)
        if not source:
            candidate = os.path.join(system_root, "System32", name)
            source = candidate if os.path.isfile(candidate) else None
        if not source and name == "vcomp140.dll":
            source = find_openmp_runtime(system_root, program_files)
        if not source:
            raise ValueError("windows_llama_runtime_missing:" + name)
        entries.append((LLAMA_RUNTIME_DIR + name, source, "BINARY"))
    return entries
