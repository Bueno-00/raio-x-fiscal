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

## Resultado da 1ª rodada (versão 1, modo rápido, 07/11/2026)

1 época, 48 tokens, 16 min de treino numa T4 (~550 descrições por segundo), 526.441 descrições, 6.589 NCMs.
Teste em 2025-09 (547.718 itens), mesmos cortes do baseline:

| Corte | BERTimbau top-1 / top-5 | Híbrido lookup -> BERTimbau | Baseline (híbrido lookup -> SVM) |
|---|---:|---:|---:|
| todos | 61,5% / 79,4% | 75,1% / 85,8% | **78,7% / 87,8%** |
| nunca vistas, únicas | 48,6% / 68,9% | 48,6% / 68,9% | **60,0% / 76,1%** |

**O baseline ainda ganha.** Com uma época só, o BERTimbau não aprendeu a cauda longa (F1 macro de 9% contra
26,5% do baseline nas nunca vistas). Por isso o semáforo do produto continua com o modelo TF-IDF + SVM.
A versão 2, em modo completo (3 épocas, 64 tokens, orçamento de 150 min), foi enviada em 07/11/2026 ~21h30;
ela só entra no produto se ganhar do baseline no mesmo mês de teste.

## Resultado da 2ª rodada (versão 2, modo completo, terminou em 08/11/2026 01:33 UTC)

3 épocas, 64 tokens, 62 min de treino numa T4 (~426 descrições por segundo; 6.171 passos), temperatura 1,1.
Mesmo teste (2025-09, 547.718 itens) e mesmos cortes:

| Corte | BERTimbau top-1 / top-5 | Híbrido lookup -> BERTimbau | Baseline (híbrido lookup -> SVM) |
|---|---:|---:|---:|
| todos | 69,5% / 86,5% | 77,7% / **88,9%** | **78,7%** / 87,8% |
| únicas | 62,3% / 81,3% | 69,1% / **83,9%** | **71,2%** / 83,2% |
| nunca vistas | 58,9% / **77,9%** | 58,9% / 77,9% | **62,1%** / 77,5% |
| nunca vistas, únicas | 56,6% / **76,6%** | 56,6% / 76,6% | **60,0%** / 76,1% |

F1 macro nas nunca vistas únicas: 19,4% (v1: 9,0%; baseline: 26,5%). Auditoria (confiança ≥ 0,99 e NCM
declarado diferente): 105 itens (0,02%) contra 3.580 (0,65%) do baseline.

**O baseline continua no semáforo.** A regra era trocar só se o BERTimbau ganhasse nas descrições nunca
vistas, e no top-1 (o que o semáforo usa) ele ainda perde por 3,4 pontos. Ele já empata ou passa no top-5 e
erra de um jeito diferente, por isso o próximo teste é o conjunto dos dois (média das probabilidades).
Saída baixada em `.tmp/bertimbau-v2-saida/` (fora do git; o modelo fp16 tem 229 MB e fica privado).

