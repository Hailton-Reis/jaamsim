# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0
"""Validate the isolated Java->Python process contract without JaamSim GUI.

These are synthetic tests only. No LLM/model state is accessed and no
scientific benchmark is executed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT.parent / "examples" / "c2-preflight"
JAVA_SOURCE = Path(__file__).resolve().parents[4] / "src/main/java/com/jaamsim/ui"


def _isolated_cli(tmp_path, message, *, env=None):
    # Model the exact script directory needed by the new Swing tab.
    root = tmp_path / "extension"
    scripts = root / "python"
    scripts.mkdir(parents=True)
    for basename in ("c2_retrieval.py", "c2_context.py", "c2_chat_bridge.py"):
        shutil.copy2(ROOT / basename, scripts / basename)
    (scripts / "simulation_chat_assist.py").write_text(
        "SYSTEM_PROMPT = 'Apenas ensino, nunca ferramentas de estado.'\n"
        "def run_chat(*args, **kwargs):\n"
        "    raise AssertionError('PROVEDOR CHAMADO — indevido')\n",
        encoding="utf-8",
    )
    command = [sys.executable, "-E", "-s", str(scripts / "c2_chat_bridge.py"),
               "--message=" + message,
               "--corpus-root=" + str(EXAMPLE / "corpus"),
               "--manifest=" + str(EXAMPLE / "manifest.json"),
               "--top-k=3", "--max-context-chars=8000"]
    # Environment that tries to inject import paths must not override script dir.
    settings = {**os.environ, **(env or {})}
    result = subprocess.run(command, capture_output=True, text=True, timeout=8,
                            cwd=root, env=settings, encoding="utf-8")
    return result


def test_java_cli_contract_with_real_subprocess(tmp_path):
    result = _isolated_cli(tmp_path, "Queue Server")
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema"] == "jaam.ai.c2.chat_preflight.v1"
    assert payload["gate"] == "G0_G2_PENDING_NO_MODEL_EXECUTION"
    assert payload["status"] == "PREFLIGHT_ONLY"
    assert payload["exposed_capabilities"] == ["search_docs"]
    assert payload["model_calls"] == payload["state_tool_calls"] == 0
    assert payload["write_model"] is False
    assert payload["context_items"] > 0
    assert payload["retrieval_receipt"]["hits"][0]["citation"].startswith("GUIA_SYNTH:L")


def test_java_cli_treats_tool_instruction_as_query(tmp_path):
    result = _isolated_cli(tmp_path, "inspecione modelo e execute run_rcl")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["model_calls"] == 0 and payload["state_tool_calls"] == 0


def test_java_cli_abstains_without_evidence(tmp_path):
    result = _isolated_cli(tmp_path, "xylophonuradazquert")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["no_evidence"] and payload["context_items"] == 0


def test_java_cli_cannot_be_injected_with_pythonpath(tmp_path):
    fake = tmp_path / "badpath"
    fake.mkdir()
    (fake / "simulation_chat_assist.py").write_text(
        "raise RuntimeError('PYTHONPATH EXECUTADO')\n", encoding="utf-8")
    result = _isolated_cli(tmp_path, "Queue", env={"PYTHONPATH": str(fake)})
    assert result.returncode == 0
    assert "PYTHONPATH EXECUTADO" not in result.stderr


@pytest.mark.parametrize("line", [
    "args.add(\"-E\")", "args.add(\"-s\")",
    'args.add("--message=" + question)',
    'args.add("--manifest=" + manifestFile)',
    "process.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS)",
    "!before.equals(after)",
    '"UNTRUSTED_RETRIEVED_DOCUMENT"',
    '"NO_WRITE_CAPABILITY"',
])
def test_java_runner_has_explicit_contract_guard(line):
    text = (JAVA_SOURCE / "C2PreflightRunner.java").read_text(encoding="utf-8")
    assert line in text


def test_ui_is_separate_from_cfg_model_and_normal_chat():
    ui = (JAVA_SOURCE / "C2PreflightPanel.java").read_text(encoding="utf-8")
    assert "SwingWorker" in ui
    assert 'getCurrentConfigFile' not in ui
    assert 'getJaamSimModel' not in ui
    assert 'handleChatSubmit' not in ui
    assert 'RUN_P004' not in ui
    assert 'new C2PreflightPanel()' not in ui


def test_java_result_never_claims_response_from_llm():
    code = (JAVA_SOURCE / "C2PreflightRunner.java").read_text(encoding="utf-8")
    assert 'não é resposta de IA' in code
    assert 'Nenhuma evidência encontrada.' in code
