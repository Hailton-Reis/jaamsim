"""No real GGUF/llama.cpp is downloaded or executed in these tests."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import local_llama_lab as lab
from test_local_llama_smoke import server, PIN


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def pinned_files(tmp_path):
    server_bin = tmp_path / ("llama-server.exe" if os.name == "nt" else "llama-server")
    server_bin.write_bytes(b"synthetic-exe-for-hash-tests-not-an-executable")
    server_bin.chmod(0o755)
    model = tmp_path / "synthetic.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 32)
    return str(server_bin), sha(server_bin.read_bytes()), str(model), sha(model.read_bytes())


def test_dry_run_checks_pins_and_makes_no_files(pinned_files, tmp_path):
    server_bin, binpin, model, modelpin = pinned_files
    evidence = tmp_path / "evidence"
    result = lab.lab(server_bin, binpin, model, modelpin, evidence_dir=str(evidence))
    assert result["status"] == "DRY_RUN_VERIFIED_FILES"
    assert not result["binary_launched"]
    assert result["model_generation_calls"] == 0
    assert result["write_model"] is False
    assert result["whole_system_8gb_validated"] is False
    assert not evidence.exists()


def test_different_binary_hash_rejected_before_launch(pinned_files):
    server_bin, binpin, model, modelpin = pinned_files
    with pytest.raises(ValueError, match="binary_sha256_mismatch"):
        lab.lab(server_bin, "a" * 64, model, modelpin, execute=True)


def test_different_model_hash_rejected_before_launch(pinned_files):
    server_bin, binpin, model, modelpin = pinned_files
    with pytest.raises(ValueError, match="gguf_sha256_mismatch"):
        lab.lab(server_bin, binpin, model, "a" * 64, execute=True)


@pytest.mark.parametrize("port", [0, 22, 80, 9931.0, 65536, -1])
def test_unsafe_ports_rejected(pinned_files, port):
    with pytest.raises(ValueError, match="unsafe_port"):
        lab.lab(*pinned_files, port=port)


def test_requires_evidence_directory_only_when_executing(pinned_files):
    with pytest.raises(ValueError, match="evidence_dir_required"):
        lab.lab(*pinned_files, execute=True)


def test_symlink_binary_rejected(pinned_files, tmp_path):
    server_bin, binpin, model, modelpin = pinned_files
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(server_bin)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="binary_not_regular_or_symlink"):
        lab.lab(str(alias), binpin, model, modelpin)


def test_invalid_gguf_magic_rejected(pinned_files):
    server_bin, binpin, model, modelpin = pinned_files
    Path(model).write_bytes(b"NOT_" + b"\0" * 32)
    with pytest.raises(ValueError, match="gguf_magic_invalid"):
        lab.lab(server_bin, binpin, model, modelpin)


def test_port_collision_rejected(pinned_files, tmp_path):
    import socket
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        with pytest.raises(OSError):
            lab.lab(*pinned_files, execute=True, port=port,
                    evidence_dir=str(tmp_path))


def test_environment_does_not_forward_api_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-secret")
    monkeypatch.setenv("GROQ_API_KEY", "fake-secret")
    monkeypatch.setenv("LLAMA_ARG_HOST", "0.0.0.0")
    monkeypatch.setenv("PATH", "minimal")
    env = lab.safe_environment()
    assert env["PATH"] == "minimal"
    assert "OPENAI_API_KEY" not in env
    assert "GROQ_API_KEY" not in env
    assert "LLAMA_ARG_HOST" not in env


def test_rss_reader_never_invents_numbers():
    assert lab.read_rss_bytes(999999999) is None
    memory = lab.read_system_ram_bytes()
    assert memory is None or (memory[0] > 0 and memory[0] >= memory[1] >= 0)


def test_file_memory_meter_has_explicit_scope():
    meter = lab.Sampler(os.getpid(), interval=0.02)
    meter.start()
    meter.stop_event.wait(0.05)
    data = meter.stop()
    assert data["samples"] >= 1
    assert "no JVM/JaamSim" in data["scope"]
    if data["server_process_rss_peak_mib"] is not None:
        assert data["server_process_rss_peak_mib"] > 0


def test_managed_launch_synthetic_http_and_single_post(monkeypatch, pinned_files, tmp_path):
    # The CI runs a fake HTTP server. Popen is replaced: it NEVER launches real llama.cpp.
    class FakeProcess:
        pid = os.getpid()
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): self.returncode = -15
        def wait(self, timeout=None):
            if self.returncode is None:
                self.returncode = 0
            return self.returncode
        def kill(self): self.returncode = -9

    commands = []
    def fake_popen(argv, **kwargs):
        commands.append((argv, kwargs))
        return FakeProcess()

    monkeypatch.setattr(lab, "check_port_available", lambda port: None)
    monkeypatch.setattr(lab.subprocess, "Popen", fake_popen)
    with server() as (endpoint, received):
        port = int(endpoint.rsplit(":", 1)[1])
        result = lab.lab(*pinned_files, execute=True, port=port,
                         startup_seconds=2, inference_seconds=5,
                         evidence_dir=str(tmp_path))
    assert result["status"] == "LAB_SMOKE_OBSERVED_REVIEW_REQUIRED"
    assert result["binary_launched"] is True
    assert result["model_generation_calls"] == 1
    assert result["local_inference_attempted"] is True
    assert result["whole_system_8gb_validated"] is False
    assert result["smoke_result"]["expected_text_match"] is True
    assert result["smoke_result"]["model_id_sha256_observed"] == PIN
    assert [x[:2] for x in received] == [
        ("GET", "/health"), ("GET", "/v1/models"),
        ("GET", "/health"), ("GET", "/v1/models"),
        ("POST", "/v1/chat/completions")]
    argv, kwargs = commands[0]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is lab.subprocess.DEVNULL
    assert kwargs["env"].get("OPENAI_API_KEY") is None
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--n-gpu-layers") + 1] == "0"
    assert argv[argv.index("--parallel") + 1] == "1"
    assert argv[argv.index("--threads") + 1] == "2"
    folder = Path(result["evidence_session"])
    assert (folder / "report.json").is_file()
    assert (folder / "llama_server.log").is_file()
    assert json.loads((folder / "report.json").read_text(encoding="utf-8")) == result


def test_failure_generates_report_and_shuts_down(monkeypatch, pinned_files, tmp_path):
    class FakeProcess:
        pid = os.getpid()
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): self.returncode = -15
        def wait(self, timeout=None): return self.returncode
        def kill(self): self.returncode = -9
    proc = FakeProcess()
    monkeypatch.setattr(lab, "check_port_available", lambda port: None)
    monkeypatch.setattr(lab.subprocess, "Popen", lambda argv, **kwargs: proc)
    monkeypatch.setattr(lab, "server_ready", lambda *args: False)
    result = lab.lab(*pinned_files, execute=True,
                     evidence_dir=str(tmp_path), startup_seconds=2)
    assert result["status"] == "LAB_FAILED"
    assert result["failure_code"] == "server_startup_failed"
    assert result["model_generation_calls"] == 0
    assert result["binary_launched"]
    assert proc.returncode == -15
    assert (Path(result["evidence_session"]) / "report.json").is_file()


def test_cli_dry_run_does_not_spawn(pinned_files, capsys):
    exe, exe_pin, gguf, gguf_pin = pinned_files
    rc = lab.main([
        "--server-bin", exe, "--expected-server-sha256", exe_pin,
        "--gguf-file", gguf, "--expected-gguf-sha256", gguf_pin])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["status"] == "DRY_RUN_VERIFIED_FILES"
    assert data["model_generation_calls"] == 0
    assert data["binary_launched"] is False
