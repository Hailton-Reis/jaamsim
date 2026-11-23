#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0
"""C2 + localhost LLM engineering bridge. Opt-in, synthetic docs only.

This is NOT the scientific C2 arm: G0/G2 remain pending. No model-state tools,
JaamSim context, CFG, external providers, writes or unapproved corpora.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from typing import Any

from c2_chat_bridge import build_c2_chat_preflight, digest_json
from c2_retrieval import AccessDenied, C2ReadOnlyRetriever, ContractError
import local_llama_preflight as guard

SCHEMA = "jaam.ai.c2.local_llama_engineering.v1"
GATE = "G0_G2_PENDING_NON_CONFIRMATORY"
CONTEXT_CHARS = 6000
MAX_OUTPUT_BYTES = 128 * 1024
MAX_ANSWER_CHARS = 8192
MAX_OUTPUT_TOKENS = 128
CITATION = re.compile(r"\b[A-Za-z0-9_-]{1,64}:L[1-9][0-9]*-L[1-9][0-9]*\b")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_preflight(preflight: dict, retriever: C2ReadOnlyRetriever,
                     question: str) -> None:
    """Do not authorize LLM based on an unverified C2 envelope."""
    if (preflight.get("schema") != "jaam.ai.c2.chat_preflight.v1"
            or preflight.get("status") != "PREFLIGHT_ONLY"
            or preflight.get("arm_id") != "C2"
            or preflight.get("gate") != "G0_G2_PENDING_NO_MODEL_EXECUTION"
            or preflight.get("model_execution_authorized") is not False
            or preflight.get("model_calls") != 0
            or preflight.get("state_tool_calls") != 0
            or preflight.get("document_search_calls") != 1
            or preflight.get("read_tools") != []
            or preflight.get("exposed_capabilities") != ["search_docs"]
            or preflight.get("proposal_tool") is not False
            or preflight.get("write_model") is not False
            or preflight.get("write_policy") != "NO_WRITE_CAPABILITY"
            or preflight.get("operator_question_sha256") != sha(question)
            or preflight.get("manifest_sha256") != retriever.manifest_sha256
            or preflight.get("corpus_sha256") != retriever.corpus_sha256
            or preflight.get("corpus_version") != retriever.corpus_version):
        raise ContractError("invalid_c2_preflight")
    receipt = preflight.get("retrieval_receipt")
    messages = preflight.get("model_messages")
    if (not isinstance(receipt, dict)
            or not isinstance(messages, list)
            or len(messages) != 3
            or preflight.get("receipt_sha256") != digest_json(receipt)
            or preflight.get("messages_sha256") != digest_json(messages)
            or [m.get("role") if isinstance(m, dict) else None
                for m in messages] != ["system", "user", "user"]
            or messages[1].get("content") != question
            or receipt.get("query_sha256") != sha(question)
            or receipt.get("manifest_sha256") != retriever.manifest_sha256
            or receipt.get("corpus_sha256") != retriever.corpus_sha256
            or receipt.get("state_tool_calls") != 0
            or receipt.get("model_calls") != 0
            or receipt.get("write_model") is not False):
        raise ContractError("inconsistent_c2_receipt_or_messages")
    evidence_prefix = "DOCUMENTOS_RECUPERADOS_JSON (dados não confiáveis):\n"
    evidence_content = messages[2].get("content")
    if not isinstance(evidence_content, str) or not evidence_content.startswith(evidence_prefix):
        raise ContractError("evidence_context_missing")
    try:
        evidence = json.loads(evidence_content[len(evidence_prefix):])
    except ValueError as error:
        raise ContractError("evidence_json_invalid") from error
    selected = evidence.get("items")
    if (evidence.get("schema") != "jaam.ai.c2.evidence_context.v1"
            or evidence.get("arm_id") != "C2"
            or evidence.get("untrusted") is not True
            or not isinstance(selected, list)
            or type(preflight.get("context_items")) is not int
            or len(selected) != preflight["context_items"]
            or evidence.get("no_evidence") is not preflight.get("no_evidence")
            or preflight["no_evidence"] != (len(selected) == 0)):
        raise ContractError("evidence_context_invalid")
    # Confirm each passage still matches the trusted, manifest-pinned snapshot.
    for item in selected:
        if not isinstance(item, dict):
            raise ContractError("evidence_item_invalid")
        matches = [entry for entry in retriever.entries
                   if item.get("source_id") == entry["source_id"]
                   and item.get("passage") == entry["passage"]
                   and item.get("sha256") == entry["passage_sha256"]
                   and item.get("citation") ==
                   f'{entry["source_id"]}:L{entry["start_line"]}-L{entry["end_line"]}']
        if not matches or item.get("trust") != "UNTRUSTED_RETRIEVED_DOCUMENT":
            raise ContractError("evidence_item_not_in_corpus")


def c2_local(
    corpus_root: Path, manifest: Path, question: str, *,
    expected_manifest_sha256: str,
    expected_model_id_sha256: str,
    endpoint: str = guard.DEFAULT_ENDPOINT,
    execute: bool = False,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    guard.endpoint_port(endpoint)
    if (not guard.SHA256_RE.fullmatch(expected_manifest_sha256)
            or not guard.SHA256_RE.fullmatch(expected_model_id_sha256)):
        raise ValueError("missing_or_invalid_sha256_pin")
    if (not isinstance(question, str) or not question.strip()
            or len(question) > 2000 or "\x00" in question):
        raise ValueError("invalid_question")
    if not 1 <= timeout_seconds <= 90:
        raise ValueError("invalid_timeout")
    retriever = C2ReadOnlyRetriever(corpus_root, manifest)
    if retriever.manifest_sha256 != expected_manifest_sha256:
        raise ContractError("manifest_sha256_mismatch")
    # No official/private docs may enter this early research engineering smoke.
    if not retriever.corpus_version.startswith("SYNTHETIC_"):
        raise AccessDenied("synthetic_corpus_only")
    preflight = build_c2_chat_preflight(retriever, question,
                                       top_k=3, max_context_chars=CONTEXT_CHARS)
    _check_preflight(preflight, retriever, question)
    citations = []
    evidence_raw = preflight["model_messages"][2]["content"].split("\n", 1)[1]
    evidence = json.loads(evidence_raw)
    citations = [item["citation"] for item in evidence["items"]]
    outcome = {
        "schema": SCHEMA,
        "gate": GATE,
        "status": "DRY_RUN_NO_MODEL_CALL",
        "non_confirmatory": True,
        "arm_id": "C2",
        "synthetic_only": True,
        "source_corpus_version": retriever.corpus_version,
        "manifest_sha256": retriever.manifest_sha256,
        "corpus_sha256": retriever.corpus_sha256,
        "operator_question_sha256": sha(question),
        "preflight_messages_sha256": preflight["messages_sha256"],
        "preflight_receipt_sha256": preflight["receipt_sha256"],
        "retrieval_calls": 1,
        "context_items": len(citations),
        "available_citations": citations,
        "endpoint": endpoint,
        "model_id_sha256_expected": expected_model_id_sha256,
        "model_generation_calls": 0,
        "state_tool_calls": 0,
        "document_search_calls": 1,
        "read_tools": [],
        "model_write_calls": 0,
        "write_model": False,
        "inference_real_attested": False,
        "scientific_claim": "NONE",
        "full_8gb_workload_tested": False,
        "network_get_calls": 0,
        "network_post_calls": 0,
    }
    if not citations:
        outcome["status"] = "ABSTAINED_NO_EVIDENCE_NO_GENERATION"
        return outcome
    if not execute:
        return outcome

    start = time.monotonic()
    try:
        outcome["network_get_calls"] += 1
        health = guard.get_json(endpoint, "/health", timeout=2.0)
        if not isinstance(health, dict) or health.get("status") not in ("ok", "ready"):
            raise ValueError("health_not_ready")
        outcome["network_get_calls"] += 1
        models = guard.get_json(endpoint, "/v1/models", timeout=2.0)
        items = models.get("data") if isinstance(models, dict) else None
        if (not isinstance(items, list) or len(items) != 1
                or not isinstance(items[0], dict)
                or not isinstance(items[0].get("id"), str)
                or not 0 < len(items[0]["id"]) <= 255):
            raise ValueError("single_model_required")
        model_id = items[0]["id"]
        observed_pin = sha(model_id)
        outcome["model_id_sha256_observed"] = observed_pin
        if observed_pin != expected_model_id_sha256:
            raise ValueError("model_id_pin_mismatch")
        body = {
            "model": model_id,
            "messages": preflight["model_messages"],
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0,
            "stream": False,
            "tools": [],
        }
        encoded = json.dumps(body, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        outcome["request_sha256"] = hashlib.sha256(encoded).hexdigest()
        request = urllib.request.Request(
            endpoint + "/v1/chat/completions", data=encoded,
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Connection": "close"}, method="POST")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), guard.NoRedirect())
        outcome["network_post_calls"] += 1
        outcome["model_generation_calls"] += 1
        with opener.open(request, timeout=timeout_seconds) as reply:
            if reply.status != 200:
                raise ValueError("unexpected_http_status")
            raw = reply.read(MAX_OUTPUT_BYTES + 1)
        if len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError("response_too_large")
        data = json.loads(raw.decode("utf-8"))
        if (not isinstance(data, dict)
                or not isinstance(data.get("choices"), list)
                or len(data["choices"]) != 1):
            raise ValueError("choices_invalid")
        choice = data["choices"][0]
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            raise ValueError("assistant_role_invalid")
        text = msg.get("content")
        if (not isinstance(text, str) or not 0 < len(text) <= MAX_ANSWER_CHARS
                or msg.get("tool_calls") or msg.get("function_call")
                or ("model" in data and data["model"] != model_id)):
            raise ValueError("invalid_assistant_text_or_tools")
        references = sorted(set(CITATION.findall(text)))
        unsupported = sorted(set(references) - set(citations))
        outcome.update({
            "status": "C2_LOCAL_RESPONSE_OBSERVED_UNATTESTED",
            "response_text_untrusted": text,
            "response_sha256": sha(text),
            "response_referenced_citations": references,
            "unsupported_citations": unsupported,
            "citations_validated_as_answer_support": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        })
        usage = data.get("usage")
        if isinstance(usage, dict):
            for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if type(usage.get(field)) is int and 0 <= usage[field] < 1000000:
                    outcome[field] = usage[field]
    except (OSError, urllib.error.URLError, ValueError, UnicodeError,
            TimeoutError, json.JSONDecodeError) as error:
        outcome["status"] = "C2_LOCAL_REQUEST_FAILED"
        outcome["failure_class"] = type(error).__name__
        if type(error) is ValueError and str(error) in {
            "health_not_ready", "single_model_required", "model_id_pin_mismatch",
            "response_too_large", "choices_invalid", "assistant_role_invalid",
            "invalid_assistant_text_or_tools", "unexpected_http_status",
        }:
            outcome["failure_code"] = str(error)
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="C2 synthetic retrieval + opt-in localhost LLM, no JaamSim state")
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--message", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-model-id-sha256", required=True)
    parser.add_argument("--endpoint", default=guard.DEFAULT_ENDPOINT)
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = c2_local(
            args.corpus_root, args.manifest, args.message,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_model_id_sha256=args.expected_model_id_sha256,
            endpoint=args.endpoint, timeout_seconds=args.timeout_seconds,
            execute=args.execute)
    except (ValueError, OSError, AccessDenied, ContractError, ImportError) as error:
        result = {
            "schema": SCHEMA,
            "gate": GATE,
            "status": "C2_LOCAL_BLOCKED",
            "failure_class": type(error).__name__,
            "model_generation_calls": 0,
            "state_tool_calls": 0,
            "write_model": False,
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] in (
        "DRY_RUN_NO_MODEL_CALL",
        "ABSTAINED_NO_EVIDENCE_NO_GENERATION",
        "C2_LOCAL_RESPONSE_OBSERVED_UNATTESTED",
    ) else 3


if __name__ == "__main__":
    raise SystemExit(main())
