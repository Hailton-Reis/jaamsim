#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""
CLI offline do modulo IA JaamSim.

Este comando implementa a decisao "algoritmo primeiro, IA sob demanda" no
formato mais simples: revisao deterministica local, sem LLM, sem IA local e
sem internet.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import jaamsim_cfg_to_snapshot
import snapshot_analyzer
import tcc_llm_assist

import assistant_paths


DEFAULT_OUTPUT_DIR = assistant_paths.OUTPUT_DIR / "offline-review"

SUPPORTED_INPUT_TYPES = {"json", "cfg"}
ALLOWED_SUGGESTION_STATUSES = {"pending", "accepted", "rejected", "applied", "cancelled"}


@dataclass
class OfflineReviewResult:
    input_file: str
    input_type: str
    generated_snapshot_file: str | None
    output_json_file: str
    output_markdown_file: str
    output_suggestions_file: str
    output_change_plan_file: str
    output_audit_file: str
    output_llm_assist_json_file: str | None
    output_llm_assist_markdown_file: str | None
    output_reviewed_snapshot_file: str | None
    analysis: snapshot_analyzer.Analysis
    local_suggestions: list["LocalSuggestion"]
    allowed_changes: list["AllowedChange"]
    suggestion_audit: list["SuggestionDecisionAudit"]
    parser_schema_version: str | None
    parser_warnings: list[dict[str, Any]]


@dataclass
class LocalSuggestion:
    suggestion_id: str
    rule_id: str
    component_id: str
    severity: str
    action_type: str
    scope: str
    automation_policy: str
    requires_user_acceptance: bool
    title: str
    suggested_change: str
    beginner_guidance: str
    experienced_guidance: str
    evidence: dict[str, Any]
    status: str = "pending"
    status_reason: str = ""
    status_actor: str = ""
    status_updated_at: str = ""


@dataclass
class AllowedChange:
    change_id: str
    suggestion_id: str
    rule_id: str
    component_id: str
    status: str
    operation: str
    path: str
    value: Any
    applyable: bool
    safety: str
    reason: str


@dataclass
class SuggestionDecisionAudit:
    audit_id: str
    suggestion_id: str
    rule_id: str
    component_id: str
    status: str
    status_source: str
    status_actor: str
    status_reason: str
    status_updated_at: str
    decision_effect: str
    allowed_change_id: str | None
    automatic_application: bool
    guardrail: str
    trace_note: str


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(snapshot_analyzer.ROOT))
    except ValueError:
        return str(resolved)


def detect_input_type(path: Path, forced_type: str = "auto") -> str:
    if forced_type != "auto":
        if forced_type not in SUPPORTED_INPUT_TYPES:
            raise ValueError(f"Tipo de entrada nao suportado: {forced_type}")
        return forced_type

    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".cfg":
        return "cfg"
    raise ValueError(f"Nao foi possivel detectar o tipo de entrada: {path}")


def load_expectations(use_matrix: bool, matrix_path: Path) -> dict[tuple[str, str], set[str]]:
    if not use_matrix:
        return {}
    return snapshot_analyzer.load_expectations(matrix_path)


def build_analysis_from_snapshot(
    snapshot_path: Path,
    expectations: dict[tuple[str, str], set[str]],
    *,
    evaluate_expected_rules: bool,
) -> snapshot_analyzer.Analysis:
    snapshot_path = snapshot_path.resolve()
    snapshot = snapshot_analyzer.load_snapshot(snapshot_path)
    alerts = snapshot_analyzer.analyze_snapshot(snapshot)
    triggered = {alert.rule_id for alert in alerts}
    expected = expectations.get((snapshot["case_id"], snapshot["variant"]), set()) if evaluate_expected_rules else set()
    false_positives = sorted(triggered - expected) if evaluate_expected_rules else []
    return snapshot_analyzer.Analysis(
        model_id=snapshot["model_id"],
        case_id=snapshot["case_id"],
        variant=snapshot["variant"],
        snapshot_file=display_path(snapshot_path),
        alerts=alerts,
        expected_rules=sorted(expected),
        unexpected_rules=false_positives,
        matched_rules=sorted(triggered & expected) if evaluate_expected_rules else [],
        omissions=sorted(expected - triggered) if evaluate_expected_rules else [],
        false_positives=false_positives,
    )


def write_generated_snapshot(snapshot: dict[str, Any], output_dir: Path) -> Path:
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{snapshot['model_id']}_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snapshot_path


def convert_cfg_input(
    cfg_path: Path,
    output_dir: Path,
    *,
    model_id: str | None,
    case_id: str,
    variant: str,
    title: str | None,
    objective: str | None,
) -> Path:
    snapshot = jaamsim_cfg_to_snapshot.convert_cfg_to_snapshot(
        cfg_path,
        model_id=model_id,
        case_id=case_id,
        variant=variant,
        title=title,
        objective=objective,
    )
    return write_generated_snapshot(snapshot, output_dir)


def triggered_rules(analysis: snapshot_analyzer.Analysis) -> list[str]:
    return sorted({alert.rule_id for alert in analysis.alerts})


SUGGESTION_TEMPLATES = {
    "RCL01": {
        "action_type": "review_flow_topology",
        "scope": "topology",
        "automation_policy": "suggestion_only",
        "title": "Revisar componente fora do caminho principal",
        "beginner_guidance": "Confira se este item deveria participar do fluxo entre entrada e saida. Se sim, conecte-o manualmente no JaamSim.",
        "experienced_guidance": "Verifique se o componente e intencionalmente auxiliar ou se ha ruptura no grafo source-sink.",
    },
    "RCL02": {
        "action_type": "repair_flow_boundary",
        "scope": "topology",
        "automation_policy": "suggestion_only",
        "title": "Revisar entrada ou saida ausente",
        "beginner_guidance": "Procure no modelo se a etapa recebe entidades e se envia entidades para a proxima etapa.",
        "experienced_guidance": "Inspecione grau de entrada/saida e confirme se a fronteira do bloco foi modelada de forma intencional.",
    },
    "RCL03": {
        "action_type": "associate_or_remove_resource",
        "scope": "resource_reference",
        "automation_policy": "suggestion_only",
        "title": "Associar ou remover recurso sem uso",
        "beginner_guidance": "Se o recurso representa uma pessoa, maquina ou servidor, associe-o a um processo. Se nao for necessario, remova-o manualmente.",
        "experienced_guidance": "Confirme se o recurso e reserva futura, capacidade implicita ou sobra de modelagem.",
    },
    "RCL04": {
        "action_type": "connect_queue_to_service",
        "scope": "topology",
        "automation_policy": "suggestion_only",
        "title": "Conectar fila a atendimento ou destino",
        "beginner_guidance": "Toda fila precisa de alguem ou algo que atenda os itens. Conecte a fila a um processo, decisao ou saida.",
        "experienced_guidance": "Valide se a fila e buffer terminal, fila de espera operacional ou artefato incompleto.",
    },
    "RCL05": {
        "action_type": "connect_process_upstream",
        "scope": "topology",
        "automation_policy": "suggestion_only",
        "title": "Revisar processo sem entrada valida",
        "beginner_guidance": "Um processo precisa receber entidades antes de executar. Verifique a etapa anterior.",
        "experienced_guidance": "Cheque alcancabilidade a partir de source e consistencia de alimentacao do processo.",
    },
    "RCL06": {
        "action_type": "document_decision_rule",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar regra de decisao ambigua",
        "beginner_guidance": "Explique com palavras simples quando cada caminho deve ser escolhido.",
        "experienced_guidance": "Formalize condicao, probabilidade, prioridade ou politica de roteamento.",
    },
    "RCL07": {
        "action_type": "add_or_review_metric",
        "scope": "metric",
        "automation_policy": "draft_only",
        "title": "Adicionar ou revisar metrica",
        "beginner_guidance": "Defina o que voce quer medir: espera, atendimento, utilizacao, fila ou throughput.",
        "experienced_guidance": "Confirme aderencia entre objetivo, KPIs e saidas batch/exportadas.",
    },
    "RCL08": {
        "action_type": "document_operational_assumption",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar premissa operacional",
        "beginner_guidance": "Escreva a regra que explica retrabalho, prioridade ou escolha de caminho.",
        "experienced_guidance": "Registre premissa verificavel para calibracao e validacao conceitual posterior.",
    },
    "RCL09": {
        "action_type": "review_process_sequence",
        "scope": "topology",
        "automation_policy": "suggestion_only",
        "title": "Revisar sequencia logica",
        "beginner_guidance": "Veja se a ordem das etapas faz sentido no mundo real antes de simular.",
        "experienced_guidance": "Confirme se a inversao e uma decisao de modelagem ou erro de precedencia.",
    },
    "RCL10": {
        "action_type": "complete_minimum_structure",
        "scope": "model_structure",
        "automation_policy": "suggestion_only",
        "title": "Completar estrutura minima do modelo",
        "beginner_guidance": "Garanta que exista chegada, fluxo intermediario e saida antes de confiar no resultado.",
        "experienced_guidance": "Valide se o snapshot possui estrutura minima para inferencia conceitual.",
    },
    "RCL11": {
        "action_type": "document_simulation_horizon",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar horizonte de simulacao",
        "beginner_guidance": "Defina por quanto tempo a simulacao deve rodar e em qual unidade.",
        "experienced_guidance": "Registre RunDuration, unidade, warm-up e criterio de parada do experimento.",
    },
    "RCL12": {
        "action_type": "define_arrival_pattern",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Definir padrao de chegada",
        "beginner_guidance": "Informe se as chegadas sao aleatorias, planejadas ou baseadas em agenda.",
        "experienced_guidance": "Formalize taxa, intervalo entre chegadas, agenda ou processo de Poisson.",
    },
    "RCL13": {
        "action_type": "define_service_time",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Definir tempo de servico",
        "beginner_guidance": "Toda etapa de atendimento precisa de um tempo fixo, uma amostra ou uma distribuicao.",
        "experienced_guidance": "Associe distribuicao, unidade e fonte de calibracao ao tempo de processamento.",
    },
    "RCL14": {
        "action_type": "document_routing_rule",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar regra de roteamento",
        "beginner_guidance": "Explique quando cada caminho e escolhido e qual percentual esperado.",
        "experienced_guidance": "Explicite probabilidade, condicao, prioridade ou politica de roteamento.",
    },
    "RCL15": {
        "action_type": "define_metric_target",
        "scope": "metric",
        "automation_policy": "draft_only",
        "title": "Definir alvo da metrica",
        "beginner_guidance": "Diga qual resultado seria bom, ruim ou aceitavel para essa metrica.",
        "experienced_guidance": "Registre target, baseline, limiar de aceitacao ou criterio de melhoria.",
    },
    "RCL16": {
        "action_type": "document_random_seed",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar semente aleatoria",
        "beginner_guidance": "Guarde a semente/stream para conseguir repetir o teste.",
        "experienced_guidance": "Defina seed, stream e politica de replicacao para auditabilidade.",
    },
    "RCL17": {
        "action_type": "define_validation_run_plan",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Definir warm-up e replicacoes",
        "beginner_guidance": "Defina quantas rodadas serao feitas e se havera periodo de aquecimento.",
        "experienced_guidance": "Registre warm-up, replicacoes, IC e criterio de comparacao entre cenarios.",
    },
    "RCL18": {
        "action_type": "document_data_limitations",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar fragilidade dos dados",
        "beginner_guidance": "Anote tamanho da amostra, origem e por que os dados ainda sao limitados.",
        "experienced_guidance": "Inclua incerteza, vieses, outliers e plano de sensibilidade.",
    },
    "RCL19": {
        "action_type": "reduce_initial_scope",
        "scope": "model_structure",
        "automation_policy": "suggestion_only",
        "title": "Reduzir escopo inicial",
        "beginner_guidance": "Comece com chegada, fila, atendimento e saida antes de adicionar detalhes.",
        "experienced_guidance": "Separe MVP conceitual de extensoes para reduzir risco de validacao.",
    },
    "RCL20": {
        "action_type": "define_comparison_scenarios",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Definir cenarios de comparacao",
        "beginner_guidance": "Crie um cenario base e uma alternativa simples para comparar.",
        "experienced_guidance": "Registre fatores alterados, controle de sementes e metricas de comparacao.",
    },
    "RCL21": {
        "action_type": "document_output_artifacts",
        "scope": "metric",
        "automation_policy": "draft_only",
        "title": "Documentar saidas esperadas",
        "beginner_guidance": "Liste quais graficos, tabelas ou arquivos serao usados para provar o resultado.",
        "experienced_guidance": "Mapeie metricas para relatorios, CSVs e evidencias reprodutiveis.",
    },
    "RCL22": {
        "action_type": "document_queue_discipline",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar disciplina da fila",
        "beginner_guidance": "Informe se a fila e FIFO, prioridade ou outra regra.",
        "experienced_guidance": "Formalize disciplina, ranking e impacto esperado no desempenho.",
    },
    "RCL23": {
        "action_type": "define_resource_capacity",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Definir capacidade do recurso",
        "beginner_guidance": "Informe quantas pessoas, maquinas ou unidades atendem ao mesmo tempo.",
        "experienced_guidance": "Registre capacidade simultanea, turnos, disponibilidade e restricoes.",
    },
    "RCL24": {
        "action_type": "document_time_unit",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Documentar unidade de tempo",
        "beginner_guidance": "Escreva se cada tempo esta em segundos, minutos, horas ou dias.",
        "experienced_guidance": "Padronize unidade temporal entre dados, distribuicoes e JaamSim.",
    },
    "RCL25": {
        "action_type": "link_metric_data_source",
        "scope": "metric",
        "automation_policy": "draft_only",
        "title": "Vincular metrica a fonte de dados",
        "beginner_guidance": "Diga de onde a metrica sera lida: relatorio, arquivo, tabela ou observacao.",
        "experienced_guidance": "Documente origem, transformacao e rastreabilidade da metrica.",
    },
    "RCL26": {
        "action_type": "define_generator_prototype",
        "scope": "assumption",
        "automation_policy": "draft_only",
        "title": "Definir entidade gerada",
        "beginner_guidance": "Selecione o EntityGenerator e informe no campo PrototypeEntity qual SimEntity ele deve criar.",
        "experienced_guidance": "Associe explicitamente o prototipo da entidade ao EntityGenerator e valide atributos herdados.",
    },
}


def build_local_suggestions(analysis: snapshot_analyzer.Analysis) -> list[LocalSuggestion]:
    suggestions: list[LocalSuggestion] = []
    for index, alert in enumerate(analysis.alerts, start=1):
        template = SUGGESTION_TEMPLATES.get(
            alert.rule_id,
            {
                "action_type": "review_alert",
                "scope": "model",
                "automation_policy": "suggestion_only",
                "title": "Revisar alerta local",
                "beginner_guidance": "Leia a mensagem e ajuste o modelo manualmente se fizer sentido.",
                "experienced_guidance": "Verifique a evidencia antes de decidir se o alerta procede.",
            },
        )
        suggestions.append(
            LocalSuggestion(
                suggestion_id=f"SUG{index:03d}",
                rule_id=alert.rule_id,
                component_id=alert.component_id,
                severity=alert.severity,
                action_type=template["action_type"],
                scope=template["scope"],
                automation_policy=template["automation_policy"],
                requires_user_acceptance=True,
                title=template["title"],
                suggested_change=alert.suggestion,
                beginner_guidance=template["beginner_guidance"],
                experienced_guidance=template["experienced_guidance"],
                evidence=alert.evidence,
            )
        )
    return suggestions


def load_suggestion_statuses(status_file: Path | None) -> dict[str, dict[str, str]]:
    if status_file is None:
        return {}
    status_file = status_file.resolve()
    if not status_file.exists():
        raise FileNotFoundError(status_file)

    payload = json.loads(status_file.read_text(encoding="utf-8-sig"))
    raw_items = payload.get("suggestions", payload)
    if isinstance(raw_items, list):
        entries = {item["suggestion_id"]: item for item in raw_items}
    elif isinstance(raw_items, dict):
        entries = raw_items
    else:
        raise ValueError("Arquivo de status de sugestoes deve conter lista ou objeto JSON.")

    statuses: dict[str, dict[str, str]] = {}
    for suggestion_id, entry in entries.items():
        if isinstance(entry, str):
            status = entry
            normalized = {"status": status}
        elif isinstance(entry, dict):
            status = str(entry.get("status", "pending"))
            normalized = {
                "status": status,
                "status_reason": str(entry.get("status_reason", entry.get("reason", ""))),
                "status_actor": str(entry.get("status_actor", entry.get("actor", ""))),
                "status_updated_at": str(entry.get("status_updated_at", entry.get("updated_at", ""))),
            }
        else:
            raise ValueError(f"Status invalido para {suggestion_id}: {entry}")
        if status not in ALLOWED_SUGGESTION_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_SUGGESTION_STATUSES))
            raise ValueError(f"Status invalido para {suggestion_id}: {status}. Permitidos: {allowed}")
        statuses[str(suggestion_id)] = normalized
    return statuses


def apply_suggestion_statuses(
    suggestions: list[LocalSuggestion],
    status_overrides: dict[str, dict[str, str]],
) -> list[LocalSuggestion]:
    for suggestion in suggestions:
        override = status_overrides.get(suggestion.suggestion_id)
        if not override:
            continue
        suggestion.status = override.get("status", suggestion.status)
        suggestion.status_reason = override.get("status_reason", suggestion.status_reason)
        suggestion.status_actor = override.get("status_actor", suggestion.status_actor)
        suggestion.status_updated_at = override.get("status_updated_at", suggestion.status_updated_at)
    return suggestions


def suggestion_status_counts(suggestions: list[LocalSuggestion]) -> dict[str, int]:
    return {status: sum(1 for item in suggestions if item.status == status) for status in sorted(ALLOWED_SUGGESTION_STATUSES)}


def build_allowed_changes(suggestions: list[LocalSuggestion]) -> list[AllowedChange]:
    changes: list[AllowedChange] = []
    accepted_statuses = {"accepted", "applied"}
    for suggestion in suggestions:
        if suggestion.status not in accepted_statuses:
            continue
        change_id = f"CHG{len(changes) + 1:03d}"
        if suggestion.scope == "assumption" and suggestion.automation_policy == "draft_only":
            changes.append(
                AllowedChange(
                    change_id=change_id,
                    suggestion_id=suggestion.suggestion_id,
                    rule_id=suggestion.rule_id,
                    component_id=suggestion.component_id,
                    status=suggestion.status,
                    operation="append",
                    path="assumptions",
                    value=(
                        f"[{suggestion.rule_id}/{suggestion.component_id}] "
                        f"Premissa a validar: {suggestion.suggested_change}"
                    ),
                    applyable=True,
                    safety="metadata_only",
                    reason="Premissas sao metadados seguros e nao alteram topologia do modelo.",
                )
            )
            continue
        if suggestion.scope == "metric" and suggestion.automation_policy == "draft_only":
            changes.append(
                AllowedChange(
                    change_id=change_id,
                    suggestion_id=suggestion.suggestion_id,
                    rule_id=suggestion.rule_id,
                    component_id=suggestion.component_id,
                    status=suggestion.status,
                    operation="review_metric",
                    path="metrics",
                    value={
                        "name": f"Metrica a definir para {suggestion.component_id}",
                        "target": suggestion.component_id,
                        "source_suggestion": suggestion.suggestion_id,
                    },
                    applyable=False,
                    safety="manual_review_required",
                    reason="Metricas exigem confirmacao de indicador, unidade e alvo antes de alterar o snapshot.",
                )
            )
            continue
        changes.append(
            AllowedChange(
                change_id=change_id,
                suggestion_id=suggestion.suggestion_id,
                rule_id=suggestion.rule_id,
                component_id=suggestion.component_id,
                status=suggestion.status,
                operation="blocked",
                path=suggestion.scope,
                value=suggestion.suggested_change,
                applyable=False,
                safety="topology_or_resource_guardrail",
                reason="Alteracoes de topologia, recurso ou fluxo exigem acao manual do operador.",
            )
        )
    return changes


def decision_effect_for(suggestion: LocalSuggestion, change: AllowedChange | None) -> str:
    if suggestion.status == "pending":
        return "aguarda_decisao_humana"
    if suggestion.status == "rejected":
        return "rejeitada_sem_plano_de_mudanca"
    if suggestion.status == "cancelled":
        return "cancelada_sem_plano_de_mudanca"
    if change is None:
        return "aceita_sem_mudanca_planejavel"
    if change.applyable:
        return "aceita_com_mudanca_segura_de_metadado"
    return "aceita_com_guardrail_manual"


def build_suggestion_audit(
    suggestions: list[LocalSuggestion],
    allowed_changes: list[AllowedChange],
    status_overrides: dict[str, dict[str, str]],
) -> list[SuggestionDecisionAudit]:
    changes_by_suggestion = {change.suggestion_id: change for change in allowed_changes}
    audit_entries: list[SuggestionDecisionAudit] = []
    for index, suggestion in enumerate(suggestions, start=1):
        change = changes_by_suggestion.get(suggestion.suggestion_id)
        override = status_overrides.get(suggestion.suggestion_id)
        status_source = "status_file" if override else "generated_default"
        guardrail = change.safety if change else "no_change_planned"
        audit_entries.append(
            SuggestionDecisionAudit(
                audit_id=f"AUD{index:03d}",
                suggestion_id=suggestion.suggestion_id,
                rule_id=suggestion.rule_id,
                component_id=suggestion.component_id,
                status=suggestion.status,
                status_source=status_source,
                status_actor=suggestion.status_actor,
                status_reason=suggestion.status_reason,
                status_updated_at=suggestion.status_updated_at,
                decision_effect=decision_effect_for(suggestion, change),
                allowed_change_id=change.change_id if change else None,
                automatic_application=bool(change and change.applyable),
                guardrail=guardrail,
                trace_note=(
                    "Decisao rastreada sem chamada a IA; alteracao automatica ocorre "
                    "somente quando applyable=true e --apply-safe-changes e usado."
                ),
            )
        )
    return audit_entries


def apply_allowed_changes_to_snapshot(snapshot_path: Path, changes: list[AllowedChange], output_dir: Path) -> Path | None:
    applyable_changes = [change for change in changes if change.applyable]
    if not applyable_changes:
        return None

    snapshot = snapshot_analyzer.load_snapshot(snapshot_path)
    assumptions = list(snapshot.get("assumptions", []))
    for change in applyable_changes:
        if change.operation == "append" and change.path == "assumptions" and change.value not in assumptions:
            assumptions.append(change.value)
    snapshot["assumptions"] = assumptions
    notes = snapshot.get("notes", "")
    snapshot["notes"] = (
        f"{notes} | Alteracoes seguras de metadados aplicadas pelo modulo offline; "
        "topologia preservada."
    ).strip(" |")

    output_dir.mkdir(parents=True, exist_ok=True)
    reviewed_path = output_dir / f"{snapshot['model_id']}_reviewed_snapshot.json"
    reviewed_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reviewed_path


def profile_guidance(suggestion: LocalSuggestion, user_profile: str) -> str:
    if user_profile == "experienced":
        return suggestion.experienced_guidance
    return suggestion.beginner_guidance


def render_offline_markdown(
    analysis: snapshot_analyzer.Analysis,
    *,
    parser_schema_version: str | None,
    parser_warnings: list[dict[str, Any]],
    input_file: str,
    input_type: str,
    generated_snapshot_file: str | None,
    use_matrix: bool,
    user_profile: str,
    local_suggestions: list[LocalSuggestion],
    allowed_changes: list[AllowedChange],
    suggestion_audit: list[SuggestionDecisionAudit],
    llm_assist_enabled: bool,
    llm_assist_markdown_file: str | None,
    reviewed_snapshot_file: str | None,
) -> str:
    lines = [
        f"# Revisao Offline do Modulo IA - {analysis.model_id}",
        "",
        "## Modo de execucao",
        "",
        "- Modo: `offline_deterministico`",
        "- Internet/API: `nao utilizada`",
        f"- LLM/IA online: `{'acionada como prototipo opcional' if llm_assist_enabled else 'nao utilizada'}`",
        "- IA local: `nao utilizada`",
        "- Motor usado: parser local + regras RCL + relatorios",
        f"- Assistente LLM opcional: `{llm_assist_markdown_file or 'nao'}`",
        f"- Perfil de orientacao: `{user_profile}`",
        f"- Entrada: `{input_file}`",
        f"- Tipo de entrada: `{input_type}`",
        f"- Snapshot analisado: `{generated_snapshot_file or analysis.snapshot_file}`",
        f"- Matriz de regras esperadas: `{'ativada' if use_matrix else 'desativada'}`",
        "",
        "## Resultado",
        "",
        f"- Caso: `{analysis.case_id}`",
        f"- Variante: `{analysis.variant}`",
        f"- Alertas: `{len(analysis.alerts)}`",
        f"- Sugestoes locais: `{len(local_suggestions)}`",
        f"- Mudancas permitidas planejadas: `{len(allowed_changes)}`",
        f"- Snapshot revisado gerado: `{reviewed_snapshot_file or 'nao'}`",
        f"- Regras acionadas: {', '.join(triggered_rules(analysis)) or 'nenhuma'}",
        "",
        "## Status das sugestoes",
        "",
    ]

    for status, count in suggestion_status_counts(local_suggestions).items():
        lines.append(f"- {status}: `{count}`")
    lines.append("")

    lines.extend(
        [
            "Estados permitidos: `pending`, `accepted`, `rejected`, `applied`, `cancelled`.",
            "",
            "Regra de seguranca: mesmo uma sugestao aceita nao altera topologia automaticamente.",
            "",
        ]
    )

    if use_matrix:
        lines.extend(
            [
                "## Conferencia contra matriz",
                "",
                f"- Regras esperadas: {', '.join(analysis.expected_rules) or 'nenhuma'}",
                f"- Acertos: {', '.join(analysis.matched_rules) or 'nenhum'}",
                f"- Omissoes: {', '.join(analysis.omissions) or 'nenhuma'}",
                f"- Falsos positivos: {', '.join(analysis.false_positives) or 'nenhum'}",
                "",
            ]
        )

    lines.extend([
        "## Diagnosticos do parser CFG",
        "",
        f"- Esquema do parser: `{parser_schema_version or 'nao informado'}`",
        f"- Avisos de leitura: `{len(parser_warnings)}`",
        "",
    ])
    if parser_warnings:
        lines.append("Atencao: avisos do parser indicam limites de cobertura ou de leitura; nao sao regras RCL.")
        lines.append("Verifique estes pontos antes de usar o snapshot como evidencia final.")
        lines.append("")
        for index, warning in enumerate(parser_warnings, start=1):
            lines.append(f"- Aviso {index}: `{json.dumps(warning, ensure_ascii=False)}`")
        lines.append("")
    else:
        lines.extend(["Nenhum aviso de leitura do parser registrado.", ""])

    lines.extend(["## Sugestoes locais estruturadas", ""])
    if not local_suggestions:
        lines.append("Nenhuma sugestao local gerada.")
    for suggestion in local_suggestions:
        lines.extend(
            [
                f"### {suggestion.suggestion_id} - {suggestion.title}",
                "",
                f"- Regra: `{suggestion.rule_id}`",
                f"- Componente: `{suggestion.component_id}`",
                f"- Tipo de acao: `{suggestion.action_type}`",
                f"- Escopo: `{suggestion.scope}`",
                f"- Politica de automacao: `{suggestion.automation_policy}`",
                f"- Exige aceite humano: `{'sim' if suggestion.requires_user_acceptance else 'nao'}`",
                f"- Status: `{suggestion.status}`",
                f"- Sugestao: {suggestion.suggested_change}",
                f"- Orientacao: {profile_guidance(suggestion, user_profile)}",
                "",
            ]
        )
        if suggestion.status_reason:
            lines.insert(-1, f"- Motivo/status: {suggestion.status_reason}")
        if suggestion.status_actor:
            lines.insert(-1, f"- Responsavel/status: {suggestion.status_actor}")
        if suggestion.status_updated_at:
            lines.insert(-1, f"- Atualizado em: {suggestion.status_updated_at}")

    lines.extend(["## Plano de mudancas permitidas", ""])
    if not allowed_changes:
        lines.append("Nenhuma mudanca permitida foi planejada. Sugestoes pendentes ou rejeitadas nao geram alteracao.")
        lines.append("")
    for change in allowed_changes:
        lines.extend(
            [
                f"### {change.change_id} - {change.operation}",
                "",
                f"- Sugestao origem: `{change.suggestion_id}`",
                f"- Regra: `{change.rule_id}`",
                f"- Componente: `{change.component_id}`",
                f"- Status da sugestao: `{change.status}`",
                f"- Caminho: `{change.path}`",
                f"- Aplicavel automaticamente: `{'sim' if change.applyable else 'nao'}`",
                f"- Seguranca: `{change.safety}`",
                f"- Motivo: {change.reason}",
                f"- Valor/plano: `{json.dumps(change.value, ensure_ascii=False)}`",
                "",
            ]
        )
    if reviewed_snapshot_file:
        lines.extend(
            [
                "Snapshot revisado gerado apenas com mudancas seguras de metadados:",
                "",
                f"- `{reviewed_snapshot_file}`",
                "",
            ]
        )

    lines.extend(["## Ledger de decisoes", ""])
    if not suggestion_audit:
        lines.append("Nenhuma decisao de sugestao registrada.")
        lines.append("")
    for audit in suggestion_audit:
        lines.extend(
            [
                f"### {audit.audit_id} - {audit.suggestion_id}",
                "",
                f"- Status: `{audit.status}`",
                f"- Origem do status: `{audit.status_source}`",
                f"- Efeito: `{audit.decision_effect}`",
                f"- Mudanca permitida vinculada: `{audit.allowed_change_id or 'nao'}`",
                f"- Aplicacao automatica possivel: `{'sim' if audit.automatic_application else 'nao'}`",
                f"- Guardrail: `{audit.guardrail}`",
                f"- Responsavel: `{audit.status_actor or 'nao informado'}`",
                f"- Motivo: {audit.status_reason or 'nao informado'}",
                f"- Atualizado em: `{audit.status_updated_at or 'nao informado'}`",
                "",
            ]
        )

    lines.extend(["## Alertas detalhados", ""])
    if not analysis.alerts:
        lines.append("Nenhum alerta gerado pelo nucleo deterministico.")
    for item in analysis.alerts:
        lines.extend(
            [
                f"### {item.rule_id} - {item.severity}",
                "",
                f"- Componente: `{item.component_id}`",
                f"- Mensagem: {item.message}",
                f"- Importancia: {item.why_it_matters}",
                f"- Sugestao: {item.suggestion}",
                f"- Evidencia: `{json.dumps(item.evidence, ensure_ascii=False)}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_offline_outputs(
    analysis: snapshot_analyzer.Analysis,
    output_dir: Path,
    *,
    parser_schema_version: str | None,
    parser_warnings: list[dict[str, Any]],
    input_file: str,
    input_type: str,
    generated_snapshot_file: str | None,
    use_matrix: bool,
    user_profile: str,
    local_suggestions: list[LocalSuggestion],
    allowed_changes: list[AllowedChange],
    suggestion_audit: list[SuggestionDecisionAudit],
    llm_assist_enabled: bool,
    llm_assist_json_file: str | None,
    llm_assist_markdown_file: str | None,
    reviewed_snapshot_file: str | None,
) -> tuple[Path, Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{analysis.model_id}_offline_review.json"
    markdown_path = output_dir / f"{analysis.model_id}_offline_review.md"
    suggestions_path = output_dir / f"{analysis.model_id}_suggestions_status.json"
    change_plan_path = output_dir / f"{analysis.model_id}_allowed_changes_plan.json"
    audit_path = output_dir / f"{analysis.model_id}_suggestion_decision_audit.json"
    payload = {
        "mode": "offline_deterministico",
        "ai_usage": {
            "internet_api": False,
            "llm_online": False,
            "local_ai": False,
        },
        "input_file": input_file,
        "input_type": input_type,
        "parser_diagnostics": {
            "schema_version": parser_schema_version,
            "warning_count": len(parser_warnings),
            "warnings": parser_warnings,
            "independent_of_rcl": True,
        },
        "user_profile": user_profile,
        "suggestion_status_file": display_path(suggestions_path),
        "suggestion_decision_audit_file": display_path(audit_path),
        "generated_snapshot_file": generated_snapshot_file,
        "use_expected_rules_matrix": use_matrix,
        "allowed_suggestion_statuses": sorted(ALLOWED_SUGGESTION_STATUSES),
        "triggered_rules": triggered_rules(analysis),
        "suggestion_status_counts": suggestion_status_counts(local_suggestions),
        "allowed_changes_plan_file": display_path(change_plan_path),
        "llm_online_assist": {
            "enabled": llm_assist_enabled,
            "prototype_only": llm_assist_enabled,
            "json_file": llm_assist_json_file,
            "markdown_file": llm_assist_markdown_file,
            "publication_policy": "nao_publicar_tokens_locais",
        },
        "reviewed_snapshot_file": reviewed_snapshot_file,
        "allowed_changes": [asdict(change) for change in allowed_changes],
        "suggestion_decision_audit": [asdict(audit) for audit in suggestion_audit],
        "local_suggestions": [asdict(suggestion) for suggestion in local_suggestions],
        "analysis": asdict(analysis),
    }
    suggestions_payload = {
        "model_id": analysis.model_id,
        "input_file": input_file,
        "allowed_statuses": sorted(ALLOWED_SUGGESTION_STATUSES),
        "instructions": (
            "Edite apenas os campos status/status_reason/status_actor/status_updated_at. "
            "Status aceito nao aplica alteracao automaticamente."
        ),
        "suggestions": [asdict(suggestion) for suggestion in local_suggestions],
    }
    change_plan_payload = {
        "model_id": analysis.model_id,
        "input_file": input_file,
        "reviewed_snapshot_file": reviewed_snapshot_file,
        "guardrails": [
            "Nao criar, apagar, conectar ou desconectar componentes automaticamente.",
            "Aplicar automaticamente apenas metadados seguros marcados como applyable=true.",
            "Metricas e topologia exigem revisao manual do operador.",
        ],
        "allowed_changes": [asdict(change) for change in allowed_changes],
    }
    audit_payload = {
        "model_id": analysis.model_id,
        "input_file": input_file,
        "mode": "offline_deterministico",
        "purpose": "Rastrear aceite, rejeicao e efeitos das sugestoes locais para evidencia academica e operacional.",
        "guardrail_summary": (
            "Sugestoes aceitas geram plano; somente metadados seguros applyable=true podem ser "
            "materializados em copia revisada quando --apply-safe-changes e usado."
        ),
        "audit_entries": [asdict(audit) for audit in suggestion_audit],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    suggestions_path.write_text(json.dumps(suggestions_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    change_plan_path.write_text(json.dumps(change_plan_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_offline_markdown(
            analysis,
            parser_schema_version=parser_schema_version,
            parser_warnings=parser_warnings,
            input_file=input_file,
            input_type=input_type,
            generated_snapshot_file=generated_snapshot_file,
            use_matrix=use_matrix,
            user_profile=user_profile,
            local_suggestions=local_suggestions,
            allowed_changes=allowed_changes,
            suggestion_audit=suggestion_audit,
            llm_assist_enabled=llm_assist_enabled,
            llm_assist_markdown_file=llm_assist_markdown_file,
            reviewed_snapshot_file=reviewed_snapshot_file,
        ),
        encoding="utf-8",
    )
    return json_path, markdown_path, suggestions_path, change_plan_path, audit_path


def review_input(
    input_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    input_type: str = "auto",
    use_matrix: bool = False,
    matrix_path: Path = snapshot_analyzer.MATRIX_PATH,
    model_id: str | None = None,
    case_id: str = "OFFLINE",
    variant: str = "review",
    title: str | None = None,
    objective: str | None = None,
    user_profile: str = "beginner",
    status_file: Path | None = None,
    apply_safe_changes: bool = False,
    llm_assist: bool = False,
    llm_provider_order: str | None = None,
    llm_env_file: Path | None = None,
    llm_request: str | None = None,
    llm_max_tokens: int = 700,
    llm_dry_run: bool = False,
) -> OfflineReviewResult:
    input_path = input_path.resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    detected_type = detect_input_type(input_path, input_type)
    output_dir = output_dir.resolve()
    expectations = load_expectations(use_matrix, matrix_path)
    generated_snapshot_path: Path | None = None

    if detected_type == "cfg":
        generated_snapshot_path = convert_cfg_input(
            input_path,
            output_dir,
            model_id=model_id,
            case_id=case_id,
            variant=variant,
            title=title,
            objective=objective,
        )
        snapshot_path = generated_snapshot_path
    else:
        snapshot_path = input_path

    # Parser warnings must reach the native assistant, not be buried only
    # in the generated snapshot. Keep them separate from deterministic RCLs.
    parsed_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    parser_schema_version = parsed_snapshot.get("parser_schema_version")
    raw_warnings = parsed_snapshot.get("parser_warnings", [])
    parser_warnings = [w for w in raw_warnings if isinstance(w, dict)] if isinstance(raw_warnings, list) else []

    analysis = build_analysis_from_snapshot(snapshot_path, expectations, evaluate_expected_rules=use_matrix)
    local_suggestions = build_local_suggestions(analysis)
    status_overrides = load_suggestion_statuses(status_file)
    local_suggestions = apply_suggestion_statuses(local_suggestions, status_overrides)
    allowed_changes = build_allowed_changes(local_suggestions)
    suggestion_audit = build_suggestion_audit(local_suggestions, allowed_changes, status_overrides)
    reviewed_snapshot_path = apply_allowed_changes_to_snapshot(snapshot_path, allowed_changes, output_dir) if apply_safe_changes else None
    reviewed_snapshot_file = display_path(reviewed_snapshot_path) if reviewed_snapshot_path else None
    generated_snapshot_file = display_path(generated_snapshot_path) if generated_snapshot_path else None
    llm_assist_json_path = output_dir / f"{analysis.model_id}_llm_assist.json" if llm_assist else None
    llm_assist_markdown_path = output_dir / f"{analysis.model_id}_llm_assist.md" if llm_assist else None
    llm_assist_json_file = display_path(llm_assist_json_path) if llm_assist_json_path else None
    llm_assist_markdown_file = display_path(llm_assist_markdown_path) if llm_assist_markdown_path else None
    json_path, markdown_path, suggestions_path, change_plan_path, audit_path = write_offline_outputs(
        analysis,
        output_dir,
        parser_schema_version=parser_schema_version,
        parser_warnings=parser_warnings,
        input_file=display_path(input_path),
        input_type=detected_type,
        generated_snapshot_file=generated_snapshot_file,
        use_matrix=use_matrix,
        user_profile=user_profile,
        local_suggestions=local_suggestions,
        allowed_changes=allowed_changes,
        suggestion_audit=suggestion_audit,
        llm_assist_enabled=llm_assist,
        llm_assist_json_file=llm_assist_json_file,
        llm_assist_markdown_file=llm_assist_markdown_file,
        reviewed_snapshot_file=reviewed_snapshot_file,
    )
    if llm_assist:
        review_payload = json.loads(json_path.read_text(encoding="utf-8"))
        tcc_llm_assist.write_assist_outputs(
            review_payload,
            output_dir,
            model_id=analysis.model_id,
            provider_order=llm_provider_order,
            env_file=llm_env_file,
            operator_request=llm_request,
            max_tokens=llm_max_tokens,
            dry_run=llm_dry_run,
        )
    return OfflineReviewResult(
        input_file=display_path(input_path),
        input_type=detected_type,
        generated_snapshot_file=generated_snapshot_file,
        output_json_file=display_path(json_path),
        output_markdown_file=display_path(markdown_path),
        output_suggestions_file=display_path(suggestions_path),
        output_change_plan_file=display_path(change_plan_path),
        output_audit_file=display_path(audit_path),
        output_llm_assist_json_file=llm_assist_json_file,
        output_llm_assist_markdown_file=llm_assist_markdown_file,
        output_reviewed_snapshot_file=reviewed_snapshot_file,
        analysis=analysis,
        local_suggestions=local_suggestions,
        allowed_changes=allowed_changes,
        suggestion_audit=suggestion_audit,
        parser_schema_version=parser_schema_version,
        parser_warnings=parser_warnings,
    )


def write_summary(results: list[OfflineReviewResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "offline_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "model_id",
                "input_type",
                "input_file",
                "generated_snapshot_file",
                "alert_count",
                "suggestion_count",
                "pending_suggestions",
                "accepted_suggestions",
                "rejected_suggestions",
                "applied_suggestions",
                "allowed_change_count",
                "applyable_change_count",
                "triggered_rules",
                "output_markdown_file",
                "output_suggestions_file",
                "output_change_plan_file",
                "output_audit_file",
                "output_llm_assist_json_file",
                "output_llm_assist_markdown_file",
                "output_reviewed_snapshot_file",
            ],
        )
        writer.writeheader()
        for result in results:
            counts = suggestion_status_counts(result.local_suggestions)
            writer.writerow(
                {
                    **{
                        "model_id": result.analysis.model_id,
                        "input_type": result.input_type,
                        "input_file": result.input_file,
                        "generated_snapshot_file": result.generated_snapshot_file or "",
                        "alert_count": len(result.analysis.alerts),
                        "suggestion_count": len(result.local_suggestions),
                        "allowed_change_count": len(result.allowed_changes),
                        "applyable_change_count": sum(1 for change in result.allowed_changes if change.applyable),
                    },
                    **{
                        f"{status}_suggestions": counts.get(status, 0)
                        for status in ["pending", "accepted", "rejected", "applied"]
                    },
                    **{
                        "triggered_rules": ";".join(triggered_rules(result.analysis)),
                        "output_markdown_file": result.output_markdown_file,
                        "output_suggestions_file": result.output_suggestions_file,
                        "output_change_plan_file": result.output_change_plan_file,
                        "output_audit_file": result.output_audit_file,
                        "output_llm_assist_json_file": result.output_llm_assist_json_file or "",
                        "output_llm_assist_markdown_file": result.output_llm_assist_markdown_file or "",
                        "output_reviewed_snapshot_file": result.output_reviewed_snapshot_file or "",
                    },
                }
            )
    return summary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Revisa snapshots/.cfg localmente, sem IA local e sem internet.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Arquivos .json ou .cfg para revisar.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Diretorio de saida.")
    parser.add_argument("--input-type", choices=["auto", "json", "cfg"], default="auto", help="Tipo de entrada.")
    parser.add_argument(
        "--use-matrix",
        action="store_true",
        help="Usa a matriz de regras esperadas dos casos controlados.",
    )
    parser.add_argument("--matrix", type=Path, default=snapshot_analyzer.MATRIX_PATH, help="CSV de regras esperadas.")
    parser.add_argument("--model-id", help="Identificador usado ao converter um unico .cfg.")
    parser.add_argument("--case-id", default="OFFLINE", help="Caso usado ao converter .cfg.")
    parser.add_argument("--variant", default="review", help="Variante usada ao converter .cfg.")
    parser.add_argument("--title", help="Titulo usado ao converter .cfg.")
    parser.add_argument("--objective", help="Objetivo usado ao converter .cfg.")
    parser.add_argument(
        "--status-file",
        type=Path,
        help="JSON opcional com status de sugestoes para reprocessar aceite/rejeicao.",
    )
    parser.add_argument(
        "--apply-safe-changes",
        action="store_true",
        help="Gera copia de snapshot apenas com mudancas seguras de metadados aceitas.",
    )
    parser.add_argument(
        "--profile",
        choices=["beginner", "experienced"],
        default="beginner",
        help="Perfil usado para orientar sugestoes locais.",
    )
    parser.add_argument(
        "--llm-assist",
        action="store_true",
        help="Aciona camada LLM online opcional do prototipo local apos a revisao offline.",
    )
    parser.add_argument(
        "--llm-provider-order",
        help="Ranking/fallback de provedores, ex.: nvidia,cerebras,groq.",
    )
    parser.add_argument(
        "--llm-env-file",
        type=Path,
        help="Arquivo .env local ignorado para carregar tokens do prototipo.",
    )
    parser.add_argument(
        "--llm-request",
        help="Pedido do operador para orientar a resposta LLM.",
    )
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=700,
        help="Limite de tokens da resposta LLM opcional.",
    )
    parser.add_argument(
        "--llm-dry-run",
        action="store_true",
        help="Configura a camada LLM sem chamar provedores externos.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.model_id and len(args.inputs) > 1:
        raise SystemExit("--model-id so pode ser usado com uma unica entrada.")

    results = [
        review_input(
            path,
            args.output_dir,
            input_type=args.input_type,
            use_matrix=args.use_matrix,
            matrix_path=args.matrix,
            model_id=args.model_id,
            case_id=args.case_id,
            variant=args.variant,
            title=args.title,
            objective=args.objective,
            user_profile=args.profile,
            status_file=args.status_file,
            apply_safe_changes=args.apply_safe_changes,
            llm_assist=args.llm_assist,
            llm_provider_order=args.llm_provider_order,
            llm_env_file=args.llm_env_file,
            llm_request=args.llm_request,
            llm_max_tokens=args.llm_max_tokens,
            llm_dry_run=args.llm_dry_run,
        )
        for path in args.inputs
    ]
    summary_path = write_summary(results, args.output_dir)
    for result in results:
        rules = ", ".join(triggered_rules(result.analysis)) or "sem regras acionadas"
        print(
            f"{result.analysis.model_id}: {len(result.analysis.alerts)} alertas, "
            f"{len(result.local_suggestions)} sugestoes locais ({rules})"
        )
        print(f"  Diagnosticos parser: {len(result.parser_warnings)} avisos")
        if result.parser_warnings:
            print("  ATENCAO: cobertura parcial de CFG; confira os detalhes no relatorio Markdown.")
            for warning in result.parser_warnings[:8]:
                print(f"    - {warning.get('type', 'UNKNOWN')}: {warning.get('object') or warning.get('target') or warning.get('encoding') or 'ver detalhes'}")
            if len(result.parser_warnings) > 8:
                print(f"    ... {len(result.parser_warnings) - 8} avisos adicionais no relatorio.")
        print(f"  Markdown: {result.output_markdown_file}")
        print(f"  Status sugestoes: {result.output_suggestions_file}")
        print(f"  Plano de mudancas: {result.output_change_plan_file}")
        print(f"  Auditoria decisoes: {result.output_audit_file}")
        if result.output_llm_assist_markdown_file:
            print(f"  Assistente LLM: {result.output_llm_assist_markdown_file}")
        if result.output_reviewed_snapshot_file:
            print(f"  Snapshot revisado: {result.output_reviewed_snapshot_file}")
    print(f"Resumo offline salvo em: {display_path(summary_path)}")


if __name__ == "__main__":
    main()
