# JAAM-AI C2 v0.7 — cancelamento e invalidação de consultas

**Estado:** `CANDIDATE_ONLY / G0_G2_PENDING / P004_DENY / FULL45_NO_GO / GUI_WINDOWS_MANUAL_PENDING`.

## Mudanças de comportamento

- A aba `Documentos C2 (prévia)` passa a exibir um botão **Cancelar**, habilitado somente quando uma consulta estiver em andamento.
- Um cancelamento invalida o resultado e solicita interrupção do `SwingWorker`. No `C2PreflightRunner`, a interrupção de `Process.waitFor` encerra forçadamente o processo Python no bloco `finally`.
- A interface mantém um contador monotônico de edições (`inputRevision`), atualizado pelos `DocumentListener` da pergunta, do corpus e do manifesto. Se uma edição ocorrer durante a busca, o resultado é descartado **mesmo que o usuário volte ao texto original** (caso ABA).
- Nenhuma citação antiga aparece após cancelamento, edição de campos ou falha.

## Verificação automatizada

O teste `C2PreflightSwingSmokeTest` continua usando **somente** o corpus sintético `extensions/academic-assistant/examples/c2-preflight`. Inclui:
1. Busca positiva com citação por linha;
2. Mudança do texto durante a execução e retorno ao valor anterior (ABA);
3. Cancelamento explícito com remoção de evidências;
4. Abstenção sem documentação relevante;
5. Rejeição de corpus adulterado.

O workflow já existente executa o Swing real em Linux/Xvfb e o painel Java em Windows headless (Java 25, Python 3.11). O sucesso automático desses testes **não substitui** abrir a aplicação completa e efetuar o aceite manual no Windows.

## Limites preservados

Este patch não dá acesso a CFG, RCL, ferramentas de estado, API de LLM ou escrita no modelo. `P004` e `Full45` permanecem bloqueados. Nenhuma publicação científica C1–C4 é autorizada. Não substitui o CMD principal ou o software operacional.

## Próximo gate

Testar o JAR desta branch no Windows gráfico real, com capturas verificáveis do fluxo C2: positivo, ausência de evidência, cancelamento, ABA, adulteração e confirmações de que o modelo CFG não mudou.
