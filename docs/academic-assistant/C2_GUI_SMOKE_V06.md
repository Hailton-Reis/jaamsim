# JAAM-AI C2 v0.6 — testes de interface sintéticos, sem promoção

**Status:** `CANDIDATE_ONLY / G0_G2_PENDING / P004_DENY / FULL45_NO_GO / GUI_WINDOWS_MANUAL_PENDING`.

## Escopo

O painel `Documentos C2 (prévia)` continua independente do chat principal e do estado do JaamSim. O teste `C2PreflightSwingSmokeTest` exercita uma instância real de `C2PreflightPanel` e o subprocesso Python usando **somente** `examples/c2-preflight/` (documentos sintéticos). Não acessa `.cfg`, não executa RCL, não chama LLM e não edita modelos.

## Mudanças de UX e consistência

- Organização compacta: nota e campos no topo, resultados ocupando a área central restante.
- Editar pergunta, corpus ou manifesto remove imediatamente citações anteriores.
- Se qualquer parâmetro mudar durante a consulta assíncrona, o retorno antigo é descartado, mesmo que o Python conclua com sucesso.
- Erros de integridade não reaproveitam passagens da busca anterior.

## Evidências automatizadas e limitações

1. **Linux/Xvfb com Swing real:** cria JFrame, edita os campos, clica no botão, espera o `SwingWorker`, valida citação sintética, ausência de evidência e bloqueio após adulterar uma **cópia descartável** do corpus; registra PNGs da interface. Isso testa desenho e comportamento da aba num display virtual, **não** representa aceite da GUI principal no Windows.
2. **Windows GitHub Actions, headless:** cria o painel Swing (`JPanel`) sem `JFrame`, e executa os mesmos cenários por Java→Python, com Java 25 e Python 3.11. Isso testa compatibilidade com subprocessos e caminhos do Windows, **não** garante que uma janela gráfica real abrirá na máquina do operador.
3. **Contrato de segurança:** sem acesso ao modelo, ferramentas de estado ou inferência científica. O filtro de variáveis de ambiente diminui exposição acidental, mas não constitui sandbox ou atestado criptográfico do host.
4. **Proveniência:** PNGs são capturas do ambiente CI (quando o workflow concluir). Hashes do JAR e dos arquivos do corpus pertencem ao artefato e ao manifesto da execução em questão. Não assumir que o pacote privado v0.69 está atualizado com esta branch.

## Etapas obrigatórias antes de qualquer homologação

- CI da branch/PR aprovada; verificar exatamente o commit e os artefatos resultantes.
- Abrir JaamSim Java/Swing em **Windows real**, numa pasta de laboratório isolada, verificar que as abas `Conversa`, `Documentos C2 (prévia)` e `Configurações` aparecem e que o botão funciona sem travar a interface.
- Verificar os casos positivo, sem evidência, alteração de entrada durante busca, corrupção do corpus, encerramento e tentativa com caminhos inválidos.
- Confirmar que o `.cfg` original não mudou (hash antes/depois), que nenhum arquivo oficial foi incorporado e que P004/Full45 não foi acionado.
- Somente após aceite humano explícito considerar promoção, sem sobrescrever automaticamente o launcher `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd` nem a versão operacional do Drive.

**Não há resultados científicos confirmatórios C1–C4 neste documento.**
