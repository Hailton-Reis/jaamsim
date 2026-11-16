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


## v0.57 — histórico RCL consultável e correção do Python no CMD original

**Estado:** candidata privada `CANDIDATE_ONLY / GUI_PENDING / P004_DENY /
FULL45_NO_GO`. O único ponto de entrada Windows continua
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`, com todas as opções
1–11 preservadas e atalho **inalterado**.

### Interface nativa JaamSim (código público)

Em `src/main/java/com/jaamsim/ui/AIAssistantBox.java` foi incluído
o botão **Histórico RCL**, que pode ser acionado também pela mensagem
"mostrar histórico de revisões". A consulta é **somente leitura**
(não invoca Python, redes, simulações ou LLM). Exibe até 10 registros,
ordenados pelas pastas existentes, com:
- identificação da revisão e resultado local do recibo;
- origem (janela JaamSim ou CMD) e data UTC declarada;
- modelo selecionado e pasta de resultados;
- comparação do SHA-256 do CFG atual com o hash registrado em cada revisão,
  distinguindo `mesmo conteúdo atual` de `outra versão / não verificável`.

Quando há um arquivo CFG aberto, não apresenta recibos de outros modelos
na lista. Quando nenhum CFG está salvo, permite consultar os registros
locais de todos os modelos. Recibos malformados ou com esquema inesperado
não são tratados como evidência válida. Os recibos são registros locais,
**não assinaturas digitais**. A política de importação de sugestões por
caminho + hash permanece distinta e continua restritiva.

### CMD privado v0.57

Foi corrigido o defeito de `Resolve-JaamPython` que usava
`$name.Contains('')`: esse teste é sempre verdadeiro e impedia
resolver `JAAMSIM_PYTHON=python.exe` pelo PATH. A nova comparação
usa `$name.Contains([char]92)`, distinguindo executáveis por nome
de caminhos relativos como `.venv\\Scripts\\python.exe`.
Nenhuma condição para P004 ou Full45 foi modificada.

O módulo nativo distribuído pelo CI público é recolocado sob
`JAAM_AI_NATIVE/`, sem distribuir segundo CMD. O controlador fixa o
SHA-256 do manifesto nativo.

### Identificação de artefatos

- CMD v0.57 (2.145.091 bytes): SHA-256
  `814d984a3470a788efe3b48ab29fc9c3fab5bbd05769abb399f2fc3af0be9e54`.
- Manifesto nativo `MANIFEST_SHA256.json`: SHA-256
  `3765340322c8a89180a72963e43d0fe53709903c34c76fe0d29888f7e3907a3e`,
  37/37 arquivos conferidos.
- Candidata privada:
  `JAAM_AI_V057_CMD_ORIGINAL_HISTORICO_RCL_CONSULTAVEL_2026-11-14.zip`.
  SHA-256 `e8a0663a3ece9e25629cf27bf3fde618df11bf21497a44d5cf10e38e33130e09`,
  63 entradas, sem nomes duplicados.
- Backups íntegros das versões v0.50–v0.56, preservando a integridade
  de todos os blocos históricos incorporados ao CMD.
- [Compilação Java/empacotamento](https://github.com/Hailton-Reis/jaamsim/actions/runs/43667426575)
  **aprovados** e
  [regressões Python](https://github.com/Hailton-Reis/jaamsim/actions/runs/43667426615)
  **aprovadas** na branch isolada.

**Não realizado:** instalação no Windows, substituição do CMD ativo no Drive,
teste manual/visual da GUI, execução do controlador histórico, experimento
P004/Full45 ou mesclagem do PR.

## v0.58 — proteção contra transferência de decisões entre regras alteradas

**Candidata privada gerada em 15/11/2026; não instalada.** Mantém o nome
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd` e a mesma posição do atalho,
com menus 1–11. P004 e Full45 continuam explicitamente NÃO autorizados.

### Falha de engenharia corrigida

O motor RCL enumerava sugestões como `SUG001`, `SUG002`, etc.
O histórico da interface exigia previamente caminho e SHA-256 iguais para o
CFG, mas **não identificava mudanças nas próprias regras entre versões**
do motor. Portanto, `SUG001` de uma versão anterior poderia corresponder
a outra regra depois de uma atualização do código, mesmo com o mesmo CFG.

Agora o assistente GUI envia `--strict-status-identity` ao chamar
`modulo_ia_offline.py` com um arquivo de status anterior. O motor só
reaproveita uma decisão cuja entrada contenha a mesma:
- `suggestion_id`, `rule_id` e `component_id`;
- `action_type` e `suggested_change`.

Decisões sem esses campos ou com identidade alterada **não são herdadas**;
a nova sugestão fica `pending`, sem status `accepted`/ `rejected` e sem
plano autorizado com base na decisão antiga. O JSON
`*_offline_review.json` e o Markdown registram quantidades importadas
e rejeições com motivos. O arquivo original de decisões permanece
inalterado; a decisão humana deve ser reavaliada no contexto atual.

**Compatibilidade:** importações explícitas antigas via CLI e
`--status-file` seguem disponíveis sem a opção estrita. A janela GUI
usa o modo estrito ao reaproveitar automaticamente histórico; o CMD
central opção 9 não importa status anteriores por padrão. Este é um
limite deliberado: mudanças de política não podem usar um identificador
ordinal como prova suficiente de identidade de regra.

### Evidências e empacotamento

- Commits de implementação: `10c3be19` (Python), `6408cec3`
  (GUI Java), `0f03b02a` (regressões).
- **95 testes + 6 subtestes aprovados** na matriz Python 3.11/3.14 ×
  Ubuntu/Windows: [CI](https://github.com/Hailton-Reis/jaamsim/actions/runs/43768787359).
- Java JDK25 compilado e pacote nativo produzido:
  [CI](https://github.com/Hailton-Reis/jaamsim/actions/runs/43768787464).
- JAR gerado contém `AIAssistantBox.class`, `StatFitAssistantBox.class`
  e a string de configuração `--strict-status-identity` verificada
  estaticamente.
- Módulo `JAAM_AI_NATIVE` com **37/37 arquivos** conferidos por tamanho
  e SHA-256. Manifesto SHA-256:
  `bce2be4cbf1171c57ea7729f9a5e2046a9ab3d1805c9433e95b1842e8a5e376a`.
- CMD v0.58 com **2.145.091 bytes** e SHA-256:
  `f3fd0f4d9f2ba4584bd2aac0dd0e67d03dc3192dddfd4dfc21dafa5cc87410b7`.
  Em relação à v0.57, só mudaram marcadores de versão, manifesto
  de integridade e pin SHA-256 do módulo. Todo o controlador histórico
  incorporado é preservado byte a byte fora dessa lista explícita.
- Pacote privado:
  `JAAM_AI_V058_CMD_ORIGINAL_IMPORTACAO_DECISOES_SEGURA_2026-11-15.zip`;
  SHA-256:
  `b83ccd2c0f77eecbed9c7c4e781d7e94f932253a9ec7ab6fd72ca0498fd6cd26`.
  **67 entradas**; backups íntegros v0.50 até v0.57.
- Artefato adicional: relatório estático
  `JAAM_AI_V058_STATIC_REPORT_2026-11-15.json` e patch da mudança
  v0.57 → v0.58 do CMD original.

**Não executado:** CMD no Windows, GUI, simulação, instalação, uso do atalho,
inferência P004, Full45 ou merge. A versão ativa do Drive/Windows segue
intacta; tudo é candidata de engenharia até aceite.

## v0.59 — validação de conteúdo e integridade dos relatórios RCL

**Estado:** candidata de desenvolvimento, não instalada, 15/11/2026.
O ponto de entrada Windows continua sendo **o mesmo CMD original**
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`; não foi criado outro
launcher, nem modificado o atalho. Menus 1–11 e barreiras P004/Full45
permanecem intactos.

### Falha de confiabilidade corrigida

Na versão anterior, a janela do JaamSim considerava suficiente para
`OFFLINE_CONCLUIDA` que o Python retornasse código 0, o CFG não
mudasse de SHA-256 e houvesse um arquivo chamado `*_offline_review.json`.
Isso não comprovava que seu **conteúdo** era válido ou que correspondia
ao modelo aberto.

A v0.59 passa a exigir conteúdo verificável para registrar conclusão:
- JSON legível, `mode=offline_deterministico` e `input_type=cfg`;
- `input_file` compatível com o caminho absoluto do CFG efetivamente
  revisado, tratando também o formato relativo emitido pelo Python;
- `analysis.model_id` esperado pelo solicitante;
- confirmação explícita `false` para `internet_api`, `llm_online`,
  `local_ai` e `llm_online_assist.enabled`;
- arquivo de status adjacente, pertencente ao mesmo modelo e CFG,
  com lista de sugestões legível;
- hash SHA-256 do JSON no recibo `report_sha256`, além dos hashes
  do CFG de entrada antes e depois.

A interface Java exige essas condições ao declarar sucesso e ao
recuperar decisões de histórico; um recibo da interface com hash
ausente ou divergente não permite transferir decisões. Recibos
antigos do CMD que ainda não fixavam hash exigem validação do conteúdo
mas seguem compatíveis para leitura, sem alegar assinatura digital.

A **opção 9 do CMD original** também confere o JSON e seu status antes
de marcar `COMPLETE_OFFLINE`; em qualquer divergência, registra
`FAILED_OR_BLOCKED` e código de erro, sem editar nem restaurar o CFG.

### Evidências técnicas

Foi acrescentado `src/test/java/com/jaamsim/ui/OfflineRclReportContractTest.java`
e uma etapa no CI Java para validar a regra **sem abrir janelas, executar
simulação, nem iniciar Python**. Foram aprovados **11 casos de contrato**
de origem, JSON inválido, modelo errado, flags de IA, status inexistente,
entre outros:
[CI Java JDK 25 + contrato](https://github.com/Hailton-Reis/jaamsim/actions/runs/43771380475).
A matriz de regressão Python permanece aprovada:
[CI Python](https://github.com/Hailton-Reis/jaamsim/actions/runs/43771380416).

**Pacote privado da v0.59**, produzido sem redistribuir o corpus oficial:
`JAAM_AI_V059_CMD_ORIGINAL_RELATORIO_RCL_VERIFICADO_2026-11-15.zip`.

| Item | SHA-256 / verificação |
|---|---|
| CMD principal v0.59 | `05436258482e267df17bba607c56abc26f073af74e4b8c49c604a9a1f7d98e4b`, 2.147.470 bytes |
| Manifesto do módulo `JAAM_AI_NATIVE` | `ba4186e552ac563e489574ffa5e6e30e418cd43f90f409758ff32d4b833ebbf2` |
| ZIP privado | `ed702066a0a0d2ed690b62f75e9853bcdbd193997498d9790028213abdd307fb`, 71 entradas |
| Códigos/recursos nativos | **37/37** arquivos conferidos por SHA-256 e tamanho |
| Backups | v0.50–v0.58 preservados por hash |

O pacote é uma **candidata estática**; a compilação e os testes
automatizados não comprovam operação gráfica nem aceitação no Windows.
Nenhum arquivo ativo do Drive/Windows foi substituído. **Não iniciar
P004, Full45, inferência, simulação experimental ou merge sem aprovação.**


## v0.60 — correção do contrato de caminhos RCL Java ↔ Python ↔ CMD (15/11/2026)

**Ponto de entrada único:** `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`,
mesmo nome e caminho do atalho existente. Candidata privada não instalada;
funções 1–11 e bloqueios `P004 DENY / Full45 NO-GO` preservados.

### Falha de integração corrigida

O Python implementa `display_path()` em `modulo_ia_offline.py`
usando `snapshot_analyzer.ROOT == assistant_paths.ASSISTANT_ROOT`.
Isso significa que entradas dentro da extensão são gravadas como caminho
**relativo a** `JAAM_AI_NATIVE/extensions/academic-assistant`.

Na v0.59, a validação de relatório na GUI (`resolveReportedSource`) e
a opção 9 do CMD assumiam equivocadamente a raiz `JAAM_AI_NATIVE`.
Isso podia bloquear um CFG válido (ou impedir reutilização legítima de
decisões) mesmo com hashes corretos.

**Correção no código público Java:**
- `resolveReportedSource` resolve caminhos relativos somente a partir
  do diretório efetivo da extensão, preservando caminhos absolutos;
- `findSuggestionStatusFile` utiliza a mesma base para a origem
  registrada no JSON de status, após conferir recibo, modelo e SHA-256;
- o teste headless `OfflineRclReportContractTest` agora inclui fontes
  relativas válidas, rejeita a raiz antiga, verifica recuperação segura
  de decisões por caminho/recibo e bloqueia histórico adulterado ou
  de outro CFG. **19 verificações passaram no Java CI**.

**Correção na candidata privada do CMD:** a opção 9 define
`$assistantRoot` a partir de `JAAM_AI_NATIVE/extensions/academic-assistant`.
Os campos `input_file` do relatório e do status passam a ser resolvidos
por essa mesma raiz; nomes absolutos continuam inalterados. Sem fallback
para diretórios arbitrários e sem relaxar as demais restrições.

### Identificação auditável da candidata

- CMD v0.60: **2.147.579 bytes**, SHA-256
  `267459ffd25eade9211e55543fcdd3147dac6526ac9420d179d20eada3438b66`.
- Manifesto do módulo nativo SHA-256
  `320b89f5148593799b97c64654b6510d42a90d450ac9fe82374903f8fc6cbf50`;
  **37/37 arquivos** íntegros por tamanho e SHA-256.
- ZIP privado `JAAM_AI_V060_CMD_ORIGINAL_CAMINHOS_RCL_CORRIGIDOS_2026-11-15.zip`:
  SHA-256 `61fdd5276cc42d2fad0be95164955502cd4028869ada2dcba6b053ba48715ffd`,
  **74 entradas**, sem duplicatas.
- **10 backups conferidos** (v0.50–v0.59), cada um com seu CMD,
  sidecar e manifesto históricos íntegros.
- [Java JDK25 + 19 verificações de contrato](https://github.com/Hailton-Reis/jaamsim/actions/runs/43774076166):
  **SUCCESS**.
- [Python 95 testes + 6 subtestes, matriz Windows/Linux × 3.11/3.14](https://github.com/Hailton-Reis/jaamsim/actions/runs/43774076179):
  **SUCCESS**.
- No manifesto do artefato nativo, `source_commit` representa o
  **commit de merge temporário do PR usado pelo workflow**; a cabeça
  da branch conferida é `2c14852549263559c56491d89459800e9ebfd1a2`,
  registrada separadamente no manifesto privado.
- Relatório de conferência estática `JAAM_AI_V060_STATIC_REPORT_2026-11-15.json`
  e diff reversível `JAAM_AI_V060_DIFF_CMD_V059_V060.patch`.

**Limites da comprovação:** o CI compila e exercita funções headless
em arquivos de teste. Não houve teste manual de GUI, execução do CMD
histórico no Windows, alteração do arquivo ativo em Google Drive,
instalação ou mesclagem deste PR. Os recibos são registros locais,
não assinaturas digitais. O estado segue `CANDIDATE_ONLY /
GUI_PENDING / P004_DENY / FULL45_NO_GO`.


## v0.61 — raiz do módulo configurado obrigatória (15/11/2026)

O ponto de entrada Windows **continua sendo o mesmo**
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`. Esta candidata
privada não altera o atalho, o CMD instalado, o menu 1–11 ou as
restrições P004/Full45.

### Correção de confiança no módulo

Nas versões anteriores, `AIAssistantBox.findAssistantRoot` e
`StatFitAssistantBox.findAssistantRoot` procuravam, por ordem:
a propriedade Java `jaamsim.assistant.root`, a variável de ambiente
`JAAMSIM_ASSISTANT_ROOT`, o diretório corrente e os diretórios
ancestrais do arquivo de entrada. Se uma raiz explicitamente configurada
estivesse errada ou não tivesse o script necessário, o código podia
localizar outro script numa pasta próxima — **diferente do módulo
verificado por SHA-256 pelo CMD**.

As duas classes foram corrigidas para respeitar a seguinte precedência:

1. Se `jaamsim.assistant.root` estiver definida, **somente essa raiz**
   pode ser usada; na ausência do script necessário, retorna `null`.
2. Caso contrário, se `JAAMSIM_ASSISTANT_ROOT` estiver definida,
   **somente essa raiz** pode ser usada; não há busca implícita posterior.
3. Somente quando **nenhuma raiz explícita** foi definida, permanece
   a descoberta por diretório corrente e caminho do arquivo, por
   compatibilidade com execuções independentes do CMD.

`AIAssistantBox` exige `modulo_ia_offline.py`; `StatFitAssistantBox`
exige `statfit_auxiliar.py`. Uma raiz inválida impede a operação,
não dispara fallback nem executa Python. Isso evita usar
silenciosamente um módulo não correspondente ao manifesto fixado
pelo controlador, mas **não constitui assinatura do código Python
em execução nem teste de segurança do Windows**.

### Evidência e candidata privada

- Commits: `bf23c3f7` (Assistente IA), `4cafbb67` (StatFit),
  `755e7775` (oito regressões adicionais).
- [Compilação Java JDK25 e 27 verificações de contrato headless](https://github.com/Hailton-Reis/jaamsim/actions/runs/43774641961):
  **SUCCESS**.
- [Python 95 testes e 6 subtestes nas 4 combinações Windows/Linux
  × Python 3.11/3.14](https://github.com/Hailton-Reis/jaamsim/actions/runs/43774641997):
  **SUCCESS**.
- Módulo `JAAM_AI_NATIVE/`: **37/37 arquivos verificados**
  por SHA-256 e tamanho. Manifesto:
  `9dce55fcf99282aa34999eb57acd1f451de35d3977b3aec7ec9c18018ee0583b`.
- CMD candidato v0.61: 2.147.579 bytes,
  SHA-256 `83237ac3a6fe045d4188961dea301e8925e3e431834117f7f0e618f30e238a07`.
- Pacote privado
  `JAAM_AI_V061_CMD_PRINCIPAL_RAIZ_IA_STATFIT_PROTEGIDA_2026-11-15.zip`:
  **77 entradas**, SHA-256
  `1a56042af6f5a67397b09b7d56e04e4d18deec4dec2e40b82afe6b3df95e5f1f`.
- **11 backups íntegros**, da v0.50 até a v0.60, com CMD,
  sidecar e manifesto históricos validados.
- O diff byte a byte da v0.60 para v0.61 tem apenas mudanças do
  número da versão, manifesto e hash fixado do módulo atualizado;
  o conteúdo funcional do CMD (incluindo o legado MC-001) é o mesmo.
- Auditoria estática:
  `JAAM_AI_V061_STATIC_REPORT_2026-11-15.json`;
  comparação do CMD:
  `JAAM_AI_V061_DIFF_CMD_V060_V061.patch`.

**Estado:** CANDIDATE_ONLY / GUI_PENDING / P004_DENY /
FULL45_NO_GO. Não foi instalado sobre a v0.50 ativa,
não foi executado manualmente no Windows e o PR continua draft.


## v0.62 — recuperação segura de histórico entre CMD e GUI (15/11/2026)

**Mesmo CMD principal**: `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`,
mesmo nome e caminho do atalho, menu 1–11, sem criar inicializador
alternativo. É uma **candidata privada não instalada**.

### Falha corrigida

A janela nativa `AIAssistantBox.java` escolhe seu `modelId` com
`buildModelId(cfgFile)`; o modo da opção 9 do CMD deixa o conversor
Python escolher `to_id(path.stem)`. Os dois nomes podem diferir em
maiúsculas, espaços e caracteres especiais. O método
`findSuggestionStatusFile` da v0.61 procurava sempre
`<buildModelId>_offline_review.json`, impedindo a interface de recuperar
decisões legítimas de uma execução feita pelo CMD.

Agora, em cada diretório individual de revisão, a janela:
- aceita **exatamente um** `*_offline_review.json`; zero ou mais de um
  significam histórico ambíguo e não autorizado;
- lê o `analysis.model_id` efetivo do JSON (sem inventar nome);
- exige identificador adequado para nome de arquivo local, e verifica
  que o próprio filename e `*_suggestions_status.json` correspondem
  a esse identificador;
- exige o mesmo CFG absoluto, SHA-256, recibo de revisão concluída,
  contexto offline e hash do relatório pinado quando disponível;
- preserva `--strict-status-identity`: as decisões só passam para
  a nova análise se a identidade da sugestão também coincidir.

O método `validateOfflineRclReport` aceita um identificador esperado
específico nas revisões **iniciadas pela GUI**, mas também pode verificar
o identificador declarado no relatório quando está lendo histórico do
CMD, sem relaxar os demais critérios.

### Evidência reproduzível e artefato privado

- Commits na branch: `3769088f` (Java) e `0aa5d6c0` (contratos).
- [GitHub Actions — Java 25, empacotamento e **33 verificações headless**](https://github.com/Hailton-Reis/jaamsim/actions/runs/43776590833):
  **SUCCESS**.
- [GitHub Actions — Python **95 testes + 6 subtestes** por plataforma,
  Windows/Linux × Python 3.11/3.14](https://github.com/Hailton-Reis/jaamsim/actions/runs/43776590808):
  **SUCCESS**.
- Módulo `JAAM_AI_NATIVE` recompilado:
  **37/37 arquivos** verificados por SHA-256 e tamanho. Manifesto:
  `2807b193a02d1d0f0edcd10cc219cc3b665f0b9d595c710281a45873aa8c06aa`.
- CMD candidato **v0.62**, 2.147.579 bytes, SHA-256:
  `cf54d5b0fdef4c0940d4bfaadc1be141f4dc8048679bf0ece93e3a59f9a15ac1`.
- ZIP privado
  `JAAM_AI_V062_CMD_ORIGINAL_HISTORICO_RCL_CMD_JAVA_2026-11-15.zip`:
  **80 entradas**, SHA-256
  `ac44efab87a1cddaf111f92fb767645b2a8693347f012010bf8927e044cfbb3b`.
- **12 backups preservados**, da v0.50 à v0.61, cada um com seu CMD
  original e os respectivos sidecar/manifesto conferidos por SHA-256.
- A modificação no CMD entre v0.61 e v0.62 foi **somente de versão e
  manifesto fixado** (reversível byte a byte); a lógica MC-001/P004
  foi mantida.
- Auditoria estática:
  `JAAM_AI_V062_STATIC_REPORT_2026-11-15.json`;
  patch de comparação:
  `JAAM_AI_V062_DIFF_CMD_V061_V062.patch`.

**Limites:** os testes headless não são um teste visual ou funcional do
programa em Windows. Não houve instalação nem alteração de CMD ativo,
atalho, arquivos do Drive, modelo .cfg, ativação de P004, Full45 ou
mesclagem do PR. Estado: `CANDIDATE_ONLY / GUI_PENDING /
P004_DENY / FULL45_NO_GO`.

## v0.63 — precedencia obrigatoria do ambiente preparado pelo CMD (15/11/2026)

A entrada do Windows continua **uma unica**
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`. O atalho, a versao ativa,
as opcoes 1–11 e o controlador MC-001 historico nao foram alterados.
Esta e uma candidata privada, **nao instalada nem testada manualmente**.

### Falha identificada

Desde a v0.61, `JAAMSIM_ASSISTANT_ROOT` configura de forma obrigatoria
a raiz dos scripts Java/Python, mas as classes do JaamSim ainda priorizavam
`-Djaamsim.assistant.root` sobre a variavel de ambiente. De modo
semelhante, `-Djaamsim.python` podia substituir o
`JAAMSIM_PYTHON` previamente inspecionado pelo CMD. Isso permitia
redirecionar a janela Assistente IA ou StatFit para modulo/interprete
diferente daquele selecionado pelo controlador.

### Correcao na branch

O helper compartilhado
`src/main/java/com/jaamsim/ui/AssistantLaunchSettings.java`
(commit `b256150b`) implementa:

1. Se o valor de ambiente herdado do CMD estiver presente,
   **ele vence a propriedade Java -D**, tanto para raiz quanto Python.
2. Se o ambiente estiver explicitamente configurado e invalido,
   nao ocorre fallback silencioso para outra propriedade ou modulo;
   o uso falha de forma segura.
3. Se a aplicacao for iniciada **sem a variavel de ambiente**,
   propriedades Java -D permanecem como alternativa compativel.
   Na ausencia de ambas, a descoberta legada independente permanece.

As janelas `AIAssistantBox.java` (`d462a8e5`) e
`StatFitAssistantBox.java` (`3d5fd083`) utilizam a mesma funcao
para `JAAMSIM_ASSISTANT_ROOT` e `JAAMSIM_PYTHON`. A prioridade
nao muda o comportamento do menu 1–11 do CMD.

### Auditoria e integridade da candidata

- Java/JDK25 e **43 verificacoes headless**:
  [CI Java](https://github.com/Hailton-Reis/jaamsim/actions/runs/43780345018)
  **SUCCESS**. Dez novos cenarios cobrem precedencia e fallback;
  regressao em `OfflineRclReportContractTest.java` (`9debbd69`).
- Python **95 testes + 6 subtestes**, aprovados nas quatro
  combinacoes Windows/Linux × 3.11/3.14:
  [CI Python](https://github.com/Hailton-Reis/jaamsim/actions/runs/43780345002)
  **SUCCESS**.
- Módulo nativo `JAAM_AI_NATIVE/` recompilado: **37/37**
  arquivos conferidos por hash e tamanho. Manifesto SHA-256
  `39eb0b82427d57fde4a07be8915c8f4c13f737bd545599525dd86d6bb133bd1c`.
- CMD v0.63 SHA-256:
  `ec817b45561d16ace6524643a23cf179d69382ceedf1494d45b36d528728050f`,
  **2.147.579 bytes**.
- Artefato:
  `JAAM_AI_V063_CMD_ORIGINAL_AMBIENTE_FIXADO_IA_STATFIT_2026-11-15.zip`;
  SHA-256 `ee70efd6b54d4f89e663f50b2e08de63fa64d2759f4e2e289b9ea85112011e8c`;
  **84 entradas unicas** e **13 backups integrais** v0.50–v0.62.
- Modificacoes no CMD v0.62→v0.63 limitadas a **numeros de versao,
  nome do manifesto e hash fixado do modulo**; diff reversivel e
  payload historico preservado byte a byte.
- Relatorio local `JAAM_AI_V063_STATIC_REPORT_2026-11-15.json` e patch
  `JAAM_AI_V063_DIFF_CMD_V062_V063.patch`.

**Limites:** os CI e hashes nao demonstram a abertura real da GUI ou
o funcionamento do atalho no Windows. Nenhuma substituicao no Drive,
teste manual, inferencia P004, Full45 ou merge foi executada.
Estado: `CANDIDATE_ONLY / GUI_PENDING / P004_DENY / FULL45_NO_GO`.


## v0.64 — proveniência local do interpretador Python usado nas revisões (15/11/2026)

**Candidata privada não instalada.** Permanece um único
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd` (mesmo nome e caminho do
atalho existente), com menu 1–11. O controlador MC-001 histórico, os
bloqueios P004 DENY / Full45 NO-GO e o arquivo ativo do Windows/Drive
não foram modificados.

### Implementação e alcance

Na extensão Python, o novo arquivo
`python/runtime_provenance.py` calcula, **no processo que grava cada
relatório**, `sys.executable` resolvido, versão Python, implementação,
SHA-256 do executável e do script de entrada. O metadado tem
`schema=jaam.ai.python_runtime.v1` e
`evidence_level=self_reported_no_external_attestation`.
Não usa internet ou novos subprocessos.

Esses dados entram em:
- `modulo_ia_offline.py`: JSON da revisão RCL e JSON de status das
  sugestões, com o mesmo campo `python_runtime`;
- `statfit_auxiliar.py`: relatório JSON de ajuste de distribuições;
- `statfit_data_assist.py`: relatório JSON de preparação de dados.

A interface `AIAssistantBox.java` exige essa evidência nas **novas
revisões RCL iniciadas pela GUI**. Compara localmente os arquivos do
interpretador e do script com seus hashes declarados, verifica o
script contra a raiz configurada e confronta o runtime dos JSON de
revisão e de sugestões. Somente depois um resultado pode ser
`OFFLINE_CONCLUIDA`. O recibo local inclui `python_runtime`,
bem como os hashes do CFG e do relatório.

O histórico de versões anteriores sem `python_runtime` permanece
consultável, mas a ausência de metadado **não pode servir como prova
de identidade do interpretador**. As condições já existentes de
origem/hash do CFG, modo offline, identidade da sugestão e recibos
continuam vigentes.

Na opção 9 do **mesmo CMD principal**, a candidata v0.64 verifica
o runtime relatado pelo Python, SHA-256 do executável e do script,
versão 3.11+, correspondência com o script instalado e consistência
entre os JSON de revisão e status. Falhas bloqueiam sucesso; o
recibo passa a incluir `python_requested_by_cmd`,
`python_runtime` e `python_runtime_local_hash_check`.
Nenhuma alteração é realizada no `.cfg`.

**Limitação fundamental:** a evidência é produzida pelo próprio
processo. Os hashes locais permitem detectar alterações e
inconsistências, mas **não são uma assinatura digital, atestação do
sistema operacional nem prova independente da identidade do processo**.
Os caminhos locais do computador aparecem nos relatórios e devem
ser revisados antes de qualquer publicação.

### Estado verificável

- [CI Java JDK25 + **49 verificações headless**](https://github.com/Hailton-Reis/jaamsim/actions/runs/43781539123):
  **SUCCESS**.
- [CI Python **95 testes + 6 subtestes**, 4 jobs
  Windows/Linux × Python 3.11/3.14](https://github.com/Hailton-Reis/jaamsim/actions/runs/43781539079):
  **SUCCESS**.
- Módulo `JAAM_AI_NATIVE/` com **38/38 arquivos** conferidos
  por SHA-256 e tamanho (um novo módulo `runtime_provenance.py`).
  Manifesto SHA-256:
  `6e24b2ab969ef17312fc20c97681dfef088127d9288ed8d87dab98a560a5d52e`.
- CMD v0.64: SHA-256
  `5a97719ecdae728ed69b6e0dd50b4f449843a273f3e5d9688b4b09e725b001bf`,
  **2.149.688 bytes**.
- ZIP privado:
  `JAAM_AI_V064_CMD_ORIGINAL_RASTREIO_PYTHON_2026-11-15.zip`,
  SHA-256
  `04ff2bf05a1e2f99482c88645fa1f3903610e692263dadc67960c3023170aa57`,
  **89 entradas únicas**, e **14 backups históricos** v0.50–v0.63
  conferidos com seus respectivos manifests e sidecars.
- Histórico CMD embutido preservado por substituições explícitas,
  byte-reversíveis, sem mudanças em funções legadas 1–7. Além da revisão
  RCL offline da opção 9, o teste de integridade e a mensagem do status
  foram ajustados de **37 para 38 arquivos**; sem isso, a verificação
  bloquearia equivocadamente o novo pacote.
- Arquivos auxiliares
  `JAAM_AI_V064_STATIC_REPORT_2026-11-15.json` e
  `JAAM_AI_V064_DIFF_CMD_V063_V064.patch`.

**Validação pendente:** sem PowerShell nativo no ambiente de preparo,
a sintaxe/execução real do CMD em Windows continua **não testada**.
Nenhuma instalação, teste visual GUI, inferência P004/Full45, alteração
do atalho ou merge foi executada. Estado:
`CANDIDATE_ONLY / GUI_PENDING / P004_DENY / FULL45_NO_GO`.


## v0.65 — preparação de dados StatFit sem chamadas online automáticas (15/11/2026)

**Candidata privada; não instalada.** A entrada continua sendo o único
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd`, sem novo CMD,
sem modificação do atalho, com opções 1–11 e legado MC-001 preservados.
P004 continua DENY e Full45 continua NO-GO.

### Defeito encontrado e corrigido

A interface nativa `StatFitAssistantBox.java` incluía
`--online --provider-order nvidia,cerebras,groq` **automaticamente**
no comando do botão de **Preparação de dados**. O script Python
`statfit_data_assist.py` faz chamadas a provedores configurados quando
recebe `--online`; portanto, preparar dados poderia solicitar
orientação LLM externa e consumir tokens sem uma autorização
explícita para essa etapa.

O código Java foi alterado para que
`buildDataAssistCommand` utilize uma função estática e isolada
`buildOfflineDataAssistCommand`, que passa somente:
interpretador escolhido, script, arquivo de entrada, diretório de
saída e, quando pertinente, `--column`. **Não fornece**
`--online`, `--provider-order` ou `--require-online`.
A preparação nativa é **somente local por padrão**.
Para usar suporte online futuramente será necessário implementar um
fluxo separado e uma autorização explícita do usuário na interface.
O CLI Python independente mantém `--online` para quem o chamar
intencionalmente fora dessa opção da janela.

### Evidência automática

- Commit Java: `65969c02` (`StatFitAssistantBox.java`).
- Teste Java headless `567cfb8c`: confirma que o comando
  sem/com coluna contém apenas os argumentos offline e bloqueia
  a regressão de qualquer flag de provedor.
- Python `1c21344b`, com ajuste de dados de teste `6b430425`:
  intercepta `run_online_assist` para confirmar que o padrão offline
  não chama o provedor.
- [CI Java JDK25 + **54 verificações headless**](https://github.com/Hailton-Reis/jaamsim/actions/runs/43784224506):
  **SUCCESS**.
- [CI Python **96 testes + 6 subtestes** por combinação, Windows/Linux
  × Python 3.11/3.14](https://github.com/Hailton-Reis/jaamsim/actions/runs/43784224505):
  **SUCCESS**.

### Identificação do pacote

- Manifesto nativo `JAAM_AI_NATIVE/MANIFEST_SHA256.json`:
  SHA-256 `86d6f35ee8fc759dc4ec0c22db71058b30b6ed19250e2b763989145d3a037d7f`;
  **38/38** arquivos, tamanho e SHA-256 conferidos.
- CMD candidato v0.65: SHA-256
  `1597a2c64fe5e16241593b686b2d66f2cad7ec0551cb43598deae0400a61e73f`,
  **2.149.688 bytes**. Em relação à v0.64, o CMD teve somente
  substituições byte-reversíveis de identificação de versão,
  nome de manifesto e hash fixado do módulo compilado.
- ZIP candidato
  `JAAM_AI_V065_CMD_ORIGINAL_STATFIT_PREPARACAO_OFFLINE_2026-11-15.zip`,
  SHA-256
  `de4ad42f9a96ca17bc27c101f4ceff423bb21d29f1f0cbd0206989c61389ba54`,
  **93 entradas únicas**, 15 backups íntegros (v0.50–v0.64).
- Arquivos de auditoria:
  `JAAM_AI_V065_STATIC_REPORT_2026-11-15.json` e
  `JAAM_AI_V065_DIFF_CMD_V064_V065.patch`.

**Limites:** não foram executados a interface Windows, o CMD,
qualquer experimento P004/Full45 ou testes manuais. Os testes
automatizados validam a composição do comando offline e a
regressão do script Python, mas não substituem o aceite em Windows.
A versão ativa do CMD/Drive e o atalho permanecem intocados;
o PR continua em rascunho e sem merge.
