#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""
Assistente de briefing para criar PRD interno de simulacoes JaamSim.

Este modulo transforma uma ideia livre em artefatos apresentaveis:
historia da simulacao, PRD interno, epicos/stories, perguntas ao operador,
plano de dados/StatFit e guardrails de alteracao. Por padrao roda em dry-run
deterministico. Com --online, usa provedores LLM locais configurados no .env,
sem imprimir ou versionar tokens.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import tcc_llm_assist

import assistant_paths


TOOLS_DIR = Path(__file__).resolve().parent
ASSISTANT_ROOT = TOOLS_DIR.parent
DEFAULT_OUTPUT_DIR = assistant_paths.OUTPUT_DIR / "briefing"

DEFAULT_IDEA = (
    "Quero simular um pronto atendimento hospitalar com chegada de pacientes, "
    "triagem, consulta, exames opcionais e alta, avaliando tempo de espera, "
    "utilizacao dos medicos e gargalos do fluxo."
)


def slugify(value: str, *, default: str = "simulacao") -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:60] or default


def read_idea(args: argparse.Namespace) -> str:
    if args.idea_file:
        idea = args.idea_file.read_text(encoding="utf-8").strip()
    elif args.idea:
        idea = args.idea.strip()
    else:
        idea = DEFAULT_IDEA
    if len(idea) < 20:
        raise ValueError("A ideia precisa ter ao menos 20 caracteres para gerar um briefing util.")
    return idea


def build_local_briefing(idea: str, case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "source": "deterministic_scaffold",
        "idea_original": idea,
        "resumo_executivo": (
            "Briefing inicial criado a partir da ideia do operador. O conteudo deve ser "
            "revisado antes de virar modelo JaamSim, mas ja organiza escopo, dados, "
            "perguntas e proximas acoes."
        ),
        "historia_simulacao": {
            "titulo": "Historia da simulacao",
            "narrativa": [
                f"O operador deseja construir uma simulacao baseada nesta ideia: {idea}",
                "A simulacao deve representar entidades que entram no sistema, passam por processos, disputam recursos e geram metricas de desempenho.",
                "O foco da primeira versao e criar um modelo pequeno, verificavel e comparavel, antes de adicionar regras avancadas.",
            ],
            "decisoes_iniciais": [
                "Separar objetivo, entidades, recursos, filas, processos e metricas antes de abrir o JaamSim.",
                "Usar dados reais quando existirem; quando nao existirem, registrar premissas e rodar cenarios controlados.",
                "Manter alteracoes automaticas fora da topologia: a IA sugere, o operador decide.",
            ],
        },
        "perguntas_ao_operador": [
            "Qual e o objetivo principal da simulacao e qual decisao ela deve apoiar?",
            "Quais entidades entram no sistema e como elas chegam?",
            "Quais recursos limitados existem e quais filas podem se formar?",
            "Quais tempos de processo possuem dados historicos ou estimativas confiaveis?",
            "Quais metricas definem sucesso: espera, utilizacao, throughput, custo, SLA ou gargalo?",
            "Quais regras de negocio mudam o fluxo normal?",
            "Quais cenarios devem ser comparados na defesa ou validacao?",
            "Quais partes ainda sao lacunas e precisam de entrevista, medicao ou premissa explicita?",
        ],
        "prd_interno": {
            "objetivo": "Converter a ideia do operador em uma simulacao discreta pequena, auditavel e evolutiva.",
            "usuarios": ["Modelador iniciante", "Modelador experiente", "Professor/orientador", "Avaliador da defesa"],
            "escopo_incluido": [
                "Modelo conceitual com entidades, filas, recursos, processos e metricas.",
                "Roteiro de construcao incremental no JaamSim.",
                "Plano de dados para distribuicoes de entrada com apoio do modulo StatFit-like.",
                "Guardrails para sugestoes de IA e alteracoes aceitas pelo operador.",
            ],
            "escopo_excluido": [
                "Criacao automatica de objetos JaamSim pela IA.",
                "Validacao estatistica definitiva sem revisao humana.",
                "Uso obrigatorio de internet para funcoes locais deterministicas.",
            ],
            "entidades_provaveis": ["Entidade de chegada", "Fila", "Servidor/recurso", "Processo", "Saida"],
            "metricas": ["Tempo de espera", "Tempo no sistema", "Utilizacao de recursos", "Tamanho de fila", "Throughput"],
            "criterios_de_aceite": [
                "O operador consegue explicar objetivo, fluxo e metricas sem depender da IA.",
                "O modelo inicial roda com parametros rastreaveis.",
                "Toda sugestao aplicada possui registro de aceite ou rejeicao.",
                "Dados importados no StatFit-like seguem formato documentado.",
            ],
            "lacunas": [
                "Dados de entrada reais ou estimados.",
                "Regras especificas do dominio.",
                "Criterios de validacao com especialista ou literatura.",
            ],
        },
        "epicos": [
            {
                "id": "EPIC-01",
                "titulo": "Briefing e entendimento do dominio",
                "stories": [
                    "Como operador, quero registrar a ideia livre da simulacao para nao perder contexto.",
                    "Como operador, quero responder perguntas guiadas para transformar a ideia em requisitos verificaveis.",
                ],
            },
            {
                "id": "EPIC-02",
                "titulo": "PRD interno e roteiro de construcao",
                "stories": [
                    "Como operador, quero um PRD interno com objetivo, escopo, entidades e metricas.",
                    "Como operador, quero um roteiro incremental para construir o modelo sem pular validacoes.",
                ],
            },
            {
                "id": "EPIC-03",
                "titulo": "Dados de entrada e StatFit-like",
                "stories": [
                    "Como operador, quero importar CSV/TXT numerico para estimar distribuicoes candidatas.",
                    "Como operador, quero receber um snippet JaamSim sugerido para revisar manualmente.",
                ],
            },
            {
                "id": "EPIC-04",
                "titulo": "Guardrails e sugestoes auditaveis",
                "stories": [
                    "Como operador, quero aceitar ou rejeitar sugestoes antes de qualquer modificacao.",
                    "Como operador, quero limitar alteracoes automaticas a valores e parametros seguros.",
                ],
            },
            {
                "id": "EPIC-05",
                "titulo": "Analise final e defesa",
                "stories": [
                    "Como pesquisador, quero consolidar resultados e limites para o estudo.",
                    "Como pesquisador, quero evidencias reproduziveis para apresentar a banca.",
                ],
            },
        ],
        "plano_statfit": {
            "papel": "Modulo auxiliar offline para apoiar distribuicoes de entrada antes da simulacao.",
            "formato_recomendado": "CSV com cabecalho e uma coluna numerica por variavel analisada.",
            "exemplo_csv": "tempo_atendimento\n12.4\n13.1\n11.8\n15.0\n",
            "saida_esperada": [
                "Ranking de distribuicoes candidatas.",
                "Relatorio Markdown/JSON.",
                "Snippet .cfg sugerido para revisao manual no JaamSim.",
            ],
            "limite": "Nao substitui validacao estatistica formal nem julgamento do modelador.",
        },
        "guardrails": [
            "A IA pode perguntar, organizar, explicar e sugerir.",
            "A IA nao deve criar objetos, apagar objetos ou alterar topologia automaticamente.",
            "Alteracoes automaticas, quando existirem, devem ficar restritas a valores/parametros permitidos.",
            "Toda sugestao deve ter aceite/rejeicao do operador e trilha de auditoria.",
            "Funcoes locais deterministicas devem funcionar offline; LLM e camada opcional.",
        ],
        "roteiro_construcao": [
            "Validar objetivo e perguntas com o operador.",
            "Criar modelo conceitual minimo.",
            "Separar dados de chegada e atendimento para analise StatFit-like.",
            "Construir primeira versao JaamSim com poucos objetos.",
            "Rodar simulacao, coletar metricas e revisar alertas do modulo IA.",
            "Registrar decisoes, lacunas e proximas iteracoes.",
        ],
    }


def build_llm_messages(local_briefing: dict[str, Any]) -> list[dict[str, str]]:
    schema_hint = {
        "case_id": "string",
        "source": "llm_assisted",
        "resumo_executivo": "string",
        "historia_simulacao": {
            "titulo": "string",
            "narrativa": ["string"],
            "decisoes_iniciais": ["string"],
        },
        "perguntas_ao_operador": ["string"],
        "prd_interno": {
            "objetivo": "string",
            "usuarios": ["string"],
            "escopo_incluido": ["string"],
            "escopo_excluido": ["string"],
            "entidades_provaveis": ["string"],
            "metricas": ["string"],
            "criterios_de_aceite": ["string"],
            "lacunas": ["string"],
        },
        "epicos": [{"id": "EPIC-01", "titulo": "string", "stories": ["string"]}],
        "plano_statfit": {
            "papel": "string",
            "formato_recomendado": "string",
            "exemplo_csv": "string",
            "saida_esperada": ["string"],
            "limite": "string",
        },
        "guardrails": ["string"],
        "roteiro_construcao": ["string"],
    }
    system_prompt = (
        "Voce e um arquiteto de simulacao discreta, JaamSim e produto academico. "
        "Transforme a ideia do operador em artefatos de trabalho. Nao invente dados "
        "como se fossem coletados. Marque lacunas quando faltar informacao. A IA "
        "pode sugerir, perguntar e organizar, mas nao pode criar objetos, apagar "
        "objetos ou alterar topologia automaticamente. Responda somente JSON valido, "
        "sem markdown fora do JSON."
    )
    user_prompt = (
        "Gere uma versao melhorada do briefing abaixo no schema informado.\n\n"
        "Schema esperado:\n"
        f"{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n\n"
        "Briefing base:\n"
        f"{json.dumps(local_briefing, ensure_ascii=False, indent=2)}"
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def extract_json_object(raw_content: str) -> dict[str, Any] | None:
    raw_content = raw_content.strip()
    candidates = [raw_content]
    start = raw_content.find("{")
    end = raw_content.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw_content[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def run_llm_briefing(
    local_briefing: dict[str, Any],
    *,
    provider_order: str | None,
    env_file: Path | None,
    max_tokens: int,
    dry_run: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = tcc_llm_assist.configured_candidates(provider_order, env_file)
    attempts: list[tcc_llm_assist.ProviderAttempt] = []
    if dry_run:
        attempts = [
            tcc_llm_assist.ProviderAttempt(
                provider=candidate.provider,
                model=candidate.model,
                ok=False,
                latency_ms=0.0,
                tokens=0,
                error="dry_run",
            )
            for candidate in candidates
        ]
        return local_briefing, {
            "online": False,
            "selected_provider": None,
            "selected_model": None,
            "attempts": [asdict(attempt) for attempt in attempts],
            "raw_content_saved": False,
            "note": "DRY RUN: chamada LLM nao executada.",
        }

    messages = build_llm_messages(local_briefing)
    raw_content = ""
    for candidate in candidates:
        try:
            content, tokens, latency_ms = tcc_llm_assist.call_chat_completion(
                candidate,
                messages,
                temperature=0.2,
                max_tokens=max_tokens,
            )
            attempts.append(
                tcc_llm_assist.ProviderAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    ok=True,
                    latency_ms=latency_ms,
                    tokens=tokens,
                )
            )
            raw_content = content
            parsed = extract_json_object(content)
            if parsed:
                parsed.setdefault("case_id", local_briefing["case_id"])
                parsed.setdefault("idea_original", local_briefing["idea_original"])
                parsed["source"] = "llm_assisted"
                return parsed, {
                    "online": True,
                    "selected_provider": candidate.provider,
                    "selected_model": candidate.model,
                    "attempts": [asdict(attempt) for attempt in attempts],
                    "raw_content_saved": False,
                    "note": "Resposta LLM parseada como JSON.",
                }
            fallback = dict(local_briefing)
            fallback["llm_raw_content"] = content
            fallback["source"] = "deterministic_scaffold_with_unparsed_llm"
            return fallback, {
                "online": True,
                "selected_provider": candidate.provider,
                "selected_model": candidate.model,
                "attempts": [asdict(attempt) for attempt in attempts],
                "raw_content_saved": True,
                "note": "Resposta LLM nao estava em JSON valido; scaffold local preservado.",
            }
        except Exception as exc:
            attempts.append(
                tcc_llm_assist.ProviderAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    ok=False,
                    latency_ms=0.0,
                    tokens=0,
                    error=str(exc)[:500],
                )
            )
    fallback = dict(local_briefing)
    if raw_content:
        fallback["llm_raw_content"] = raw_content
    return fallback, {
        "online": True,
        "selected_provider": None,
        "selected_model": None,
        "attempts": [asdict(attempt) for attempt in attempts],
        "raw_content_saved": bool(raw_content),
        "note": "Nenhum provedor LLM retornou uma resposta utilizavel; scaffold local preservado.",
    }


def bullet_lines(items: list[Any]) -> list[str]:
    return [f"- {item}" for item in items]


def render_prd_markdown(briefing: dict[str, Any]) -> str:
    prd = briefing["prd_interno"]
    lines = [
        f"# PRD interno - {briefing['case_id']}",
        "",
        "> Documento operacional de uma simulacao especifica. Nao substitui revisao humana.",
        "",
        "## Ideia original",
        "",
        briefing.get("idea_original", ""),
        "",
        "## Objetivo",
        "",
        prd.get("objetivo", ""),
        "",
        "## Usuarios",
        "",
        *bullet_lines(prd.get("usuarios", [])),
        "",
        "## Escopo incluido",
        "",
        *bullet_lines(prd.get("escopo_incluido", [])),
        "",
        "## Escopo excluido",
        "",
        *bullet_lines(prd.get("escopo_excluido", [])),
        "",
        "## Entidades provaveis",
        "",
        *bullet_lines(prd.get("entidades_provaveis", [])),
        "",
        "## Metricas",
        "",
        *bullet_lines(prd.get("metricas", [])),
        "",
        "## Criterios de aceite",
        "",
        *bullet_lines(prd.get("criterios_de_aceite", [])),
        "",
        "## Lacunas",
        "",
        *bullet_lines(prd.get("lacunas", [])),
        "",
    ]
    return "\n".join(line.rstrip() for line in lines)


def render_history_markdown(briefing: dict[str, Any]) -> str:
    history = briefing["historia_simulacao"]
    lines = [
        f"# Historia da simulacao - {briefing['case_id']}",
        "",
        "## Narrativa",
        "",
        *bullet_lines(history.get("narrativa", [])),
        "",
        "## Decisoes iniciais",
        "",
        *bullet_lines(history.get("decisoes_iniciais", [])),
        "",
        "## Perguntas ao operador",
        "",
        *bullet_lines(briefing.get("perguntas_ao_operador", [])),
        "",
    ]
    return "\n".join(line.rstrip() for line in lines)


def render_epics_markdown(briefing: dict[str, Any]) -> str:
    lines = [
        f"# Epicos e stories - {briefing['case_id']}",
        "",
    ]
    for epic in briefing.get("epicos", []):
        lines.extend(
            [
                f"## {epic.get('id', 'EPIC')} - {epic.get('titulo', '')}",
                "",
                *bullet_lines(epic.get("stories", [])),
                "",
            ]
        )
    return "\n".join(line.rstrip() for line in lines)


def render_consolidated_markdown(briefing: dict[str, Any], metadata: dict[str, Any]) -> str:
    statfit = briefing["plano_statfit"]
    lines = [
        f"# Assistente de briefing - {briefing['case_id']}",
        "",
        "> Prototipo apresentavel para defesa. A IA online e opcional; o scaffold local funciona offline.",
        "",
        "## Execucao",
        "",
        f"- Fonte: `{briefing.get('source', 'desconhecida')}`",
        f"- IA online: `{'sim' if metadata.get('online') else 'nao'}`",
        f"- Provedor selecionado: `{metadata.get('selected_provider') or 'nenhum'}`",
        f"- Modelo selecionado: `{metadata.get('selected_model') or 'nenhum'}`",
        f"- Nota: {metadata.get('note', '')}",
        "",
        "## Resumo executivo",
        "",
        briefing.get("resumo_executivo", ""),
        "",
        "## Perguntas ao operador",
        "",
        *bullet_lines(briefing.get("perguntas_ao_operador", [])),
        "",
        "## Guardrails",
        "",
        *bullet_lines(briefing.get("guardrails", [])),
        "",
        "## Plano StatFit-like",
        "",
        f"- Papel: {statfit.get('papel', '')}",
        f"- Formato recomendado: {statfit.get('formato_recomendado', '')}",
        f"- Limite: {statfit.get('limite', '')}",
        "",
        "```csv",
        statfit.get("exemplo_csv", "").strip(),
        "```",
        "",
        "## Roteiro de construcao",
        "",
        *bullet_lines(briefing.get("roteiro_construcao", [])),
        "",
        "## Artefatos gerados",
        "",
        "- Historia da simulacao.",
        "- PRD interno.",
        "- Epicos e stories.",
        "- JSON auditavel do briefing.",
        "",
    ]
    if briefing.get("llm_raw_content"):
        lines.extend(
            [
                "## Resposta LLM bruta",
                "",
                briefing["llm_raw_content"],
                "",
            ]
        )
    return "\n".join(line.rstrip() for line in lines)


def write_outputs(
    briefing: dict[str, Any],
    metadata: dict[str, Any],
    output_dir: Path,
    *,
    provider_order: str | None = None,
    env_file: Path | None = None,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    case_id = briefing["case_id"]
    payload = {
        "prototype_only": True,
        "publication_policy": "tokens_locais_nao_publicar",
        "provider_status": tcc_llm_assist.provider_status(provider_order, env_file),
        "metadata": metadata,
        "briefing": briefing,
        "generated_at_epoch": int(time.time()),
    }
    files = {
        "json": output_dir / f"{case_id}_briefing_assist.json",
        "markdown": output_dir / f"{case_id}_briefing_assist.md",
        "historia": output_dir / f"{case_id}_historia_simulacao.md",
        "prd": output_dir / f"{case_id}_prd_interno.md",
        "epicos": output_dir / f"{case_id}_epicos_stories.md",
    }
    files["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files["markdown"].write_text(render_consolidated_markdown(briefing, metadata).rstrip() + "\n", encoding="utf-8")
    files["historia"].write_text(render_history_markdown(briefing).rstrip() + "\n", encoding="utf-8")
    files["prd"].write_text(render_prd_markdown(briefing).rstrip() + "\n", encoding="utf-8")
    files["epicos"].write_text(render_epics_markdown(briefing).rstrip() + "\n", encoding="utf-8")
    return {key: str(path) for key, path in files.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera historia da simulacao, PRD interno e epicos/stories.")
    parser.add_argument("--idea", help="Ideia livre da simulacao.")
    parser.add_argument("--idea-file", type=Path, help="Arquivo texto com a ideia/briefing do operador.")
    parser.add_argument("--case-id", help="Identificador dos arquivos gerados.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Diretorio de saida.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Arquivo .env local ignorado.")
    parser.add_argument("--provider-order", default="nvidia,cerebras,groq", help="Ranking/fallback de IA.")
    parser.add_argument("--online", action="store_true", help="Chama IA real. Sem isso, roda dry-run offline.")
    parser.add_argument("--max-tokens", type=int, default=1400, help="Limite de tokens da resposta LLM.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    idea = read_idea(args)
    case_id = args.case_id or slugify(idea.split(".")[0], default="prd_interno")
    local_briefing = build_local_briefing(idea, case_id)
    briefing, metadata = run_llm_briefing(
        local_briefing,
        provider_order=args.provider_order,
        env_file=args.env_file,
        max_tokens=args.max_tokens,
        dry_run=not args.online,
    )
    files = write_outputs(
        briefing,
        metadata,
        args.output_dir,
        provider_order=args.provider_order,
        env_file=args.env_file,
    )
    print("Assistente de briefing - PRD interno")
    print(f"Modo IA online: {'sim' if args.online else 'nao, dry-run'}")
    print(f"Arquivo consolidado: {files['markdown']}")
    print(f"PRD interno: {files['prd']}")
    print(f"Epicos/stories: {files['epicos']}")
    print(f"Historia: {files['historia']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
