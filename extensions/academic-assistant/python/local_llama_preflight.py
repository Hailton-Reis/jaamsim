"""JAAM-AI: localhost-only llama.cpp discovery; no inference, LLM access or model changes.

Candidate engineering preflight. The scientific G0/G2 gates remain closed.
Python 3.11+, standard library only. Do not treat this as model validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SCHEMA = "jaam.ai.local_llama_preflight.v1"
GATE = "G0_G2_PENDING_NO_MODEL_INFERENCE"
MAX_RESPONSE_BYTES = 64 * 1024
DEFAULT_ENDPOINT = "http://127.0.0.1:9931"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def endpoint_port(endpoint: str) -> int:
    """Only literal IPv4 loopback with explicit port. No proxy or DNS resolution."""
    if not isinstance(endpoint, str) or len(endpoint) > 80:
        raise ValueError("endpoint_invalid")
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint_invalid") from exc
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment
            or port is None or not 1 <= port <= 65535
            or parsed.netloc != f"127.0.0.1:{port}"):
        raise ValueError("endpoint_must_be_literal_loopback_ipv4")
    return port


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def get_json(endpoint: str, path: str, *, timeout: float = 2.0) -> object:
    endpoint_port(endpoint)
    if path not in ("/health", "/v1/models"):
        raise ValueError("path_not_allowed")
    request = urllib.request.Request(endpoint + path, headers={
        "Accept": "application/json",
        "Connection": "close",
    }, method="GET")
    # No inherited HTTP(S) proxies, cookies, redirects, userinfo, or auth headers.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        if response.getcode() != 200:
            raise ValueError("unexpected_http_status")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("response_too_large")
    return json.loads(data.decode("utf-8"))


def gguf_identity(file_path: str | None, expected_sha256: str | None) -> dict:
    if expected_sha256 and (not file_path or not SHA256_RE.fullmatch(expected_sha256)):
        raise ValueError("invalid_model_pin")
    if not file_path:
        return {"gguf_examined": False, "gguf_pinned": False}
    path = Path(file_path)
    if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
        raise ValueError("gguf_missing_or_symlink")
    length = path.stat().st_size
    if length < 8 or length > 8 * 1024**3:
        raise ValueError("gguf_size_invalid")
    digest = hashlib.sha256()
    with path.open("rb") as infile:
        if infile.read(4) != b"GGUF":
            raise ValueError("gguf_magic_invalid")
        infile.seek(0)
        for chunk in iter(lambda: infile.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = digest.hexdigest()
    return {
        "gguf_examined": True,
        "gguf_pinned": bool(expected_sha256 and checksum == expected_sha256),
        "gguf_sha256": checksum,
        "gguf_size_bytes": length,
        "expected_pin_matched": checksum == expected_sha256 if expected_sha256 else None,
    }


def inspect(endpoint: str = DEFAULT_ENDPOINT, *, probe: bool = False,
            gguf_file: str | None = None, expected_gguf_sha256: str | None = None) -> dict:
    """Does not generate text, call tools, send prompts, or read JaamSim state."""
    endpoint_port(endpoint)
    model = gguf_identity(gguf_file, expected_gguf_sha256)
    result = {
        "schema": SCHEMA,
        "gate": GATE,
        "status": "PLAN_ONLY_NO_NETWORK",
        "local_endpoint": endpoint,
        "probe_requested": bool(probe),
        "network_calls": 0,
        "model_generation_calls": 0,
        "state_tool_calls": 0,
        "write_model": False,
        "server_discovered": False,
        "model_identity": model,
        "model_list_count": None,
        "model_id_sha256": [],
        "science_evidence": "NONE",
        "full_8gb_workload_tested": False,
    }
    if not probe:
        return result
    result["network_calls"] = 2
    try:
        health = get_json(endpoint, "/health")
        models = get_json(endpoint, "/v1/models")
        if not isinstance(health, dict) or health.get("status") not in ("ok", "ready"):
            raise ValueError("health_not_ready")
        if not isinstance(models, dict) or not isinstance(models.get("data"), list):
            raise ValueError("model_list_invalid")
        items = models["data"]
        if len(items) > 8 or not all(isinstance(x, dict) and
                                    isinstance(x.get("id"), str) and
                                    0 < len(x["id"]) < 256 for x in items):
            raise ValueError("model_list_invalid")
        result["server_discovered"] = True
        result["model_list_count"] = len(items)
        result["model_id_sha256"] = [
            hashlib.sha256(item["id"].encode("utf-8")).hexdigest() for item in items
        ]
        result["status"] = "API_DISCOVERED_NO_GENERATION"
    except (ValueError, UnicodeError, json.JSONDecodeError,
            OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        result["status"] = "API_DISCOVERY_FAILED"
        # Never emit raw exception strings: they may contain model paths/URLs.
        result["failure_class"] = type(exc).__name__
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe localhost llama.cpp preflight, without inference.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--probe", action="store_true", help="GET localhost /health and /v1/models only")
    parser.add_argument("--gguf-file", help="optional local GGUF for streaming SHA-256, no model load")
    parser.add_argument("--expected-gguf-sha256", help="lowercase 64 hex pin")
    args = parser.parse_args(argv)
    try:
        payload = inspect(args.endpoint, probe=args.probe,
                          gguf_file=args.gguf_file,
                          expected_gguf_sha256=args.expected_gguf_sha256)
    except ValueError as exc:
        # Avoid any untrusted path or URL in an error response.
        payload = {"schema": SCHEMA, "status": "INVALID_PREFLIGHT_REQUEST",
                   "failure_code": str(exc), "model_generation_calls": 0}
        print(json.dumps(payload, sort_keys=True))
        return 2
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0 if payload["status"] != "API_DISCOVERY_FAILED" else 3


if __name__ == "__main__":
    sys.exit(main())
