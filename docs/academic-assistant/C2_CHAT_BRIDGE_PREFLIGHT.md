# JAAM-AI — C2 Chat Bridge v0.3 (pré-validação isolada)

**Objetivo:** conectar o *contrato de prompt* do `simulation_chat_assist.py` à busca documental C2 sem executar o modelo de linguagem, sem consultar o `.cfg` ativo e sem expor ferramentas de estado.

O adaptador `c2_chat_bridge.py` importa somente a constante `simulation_chat_assist.SYSTEM_PROMPT`. Ele **não chama** `run_chat`, `configured_candidates`, serviços externos, GUI, Java, `parse_cfg`, `run_rcl`, `inspect_model`, `compare_results`, ferramentas de proposta ou de escrita. Não carrega o histórico de conversa nem o contexto do modelo aberto. A consulta do usuário é usada apenas em `search_docs` e na construção de um envelope de mensagens.

## Uso para revisão técnica (em cópia isolada)

Na pasta `extensions/academic-assistant`:

```bash
python python/c2_chat_bridge.py \
  --corpus-root examples/c2-preflight/corpus \
  --manifest examples/c2-preflight/manifest.json \
  --message 'Qual é a função da Queue e do Server?'
python -m pytest -q python/tests/test_c2_*.py
```

O resultado JSON em `stdout` tem `schema=jaam.ai.c2.chat_preflight.v1`, `status=PREFLIGHT_ONLY`, `model_calls=0`, `state_tool_calls=0`, `model_execution_authorized=false`, `messages_sha256`, fontes, citações, recibo e envelope `model_messages` **ainda não enviado** a qualquer provedor.

Os textos recuperados aparecem exclusivamente como dados com selo `UNTRUSTED_RETRIEVED_DOCUMENT`. Uma política fixa (papel `system`) informa que conteúdo documental não é instrução. Isso é um controle de preparação, **não** uma garantia de que todo LLM obedecerá a esse controle. A qualidade factual de uma eventual resposta LLM não foi medida.

## Limites e bloqueios

- **C2**: permitido `search_docs`; **sem** ferramentas de estado, **sem** escrita de modelo.
- **G0/G2**: pendentes, portanto sem chamada LLM ou benchmark confirmatório.
- **C3/C4**: fora do escopo. Não existem rotas indiretas via busca para o mecanismo RCL ou CFG.
- Não instalar sobre `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd` e não alterar v0.69, o atalho, a GUI Java nem o PR existente automaticamente.
- A biblioteca legada `simulation_chat_assist.py` **não foi modificada**: só a importação de um texto constante a reutiliza. A integração do comando à GUI Java e o controle do modo experimental ainda estão pendentes.
- Documentos usados nos testes são sintéticos. Não provaram precisão científica, generalização, funcionamento Windows real nem segurança contra um host comprometido.

## Próximos gates

1. Revisar com orientador a definição do braço C2, os documentos permitidos e o tratamento de citações e abstenção.
2. Inserir o acionamento explícito do bridge na GUI, exclusivamente em modo de pré-validação, numa branch isolada.
3. Validar em GitHub Actions Linux/Windows, depois testar a GUI real no Windows; somente após critérios G0/G2 reavaliar a possibilidade de chamadas de modelo.
