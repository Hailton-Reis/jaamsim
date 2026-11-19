# JAAM-AI C2 v0.4 — aba Java/Swing de pré-validação documental

**Status:** `CANDIDATE_ONLY / G0_G2_PENDING / JAVA_HEADLESS_CONTRACT / GUI_WINDOWS_PENDING / NOT_CONFIRMATORY`.

## Integração prevista

A janela existente `AIAssistantBox.java` recebe **uma única nova aba**: **Documentos C2 (prévia)**. As abas Conversa e Configurações, o botão Enviar, os fluxos RCL, StatFit, as opções 1–11 do CMD e o companion `.jaamsim-ai.zip` não são alterados.

A aba usa `C2PreflightPanel` (SwingWorker fora da EDT) e `C2PreflightRunner` (subprocesso Python **sem shell**), exclusivamente para `c2_chat_bridge.py`. Não há criação nem edição de objetos do JaamSim, leitura de `.cfg`, histórico comum do chat, acesso a provedores LLM ou ferramentas de estado.

O comando é montado como uma lista de argumentos (não como texto de shell):

```
<JAAMSIM_PYTHON|jaamsim.python|python> -E -s \
  <JAAMSIM_ASSISTANT_ROOT>/python/c2_chat_bridge.py \
  --message=<pergunta> \
  --corpus-root=<pasta> --manifest=<manifesto> \
  --top-k=3 --max-context-chars=8000
```

`-E` ignora PYTHONPATH/PYTHONHOME, e `-s` impede usar site-packages do usuário. As importações de arquivos Python do módulo continuam sendo feitas do diretório do script. A raiz da extensão é **explícita e obrigatória** via `JAAMSIM_ASSISTANT_ROOT` (prioritária) ou `-Djaamsim.assistant.root`, sem busca perto do modelo em aberto. O interpretador segue a precedência definida pelo launcher. O CMD original/manifesto nativo continuam sendo a barreira de integridade para um eventual empacotamento.

A aba permite selecionar a pasta documental e um manifesto; a integridade SHA-256 dos documentos é verificada pelo C2 Python, e o SHA-256 do manifesto é conferido também pelo Java antes e depois da consulta. Arquivos e pastas finais selecionados não podem ser links simbólicos. O processo tem limite de 35 segundos e saída JSON limitada a 256 KiB. Falhas fecham a consulta sem recorrer à análise do modelo ou ao modo online.

## Saída da interface

O Java aceita **somente** `schema=jaam.ai.c2.chat_preflight.v1`, `status=PREFLIGHT_ONLY`, `gate=G0_G2_PENDING_NO_MODEL_EXECUTION`, `arm_id=C2`, `model_calls=0`, `state_tool_calls=0`, `write_model=false`, `read_tools=[]`, `exposed_capabilities=[search_docs]`, recibo do mesmo corpus, hash da consulta e citações com hash de passagem. Resultados são exibidos como **texto plano não confiável**; não são resposta de um LLM. Sem evidência, a aba informa que a resposta fundamentada deve se abster.

O processo Python prepara um envelope com mensagens para uso experimental futuro, mas a aba Java **não envia esse envelope a nenhum provedor** e não armazena token ou segredo.

## Verificação realizada em cópia isolada

- Testes Python C2 completos (v0.2, v0.3 e pré-validação de chamada Java), usando corpus sintético: ver `RESULTADOS_C2_V04.json`.
- Contratos Java em modo headless para o novo runner; compilação com JDK 21 contra *stubs exclusivamente de compilação* das classes JSON do JaamSim e `AssistantLaunchSettings`. Esses stubs NÃO fazem parte do pacote e NÃO substituem a compilação contra o JaamSim real.
- Comando real de Python `-E -s` validado em subprocesso com adaptador local sintético; sem GUI.
- Patch ancorado no trecho da `AIAssistantBox.java` da branch `fix/jaam-ai-resource-provenance-20261113` observado em 19/11/2026.

## Limitações e próximos gates

1. **Ainda falta compilar o JaamSim completo** com a aba nova usando JDK 25/Ant na branch real. A compilação dos dois arquivos com stubs não prova compatibilidade integral.
2. **Ainda falta o teste visual no Windows**: abrir a nova aba, escolher corpus, recuperar, citar, buscar sem evidências, e fechar/abrir a janela sem regressão.
3. **G0/G2 permanecem pendentes**; não iniciar execução do LLM, estudo fatorial C1–C4, P004, Full45, benchmark confirmatório nem aprovação científica por conta desta candidata.
4. O corpus sintético não representa as fontes oficiais, tampouco valida desempenho, precisão, robustez total ou segurança sob host comprometido.
5. A v0.69 privada e a v0.50 ativa permanecem intocadas, assim como atalho, Drive, PR #1 e produção.

## Instalação em laboratório (não na pasta ativa)

Partir de **um clone separado** da branch de referência. Aplicar o patch completo v0.4 se as versões C2 anteriores ainda não estiverem presentes; se v0.3 já estiver, aplicar só o patch incremental. Validar com `git apply --check` antes. **Não executar em `00_PROJETO_ATUAL`** nem atualizar o CMD sem novo manifesto/versionamento e aceitação.
