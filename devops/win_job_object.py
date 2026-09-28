"""Windows Job Object containment for a process group.

Children inherit the job. Breakaway flags are never granted, and the process
is assigned while still suspended so it cannot spawn before it is inside the
job. Peak memory is ``JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakJobMemoryUsed``
(the Job Object process-group high-water mark).

This module imports on every platform. Kernel calls run only on Windows.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

# https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000

JobObjectExtendedLimitInformation = 9
JobObjectAssociateCompletionPortInformation = 7
# Posted on the job's completion port when a commit hits JobMemoryLimit.
JOB_OBJECT_MSG_JOB_MEMORY_LIMIT = 10
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def containment_limit_flags(*, enforce_memory_bytes: int | None = None) -> int:
    """Limit flags that keep every child inside the job.

    ``JOB_OBJECT_LIMIT_BREAKAWAY_OK`` and ``JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK``
    are never set. ``CREATE_BREAKAWAY_FROM_JOB`` is not a limit flag; creation
    flags are checked separately in :func:`create_process_flags`.
    """
    flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
    if enforce_memory_bytes is not None:
        if enforce_memory_bytes <= 0:
            raise ValueError("enforce_memory_bytes must be > 0")
        flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
    forbidden = JOB_OBJECT_LIMIT_BREAKAWAY_OK | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
    if flags & forbidden:
        raise RuntimeError("job breakaway flags must not be set")
    return flags


def create_process_flags(*, console: bool) -> int:
    """Create the process suspended, without breakaway-from-job."""
    flags = CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP
    if not console:
        flags |= CREATE_NO_WINDOW
    if flags & CREATE_BREAKAWAY_FROM_JOB:
        raise RuntimeError("CREATE_BREAKAWAY_FROM_JOB must not be set")
    if not (flags & CREATE_SUSPENDED):
        raise RuntimeError("process must be created suspended so it can be assigned first")
    return flags


def assign_then_resume(kernel: object, job_handle: int, process_handle: int, thread_handle: int) -> None:
    """Assign the suspended process to the job, then resume its primary thread."""
    assigned = kernel.AssignProcessToJobObject(job_handle, process_handle)  # type: ignore[attr-defined]
    if not assigned:
        err = ctypes.get_last_error() if sys.platform == "win32" else 0
        raise OSError(err, "AssignProcessToJobObject failed before ResumeThread")
    resumed = kernel.ResumeThread(thread_handle)  # type: ignore[attr-defined]
    if resumed == 0xFFFFFFFF:
        err = ctypes.get_last_error() if sys.platform == "win32" else 0
        raise OSError(err, "ResumeThread failed after the process was assigned to the job")


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """Windows ABI. DWORD fields are explicitly 32-bit (Linux ``wintypes.DWORD`` is not)."""

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_ASSOCIATE_COMPLETION_PORT(ctypes.Structure):
    _fields_ = [
        ("CompletionKey", ctypes.c_void_p),
        ("CompletionPort", ctypes.c_void_p),
    ]


def is_job_memory_limit_message(number_of_bytes: int) -> bool:
    """True for ``JOB_OBJECT_MSG_JOB_MEMORY_LIMIT`` (the completion-port payload)."""
    return int(number_of_bytes) == JOB_OBJECT_MSG_JOB_MEMORY_LIMIT


def associate_job_memory_completion_port(kernel: object, job_handle: int) -> object:
    """Associate a new I/O completion port with ``job_handle``. Windows only.

    The port receives ``JOB_OBJECT_MSG_JOB_MEMORY_LIMIT`` when the job memory
    limit refuses a commit. The caller closes the returned handle.
    """
    invalid = ctypes.c_void_p(-1)
    port = kernel.CreateIoCompletionPort(invalid, None, 0, 1)  # type: ignore[attr-defined]
    if not port:
        err = ctypes.get_last_error() if sys.platform == "win32" else 0
        raise OSError(err, "CreateIoCompletionPort failed")
    info = JOBOBJECT_ASSOCIATE_COMPLETION_PORT()
    info.CompletionKey = 1
    info.CompletionPort = port
    ok = kernel.SetInformationJobObject(  # type: ignore[attr-defined]
        job_handle,
        JobObjectAssociateCompletionPortInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        err = ctypes.get_last_error() if sys.platform == "win32" else 0
        kernel.CloseHandle(port)  # type: ignore[attr-defined]
        raise OSError(err, "SetInformationJobObject completion port failed")
    return port


def drain_job_memory_limit(kernel: object, port: object) -> bool:
    """Drain the job completion port. True if a job-memory-limit message was queued."""
    hit = False
    while True:
        transferred = wintypes.DWORD(0)
        key = ctypes.c_size_t(0)
        overlapped = ctypes.c_void_p()
        ok = kernel.GetQueuedCompletionStatus(  # type: ignore[attr-defined]
            port,
            ctypes.byref(transferred),
            ctypes.byref(key),
            ctypes.byref(overlapped),
            0,
        )
        if not ok:
            break
        if is_job_memory_limit_message(int(transferred.value)):
            hit = True
    return hit


def extended_limit_info(
    *,
    enforce_memory_bytes: int | None = None,
) -> JOBOBJECT_EXTENDED_LIMIT_INFORMATION:
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = containment_limit_flags(
        enforce_memory_bytes=enforce_memory_bytes
    )
    if enforce_memory_bytes is not None:
        info.JobMemoryLimit = int(enforce_memory_bytes)
    return info


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


_KERNEL = None


def kernel32():
    """Bound Win32 kernel32. Windows only."""
    global _KERNEL
    if sys.platform != "win32":
        raise OSError("Windows Job Object API is only available on Windows")
    if _KERNEL is not None:
        return _KERNEL
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
    ]
    k.QueryInformationJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    k.CreateProcessW.restype = wintypes.BOOL
    k.ResumeThread.argtypes = [wintypes.HANDLE]
    k.ResumeThread.restype = wintypes.DWORD
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k.TerminateJobObject.restype = wintypes.BOOL
    k.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k.TerminateProcess.restype = wintypes.BOOL
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    k.GetExitCodeProcess.restype = wintypes.BOOL
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    k.IsProcessInJob.restype = wintypes.BOOL
    k.CreateIoCompletionPort.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        wintypes.DWORD,
    ]
    k.CreateIoCompletionPort.restype = ctypes.c_void_p
    k.GetQueuedCompletionStatus.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.DWORD,
    ]
    k.GetQueuedCompletionStatus.restype = wintypes.BOOL
    _KERNEL = k
    return k


def _win_error(action: str) -> OSError:
    err = ctypes.get_last_error()
    return OSError(err, f"{action} failed: {ctypes.WinError(err)}")
