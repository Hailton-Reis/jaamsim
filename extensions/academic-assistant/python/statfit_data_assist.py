#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""
Assistente de preparação de dados para o StatFit-like do JaamSim Academic Assistant.

Esta etapa fica antes do ajuste de distribuições: ela interpreta uma entrada
colada/CSV/TXT, escolhe uma coluna numérica candidata, grava um CSV limpo e,
opcionalmente, pede a uma LLM online uma orientação de limpeza. A decisão de
usar o CSV preparado continua humana.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import statfit_auxiliar
import tcc_llm_assist

import assistant_paths
import runtime_provenance


ROOT = assistant_paths.ASSISTANT_ROOT
DEFAULT_OUTPUT_DIR = assistant_paths.OUTPUT_DIR / "statfit" / "data-assist"

MAX_LLM_VALUES = 80


@dataclass
class ColumnProfile:
    index: int
    label: str
    numeric_count: int
    ignored_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    standard_deviation: float | None
    probable_index: bool
    sample: list[float]


@dataclass
class PreparedDataReport:
    source: str
    requested_column: str | None
    selected_column: str
    selected_column_index: int
    sample_size: int
    data_quality_level: str
    ignored_values: int
    empty_lines: int
    outlier_count: int
    has_header: bool
    columns_detected: int
    warnings: list[str]
    local_guidance: list[str]
    column_profiles: list[ColumnProfile]
    cleaned_csv_path: str
    markdown_path: str
    json_path: str
    online_assist_enabled: bool
    online_assist_used: bool
    selected_provider: str | None
    selected_model: str | None
    llm_summary: str
    created_at: str


def read_input_text(input_file: Path | None, values: str | None) -> tuple[str, str]:
    if values and values.strip():
        return values, "dados_colados"
    if not input_file:
        raise ValueError("Informe um arquivo de dados ou --values.")
    return input_file.read_text(encoding="utf-8-sig"), str(input_file)


def split_rows(text: str) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    empty_lines = 0
    for line in text.splitlines():
        if not line.strip():
            empty_lines += 1
            continue
        row = statfit_auxiliar.split_messy_row(line)
        if row:
            rows.append(row)
    return rows, empty_lines


def looks_like_header(row: list[str]) -> bool:
    non_empty = [cell for cell in row if cell.strip()]
    if not non_empty:
        return False
    numeric = [statfit_auxiliar.try_parse_number(cell) for cell in non_empty]
    return any(value is None for value in numeric) and not any(value is not None for value in numeric)


def normalize_label(value: str) -> str:
    return statfit_auxiliar.normalize_label(value)


def column_label(header: list[str] | None, index: int) -> str:
    if header and index < len(header) and header[index].strip():
        return header[index].strip()
    return f"coluna_{index + 1}"


def build_column_profiles(rows: list[list[str]], header: list[str] | None, start_row: int) -> list[ColumnProfile]:
    max_columns = max((len(row) for row in rows), default=0)
    raw_values: list[list[float]] = [[] for _ in range(max_columns)]
    ignored = [0 for _ in range(max_columns)]

    for row in rows[start_row:]:
        for index in range(max_columns):
            cell = row[index] if index < len(row) else ""
            if not cell.strip():
                continue
            parsed = statfit_auxiliar.try_parse_number(cell)
            if parsed is None:
                tokens = statfit_auxiliar.extract_numeric_tokens(cell)
                if len(tokens) == 1:
                    parsed = tokens[0]
            if parsed is None or not math.isfinite(parsed):
                ignored[index] += 1
            else:
                raw_values[index].append(parsed)

    profiles: list[ColumnProfile] = []
    for index, values in enumerate(raw_values):
        if len(values) >= 2:
            stdev = statistics.pstdev(values)
        else:
            stdev = None
        profiles.append(
            ColumnProfile(
                index=index,
                label=column_label(header, index),
                numeric_count=len(values),
                ignored_count=ignored[index],
                minimum=min(values) if values else None,
                maximum=max(values) if values else None,
                mean=statistics.fmean(values) if values else None,
                standard_deviation=stdev,
                probable_index=statfit_auxiliar.is_probable_index(values),
                sample=values[:12],
            )
        )
    return profiles


def choose_column(
    profiles: list[ColumnProfile],
    requested_column: str | None,
    *,
    allow_index_column: bool = False,
) -> ColumnProfile:
    if not profiles:
        raise ValueError("Nenhuma coluna detectada.")

    if requested_column and requested_column.strip():
        wanted = requested_column.strip()
        try:
            one_based = int(wanted)
            for profile in profiles:
                if profile.index == one_based - 1:
                    return profile
        except ValueError:
            pass
        normalized = normalize_label(wanted)
        for profile in profiles:
            label = normalize_label(profile.label)
            if normalized and (normalized == label or normalized in label or label in normalized):
                return profile

    candidates = [profile for profile in profiles if profile.numeric_count > 0]
    if not candidates:
        raise ValueError("Nenhum valor numérico encontrado.")

    non_index = [profile for profile in candidates if allow_index_column or not profile.probable_index]
    if non_index:
        candidates = non_index
    return max(candidates, key=lambda item: (item.numeric_count, -item.ignored_count))


def selected_values(rows: list[list[str]], selected_index: int, start_row: int) -> tuple[list[float], int]:
    values: list[float] = []
    ignored = 0
    for row in rows[start_row:]:
        if selected_index >= len(row):
            continue
        cell = row[selected_index]
        if not cell.strip():
            continue
        parsed = statfit_auxiliar.try_parse_number(cell)
        if parsed is None:
            tokens = statfit_auxiliar.extract_numeric_tokens(cell)
            if len(tokens) == 1:
                parsed = tokens[0]
        if parsed is None or not math.isfinite(parsed):
            ignored += 1
        else:
            values.append(parsed)
    return values, ignored


def build_warnings(values: list[float], ignored_count: int, columns_detected: int) -> list[str]:
    warnings: list[str] = []
    if len(values) < 5:
        warnings.append("A amostra tem poucos valores; use apenas como ensaio inicial.")
    elif len(values) < statfit_auxiliar.MIN_RECOMMENDED_SAMPLE:
        warnings.append(
            f"A amostra tem {len(values)} valores; o ideal para ajuste e ter pelo menos "
            f"{statfit_auxiliar.MIN_RECOMMENDED_SAMPLE} observações."
        )
    if ignored_count:
        warnings.append(f"{ignored_count} célula(s) da coluna selecionada foram ignoradas por não serem numéricas.")
    if columns_detected > 1:
        warnings.append("Foram detectadas várias colunas; confirme se a coluna escolhida representa a variável correta.")
    if values and min(values) < 0:
        warnings.append("Há valores negativos; confira se a variável pode ser negativa no modelo.")
    if len(set(values)) == 1 and values:
        warnings.append("Todos os valores são iguais; talvez a entrada seja determinística, não uma distribuição ajustada.")
    outlier_count = statfit_auxiliar.count_iqr_outliers(values)
    if outlier_count:
        warnings.append(
            f"Possíveis outliers pelo critério IQR: {outlier_count} valor(es). Confirme se são medições reais ou erro de digitação."
        )
    return warnings


def classify_preparation_quality(
    values: list[float],
    *,
    ignored_count: int,
    columns_detected: int,
) -> str:
    if len(values) < 5 or len(set(values)) < 3:
        return "fraca"
    if ignored_count > 0:
        return "preparacao_com_cautela"
    if statfit_auxiliar.count_iqr_outliers(values) > 0:
        return "preparacao_com_cautela"
    if len(values) < statfit_auxiliar.MIN_RECOMMENDED_SAMPLE:
        return "preparacao_com_cautela"
    if columns_detected > 1:
        return "preparacao_com_cautela"
    return "preparacao_consistente"


def coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_value = statistics.fmean(values)
    if abs(mean_value) < 1e-12:
        return None
    return statistics.pstdev(values) / abs(mean_value)


def build_local_guidance(values: list[float]) -> list[str]:
    if not values:
        return ["Não foi possível gerar orientação sem valores numéricos."]
    guidance: list[str] = []
    cv = coefficient_of_variation(values)
    all_positive = min(values) >= 0
    if cv is not None and cv < 0.10:
        guidance.append("A variação é baixa; considere valor determinístico ou uniforme estreita como hipótese inicial.")
    elif all_positive and cv is not None and cv >= 0.80:
        guidance.append("A variação é alta e positiva; compare lognormal e exponencial no ajuste.")
    elif all_positive:
        guidance.append("Os valores sao positivos; normal truncada, lognormal ou triangular podem ser hipoteses candidatas.")
    else:
        guidance.append("Como há valores negativos ou mistos, valide se a variável física permite isso antes do ajuste.")
    guidance.append("Depois de preparar os dados, rode o ajuste e revise ranking, avisos e aderência conceitual.")
    guidance.append("Não aplique snippet automaticamente; copie para o modelo apenas depois de validar com o processo real.")
    return guidance


def write_clean_csv(values: list[float], output_dir: Path, source: str, column: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = statfit_auxiliar.safe_stem(source, column)
    csv_path = output_dir / f"{stem}_dados_preparados.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([column])
        for value in values:
            writer.writerow([statfit_auxiliar.format_cfg_number(value)])
    return csv_path


def llm_messages(report_context: dict[str, Any], values: list[float]) -> list[dict[str, str]]:
    system = (
        "Você é um assistente de preparação de dados para simulação discreta e StatFit. "
        "Analise somente o contexto fornecido. Não invente dados, validação, prints ou arquivos. "
        "Explique em português brasileiro: coluna escolhida, riscos de limpeza, perguntas ao operador "
        "e próximo passo. Não mande alterar o modelo automaticamente."
    )
    payload = {
        "perfil": report_context,
        "amostra_valores": values[:MAX_LLM_VALUES],
    }
    user = "Analise esta entrada de dados antes do ajuste de distribuição:\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_online_assist(
    report_context: dict[str, Any],
    values: list[float],
    *,
    provider_order: str,
    env_file: Path | None,
    max_tokens: int,
    dry_run: bool,
) -> tuple[bool, str | None, str | None, str, list[dict[str, Any]]]:
    candidates = tcc_llm_assist.configured_candidates(provider_order, env_file)
    attempts: list[dict[str, Any]] = []
    if dry_run:
        return (
            False,
            None,
            None,
            "DRY RUN: chamada LLM não executada; prompt e provedores foram preparados.",
            [
                {
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "ok": False,
                    "error": "dry_run",
                }
                for candidate in candidates
            ],
        )
    if not candidates:
        return False, None, None, "Nenhum provedor LLM configurado para esta analise.", attempts

    messages = llm_messages(report_context, values)
    for candidate in candidates:
        try:
            content, tokens, latency_ms = tcc_llm_assist.call_chat_completion(
                candidate,
                messages,
                temperature=0.2,
                max_tokens=max_tokens,
            )
            attempts.append(
                {
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "ok": True,
                    "latency_ms": latency_ms,
                    "tokens": tokens,
                }
            )
            return True, candidate.provider, candidate.model, content.strip(), attempts
        except Exception as exc:
            attempts.append(
                {
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "ok": False,
                    "error": str(exc)[:400],
                }
            )
    return False, None, None, "Todos os provedores configurados falharam; use a preparação local como base.", attempts


def render_markdown(report: PreparedDataReport, attempts: list[dict[str, Any]]) -> str:
    lines = [
        "# Preparação de dados StatFit",
        "",
        "> Relatório auxiliar. O CSV preparado só deve ser usado após revisão humana.",
        "",
        "## Resumo",
        "",
        f"- Origem: `{report.source}`",
        f"- Coluna selecionada: `{report.selected_column}`",
        f"- Tamanho da amostra: `{report.sample_size}`",
        f"- Classificação local da preparação: `{report.data_quality_level}`",
        f"- Valores ignorados: `{report.ignored_values}`",
        f"- Linhas vazias: `{report.empty_lines}`",
        f"- Possíveis outliers por IQR: `{report.outlier_count}`",
        f"- CSV limpo: `{report.cleaned_csv_path}`",
        f"- IA online usada: `{'sim' if report.online_assist_used else 'não'}`",
        f"- Provedor: `{report.selected_provider or 'nenhum'}`",
        "",
        "## Avisos",
        "",
    ]
    lines.extend([f"- {item}" for item in report.warnings] or ["- Nenhum aviso critico local."])
    lines.extend(["", "## Orientação local", ""])
    lines.extend([f"- {item}" for item in report.local_guidance])
    lines.extend(["", "## Colunas detectadas", ""])
    for profile in report.column_profiles:
        lines.append(
            "- "
            f"{profile.label}: numericos={profile.numeric_count}, ignorados={profile.ignored_count}, "
            f"media={profile.mean if profile.mean is not None else 'n/a'}, "
            f"provável_indice={'sim' if profile.probable_index else 'não'}"
        )
    lines.extend(["", "## Resposta IA", "", report.llm_summary.strip() or "IA online não acionada.", ""])
    if attempts:
        lines.extend(["## Tentativas IA", ""])
        for attempt in attempts:
            status = "OK" if attempt.get("ok") else "falhou"
            lines.append(f"- `{attempt.get('provider')}` / `{attempt.get('model')}`: {status}")
    return "\n".join(lines).strip() + "\n"


def prepare_data(args: argparse.Namespace) -> tuple[PreparedDataReport, list[dict[str, Any]]]:
    text, source = read_input_text(args.input_file, args.values)
    rows, empty_lines = split_rows(text)
    if not rows:
        raise ValueError("Nenhuma linha util encontrada.")
    header = rows[0] if looks_like_header(rows[0]) else None
    start_row = 1 if header else 0
    profiles = build_column_profiles(rows, header, start_row)
    selected = choose_column(profiles, args.column, allow_index_column=args.allow_index_column)
    values, ignored_count = selected_values(rows, selected.index, start_row)
    if not values:
        raise ValueError("A coluna selecionada não possui valores numéricos.")

    output_dir = args.output_dir
    csv_path = write_clean_csv(values, output_dir, source, selected.label)
    warnings = build_warnings(values, ignored_count, len(profiles))
    local_guidance = build_local_guidance(values)
    outlier_count = statfit_auxiliar.count_iqr_outliers(values)
    quality_level = classify_preparation_quality(
        values,
        ignored_count=ignored_count,
        columns_detected=len(profiles),
    )
    now = datetime.now().isoformat(timespec="seconds")

    report_context = {
        "source": source,
        "requested_column": args.column,
        "selected_column": selected.label,
        "selected_column_index": selected.index + 1,
        "sample_size": len(values),
        "data_quality_level": quality_level,
        "ignored_values": ignored_count,
        "empty_lines": empty_lines,
        "outlier_count": outlier_count,
        "has_header": bool(header),
        "columns_detected": len(profiles),
        "warnings": warnings,
        "local_guidance": local_guidance,
        "column_profiles": [asdict(profile) for profile in profiles],
    }

    online_used = False
    selected_provider = None
    selected_model = None
    llm_summary = "IA online não acionada. Preparação local concluída."
    attempts: list[dict[str, Any]] = []
    if args.online:
        online_used, selected_provider, selected_model, llm_summary, attempts = run_online_assist(
            report_context,
            values,
            provider_order=args.provider_order,
            env_file=args.env_file,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run_llm,
        )

    json_path = output_dir / f"{statfit_auxiliar.safe_stem(source, selected.label)}_data_assist.json"
    md_path = output_dir / f"{statfit_auxiliar.safe_stem(source, selected.label)}_data_assist.md"
    report = PreparedDataReport(
        source=source,
        requested_column=args.column,
        selected_column=selected.label,
        selected_column_index=selected.index + 1,
        sample_size=len(values),
        data_quality_level=quality_level,
        ignored_values=ignored_count,
        empty_lines=empty_lines,
        outlier_count=outlier_count,
        has_header=bool(header),
        columns_detected=len(profiles),
        warnings=warnings,
        local_guidance=local_guidance,
        column_profiles=profiles,
        cleaned_csv_path=str(csv_path),
        markdown_path=str(md_path),
        json_path=str(json_path),
        online_assist_enabled=bool(args.online),
        online_assist_used=online_used,
        selected_provider=selected_provider,
        selected_model=selected_model,
        llm_summary=llm_summary,
        created_at=now,
    )
    payload = asdict(report)
    payload["provider_attempts"] = attempts
    payload["python_runtime"] = runtime_provenance.capture_runtime(Path(__file__))
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report, attempts), encoding="utf-8")
    return report, attempts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepara dados para o StatFit-like com apoio local/IA opcional.")
    parser.add_argument("input_file", nargs="?", type=Path, help="Arquivo CSV/TXT com dados.")
    parser.add_argument("--values", help="Dados colados do Excel/CSV/TXT.")
    parser.add_argument("--column", help="Nome ou numero da coluna a preparar.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--online", action="store_true", help="Tenta chamar IA online com provedores configurados.")
    parser.add_argument("--require-online", action="store_true", help="Retorna erro se a IA online não for usada.")
    parser.add_argument("--provider-order", default=tcc_llm_assist.DEFAULT_PROVIDER_ORDER)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-tokens", type=int, default=650)
    parser.add_argument("--dry-run-llm", action="store_true", help="Monta a chamada sem gastar tokens.")
    parser.add_argument("--allow-index-column", action="store_true", help="Permite selecionar coluna que parece indice.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report, _attempts = prepare_data(args)
    if args.require_online and not report.online_assist_used:
        print("IA online: não")
        print(f"Relatório Markdown: {report.markdown_path}")
        print(f"Relatório JSON: {report.json_path}")
        return 2
    print(f"Coluna preparada: {report.selected_column}")
    print(f"Amostra: {report.sample_size}")
    print(f"Classificação preparação: {report.data_quality_level}")
    print(f"Outliers IQR: {report.outlier_count}")
    print(f"Valores ignorados: {report.ignored_values}")
    print(f"IA online: {'sim' if report.online_assist_used else 'não'}")
    print(f"Provedor: {report.selected_provider or 'nenhum'}")
    print(f"CSV limpo: {report.cleaned_csv_path}")
    print(f"Relatório Markdown: {report.markdown_path}")
    print(f"Relatório JSON: {report.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
