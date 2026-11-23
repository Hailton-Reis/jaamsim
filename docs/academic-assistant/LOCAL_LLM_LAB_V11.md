# JAAM-AI v0.11 — laboratório de inferência local e medição de memória

**Estado:** CANDIDATE_ONLY · G0/G2 PENDING · P004 DENY · Full45 NO-GO · Windows GUI manual pending.

A v0.10 consegue realizar uma chamada POST de smoke quando o operador previamente carrega um modelo no servidor local. A v0.11 adiciona um **laboratório isolado para executar o servidor com identidade fixada** (sem instalar ou baixar pesos), realizar a mesma chamada curta e capturar evidências reproduzíveis de memória e latência.

## Restrições

- O comando requer **--execute** para abrir o processo. Sem a opção, somente verifica SHA-256 do executável e do arquivo GGUF, sem servidor, sem rede e sem escrever relatório.
- Executável e GGUF precisam existir como arquivos regulares e corresponder a hashes SHA-256 fornecidos pelo operador. Um cabeçalho GGUF e um hash não comprovam qualidade, licença, origem, autenticidade de pesos ou compatibilidade.
- O laboratório inicia exatamente um processo com argumentos fixos de CPU: 127.0.0.1, 1 slot, 2 threads, 2048 tokens de contexto, 0 camadas GPU. Não aceita argumentos extras, host remoto, proxies, downloads, scripts, ferramentas ou acesso ao CFG.
- A porta local deve estar livre, e o usuário deve indicar um diretório já existente para evidências. Cada execução ganha uma subpasta nova; o CMD do JaamSim e os arquivos da versão ativa não são modificados.
- Não encaminha variáveis de API tokens nem LLAMA_ARG_* herdadas. Não usa shell=True. O servidor é encerrado ao terminar ou falhar.
- A chamada de inferência continua sendo **um único prompt técnico fixo**; não usa RAG, RCL, StatFit ou ferramentas. O relatório não é resultado científico.

## Modo 1: checagem local sem iniciar nada

Na pasta raiz do clone, verifique os hashes:

Linux:
~~~bash
sha256sum /CAMINHO/llama-server /CAMINHO/Granite-1B-Q4_K_M.gguf
~~~

Windows PowerShell:
~~~powershell
Get-FileHash "C:\Lab\llama-server.exe" -Algorithm SHA256
Get-FileHash "C:\Lab\Granite-1B-Q4_K_M.gguf" -Algorithm SHA256
~~~

Depois:

~~~bash
python extensions/academic-assistant/python/local_llama_lab.py \
  --server-bin "/CAMINHO/llama-server" \
  --expected-server-sha256 HASH_DO_EXECUTAVEL_64_HEX \
  --gguf-file "/CAMINHO/Granite-1B-Q4_K_M.gguf" \
  --expected-gguf-sha256 HASH_DO_GGUF_64_HEX
~~~

Retorna `DRY_RUN_VERIFIED_FILES`. Os valores são espaços reservados: **não** use hashes inventados. O nome do modelo é um exemplo de candidato, não uma indicação de que o arquivo já esteja instalado.

## Modo 2: primeiro smoke real (somente no computador com pesos autorizados)

Crie um diretório de laboratório separado e execute o mesmo comando incluindo:

~~~text
--evidence-dir "/CAMINHO/EVIDENCIAS" --port 9931 --execute
~~~

O servidor será iniciado em CPU, com somente loopback, e ficará ativo apenas durante a sessão. Primeiro deverá responder ao GET /health e GET /v1/models; depois o cliente existente envia uma única chamada POST /v1/chat/completions com no máximo 48 tokens de saída. Não use a pasta de produção do JaamSim como diretório de evidências.

O relatório JSON registra:
- SHA-256 e tamanhos do binário/arquivo GGUF;
- SHA-256 do nome de modelo anunciado;
- quantas chamadas de geração foram feitas e o envelope bruto do smoke;
- tempo de inicialização, duração total, latência e tokens (quando informados pelo servidor);
- amostras do RSS do processo principal do servidor e RAM física usada no host;
- hash e tamanho do log local.

Amostragem de RAM: Linux usa /proc e Windows usa APIs nativas; sem permissão ou suporte, o campo fica null. **RSS do processo não inclui necessariamente processos filhos nem todos os buffers, e RAM usada no host inclui outros aplicativos.** O uso conjunto de JaamSim+RAG+servidor+SO não é medido neste laboratório. Portanto **não se pode declarar 8 GB validado**.

Os arquivos report.json e llama_server.log são criados apenas na subpasta nova. Logs podem conter caminhos pessoais e devem permanecer locais. O script não os envia a terceiros.

## Como interpretar

- DRY_RUN_VERIFIED_FILES = arquivos presentes e hashes correspondentes; nenhum modelo executado.
- LAB_SMOKE_OBSERVED_REVIEW_REQUIRED = uma API local respondeu após iniciar processo fixado; requer revisão do log, da implementação e do hardware. Não comprova, por si, que o modelo teve bom desempenho.
- LAB_FAILED = alguma pré-condição ou etapa falhou. Não promover nem inferir resultados científicos.

## Testes automáticos da CI

Os testes usam executável/GGUF **sintéticos** e um servidor HTTP simulado. O subprocesso é substituído por um stub, portanto **nenhum llama.cpp real é iniciado na CI**. A suíte verifica identidades, proibição de portas inseguras, ausência de variáveis de credenciais, bloqueios, argumentos CPU, encerramento e relatório. A CI comprova integridade do programa de laboratório, não inferência por pesos Granite.

## Próximos passos científicos

1. Registrar licença/versão/hash do Granite e do llama.cpp efetivamente escolhidos.
2. Executar o laboratório na máquina-alvo, coletando resultados reais e comparando logs de servidor.
3. Completar o aceite visual Windows C2 e medir o workload **integral** HW001.
4. Integrar a saída documental C2 à inferência em branch separada e somente depois iniciar piloto não confirmatório; G0/G2 e a adjudicação humana das tarefas permanecem pré-requisitos para o ensaio fatorial.
