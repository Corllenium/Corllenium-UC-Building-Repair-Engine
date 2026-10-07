"""Windows system and process telemetry probes via ctypes."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from typing import Any


def _get_system_times_nt() -> dict[str, int]:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    def _ft(ft: FILETIME) -> int:
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    kernel32 = ctypes.WinDLL("kernel32")
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return {"idle": _ft(idle), "kernel": _ft(kernel), "user": _ft(user)}
    return {}


def _count_processes_nt() -> tuple[int, int]:
    """Count (other python.exe, msedge.exe) processes."""
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    h = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h == wintypes.HANDLE(-1).value:
        return 0, 0
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    py_count = 0
    edge_count = 0
    cur_pid = kernel32.GetCurrentProcessId()
    success = kernel32.Process32First(h, ctypes.byref(pe))
    while success:
        exe = pe.szExeFile.decode("ascii", errors="ignore").lower()
        if exe == "python.exe":
            if pe.th32ProcessID != cur_pid:
                py_count += 1
        elif exe == "msedge.exe":
            edge_count += 1
        success = kernel32.Process32Next(h, ctypes.byref(pe))
    kernel32.CloseHandle(h)
    return py_count, edge_count


def get_machine_load() -> dict[str, Any]:
    """Snapshot of machine load (other python/edge processes, CPU times)."""
    if os.name == "nt":
        py_count, edge_count = _count_processes_nt()
        times = _get_system_times_nt()
        return {
            "python_processes": py_count,
            "msedge_processes": edge_count,
            "system_times": times,
        }
    return {"python_processes": 0, "msedge_processes": 0, "system_times": {}}


def peak_memory_mb() -> tuple[float | None, float | None]:
    """`(peak working set, peak commit)` of this process in MB via Windows GetProcessMemoryInfo (`PeakWorkingSetSize`
    and `PeakPagefileUsage`); `(None, None)` off Windows or when the call fails. The one place the engine reads
    them: the census, the SketchUp reader and the Validator's `validate` command all ask here."""
    if os.name != "nt":
        return None, None

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return (round(counters.PeakWorkingSetSize / (1024 * 1024), 1),
                round(counters.PeakPagefileUsage / (1024 * 1024), 1))
    return None, None


def get_process_peak_memory_mb() -> float:
    """Current process's peak working set size in MB via Windows GetProcessMemoryInfo; 0.0 off Windows."""
    peak, _ = peak_memory_mb()
    return peak if peak is not None else 0.0
