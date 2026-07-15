# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""Shared paths for the public academic-assistant extension."""

from pathlib import Path


PYTHON_DIR = Path(__file__).resolve().parent
ASSISTANT_ROOT = PYTHON_DIR.parent
REPOSITORY_ROOT = ASSISTANT_ROOT.parents[1]
EXAMPLES_DIR = ASSISTANT_ROOT / "examples"
OUTPUT_DIR = ASSISTANT_ROOT / "output"
