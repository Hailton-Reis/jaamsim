#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""
Assistente LLM opcional para o prototipo academico JaamSim.

Esta camada nao faz parte do nucleo offline do MVP. Ela e acionada apenas por
flag/CLI, usa variaveis locais de ambiente e mantem fallback por ranking
de provedores. Nenhum token e impresso ou versionado por este modulo.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import assistant_paths


TOOLS_DIR = Path(__file__).resolve().parent
ASSISTANT_ROOT = assistant_paths.ASSISTANT_ROOT
REPO_ROOT = assistant_paths.REPOSITORY_ROOT
DEFAULT_PROVIDER_ORDER = "dashscope,nvidia,cerebras,groq"
DEFAULT_VISION_PROVIDER_ORDER = "dashscope,nvidia"
SUPPORTED_PROVIDERS = {"nvidia", "cerebras", "groq", "dashscope"}


@dataclass(frozen=True)
class ProviderCandidate:
    provider: str
    label: str
    base_url: str
    api_key_env: str
    model_env: str
    default_model: str
    model: str
    rank: int


@dataclass
class ProviderAttempt:
    provider: str
    model: str
    ok: bool
    latency_ms: float
    tokens: int
    error: str = ""


@dataclass
class LlmAssistResult:
    enabled: bool
    selected_provider: str | None
    selected_model: str | None
    content: str
    attempts: list[ProviderAttempt]
    prompt_policy: str


PROVIDER_DEFINITIONS: dict[str, dict[str, str]] = {
    "nvidia": {
        "label": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model_env": "NVIDIA_MODEL_CHAT",
        "default_model": "nvidia/nemotron-3-super-120b-a12b",
    },
    "cerebras": {
        "label": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "model_env": "CEREBRAS_MODEL_CHAT",
        "default_model": "gpt-oss-120b",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL_COMPLEX",
        "default_model": "llama-3.3-70b-versatile",
    },
    "dashscope": {
        "label": "Alibaba Cloud Model Studio (DashScope/Qwen)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_env": "DASHSCOPE_MODEL_CHAT",
        "default_model": "qwen-plus",
    },
}

VISION_PROVIDER_SPECS: list[dict[str, str]] = [
    {
        "provider": "dashscope",
        "model_env": "DASHSCOPE_MODEL_VISION",
        "default_model": "qwen-vl-ocr-2025-11-20",
    },
    {
        "provider": "dashscope",
        "model_env": "DASHSCOPE_MODEL_VISION_FALLBACK",
        "default_model": "qwen3.5-omni-plus-2026-03-15",
    },
    {
        "provider": "nvidia",
        "model_env": "NVIDIA_MODEL_VISION",
        "default_model": "nvidia/nemotron-nano-12b-v2-vl",
    },
    {
        "provider": "nvidia",
        "model_env": "NVIDIA_MODEL_VISION_FALLBACK",
        "default_model": "meta/llama-3.2-11b-vision-instruct",
    },
]


def parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_env_file(path: Path, *, override: bool = False) -> list[str]:
    if not path.exists():
        return []
    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parsed = parse_env_line(line)
        if not parsed:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def load_local_env(env_file: Path | None = None) -> list[str]:
    candidates = []
    if env_file:
        candidates.append(env_file)
    candidates.extend([ASSISTANT_ROOT / ".env", REPO_ROOT / ".env", REPO_ROOT / ".env.local"])
    loaded: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        loaded.extend(load_env_file(resolved))
    return loaded


def parse_provider_order(raw_order: str | None) -> list[str]:
    order = (
        raw_order
        or os.getenv("JAAMSIM_LLM_PROVIDER_ORDER")
        or os.getenv("TCC_LLM_PROVIDER_ORDER")
        or os.getenv("CHAT_PROVIDER_ORDER")
        or DEFAULT_PROVIDER_ORDER
    )
    providers: list[str] = []
    for item in order.split(","):
        provider = item.strip().lower()
        if provider in SUPPORTED_PROVIDERS and provider not in providers:
            providers.append(provider)
    return providers or DEFAULT_PROVIDER_ORDER.split(",")


def parse_vision_provider_order(raw_order: str | None) -> list[str]:
    order = (
        raw_order
        or os.getenv("JAAMSIM_VISION_PROVIDER_ORDER")
        or os.getenv("TCC_VISION_PROVIDER_ORDER")
        or os.getenv("VISION_PROVIDER_ORDER")
        or DEFAULT_VISION_PROVIDER_ORDER
    )
    providers: list[str] = []
    for item in order.split(","):
        provider = item.strip().lower()
        if provider in SUPPORTED_PROVIDERS and provider not in providers:
            providers.append(provider)
    return providers or DEFAULT_VISION_PROVIDER_ORDER.split(",")


def configured_candidates(provider_order: str | None = None, env_file: Path | None = None) -> list[ProviderCandidate]:
    load_local_env(env_file)
    candidates: list[ProviderCandidate] = []
    for rank, provider in enumerate(parse_provider_order(provider_order), start=1):
        definition = PROVIDER_DEFINITIONS[provider]
        api_key = os.getenv(definition["api_key_env"], "").strip()
        if not api_key:
            continue
        if provider == "dashscope" and os.getenv("DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED", "").strip() != "1":
            continue
        model = os.getenv(definition["model_env"], "").strip() or definition["default_model"]
        base_url_env = definition.get("base_url_env", "")
        base_url = os.getenv(base_url_env, "").strip() if base_url_env else ""
        candidates.append(
            ProviderCandidate(
                provider=provider,
                label=definition["label"],
                base_url=base_url or definition["base_url"],
                api_key_env=definition["api_key_env"],
                model_env=definition["model_env"],
                default_model=definition["default_model"],
                model=model,
                rank=rank,
            )
        )
    return candidates


def configured_vision_candidates(provider_order: str | None = None, env_file: Path | None = None) -> list[ProviderCandidate]:
    load_local_env(env_file)
    provider_order_list = parse_vision_provider_order(provider_order)
    candidates: list[ProviderCandidate] = []
    rank = 1
    for provider in provider_order_list:
        for spec in VISION_PROVIDER_SPECS:
            if spec["provider"] != provider:
                continue
            definition = PROVIDER_DEFINITIONS[provider]
            api_key = os.getenv(definition["api_key_env"], "").strip()
            if not api_key:
                continue
            if provider == "dashscope" and os.getenv("DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED", "").strip() != "1":
                continue
            model = os.getenv(spec["model_env"], "").strip() or spec["default_model"]
            base_url_env = definition.get("base_url_env", "")
            base_url = os.getenv(base_url_env, "").strip() if base_url_env else ""
            candidates.append(
                ProviderCandidate(
                    provider=provider,
                    label=definition["label"],
                    base_url=base_url or definition["base_url"],
                    api_key_env=definition["api_key_env"],
                    model_env=spec["model_env"],
                    default_model=spec["default_model"],
                    model=model,
                    rank=rank,
                )
            )
            rank += 1
    return candidates


def provider_status(provider_order: str | None = None, env_file: Path | None = None) -> list[dict[str, Any]]:
    load_local_env(env_file)
    status: list[dict[str, Any]] = []
    for rank, provider in enumerate(parse_provider_order(provider_order), start=1):
        definition = PROVIDER_DEFINITIONS[provider]
        status.append(
            {
                "rank": rank,
                "provider": provider,
                "api_key_env": definition["api_key_env"],
                "configured": bool(os.getenv(definition["api_key_env"], "").strip()),
                "model_env": definition["model_env"],
                "model": os.getenv(definition["model_env"], "").strip() or definition["default_model"],
                "available_for_use": provider != "dashscope"
                or os.getenv("DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED", "").strip() == "1",
            }
        )
    return status


def compact_review_context(review_payload: dict[str, Any]) -> dict[str, Any]:
    analysis = review_payload.get("analysis", {})
    suggestions = review_payload.get("local_suggestions", [])
    allowed_changes = review_payload.get("allowed_changes", [])
    decision_audit = review_payload.get("suggestion_decision_audit", [])
    return {
        "mode": review_payload.get("mode"),
        "input_type": review_payload.get("input_type"),
        "model_id": analysis.get("model_id"),
        "case_id": analysis.get("case_id"),
        "variant": analysis.get("variant"),
        "triggered_rules": review_payload.get("triggered_rules", []),
        "suggestion_status_counts": review_payload.get("suggestion_status_counts", {}),
        "alerts": [
            {
                "rule_id": item.get("rule_id"),
                "severity": item.get("severity"),
                "component_id": item.get("component_id"),
                "message": item.get("message"),
                "why_it_matters": item.get("why_it_matters"),
                "suggestion": item.get("suggestion"),
            }
            for item in analysis.get("alerts", [])
        ],
        "local_suggestions": [
            {
                "suggestion_id": item.get("suggestion_id"),
                "rule_id": item.get("rule_id"),
                "component_id": item.get("component_id"),
                "status": item.get("status"),
                "title": item.get("title"),
                "suggested_change": item.get("suggested_change"),
                "automation_policy": item.get("automation_policy"),
            }
            for item in suggestions
        ],
        "allowed_changes": [
            {
                "change_id": item.get("change_id"),
                "suggestion_id": item.get("suggestion_id"),
                "operation": item.get("operation"),
                "applyable": item.get("applyable"),
                "safety": item.get("safety"),
                "reason": item.get("reason"),
            }
            for item in allowed_changes
        ],
        "decision_audit": [
            {
                "audit_id": item.get("audit_id"),
                "suggestion_id": item.get("suggestion_id"),
                "status": item.get("status"),
                "decision_effect": item.get("decision_effect"),
                "guardrail": item.get("guardrail"),
                "automatic_application": item.get("automatic_application"),
            }
            for item in decision_audit
        ],
    }


def build_assist_messages(review_payload: dict[str, Any], operator_request: str | None = None) -> list[dict[str, str]]:
    context = compact_review_context(review_payload)
    request = operator_request or (
        "Analise o resultado do modulo offline e gere uma orientacao curta para o operador."
    )
    system_prompt = (
        "Voce e um assistente tecnico de simulacao discreta e JaamSim. "
        "Use somente o contexto fornecido. Nao invente evidencias, metricas, "
        "validacao com usuarios ou execucao visual. Trate a IA como camada opcional "
        "do prototipo local. Nao proponha alterar topologia automaticamente. "
        "Responda em portugues brasileiro, com secoes curtas: diagnostico, "
        "prioridades, perguntas ao operador e limite de seguranca."
    )
    user_prompt = (
        f"Pedido do operador: {request}\n\n"
        "Contexto auditavel do modulo offline:\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def call_chat_completion(
    candidate: ProviderCandidate,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 700,
    timeout_seconds: float = 60.0,
) -> tuple[str, int, float]:
    api_key = os.getenv(candidate.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"{candidate.api_key_env} nao configurada.")

    payload = {
        "model": candidate.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{candidate.base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "jaamsim-academic-assistant/0.1",
        },
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    latency_ms = (time.monotonic() - start) * 1000
    payload_response = json.loads(body)
    content = payload_response["choices"][0]["message"].get("content") or ""
    tokens = int(payload_response.get("usage", {}).get("total_tokens") or 0)
    if not content.strip():
        raise RuntimeError("Resposta vazia do provedor.")
    return content, tokens, latency_ms


def extract_response_content(payload_response: dict[str, Any]) -> str:
    choices = payload_response.get("choices") or []
    if not choices:
        return json.dumps(payload_response, ensure_ascii=False)[:4000]
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    chunks.append(str(text))
                else:
                    chunks.append(json.dumps(item, ensure_ascii=False))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, indent=2)
    return json.dumps(message, ensure_ascii=False, indent=2)


def call_vision_completion(
    candidate: ProviderCandidate,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 900,
    timeout_seconds: float = 90.0,
) -> tuple[str, int, float]:
    api_key = os.getenv(candidate.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"{candidate.api_key_env} nao configurada.")

    payload = {
        "model": candidate.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{candidate.base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "jaamsim-academic-assistant/0.1",
        },
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    latency_ms = (time.monotonic() - start) * 1000
    payload_response = json.loads(body)
    content = extract_response_content(payload_response)
    tokens = int(payload_response.get("usage", {}).get("total_tokens") or 0)
    if not content.strip():
        raise RuntimeError("Resposta vazia do provedor.")
    return content, tokens, latency_ms


def run_llm_assist(
    review_payload: dict[str, Any],
    *,
    provider_order: str | None = None,
    env_file: Path | None = None,
    operator_request: str | None = None,
    max_tokens: int = 700,
    dry_run: bool = False,
) -> LlmAssistResult:
    candidates = configured_candidates(provider_order, env_file)
    attempts: list[ProviderAttempt] = []
    messages = build_assist_messages(review_payload, operator_request)
    if dry_run:
        return LlmAssistResult(
            enabled=True,
            selected_provider=None,
            selected_model=None,
            content="DRY RUN: chamada LLM nao executada.",
            attempts=[
                ProviderAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    ok=False,
                    latency_ms=0.0,
                    tokens=0,
                    error="dry_run",
                )
                for candidate in candidates
            ],
            prompt_policy="contexto_minimo_sem_tokens_sem_topologia_automatica",
        )
    if not candidates:
        return LlmAssistResult(
            enabled=True,
            selected_provider=None,
            selected_model=None,
            content="Nenhum provedor LLM configurado para o prototipo local.",
            attempts=[],
            prompt_policy="contexto_minimo_sem_tokens_sem_topologia_automatica",
        )
    for candidate in candidates:
        try:
            content, tokens, latency_ms = call_chat_completion(
                candidate,
                messages,
                max_tokens=max_tokens,
            )
            attempts.append(
                ProviderAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    ok=True,
                    latency_ms=latency_ms,
                    tokens=tokens,
                )
            )
            return LlmAssistResult(
                enabled=True,
                selected_provider=candidate.provider,
                selected_model=candidate.model,
                content=content,
                attempts=attempts,
                prompt_policy="contexto_minimo_sem_tokens_sem_topologia_automatica",
            )
        except Exception as exc:
            attempts.append(
                ProviderAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    ok=False,
                    latency_ms=0.0,
                    tokens=0,
                    error=str(exc)[:500],
                )
            )
    return LlmAssistResult(
        enabled=True,
        selected_provider=None,
        selected_model=None,
        content="Todos os provedores LLM configurados falharam; manter saida offline como fonte principal.",
        attempts=attempts,
        prompt_policy="contexto_minimo_sem_tokens_sem_topologia_automatica",
    )


def render_markdown(result: LlmAssistResult) -> str:
    clean_content = "\n".join(line.rstrip() for line in result.content.strip().splitlines())
    lines = [
        "# Assistente LLM opcional - JaamSim Academic Assistant",
        "",
        "> Prototipo local. Nao versiona tokens e nao substitui o nucleo deterministico/offline.",
        "",
        "## Execucao",
        "",
        f"- Provedor selecionado: `{result.selected_provider or 'nenhum'}`",
        f"- Modelo selecionado: `{result.selected_model or 'nenhum'}`",
        f"- Politica de prompt: `{result.prompt_policy}`",
        "",
        "## Tentativas",
        "",
    ]
    if not result.attempts:
        lines.append("Nenhum provedor configurado.")
    for attempt in result.attempts:
        lines.extend(
            [
                f"- `{attempt.provider}` / `{attempt.model}`: {'OK' if attempt.ok else 'falhou'}",
                f"  - Tokens: `{attempt.tokens}`",
                f"  - Latencia ms: `{attempt.latency_ms:.0f}`",
            ]
        )
        if attempt.error:
            lines.append(f"  - Erro resumido: `{attempt.error}`")
    lines.extend(["", "## Resposta assistiva", "", clean_content, ""])
    return "\n".join(lines)


def write_assist_outputs(
    review_payload: dict[str, Any],
    output_dir: Path,
    *,
    model_id: str,
    provider_order: str | None = None,
    env_file: Path | None = None,
    operator_request: str | None = None,
    max_tokens: int = 700,
    dry_run: bool = False,
) -> tuple[Path, Path, LlmAssistResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = run_llm_assist(
        review_payload,
        provider_order=provider_order,
        env_file=env_file,
        operator_request=operator_request,
        max_tokens=max_tokens,
        dry_run=dry_run,
    )
    json_path = output_dir / f"{model_id}_llm_assist.json"
    markdown_path = output_dir / f"{model_id}_llm_assist.md"
    payload = {
        "prototype_only": True,
        "publication_policy": "tokens_locais_nao_publicar",
        "provider_status": provider_status(provider_order, env_file),
        "result": {
            **asdict(result),
            "attempts": [asdict(attempt) for attempt in result.attempts],
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, markdown_path, result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa assistente LLM opcional sobre um relatorio offline.")
    parser.add_argument("offline_review_json", nargs="?", type=Path, help="Arquivo *_offline_review.json.")
    parser.add_argument("--output-dir", type=Path, help="Diretorio de saida. Padrao: mesmo diretorio do relatorio.")
    parser.add_argument("--provider-order", help="Ranking/fallback, ex.: nvidia,cerebras,groq.")
    parser.add_argument("--env-file", type=Path, help="Arquivo .env local ignorado a carregar.")
    parser.add_argument("--request", help="Pedido do operador para a camada LLM.")
    parser.add_argument("--max-tokens", type=int, default=700, help="Limite de tokens da resposta.")
    parser.add_argument("--dry-run", action="store_true", help="Monta configuracao sem chamar provedores.")
    parser.add_argument("--status", action="store_true", help="Mostra apenas status redigido dos provedores.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.status:
        for item in provider_status(args.provider_order, args.env_file):
            configured = "sim" if item["configured"] else "nao"
            print(f"{item['rank']}. {item['provider']} | {item['api_key_env']}={configured} | model={item['model']}")
        return
    if not args.offline_review_json:
        raise SystemExit("Informe um arquivo *_offline_review.json ou use --status.")
    review_payload = json.loads(args.offline_review_json.read_text(encoding="utf-8"))
    output_dir = args.output_dir or args.offline_review_json.parent
    model_id = review_payload.get("analysis", {}).get("model_id") or args.offline_review_json.stem
    json_path, markdown_path, result = write_assist_outputs(
        review_payload,
        output_dir,
        model_id=model_id,
        provider_order=args.provider_order,
        env_file=args.env_file,
        operator_request=args.request,
        max_tokens=args.max_tokens,
        dry_run=args.dry_run,
    )
    print(f"LLM assist JSON: {json_path}")
    print(f"LLM assist Markdown: {markdown_path}")
    print(f"Provedor selecionado: {result.selected_provider or 'nenhum'}")


if __name__ == "__main__":
    main()
