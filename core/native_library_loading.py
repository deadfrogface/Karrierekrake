"""Keep optional DLL load errors inside the app; preserve Windows policy."""
from contextlib import contextmanager
import sys


def is_integrity_policy_error(error: BaseException) -> bool:
    """Recognize Windows policy/hash rejection, including ctypes wrappers."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if getattr(error, "winerror", None) == 577 or "0xc0e90002" in str(error).lower():
            return True
        error = error.__cause__ or error.__context__
    return False


@contextmanager
def quiet_native_loader():
    """Suppress the loader's modal error box on this thread, then restore it.

    LoadLibrary still fails for blocked/invalid binaries. This does not alter
    Smart App Control, signature checks, or any system-wide security setting.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetThreadErrorMode.argtypes = []
    kernel.GetThreadErrorMode.restype = wintypes.DWORD
    kernel.SetThreadErrorMode.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetThreadErrorMode.restype = wintypes.BOOL
    previous = wintypes.DWORD()
    flags = kernel.GetThreadErrorMode() | 0x0001 | 0x8000
    changed = kernel.SetThreadErrorMode(flags, ctypes.byref(previous))
    try:
        yield
    finally:
        if changed:
            kernel.SetThreadErrorMode(previous.value, None)
