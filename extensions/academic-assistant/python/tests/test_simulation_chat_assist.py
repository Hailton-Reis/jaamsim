import json
from argparse import Namespace
from pathlib import Path
import subprocess
import sys

PYTHON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_DIR))

import simulation_chat_assist


def test_simulation_chat_assist_dry_run(tmp_path):
    history_file = tmp_path / "chat.jsonl"
    output_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            str(PYTHON_DIR / "simulation_chat_assist.py"),
            "--message",
            "quero construir um modelo de simulacao",
            "--history-file",
            str(history_file),
            "--output-dir",
            str(output_dir),
            "--case-id",
            "smoke_chat",
            "--dry-run",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["online"] is False
    assert "processo" in payload["response"].lower()
    assert history_file.exists()
    assert (output_dir / "smoke_chat_chat_last_response.json").exists()


def test_simulation_chat_assist_dry_run_returns_offline_playbook(tmp_path):
    args = Namespace(
        message="Quero modelar um pronto atendimento com pacientes, triagem e medico",
        history_file=tmp_path / "chat.jsonl",
        output_dir=tmp_path,
        case_id="offline_playbook",
        model_context="",
        provider_order="nvidia,cerebras,groq",
        env_file=None,
        max_tokens=80,
        dry_run=True,
        require_online=False,
    )

    payload = simulation_chat_assist.run_chat(args)

    assert payload["mode"] == "offline_playbook"
    assert payload["intent"] == "create_model"
    assert payload["next_actions"]
    assert payload["checklist"]
    assert payload["suggestions"]
    assert "pronto" in " ".join(payload["suggestions"]).lower() or "pronto" in payload["response"].lower()


def test_simulation_chat_assist_offline_intents_cover_core_actions():
    cases = {
        "usar StatFit com esses dados": "statfit",
        "revisar modelo e alertas RCL": "review_model",
        "Quero revisar este modelo antes de continuar": "review_model",
        "interpretar resultado com gargalo e throughput": "interpret_results",
        "Está formando fila, o que faço?": "interpret_results",
        "explicar objeto Queue": "explain_object",
        "checklist para defesa na banca": "defense_checklist",
        "Tenho dois atendentes e clientes chegam a cada cinco minutos": "create_model",
        "": "empty",
    }

    for message, expected in cases.items():
        assert simulation_chat_assist.build_offline_playbook(message)["intent"] == expected


def test_simulation_chat_assist_offline_returns_guided_model_steps():
    payload = simulation_chat_assist.build_offline_playbook(
        "Quero modelar um pronto atendimento intermediario com recepcao, triagem, medico e filas"
    )

    assert payload["pattern"] == "pronto atendimento"
    assert payload["complexity"] == "intermediario"
    assert any("EntityGenerator" in step for step in payload["jaamsim_steps"])
    assert any("PrototypeEntity" in step for step in payload["jaamsim_steps"])
    assert any("WaitQueue" in step for step in payload["jaamsim_steps"])
    assert any("ServiceTime" in step for step in payload["jaamsim_steps"])
    assert any("RunDuration" in step for step in payload["jaamsim_steps"])
    assert any("recepção" in step.lower() for step in payload["jaamsim_steps"])
    assert any("ProModel" not in step for step in payload["jaamsim_steps"])
    assert payload["promodel_steps"]
    assert payload["evidence_plan"]
    assert any("interpretação offline" in item.lower() for item in payload["evidence_plan"])
    assert "JaamSim:" in payload["response"]
    assert "ProModel:" in payload["response"]
    assert "Evidência:" in payload["response"]


def test_simulation_chat_assist_short_greeting_does_not_match_inside_dois():
    assert simulation_chat_assist.detect_intent("Tenho dois atendentes") == "create_model"


def test_simulation_chat_assist_uses_history_to_keep_pattern_context():
    history = [
        {"role": "user", "content": "Quero modelar um pronto atendimento com recepção e triagem."},
        {"role": "assistant", "content": "Vamos definir o fluxo."},
    ]

    payload = simulation_chat_assist.build_offline_playbook(
        "Qual é o próximo passo?",
        history=history,
        model_context="Modelo JaamSim ainda vazio.",
    )

    assert payload["pattern"] == "pronto atendimento"
    assert "PrototypeEntity" in payload["response"]


def test_simulation_chat_assist_defense_mode_adds_evidence_contract():
    payload = simulation_chat_assist.build_offline_playbook(
        "Preciso justificar para defesa uma simulacao com replicacoes e validacao"
    )

    assert payload["complexity"] == "defesa"
    assert any("confirmado" in item.lower() for item in payload["evidence_plan"])
    assert any("evidência" in step.lower() for step in payload["jaamsim_steps"])


def test_simulation_chat_assist_require_online_does_not_fake_response(monkeypatch, tmp_path):
    monkeypatch.setattr(simulation_chat_assist.tcc_llm_assist, "configured_candidates", lambda *_args, **_kwargs: [])
    args = Namespace(
        message="oi",
        history_file=tmp_path / "chat.jsonl",
        output_dir=tmp_path,
        case_id="online_required",
        model_context="Modelo de teste",
        provider_order="nvidia,cerebras,groq",
        env_file=None,
        max_tokens=80,
        dry_run=False,
        require_online=True,
    )

    payload = simulation_chat_assist.run_chat(args)

    assert payload["ok"] is False
    assert payload["online"] is False
    assert payload["response"] == ""
    assert payload["note"] == "online_required_no_provider"


def test_simulation_chat_assist_prompt_guides_distribution_and_flow_images():
    prompt = simulation_chat_assist.SYSTEM_PROMPT.lower()

    assert "poisson" in prompt
    assert "exponenciais" in prompt
    assert "triangular" in prompt
    assert "statfit" in prompt
    assert "bizagi" in prompt
    assert "idef-sim" in prompt


def test_simulation_chat_assist_prompt_keeps_utf8_sentinel_words():
    text = simulation_chat_assist.SYSTEM_PROMPT + "\n" + simulation_chat_assist.fallback_response("oi")

    for word in [
        "Você",
        "simulação",
        "distribuição",
        "distribuições",
        "horários",
        "mínimo",
        "máximo",
        "útil",
        "serviço",
        "lógica",
        "próximo",
        "única",
        "óleo",
        "métricas",
        "estágios",
    ]:
        assert word in text


def test_simulation_chat_assist_stdout_payload_is_ascii_safe():
    payload = {"response": "ação com espaço estreito \u202f e símbolo \u2248"}

    json.dumps(payload, ensure_ascii=True).encode("ascii")
