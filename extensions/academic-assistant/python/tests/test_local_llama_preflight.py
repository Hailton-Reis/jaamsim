"""Synthetic-only local llama.cpp preflight tests (no model downloaded or executed)."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

import local_llama_preflight as pre


@contextmanager
def fake_server(*, health=None, models=None, statuses=None):
    logs = []
    health = health if health is not None else {"status": "ok"}
    models = models if models is not None else {
        "object": "list", "data": [{"id": "synthetic-gguf", "object": "model"}]}
    statuses = statuses or {}
    outputs = {"/health": health, "/v1/models": models}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            logs.append(("GET", self.path))
            status = statuses.get(self.path, 200)
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "https://example.com/forbidden")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if status != 302:
                value = outputs.get(self.path, {})
                raw = (value if isinstance(value, bytes) else
                       json.dumps(value).encode("utf-8"))
                self.wfile.write(raw)

        def do_POST(self):
            logs.append(("POST", self.path))
            self.send_response(405)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", logs
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("url", [
    "http://localhost:9931", "http://0.0.0.0:9931",
    "http://192.168.1.1:8080", "https://127.0.0.1:9931",
    "http://127.0.0.1", "http://127.0.0.1:0",
    "http://127.0.0.1:65536", "http://127.0.0.1:abc",
    "http://me@127.0.0.1:9931", "http://127.0.0.1:9931/v1",
    "http://127.0.0.1:9931?token=a", "http://127.0.0.1:9931#fragment",
    "http://127.0.0.1:9931@external.example:80",
    "file:///tmp/local-model", "http://[::1]:9931",
])
def test_forbidden_endpoints(url):
    with pytest.raises(ValueError):
        pre.endpoint_port(url)


def test_valid_default_endpoint():
    assert pre.endpoint_port(pre.DEFAULT_ENDPOINT) == 9931


def test_no_probe_makes_no_requests():
    result = pre.inspect()
    assert result["status"] == "PLAN_ONLY_NO_NETWORK"
    assert result["network_calls"] == 0
    assert result["model_generation_calls"] == 0
    assert result["science_evidence"] == "NONE"
    assert not result["server_discovered"]


def test_good_local_api_discovery_only():
    with fake_server() as (url, logs):
        result = pre.inspect(url, probe=True)
    assert result["status"] == "API_DISCOVERED_NO_GENERATION"
    assert result["server_discovered"]
    assert result["network_calls"] == 2
    assert result["model_list_count"] == 1
    assert result["model_id_sha256"] == [
        hashlib.sha256(b"synthetic-gguf").hexdigest()]
    assert result["model_generation_calls"] == result["state_tool_calls"] == 0
    assert result["write_model"] is False
    assert logs == [("GET", "/health"), ("GET", "/v1/models")]


@pytest.mark.parametrize("health", [
    {"status": "loading"}, {"error": "unavailable"}, [], "ok", {},
])
def test_health_fail_closed(health):
    with fake_server(health=health) as (url, logs):
        result = pre.inspect(url, probe=True)
    assert result["status"] == "API_DISCOVERY_FAILED"
    assert logs == [("GET", "/health")]


@pytest.mark.parametrize("models", [
    {}, [], {"data": "text"}, {"data": [{"name": "missing-id"}]},
    {"data": [{"id": ""}]}, {"data": [{"id": "x"}] * 9},
])
def test_model_list_fail_closed(models):
    with fake_server(models=models) as (url, logs):
        result = pre.inspect(url, probe=True)
    assert result["status"] == "API_DISCOVERY_FAILED"
    assert logs == [("GET", "/health"), ("GET", "/v1/models")]


def test_server_unavailable_fails_without_external_fallback():
    with fake_server() as (url, logs):
        port = int(url.rsplit(":", 1)[1])
    result = pre.inspect(f"http://127.0.0.1:{port}", probe=True)
    assert result["status"] == "API_DISCOVERY_FAILED"
    assert result["model_generation_calls"] == 0


def test_redirect_must_not_be_followed():
    with fake_server(statuses={"/health": 302}) as (url, logs):
        result = pre.inspect(url, probe=True)
    assert result["status"] == "API_DISCOVERY_FAILED"
    assert logs == [("GET", "/health")]


def test_oversized_health_response_rejected():
    with fake_server(health=b"x" * (pre.MAX_RESPONSE_BYTES + 1)) as (url, logs):
        result = pre.inspect(url, probe=True)
    assert result["status"] == "API_DISCOVERY_FAILED"
    assert result["model_generation_calls"] == 0


def test_invalid_json_response_rejected():
    with fake_server(models=b"not json") as (url, logs):
        result = pre.inspect(url, probe=True)
    assert result["status"] == "API_DISCOVERY_FAILED"


def test_unlisted_api_path_denied():
    with pytest.raises(ValueError, match="path_not_allowed"):
        pre.get_json("http://127.0.0.1:9931", "/v1/chat/completions")


def test_valid_gguf_metadata_and_pin(tmp_path):
    model = tmp_path / "synthetic.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 8)
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    identity = pre.gguf_identity(str(model), digest)
    assert identity["gguf_examined"] is True
    assert identity["gguf_pinned"] is True
    assert identity["gguf_sha256"] == digest
    assert pre.gguf_identity(str(model), "f" * 64)["gguf_pinned"] is False


def test_fake_gguf_magic_rejected(tmp_path):
    model = tmp_path / "bad.gguf"
    model.write_bytes(b"FAIL" + b"\x00" * 8)
    with pytest.raises(ValueError, match="gguf_magic_invalid"):
        pre.gguf_identity(str(model), None)


def test_model_symlink_rejected(tmp_path):
    model = tmp_path / "real.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 8)
    link = tmp_path / "alias.gguf"
    try:
        link.symlink_to(model)
    except (OSError, NotImplementedError):
        pytest.skip("OS denies creation of test symlinks")
    with pytest.raises(ValueError, match="gguf_missing_or_symlink"):
        pre.gguf_identity(str(link), None)


def test_bad_pin_requires_model_file():
    with pytest.raises(ValueError, match="invalid_model_pin"):
        pre.gguf_identity(None, "a" * 64)
    with pytest.raises(ValueError, match="invalid_model_pin"):
        pre.gguf_identity("model.gguf", "NOT_A_SHA256")


def test_cli_dry_run_cannot_generate(capsys):
    assert pre.main([]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "PLAN_ONLY_NO_NETWORK"
    assert data["model_generation_calls"] == 0


def test_cli_non_local_host_denied(capsys):
    assert pre.main(["--endpoint", "http://example.com:8080", "--probe"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "INVALID_PREFLIGHT_REQUEST"
    assert data["model_generation_calls"] == 0
