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

README = """JAAM-AI / JAAMSIM 2026-03 - DESENVOLVIMENTO (SEM PROMOCAO)

STATUS: CANDIDATE_ONLY / GUI_WINDOWS_PENDING / P004_DENY / FULL45_NO_GO
O CMD central foi substituido por um menu pequeno e seguro. O arquivo
historico de 2.1MB v0.50 NAO foi editado e NAO e redistribuido no ZIP.

PONTO DE ENTRADA WINDOWS:
RODAR_JAAM_AI_COMPLETO.cmd

MENU:
ENTER/1 - Estado passivo; nao inicia servidores, testes ou inferencia.
2       - Abrir JaamSim 2026-03 (Assistente IA e StatFit).
3       - Revisar .cfg somente offline, gerando relatorios.
4       - Abrir relatorios existentes.
5       - Entrar no modulo MC-001 v0.50 original, se instalado separadamente.
6       - Compilar JaamSim com Ant no checkout de codigo (indisponivel no ZIP).
0       - Sair.

O modulo v0.50 original exige seus 3 arquivos imutaveis, na pasta:
legacy\\MC001_v050\\
  RODAR_JAAM_AI_COMPLETO.cmd
  RODAR_JAAM_AI_COMPLETO.cmd.sha256
  JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json
Alternativamente, defina JAAM_LEGACY_DIR com caminho absoluto para uma
pasta que contenha os 3 arquivos originais. O integrador verifica o hash
SHA-256 esperado antes de delegar qualquer acao ao modulo historico.
NAO RENOMEIE OU MODIFIQUE O ORIGINAL: sua opcao 7 e protegida por hash.

Linux continua com RODAR_LINUX.sh, por compatibilidade com bash.
Requisitos operacionais futuros: Java JDK 25 e Python 3.11 ou superior.
Nenhum teste manual foi solicitado ou executado nesta etapa.
Este pacote NAO inclui os 90 CFG oficiais de licenca mista.
Nao sobrescreva versoes ja validadas.
"""

LEGACY_README = """MC-001 v0.50 - ARQUIVOS HISTORICOS FORA DESTE CANDIDATO

Coloque nesta pasta os tres arquivos ORIGINAIS e inalterados disponiveis
no workspace do projeto JAAM-AI no Google Drive:
  RODAR_JAAM_AI_COMPLETO.cmd
  RODAR_JAAM_AI_COMPLETO.cmd.sha256
  JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json

Atalho equivalente: configure JAAM_LEGACY_DIR apontando para a pasta original.
O launcher central bloqueia o modulo se faltar arquivo ou checksum.
A opcao 7 historica continua offline e DENY: nunca autoriza P004 ou Full45.
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
    central = ROOT / "RODAR_JAAM_AI_COMPLETO.cmd"
    if not central.is_file():
        raise FileNotFoundError("Central launcher missing in repository root")
    files["RODAR_JAAM_AI_COMPLETO.cmd"] = central.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    files["legacy/MC001_v050/LEIA_ONDE_COLOCAR_ORIGINAL.txt"] = LEGACY_README.encode("utf-8")
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
        for name in ("JaamSim2026-03.jar", "RODAR_JAAM_AI_COMPLETO.cmd", "RODAR_LINUX.sh",
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
