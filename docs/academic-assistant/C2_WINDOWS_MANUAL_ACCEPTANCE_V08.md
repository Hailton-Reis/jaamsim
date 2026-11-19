# JAAM-AI C2 v0.8 — aceite GUI Windows em laboratório

**Estado:** CANDIDATE_ONLY / GUI_WINDOWS_MANUAL_PENDING / G0_G2_PENDING / P004_DENY / FULL45_NO_GO.

A candidata v0.7 já compila com Java 25 e passa no smoke de Swing em tela virtual Linux e em Windows headless. Esta etapa adiciona um **roteiro PowerShell de laboratório** para a última lacuna: documentar o funcionamento da interface completa no Windows gráfico real, sob controle do operador. O script **não concede aceite automaticamente**.

## Preparação

1. Baixe o artefato **jaam-ai-native-module** do GitHub Actions da branch v0.8 e extraia em uma pasta nova de laboratório. A pasta indicada em NativeRoot deve terminar exatamente em JAAM_AI_NATIVE. **Não** copie para 00_PROJETO_ATUAL e **não** substitua o CMD original.
2. Disponibilize Java 25 e Python 3.11 ou superior. O script recusa versões incompatíveis.
3. Baixe o script scripts/windows/JAAM_AI_C2_ACCEPTANCE_LAB.ps1 do **mesmo commit**. Execute como usuário comum, nunca como administrador. Use um diretório de evidências fora do módulo e da pasta operacional.
4. Primeiro execute apenas a pré-verificação:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\JAAM_AI_C2_ACCEPTANCE_LAB.ps1" -NativeRoot "C:\Lab\JAAM_AI_NATIVE" -EvidenceRoot "C:\Lab\Evidencias" -PreflightOnly
~~~

A pré-verificação compara SHA-256 e tamanho de todos os arquivos declarados no manifesto, rejeita caminhos relativos inseguros e links/junctions no pacote, verifica as classes C2 no JAR e confere Java/Python. Gera um JSON com status PREFLIGHT_ONLY_MANUAL_ACCEPTANCE_PENDING. **O manifesto do pacote não é uma assinatura digital.**

## Execução assistida

Após conferir a origem e a integridade, use:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\JAAM_AI_C2_ACCEPTANCE_LAB.ps1" -NativeRoot "C:\Lab\JAAM_AI_NATIVE" -EvidenceRoot "C:\Lab\Evidencias" -LaunchGui
~~~

Opcionalmente acrescente -CfgPath "C:\MeusModelos\teste.cfg". O arquivo de origem é **copiado** para uma sessão de laboratório; sem esse parâmetro, utiliza-se um CFG sintético do pacote. O script também copia o corpus/manifesto autorizados e prepara uma **cópia propositalmente adulterada** para o teste negativo.

Na janela do JaamSim, abra Ferramentas > Assistente de Simulação IA > Documentos C2 (prévia) e confira:

1. Busca positiva com fonte e citação;
2. Abstenção sem reuso de citações;
3. Cancelamento de consulta;
4. Alteração da pergunta durante busca e retorno ao texto original (ABA);
5. Recusa de corpus adulterado;
6. Nenhuma modificação do CFG.

Em cada cenário, o operador pode digitar CAPTURAR para salvar um PNG ou PULAR para não capturar. **A captura contém a tela inteira, inclusive outras aplicações; feche janelas privadas antes.** Nenhuma imagem é enviada pelo script.

Ao terminar e fechar o JaamSim, o roteiro compara os hashes SHA-256 do CFG original e da cópia. O relatório acceptance_report.json fica na sessão e permanece em status GUI_EXECUTED_MANUAL_REVIEW_REQUIRED, ou HOLD_CFG_INTEGRITY_FAILURE em caso de alteração. **Isso nunca representa homologação automática.**

## Teste no GitHub Actions

O workflow executa somente -PreflightOnly no Windows, com o módulo compilado no próprio workflow, e publica o JSON como artefato. A opção -LaunchGui é interativa e **não é executada** no runner. Os testes sintéticos e os hashes não substituem o aceite humano da interface completa.

Permanecem vedados LLM, C1–C4 confirmatório, alterações de CFG em produção, instalação, promoção de release, substituição do CMD original, P004 e Full45.
