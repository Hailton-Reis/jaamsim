# JAAM-AI C2 v0.5 — vínculo entre evidências exibidas e contexto documental

Estado: `CANDIDATE_ONLY / G0_G2_PENDING / JAVA_GUI_WINDOWS_PENDING / P004_DENY / FULL45_NO_GO`.

## Correção funcional

A prévia Java v0.4 verificava os hashes SHA-256 dos trechos no recibo e a identidade do manifesto, mas aceitava o conteúdo de `model_messages[2]` apenas por começar com o rótulo `DOCUMENTOS_RECUPERADOS_JSON`. Não exigia igualdade entre os trechos efetivamente inseridos no contexto C2 e as fontes mostradas ao operador.

A v0.5 extrai o JSON da terceira mensagem de modelo, exige o contrato `jaam.ai.c2.evidence_context.v1`, valida o braço C2, rótulo de baixa confiança, abstenção, contagem e orçamento. **Cada item do contexto deve coincidir, na mesma ordem, com o início dos hits do recibo:** `source_id`, citação, passagem, SHA-256 e rótulo. O número de registros omitidos precisa coincidir com o orçamento real. Qualquer divergência bloqueia a resposta na aba, sem exibir uma citação contraditória.

Isso é verificação de consistência de envelopes **dentro da mesma execução local**. Não certifica autenticidade independente do Python/host, assinatura criptográfica, veracidade de fontes nem resistência a processos maliciosos com controle da máquina.

## Higiene do processo experimental

Antes de `ProcessBuilder.start()`, a chamada Java filtra do ambiente herdado variáveis com nomes típicos de tokens, senhas, segredos, chaves privadas e configurações de provedores (`OPENAI_`, `GROQ_`, `CEREBRAS_`, `NVIDIA_`, `ANTHROPIC_`). `PATH`, `SystemRoot` e variáveis não sensíveis permanecem para compatibilidade com a inicialização do Python. A filtragem reduz a chance de propagar credenciais, **mas não transforma o subprocesso em sandbox**.

## Validação da candidata

- 99 testes Python + 33 subtestes locais da v0.4 mantidos no ambiente Linux;
- 45 verificações de contratos Java headless no JDK 21 usando implementações simuladas de JSON e lançamento (não equivalentes à compilação do JaamSim completo);
- Java -> subprocesso Python -> JSON -> validação C2 concluído em um corpus inteiramente sintético, sem rede e sem LLM;
- Foi utilizada uma constante simulada de `simulation_chat_assist.SYSTEM_PROMPT` somente no ensaio end-to-end; a execução com classes reais do JaamSim ainda depende da CI JDK25.

## Ainda não autorizado

- Não executar inferência de modelos, experimentos P004/Full45 ou benchmark confirmatório dos quatro braços;
- Não mesclar o PR existente, alterar arquivos ativos no Drive, substituir o CMD/atalho ou instalar a candidata no Windows;
- Nenhuma aprovação de G0/G2 ou aceite GUI/Windows foi produzida.

## Proposta de CI

Aplicar o patch v0.4 original seguido do incremento v0.5 em uma **branch isolada** da branch `fix/jaam-ai-resource-provenance-20261113`, abrir PR em rascunho e exigir os workflows Java 25/Ant e Python Linux/Windows antes de qualquer teste manual.

## Defeito adicional reproduzido com o parser JSON real

A v0.4 usava `json.dumps(..., ensure_ascii=True)` para a resposta de CLI. O JSONParser real do JaamSim 2026-03 interpreta incorretamente, neste contexto, alguns caracteres Unicode escapados: trechos de `dados não confiáveis` recebiam um caractere tab adicional, causando falha na validação do prefixo da mensagem. A falha foi reproduzida com o **JAR nativo extraído do artefato Java do GitHub Actions 43903459615** e o bridge Python local. A v0.5 emite UTF-8 direto (`ensure_ascii=False`), utilizando `PYTHONIOENCODING=utf-8` fixado pelo runner, e a interoperabilidade foi retestada com o `JSONParser` verdadeiro.

Um novo teste headless Java, `C2PythonInteropContractTest.java`, realiza execução Java->Python->JSON em documentos sintéticos, incluindo busca positiva, abstenção e manifesto corrompido. O workflow JDK25/Ant deve incluir essa verificação após a compilação completa.

Validação local adicional (Linux): 7 verificações de interoperabilidade Java/Python usando o **JAR real** v0.69 compilado em CI, 45 contratos com as classes reais do JAR e a suíte Python de 99 testes + 33 subtestes. Isso **não comprova build full da nova branch** e usa uma constante simulada de prompt durante o smoke test local; o CI da branch deverá executar com o módulo de chat real e JDK25.
