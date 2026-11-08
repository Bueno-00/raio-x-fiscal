# Raio-X Fiscal

[Português](README.md) · **English**

An AI platform for the accounting and tax domain, built on **public Brazilian electronic invoices**
(NF-e, *Nota Fiscal eletrônica*: the mandatory digital invoice every Brazilian sale is issued on), taken
from federal government purchases published by the Transparency Portal. It has a medallion pipeline in
DuckDB with measured data quality, a machine learning baseline that **classifies a free-text product
description into its NCM code**, and an audit that flags declared NCM codes that are probably wrong.

**NCM** (*Nomenclatura Comum do Mercosul*) is the 8-digit product code used across Mercosur, the regional
extension of the international Harmonized System (HS). Every line item on a Brazilian invoice carries
one, and it drives the tax rates applied to that item.

> The detailed reports in [`reports/`](reports/) and the original dataset card are written in
> Portuguese. An English version of the dataset card is at [docs/DATASET_CARD.en.md](docs/DATASET_CARD.en.md).

<!-- RESULTS_BOX_START -->
> **Results (PHASE 1, measured on 2026-11-04).** 6 months (2025-04 to 2025-09), **878,858 invoices** and
> **3,124,925 line items** (R$ 46.5 bn in items), 7,381 distinct NCMs, 0 rejected rows and 0 duplicates,
> 98.8% to 99.2% of items with a valid NCM. Inconsistencies found and documented: the sum of the items
> differs from the invoice total in 14% to 23% of invoices per month; the buying agency is missing in 83%
> of the rows of the items file (but present in 98.5% of the invoices); 4,344 invoices with no items.
> Description -> NCM baseline (hierarchical TF-IDF + LinearSVC, CPU only): **78.7%** accuracy on the
> 8-digit NCM in the test month and **60.0% / 76.1%** (top-1 / top-5) on never-seen descriptions. NCM
> audit: 3,580 alerts in the test month; in a manual inspection of 60, **50 (83%)** were a wrong declared
> NCM with the model's suggestion correct, and 3 (5%) were model errors.
>
> **Product (2026-11-07 and 08).** Checks NF-e XML, the product register spreadsheet or a typed description and
> returns a traffic light per line item with the reason and the suggested NCM and CFOP, in a **web app**
> (`rxf app`) or from the command line. On a real sample of 50,000 items from a month the model never saw:
> **0.6% red, 6.0% yellow, 93.4% green**. On example invoices from 8 businesses (real product descriptions
> from the public data, planted errors with an answer key): **184 of 186 errors flagged**. Fixes come out
> in Bling's and Olist's import format (ready file) and as a list for Omie, Conta Azul and Domínio. The
> official NCM table is checked by a daily job with version history.
<!-- RESULTS_BOX_END -->

---

## The problem

Every Brazilian invoice classifies each line item with an **NCM** code (8 digits, an extension of the
Harmonized System). The NCM decides federal excise tax (IPI), PIS/COFINS, ICMS-ST (state tax collected
in advance) and eligibility for tax incentives. In practice the code is chosen by the supplier, from a
free-text description ("ARROZ TIPO 1", "CABO FLEXIVEL 2,5MM2 750V"), and the accounting firm inherits
the mistake: it either overpays tax, or underpays and gets fined later.

Two facts make this a data problem and an AI problem at the same time:

1. The same text gets different NCMs from different suppliers. In this data, among test items whose
   exact description already existed in training, the NCM matches in only **86.5%** of cases.
2. The volume is large and repetitive: 3.1 million items in six months, but only ~900 thousand
   distinct descriptions. Any evaluation that ignores the repetition measures memory, not generalization.

It is the same problem as **catalogue categorization** in a marketplace: short, noisy text typed by
third parties, thousands of hierarchical classes, and a real cost when the class comes out wrong.

## What this repository proves (PHASE 1)

1. **Reproducible, cheap data engineering** (`src/raio_x_fiscal/pipeline/`): monthly zip from the CGU
   (the federal comptroller; latin-1 CSV, `;` separator, comma as decimal mark) -> bronze -> silver ->
   gold in DuckDB, local, idempotent per month, with a schema contract that fails loudly when the source
   changes.
2. **Data quality as code** (`pipeline/quality.py`): explicit expectations per layer, numbers stored as
   JSON and a markdown report with what was measured, including what does not reconcile
   ([reports/quality_report.md](reports/quality_report.md)).
3. **An honest ML baseline** (`src/raio_x_fiscal/ml/`): temporal split, dedup by normalized
   description, the "as in production" number reported next to the "never-seen descriptions" number,
   calibration on a separate validation month, measured latency
   ([reports/ml_results.md](reports/ml_results.md)).
4. **A business application**: an NCM audit with a threshold chosen for a target precision and a sample
   inspected by hand, stating how many alerts look like real errors and how many are model errors
   ([reports/ncm_audit.md](reports/ncm_audit.md), [reports/ncm_audit_inspection.md](reports/ncm_audit_inspection.md)).
5. **Orchestration both ways**: `make pipeline` from the CLI on the server and the same sequence as an
   Airflow DAG with dynamic task mapping per month (`dags/`, `airflow/docker-compose.yml`), parse
   validated with Airflow 2.10.5.
6. **An anonymized dataset ready to publish** in PHASE 2 (Kaggle / Hugging Face), with a dataset card
   ([docs/DATASET_CARD.en.md](docs/DATASET_CARD.en.md)).

## The product: checking invoices before they are imported (new, 2026-11-07)

On top of the pipeline and the model, the repository now has a **product that runs on the user's own
machine**: it takes the invoices, the product register or a typed description, and returns a
**traffic light per line item** (green ok, yellow check, red probable error) with **the reason in
plain Portuguese, what to do, and the suggested NCM and CFOP**. The output is an HTML report (to read)
and an XLSX spreadsheet (to work on). No invoice leaves the machine: no external API, no cloud. Code in
`src/raio_x_fiscal/produto/`.

**Three entry points, one engine:**

| Entry point | Input | Command | What for |
|---|---|---|---|
| 1. Invoices (main) | NF-e/NFC-e XML: loose files, a folder (one subfolder per company) or a `.zip` | `rxf auditar <folder>` | check the month's invoices before importing them into the accounting system |
| 2. Product register | product spreadsheet exported from the ERP (CSV or XLSX; recognizes the Bling export) | `rxf cadastro <sheet>` | check the NCM **before** issuing invoices |
| 3. Search | a typed description ("leite condensado 395 g") | `rxf pesquisar "<text>"` | the 3 most likely NCMs, with the official description and the confidence |

**Web app (2026-11-08).** `rxf app` serves the three entry points on a page ready to publish (FastAPI,
bound to `127.0.0.1:8770`; Nginx publishes it): upload XML, a folder or a `.zip`, "use example invoices",
the product register and the search box, with a traffic light per item, filters by color, company and
check, and downloads of the XLSX report and of the fix in the chosen ERP's format. Built for visitors who
upload real invoices:
- uploads are read **in memory** (the app reads the request body itself, skipping the server's temporary
  file), checked and discarded; no access log; the result stays in memory for 30 minutes only so the
  spreadsheet can be downloaded;
- limits: 25 MB and 3,000 XML files per upload, 30,000 items, 12 uploads per IP per hour and 40 per day,
  one check at a time; security headers (same-origin CSP, no framing, no referrer);
- the "Pergunte ao Simples" chat (a separate project) only shows up if the `pergunte_ao_simples` package
  is installed and `CHAT_ENV_FILE` points to an existing file; it receives the check summary without
  names or tax IDs.

`pip install -e ".[app]"` installs FastAPI and Uvicorn. `rxf painel` (the older local page, port 8765)
is still there for machine-only use.

**Example invoices from 8 businesses (2026-11-08).** `rxf exemplos-lojas` writes
`exemplos/lojas/notas-exemplo-raio-x.zip`: a grocery store, auto parts, pharmacy, building supplies,
clothing store, restaurant, stationery and IT store, in 8 states, 132 invoices (NF-e and NFC-e, layout
4.00, test environment) and 667 items. The companies are made up; **the products are real descriptions
from the public data**, with the NCM used 85% of the time or more (`scripts/extrair_catalogo_exemplos.py`
-> `src/raio_x_fiscal/seeds/catalogo_exemplos.csv`). Errors were planted the way they happen in an
accounting office (mostly in the product register, so they repeat on every invoice): NCM copied from
another product, an outdated code, the leading zero eaten by Excel, a wrong GTIN, a regular-regime CST in
a Simples company, in-state CFOP on an interstate sale and the reverse, a different NCM typed on one
invoice only, a purchase CFOP on a sale, a cancelled invoice. The zip ships the **answer key** item by
item, the office rules and each company's product register (the grocery store's in Bling's format).
Result in [reports/exemplos_lojas.md](reports/exemplos_lojas.md) (Portuguese): **184 of 186 errors
flagged**; the one that slipped through was a tea with the NCM of "food preparations", the model's
second choice.

**Checks per line item** (each one is a simple rule; the model covers what a rule cannot):

| Check | Level | How it decides |
|---|---|---|
| NCM does not match the description | red / yellow | phase 1 model: red at confidence ≥ 0.99 with a different NCM (the audit threshold; 50 of 60 hand-inspected alerts were real errors); yellow at ≥ 0.90 with the declared NCM outside the top 5; also yellow when the declared NCM is not even in the top 10 and belongs to another chapter (≥ 0.60) or another 4-digit heading (≥ 0.75), the typical NCM copied from another product (rule added 2026-11-08, measured on the public sample: +1.6% items flagged, 43% of them with an NCM almost nobody uses for that description, under 5% with the usual NCM). Suggestions only use codes that exist in the current official table |
| NCM does not exist or is out of force | red / yellow | official Siscomex table **on the invoice date** (red); for invoices older than the first stored table, compares with today's (yellow). Lists today's codes in the same group and suggests the one the model prefers among them |
| NCM empty or shorter than 8 digits | red | format (a service item with ISSQN and NCM 00 is accepted); with 7 digits, if the code with a leading zero exists, says Excel ate the zero and suggests the right code |
| CFOP vs states | yellow | an in-state CFOP (5.xxx) on an interstate invoice, 6.xxx within one state, 7.xxx without a foreign buyer; suggests the mirror CFOP. **An in-person sale with 5.xxx turns green on its own.** Never red: it may be on purpose |
| Inbound CFOP on an outbound invoice (or the reverse) | red | first digit vs `tpNF` |
| CST vs tax regime | red | a Simples Nacional company (CRT 1 or 4) using a regular-regime CST, or the reverse with CSOSN |
| Same product with different NCMs | yellow | same issuer product code or same GTIN with different NCMs across the folder |
| Invoice vs register | yellow | with `--cadastro`, the invoice NCM differs from the register NCM (by GTIN or code) |
| Invalid GTIN | yellow | length and GS1 check digit |
| Cancelled invoice | yellow | a cancellation event (110111) in the same folder: "do not import" |

**Office rules.** Sometimes the accounting office uses a CFOP on purpose. A plain CSV
(`cnpj_empresa;regra;cfop;ncm;codigo_produto;motivo`, empty = any) lists what is accepted per company;
the alert stays in the report but turns green with the reason, so reviewers are not worn down. A
`regras-do-escritorio.csv` inside the invoice folder is picked up automatically.

**An always up-to-date NCM table.** `rxf ncm-atualizar` downloads the official table from
[Portal Único Siscomex](https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO),
hashes its content (ignoring the daily "Vigente em" stamp) and compares it with the last stored
version: if it changed, the new version is stored with its date in `data/ncm/versoes/`; if not, a
"sem mudança" (no change) line is written to `data/ncm/registro.csv` as proof that it ran. The
official file only carries what is in force today, so the history is kept here, and the "NCM on the
invoice date" check uses the right version. A copy from 2026-11-07 ships with the package so it works
right after `git clone`. Scheduling is left to whoever runs the server; the suggested line (every day
at 6 am) is:

```
0 6 * * * cd /path/raio-x-fiscal && .venv/bin/rxf ncm-atualizar >> data/ncm/cron.log 2>&1
```

**Measured** (2026-11-07 and 08):

- **Example invoices from the 8 businesses** (above): 132 invoices, 667 items, 186 planted errors, **184 flagged**.
- **Minimal example invoices** (`exemplos/`, 3 fictitious companies, used by the tests): 15 invoices,
  41 items; every planted error is caught by the right rule (`tests/test_produto.py`).
- **Real sample of the public data**, 50,000 items (13,361 invoices) from 2025-09, a month the model
  never saw: **0.6% red, 6.0% yellow, 93.4% green** (4.5% yellow before the 2026-11-08 rule); 1,629 items
  per second on an idle 2-core CPU. Out of every 1,000 items a person looks closely at 6 and double-checks
  60. Details in [reports/produto_amostra_publica.md](reports/produto_amostra_publica.md) (Portuguese).
- 97 tests passing (26 for the product, 12 for the app, import formats and example invoices), `ruff` clean.

**Does someone have to review everything?** No. The model and the rules do the triage; a person looks
at the red items (0.6% in the sample) and decides; yellow items that are intentional become office
rules. The model's accuracy is measured automatically every month: train on the previous months and
measure on a month it has not seen (`rxf avaliar-publico --mes AAAAMM`), with nobody checking item by
item.

**Sending the fix back to the ERP** (official help pages accessed 2026-11-08). The person approves the
changes (in the app by ticking suggestions; on the command line in the "approved NCM" column) and Raio-X
hands back a file the way each system accepts it. Code in `src/raio_x_fiscal/produto/formatos.py`.

| ERP | Updates NCM by spreadsheet? | What Raio-X returns |
|---|---|---|
| **Bling** | yes: "Importar e Atualizar produtos", "Atualizar" operation; key **ID**; an emptied cell erases the field; up to 1,000 per file; the template is CSV | **ready file**: the same CSV you exported, approved rows only, NCM changed only, in parts of 1,000 ([help](https://ajuda.bling.com.br/hc/pt-br/articles/360060827554), [template](https://ajuda.bling.com.br/hc/pt-br/articles/360062630653)) |
| **Olist ERP** (formerly Tiny) | yes: "Importar produtos de uma planilha" with the official template, column names and order unchanged; key **ID** (or SKU); recommends up to 500 per file | **ready file** in your export's layout, in parts of 500 ([help](https://ajuda.olist.com/produtos/importar-planilha-de-produtos)) |
| **Omie** | yes, but only with the password-protected official template; **an empty cell erases the field**; the update key is not published (likely "Código do Produto") | a mapping list (code and new NCM) to paste into the template, with the warning ([help](https://ajuda.omie.com.br/pt-BR/articles/6590176-cadastrando-produtos-em-lote-via-planilha)) |
| **Conta Azul** | **no**: the import only creates new products; NCM is edited product by product | a list to fix one by one ([help](https://ajuda.contaazul.com/hc/pt-br/articles/49003711419149-A%C3%A7%C3%B5es-em-lote-o-que-%C3%A9-poss%C3%ADvel-fazer-em-lote-na-Conta-Azul-Pro)) |
| **Domínio** (Thomson Reuters) | **no public layout** for importing products (its knowledge base is customers-only); inside the system there is a bulk "Alterar Produtos" utility (solution 172) | a list for that utility or to ask support for the layout. Domínio also **creates a new NCM validity period on its own** when the XML differs from the register ([release notes](https://www.dominiosistemas.com.br/atualizacoes)), so the right place to fix it is **before importing** (entry point 1) |

The list (XLSX) has a "Como usar" tab with the chosen ERP's steps and sources. From invoices (entry point
1) the ERP's product ID is not in the XML, so that path always returns the list; Bling's and Olist's ready
file comes from entry point 2, starting from the spreadsheet exported by the ERP itself.

**Real invoices stay local.** `entrada-local/` and `saida-local/` are in `.gitignore`. `make auditar`
checks whatever is in `entrada-local/` and writes `saida-local/<date-time>/relatorio.html` and
`relatorio.xlsx`. Client invoices never go to git, Kaggle or any external API.

## Architecture

```mermaid
flowchart LR
  CGU["Transparency Portal (CGU)<br/>monthly zip: 3 latin-1 CSVs, ';'"]
  subgraph med["Medallion pipeline (DuckDB + Python, local and free)"]
    B["bronze<br/>raw parquet, schema contract,<br/>ingestion metadata"]
    S["silver<br/>Brazilian types, 8-digit NCM, CFOP,<br/>normalized description, rejects, dedup"]
    G["gold<br/>fato_item, fato_nota, dim_ncm, dim_orgao,<br/>aggregates, ml_ncm_items (anonymized)"]
    Q["quality<br/>expectations per layer,<br/>JSON + report"]
    B --> S --> G
    Q -.-> B
    Q -.-> S
    Q -.-> G
  end
  CGU -->|"rxf download"| B
  G --> ML["PHASE 1: baseline<br/>hierarchical TF-IDF + LinearSVC<br/>description -> chapter -> NCM"]
  ML --> AUD["NCM audit<br/>alerts with calibrated confidence"]
  G --> DS["Anonymized dataset<br/>+ dataset card"]
  DS -.-> F2["PHASE 2: fine-tuning a PT-BR encoder<br/>on Kaggle; model, dataset and Space on HF"]
  G -.-> F3["PHASE 3: analytical agent in Portuguese<br/>read-only text-to-SQL, numeric guard,<br/>evals + injection attacks"]
  subgraph orq["Orchestration"]
    CLI["make pipeline (server)"]
    AF["Airflow DAG<br/>(docker-compose, off the server)"]
  end
  orq -.-> med
```

The three layers live in `data/` (outside git): `bronze/<entity>/mes=AAAAMM/`,
`silver/<entity>/mes=AAAAMM/` (Parquet partitioned by month) and `gold/raio_x_fiscal.duckdb` (plus a
Parquet export of each table). Reprocessing a month replaces its partition; gold is rebuilt from
scratch (`CREATE OR REPLACE`). Running twice gives the same result.

## Data source, license and LGPD

- **Source:** Transparency Portal (*Portal da Transparência*, run by the CGU, *Controladoria-Geral da
  União*), dataset "Notas Fiscais", monthly download at
  `https://portaldatransparencia.gov.br/download-de-dados/notas-fiscais/AAAAMM` (redirects to the CGU
  open data bucket). Three files per month: `NotaFiscal` (invoice header), `NotaFiscalItem` (line items)
  and `NotaFiscalEvento` (events; empty in the processed months).
- **Data license:** federal government open data. The dados.gov.br catalogue lists the CGU datasets
  under the **ODbL (Open Database License)**; before publishing the derived dataset in PHASE 2 this will
  be confirmed on the dataset page and cited in the card. The code in this repository is MIT.
- **LGPD** (*Lei Geral de Proteção de Dados*, Brazil's data protection law, similar to GDPR): the issuer
  of an NF-e can be an individual (identified by a CPF, the personal taxpayer number). Rules applied:
  - in **gold**, the CPF becomes a salted hash (`cpf:<16 hex>`) and the individual's name is dropped;
    company CNPJs (corporate taxpayer numbers) stay, since a public purchase from a company is public
    information. The check `fato_nota_cpf_mascarado` enforces this on every build. In the six processed
    months no invoice was issued by a CPF, so the rule is covered by the tests, not by the data;
  - the ML table (`ml_ncm_items`) and the publishable dataset **do not carry** the access key, CPF/CNPJ,
    company name, state registration, or the buyer's CNPJ/name. What remains is description, NCM, CFOP,
    unit, quantity, values, state (UF) and month. `item_id` is an md5 of the key + item number. The check
    `ml_sem_identificadores` fails the build if any of those columns shows up.

## Medallion pipeline

| Layer | What it does | Key / idempotency |
|---|---|---|
| **bronze** (`bronze.py`) | extracts the zip, validates the header against the contract (`schema.py`), reads the CSV with DuckDB (`encoding='latin-1'`, everything VARCHAR), writes ZSTD Parquet + `_mes_referencia`, `_source_file`, `_ingested_at`, a JSON manifest; deletes the extracted CSV | one partition per month and entity; reprocessing replaces it |
| **silver** (`silver.py`) | renames to snake_case, casts types (`DECIMAL` from `1.234,56`, `DATE` from `dd/mm/aaaa`, integer codes), normalizes the NCM to 8 digits (the CSV drops the leading zero of chapters 01 to 09 and uses `-1` for missing), validates the CFOP (fiscal operation code), normalizes the description (lowercase, no accents, only `[a-z0-9]`), splits **rejects** with a reason (key without 44 digits, invalid date or value), deduplicates on the natural key | invoice: `chave_acesso`; item: `(chave_acesso, numero_produto)` |
| **gold** (`gold.py`) | `fato_item`, `fato_nota`, `dim_ncm` (chapter/heading/subheading + most frequent official description), `dim_capitulo` (97 chapters and sections, seed), `dim_cfop`, `dim_orgao`, `dim_destinatario`, `dim_uf`; aggregates `agg_gasto_ncm_mes`, `agg_gasto_orgao_mes`, `agg_gasto_capitulo_uf_mes`; anonymized `ml_ncm_items` | full refresh into one DuckDB file + Parquet export |

The normalization rules exist in **SQL (silver) and in Python (inference)**, and a test makes sure both
versions agree (`tests/test_normalize.py::test_sql_and_python_rules_agree`).

### Data quality: what was measured

Summary per month (silver). Full report, with every check and its details, in
[reports/quality_report.md](reports/quality_report.md) (in Portuguese).

| Month | Invoices | Items | Rejected | Duplicates | Valid NCM | qty x unit = total | Sum of items = invoice |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-04 | 128,641 | 470,126 | 0 | 0 | 99.11% | 100% | 77.37% |
| 2025-05 | 143,760 | 523,639 | 0 | 0 | 99.13% | 100% | 84.46% |
| 2025-06 | 147,791 | 517,843 | 0 | 0 | 99.12% | 100% | 85.17% |
| 2025-07 | 173,981 | 569,088 | 0 | 0 | 99.22% | 100% | 85.92% |
| 2025-08 | 135,999 | 489,660 | 0 | 0 | 98.83% | 100% | 83.30% |
| 2025-09 | 148,686 | 554,569 | 0 | 0 | 98.78% | 100% | 83.90% |

Inconsistencies found (logged as `warn`/`info`, not hidden):

- **Sum of items vs. invoice total** matches in 77% to 86% of invoices. Where it does not, in half the
  cases the items add up to more (an unconditional discount applied to the invoice total) and in the
  other half to less (freight, IPI, ICMS-ST and other ancillary charges are included in the total).
  Across the six months the items add up to **R$ 46.5 bn** and the invoices to **R$ 39.3 bn**; the gap
  (R$ 7.7 bn of items above the invoice) is concentrated in chapter 30 (pharmaceutical products,
  Ministry of Health purchases with large discounts over list price). That is why item value and invoice
  value are separate facts in gold.
- **Invalid NCM** in 0.8% to 1.2% of items: almost all of it is the `-1` sentinel ("no NCM", typical of
  services described as an item); a small residue has a chapter that does not exist. 85 thousand items
  per month came with 7 digits because the leading zero was lost: fixed, not discarded.
- **Buying agency** shows as "Sem informação" (no information) in **83% of the rows of the items file**,
  but it is filled in 98.5% of the invoices. Gold takes the agency from the invoice when the item has none.
- **Invoices with no items**: 4,296 in 2025-04 (and a handful in the other months); 0 orphan items.
- `quantidade x valor_unitario = valor_total` closes on 100% of items, and there is no key outside 44
  digits, no duplicate and no invalid CFOP in these six months: the rules exist because the pipeline has
  to survive the month this changes, not because it already happened.

## ML baseline: description -> NCM

### Protocol

- **Temporal split**: train 2025-04 to 2025-07, validation 2025-08 (only to calibrate temperatures and
  pick the audit threshold), test 2025-09. Nothing from the test month touches fitting.
- **Dedup**: training collapses to **one row per normalized description** (526,441 descriptions, from
  2.06 million items), label = most frequent NCM for that description, weight `log(1 + ocorrencias)`.
  3.6% of descriptions appear with more than one NCM, but they account for **26% of items**: that is the
  label-noise ceiling of the problem.
- **Four test subsets**, all reported: `todos` (all 547,718 items, as in production), `unicos` (206,928
  distinct descriptions), `nao_vistos` (items whose description never appeared in training) and
  `nao_vistos_unicos` (126,723 descriptions; the honest generalization number).
- **Models**: majority class; exact lookup (memorization); **word (1-2) + character (3-5) TF-IDF, 400
  thousand dimensions, a chapter-level LinearSVC (96 classes) and one LinearSVC per chapter for the NCM**
  (a flat model with ~6.6 thousand classes x 400 thousand features would need ~20 GB of coefficients; the
  hierarchy brings it down to the sum of `classes_do_capitulo x features_presentes_no_capitulo`); and a
  hybrid lookup -> SVM. Probabilities via **temperature scaling** fitted on the validation month,
  `P(ncm) = P(capitulo) x P(ncm | capitulo)`.

<!-- ML_RESULTS_START -->
### Baseline results

Test month 2025-09 (547,718 items). Full table (four subsets, weighted F1), calibration, per-chapter
performance, confusions and error examples in [reports/ml_results.md](reports/ml_results.md) (in
Portuguese).

| Task | Model | All items: top-1 / top-5 | Never seen, unique: top-1 / top-5 | Macro F1 (never seen) |
|---|---|---:|---:|---:|
| Chapter (2 digits) | majority class | 7.6% / 30.7% | 5.4% / 27.8% | 0.1% |
| Chapter | exact lookup | 65.3% / 73.8% | 5.4% / 27.8% | 0.1% |
| Chapter | TF-IDF + LinearSVC | **89.0% / 96.0%** | **79.7% / 92.4%** | 60.3% |
| Chapter | hybrid lookup -> SVM | 89.5% / 93.9% | 79.3% / 87.8% | 59.2% |
| NCM (8 digits) | majority class | 5.8% / 18.1% | 4.2% / 13.5% | 0.0% |
| NCM | exact lookup | 60.0% / 64.1% | 4.2% / 13.5% | 0.0% |
| NCM | hierarchical TF-IDF + LinearSVC | 77.3% / 87.7% | **60.0% / 76.1%** | 26.5% |
| NCM | hybrid lookup -> SVM | **78.7% / 87.8%** | 60.0% / 76.1% | 26.5% |

What the numbers say:

- **Memorizing does not generalize.** Exact lookup reaches 60% on the NCM because 68% of the month's
  items repeat a training description; on the 126,723 never-seen descriptions it drops to the level of
  the majority class. That is why the reference number is the "never seen, unique" column.
- **Noise ceiling.** On items whose description was already in training, the declared NCM matches the
  training one in only 86.5%: part of any model's "error" is a label error (the audit below confirms it).
- **Long tail.** 6,583 NCMs in training, many with few examples: macro F1 of 26.5% against a weighted F1
  of 57.7% on never-seen descriptions. This is what PHASE 2 (a Portuguese encoder) has to improve.
- **Cost.** Training on a single CPU core: 28 min (chapter) + 15 min (NCM), peak of ~2.9 GB of RAM,
  resumable from checkpoints. Inference: 0.23 ms/item in batch (the whole test month in 92 s) and 150 ms
  (p50) for a single item. A 215 MB model, pruned to sparse with 99.6% top-1 agreement with the dense
  model.
<!-- ML_RESULTS_END -->

### NCM audit

<!-- AUDIT_START -->
An alert is an item whose declared NCM differs from the prediction with confidence above the threshold.
The threshold was chosen on the validation month. The goal was 95% precision, but it is not reachable:
"precision" there means agreement with the declared NCM, which is noisy. So the threshold with the
highest measured precision is used: **0.99** (92.0% on 45,234 items).

- **Test month:** 3,580 alerts (0.65% of items), across 723 distinct descriptions, totalling
  R$ 2.63 mn; 1,305 of them change even the chapter. Details in [reports/ncm_audit.md](reports/ncm_audit.md).
- **Manual inspection of 60 random alerts**
  ([reports/ncm_audit_inspection.md](reports/ncm_audit_inspection.md)): **50 (83%, 95% CI 72% to 91%)**
  are a wrong declared NCM with the model's suggestion correct (e.g. carrots declared as "horses", wheat
  flour as "cotton waste", tomatoes as "other vegetables"); 5 are books in a neighbouring code, with no
  tax impact; 1 is ambiguous; 1 has both the declared and the predicted code wrong; **3 (5%)** are model
  errors.
- **Caveat:** 45% of the alerts are fresh vegetables and fruit, which usually carry zero federal tax on
  both sides of the mistake. The summed value measures volume, not recoverable tax. The honest use is to
  prioritize human review of the supplier's product registry, not to correct NCMs automatically.
<!-- AUDIT_END -->

## How to run

Requirements: Python 3.11+, ~2 GB of free RAM for the pipeline (DuckDB capped at 1.5 GB) and ~4 GB to
train the baseline; ~3 GB of disk for six months (zips + Parquet + DuckDB) and ~1 GB for the models.

```bash
make install                         # creates .venv and installs the package (editable) + dev
make pipeline MESES=202504-202509    # download -> bronze -> silver -> quality -> gold -> report
make ml                              # ml-dataset (temporal split) -> ml-train -> ml-audit
make publish                         # anonymized dataset + manifest in data/publish/ (does not publish)
make test && make lint               # offline pytest (small fixtures) and ruff

# inference
.venv/bin/python -m raio_x_fiscal.ml.predict "ARROZ TIPO 1" "Vidro temperado 6mm" --k 3

# web app (127.0.0.1:8770; put Nginx in front to publish) and the 8-business example invoices
.venv/bin/pip install -e ".[app]" && .venv/bin/rxf app
.venv/bin/rxf exemplos-lojas         # exemplos/lojas/notas-exemplo-raio-x.zip + reports/exemplos_lojas.md
```

Optional environment variables: `RXF_DATA_DIR`, `RXF_MODELS_DIR`, `RXF_DUCKDB_MEMORY` (default
`1500MB`), `RXF_DUCKDB_THREADS` (default `2`), `RXF_HASH_SALT` (salt for the CPF hash).

**Airflow** (off the production server): `cd airflow && echo "AIRFLOW_UID=$(id -u)" > .env &&
docker compose up airflow-init && docker compose up`, then `http://localhost:8080`. The
`raio_x_fiscal_pipeline` DAG runs `download -> bronze -> silver -> quality` mapped per month (param
`meses`) and then `gold -> quality_gold -> report`; each task calls the same function from
`pipeline/tasks.py` that the CLI uses. The DAG parse was validated with `DagBag` on Airflow 2.10.5
(`tests/test_cli_dag.py`, skipped automatically when Airflow is not installed).

## Layout

```
raio-x-fiscal/
├── src/raio_x_fiscal/
│   ├── config.py             # Paths, months, DuckDB connection with a memory cap
│   ├── cli.py                # rxf: download | bronze | silver | quality | pipeline | gold | ml-* | publish
│   ├── pipeline/
│   │   ├── schema.py         # column contract for the 3 CSVs (bronze fails if it changes)
│   │   ├── normalize.py      # pure rules in Python and in SQL (NCM, CFOP, BR decimal, description)
│   │   ├── download.py       # idempotent monthly zip + sha256 manifest
│   │   ├── bronze.py / silver.py / gold.py
│   │   ├── quality.py        # expectations per layer, JSON + markdown report
│   │   └── tasks.py          # functions shared by the CLI and the DAG
│   ├── ml/
│   │   ├── dataset.py        # temporal split + dedup + leakage flags
│   │   ├── features.py       # word + character TF-IDF (float32)
│   │   ├── models.py         # majority, lookup, calibrated hierarchical SVM
│   │   ├── evaluate.py       # metrics, confusion, latency, calibration
│   │   ├── train.py          # training, evaluation, reports/ml_results.md
│   │   ├── audit.py          # NCM alerts + sample for inspection
│   │   └── predict.py        # inference from the CLI / NcmPredictor class
│   ├── publish/dataset.py    # anonymized dataset for Kaggle/HF
│   ├── produto/              # the product: nfe.py (XML), regras.py (rules), motor.py (engine), cadastro.py
│   │                         #   (register/Bling), ncm_tabela.py (official table + daily job), relatorio.py
│   │                         #   (HTML/XLSX), servidor.py (127.0.0.1 panel), avaliacao.py (public sample)
│   └── seeds/                # NCM chapters (97) and states (UF)
├── dags/raio_x_fiscal_dag.py # Airflow (TaskFlow, dynamic mapping per month)
├── airflow/docker-compose.yml
├── tests/                    # offline pytest, latin-1 fixture with edge cases
├── reports/                  # quality_report.md, ml_results.md, ncm_audit*.md (real numbers, in Portuguese)
├── docs/DATASET_CARD.md      # dataset card (Portuguese); DATASET_CARD.en.md (English)
├── data/ (gitignored)        # raw/ bronze/ silver/ gold/ quality/ ml/ publish/
└── models/ (gitignored)      # featurizer, hierarchical SVM, lookup, metadata.json
```

## Decisions and limitations

- **DuckDB instead of Spark/Databricks**: 3 million rows per semester fit on an 8 GB machine; the
  medallion pattern is the same and the cost is zero. The structure (monthly partitions, schema
  contract, rejects, expectations) is what would move to Delta/Databricks without changing shape.
- **Parquet per partition + DuckDB for gold**: gold is a single file because PHASE 3 needs a database
  that can be queried with read-only SQL; the Parquet export exists for anyone not using DuckDB.
- **Label = NCM declared by the supplier**, which is noisy (26% of items have an ambiguous
  description). Every accuracy figure here is "agreement with the declared code", and part of the
  model's error is being right against a wrong label. The audit exploits exactly that.
- **A linear model, not a transformer**, on purpose: it is the baseline PHASE 2 has to beat, it runs on
  CPU in milliseconds and it is explainable through n-gram weights.
- **Temperature-calibrated confidence** is cheap and a big improvement over the raw SVM score, but it is
  still an approximation; the audit threshold was chosen empirically on the validation month.
- **Rare chapters** (few descriptions) have low F1 and macro F1 reflects that; weighted F1 is the
  operational number.
- **Events** (cancellation, correction letter) came empty in all six months; the layer is ready but has
  not been exercised by real data.
- **No CPF** appeared as an issuer in these months; the mask is tested on a fixture, not in production.

## Roadmap

**Product, next steps.** Suggest the inbound CFOP from the office's own history (the mapping that is
manual today); `cClassTrib` vs NCM after 2027 (tax reform); swap the traffic-light model for the phase 2
TF-IDF + BERTimbau ensemble (on its own BERTimbau still loses; see below); the Q&A chat inside the app
(project A; the slot is ready).

**PHASE 2, BERTimbau on Kaggle (2026-11-07 and 08, private).** Same test month (2025-09, 547,718 items) and
the same subsets as the baseline:

| Run | All items (top-1 / top-5) | Never-seen, unique (top-1 / top-5) | Macro F1 (never-seen) |
|---|---:|---:|---:|
| Baseline TF-IDF + SVM (hybrid with lookup) | **78.7%** / 87.8% | **60.0%** / 76.1% | **26.5%** |
| BERTimbau v1, fast (1 epoch, 16 min on a T4) | 61.5% / 79.4% (hybrid 75.1% / 85.8%) | 48.6% / 68.9% | 9.0% |
| BERTimbau v2, full (3 epochs, 64 tokens, 62 min on a T4) | 69.5% / 86.5% (hybrid 77.7% / **88.9%**) | 56.6% / **76.6%** | 19.4% |

**The baseline still wins on what the traffic light uses** (the top NCM on never-seen descriptions: 60.0%
vs 56.6%), so the traffic light keeps it. BERTimbau v2 already ties or wins at top-5 (76.6% vs 76.1% on
never-seen; 88.9% vs 87.8% hybrid) and is more cautious: at confidence ≥ 0.99 it flags only 105
disagreements in the month (0.02%), against the baseline's 3,580. Next step: an ensemble (averaged
probabilities), measured again. Details in `publicar/kaggle/bertimbau/README.en.md`.

**PHASE 2: a published model.** Fine-tuning a Portuguese encoder (BERTimbau base or similar) on Kaggle
(free GPU) over this phase's anonymized dataset, with the same split protocol and the same four
subsets, for a direct comparison with the baseline. Deliverables: dataset + notebook on Kaggle, model +
dataset on Hugging Face, and a Space with the inference demo and the NCM audit.

**PHASE 3: an analytical agent.** Questions in Portuguese over the gold layer ("how much did the
Ministry of Health spend on NCM 3004 in August, by state?") answered through **read-only** text-to-SQL
(DuckDB read-only, an allow-list of tables, row and time limits), with a **numeric guard**: every
number in the answer text must exist in the query result, otherwise the answer is blocked and
regenerated. Evals with known-answer questions and prompt-injection attacks, cost per role, a pinned
judge, a budget guard and an HTML report, reusing the evaluation harness I already use for my WhatsApp
agents (12 personas, simulated customer, pinned judge, cost per role; private repository). Public demo with a daily usage cap;
the API key stays on the server only.

## Tests and lint

`make test` runs 97 offline tests (12 for the web app, import formats and the 8-business example
invoices: zip upload that never touches disk, per-IP limit, maximum size, Bling CSV with approved rows
only, Olist parts of 500, chat that only mounts with the package and the env file; 26 for the product: XML, folder and zip reading, refusal of
unsafe XML, every rule with a right and a wrong case, office rules, the NCM table job without internet, a
tiny model for NCM-vs-description and search, a report that escapes invoice text, the Bling spreadsheet
round trip and the local panel); besides that: parsing of the latin-1 CSV and Brazilian decimals,
schema contract (drift fails), normalization rules in Python and SQL (parity), rejects and dedup,
bronze/silver/gold idempotency, expectations with the known inconsistencies of the fixture, CPF
masking, a leakage-free split, the hierarchical model (shapes, probabilities, calibration), inference
after a `joblib` round trip, the CLI parser and the DAG structure. `make lint` runs `ruff check` and
`ruff format --check`.

## License

Code under MIT (see `LICENSE`). Data: Transparency Portal / CGU, open data (see the section "Data
source, license and LGPD").
