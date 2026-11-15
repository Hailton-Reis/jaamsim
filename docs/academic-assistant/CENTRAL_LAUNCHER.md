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

A v0.52 fixa o SHA-256 do arquivo
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
  JAAM_AI_LAB_V0_52_RELEASE_MANIFEST.json
  JAAM_AI_NATIVE/
    MANIFEST_SHA256.json
    JaamSim2026-03.jar
    extensions/academic-assistant/python/
  BACKUP_ORIGINAL_V050_NAO_ALTERAR/
  BACKUP_CANDIDATA_V051_NAO_INSTALAR/
```

Os arquivos de backup sao **copias de arquivo**, e nao pontos de entrada.
O substituicao do CMD ativo nao foi solicitada; executar uma atualizacao
no futuro requer trocar a candidata e seu manifesto em conjunto.
Nao modificar o atalho existente.

### Estado de engenharia e limites de comprovacao

Verificado estaticamente no artefato privado v0.52:
**37/37 hashes/tamanhos, manifesto pinado e integridade do ZIP**,
sem executar o CMD. Verificado no GitHub: compilacao Java/JDK25 e
regressoes Python, sem teste funcional do launcher.
**NAO executados:** PowerShell real em Windows, GUI, validacao de
interacao, ensaio P004 ou Full45, alteracao do CMD ativo, mesclagem do PR.
Estado: `CANDIDATE_ONLY / GUI_PENDING / P004_DENY / FULL45_NO_GO`.

O relato de auditoria do CMD v0.52 passa a diferenciar as tentativas
explicitas de JaamSim nativo e revisao RCL de inferencia P004.
