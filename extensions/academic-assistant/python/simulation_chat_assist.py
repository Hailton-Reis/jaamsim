#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""Conversational JaamSim assistant helper.

This helper is intentionally small: it sends a simulation-focused chat turn to
the configured LLM providers and stores a local JSONL history. It never prints
tokens or credentials. When no provider is available, it returns a deterministic
offline playbook useful for teaching, review and defense.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import tcc_llm_assist

try:
    from ftfy import fix_text as _ftfy_fix_text
except Exception:  # pragma: no cover - optional runtime dependency
    _ftfy_fix_text = None


SYSTEM_PROMPT = (
    "Você é um assistente conversacional integrado ao JaamSim, focado em "
    "simulação discreta, modelagem conceitual, filas, recursos, chegadas, "
    "processamento, saídas, métricas e StatFit. Converse em português do Brasil. "
    "Escreva com ortografia e acentuação corretas. Nunca insira espaços dentro "
    "de palavras acentuadas ou com cedilha, como serviço, lógica, distribuições, "
    "próximo, única, óleo, métricas e estágios. "
    "Faça no máximo uma pergunta por resposta quando estiver levantando requisitos. "
    "Prefira respostas curtas e progressivas. Evite tabelas longas enquanto o "
    "operador ainda estiver refinando requisitos. "
    "Não diga ao usuário se você é algoritmo, LLM, online ou offline. "
    "Não crie objetos, não apague objetos, não conecte topologia e não prometa "
    "alteração automática do modelo. Se faltar informação, pergunte. "
    "Quando o usuário não tiver dados históricos e pedir uma distribuição, sugira "
    "uma hipótese inicial e deixe claro que ela deve ser validada por cenários. "
    "Para chegadas ou vendas aleatórias, considere processo de Poisson e tempos "
    "entre chegadas exponenciais; para horários planejados, use chegada determinística "
    "ou agenda; para tempos com mínimo e máximo, considere uniforme ou triangular; "
    "para lotes fixos, use valor determinístico. Se houver média diária, pergunte "
    "o tempo de expediente para converter em taxa. Não abra StatFit apenas porque "
    "o usuário mencionou distribuição; StatFit deve ser sugerido quando houver amostras "
    "numéricas ou quando o usuário pedir explicitamente ajuste por arquivo. "
    "Se o usuário mencionar Bizagi, BPMN, IDEF-SIM, imagem, print ou fluxograma, "
    "explique que o fluxo pode ser usado como entrada conceitual. Quando houver "
    "anexo disponível, use a leitura visual opcional; quando não houver, peça a "
    "descrição dos elementos principais. "
    "Se o usuário pedir revisão/correção do modelo, oriente que pode pedir "
    "'revisar modelo'. Seja direto, útil e natural."
)


_TEXT_TRANSLATION = {
    ord("\u00a0"): " ",
    ord("\u2007"): " ",
    ord("\u202f"): " ",
    ord("\u00ad"): None,
    ord("\u200b"): None,
    ord("\u200c"): None,
    ord("\u200d"): None,
    ord("\ufeff"): None,
}


OBJECT_GUIDANCE = {
    "entitygenerator": (
        "EntityGenerator cria entidades no modelo. Use para representar chegadas de pacientes, clientes, peças "
        "ou pedidos. Defina taxa, agenda ou intervalo entre chegadas antes de discutir capacidade."
    ),
    "queue": (
        "Queue representa espera. Ela precisa receber entidades e encaminhar para um processo, servidor, decisão "
        "ou saída. A fila costuma medir tamanho médio, espera e gargalo."
    ),
    "server": (
        "Server representa um recurso que atende entidades por um tempo de serviço. Defina capacidade, tempo de "
        "serviço, disciplina de fila e métrica de utilização."
    ),
    "entityprocessor": (
        "EntityProcessor representa uma etapa de processamento. Use quando a entidade passa por uma atividade com "
        "duração, como triagem, atendimento, inspeção ou embalagem."
    ),
    "branch": (
        "Branch separa caminhos. Documente probabilidade, regra, prioridade ou condição de roteamento; sem isso o "
        "modelo fica difícil de validar."
    ),
    "entitysink": (
        "EntitySink remove entidades do modelo. Use para marcar saída do sistema, alta, entrega final, descarte ou "
        "fim do atendimento."
    ),
}


PATTERN_CATALOG = {
    "fila_simples": {
        "label": "fila simples",
        "when": "um único ponto de atendimento ou recurso principal",
        "steps": [
            "Defina a entidade que chega ao sistema.",
            "Crie uma origem de chegadas e uma fila antes do atendimento.",
            "Crie um servidor/processo com tempo de serviço.",
            "Conecte a saída e meça espera, fila, utilização e throughput.",
        ],
    },
    "multiplos_servidores": {
        "label": "múltiplos servidores",
        "when": "vários atendentes ou máquinas executam o mesmo serviço",
        "steps": [
            "Modele uma fila compartilhada ou filas separadas, conforme o processo real.",
            "Defina capacidade de cada servidor e política de escolha.",
            "Compare cenários com diferentes quantidades de recursos.",
            "Observe utilização, tempo de espera e ociosidade.",
        ],
    },
    "pronto_atendimento": {
        "label": "pronto atendimento",
        "when": "pacientes passam por recepção, triagem, consulta e saída",
        "steps": [
            "Entidade: paciente; recursos: recepção, triagem e médico.",
            "Crie uma fila para cada etapa que possa acumular pacientes.",
            "Use distribuições separadas para chegadas, triagem e atendimento médico.",
            "Meça espera por etapa, utilização dos recursos e tempo total no sistema.",
        ],
    },
    "linha_sequencial": {
        "label": "linha sequencial",
        "when": "produto ou pedido passa por etapas em série",
        "steps": [
            "Liste as etapas na ordem real.",
            "Crie processo e fila/buffer para cada etapa crítica.",
            "Registre tempo de ciclo, gargalo e WIP.",
            "Teste cenários alterando capacidade da etapa mais carregada.",
        ],
    },
    "inspecao_retrabalho": {
        "label": "inspeção e retrabalho",
        "when": "itens podem ser aprovados, reprovados ou voltar para uma etapa anterior",
        "steps": [
            "Modele a inspeção depois da etapa que gera possibilidade de falha.",
            "Documente a probabilidade ou regra de aprovação.",
            "Conecte retrabalho sem automatizar topologia sem revisão humana.",
            "Meça taxa de retrabalho, fila na inspeção e tempo de ciclo.",
        ],
    },
    "estoque_simples": {
        "label": "estoque simples",
        "when": "há demanda, reposição e risco de falta",
        "steps": [
            "Defina demanda, reposição, lote e ponto de pedido.",
            "Separe evento de consumo e evento de reposição.",
            "Meça faltas, estoque médio e nível de serviço.",
            "Teste cenários com política de reposição alternativa.",
        ],
    },
    "transporte": {
        "label": "transporte",
        "when": "entidades se deslocam entre pontos com tempo de viagem",
        "steps": [
            "Defina origem, destino, recurso de transporte e capacidade.",
            "Modele tempo de carregamento, viagem e descarregamento.",
            "Meça fila por transporte, utilização e tempo de entrega.",
            "Teste frota, rota e janelas de atendimento.",
        ],
    },
}


def clean_contract_text(value: str) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""

    if _ftfy_fix_text is not None:
        try:
            text = _ftfy_fix_text(text)
        except Exception:
            pass

    text = text.translate(_TEXT_TRANSLATION)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def normalize_for_intent(value: str) -> str:
    text = clean_contract_text(value).lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_phrase(text: str, phrases: list[str] | tuple[str, ...]) -> bool:
    """Match complete words/phrases so short greetings do not match inside other words."""
    return any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) for phrase in phrases)


def load_history(path: Path, limit: int = 10) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    messages: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
            content = clean_contract_text(str(item.get("content") or ""))
            if content:
                messages.append({"role": item["role"], "content": content})
    return messages[-limit:]


def append_history(path: Path, role: str, content: str) -> None:
    clean_content = clean_contract_text(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"role": role, "content": clean_content}, ensure_ascii=False) + "\n")


def detect_intent(message: str) -> str:
    text = normalize_for_intent(message)
    if not text:
        return "empty"
    if contains_phrase(
        text,
        (
            "resultado",
            "resultados",
            "relatorio",
            "throughput",
            "utilizacao",
            "gargalo",
            "fila critica",
            "formando fila",
            "fila crescendo",
            "fila aumentou",
            "o que faco com a fila",
        ),
    ):
        return "interpret_results"
    if contains_phrase(text, ("statfit", "distribuicao", "ajustar dados", "csv", "amostra", "ks", "aic", "bic")):
        return "statfit"
    if contains_phrase(
        text,
        (
            "revisar modelo",
            "revisar este modelo",
            "revisar o modelo",
            "quero revisar",
            "corrigir modelo",
            "validar modelo",
            "analisar modelo",
            "alerta",
            "rcl",
            "premissa",
        ),
    ):
        return "review_model"
    if contains_phrase(text, ("explicar objeto", "o que e", "para que serve", "entitygenerator", "queue", "server", "branch", "entitysink")):
        return "explain_object"
    if contains_phrase(text, ("defesa", "banca", "orientador", "apresentacao", "justificar")):
        return "defense_checklist"
    if contains_phrase(
        text,
        (
            "criar modelo",
            "criar um modelo",
            "montar modelo",
            "construir modelo",
            "modelar",
            "simulacao",
            "simular",
            "processo",
            "atendentes",
            "clientes chegam",
            "pacientes chegam",
        ),
    ):
        return "create_model"
    if contains_phrase(text, ("oi", "ola", "bom dia", "boa tarde", "boa noite")):
        return "greeting"
    return "general_guidance"


def choose_pattern(message: str, context: str = "") -> dict[str, Any]:
    text = normalize_for_intent(f"{message}\n{context}")
    if any(word in text for word in ["pronto atendimento", "paciente", "triagem", "medico", "hospital"]):
        return PATTERN_CATALOG["pronto_atendimento"]
    if any(word in text for word in ["retrabalho", "inspecao", "reprov", "qualidade"]):
        return PATTERN_CATALOG["inspecao_retrabalho"]
    if any(word in text for word in ["estoque", "reposicao", "demanda", "falta"]):
        return PATTERN_CATALOG["estoque_simples"]
    if any(word in text for word in ["transporte", "rota", "viagem", "entrega"]):
        return PATTERN_CATALOG["transporte"]
    if any(word in text for word in ["linha", "sequencial", "producao", "estacao"]):
        return PATTERN_CATALOG["linha_sequencial"]
    if any(word in text for word in ["multiplos", "varios", "atendentes", "servidores"]):
        return PATTERN_CATALOG["multiplos_servidores"]
    return PATTERN_CATALOG["fila_simples"]


def pattern_key_from_label(label: str) -> str:
    for key, value in PATTERN_CATALOG.items():
        if value["label"] == label:
            return key
    return "fila_simples"


def detect_complexity(message: str, pattern_key: str) -> str:
    text = normalize_for_intent(message)
    if any(word in text for word in ["defesa", "banca", "validacao", "replicacoes", "sensibilidade"]):
        return "defesa"
    if any(word in text for word in ["intermediario", "retrabalho", "prioridade", "multi", "varios", "cenarios", "branch"]):
        return "intermediario"
    if pattern_key in {"pronto_atendimento", "linha_sequencial", "inspecao_retrabalho", "transporte"}:
        return "intermediario"
    return "simples"


def build_jaamsim_steps(pattern: dict[str, Any], complexity: str) -> list[str]:
    label = pattern["label"]
    steps = [
        "Abra File > New, salve o .cfg e confirme a unidade de tempo do modelo.",
        "No Model Builder, crie um SimEntity para representar a entidade e renomeie-o com o nome real do processo.",
        "Arraste um EntityGenerator; no Input Editor > Key Inputs, defina PrototypeEntity e InterArrivalTime.",
        "Arraste uma Queue e ligue o NextComponent do EntityGenerator a essa fila.",
        "Arraste um Server; defina WaitQueue com a fila criada e ServiceTime com valor ou distribuição e unidade.",
        "Arraste um EntitySink e complete os NextComponent até a saída.",
        "Selecione Simulation e defina RunDuration com horizonte e unidade coerentes.",
        "Rode por poucos minutos de tempo simulado e observe se entidades chegam, esperam, são atendidas e saem.",
        "Registre pelo menos espera/fila, utilização do servidor, throughput e tempo no sistema.",
        "Salve, peça 'revisar este modelo' e classifique os alertas RCL antes de alterar a topologia.",
    ]
    if label == "pronto atendimento":
        steps.extend(
            [
                "Separar recepção, triagem e consulta médica em etapas distintas quando houver fila em cada ponto.",
                "Medir espera por etapa, utilização dos recursos e tempo total do paciente no sistema.",
            ]
        )
    elif label == "inspeção e retrabalho":
        steps.extend(
            [
                "Inserir Branch somente depois de documentar probabilidade ou regra de reprovação.",
                "Manter retrabalho como hipótese revisável, sem aceitar alteração automática de topologia.",
            ]
        )
    elif label == "estoque simples":
        steps.extend(
            [
                "Separar demanda, reposição e falta como eventos diferentes.",
                "Medir estoque médio, falta e nível de serviço.",
            ]
        )
    elif label == "transporte":
        steps.extend(
            [
                "Modelar capacidade do transporte e tempo de deslocamento.",
                "Testar frota/rota antes de concluir gargalo.",
            ]
        )
    if complexity in {"intermediario", "defesa"}:
        steps.extend(
            [
                "Criar pelo menos dois cenários: base e alternativa de capacidade/regra operacional.",
                "Exportar ou registrar métricas para interpretação offline de gargalo.",
            ]
        )
    if complexity == "defesa":
        steps.append("Preparar evidência: print do fluxo, dados usados, premissas, resultado base e limitação assumida.")
    return steps


def build_promodel_steps(pattern: dict[str, Any], complexity: str) -> list[str]:
    label = pattern["label"]
    steps = [
        "Criar entidade principal, locais, recurso principal e rota do fluxo.",
        "Configurar chegadas e tempo de processamento com a mesma premissa usada no JaamSim.",
        "Rodar o cenário base e registrar fila, utilização, throughput e tempo no sistema.",
    ]
    if label == "pronto atendimento":
        steps.append("Criar locais separados para recepção, triagem, consulta e saída.")
    elif label == "linha sequencial":
        steps.append("Criar uma localização/processo por estação crítica da linha.")
    elif label == "inspeção e retrabalho":
        steps.append("Configurar roteamento condicional para aprovado/retrabalho com probabilidade documentada.")
    if complexity in {"intermediario", "defesa"}:
        steps.append("Criar cenário alternativo equivalente ao JaamSim para comparação operacional.")
    return steps


def build_evidence_plan(intent: str, pattern: dict[str, Any], complexity: str) -> list[str]:
    plan = [
        "Registrar data, ferramenta usada, modo offline/online e ajuda acionada.",
        "Capturar print do fluxo conceitual e dos objetos principais.",
        "Salvar dados de entrada, distribuição escolhida e premissas em arquivo rastreável.",
    ]
    if intent == "review_model":
        plan.append("Anexar relatório RCL com regras acionadas, decisão humana e pendências.")
    if intent == "interpret_results" or complexity in {"intermediario", "defesa"}:
        plan.append("Anexar interpretação offline de resultados com hipótese, evidência e próximo cenário.")
    if pattern["label"] in {"pronto atendimento", "fila simples", "múltiplos servidores"}:
        plan.append("Registrar tempo de espera, tamanho de fila e utilização do recurso gargalo.")
    if complexity == "defesa":
        plan.append("Separar confirmado, inferido, limitação e próximo teste para banca/orientador.")
    return plan


def format_short_list(items: list[str], limit: int) -> str:
    return " ".join(f"{index + 1}. {item}" for index, item in enumerate(items[:limit]))


def build_guided_model_response(
    pattern: dict[str, Any],
    complexity: str,
    jaamsim_steps: list[str],
    promodel_steps: list[str],
    evidence_plan: list[str],
) -> str:
    return (
        f"Roteiro offline sugerido: padrão {pattern['label']} ({pattern['when']}); complexidade {complexity}.\n\n"
        f"JaamSim: {format_short_list(jaamsim_steps, 10)}\n\n"
        f"ProModel: {format_short_list(promodel_steps, 4)}\n\n"
        f"Evidência: {format_short_list(evidence_plan, 4)}\n\n"
        "Primeiro confirme entidade, chegada, recurso restritivo e métrica principal. Depois rode um cenário base curto antes de comparar alternativas."
    )


def explain_requested_object(message: str) -> str:
    text = normalize_for_intent(message).replace(" ", "")
    for key, guidance in OBJECT_GUIDANCE.items():
        if key in text:
            return guidance
    return (
        "Escolha um objeto JaamSim para explicar, por exemplo EntityGenerator, Queue, Server, "
        "EntityProcessor, Branch ou EntitySink. Eu explico o papel, os dados mínimos e as métricas esperadas."
    )


def build_offline_playbook(
    message: str,
    history: list[dict[str, str]] | None = None,
    model_context: str = "",
) -> dict[str, Any]:
    intent = detect_intent(message)
    prior_context = "\n".join(
        item.get("content", "")
        for item in (history or [])[-6:]
        if item.get("role") in {"user", "assistant"}
    )
    pattern = choose_pattern(message, f"{prior_context}\n{model_context}")
    pattern_key = pattern_key_from_label(pattern["label"])
    complexity = detect_complexity(message, pattern_key)
    jaamsim_steps = build_jaamsim_steps(pattern, complexity)
    promodel_steps = build_promodel_steps(pattern, complexity)
    evidence_plan = build_evidence_plan(intent, pattern, complexity)
    limitations = [
        "Modo offline: não consulta internet, não chama LLM e não altera topologia automaticamente.",
        "Use as respostas como roteiro de modelagem; valide dados reais, premissas e resultados antes da defesa.",
    ]

    if intent == "empty":
        response = "Me diga o processo que você quer modelar ou escolha uma ação: criar modelo, revisar modelo, usar StatFit, interpretar resultados ou checklist defesa."
        next_actions = ["Descrever entidade, recurso principal, chegada e objetivo da simulação."]
        checklist = ["Processo real identificado", "Entidade principal definida", "Objetivo da simulação declarado"]
        suggestions: list[str] = []
    elif intent == "greeting":
        response = "Oi! Posso ajudar offline com um roteiro determinístico para criar, revisar ou defender um modelo no JaamSim. Qual processo você quer simular?"
        next_actions = ["Informar o processo real em uma frase.", "Dizer se quer um modelo simples, intermediário ou de defesa."]
        checklist = ["Processo escolhido", "Nível de detalhe escolhido", "Dado histórico disponível ou hipótese inicial"]
        suggestions = [pattern["label"]]
    elif intent == "statfit":
        response = (
            "Para usar StatFit com segurança, separe uma coluna numérica limpa e identifique o tipo da variável: "
            "chegada, atendimento, contagem, retrabalho, demanda ou prioridade. O melhor KS/AIC/BIC é uma hipótese, "
            "não uma decisão automática; compare com a plausibilidade do processo."
        )
        next_actions = [
            "Colar ou anexar a amostra numérica.",
            "Confirmar se os dados representam tempo, contagem ou proporção.",
            "Comparar ranking estatístico com conhecimento do processo real.",
        ]
        checklist = ["Amostra numérica limpa", "Unidade conhecida", "Outliers revisados", "Distribuição plausível para o processo"]
        suggestions = ["chegada: exponencial/Poisson quando aleatória", "atendimento: triangular, lognormal, gamma ou normal conforme variação"]
    elif intent == "review_model":
        response = (
            "Na revisão offline, eu verificaria primeiro estrutura mínima, fluxo fonte-saída, filas sem atendimento, "
            "recursos sem uso, decisões sem regra e métricas desalinhadas ao objetivo. Nenhuma conexão deve ser criada automaticamente."
        )
        next_actions = ["Gerar snapshot do modelo.", "Rodar RCL offline.", "Classificar cada alerta como procede, falso positivo ou pendente."]
        checklist = ["Origem conectada", "Fila atendida", "Processo com recurso/tempo", "Saída definida", "Métricas alinhadas", "Premissas documentadas"]
        suggestions = ["Aplicar apenas sugestões de metadados/premissas após aceite humano."]
    elif intent == "interpret_results":
        response = (
            "Para interpretar resultados offline, procure primeiro utilização alta, fila crescente, espera elevada, throughput baixo "
            "e diferença entre cenários. Um gargalo provável aparece quando a etapa tem alta utilização e alimenta uma fila crítica."
        )
        next_actions = ["Anexar CSV/JSON/DAT de resultados.", "Comparar utilização e espera por etapa.", "Propor um cenário de capacidade ou regra operacional."]
        checklist = ["Resultados exportados", "Unidades conferidas", "Cenário base identificado", "Gargalo e evidência separados"]
        suggestions = ["Testar aumento de capacidade na etapa crítica", "Testar redução de variabilidade ou mudança de regra de fila"]
    elif intent == "explain_object":
        response = explain_requested_object(message)
        next_actions = ["Relacionar o objeto explicado com entidade, fila, recurso ou saída do seu processo."]
        checklist = ["Papel do objeto entendido", "Entrada e saída do objeto identificadas", "Parâmetro mínimo definido"]
        suggestions = ["Pedir exemplo do objeto aplicado ao seu processo."]
    elif intent == "defense_checklist":
        response = (
            "Para defender o modelo, separe problema, escopo, entidade, recursos, dados, distribuições, premissas, regras de decisão, "
            "métricas, cenários e limitações. Mostre que o modo offline apoia aprendizado e auditoria mesmo sem API."
        )
        next_actions = ["Preparar um slide com fluxo conceitual.", "Preparar um slide com dados/StatFit.", "Preparar um slide com validação e limitações."]
        checklist = ["Problema claro", "Modelo conceitual", "Dados e premissas", "Evidência de teste", "Limites assumidos", "Próximo trabalho"]
        suggestions = ["Usar NAT17 como evidência de replicabilidade acadêmica."]
    else:
        response = build_guided_model_response(pattern, complexity, jaamsim_steps, promodel_steps, evidence_plan)
        next_actions = [
            "Confirmar entidade principal.",
            "Definir como ela chega ao sistema.",
            "Definir recurso/etapa que pode virar gargalo.",
            "Escolher métrica principal para validar o objetivo.",
        ]
        checklist = ["Entidade", "Chegada", "Fila", "Recurso", "Tempo de serviço", "Saída", "Métrica"]
        suggestions = [pattern["label"], *pattern["steps"][:2]]

    return {
        "mode": "offline_playbook",
        "intent": intent,
        "response": clean_contract_text(response),
        "next_actions": next_actions,
        "checklist": checklist,
        "suggestions": suggestions,
        "pattern": pattern["label"],
        "complexity": complexity,
        "jaamsim_steps": jaamsim_steps,
        "promodel_steps": promodel_steps,
        "evidence_plan": evidence_plan,
        "limitations": limitations,
    }


def fallback_response(message: str) -> str:
    return build_offline_playbook(message)["response"]


def build_messages(message: str, history: list[dict[str, str]], model_context: str) -> list[dict[str, str]]:
    context = model_context.strip() or "Contexto do modelo JaamSim ainda não informado."
    user_content = f"Contexto atual do JaamSim:\n{context}\n\nMensagem do operador:\n{message}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": user_content}]


def offline_chat_payload(
    user_message: str,
    *,
    history: list[dict[str, str]] | None = None,
    model_context: str = "",
    attempts: list[dict[str, Any]] | None = None,
    note: str,
    ok: bool,
) -> dict[str, Any]:
    playbook = build_offline_playbook(user_message, history=history, model_context=model_context)
    append_history_args = playbook["response"]
    return {
        "ok": ok,
        "online": False,
        "response": append_history_args,
        "selected_provider": None,
        "selected_model": None,
        "attempts": attempts or [],
        "note": note,
        **playbook,
    }


def run_chat(args: argparse.Namespace) -> dict[str, Any]:
    user_message = clean_contract_text(args.message)
    model_context = clean_contract_text(args.model_context or "")
    history = load_history(args.history_file)
    append_history(args.history_file, "user", user_message)

    if args.dry_run:
        payload = offline_chat_payload(
            user_message,
            history=history,
            model_context=model_context,
            note="dry_run",
            ok=True,
        )
        append_history(args.history_file, "assistant", payload["response"])
        return payload

    candidates = tcc_llm_assist.configured_candidates(args.provider_order, args.env_file)
    if args.require_online and not candidates:
        return {
            "ok": False,
            "online": False,
            "response": "",
            "selected_provider": None,
            "selected_model": None,
            "attempts": [],
            "note": "online_required_no_provider",
        }

    messages = build_messages(user_message, history, model_context)
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            content, tokens, latency_ms = tcc_llm_assist.call_chat_completion(
                candidate,
                messages,
                temperature=0.35,
                max_tokens=args.max_tokens,
            )
            response = clean_contract_text(content) or clean_contract_text(fallback_response(user_message))
            append_history(args.history_file, "assistant", response)
            attempts.append(
                {
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "ok": True,
                    "latency_ms": latency_ms,
                    "tokens": tokens,
                }
            )
            return {
                "ok": True,
                "online": True,
                "response": response,
                "selected_provider": candidate.provider,
                "selected_model": candidate.model,
                "attempts": attempts,
            }
        except Exception as exc:
            attempts.append(
                {
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "ok": False,
                    "error": str(exc)[:300],
                }
            )

    if args.require_online:
        return {
            "ok": False,
            "online": False,
            "response": "",
            "selected_provider": None,
            "selected_model": None,
            "attempts": attempts,
            "note": "online_required_failed",
        }

    payload = offline_chat_payload(
        user_message,
        history=history,
        model_context=model_context,
        attempts=attempts,
        note="fallback_local",
        ok=False,
    )
    append_history(args.history_file, "assistant", payload["response"])
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat LLM opcional para o assistente nativo JaamSim.")
    parser.add_argument("--message", required=True)
    parser.add_argument("--history-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--model-context", default="")
    parser.add_argument("--provider-order", default=tcc_llm_assist.DEFAULT_PROVIDER_ORDER)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-online", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = run_chat(args)
    output_path = args.output_dir / f"{args.case_id}_chat_last_response.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
