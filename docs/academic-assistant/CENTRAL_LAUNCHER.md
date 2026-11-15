# JAAM-AI — entrada central preservada

O ponto de entrada principal no Windows e o CMD historico
`00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd` no workspace privado,
referenciado pelo atalho existente. **Nao criar segundo CMD principal.**

O original v0.50 permanece preservado com SHA-256
`ade157d85582a791b6600dc19b611d00535bb58f16b51c3c416c8cd8de5d3931`.
A versao candidata privada v0.51 foi preparada mediante adicao, dentro
do proprio codigo de menu PowerShell incorporado, das opcoes 8-11:

| Opcao | Funcao |
|---|---|
| Enter/1 | Observar estado (comportamento anterior) |
| 2-7 | Funcoes originais MC-001, protecoes e confirmacoes preservadas |
| 8 | Abrir JaamSim com Assistente IA e StatFit |
| 9 | Revisar arquivo CFG pelo motor RCL local, sem alterar o original |
| 10 | Abrir a pasta de relatorios ja gerados |
| 11 | Mostrar estado dos modulos, sem iniciar processos |

A candidata privada e acompanhada por novo
`RODAR_JAAM_AI_COMPLETO.cmd.sha256` e
`JAAM_AI_LAB_V0_51_RELEASE_MANIFEST.json`. A opcao 7 confere
o manifesto e o hash da nova candidata, permanecendo no escopo
`OFFLINE_READINESS_DENY_ONLY`; nao ha P004 nem Full45 autorizado.
O backup da v0.50 e mantido separado e sem modificacao de bytes.

## Fronteira com o GitHub publico

O GitHub **nao** distribui o CMD historico de 2.1 MB nem uma copia
alternativa que pudesse competir com o atalho ja existente. O workflow
GitHub gera somente o pacote `JAAM_AI_NATIVE` com JAR Java, scripts
Python e exemplos publicos. Coloca-se esse diretorio **ao lado** do
CMD historico no workspace `00_PROJETO_ATUAL`. Os modulos nao sao
executados automaticamente.

O estado e `CANDIDATE_ONLY / GUI_PENDING / P004_DENY /
FULL45_NO_GO`. Por orientacao do usuario, nao executar testes
manuais ainda, nao instalar no sistema principal automaticamente,
nao mesclar PR e nao promover a release.
