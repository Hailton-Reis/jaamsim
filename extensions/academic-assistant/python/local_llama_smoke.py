"""Opt-in first local text generation smoke for an already running llama.cpp server.

No JaamSim state, RCL tools, RAG, model writes, or scientific conclusions.
No downloads; localhost literal IPv4 only; standard library, Python >=3.11.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Any

import local_llama_preflight as guard

SCHEMA = "jaam.ai.local_llama_smoke.v1"
PROMPT = "Teste técnico isolado JAAM-AI. Responda somente: JAAM_AI_SMOKE_OK"
SYSTEM = "Teste de infraestrutura offline. Não acesse ferramentas, arquivos ou fontes externas."
MAX_TOKENS = 48
MAX_OUTPUT_BYTES = 128 * 1024
MAX_ANSWER_CHARS = 4096
VALID_PIN = guard.SHA256_RE


def sha(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def smoke(endpoint: str, expected_model_id_sha256: str,
          *, execute: bool = False, timeout: float = 45.0) -> dict[str, Any]:
    guard.endpoint_port(endpoint)
    if not VALID_PIN.fullmatch(expected_model_id_sha256):
        raise ValueError("invalid_model_id_pin")
    if not 0.5 <= timeout <= 90:
        raise ValueError("invalid_timeout")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "gate": "G0_G2_PENDING_ENGINEERING_ONLY",
        "scientific_authorization": False,
        "status": "DRY_RUN_NO_REQUESTS",
        "endpoint": endpoint,
        "model_id_sha256_expected": expected_model_id_sha256,
        "model_id_sha256_observed": None,
        "prompt_sha256": sha(PROMPT),
        "system_prompt_sha256": sha(SYSTEM),
        "network_get_calls": 0,
        "network_post_calls": 0,
        "model_generation_calls": 0,
        "state_tool_calls": 0,
        "document_search_calls": 0,
        "write_model": False,
        "max_output_tokens_requested": MAX_TOKENS,
        "model_gguf_sha256_verified": False,
        "whole_system_8gb_tested": False,
        "inference_real": False,
        "benchmark_claim": "NONE",
    }
    if not execute:
        return result
    start = time.monotonic()
    try:
        result["network_get_calls"] += 1
        health = guard.get_json(endpoint, "/health", timeout=2.0)
        if not isinstance(health, dict) or health.get("status") not in ("ok", "ready"):
            raise ValueError("health_not_ready")
        result["network_get_calls"] += 1
        models = guard.get_json(endpoint, "/v1/models", timeout=2.0)
        if not isinstance(models, dict) or not isinstance(models.get("data"), list):
            raise ValueError("models_invalid")
        items = models["data"]
        # Require exactly one advertised model. No auto-selection or fallback.
        if len(items) != 1 or not isinstance(items[0], dict) or not isinstance(items[0].get("id"), str):
            raise ValueError("require_single_model")
        model_name = items[0]["id"]
        if not 0 < len(model_name) <= 255:
            raise ValueError("model_id_invalid")
        result["model_id_sha256_observed"] = sha(model_name)
        if result["model_id_sha256_observed"] != expected_model_id_sha256:
            raise ValueError("model_identity_not_pinned")
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT},
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
            "stream": False,
            "tools": [],
        }
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            endpoint + "/v1/chat/completions",
            data=encoded,
            headers={"Content-Type": "application/json",
                     "Accept": "application/json", "Connection": "close"},
            method="POST",
        )
        # No inherited proxy, credentials, redirects, network fallback, or arbitrary prompts.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), guard.NoRedirect())
        result["network_post_calls"] += 1
        result["model_generation_calls"] += 1
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError("unexpected_http_status")
            raw = response.read(MAX_OUTPUT_BYTES + 1)
        if len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError("response_too_large")
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("choices"), list) or len(parsed["choices"]) != 1:
            raise ValueError("choices_invalid")
        item = parsed["choices"][0]
        if not isinstance(item, dict) or not isinstance(item.get("message"), dict):
            raise ValueError("message_invalid")
        message = item["message"]
        text = message.get("content")
        if (message.get("role") != "assistant" or not isinstance(text, str)
                or not 0 < len(text) <= MAX_ANSWER_CHARS
                or message.get("tool_calls") or message.get("function_call")):
            raise ValueError("assistant_text_invalid_or_tool_call")
        # Observed model may be absent in some compatible servers; do not silently accept mismatch.
        if "model" in parsed and parsed["model"] != model_name:
            raise ValueError("response_model_mismatch")
        result.update({
            "status": "LOCAL_GENERATION_OBSERVED_UNATTESTED",
            "inference_real": True,
            "response_text": text,
            "response_sha256": sha(text),
            "expected_text_match": text.strip() == "JAAM_AI_SMOKE_OK",
            "finish_reason": item.get("finish_reason") if isinstance(item.get("finish_reason"), str) else None,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        })
        usage = parsed.get("usage")
        if isinstance(usage, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if type(value) is int and 0 <= value <= 1000000:
                    result[key] = value
    except (OSError, urllib.error.URLError, ValueError, UnicodeError,
            json.JSONDecodeError, TimeoutError) as exc:
        result["status"] = "LOCAL_SMOKE_FAILED"
        result["failure_class"] = type(exc).__name__
        if type(exc) is ValueError and str(exc) in (
            "health_not_ready", "models_invalid", "require_single_model",
            "model_id_invalid", "model_identity_not_pinned",
            "response_too_large", "choices_invalid", "message_invalid",
            "assistant_text_invalid_or_tool_call", "response_model_mismatch"):
            result["failure_code"] = str(exc)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in llama.cpp localhost generation smoke: engineering only.")
    parser.add_argument("--endpoint", default=guard.DEFAULT_ENDPOINT)
    parser.add_argument("--expected-model-id-sha256", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly authorize exactly one small local generation request")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args(argv)
    try:
        data = smoke(args.endpoint, args.expected_model_id_sha256,
                     execute=args.execute, timeout=args.timeout_seconds)
    except ValueError:
        data = {
            "schema": SCHEMA, "status": "INVALID_SMOKE_REQUEST",
            "model_generation_calls": 0, "write_model": False,
        }
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return 0 if data["status"] in (
        "DRY_RUN_NO_REQUESTS", "LOCAL_GENERATION_OBSERVED_UNATTESTED") else 3


if __name__ == "__main__":
    raise SystemExit(main())
