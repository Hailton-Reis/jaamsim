# JAAM-AI — CMD central e compatibilidade com MC-001

**Estado:** candidata de desenvolvimento, sem aceitação gráfica/manual e sem promoção.
**Entrada única no Windows:** `RODAR_JAAM_AI_COMPLETO.cmd`, na raiz do pacote.

## Por que não alterar o CMD v0.50 original

O controlador legado do Google Drive tem **2.132.276 bytes**, contém o próprio
PowerShell e o pacote de prontidão offline embutidos. Seu SHA-256 verificável é:

`ade157d85582a791b6600dc19b611d00535bb58f16b51c3c416c8cd8de5d3931`

O manifesto `JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json` e o arquivo
`RODAR_JAAM_AI_COMPLETO.cmd.sha256` associam a versão `0.50` ao
nome e ao conteúdo **exatos** desse CMD. A opção 7 faz novamente essas
verificações antes da revisão P004, que continua **DENY / Full45 NO-GO**.
Renomear, reformular ou inserir outros comandos nesse arquivo invalidaria
as evidências originais. O código novo **não** altera o arquivo legado.

## Estrutura de desenvolvimento e integração

```text
JAAM_AI_JAAMSIM_NATIVE_CANDIDATE/
  RODAR_JAAM_AI_COMPLETO.cmd       <-- UNICO ponto de entrada Windows
  RODAR_LINUX.sh                    <-- entrada equivalente para Linux
  JaamSim2026-03.jar                <-- Java 25 / IA + StatFit
  MANIFEST_SHA256.json              <-- integridade do pacote candidato
  extensions/
    academic-assistant/
      python/modulo_ia_offline.py   <-- revisao CFG deterministica
      python/jaamsim_cfg_to_snapshot.py
      output/offline-review/        <-- criado apenas apos revisao
  legacy/MC001_v050/                <-- opcional, protegido por SHA-256
    RODAR_JAAM_AI_COMPLETO.cmd      <-- arquivo v0.50 ORIGINAL e INALTERADO
    RODAR_JAAM_AI_COMPLETO.cmd.sha256
    JAAM_AI_LAB_V0_50_RELEASE_MANIFEST.json
```

O novo ponto de entrada nunca invoca o CMD antigo por engano: a opção MC-001
só aparece após escolha explícita e exige os três arquivos íntegros. No
pacote produzido pelo CI o subdiretório `legacy/MC001_v050` contém **somente
instruções**; os três arquivos são preservados fora do repositório, no Drive
do projeto. Para acoplar o legado, copie os três arquivos originais sem
alteração de bytes ou configure `JAAM_LEGACY_DIR` apontando à sua pasta.

## Menu e comandos

| Entrada | Função | Comportamento seguro |
|---|---|---|
| Enter ou 1 | Estado | Somente leitura. Não inicia nenhum processo ou rede |
| 2 | Abrir JaamSim | Inicia GUI Java apenas por escolha explícita; IA e StatFit são janelas internas |
| 3 | Revisar CFG | Chama Python offline e escreve apenas os relatórios em `output/offline-review` |
| 4 | Abrir relatórios | Abre somente uma pasta já existente |
| 5 | MC-001 v0.50 | Só delega ao histórico após hash, sidecar e manifesto verificados |
| 0 | Sair | Não encerra servidores alheios |

Também há parâmetros para integração futura: `--help`, `--status`,
`--jaamsim`, `--review "arquivo.cfg"`, `--reports`, `--mc001`.
Nenhuma dessas operações é chamada automaticamente durante a abertura
padrão; usar parâmetros que iniciam programas exige uma ação deliberada.

O launcher configura `JAAMSIM_ASSISTANT_ROOT` para a extensão empacotada
e respeita `JAAMSIM_PYTHON` quando definido. A execução do Python não
altera o CFG e o pipeline de sugestões permanece sob revisão humana.

## Separação entre engenharia, teste e pesquisa

**Não executado nesta etapa:** testes manuais em Windows, avaliação visual
das janelas, inferência Granite, P004, Full45 ou experimentos confirmatórios.
Compilação/CI do projeto podem continuar validando integridade estática do
pacote sem qualquer aprovação de uso.

**Não mesclar** o PR enquanto a aceitação das interfaces estiver pendente.
Nenhuma geração ou reescrita de arquivos `.cfg` é permitida automaticamente.
