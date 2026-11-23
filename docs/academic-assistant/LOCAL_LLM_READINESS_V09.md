# JAAM-AI — marco v0.9 de preparação para IA local

**Estado:** CANDIDATE_ONLY / SEM INFERÊNCIA REAL / GUI_WINDOWS_MANUAL_PENDING / G0_G2_PENDING / P004_DENY / FULL45_NO_GO.

## Por que não conectar o LLM ao JaamSim ainda?

A camada determinística e a recuperação C2 evoluíram em paralelo, mas o assistente de chat ainda usa provedores remotos em tcc_llm_assist.py. Antes de introduzir a inferência local, é necessário confirmar o runtime, identidade do modelo e os limites de confiança de um modo reproduzível.

O primeiro candidato experimental discutido é **IBM Granite 4.0 1B GGUF Q4_K_M**, não uma escolha final validada. O runtime pretendido é o **llama.cpp** (não um modelo em si). A execução de um modelo local, qualidade das respostas, function calling, consumo total em 8 GB e os quatro braços C1–C4 **não foram demonstrados** neste marco.

## Novo contrato: local_llama_preflight.py

Este módulo utiliza exclusivamente a biblioteca padrão Python, sem abrir modelos nem enviar prompts. Por padrão ele não faz nenhuma conexão: gera PLAN_ONLY_NO_NETWORK.

Com a opção explícita --probe, faz **somente dois GETs** de descoberta do servidor local:
- GET /health;
- GET /v1/models.

O endpoint aceita apenas http://127.0.0.1:PORT com porta explícita; rejeita hosts externos, localhost por DNS, TLS, fragmentos e autenticação embutida, e bloqueia redirecionamentos/proxies. Não implementa POST, chamadas de LLM, ferramentas de estado, leitura de CFG ou alterações no modelo. As IDs encontradas são registradas **apenas como SHA-256** para evitar expor caminhos locais.

É possível inspecionar um arquivo GGUF local **sem carregá-lo**: verifica os quatro bytes GGUF, tamanho e SHA-256 em streaming. A opção --expected-gguf-sha256 documenta uma expectativa explícita de identidade; a conferência do cabeçalho e hash NÃO confirma compatibilidade, segurança, licença nem validade do modelo.

### Exemplo 1 — sem rede

~~~bash
python extensions/academic-assistant/python/local_llama_preflight.py
~~~

### Exemplo 2 — somente descoberta de um servidor que já esteja rodando

~~~bash
python extensions/academic-assistant/python/local_llama_preflight.py --probe --endpoint http://127.0.0.1:9931
~~~

Não é necessário baixar pesos/modelos para executar os testes sintéticos. Os comandos NÃO fazem inferência, mesmo se um servidor real já estiver carregado. Em Windows, chamar com python em vez de python3 conforme a instalação.

### Exemplo 3 — conferência opcional de um GGUF obtido legalmente

~~~bash
python extensions/academic-assistant/python/local_llama_preflight.py --gguf-file /caminho/modelo.gguf --expected-gguf-sha256 <HASH_SHA256_64_HEXA>
~~~

O relatório é JSON, sempre declara model_generation_calls=0 e science_evidence=NONE. O status API_DISCOVERED_NO_GENERATION informa apenas que as rotas de descoberta respondem; **não** representa teste de prompt, execução correta do modelo ou validação da viabilidade com 8 GB.

## Portões antes do primeiro smoke real

1. Aceite visual da candidata C2 em Windows (separado da CI).
2. Seleção e licença do modelo exato, revisão, quantização GGUF, tokenizer/chat template, hash dos pesos e versão/commit do llama.cpp.
3. Serviço local somente em loopback; timeouts, quotas de saída, interceptação dos prompts e tool calls; chamadas ao CFG/estado proibidas nos braços que não as tenham.
4. **Smoke de engenharia, não confirmatório:** um único prompt sem ferramentas e sem RAG; depois um teste C2 com fonte documentada. Qualquer efeito científico continua condicionado aos gates G0/G2 e à adjudicação humana.
5. Medir separadamente uso de RAM/CPU do processo modelo e da pilha inteira (JaamSim+JVM+RAG+servidor+SO). O alvo HW001 de 8 GB é **sistema total**, não tamanho do arquivo GGUF.
6. Não integrar ao CMD privado, nem fazer merge dos PRs em rascunho sem os aceites correspondentes.

## Critérios de término do v0.9

- Testes negativos contra endpoints não locais, redirecionamentos, caminhos inválidos e payloads malformados.
- Resposta sintética positiva apenas para duas rotas GET.
- Pacotes GitHub Actions Windows/Linux Python 3.11/3.14 aprovados.
- Evidência explícita de que nenhuma chamada POST/inferência é feita.

**O v0.9 é apenas preparação para o primeiro teste real com llama.cpp.**
