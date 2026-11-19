# JAAM-AI — C2 documental: pacote técnico de pré-validação

**Estado:** C2-RETRIEVAL-V0.2 / CANDIDATE_ONLY / G0-G2_PENDING / NOT_GUI_VALIDATED / NOT_CONFIRMATORY.

## Motivação

O Artigo 2 propõe quatro braços fatoriais. C2 significa **modelo + recuperação documental**, **sem ferramentas determinísticas de estado**, sem alteração de CFG e sem autorização de inferência confirmatória. A documentação recuperada é uma fonte de baixa confiança, jamais um comando operacional. Este pacote implementa **somente** a recuperação local e sua instrumentação preparatória; não invoca um LLM.

| Braço de pesquisa | Recuperação | Ferramentas de estado |
| --- | --- | --- |
| C1 | Não | Não |
| C2 | Sim | Não |
| C3 | Não | Sim, somente leitura |
| C4 | Sim | Sim, somente leitura |

C3/C4 **não** são implementados por este pacote. Nenhum braço recebe escrita.

## Código e limites

- `extensions/academic-assistant/python/c2_retrieval.py`: leitura de corpus imutável em memória, manifesto versionado, allowlist de documentos `.txt`/`.md`, verificação SHA-256, blocos com fonte e linhas, top-k determinístico, `search_docs` como única ferramenta exposta;
- `.../python/c2_context.py`: preparador de contexto **sem chamada de LLM**, conferindo os trechos contra a instância de corpus já verificada; citações e rótulos de confiança preservados;
- `.../python/c2_eval.py`: avaliação **sintética de recuperação** com Recall@k, MRR@k e abstenção negativa, sem indicadores científicos confirmatórios;
- `.../python/tests/test_c2_*.py`: regressões positivas e negativas com diretórios temporários e sem artefatos reais;
- `.../examples/c2-preflight/`: documentos e tarefas inteiramente sintéticos, incluindo texto de injeção simulado.

O manifesto define `source_id`, `path`, `sha256` e `corpus_version`. A pesquisa registra SHA-256 do manifesto, corpus, consulta e trechos, mas **esses hashes não são uma assinatura digital de proveniência**. A aplicação deve controlar confiança e licença do corpus por outras camadas. O corpus é carregado com limites de tamanho/quantidade e convertido em um snapshot estável.

O código recusa qualquer ferramenta diferente de `search_docs`. Em POSIX, os arquivos são abertos por descritores de diretório com `O_NOFOLLOW` para reduzir ataques TOCTOU/symlink. No Windows há inspeção de symlink/reparse point, **mas não há garantia equivalente contra troca concorrente de junctions**; a camada precisa de um teste/adaptador nativo antes de ser considerada robusta em ambiente adversarial Windows.

## Como executar em uma cópia do repositório

```bash
cd extensions/academic-assistant
python python/c2_retrieval.py --corpus-root examples/c2-preflight/corpus --manifest examples/c2-preflight/manifest.json --query "Queue Server chegada" --top-k 3
python python/c2_eval.py --corpus-root examples/c2-preflight/corpus --manifest examples/c2-preflight/manifest.json --cases examples/c2-preflight/cases.json --top-k 3
python -m pytest python/tests/test_c2_retrieval.py python/tests/test_c2_context_eval.py -q
```

Requisitos: Python 3.11+; a suíte de C2 não usa bibliotecas externas, mas o teste `pytest` usa o ambiente de desenvolvimento da extensão. Os arquivos do exemplo são sintéticos, não derivados do corpus JaamSim oficial, nem dos documentos reservados da pesquisa.

## Evidência: separação entre modos

- `model_access=True` é apenas um atributo **do braço experimental planejado**. O código desta entrega não chama modelo: `model_calls=0`.
- `search_docs` nunca chama `run_rcl`, `parse_cfg`, `inspect_model`, `compare_results`, `run_simulation` ou escrita.
- A preparação de contexto exige a mesma instância de corpus e valida novamente cada trecho; isso não prova que um futuro LLM ignorará injeção de prompt.
- Não armazenar chaves, tokens, credenciais ou corpus não autorizado.
- G0/G2 permanecem pendentes, `test_locked` não foi criado, P004=DENY, Full45=NO-GO.
- A cópia ativa do Drive `00_PROJETO_ATUAL/RODAR_JAAM_AI_COMPLETO.cmd` (v0.50) não pode ser substituída por este pacote. Candidata privada v0.69 permanece independente.

## Gates antes de integrar à UI

1. Revisão humana do contrato de C2, fontes documentais, direitos/licenças e termos de abstenção.
2. Instrumentação simétrica dos quatro braços sem leaks de ferramentas entre C2/C3/C4; negar e registrar acessos ilegítimos.
3. Validar acesso seguro a pastas no Windows real, incluindo junction, symlink, troca concorrente e arquivo aberto.
4. Fazer testes end-to-end com UI Java, sem gravar modelos originais, e só depois considerar promoção.
5. Congelar modelo, prompt, seed, corpus/manifesto, casos gold, avaliação e contexto após os gates G0/G2 e a revisão do orientador. Não relatar os ensaios sintéticos como evidência científica.
