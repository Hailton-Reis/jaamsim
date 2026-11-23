# JAAM-AI v0.12 — C2 para IA local: experimento de engenharia

**Status:** CANDIDATE_ONLY; G0/G2 pendentes; P004 DENY; Full45 NO-GO; GUI Windows manual pendente.

Este marco liga a busca documental C2 existente a um servidor local compatível com llama.cpp, mas **somente em um laboratório com corpus sintético**. Não realiza o experimento científico C1–C4, não lê estados do JaamSim, não usa RCL nem executa ferramentas ou escrita no CFG.

## Garantias e limitações

1. É obrigatório informar o SHA-256 exato do manifesto C2 antes de buscar documentos. A recuperação confere o hash de cada fonte e o programa recusa corpus sem versão começando por SYNTHETIC_.
2. A ponte reutiliza o contrato já testado de preflight C2: confere o envelope, a identidade do corpus, hashes de recibo/mensagens, papéis, citações e correspondência de cada passagem com o snapshot do corpus.
3. **Sem --execute** prepara a busca, devolve DRY_RUN_NO_MODEL_CALL e não faz qualquer requisição HTTP.
4. **Sem evidência** devolve ABSTAINED_NO_EVIDENCE_NO_GENERATION, inclusive se --execute estiver presente. Não faz consulta ao servidor.
5. **Com --execute e documentos**, faz somente GET /health e GET /v1/models em 127.0.0.1 com porta explícita, sem proxy nem redirecionamento. Exige exatamente um modelo anunciado, com ID cujo hash foi informado antecipadamente. Só então faz um único POST /v1/chat/completions, até 128 tokens, temperatura zero, sem tools e sem streaming.
6. A resposta não é executada nem tratada como verdade. O relatório lista citações presentes na saída que não constavam das fontes recuperadas. Uma citação presente nas fontes **não significa que sustente a afirmação**.
7. O hash do ID do servidor não é atestado dos pesos GGUF. Inferência verdadeira, consumo total de memória em 8 GB e qualidade científica continuam não demonstrados.

## Uso: modo seco, sem modelo e sem rede

Calcule o SHA-256 real do manifesto no clone:

~~~bash
python -c "import hashlib,pathlib; p=pathlib.Path('extensions/academic-assistant/examples/c2-preflight/manifest.json'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
~~~

Execute com os hashes reais (não invente valores):

~~~bash
python extensions/academic-assistant/python/c2_local_inference.py \
  --corpus-root extensions/academic-assistant/examples/c2-preflight/corpus \
  --manifest extensions/academic-assistant/examples/c2-preflight/manifest.json \
  --message "Queue Server" \
  --expected-manifest-sha256 HASH_REAL_MANIFESTO_64HEX \
  --expected-model-id-sha256 HASH_REAL_ID_MODELO_64HEX
~~~

No Windows, use uma linha única ou a continuação de linha do PowerShell.

## Próxima etapa: inferência somente no laboratório

Depois de verificar binário, licença e arquivo GGUF pela v0.11, inicie o servidor local em 127.0.0.1:9931. Descubra o ID via local_llama_preflight.py --probe. Execute o comando acima incluindo --endpoint http://127.0.0.1:9931 --execute.

Mesmo se a API responder com C2_LOCAL_RESPONSE_OBSERVED_UNATTESTED, isso **não comprova** que o Granite real executou, que os trechos sustentam a resposta ou que o protótipo foi homologado.

## Regressões

A suíte de teste usa servidor HTTP simulado, sem baixar ou executar GGUF: consulta positiva, citações reconhecidas/não reconhecidas, falha de manifesto e corpus, versão não sintética, abstenção, porta/host fora de loopback, modelo não identificado, conteúdo malicioso em fonte e resposta com pedido de ferramenta. O cliente de produção e o CMD ativo permanecem inalterados.

**Nenhum estudo C1–C4 confirmatório será executado sem G0/G2, corpus documental oficial aprovado e revisão humana dos 54 casos.**
