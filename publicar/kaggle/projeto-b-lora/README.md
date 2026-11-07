# Projeto B: "Catálogo de mercado", LoRA de um LLM em português (notebook privado no Kaggle)

Notebook `rafabueno/catalogo-mercado-lora` (PRIVADO; GPU e internet ligadas no metadata; ainda **não rodou na GPU**, foi enviado com `--no-run` em 07/11/2026). O que ele faz: lê produtos do Brasil do Open Food Facts direto do Parquet remoto (DuckDB, só colunas e linhas necessárias), monta o rótulo (tag mais específica entre as 60 mais frequentes), separa treino e teste 80/20 e responde o mesmo teste de 3 jeitos: zero-shot (Qwen2.5-1.5B-Instruct em 4 bits), TF-IDF + SVM linear, e LoRA (QLoRA 4 bits, r=16, 1 época). Tabela final com acurácia, F1 macro e ms por item; 10 erros do LoRA; subida opcional do adapter para o HF (privado, desligada por padrão, token via Kaggle Secrets).

## Como gerar, testar e subir

```bash
cd /workspace/projetos/raio-x-fiscal
.venv/bin/python publicar/kaggle/projeto-b-lora/gerar_notebook.py                        # escreve notebook/catalogo-mercado-lora.ipynb
RXF_B_MODO=smoke RXF_B_SAIDA=.tmp/projeto-b .venv/bin/python publicar/kaggle/projeto-b-lora/gerar_notebook.py --run   # teste local (CPU): dados + TF-IDF
set -a; . ./.env; set +a
.venv/bin/kaggle kernels push -p publicar/kaggle/projeto-b-lora/notebook --no-run        # salva sem executar (privado)
.venv/bin/kaggle kernels push -p publicar/kaggle/projeto-b-lora/notebook                 # executa no Kaggle (gasta cota de GPU; só com OK)
.venv/bin/kaggle kernels status rafabueno/catalogo-mercado-lora
```

## Modos (`MODO` na 1ª célula; no Kaggle, editar a variável; localmente, `RXF_B_MODO`)

| Modo | Produtos BR | Zero-shot | LoRA (treino / teste) | Tempo estimado na T4 |
|---|---|---|---|---|
| `smoke` | 200 | não | não | só CPU, 1 a 4 min (o tempo é o download do Parquet remoto) |
| `rapido` | 3.000 | 300 itens | ~2.400 / 600 | 35 a 50 min (download 3 a 5, modelo 2 a 3, zero-shot 2 a 4, treino 12 a 20, avaliação 5 a 8) |
| `completo` | 60.000 | 1.000 itens | ~48.000 / 3.000 | 2 a 3 h (treino ~1,5 a 2 h); pode exigir 2 sessões ou `EPOCAS` fracionária por amostra |

Estimativas sem medição real (o notebook ainda não rodou na GPU). O limite semanal de GPU do Kaggle é ~30 h; a sessão máxima é 12 h.

## O que foi testado localmente (07/11/2026, CPU da VPS, sem torch)
- Esquema real do Parquet do Open Food Facts lido pelo DuckDB (111 colunas): `product_name` é `STRUCT(lang, text)[]`, `countries_tags` e `categories_tags` são `VARCHAR[]`, `brands`, `quantity`, `lang`, `code` são `VARCHAR`.
- Consulta com `list_contains(countries_tags, 'en:brazil')` + `LIMIT 200` funciona (sem lambdas no SQL: a sintaxe `->` foi descontinuada no DuckDB 2.0 e o Kaggle pode ter outra versão). Rótulo, split e TF-IDF + SVM rodaram no modo smoke (resultado no relatório da sessão).
- Não testado: células do modelo (zero-shot, LoRA, avaliação, subida ao HF) por falta de GPU e de torch aqui. Risco conhecido: versões de `peft`/`bitsandbytes`/`transformers` no Kaggle (o `apply_chat_template(..., return_dict=True)` precisa de transformers >= 4.41).

## O que falta antes de rodar na GPU
1. OK do Rafael para gastar cota de GPU (grátis, mas é a mesma cota do BERTimbau do Raio-X).
2. Opcional: cadastrar o secret `HF_TOKEN` no Kaggle (Add-ons › Secrets) se quiser subir o adapter direto para o HF.
3. Rodar em `rapido` primeiro; se a tabela fizer sentido, `completo`.
