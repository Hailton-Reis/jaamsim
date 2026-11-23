"""Local-only simulated-server tests; never load an actual GGUF or run llama.cpp."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

import local_llama_smoke as smoke

NAME = "synthetic-single-model"
PIN = hashlib.sha256(NAME.encode("utf-8")).hexdigest()


@contextmanager
def server(*, health=None, models=None, reply=None, redirect=False):
    logs = []
    health = {"status": "ok"} if health is None else health
    models = {"data": [{"id": NAME}]} if models is None else models
    reply = ({"model": NAME, "choices": [{
        "message": {"role": "assistant", "content": "JAAM_AI_SMOKE_OK"},
        "finish_reason": "stop",
    }], "usage": {"prompt_tokens": 20, "completion_tokens": 9, "total_tokens": 29}}
             if reply is None else reply)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            logs.append(("GET", self.path, None))
            self.send_response(302 if redirect else 200)
            if redirect:
                self.send_header("Location", "https://example.invalid/private")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if not redirect:
                self.wfile.write(json.dumps({
                    "/health": health, "/v1/models": models
                }.get(self.path, {})).encode("utf-8"))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            content = self.rfile.read(length)
            logs.append(("POST", self.path, json.loads(content)))
            self.send_response(302 if redirect else 200)
            if redirect:
                self.send_header("Location", "http://127.0.0.1:99/redirect")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if not redirect:
                self.wfile.write(json.dumps(reply).encode("utf-8"))

        def log_message(self, format, *args):
            return

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    task = threading.Thread(target=srv.serve_forever, daemon=True)
    task.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}", logs
    finally:
        srv.shutdown()
        srv.server_close()
        task.join(timeout=3)


def test_dry_run_makes_no_request():
    with server() as (url, log):
        result = smoke.smoke(url, PIN)
    assert result["status"] == "DRY_RUN_NO_REQUESTS"
    assert result["model_generation_calls"] == 0
    assert not log


def test_explicit_single_small_generation():
    with server() as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["status"] == "LOCAL_GENERATION_OBSERVED_UNATTESTED"
    assert result["inference_real"]
    assert result["response_text"] == "JAAM_AI_SMOKE_OK"
    assert result["expected_text_match"]
    assert result["prompt_tokens"] == 20
    assert result["completion_tokens"] == 9
    assert result["network_get_calls"] == 2
    assert result["network_post_calls"] == 1
    assert result["model_generation_calls"] == 1
    assert result["state_tool_calls"] == result["document_search_calls"] == 0
    assert not result["write_model"]
    assert [x[:2] for x in log] == [
        ("GET", "/health"), ("GET", "/v1/models"), ("POST", "/v1/chat/completions")]
    body = log[-1][2]
    assert body["max_tokens"] == 48
    assert body["temperature"] == 0
    assert body["stream"] is False
    assert body["tools"] == []
    assert body["model"] == NAME
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_mismatched_pin_prevents_post():
    with server() as (url, log):
        result = smoke.smoke(url, "a" * 64, execute=True)
    assert result["status"] == "LOCAL_SMOKE_FAILED"
    assert result["failure_code"] == "model_identity_not_pinned"
    assert result["network_post_calls"] == 0
    assert [x[0] for x in log] == ["GET", "GET"]


@pytest.mark.parametrize("health", [{"status": "loading"}, {"status": "failed"}, [], {}])
def test_health_failure_prevents_list_and_post(health):
    with server(health=health) as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["status"] == "LOCAL_SMOKE_FAILED"
    assert result["network_get_calls"] == 1
    assert result["network_post_calls"] == 0
    assert [x[1] for x in log] == ["/health"]


def test_multiple_advertised_models_rejected():
    with server(models={"data": [{"id": NAME}, {"id": "other"}]}) as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["failure_code"] == "require_single_model"
    assert len(log) == 2


def test_untrusted_tool_call_response_rejected():
    reply = {
        "model": NAME,
        "choices": [{"message": {"role": "assistant", "content": "text",
                                  "tool_calls": [{"function": {"name": "write_model"}}]}}],
    }
    with server(reply=reply) as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["status"] == "LOCAL_SMOKE_FAILED"
    assert result["failure_code"] == "assistant_text_invalid_or_tool_call"
    assert len(log) == 3
    assert result["state_tool_calls"] == 0


def test_wrong_response_model_rejected():
    reply = {"model": "other", "choices": [
        {"message": {"role": "assistant", "content": "JAAM_AI_SMOKE_OK"}}]}
    with server(reply=reply) as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["failure_code"] == "response_model_mismatch"


def test_reply_without_text_fails_closed():
    with server(reply={"model": NAME, "choices": [
        {"message": {"role": "assistant", "content": None}}]}) as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["failure_code"] == "assistant_text_invalid_or_tool_call"


def test_health_redirect_is_never_followed():
    with server(redirect=True) as (url, log):
        result = smoke.smoke(url, PIN, execute=True)
    assert result["status"] == "LOCAL_SMOKE_FAILED"
    assert len(log) == 1


@pytest.mark.parametrize("endpoint", [
    "http://localhost:9999", "http://8.8.8.8:9999", "https://127.0.0.1:9931",
    "http://127.0.0.1:9931/path",
])
def test_non_loopback_endpoints_cannot_be_used(endpoint):
    with pytest.raises(ValueError):
        smoke.smoke(endpoint, PIN, execute=True)


def test_invalid_or_missing_pin_denied():
    with pytest.raises(ValueError):
        smoke.smoke("http://127.0.0.1:9931", "x", execute=True)


def test_cli_never_executes_without_flag(capsys):
    assert smoke.main(["--expected-model-id-sha256", PIN]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DRY_RUN_NO_REQUESTS"
    assert result["model_generation_calls"] == 0
