#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""Deterministic analyzer for structured JaamSim model snapshots."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import assistant_paths


ROOT = assistant_paths.ASSISTANT_ROOT
CASES_DIR = assistant_paths.EXAMPLES_DIR / "snapshots"
RESULTS_DIR = assistant_paths.OUTPUT_DIR / "rcl"
MATRIX_PATH = assistant_paths.EXAMPLES_DIR / "evaluation_matrix.csv"

REQUIRED_TOP_LEVEL_FIELDS = {
    "model_id",
    "case_id",
    "variant",
    "title",
    "objective",
    "components",
    "connections",
    "resources",
    "metrics",
    "assumptions",
}

FLOW_COMPONENT_TYPES = {"source", "queue", "process", "decision", "sink"}
FLOW_CONNECTION_TYPES = {"entity_flow", "approved_flow", "rework_flow", "conditional_flow"}
ESSENTIAL_TYPES = {"source", "sink"}
METRIC_KEYWORDS = {
    "tempo": ("tempo", "espera", "ciclo"),
    "throughput": ("throughput", "clientes atendidos", "itens aprovados", "atendidos", "aprovados"),
    "utilizacao": ("utilizacao", "utilização", "servidor", "maquina", "máquina"),
    "fila": ("fila", "espera"),
}


@dataclass
class Alert:
    rule_id: str
    severity: str
    component_id: str
    message: str
    why_it_matters: str
    suggestion: str
    evidence: dict[str, Any]


@dataclass
class Analysis:
    model_id: str
    case_id: str
    variant: str
    snapshot_file: str
    alerts: list[Alert]
    expected_rules: list[str]
    unexpected_rules: list[str]
    matched_rules: list[str]
    omissions: list[str]
    false_positives: list[str]


def load_snapshot(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    missing = sorted(REQUIRED_TOP_LEVEL_FIELDS - set(data))
    if missing:
        raise ValueError(f"{path}: campos obrigatorios ausentes: {', '.join(missing)}")

    component_ids = [component.get("id") for component in data["components"]]
    if len(component_ids) != len(set(component_ids)):
        raise ValueError(f"{path}: existem componentes com ids duplicados")

    known_ids = set(component_ids)
    for connection in data["connections"]:
        if connection.get("from") not in known_ids:
            raise ValueError(f"{path}: conexao com origem desconhecida: {connection}")
        if connection.get("to") not in known_ids:
            raise ValueError(f"{path}: conexao com destino desconhecido: {connection}")

    return data


def load_expectations(matrix_path: Path) -> dict[tuple[str, str], set[str]]:
    expectations: dict[tuple[str, str], set[str]] = defaultdict(set)
    with matrix_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["expected"].strip().lower() == "yes":
                expectations[(row["case_id"], row["variant"])].add(row["rule_id"])
    return expectations


def component_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {component["id"]: component for component in snapshot["components"]}


def build_degrees(snapshot: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for connection in snapshot["connections"]:
        if connection.get("type") not in FLOW_CONNECTION_TYPES:
            continue
        outgoing[connection["from"]].append(connection["to"])
        incoming[connection["to"]].append(connection["from"])
    return incoming, outgoing


def reachable_from_sources(snapshot: dict[str, Any]) -> set[str]:
    components = component_index(snapshot)
    _, outgoing = build_degrees(snapshot)
    sources = [cid for cid, component in components.items() if component.get("type") == "source"]
    visited: set[str] = set()
    queue: deque[str] = deque(sources)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(outgoing.get(current, []))
    return visited


def can_reach_sink(snapshot: dict[str, Any]) -> set[str]:
    components = component_index(snapshot)
    incoming, _ = build_degrees(snapshot)
    sinks = [cid for cid, component in components.items() if component.get("type") == "sink"]
    visited: set[str] = set()
    queue: deque[str] = deque(sinks)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(incoming.get(current, []))
    return visited


def has_complete_source_to_sink_path(snapshot: dict[str, Any]) -> bool:
    components = component_index(snapshot)
    reachable = reachable_from_sources(snapshot)
    return any(components[cid].get("type") == "sink" for cid in reachable)


def alert(
    rule_id: str,
    severity: str,
    component_id: str,
    message: str,
    why_it_matters: str,
    suggestion: str,
    evidence: dict[str, Any],
) -> Alert:
    return Alert(rule_id, severity, component_id, message, why_it_matters, suggestion, evidence)


def nested_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def optional_params(component: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("parameters", "inputs", "settings"):
        value = component.get(key)
        if isinstance(value, dict):
            merged.update(value)
    return merged


def has_any_key(mapping: dict[str, Any], aliases: set[str]) -> bool:
    lowered = {str(key).lower() for key in mapping}
    return any(alias.lower() in lowered for alias in aliases)


def text_contains(value: Any, aliases: set[str]) -> bool:
    text = str(value or "").lower()
    return any(alias.lower() in text for alias in aliases)


def component_text(component: dict[str, Any]) -> str:
    values = [component.get("id", ""), component.get("name", ""), component.get("type", "")]
    params = optional_params(component)
    values.extend(str(key) for key in params)
    values.extend(str(value) for value in params.values())
    return " ".join(values).lower()


def analyze_snapshot(snapshot: dict[str, Any]) -> list[Alert]:
    components = component_index(snapshot)
    incoming, outgoing = build_degrees(snapshot)
    reachable = reachable_from_sources(snapshot)
    reaches_sink = can_reach_sink(snapshot)
    alerts: list[Alert] = []
    types = {component.get("type") for component in components.values()}
    has_intermediate = bool(types & {"queue", "process", "decision"})
    structurally_insufficient = not {"source", "sink"} <= types or not has_intermediate

    # Avoid cascading structural alerts when the whole snapshot is still too partial.
    if not structurally_insufficient:
        # RCL01: component is not on a complete source->sink path.
        for cid, component in components.items():
            ctype = component.get("type")
            if ctype not in FLOW_COMPONENT_TYPES:
                continue
            if ctype in ESSENTIAL_TYPES and (cid in reachable or cid in reaches_sink):
                continue
            if cid not in reachable or cid not in reaches_sink:
                alerts.append(
                    alert(
                        "RCL01",
                        "media",
                        cid,
                        f"O componente '{component['name']}' parece estar fora de um fluxo completo entre origem e saida.",
                        "Componentes fora do fluxo principal podem indicar modelo incompleto ou etapa sem funcao operacional.",
                        "Conecte o componente ao fluxo principal ou documente por que ele existe como fragmento isolado.",
                        {
                            "incoming": incoming.get(cid, []),
                            "outgoing": outgoing.get(cid, []),
                            "reachable_from_source": cid in reachable,
                            "can_reach_sink": cid in reaches_sink,
                        },
                    )
                )

        # RCL02: queue/process/decision without incoming or outgoing flow.
        for cid, component in components.items():
            ctype = component.get("type")
            if ctype in {"queue", "process", "decision"} and (
                not incoming.get(cid) or not outgoing.get(cid)
            ):
                alerts.append(
                    alert(
                        "RCL02",
                        "alta",
                        cid,
                        f"O componente '{component['name']}' possui fluxo incompleto.",
                        "Etapas intermediarias precisam receber entidades e encaminha-las para que o modelo represente uma operacao coerente.",
                        "Verifique se existe origem, destino e papel operacional claro para esta etapa.",
                        {"incoming": incoming.get(cid, []), "outgoing": outgoing.get(cid, [])},
                    )
                )

    # RCL03: resources without usage.
    for resource in snapshot["resources"]:
        if not resource.get("used_by"):
            alerts.append(
                alert(
                    "RCL03",
                    "media",
                    resource["id"],
                    f"O recurso '{resource['name']}' foi definido, mas nao possui uso observavel.",
                    "Recursos sem associacao podem esconder capacidade nao modelada ou elemento criado sem funcao.",
                    "Associe o recurso a um processo ou remova-o do snapshot se ele nao for necessario.",
                    {"used_by": resource.get("used_by", [])},
                )
            )

    # RCL04: queue without service/destination.
    for cid, component in components.items():
        if component.get("type") != "queue":
            continue
        outgoing_types = [components[target].get("type") for target in outgoing.get(cid, [])]
        if not any(target_type in {"process", "decision", "sink"} for target_type in outgoing_types):
            alerts.append(
                alert(
                    "RCL04",
                    "alta",
                    cid,
                    f"A fila '{component['name']}' nao possui processo de atendimento ou destino coerente.",
                    "Uma fila sem atendimento representa acumulacao sem logica operacional completa.",
                    "Conecte a fila a um processo, decisao ou saida, e documente o criterio de atendimento.",
                    {"outgoing": outgoing.get(cid, []), "outgoing_types": outgoing_types},
                )
            )

    if not structurally_insufficient:
        # RCL05: process without valid upstream source path.
        for cid, component in components.items():
            if component.get("type") != "process":
                continue
            if not incoming.get(cid) or cid not in reachable:
                alerts.append(
                    alert(
                        "RCL05",
                        "alta",
                        cid,
                        f"O processo '{component['name']}' nao possui entidade de entrada claramente associada.",
                        "Processos sem entrada valida nao representam uma transformacao executavel no fluxo.",
                        "Conecte uma origem, fila ou etapa anterior ao processo.",
                        {
                            "incoming": incoming.get(cid, []),
                            "reachable_from_source": cid in reachable,
                        },
                    )
                )

    # RCL06: ambiguity in decisions/conditional flows without assumptions.
    assumptions = [item.strip() for item in snapshot.get("assumptions", []) if item.strip()]
    if not assumptions:
        for cid, component in components.items():
            if component.get("type") == "decision":
                alerts.append(
                    alert(
                        "RCL06",
                        "media",
                        cid,
                        f"A estrutura observada nao permite concluir com seguranca o papel de '{component['name']}'.",
                        "Decisoes sem regra operacional podem levar a interpretacoes diferentes do mesmo modelo.",
                        "Informe a regra operacional, percentual, criterio de roteamento ou condicao usada nesta decisao.",
                        {"assumptions": assumptions, "outgoing": outgoing.get(cid, [])},
                    )
                )

    # RCL07: missing or weak metrics for objective.
    objective = snapshot.get("objective", "").lower()
    metrics = snapshot.get("metrics", [])
    metric_text = " ".join(metric.get("name", "").lower() for metric in metrics)
    missing_metric = not metrics
    if not missing_metric:
        for keyword, aliases in METRIC_KEYWORDS.items():
            if keyword in objective and not any(alias in metric_text for alias in aliases):
                missing_metric = True
                break
    if missing_metric:
        alerts.append(
            alert(
                "RCL07",
                "media",
                "metrics",
                "O modelo nao declara metrica suficiente para avaliar o objetivo informado.",
                "Sem indicadores minimos, a simulacao pode rodar sem responder a pergunta de pesquisa ou de gestao.",
                "Inclua ao menos um indicador alinhado ao objetivo, como tempo de espera, throughput, utilizacao ou tempo de ciclo.",
                {"objective": snapshot.get("objective"), "metrics": metrics},
            )
        )

    # RCL08: decisions, rework or conditional flow without assumptions.
    has_decision_or_conditional = any(
        component.get("type") == "decision" for component in components.values()
    ) or any(connection.get("type") in {"conditional_flow", "rework_flow"} for connection in snapshot["connections"])
    if has_decision_or_conditional and not assumptions:
        target = next(
            (cid for cid, component in components.items() if component.get("type") == "decision"),
            "assumptions",
        )
        alerts.append(
            alert(
                "RCL08",
                "baixa",
                target,
                "A logica de decisao ou retrabalho parece depender de uma premissa nao documentada.",
                "Premissas implicitas dificultam a revisao conceitual e a reproducao do modelo.",
                "Registre a regra operacional usada para orientar a decisao, prioridade, percentual ou retrabalho.",
                {"assumptions": assumptions},
            )
        )

    # RCL09: inspection before processing without assumptions.
    if not assumptions:
        for connection in snapshot["connections"]:
            source = components[connection["from"]]
            target = components[connection["to"]]
            source_name = source.get("name", "").lower()
            target_name = target.get("name", "").lower()
            if "inspec" in target_name and "process" not in source_name:
                alerts.append(
                    alert(
                        "RCL09",
                        "media",
                        target["id"],
                        f"A sequencia '{source['name']}' -> '{target['name']}' pode estar incoerente com o fluxo operacional esperado.",
                        "Em fluxos produtivos simples, a inspecao costuma ocorrer apos algum processamento ou transformacao.",
                        "Verifique se a ordem das etapas reflete a operacao real ou documente a excecao.",
                        {"from": source["id"], "to": target["id"]},
                    )
                )

    # RCL10: insufficient structure.
    if structurally_insufficient:
        alerts.append(
            alert(
                "RCL10",
                "alta",
                "model",
                "O snapshot ainda nao possui estrutura minima para avaliacao conceitual.",
                "Sem origem, transformacao/fila e saida conectadas, a ferramenta nao consegue avaliar um fluxo completo.",
                "Inclua ao menos origem, fluxo intermediario e saida antes de solicitar avaliacao completa.",
                {
                    "component_types": sorted(types),
                    "has_complete_source_to_sink_path": has_complete_source_to_sink_path(snapshot),
                },
            )
        )

    simulation_settings = nested_mapping(snapshot.get("simulation"), snapshot.get("run_settings"))
    if simulation_settings and not has_any_key(
        simulation_settings,
        {"run_duration", "runduration", "duration", "sim_time", "simulation_time"},
    ):
        alerts.append(
            alert(
                "RCL11",
                "media",
                "simulation",
                "A duracao da simulacao nao esta documentada nos parametros do experimento.",
                "Sem duracao, o resultado pode misturar horizonte operacional, periodo de aquecimento e comparacoes incoerentes.",
                "Declare RunDuration/horizonte de simulacao e a unidade usada antes de comparar cenarios.",
                {"simulation": simulation_settings},
            )
        )

    distributions = snapshot.get("distributions", [])
    distribution_items: list[dict[str, Any]] = []
    if isinstance(distributions, dict):
        distribution_items = [value for value in distributions.values() if isinstance(value, dict)]
    elif isinstance(distributions, list):
        distribution_items = [value for value in distributions if isinstance(value, dict)]
    distribution_references = {
        str(value).strip().lower()
        for item in distribution_items
        for value in (item.get("id"), item.get("name"))
        if value
    }

    for cid, component in components.items():
        params = optional_params(component)
        has_parameter_contract = any(key in component for key in ("parameters", "inputs", "settings"))
        if component.get("type") == "source" and has_parameter_contract and not has_any_key(
            params,
            {"interarrival_time", "interarrivaltime", "arrival_rate", "schedule", "rate", "period"},
        ):
            alerts.append(
                alert(
                    "RCL12",
                    "alta",
                    cid,
                    f"A origem '{component['name']}' nao declara taxa, agenda ou intervalo entre chegadas.",
                    "Chegadas sem parametrizacao impedem calibracao e tornam a carga do sistema indefinida.",
                    "Informe taxa de chegada, agenda ou intervalo entre chegadas e documente a unidade.",
                    {"parameters": params},
                )
            )

        if (
            component.get("type") == "source"
            and str(component.get("jaamsim_class") or "").lower() == "entitygenerator"
            and not has_any_key(params, {"prototype_entity", "prototypeentity", "prototype"})
        ):
            alerts.append(
                alert(
                    "RCL26",
                    "alta",
                    cid,
                    f"A origem '{component['name']}' nao declara PrototypeEntity.",
                    "Sem prototipo, o EntityGenerator nao sabe qual entidade deve criar durante a simulacao.",
                    "Crie ou selecione um SimEntity e informe-o no campo PrototypeEntity do EntityGenerator.",
                    {"parameters": params, "jaamsim_class": component.get("jaamsim_class")},
                )
            )

        if component.get("type") == "process" and has_parameter_contract and not has_any_key(
            params,
            {"service_time", "servicetime", "processing_time", "processingtime", "duration", "delay"},
        ):
            alerts.append(
                alert(
                    "RCL13",
                    "alta",
                    cid,
                    f"O processo '{component['name']}' nao declara tempo de servico/processamento.",
                    "Processos sem tempo nao representam capacidade, ocupacao ou fila de forma interpretavel.",
                    "Defina tempo fixo, distribuicao ou amostra calibrada para a etapa.",
                    {"parameters": params},
                )
            )

        if component.get("type") == "decision" and params and not has_any_key(
            params,
            {"probability", "probabilities", "rule", "condition", "routing", "priority"},
        ) and not assumptions:
            alerts.append(
                alert(
                    "RCL14",
                    "media",
                    cid,
                    f"A decisao '{component['name']}' nao explicita probabilidade, regra ou condicao.",
                    "Roteamentos sem criterio dificultam replicacao e defesa do modelo.",
                    "Documente percentual, regra operacional, prioridade ou condicao de decisao.",
                    {"parameters": params, "assumptions": assumptions},
                )
            )

        if component.get("type") == "queue" and params and not has_any_key(
            params,
            {"queue_discipline", "discipline", "ranking", "fifo", "priority"},
        ):
            alerts.append(
                alert(
                    "RCL22",
                    "baixa",
                    cid,
                    f"A fila '{component['name']}' nao declara disciplina de atendimento.",
                    "Sem disciplina, FIFO/prioridade/preferencia podem ficar implicitos e confundir cenarios.",
                    "Declare FIFO, prioridade ou regra de selecao quando isso afetar o processo.",
                    {"parameters": params},
                )
            )

        references_distribution = any(
            str(value).strip().lower() in distribution_references for value in params.values()
        )
        if component.get("type") in {"process", "queue", "source"} and text_contains(
            component_text(component),
            {"tempo", "time", "duration", "service", "processing", "arrival"},
        ) and not references_distribution and not text_contains(
            component_text(component),
            {" min", " h", " hora", "dia", "seg", "second", "minute", "hour"},
        ):
            alerts.append(
                alert(
                    "RCL24",
                    "baixa",
                    cid,
                    f"O componente '{component['name']}' usa parametro temporal sem unidade evidente.",
                    "Unidades implicitas podem gerar erro de escala entre ProModel, JaamSim e relatorio.",
                    "Documente minutos, horas, dias ou segundos em cada parametro temporal.",
                    {"text": component_text(component)[:500]},
                )
            )

    metric_targets_required = bool(simulation_settings.get("metric_targets_required"))
    for metric in metrics:
        metric_id = metric.get("id") or metric.get("name") or "metric"
        if isinstance(metric, dict) and (metric.get("requires_target") or metric_targets_required) and not has_any_key(
            metric,
            {"target", "goal", "expected", "threshold"},
        ):
            alerts.append(
                alert(
                    "RCL15",
                    "baixa",
                    str(metric_id),
                    f"A metrica '{metric.get('name', metric_id)}' nao declara alvo, limite ou criterio de aceitacao.",
                    "Metricas sem alvo ajudam a observar, mas nao sustentam decisao ou comparacao de cenarios.",
                    "Defina alvo esperado, limite aceitavel ou criterio de melhoria.",
                    {"metric": metric},
                )
            )
        if isinstance(metric, dict) and metric.get("requires_data_source") and not has_any_key(
            metric,
            {"data_source", "source", "input", "sample"},
        ):
            alerts.append(
                alert(
                    "RCL25",
                    "media",
                    str(metric_id),
                    f"A metrica '{metric.get('name', metric_id)}' exige fonte de dados, mas ela nao foi documentada.",
                    "Sem fonte, a metrica pode virar apenas uma intencao sem rastreabilidade.",
                    "Indique arquivo, observacao, relatorio ou campo do JaamSim usado como fonte.",
                    {"metric": metric},
                )
            )

    for item in distribution_items:
        distribution_params = nested_mapping(item.get("parameters"), item.get("inputs"), item)
        if not has_any_key(distribution_params, {"random_seed", "randomseed", "seed", "stream"}):
            alerts.append(
                alert(
                    "RCL16",
                    "baixa",
                    str(item.get("id") or item.get("name") or "distribution"),
                    f"A distribuicao '{item.get('name', item.get('id', 'sem_nome'))}' nao declara seed/stream.",
                    "Sem semente ou stream, replicacoes ficam menos auditaveis.",
                    "Documente semente, stream ou politica de aleatoriedade para reproducao.",
                    {"distribution": item},
                )
            )

    if simulation_settings and (
        simulation_settings.get("validation_required") or snapshot.get("validation_stage")
    ) and not has_any_key(simulation_settings, {"warmup", "warm_up", "replications", "replicas", "replicacoes"}):
        alerts.append(
            alert(
                "RCL17",
                "media",
                "simulation",
                "A validacao foi marcada, mas warm-up/replicacoes nao foram definidos.",
                "Sem plano de execucao, resultados podem refletir transiente ou variabilidade de uma unica rodada.",
                "Declare warm-up, numero de replicacoes e criterio de comparacao.",
                {"simulation": simulation_settings, "validation_stage": snapshot.get("validation_stage")},
            )
        )

    data_quality = str(snapshot.get("data_quality_level") or simulation_settings.get("data_quality_level") or "").lower()
    if data_quality and any(word in data_quality for word in ["fraca", "weak", "fragil", "baixa"]):
        alerts.append(
            alert(
                "RCL18",
                "media",
                "data_quality",
                "A qualidade dos dados foi marcada como fragil.",
                "Dados frageis exigem comunicacao explicita de incerteza e cenarios de sensibilidade.",
                "Documente origem, tamanho da amostra, outliers e limite de uso dos dados.",
                {"data_quality_level": data_quality},
            )
        )

    user_profile = str(snapshot.get("user_profile") or "").lower()
    if user_profile in {"beginner", "iniciante"} and len(components) > 10:
        alerts.append(
            alert(
                "RCL19",
                "baixa",
                "model",
                "O modelo parece complexo para um primeiro ciclo de aprendizagem.",
                "Complexidade inicial aumenta risco de erro conceitual antes de validar o fluxo basico.",
                "Comece por um recorte minimo e adicione detalhes apos validar entidade, fila, recurso e saida.",
                {"component_count": len(components), "user_profile": user_profile},
            )
        )

    objective_text = str(snapshot.get("objective") or "").lower()
    if any(word in objective_text for word in ["compar", "cenario", "cenarios", "melhorar"]) and not snapshot.get("scenarios"):
        alerts.append(
            alert(
                "RCL20",
                "media",
                "scenarios",
                "O objetivo sugere comparacao de cenarios, mas nenhum cenario alternativo foi documentado.",
                "Sem cenarios, a simulacao pode nao responder a pergunta de melhoria.",
                "Registre cenario base e pelo menos uma alternativa operacional testavel.",
                {"objective": snapshot.get("objective"), "scenarios": snapshot.get("scenarios")},
            )
        )

    if simulation_settings and metrics and not snapshot.get("outputs"):
        alerts.append(
            alert(
                "RCL21",
                "baixa",
                "outputs",
                "Ha metricas definidas, mas as saidas/relatorios esperados nao foram listados.",
                "Saidas nao documentadas dificultam repetir a coleta e defender evidencias.",
                "Liste tabelas, graficos, CSVs ou relatorios que serao usados para cada metrica.",
                {"metrics": metrics, "outputs": snapshot.get("outputs")},
            )
        )

    for resource in snapshot.get("resources", []):
        if isinstance(resource, dict):
            params = nested_mapping(resource.get("parameters"), resource.get("inputs"), resource)
            if (resource.get("parameters") or resource.get("inputs")) and not has_any_key(
                params,
                {"capacity", "capacidade", "units", "quantity", "number"},
            ):
                alerts.append(
                    alert(
                        "RCL23",
                        "media",
                        str(resource.get("id") or resource.get("name") or "resource"),
                        f"O recurso '{resource.get('name', resource.get('id', 'sem_nome'))}' nao declara capacidade.",
                        "Capacidade ausente impede interpretar utilizacao, fila e gargalo.",
                        "Declare numero de unidades, capacidade simultanea ou turno disponivel.",
                        {"resource": resource},
                    )
                )

    return deduplicate_alerts(alerts)


def deduplicate_alerts(alerts: list[Alert]) -> list[Alert]:
    seen: set[tuple[str, str]] = set()
    result: list[Alert] = []
    for item in alerts:
        key = (item.rule_id, item.component_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def render_markdown(analysis: Analysis) -> str:
    lines = [
        f"# Relatorio de Analise — {analysis.model_id}",
        "",
        f"- Caso: `{analysis.case_id}`",
        f"- Variante: `{analysis.variant}`",
        f"- Snapshot: `{analysis.snapshot_file}`",
        f"- Regras esperadas: {', '.join(analysis.expected_rules) or 'nenhuma'}",
        f"- Regras acionadas: {', '.join(sorted({alert.rule_id for alert in analysis.alerts})) or 'nenhuma'}",
        f"- Acertos: {', '.join(analysis.matched_rules) or 'nenhum'}",
        f"- Omissoes: {', '.join(analysis.omissions) or 'nenhuma'}",
        f"- Falsos positivos: {', '.join(analysis.false_positives) or 'nenhum'}",
        "",
        "## Alertas",
        "",
    ]
    if not analysis.alerts:
        lines.append("Nenhum alerta gerado.")
    for item in analysis.alerts:
        lines.extend(
            [
                f"### {item.rule_id} — {item.severity}",
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


def analyze_file(path: Path, expectations: dict[tuple[str, str], set[str]]) -> Analysis:
    path = path.resolve()
    snapshot = load_snapshot(path)
    alerts = analyze_snapshot(snapshot)
    triggered = {alert.rule_id for alert in alerts}
    expected = expectations.get((snapshot["case_id"], snapshot["variant"]), set())
    matched = sorted(triggered & expected)
    omissions = sorted(expected - triggered)
    false_positives = sorted(triggered - expected)
    return Analysis(
        model_id=snapshot["model_id"],
        case_id=snapshot["case_id"],
        variant=snapshot["variant"],
        snapshot_file=str(path.relative_to(ROOT)),
        alerts=alerts,
        expected_rules=sorted(expected),
        unexpected_rules=sorted(false_positives),
        matched_rules=matched,
        omissions=omissions,
        false_positives=false_positives,
    )


def write_outputs(analysis: Analysis, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{analysis.model_id}_analysis.json"
    md_path = output_dir / f"{analysis.model_id}_analysis.md"
    payload = asdict(analysis)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    md_path.write_text(render_markdown(analysis), encoding="utf-8")


def write_summary(analyses: list[Analysis], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "model_id",
                "case_id",
                "variant",
                "expected_rules",
                "triggered_rules",
                "matched_rules",
                "omissions",
                "false_positives",
                "alert_count",
            ],
        )
        writer.writeheader()
        for analysis in analyses:
            writer.writerow(
                {
                    "model_id": analysis.model_id,
                    "case_id": analysis.case_id,
                    "variant": analysis.variant,
                    "expected_rules": ";".join(analysis.expected_rules),
                    "triggered_rules": ";".join(sorted({alert.rule_id for alert in analysis.alerts})),
                    "matched_rules": ";".join(analysis.matched_rules),
                    "omissions": ";".join(analysis.omissions),
                    "false_positives": ";".join(analysis.false_positives),
                    "alert_count": len(analysis.alerts),
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analisa snapshots estruturados para modelos JaamSim.")
    parser.add_argument(
        "snapshots",
        nargs="*",
        type=Path,
        help="Arquivos JSON. Se omitido, analisa todos os casos em Modelos_e_Snapshots_JaamSim/casos.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RESULTS_DIR,
        help="Diretorio de saida para relatorios.",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=MATRIX_PATH,
        help="CSV com regras esperadas por caso.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshots = args.snapshots or sorted(CASES_DIR.glob("*.json"))
    expectations = load_expectations(args.matrix)
    analyses: list[Analysis] = []
    for path in snapshots:
        analysis = analyze_file(path, expectations)
        write_outputs(analysis, args.output_dir)
        analyses.append(analysis)
        triggered = sorted({alert.rule_id for alert in analysis.alerts})
        print(
            f"{analysis.model_id}: {len(analysis.alerts)} alertas "
            f"({', '.join(triggered) or 'sem regras acionadas'})"
        )
    write_summary(analyses, args.output_dir)
    print(f"Relatorios salvos em: {args.output_dir}")


if __name__ == "__main__":
    main()
