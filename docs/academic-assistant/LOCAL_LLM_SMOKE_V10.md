# JAAM-AI v0.10 — primeira chamada local controlada, sem execução nesta CI

**Situação:** candidata de engenharia / G0 e G2 pendentes / P004 DENY / Full45 NO-GO / Windows GUI manual pendente.

A versão v0.9 apenas consulta GET /health e GET /v1/models. Esta v0.10 acrescenta um **smoke opcional com exatamente um POST** para um servidor de modelos já iniciado e carregado pelo operador. O script não baixa, instala, treina ou carrega pesos. Os testes automatizados usam exclusivamente servidor HTTP sintético; portanto **não são evidência de geração por um GGUF real**.

## Ordem para primeiro teste real (operador, em ambiente isolado)

1. Registrar commit/revisão do llama.cpp, licença, modelo GGUF, licença/revisão/quantização dos pesos e SHA-256 do arquivo. Não considerar nomes ou "model id" como atestado de correspondência dos pesos.
2. Iniciar o llama-server manualmente com bind **somente em 127.0.0.1**, por exemplo, trocando o caminho pelo GGUF autorizado:

~~~text
llama-server -m "CAMINHO_DO_MODELO.gguf" --host 127.0.0.1 --port 9931 -c 2048
~~~

3. Num terminal separado, executar somente descoberta, sem geração:

~~~text
python extensions/academic-assistant/python/local_llama_preflight.py --probe --endpoint http://127.0.0.1:9931
~~~

4. Copiar o **único** campo `model_id_sha256` retornado em seu array de hashes. Se não houver exatamente um modelo, interromper. Conferir separadamente o hash do GGUF com `--gguf-file` e, se disponível, `--expected-gguf-sha256`.
5. Primeira chamada experimental: opção **--execute** deve ser incluída expressamente; sem ela o código produz apenas DRY_RUN_NO_REQUESTS e não faz chamadas de rede:

~~~text
python extensions/academic-assistant/python/local_llama_smoke.py --expected-model-id-sha256 HASH_REAL_COM_64_CARACTERES --endpoint http://127.0.0.1:9931 --execute
~~~

Somente este roteiro isolado permite um POST /v1/chat/completions com prompt curto e fixo, max_tokens=48, temperature=0, stream=false, tools=[] e limites de tempo. Não consulta RAG, CFG, RCL ou o chat online existente. A saída informa texto observado, hash da resposta, latência do cliente e token usage **se o servidor reportar**. Sem `--execute`, o teste não realiza inferência.

## Limitações metodológicas

- `model_id_sha256` pinado é um bloqueio de seleção do nome anunciado pelo servidor, **não** prova identidade criptográfica dos pesos usados. O servidor pode anunciar outro modelo ou uma implementação compatível que não seja llama.cpp.
- O status LOCAL_GENERATION_OBSERVED_UNATTESTED significa somente que o endpoint respondeu com um envelope compatível; **não atesta que um GGUF real executou**. Essa evidência só é aceitável junto com logs, processo/binário, pesos e hardware observados.
- Testes de CI usam respostas sintéticas; sucesso da CI valida o contrato do cliente, não qualidade, velocidade real ou viabilidade em 8 GB.
- O prompt fixo avalia conectividade, não correção técnica, RAG, hallucination, alignment, function calling ou segurança real do modelo.
- Medição de "latency_ms" não inclui auditoria independente de inicialização do modelo, recursos de todo o host, JVM/JaamSim ou SO. HW001 8 GB continua pendente.
- G0/G2 e 54 golds com revisão humana continuam necessários **antes** de qualquer estudo C1–C4 confirmatório. Nenhum resultado científico é autorizado por este script.

## Próximo marco

Registrar o primeiro smoke real com logs reproduzíveis do llama-server + hash do modelo e do runtime, medição externa de RAM/CPU, latência, e conferência se o texto foi realmente gerado. Depois integrar, em branch separada, o cliente local com o envelope C2, mantendo C2 incapaz de consultar ferramentas de estado e o JaamSim incapaz de escrita automática.
