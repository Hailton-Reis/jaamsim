# JAAM-AI — CMD central original com modulo nativo integrado

**Fonte do launcher central:** Google Drive privado `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`.
O usuario ja tem um atalho para este **mesmo nome e caminho**. Nao criar
`RODAR_WINDOWS.cmd`, outro `RODAR_JAAM_AI_COMPLETO.cmd` no GitHub
nem outro atalho.

## Evolucao preservando as funcoes existentes

- v0.50: controle historico imutavel, SHA-256
  `ade157d85582a791b6600dc19b611d00535bb58f16b51c3c416c8cd8de5d3931`.
- v0.51: candidata privada gerada a partir da v0.50, mantem opcoes
  1-7 e acrescenta 8-11; SHA-256
  `8623ed572d69e1c43959ebc4285b5ebee7d04bbf6e002dba52eb257e17c09981`.
- **v0.52**: candidata privada (sem instalacao no Windows), mesma
  `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`, 1-11 intactas,
  com protecao fail-closed antes de chamar o modulo Java ou Python.
  SHA-256 do CMD:
  `d00cf3dcec3cf65fe554e2e6d0503ca07fb065c4e7a15b9b56e32006faf7314b`.

- v0.53: candidata privada com pasta nativa unica, confirmacao sob demanda
  de Java 25+ na opcao 8 e de Python 3.11+ na opcao 9; SHA-256
  `b44b3f5e5c64c6725d211718c332efc9f9c85089ea81b4dcdba22bd893225fc5`.
- **v0.54 (candidata atual, nao instalada):** preserva o mesmo CMD e menu,
  resolve **um Python 3.11+** para ambas as janelas Java e o motor RCL,
  verifica paths relativos de .cfg desde a pasta do CMD e confere hash
  SHA-256 do arquivo antes e depois da revisao, sem edicao automatica.
  SHA-256 do CMD:
  `a72f348860e88a6395e347e9134c9b1de2f7d28fcf51dbdb9e4627903063c3b5`.

| Escolha do menu central | Comportamento |
|---|---|
| Enter/1 | Somente observar; nao iniciar processos |
| 2-5 | Operacoes MC-001 anteriores, com confirmacao e restricoes originais |
| 6 | Ensaio offline legado |
| 7 | Prontidao P004: **DENY** (nao executa inferencia) |
| 8 | Abrir JaamSim Java com IA/StatFit **apos integridade** |
| 9 | Revisar CFG pelo motor offline RCL **apos integridade**, sem editar o modelo |
| 10 | Abrir pasta local de relatorios |
| 11 | Mostrar status e verificacao dos arquivos do modulo, sem abrir aplicativos |

Desde v0.52, o CMD fixa o SHA-256 do arquivo
`JAAM_AI_NATIVE/MANIFEST_SHA256.json` como
`61b18f7d89f345e212e761514e1f292303e93722daf82bfc54d912287357e180`.
O manifesto tem **37 arquivos** e registra SHA-256/tamanho de cada
um. O controlador verifica o manifesto, os 37 caminhos (rejeita traversal),
a existencia, o tamanho e SHA-256 de cada arquivo. Se algo difere,
**bloqueia as opcoes 8 e 9**, sem tentar reparar automaticamente.
O status 11 permite observar o bloqueio com seguranca.
O modulo corresponde ao ZIP produzido pelo
[CI do GitHub](https://github.com/Hailton-Reis/jaamsim/actions/runs/43657257078).

### Separacao dos artefatos

O GitHub publica somente o pacote de codigo JaamSim/Python
`JAAM_AI_NATIVE/`. O CMD historico embute codigo e evidencias
proprias e nao e colocado no repositorio publico.

A candidata privada pode ser organizada como:

```text
00_PROJETO_ATUAL/
  RODAR_JAAM_AI_COMPLETO.cmd           <- MESMO destino do atalho
  RODAR_JAAM_AI_COMPLETO.cmd.sha256
  JAAM_AI_LAB_V0_54_RELEASE_MANIFEST.json
  JAAM_AI_NATIVE/
    MANIFEST_SHA256.json
    JaamSim2026-03.jar
    extensions/academic-assistant/python/
  BACKUP_ORIGINAL_V050_NAO_ALTERAR/
  BACKUP_CANDIDATA_V051_NAO_INSTALAR/
  BACKUP_CANDIDATA_V052_NAO_INSTALAR/
  BACKUP_CANDIDATA_V053_NAO_INSTALAR/
```

Os arquivos de backup sao **copias de arquivo**, e nao pontos de entrada.
A substituicao do CMD ativo nao foi solicitada; executar uma atualizacao
no futuro requer trocar a candidata e seu manifesto em conjunto.
Nao modificar o atalho existente.

### Estado de engenharia e limites de comprovacao

Verificado estaticamente no artefato privado v0.54:
**37/37 hashes/tamanhos, manifesto pinado e integridade do ZIP**,
sem executar o CMD. Verificado no GitHub: compilacao Java/JDK25 e
regressoes Python, sem teste funcional do launcher.
**NAO executados:** PowerShell real em Windows, GUI, validacao de
interacao, ensaio P004 ou Full45, alteracao do CMD ativo, mesclagem do PR.
Estado: `CANDIDATE_ONLY / GUI_PENDING / P004_DENY / FULL45_NO_GO`.

O relato de auditoria do CMD v0.54 continua a diferenciar as tentativas
explicitas de JaamSim nativo e revisao RCL de inferencia P004.

### Limites especificos da v0.54

O mesmo Python e escolhido em `Resolve-JaamPython` nas opcoes 8 e 9; se `JAAMSIM_PYTHON` foi configurado e falha, nao existe fallback silencioso. O hash do CFG permite **detectar**, mas nao desfazer, alteracoes acidentais ou externas. Os comandos de verificacao de versao sao disparados somente nas opcoes 8 e 9, nao ao abrir o menu.

A distribuicao privada v0.54 inclui backups SHA-256 das candidatas v0.50 a v0.53; o menu de base permanece 1-11. O modulo publico Java/Python foi mantido byte a byte, sem novas mudancas no codigo do simulador. Tudo nesta etapa e **inspecao estatica**, sem testar o CMD em Windows ou o JaamSim graficamente.


## v0.55 — isolamento da evidencia por revisao (candidata privada)

O **mesmo CMD historico** (`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`)
foi atualizado em uma candidata privada **nao instalada**; as opcoes 1-11
e a entrada do atalho permanecem. Em relacao a v0.54:

- A configuracao explicita `JAAMSIM_PYTHON` aceita caminho
  relativo, como `.venv\\Scripts\\python.exe`, interpretado **a partir
  da pasta do CMD** (e nao da pasta "Iniciar em" do atalho); se esse caminho
  estiver incorreto, o menu bloqueia a operacao sem trocar silenciosamente
  por outro interpretador no PATH.
- Cada escolha de revisao offline (opcao **9**) passa a usar
  `JAAM_AI_NATIVE/extensions/academic-assistant/output/offline-review/<run_id>/`.
  Assim, relatorios anteriores nao sao silenciosamente substituidos pelo
  simples reaproveitamento de um diretorio compartilhado.
- O arquivo `JAAM_AI_OFFLINE_REVIEW_RECEIPT.json`, local a cada
  revisao, registra ID da sessao, data UTC, caminho do CFG de entrada,
  hashes SHA-256 antes e depois, resultado e codigo de saida, hash fixado
  do manifesto nativo, e flags negativas para autoedicao, LLM, P004 e
  Full45. A opcao **10** continua abrindo a pasta agregadora.
- A conferencia do CFG acontece mesmo quando o Python retorna codigo
  de erro. Um arquivo alterado ou nao verificavel impede status de
  sucesso; nenhuma restauracao/reedicao automatica e tentada.
  Se o recibo nao puder ser gravado, a revisao e sinalizada como falha.
- Backups independentes **v0.50-v0.54**, preservados por hash.
  O CMD candidato v0.55 tem SHA-256
  `a833c9876cde2960d342d818104190c400e4bfdfef020c1bf19ab2b296b37421`,
  2.143.856 bytes (confirmados pelo manifesto e pelo artefato).
  O ZIP candidato tem **57 entradas** e SHA-256
  `ffe2daf4f7b99e147d192e2c25f490499ad375fad589f1bdd45c66bac259e39b`.

O recibo nao e assinatura digital ou prova independente de execucao;
e um registro local auditavel por seu conteudo. Nenhuma GUI, CMD,
Python de revisao ou experimento foi executado como teste manual nesta
etapa. O atalho e o CMD ativo do Windows/Drive nao foram modificados.
**P004 DENY / Full45 NO-GO; PR em rascunho.**


## v0.56 — historico unificado entre CMD e Assistente IA nativo

**Estado:** `CANDIDATE_ONLY`, nao instalado no Windows nem no arquivo
ativo do Google Drive. **O atalho continua apontando para o MESMO**
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`, com o menu 1-11.

No GitHub publico, a classe
`src/main/java/com/jaamsim/ui/AIAssistantBox.java` foi atualizada
para gravar revisoes RCL na mesma raiz usada pela opcao **9** do CMD:

`JAAM_AI_NATIVE/extensions/academic-assistant/output/offline-review/`

- **CMD:** cada revisao continua em uma subpasta com `run_id` historico.
- **Janela IA do JaamSim:** nova subpasta `gui_<timestamp_utc>_<id_aleatorio>`
  para cada execucao, com arquivo
  `JAAM_AI_OFFLINE_REVIEW_RECEIPT.json`, SHA-256 do CFG original
  antes/depois, origem `JAAMSIM_GUI_RCL`, resultado de processo e
  flags negativas de autoedicao, IA externa, P004 e Full45.
- **Reutilizacao de decisoes:** o assistente le arquivos
  `*_suggestions_status.json` apenas quando o recibo foi concluido,
  o `source_cfg` indica **o mesmo caminho absoluto**, o
  `cfg_sha256_after` coincide com o conteudo atual, o CFG esta
  marcado como inalterado e a origem do status corresponde ao mesmo
  arquivo. Entradas antigas `native_rcl` sem recibo confiavel nao
  sao importadas automaticamente.
- **Sucesso rigoroso:** a janela so informa `OFFLINE_CONCLUIDA`
  se o processo retornou 0, o JSON esperado foi encontrado, o
  hash do CFG permaneceu igual e o recibo de auditoria foi salvo.
  Erros de Python, limite de tempo ou divergencia de hash sao
  reportados sem apagar nem restaurar o modelo automaticamente.
- **Opcao 10:** abre a raiz comum de todos os relatorios.
- **Opcao 11:** mostra ultimo recibo local existente em modo
  somente leitura; nao altera o status de nenhuma sugestao.

O JAR Java do modulo foi recompilado pelo
[GitHub Actions](https://github.com/Hailton-Reis/jaamsim/actions/runs/43666001110),
e as regressoes Python permaneceram aprovadas no
[pipeline](https://github.com/Hailton-Reis/jaamsim/actions/runs/43666001141).
Isso **nao representa teste GUI ou aceite operacional**.

### Identificacao e cadeia de integridade da candidata privada

- CMD candidato v0.55 (origem): SHA-256
  `a833c9876cde2960d342d818104190c400e4bfdfef020c1bf19ab2b296b37421`.
- CMD candidato **v0.56**: SHA-256
  `48075f86794e02a477bf31aee0c06175590598b4b55f2db4f1d283ec37b82f16`,
  **2.145.083 bytes**.
- Manifesto `JAAM_AI_NATIVE/MANIFEST_SHA256.json`: SHA-256
  `518819bfef9cf55aec3591936028d98a49a4072b95eb876f1bb55cace6fa7b1b`;
  **37 arquivos** conferidos.
- ZIP privado `JAAM_AI_V056_CMD_ORIGINAL_HISTORICO_RCL_UNIFICADO_2026-11-14.zip`:
  **60 entradas**, SHA-256
  `d5470e1f3d0f4ca943e85377568c896d03f945941b1e9e288c1e36bdd074bf0f`.
- Backups v0.50-v0.55 inteiros e sem modificacao de SHA;
  blocos historicos de payload embutido do CMD mantidos byte a byte.

Os recibos sao **metadados locais e nao assinaturas digitais**.
Os hashes protegem verificacao de conteudo, mas nao comprovam
correcao conceitual de um modelo ou execucao valida do simulador.
Nenhum teste manual de Windows, GUI, P004 ou Full45 foi executado.
O CMD ativo no Drive/Windows nao foi substituido; PR continua draft.
