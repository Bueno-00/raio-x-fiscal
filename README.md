# Raio-X Fiscal

Plataforma de IA para o setor contabil construida sobre **notas fiscais eletronicas publicas**
(compras do governo federal, Portal da Transparencia): pipeline medalhao em DuckDB com qualidade
de dados medida, baseline de machine learning para **classificar descricao de produto em NCM**, e
uma auditoria que aponta NCMs declarados que provavelmente estao errados.

> **TL;DR in English.** Brazilian invoices (NF-e) carry an 8-digit product code (NCM, the local
> extension of the Harmonized System) that drives every tax rate; a wrong NCM means a wrong tax,
> and the same text-to-code problem is marketplace catalogue categorisation. This repo takes six
> months of public federal-procurement invoices (3.1 M line items, R$ 46 bi), runs them through a
> local medallion pipeline (DuckDB + Python, Airflow DAG included) with explicit data-quality
> expectations, and trains an honest baseline for description -> NCM: temporal split, dedup by
> normalised description between train and test, leakage numbers reported side by side, hierarchical
> TF-IDF + LinearSVC (chapter, then NCM inside the chapter) with temperature-calibrated
> confidence, and an NCM audit whose alerts were inspected by hand. Phase 2 fine-tunes a Portuguese
> encoder on Kaggle and publishes model, dataset and Space on Hugging Face; Phase 3 adds a
> read-only text-to-SQL analytical agent with a numeric guard (every number in the answer must
> exist in the query result) and an eval harness. No customer data: public open data only, with
> emitter identifiers removed from anything meant for publication.

<!-- RESULTS_BOX_START -->
> **Resultados (FASE 1, medidos em 04/11/2026).** 6 meses (2025-04 a 2025-09), **878.858 notas** e
> **3.124.925 itens** (R$ 46,5 bi em itens), 7.381 NCMs distintos, 0 linhas rejeitadas e 0 duplicatas,
> 98,8% a 99,2% dos itens com NCM valido. Divergencias encontradas e documentadas: soma dos itens
> diferente do total da nota em 14% a 23% das notas por mes; orgao destinatario ausente em 83% das
> linhas do arquivo de itens (mas presente em 98,5% das notas); 4.344 notas sem nenhum item.
> Baseline descricao -> NCM (TF-IDF + LinearSVC hierarquico, so CPU): **78,7%** de acerto no NCM de 8
> digitos no mes de teste e **60,0% / 76,1%** (top-1 / top-5) nas descricoes nunca vistas. Auditoria de
> NCM: 3.580 alertas no mes de teste; numa inspecao manual de 60, **50 (83%)** eram NCM declarado errado
> com a sugestao do modelo correta, e 3 (5%) eram erro do modelo.
<!-- RESULTS_BOX_END -->

---

## O problema

Toda nota fiscal brasileira classifica cada item com um **NCM** (Nomenclatura Comum do Mercosul, 8
digitos, extensao do Sistema Harmonizado). O NCM decide IPI, PIS/COFINS, ICMS-ST e enquadramentos de
beneficio fiscal. Na pratica quem escolhe o codigo e o fornecedor, a partir de uma descricao livre
("ARROZ TIPO 1", "CABO FLEXIVEL 2,5MM2 750V"), e o escritorio contabil herda o erro: paga imposto a mais,
ou a menos e recebe autuacao depois.

Dois fatos tornam isso um problema de dados e de IA ao mesmo tempo:

1. O mesmo texto recebe NCMs diferentes de fornecedores diferentes. Nestes dados, entre os itens de
   teste cuja descricao identica ja existia no treino, o NCM coincide em so **86,5%** dos casos.
2. O volume e grande e repetitivo: 3,1 milhoes de itens em seis meses, mas so ~900 mil descricoes
   distintas. Qualquer avaliacao que ignore a repeticao mede memoria, nao generalizacao.

E o mesmo problema de **categorizacao de catalogo** em marketplace: texto curto, ruidoso, digitado por
terceiros, milhares de classes hierarquicas e custo real quando a classe sai errada.

## O que este repositorio prova (FASE 1)

1. **Engenharia de dados reproduzivel e barata** (`src/raio_x_fiscal/pipeline/`): zip mensal da CGU
   (CSV latin-1, `;`, decimal com virgula) -> bronze -> silver -> gold em DuckDB, local, idempotente por
   mes, com contrato de schema que falha alto quando a fonte muda.
2. **Qualidade de dados como codigo** (`pipeline/quality.py`): expectativas explicitas por camada,
   numeros gravados em JSON e relatorio em markdown com o que foi medido, inclusive o que nao bate
   ([reports/quality_report.md](reports/quality_report.md)).
3. **Baseline de ML honesto** (`src/raio_x_fiscal/ml/`): split temporal, dedup por descricao
   normalizada, numero "como em producao" ao lado do numero "descricoes nunca vistas", calibracao em mes
   de validacao separado, latencia medida ([reports/ml_results.md](reports/ml_results.md)).
4. **Aplicacao de negocio**: auditoria de NCM com limiar escolhido por precisao alvo e amostra
   inspecionada a mao, dizendo quantos alertas parecem erro real e quantos sao erro do modelo
   ([reports/ncm_audit.md](reports/ncm_audit.md), [reports/ncm_audit_inspection.md](reports/ncm_audit_inspection.md)).
5. **Orquestracao dos dois jeitos**: `make pipeline` por CLI na VPS e a mesma sequencia como DAG do
   Airflow com mapeamento dinamico por mes (`dags/`, `airflow/docker-compose.yml`), parse validado
   com Airflow 2.10.5.
6. **Dataset anonimizado pronto para publicar** na FASE 2 (Kaggle / Hugging Face), com dataset card
   ([docs/DATASET_CARD.md](docs/DATASET_CARD.md)).

## Arquitetura

```mermaid
flowchart LR
  CGU["Portal da Transparencia (CGU)<br/>zip mensal: 3 CSV latin-1, ';'"]
  subgraph med["Pipeline medalhao (DuckDB + Python, local e gratuito)"]
    B["bronze<br/>parquet bruto, contrato de schema,<br/>metadados de ingestao"]
    S["silver<br/>tipos BR, NCM 8 digitos, CFOP,<br/>descricao normalizada, rejects, dedup"]
    G["gold<br/>fato_item, fato_nota, dim_ncm, dim_orgao,<br/>agregados, ml_ncm_items (anonimizada)"]
    Q["quality<br/>expectations por camada,<br/>JSON + relatorio"]
    B --> S --> G
    Q -.-> B
    Q -.-> S
    Q -.-> G
  end
  CGU -->|"rxf download"| B
  G --> ML["FASE 1: baseline<br/>TF-IDF + LinearSVC hierarquico<br/>descricao -> capitulo -> NCM"]
  ML --> AUD["Auditoria de NCM<br/>alertas com confianca calibrada"]
  G --> DS["Dataset anonimizado<br/>+ dataset card"]
  DS -.-> F2["FASE 2: fine-tuning de encoder PT-BR<br/>no Kaggle; modelo, dataset e Space no HF"]
  G -.-> F3["FASE 3: agente analitico em PT-BR<br/>text-to-SQL somente leitura, trava numerica,<br/>evals + ataques de injecao"]
  subgraph orq["Orquestracao"]
    CLI["make pipeline (VPS)"]
    AF["Airflow DAG<br/>(docker-compose, fora da VPS)"]
  end
  orq -.-> med
```

As tres camadas vivem em `data/` (fora do git): `bronze/<entidade>/mes=AAAAMM/`,
`silver/<entidade>/mes=AAAAMM/` (Parquet particionado por mes) e `gold/raio_x_fiscal.duckdb` (+ export
Parquet de cada tabela). Reprocessar um mes substitui a particao dele; o gold e refeito por completo
(`CREATE OR REPLACE`). Rodar duas vezes da o mesmo resultado.

## Fonte dos dados, licenca e LGPD

- **Fonte:** Portal da Transparencia (Controladoria-Geral da Uniao), conjunto "Notas Fiscais",
  download mensal em `https://portaldatransparencia.gov.br/download-de-dados/notas-fiscais/AAAAMM`
  (redireciona para o bucket de dados abertos da CGU). Tres arquivos por mes: `NotaFiscal` (cabecalho),
  `NotaFiscalItem` (itens) e `NotaFiscalEvento` (eventos; vazio nos meses processados).
- **Licenca dos dados:** dados abertos do governo federal. O catalogo dados.gov.br registra os conjuntos
  da CGU sob **ODbL (Open Database License)**; antes de publicar o dataset derivado na FASE 2 isso sera
  confirmado na pagina do conjunto e citado no card. O codigo deste repositorio e MIT.
- **LGPD:** o emitente de uma NF-e pode ser pessoa fisica (CPF). Regras aplicadas:
  - no **gold**, CPF vira hash com sal (`cpf:<16 hex>`) e a razao social da pessoa fisica e descartada;
    CNPJ de empresa permanece (compra publica de pessoa juridica e informacao publica). Checagem
    `fato_nota_cpf_mascarado` garante isso a cada build. Nos seis meses processados nao havia nenhuma
    nota emitida por CPF, entao a regra esta coberta pelos testes, nao pelos dados;
  - a tabela de ML (`ml_ncm_items`) e o dataset publicavel **nao carregam** chave de acesso, CPF/CNPJ,
    razao social, inscricao estadual nem CNPJ/nome do destinatario. Ficam descricao, NCM, CFOP,
    unidade, quantidade, valores, UF e mes. `item_id` e um md5 da chave + numero do item. A checagem
    `ml_sem_identificadores` falha o build se alguma dessas colunas aparecer.

## Pipeline medalhao

| Camada | O que faz | Chave / idempotencia |
|---|---|---|
| **bronze** (`bronze.py`) | extrai o zip, valida o cabecalho contra o contrato (`schema.py`), le o CSV com DuckDB (`encoding='latin-1'`, tudo VARCHAR), grava Parquet ZSTD + `_mes_referencia`, `_source_file`, `_ingested_at`, manifesto JSON; apaga o CSV extraido | uma particao por mes e entidade; reprocessar substitui |
| **silver** (`silver.py`) | renomeia para snake_case, tipa (`DECIMAL` a partir de `1.234,56`, `DATE` de `dd/mm/aaaa`, codigos inteiros), normaliza NCM para 8 digitos (o CSV perde o zero a esquerda dos capitulos 01 a 09 e usa `-1` para ausente), valida CFOP, normaliza a descricao (minusculas, sem acento, so `[a-z0-9]`), separa **rejects** com motivo (chave sem 44 digitos, data ou valor invalidos), deduplica pela chave natural | nota: `chave_acesso`; item: `(chave_acesso, numero_produto)` |
| **gold** (`gold.py`) | `fato_item`, `fato_nota`, `dim_ncm` (capitulo/posicao/subposicao + descricao oficial mais frequente), `dim_capitulo` (97 capitulos e secoes, seed), `dim_cfop`, `dim_orgao`, `dim_destinatario`, `dim_uf`; agregados `agg_gasto_ncm_mes`, `agg_gasto_orgao_mes`, `agg_gasto_capitulo_uf_mes`; `ml_ncm_items` anonimizada | refresh completo em um arquivo DuckDB + export Parquet |

As regras de normalizacao existem em **SQL (silver) e em Python (inferencia)**, e um teste garante que
as duas versoes concordam (`tests/test_normalize.py::test_sql_and_python_rules_agree`).

### Qualidade de dados: o que foi medido

Resumo por mes (silver). Relatorio completo, com todas as checagens e detalhes, em
[reports/quality_report.md](reports/quality_report.md).

| Mes | Notas | Itens | Rejeitadas | Duplicadas | NCM valido | qtd x unit = total | Soma itens = nota |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-04 | 128.641 | 470.126 | 0 | 0 | 99,11% | 100% | 77,37% |
| 2025-05 | 143.760 | 523.639 | 0 | 0 | 99,13% | 100% | 84,46% |
| 2025-06 | 147.791 | 517.843 | 0 | 0 | 99,12% | 100% | 85,17% |
| 2025-07 | 173.981 | 569.088 | 0 | 0 | 99,22% | 100% | 85,92% |
| 2025-08 | 135.999 | 489.660 | 0 | 0 | 98,83% | 100% | 83,30% |
| 2025-09 | 148.686 | 554.569 | 0 | 0 | 98,78% | 100% | 83,90% |

Divergencias encontradas (registradas como `warn`/`info`, nao escondidas):

- **Soma dos itens x valor da nota** bate em 77% a 86% das notas. Onde nao bate, em metade dos casos os
  itens somam mais (desconto incondicional lancado no total da nota) e na outra metade menos (frete,
  IPI, ICMS-ST e outras despesas acessorias entram no total). No agregado dos seis meses os itens
  somam **R$ 46,5 bi** e as notas **R$ 39,3 bi**; a diferenca (R$ 7,7 bi de itens acima da nota) esta
  concentrada no capitulo 30 (produtos farmaceuticos, compras do Ministerio da Saude com desconto
  grande sobre o preco de tabela). Por isso o valor de item e o valor de nota sao fatos separados no gold.
- **NCM invalido** em 0,8% a 1,2% dos itens: quase tudo e o sentinela `-1` ("sem NCM", tipico de
  servicos descritos como item); um residuo tem capitulo inexistente. 85 mil itens por mes vinham com
  7 digitos por perda do zero a esquerda: corrigidos, nao descartados.
- **Orgao destinatario** aparece como "Sem informacao" em **83% das linhas do arquivo de itens**, mas
  esta preenchido em 98,5% das notas. O gold pega o orgao da nota quando o item nao tem.
- **Notas sem item**: 4.296 em 2025-04 (e um punhado nos outros meses); 0 itens orfaos.
- `quantidade x valor_unitario = valor_total` fecha em 100% dos itens, e nao ha chave fora de 44
  digitos, duplicata ou CFOP invalido nestes seis meses: as regras existem porque o pipeline precisa
  sobreviver ao mes em que isso mudar, nao porque ja aconteceu.

## Baseline de ML: descricao -> NCM

### Protocolo

- **Split temporal**: treino 2025-04 a 2025-07, validacao 2025-08 (so para calibrar temperaturas e
  escolher o limiar da auditoria), teste 2025-09. Nada do mes de teste toca o ajuste.
- **Dedup**: o treino colapsa para **uma linha por descricao normalizada** (526.441 descricoes, de
  2,06 milhoes de itens), rotulo = NCM mais frequente daquela descricao, peso `log(1 + ocorrencias)`.
  3,6% das descricoes aparecem com mais de um NCM, mas elas concentram **26% dos itens**: esse e o teto
  de ruido de rotulo do problema.
- **Quatro subconjuntos de teste**, todos reportados: `todos` (547.718 itens, como em producao),
  `unicos` (206.928 descricoes distintas), `nao_vistos` (itens cuja descricao nunca apareceu no treino)
  e `nao_vistos_unicos` (126.723 descricoes; o numero honesto de generalizacao).
- **Modelos**: classe majoritaria; lookup exato (memorizacao); **TF-IDF palavra (1-2) + caractere
  (3-5), 400 mil dimensoes, LinearSVC do capitulo (96 classes) e um LinearSVC por capitulo para o NCM**
  (um modelo plano com ~6,6 mil classes x 400 mil features precisaria de ~20 GB de coeficientes; a
  hierarquia reduz para a soma de `classes_do_capitulo x features_presentes_no_capitulo`); e o hibrido
  lookup -> SVM. Probabilidades por **temperature scaling** ajustado no mes de validacao,
  `P(ncm) = P(capitulo) x P(ncm | capitulo)`.

<!-- ML_RESULTS_START -->
### Resultados do baseline

Mes de teste 2025-09 (547.718 itens). Tabela completa (quatro subconjuntos, F1 ponderado), calibracao,
desempenho por capitulo, confusoes e exemplos de erro em [reports/ml_results.md](reports/ml_results.md).

| Tarefa | Modelo | Todos os itens: top-1 / top-5 | Nunca vistas, unicas: top-1 / top-5 | F1 macro (nunca vistas) |
|---|---|---:|---:|---:|
| Capitulo (2 digitos) | classe majoritaria | 7,6% / 30,7% | 5,4% / 27,8% | 0,1% |
| Capitulo | lookup exato | 65,3% / 73,8% | 5,4% / 27,8% | 0,1% |
| Capitulo | TF-IDF + LinearSVC | **89,0% / 96,0%** | **79,7% / 92,4%** | 60,3% |
| Capitulo | hibrido lookup -> SVM | 89,5% / 93,9% | 79,3% / 87,8% | 59,2% |
| NCM (8 digitos) | classe majoritaria | 5,8% / 18,1% | 4,2% / 13,5% | 0,0% |
| NCM | lookup exato | 60,0% / 64,1% | 4,2% / 13,5% | 0,0% |
| NCM | TF-IDF + LinearSVC hierarquico | 77,3% / 87,7% | **60,0% / 76,1%** | 26,5% |
| NCM | hibrido lookup -> SVM | **78,7% / 87,8%** | 60,0% / 76,1% | 26,5% |

O que os numeros dizem:

- **Memorizar nao generaliza.** O lookup exato chega a 60% no NCM porque 68% dos itens do mes repetem uma
  descricao do treino; nas 126.723 descricoes nunca vistas ele cai para o nivel da classe majoritaria.
  Por isso o numero de referencia e a coluna "nunca vistas, unicas".
- **Teto de ruido.** Nos itens cuja descricao ja estava no treino, o NCM declarado coincide com o do treino
  em so 86,5%: parte do "erro" de qualquer modelo e erro do rotulo (a auditoria abaixo confirma isso).
- **Cauda longa.** 6.583 NCMs no treino, muitos com poucos exemplos: F1 macro de 26,5% contra F1 ponderado
  de 57,7% nas descricoes nunca vistas. E o ponto que a FASE 2 (encoder PT-BR) precisa melhorar.
- **Custo.** Treino em CPU de 1 nucleo: 28 min (capitulo) + 15 min (NCM), pico de ~2,9 GB de RAM,
  retomavel por checkpoint. Inferencia: 0,23 ms/item em lote (mes de teste inteiro em 92 s) e 150 ms
  (p50) por item isolado. Modelo de 215 MB, podado para esparso com concordancia top-1 de 99,6% com o
  modelo denso.
<!-- ML_RESULTS_END -->

### Auditoria de NCM

<!-- AUDIT_START -->
Um alerta e um item cujo NCM declarado diverge da predicao com confianca acima do limiar. O limiar foi
escolhido no mes de validacao. A meta era 95% de precisao, mas ela nao e alcancavel: a "precisao" ali e
concordancia com o NCM declarado, que tem ruido. Por isso vale o limiar de maior precisao medida:
**0,99** (92,0% em 45.234 itens).

- **Mes de teste:** 3.580 alertas (0,65% dos itens), em 723 descricoes distintas, somando R$ 2,63 mi;
  1.305 deles trocam ate o capitulo. Detalhes em [reports/ncm_audit.md](reports/ncm_audit.md).
- **Inspecao manual de 60 alertas aleatorios**
  ([reports/ncm_audit_inspection.md](reports/ncm_audit_inspection.md)): **50 (83%, IC 95% de 72% a 91%)**
  sao NCM declarado errado com a sugestao do modelo correta (ex.: cenoura declarada como "cavalos",
  farinha de trigo como "desperdicio de algodao", tomate como "outros horticolas"); 5 sao livros em codigo
  vizinho, sem impacto tributario; 1 e ambiguo; 1 tem declarado e previsto errados; **3 (5%)** sao erro do
  modelo.
- **Ressalva:** 45% dos alertas sao horticolas e frutas in natura, que em geral tem tributacao federal
  zero dos dois lados do erro. O valor somado mede volume, nao imposto recuperavel. O uso honesto e
  priorizar a revisao humana do cadastro de produto do fornecedor, nao corrigir NCM automaticamente.
<!-- AUDIT_END -->

## Como rodar

Requisitos: Python 3.11+, ~2 GB de RAM livres para o pipeline (DuckDB limitado a 1,5 GB) e ~4 GB para
treinar o baseline; ~3 GB de disco para seis meses (zips + Parquet + DuckDB) e ~1 GB para os modelos.

```bash
make install                         # cria .venv e instala o pacote (editavel) + dev
make pipeline MESES=202504-202509    # download -> bronze -> silver -> quality -> gold -> relatorio
make ml                              # ml-dataset (split temporal) -> ml-train -> ml-audit
make publish                         # dataset anonimizado + manifesto em data/publish/ (nao publica)
make test && make lint               # pytest offline (fixtures pequenas) e ruff

# inferencia
.venv/bin/python -m raio_x_fiscal.ml.predict "ARROZ TIPO 1" "Vidro temperado 6mm" --k 3
```

Variaveis de ambiente opcionais: `RXF_DATA_DIR`, `RXF_MODELS_DIR`, `RXF_DUCKDB_MEMORY` (padrao
`1500MB`), `RXF_DUCKDB_THREADS` (padrao `2`), `RXF_HASH_SALT` (sal do hash de CPF).

**Airflow** (fora da VPS de producao): `cd airflow && echo "AIRFLOW_UID=$(id -u)" > .env &&
docker compose up airflow-init && docker compose up`, depois `http://localhost:8080`. A DAG
`raio_x_fiscal_pipeline` roda `download -> bronze -> silver -> quality` mapeados por mes (param
`meses`) e em seguida `gold -> quality_gold -> report`; cada task chama a mesma funcao de
`pipeline/tasks.py` que a CLI usa. O parse da DAG foi validado com `DagBag` no Airflow 2.10.5
(`tests/test_cli_dag.py`, pulado automaticamente quando o Airflow nao esta instalado).

## Estrutura

```
raio-x-fiscal/
├── src/raio_x_fiscal/
│   ├── config.py             # Paths, meses, conexao DuckDB com limite de memoria
│   ├── cli.py                # rxf: download | bronze | silver | quality | pipeline | gold | ml-* | publish
│   ├── pipeline/
│   │   ├── schema.py         # contrato de colunas dos 3 CSVs (bronze falha se mudar)
│   │   ├── normalize.py      # regras puras em Python e em SQL (NCM, CFOP, decimal BR, descricao)
│   │   ├── download.py       # zip mensal idempotente + manifesto sha256
│   │   ├── bronze.py / silver.py / gold.py
│   │   ├── quality.py        # expectations por camada, JSON + relatorio markdown
│   │   └── tasks.py          # funcoes compartilhadas por CLI e DAG
│   ├── ml/
│   │   ├── dataset.py        # split temporal + dedup + flags de vazamento
│   │   ├── features.py       # TF-IDF palavra + caractere (float32)
│   │   ├── models.py         # majoritario, lookup, SVM hierarquico calibrado
│   │   ├── evaluate.py       # metricas, confusao, latencia, calibracao
│   │   ├── train.py          # treino, avaliacao, reports/ml_results.md
│   │   ├── audit.py          # alertas de NCM + amostra para inspecao
│   │   └── predict.py        # inferencia por CLI / classe NcmPredictor
│   ├── publish/dataset.py    # dataset anonimizado para Kaggle/HF
│   └── seeds/                # capitulos NCM (97) e UFs
├── dags/raio_x_fiscal_dag.py # Airflow (TaskFlow, mapeamento dinamico por mes)
├── airflow/docker-compose.yml
├── tests/                    # pytest offline, fixture latin-1 com casos de borda
├── reports/                  # quality_report.md, ml_results.md, ncm_audit*.md (numeros reais)
├── docs/DATASET_CARD.md
├── data/ (gitignored)        # raw/ bronze/ silver/ gold/ quality/ ml/ publish/
└── models/ (gitignored)      # featurizer, SVM hierarquico, lookup, metadata.json
```

## Decisoes e limitacoes

- **DuckDB em vez de Spark/Databricks**: 3 milhoes de linhas por semestre cabem em uma maquina de 8 GB;
  o padrao medalhao e o mesmo, o custo e zero. A estrutura (particao por mes, contrato de schema,
  rejects, expectations) e a que migraria para Delta/Databricks sem mudar de forma.
- **Parquet por particao + DuckDB no gold**: o gold e um unico arquivo porque a FASE 3 precisa de um
  banco consultavel por SQL somente leitura; o export Parquet existe para quem nao usa DuckDB.
- **Rotulo = NCM declarado pelo fornecedor**, que e ruidoso (26% dos itens tem descricao ambigua).
  Toda acuracia aqui e "concordancia com o declarado", e parte do erro do modelo e acerto contra um
  rotulo errado. A auditoria explora exatamente isso.
- **Modelo linear, nao transformer**, de proposito: e o baseline que a FASE 2 precisa superar, roda em
  CPU em milissegundos e e explicavel por pesos de n-gramas.
- **Confianca calibrada por temperatura** e barata e melhora muito sobre o score bruto do SVM, mas
  continua sendo uma aproximacao; o limiar da auditoria foi escolhido empiricamente no mes de validacao.
- **Capitulos raros** (poucas descricoes) tem F1 baixo e o F1 macro reflete isso; o F1 ponderado e o
  numero operacional.
- **Eventos** (cancelamento, carta de correcao) vieram vazios nos seis meses; a camada esta pronta mas
  nao foi exercitada por dados reais.
- **Nenhum CPF** apareceu como emitente nestes meses; a mascara esta testada em fixture, nao em producao.

## Roadmap

**FASE 2: modelo publicado.** Fine-tuning de um encoder PT-BR (BERTimbau base ou similar) no Kaggle
(GPU gratuita) sobre o dataset anonimizado desta fase, com o mesmo protocolo de split e os mesmos
quatro subconjuntos, para comparar diretamente com o baseline. Entregas: dataset + notebook no Kaggle,
modelo + dataset no Hugging Face, Space com a demo de inferencia e a auditoria de NCM.

**FASE 3: agente analitico.** Perguntas em portugues sobre a camada gold ("quanto o Ministerio da
Saude gastou com NCM 3004 em agosto, por UF?") respondidas por text-to-SQL **somente leitura** (DuckDB
read-only, lista de tabelas permitidas, limite de linhas e tempo), com **trava numerica**: todo numero
no texto da resposta tem que existir no resultado da query, senao a resposta e bloqueada e refeita.
Evals com perguntas de resposta conhecida e ataques de injecao, custo por papel, juiz pinado, guarda de
orcamento e relatorio HTML, reaproveitando o harness do projeto `whatsapp-agent-evals` (12 personas, juiz
pinado, custo por papel, publicacao prevista junto com este). Demo com login.

## Testes e lint

`make test` roda 50+ testes offline em segundos: parse do CSV latin-1 e dos decimais BR, contrato de
schema (drift falha), regras de normalizacao em Python e SQL (paridade), rejects e dedup, idempotencia
de bronze/silver/gold, expectations com as divergencias conhecidas da fixture, mascara de CPF, split
sem vazamento, modelo hierarquico (shapes, probabilidades, calibracao), inferencia apos
`joblib` roundtrip, parser da CLI e estrutura da DAG. `make lint` roda `ruff check` e `ruff format
--check`.

## Licenca

Codigo sob MIT (ver `LICENSE`). Dados: Portal da Transparencia / CGU, dados abertos (ver secao
"Fonte dos dados, licenca e LGPD").
