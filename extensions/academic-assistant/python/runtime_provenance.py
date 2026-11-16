#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""Local, self-reported interpreter provenance for offline JaamSim tools.

This is an auditable record from the process actually writing the report,
NOT a cryptographic attestation of the Python interpreter, the host or the
environment. No network, subprocesses, credentials or external dependencies.
"""
from __future__ import annotations

import hashlib
import platform
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_runtime(entry_script: Path) -> dict[str, Any]:
    """Record the executable and script of this Python process, fail closed.

    Runtime paths are local metadata; don't upload these reports to a public
    repository. A file digest proves the contents of that file at capture
    time, but does not independently attest process integrity.
    """
    script = Path(entry_script).resolve(strict=True)
    executable = Path(sys.executable).resolve(strict=True)
    if not script.is_file() or not executable.is_file():
        raise RuntimeError("Python executable or entry script cannot be verified")
    return {
        "schema": "jaam.ai.python_runtime.v1",
        "evidence_level": "self_reported_no_external_attestation",
        "python_executable": str(executable),
        "python_executable_sha256": sha256_file(executable),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_implementation": platform.python_implementation(),
        "entry_script": str(script),
        "entry_script_sha256": sha256_file(script),
    }
