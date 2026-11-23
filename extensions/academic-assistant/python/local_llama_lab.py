"""Isolated, opt-in llama.cpp lab runner: pin binary/GGUF, start one local server, measure.

Does NOT touch JaamSim/CFG, call RCL/RAG/tools, install software or run a study.
Python >=3.11 standard library. Explicit --execute is required to launch.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any

import local_llama_preflight as guard
import local_llama_smoke as smoke

SCHEMA = "jaam.ai.local_llama_lab.v1"
GATE = "G0_G2_PENDING_ENGINEERING_ONLY"
MiB = 1024 * 1024
MAX_BINARY = 2 * 1024**3


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(MiB), b""):
            h.update(chunk)
    return h.hexdigest()


def check_binary(path: str, pin: str) -> dict[str, Any]:
    if not guard.SHA256_RE.fullmatch(pin):
        raise ValueError("binary_pin_invalid")
    item = Path(path)
    if item.is_symlink() or not item.is_file():
        raise ValueError("binary_not_regular_or_symlink")
    if os.name != "nt" and not os.access(item, os.X_OK):
        raise ValueError("binary_not_executable")
    size = item.stat().st_size
    if not 1 <= size <= MAX_BINARY:
        raise ValueError("binary_size_out_of_range")
    observed = sha_file(item)
    if observed != pin:
        raise ValueError("binary_sha256_mismatch")
    return {"sha256": observed, "bytes": size}


def check_model(path: str, pin: str) -> dict[str, Any]:
    identity = guard.gguf_identity(path, pin)
    if not identity["gguf_examined"] or not identity["gguf_pinned"]:
        raise ValueError("gguf_sha256_mismatch")
    return {"sha256": identity["gguf_sha256"],
            "bytes": identity["gguf_size_bytes"]}


def check_port_available(port: int) -> None:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("unsafe_port")
    # Bind test, not a security guarantee against other local processes.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
        check.bind(("127.0.0.1", port))


def read_rss_bytes(pid: int) -> int | None:
    """One process RSS, not the entire machine or spawned process tree."""
    try:
        if os.name == "nt":
            from ctypes import wintypes
            class PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
            if not handle:
                return None
            try:
                item = PMC()
                item.cb = ctypes.sizeof(PMC)
                api = ctypes.WinDLL("psapi", use_last_error=True)
                api.GetProcessMemoryInfo.argtypes = [
                    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
                api.GetProcessMemoryInfo.restype = wintypes.BOOL
                if not api.GetProcessMemoryInfo(handle, ctypes.byref(item), item.cb):
                    return None
                return int(item.WorkingSetSize)
            finally:
                kernel.CloseHandle(handle)
        status = Path(f"/proc/{pid}/status")
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError, AttributeError):
        return None
    return None


def read_system_ram_bytes() -> tuple[int, int] | None:
    """Total and used physical memory at sample time; system-wide, not JAAM-AI-only."""
    try:
        if os.name == "nt":
            from ctypes import wintypes
            class MEM(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            memory = MEM()
            memory.dwLength = ctypes.sizeof(MEM)
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.GlobalMemoryStatusEx.argtypes = [ctypes.c_void_p]
            api.GlobalMemoryStatusEx.restype = wintypes.BOOL
            if not api.GlobalMemoryStatusEx(ctypes.byref(memory)):
                return None
            return int(memory.ullTotalPhys), int(memory.ullTotalPhys - memory.ullAvailPhys)
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if ":" in line:
                key, rest = line.split(":", 1)
                parts = rest.split()
                if key in ("MemTotal", "MemAvailable") and parts:
                    values[key] = int(parts[0]) * 1024
        if len(values) == 2:
            return values["MemTotal"], values["MemTotal"] - values["MemAvailable"]
    except (OSError, ValueError, IndexError, AttributeError):
        return None
    return None


class Sampler:
    def __init__(self, pid: int, interval: float = 0.2):
        self.pid = pid
        self.interval = interval
        self.stop_event = threading.Event()
        self.samples = 0
        self.peak_process_rss = None
        self.peak_system_used = None
        self.total_system = None
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            rss = read_rss_bytes(self.pid)
            memory = read_system_ram_bytes()
            if rss is not None:
                self.peak_process_rss = max(self.peak_process_rss or 0, rss)
            if memory is not None:
                total, used = memory
                self.total_system = total
                self.peak_system_used = max(self.peak_system_used or 0, used)
            self.samples += 1
            self.stop_event.wait(self.interval)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> dict[str, Any]:
        self.stop_event.set()
        self.thread.join(timeout=2)
        return {
            "samples": self.samples,
            "server_process_rss_peak_mib": round(self.peak_process_rss / MiB, 2)
                if self.peak_process_rss is not None else None,
            "system_ram_used_sampled_peak_mib": round(self.peak_system_used / MiB, 2)
                if self.peak_system_used is not None else None,
            "system_physical_total_mib": round(self.total_system / MiB, 2)
                if self.total_system is not None else None,
            "scope": "single-server-process RSS and host-wide used RAM (sampled); no JVM/JaamSim",
        }


def server_ready(endpoint: str, process: subprocess.Popen, limit: float) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            response = guard.get_json(endpoint, "/health", timeout=1)
            if isinstance(response, dict) and response.get("status") in ("ok", "ready"):
                return True
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    return False


def safe_environment() -> dict[str, str]:
    # Avoid accidentally forwarding API tokens and arbitrary LLAMA_ARG_* controls.
    permitted = {"PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE",
                 "TEMP", "TMP", "LANG", "LC_ALL"}
    return {key: value for key, value in os.environ.items()
            if key.upper() in permitted}


def lab(server_bin: str, server_sha256: str, gguf_file: str, gguf_sha256: str,
        *, execute: bool = False, evidence_dir: str | None = None,
        port: int = 9931, startup_seconds: float = 90,
        inference_seconds: float = 45) -> dict[str, Any]:
    if not 2 <= startup_seconds <= 180 or not 1 <= inference_seconds <= 90:
        raise ValueError("unsafe_timeout")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("unsafe_port")
    binary_identity = check_binary(server_bin, server_sha256)
    model_identity = check_model(gguf_file, gguf_sha256)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "gate": GATE,
        "status": "DRY_RUN_VERIFIED_FILES",
        "scientific_authorization": False,
        "binary_identity": binary_identity,
        "model_identity": model_identity,
        "model_generation_calls": 0,
        "state_tool_calls": 0,
        "document_search_calls": 0,
        "write_model": False,
        "whole_system_8gb_validated": False,
        "java_gui_windows_accepted": False,
        "binary_launched": False,
        "local_inference_attempted": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not execute:
        return result
    if not evidence_dir:
        raise ValueError("evidence_dir_required")
    base = Path(evidence_dir)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("evidence_dir_invalid_or_symlink")
    check_port_available(port)
    # Always create a new run folder; never overwrite a previous run.
    session = Path(tempfile.mkdtemp(prefix="jaam-local-llm-", dir=base))
    log_file = session / "llama_server.log"
    report_file = session / "report.json"
    endpoint = f"http://127.0.0.1:{port}"
    argv = [
        str(Path(server_bin).absolute()),
        "--model", str(Path(gguf_file).absolute()),
        "--host", "127.0.0.1", "--port", str(port),
        "--ctx-size", "2048", "--parallel", "1",
        "--threads", "2", "--n-gpu-layers", "0",
    ]
    result.update({"status": "LAB_FAILED", "evidence_session": str(session),
                   "server_log_sha256": None,
                   "resource_metrics": None,
                   "startup_seconds": None})
    process = None
    monitor = None
    started = time.monotonic()
    try:
        with log_file.open("wb") as log:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       cwd=session, env=safe_environment(),
                                       shell=False)
            result["binary_launched"] = True
            monitor = Sampler(process.pid)
            monitor.start()
            if not server_ready(endpoint, process, startup_seconds):
                raise RuntimeError("server_startup_failed")
            result["startup_seconds"] = round(time.monotonic() - started, 2)
            # Read server-advertised ID only after launching a pinned local binary.
            meta = guard.get_json(endpoint, "/v1/models", timeout=2)
            items = meta.get("data") if isinstance(meta, dict) else None
            if (not isinstance(items, list) or len(items) != 1
                    or not isinstance(items[0], dict)
                    or not isinstance(items[0].get("id"), str)
                    or not 0 < len(items[0]["id"]) < 256):
                raise RuntimeError("model_id_unavailable")
            pinned_name = smoke.sha(items[0]["id"])
            result["advertised_model_id_sha256"] = pinned_name
            result["local_inference_attempted"] = True
            shot = smoke.smoke(endpoint, pinned_name, execute=True,
                               timeout=inference_seconds)
            # Do not misrepresent a protocol response as proof of genuine model output.
            result["smoke_result"] = shot
            result["model_generation_calls"] = shot["model_generation_calls"]
            if shot["status"] != "LOCAL_GENERATION_OBSERVED_UNATTESTED":
                raise RuntimeError("smoke_protocol_failure")
            result["status"] = "LAB_SMOKE_OBSERVED_REVIEW_REQUIRED"
    except (OSError, ValueError, RuntimeError) as error:
        result["status"] = "LAB_FAILED"
        # Never store untrusted message/path contents in the public report.
        result["failure_class"] = type(error).__name__
        if type(error) is RuntimeError and str(error) in (
                "server_startup_failed", "model_id_unavailable",
                "smoke_protocol_failure"):
            result["failure_code"] = str(error)
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)
            result["server_exit_code_after_shutdown"] = process.returncode
        if monitor is not None:
            result["resource_metrics"] = monitor.stop()
        if log_file.is_file():
            result["server_log_sha256"] = sha_file(log_file)
            result["server_log_bytes"] = log_file.stat().st_size
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        # Write atomically within this newly created session only.
        tmp = session / "report.tmp"
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        tmp.replace(report_file)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated, opt-in llama.cpp server smoke + RSS lab")
    parser.add_argument("--server-bin", required=True)
    parser.add_argument("--expected-server-sha256", required=True)
    parser.add_argument("--gguf-file", required=True)
    parser.add_argument("--expected-gguf-sha256", required=True)
    parser.add_argument("--port", type=int, default=9931)
    parser.add_argument("--startup-seconds", type=float, default=90)
    parser.add_argument("--inference-seconds", type=float, default=45)
    parser.add_argument("--evidence-dir")
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly start a pinned CPU-only server and send one fixed prompt")
    a = parser.parse_args(argv)
    try:
        result = lab(a.server_bin, a.expected_server_sha256,
                     a.gguf_file, a.expected_gguf_sha256,
                     port=a.port, startup_seconds=a.startup_seconds,
                     inference_seconds=a.inference_seconds,
                     evidence_dir=a.evidence_dir, execute=a.execute)
    except (ValueError, OSError) as exc:
        result = {"schema": SCHEMA, "status": "INVALID_LAB_REQUEST",
                  "failure_class": type(exc).__name__,
                  "model_generation_calls": 0, "binary_launched": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in (
        "DRY_RUN_VERIFIED_FILES", "LAB_SMOKE_OBSERVED_REVIEW_REQUIRED") else 3


if __name__ == "__main__":
    raise SystemExit(main())
