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
PACKAGE_DIR = "JAAM_AI_NATIVE"
ZIP_TIME = (2026, 11, 14, 0, 0, 0)

README = """JAAM-AI / MODULO NATIVO - CANDIDATO DE DESENVOLVIMENTO

Este pacote NAO contem CMD principal. A entrada Windows e somente o
RODAR_JAAM_AI_COMPLETO.cmd original no workspace 00_PROJETO_ATUAL.
O CMD historico foi atualizado separadamente para o candidato v0.51,
sem alterar o atalho ou iniciar qualquer fase de testes.

Extraia esta pasta JAAM_AI_NATIVE ao lado do CMD original.
O menu central incorpora opcoes:
8 JaamSim IA e StatFit; 9 revisao CFG offline; 10 relatorios;
11 estado do modulo.
As opcoes legadas 1 a 7 continuam no CMD original.

Java JDK 25 e Python 3.11+ so sao exigidos quando suas funcoes
forem explicitamente acionadas pelo operador.
P004 DENY / Full45 NO-GO. Sem inferencia automatica.
Nao inclui o corpus licenca mista de 90 modelos oficiais.
Nao substitua instalacao validada nem execute testes antes da revisao.
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
    files["INTEGRACAO_COM_CMD_CENTRAL.txt"] = README.encode("utf-8")
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
        for name in ("JaamSim2026-03.jar",
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
