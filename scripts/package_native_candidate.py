#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0
"""Package an isolated JaamSim native GUI candidate with its Python extension.

This is a test candidate, not a promoted release. The official 90-CFG corpus,
including separately licensed BigLean files, must never be embedded here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = "JAAM_AI_JAAMSIM_NATIVE_CANDIDATE"
ZIP_TIME = (2026, 11, 14, 0, 0, 0)

README = """JAAM-AI / JAAMSIM 2026-03 - CANDIDATO PARA TESTES

ESTADO: CANDIDATE_ONLY / WINDOWS_GUI_PENDING / NAO E RELEASE FINAL.
Esta copia nao substitui a instalacao JaamSim validada.

REQUISITOS
- JDK 25 no PATH
- Python 3.11 ou superior para revisao local
- Windows ou Linux com ambiente grafico

TESTE
1. Extraia em pasta NOVA; nao sobrescreva a versao principal.
2. Windows: execute RODAR_WINDOWS.cmd.
   Linux: chmod +x RODAR_LINUX.sh && ./RODAR_LINUX.sh.
3. Na interface, abra o exemplo C1 e salve um modelo como .cfg.
4. Na janela Assistente IA, execute revisao offline.
5. Confira relatorios em extensions/academic-assistant/output/.
6. Confira os avisos de fluxo nao resolvido em JSON/Markdown e no painel.
7. Abra e feche a janela StatFit e confira o layout.

Se o Python nao for localizado, defina JAAMSIM_PYTHON com seu caminho.
Para testar Python:
python extensions/academic-assistant/python/modulo_ia_offline.py --help

Nenhum .cfg deve ser editado automaticamente pela revisao offline.
Nao envie dados pessoais, .env, credenciais ou chaves para o teste.
Os hashes de cada arquivo estao em MANIFEST_SHA256.json.
O pacote NAO inclui o corpus oficial de 90 .cfg do JaamSim.
"""

WINDOWS = """@echo off
setlocal
cd /d "%~dp0"
set "JAAMSIM_ASSISTANT_ROOT=%CD%\\extensions\\academic-assistant"
if not defined JAAMSIM_PYTHON set "JAAMSIM_PYTHON=python"
where java >nul 2>nul
if errorlevel 1 (
  echo ERRO: Java nao encontrado. Instale JDK 25 e adicione ao PATH.
  pause
  exit /b 1
)
echo JAAM-AI - candidato sem aceite GUI
java -version
java -jar "JaamSim2026-03.jar"
if errorlevel 1 (
  echo ERRO ao abrir JaamSim. Confira Java 25 e dependencias.
  pause
  exit /b 1
)
endlocal
"""

LINUX = """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export JAAMSIM_ASSISTANT_ROOT="$PWD/extensions/academic-assistant"
if [ -z "$(printenv JAAMSIM_PYTHON 2>/dev/null || true)" ]; then
  export JAAMSIM_PYTHON=python3
fi
echo "JAAM-AI - candidato sem aceite GUI"
java -version
exec java -jar "JaamSim2026-03.jar"
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect() -> dict[str, bytes]:
    jar = ROOT / "build/jars/JaamSim2026-03.jar"
    if not jar.is_file() or jar.stat().st_size == 0:
        raise FileNotFoundError("Run scripts/build.sh before packaging")
    files = {"JaamSim2026-03.jar": jar.read_bytes()}
    for name in ("LICENSE", "NOTICE"):
        if (ROOT / name).is_file():
            files[name] = (ROOT / name).read_bytes()
    base = ROOT / "extensions/academic-assistant"
    for p in sorted((base / "python").rglob("*.py")):
        if "__pycache__" not in p.parts:
            files[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    for p in sorted((base / "examples").rglob("*")):
        if p.is_file() and p.suffix.lower() in {".cfg", ".csv", ".json", ".md", ".txt"}:
            files[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    files["LEIA_ANTES_DO_TESTE.txt"] = README.encode("utf-8")
    files["RODAR_WINDOWS.cmd"] = WINDOWS.replace("\n", "\r\n").encode("utf-8")
    files["RODAR_LINUX.sh"] = LINUX.encode("utf-8")
    return files


def package(output: Path) -> dict:
    files = collect()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    manifest = {
        "package": PACKAGE_DIR,
        "status": "CANDIDATE_ONLY_GUI_PENDING",
        "source_commit": sha,
        "official_corpus_90_cfg_included": False,
        "files": {
            name: {"sha256": digest(data), "bytes": len(data)}
            for name, data in sorted(files.items())
        },
    }
    files["MANIFEST_SHA256.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(files.items()):
            zinfo = zipfile.ZipInfo(f"{PACKAGE_DIR}/{name}", date_time=ZIP_TIME)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
            archive.writestr(zinfo, data)
    return manifest


def verify(output: Path) -> dict:
    with zipfile.ZipFile(output) as archive:
        manifest_name = f"{PACKAGE_DIR}/MANIFEST_SHA256.json"
        manifest = json.loads(archive.read(manifest_name))
        expected = {f"{PACKAGE_DIR}/{name}" for name in manifest["files"]}
        if set(archive.namelist()) != expected | {manifest_name}:
            raise ValueError("Unexpected or missing ZIP entries")
        for name, row in manifest["files"].items():
            data = archive.read(f"{PACKAGE_DIR}/{name}")
            if len(data) != row["bytes"] or digest(data) != row["sha256"]:
                raise ValueError(f"Invalid SHA256 for {name}")
        for name in ("JaamSim2026-03.jar", "RODAR_WINDOWS.cmd", "RODAR_LINUX.sh",
                     "extensions/academic-assistant/python/modulo_ia_offline.py",
                     "extensions/academic-assistant/python/jaamsim_cfg_to_snapshot.py"):
            if f"{PACKAGE_DIR}/{name}" not in expected:
                raise ValueError(f"Required runtime path missing: {name}")
        if any("official_examples_extracted" in name for name in expected):
            raise ValueError("Mixed-license official corpus must stay outside test package")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "build/dist/jaam-ai-native-candidate.zip",
    )
    args = parser.parse_args()
    manifest = package(args.output)
    if manifest != verify(args.output):
        raise ValueError("Packaging verification mismatch")
    print(f"CANDIDATE_PACKAGE_OK {args.output}")
    print(f"CANDIDATE_PACKAGE_SHA256 {digest(args.output.read_bytes())}")
    print(f"CANDIDATE_FILES {len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
