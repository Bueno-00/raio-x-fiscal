# FASE 2, parte 2: BERTimbau na GPU do Kaggle (privado)

**Português** · [English](README.en.md)

Notebook `rafabueno/raio-x-fiscal-ncm-bertimbau` (privado, GPU T4, internet ligada só para baixar o
modelo `neuralmind/bert-base-portuguese-cased` do Hugging Face). Lê o dataset privado
`rafabueno/nfe-ncm-brasil-raio-x-fiscal` e faz o *fine-tuning* do BERTimbau base para classificar a
descrição do produto no NCM de 8 dígitos.

## Mesmo protocolo do baseline

- Split temporal: treino 2025-04 a 2025-07, validação 2025-08 (só calibra a temperatura da confiança),
  teste 2025-09.
- Treino deduplicado por descrição normalizada: rótulo = NCM mais frequente, peso `log(1 + ocorrências)`
  na perda. O texto de entrada é a grafia original mais frequente (o BERTimbau é *cased* e conhece acento);
  a descrição normalizada segue como chave de dedup, de "vista / não vista" e do lookup.
- Quatro cortes do mês de teste (`todos`, `unicos`, `nao_vistos`, `nao_vistos_unicos`) e o híbrido
  lookup → modelo. A tabela final põe as linhas do baseline (`reports/ml_results.md`) ao lado.

## Escolhas e por quê

- **Classificação plana em todos os NCMs do treino (~6,6 mil classes).** A cabeça linear tem 768 × 6,6 mil
  ≈ 5 milhões de parâmetros: cabe com folga na T4. Nenhum NCM raro foi agrupado em "outros"; NCM do teste
  que não existe no treino conta como erro, igual ao baseline.
- **fp16, batch 256, AdamW** (taxa 5e-5 no encoder e 1e-3 na cabeça nova), aquecimento de 6%,
  *clipping* 1,0.
- **Orçamento de tempo:** o agendamento linear usa o maior entre o progresso em passos e o progresso no
  relógio. Se o orçamento acabar antes da época, a taxa já chegou a zero e o modelo termina "fechado".
- **Predição por grafia única** do mês de teste, copiada para os itens repetidos.
- Uma GPU só (a sessão "T4 x2" deixa a segunda livre): menos risco de erro na primeira rodada.

| Modo | Épocas | Tokens | Orçamento de treino | Tempo total estimado |
|---|---:|---:|---:|---:|
| `MODO_RAPIDO = True` (padrão, versão 1) | 1 | 48 | 25 min | ~40 min |
| `MODO_RAPIDO = False` | 3 | 64 | 150 min | ~3 h |

## Saídas (em `/kaggle/working`)

`resultados_bertimbau.md` (tabela BERTimbau x baseline), `metricas_bertimbau.json` (tudo, inclusive o
histórico da perda e a velocidade), `divergencias_confiantes.csv` (300 descrições em que o modelo discorda
do declarado com mais confiança) e `modelo-bertimbau-ncm/` (pesos fp16, ~220 MB, tokenizer e temperatura).

## Comandos

```bash
# gerar o notebook e conferir a sintaxe
python3 publicar/kaggle/bertimbau/gerar_notebook.py --check
python3 publicar/kaggle/bertimbau/gerar_notebook.py

# teste de fumaça local em CPU (precisa de torch e transformers; modelo minúsculo, números sem sentido)
RXF_PUBLISH_PARQUET=/caminho/amostra.parquet RXF_NB_SMOKE=1 RXF_NB_MODELO=hf-internal-testing/tiny-random-bert \
  RXF_NB_SAIDA=/tmp/saida python3 publicar/kaggle/bertimbau/gerar_notebook.py --run

# subir e rodar no Kaggle (privado, T4, limite de 3 h)
set -a; . ./.env; set +a
.venv/bin/kaggle kernels push -p publicar/kaggle/bertimbau/notebook --accelerator NvidiaTeslaT4 -t 10800
.venv/bin/kaggle kernels status rafabueno/raio-x-fiscal-ncm-bertimbau
.venv/bin/kaggle kernels logs rafabueno/raio-x-fiscal-ncm-bertimbau          # log ao vivo
.venv/bin/kaggle kernels output rafabueno/raio-x-fiscal-ncm-bertimbau -p .tmp/bertimbau-saida
```

O teste de fumaça local rodou de ponta a ponta em 07/11/2026 (amostra de 87 mil itens, modelo
`hf-internal-testing/tiny-random-bert`, CPU): carga, dedup, cortes, treino, calibração, predição,
tabela e arquivos de saída.
