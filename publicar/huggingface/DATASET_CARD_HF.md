---
language:
  - pt
license: odbl
pretty_name: "NF-e públicas BR: descrição de produto → NCM"
task_categories:
  - text-classification
tags:
  - portuguese
  - brazil
  - fiscal
  - ncm
  - nf-e
  - e-commerce
  - catalog
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/nfe_ncm_dataset.parquet
---

# NF-e públicas BR: descrição de produto → NCM

**Português** · [English below](#english)

> **Status (06/11/2026):** repositório privado durante a revisão final; vira público com a FASE 2 do
> projeto [raio-x-fiscal](https://github.com/Bueno-00/raio-x-fiscal). O arquivo é um único Parquet com a
> coluna `split` (`train` / `valid` / `test`); filtre por ela.

Itens de notas fiscais eletrônicas de compras do governo federal brasileiro, publicados pelo Portal da
Transparência (CGU), com a **descrição livre do produto** escrita pelo fornecedor e o **NCM de 8 dígitos**
declarado por ele. Tarefa principal: classificar a descrição no NCM (8 dígitos) ou no capítulo (2 dígitos).
Tarefas secundárias: detecção de inconsistência de classificação, normalização de descrições, estudo de
gasto público por categoria.

- Linhas: **3.094.298** itens (seis meses, 2025-04 a 2025-09), 7.381 NCMs, 96 capítulos, ~900 mil
  descrições normalizadas distintas. `train` 2.062.719 · `valid` 483.861 · `test` 547.718.
- Idioma: português do Brasil (texto de fornecedor: abreviações, maiúsculas, erros de digitação).
- Formato: Parquet (ZSTD), 155 MB. `manifest.json` traz contagens, sha256 e data de geração.

## Fonte e licença

Portal da Transparência, conjunto "Notas Fiscais", download mensal
(`https://portaldatransparencia.gov.br/download-de-dados/notas-fiscais/AAAAMM`), arquivos `NotaFiscal` e
`NotaFiscalItem`. Dados abertos do governo federal (catálogo dados.gov.br: ODbL). Este dataset derivado
mantém a licença dos dados de origem; o código que o gera é MIT. Citação sugerida: Controladoria-Geral da
União, Portal da Transparência, Notas Fiscais Eletrônicas (acesso em novembro de 2026); derivado por
Rafael Bueno, repositório `raio-x-fiscal`.

## Privacidade (LGPD)

Removidos: chave de acesso (contém o CNPJ do emitente), CPF/CNPJ e razão social do emitente, inscrição
estadual, CNPJ e nome do destinatário, número e série da nota. Mantidos: descrição do produto, NCM e
descrição oficial do NCM, CFOP, unidade, quantidade, valores, UF do emitente e do destinatário, mês.
`item_id` é um md5 de (chave de acesso, número do item), não reversível sem a chave. A descrição é texto
livre do fornecedor: CNPJs de **fabricante** digitados dentro dela (10 ocorrências formatadas em 3,09
milhões de linhas) foram mascarados como `[cnpj]`; a varredura não encontrou CPF de pessoa, e-mail nem
chave de acesso no texto. Nomes de marca podem aparecer, como na fonte.

## Colunas

| Coluna | Tipo | Descrição |
|---|---|---|
| `item_id` | string | md5(chave_acesso, numero_produto); identificador estável do item |
| `split` | string | `train` (2025-04 a 2025-07), `valid` (2025-08), `test` (2025-09) |
| `mes_referencia` | string | AAAA-MM do arquivo de origem |
| `descricao_produto` | string | descrição livre do fornecedor, como publicada |
| `descricao_normalizada` | string | minúsculas, sem acento, só `[a-z0-9]` separados por espaço |
| `ncm_codigo` | string | NCM de 8 dígitos, zero à esquerda restaurado (**rótulo**) |
| `capitulo` | string | 2 primeiros dígitos do NCM (rótulo grosso) |
| `posicao` | string | 4 primeiros dígitos do NCM |
| `ncm_descricao` | string | descrição oficial do NCM mais frequente para o código |
| `cfop` | string | CFOP de 4 dígitos (NULL se inválido) |
| `unidade` | string | unidade comercial em maiúsculas |
| `quantidade` | decimal(18,4) | quantidade do item |
| `valor_unitario` | decimal(18,4) | valor unitário em BRL |
| `valor_total` | decimal(18,2) | valor total do item em BRL |
| `emitente_uf` | string | UF do fornecedor |
| `destinatario_uf` | string | UF do órgão comprador |
| `seen_in_train` | bool | para `valid`/`test`: a `descricao_normalizada` existe no `train` (NULL no treino) |

## Protocolo recomendado

Split **temporal**: treinar nos meses anteriores, testar no mais recente. O dataset entrega todos os itens
(com repetição) para que cada usuário escolha a política de deduplicação; a recomendada é a do baseline:
(1) treino colapsado a uma linha por `descricao_normalizada`, rótulo = NCM mais frequente; (2) teste em
quatro cortes: todos os itens, descrições únicas, itens com `seen_in_train = false`, e descrições únicas
não vistas (número honesto de generalização).

Ruído de rótulo conhecido: 3,6% das descrições de treino aparecem com mais de um NCM, concentrando 26% dos
itens; entre itens de teste com descrição já vista, o NCM coincide em 86,5% dos casos. O rótulo é o que o
fornecedor declarou, não uma verdade auditada.

## Baseline

TF-IDF (palavra 1-2 + caractere 3-5, 400 mil dimensões) + LinearSVC hierárquico (capítulo, depois NCM
dentro do capítulo), treino 2025-04 a 2025-07, teste 2025-09. Modelo em
`RafaelBueno00/raio-x-fiscal-ncm-baseline`.

| Corte do teste | Capítulo top-1 / top-5 | NCM top-1 / top-5 | NCM F1 macro |
|---|---:|---:|---:|
| Todos os itens (547.718) | 89,0% / 96,0% | 78,7% / 87,8% | 38,1% |
| Descrições únicas não vistas (126.723) | 79,7% / 92,4% | 60,0% / 76,1% | 26,5% |

## Limitações e vieses

Só compras do governo federal (peso forte em material médico-hospitalar, medicamentos, alimentos, livros,
máquinas e eletrônicos); não representa o varejo. Rótulo ruidoso; descrições muito curtas são ambíguas.
Seis meses de um único ano. Valores declarados na nota, sem deflação.

---

<a id="english"></a>
# English

**Brazilian public e-invoices: product description → NCM.** Line items from Brazilian federal-government
purchase e-invoices (NF-e), published as open data by Portal da Transparência (CGU), with the supplier's
free-text product description and the declared 8-digit **NCM** (Mercosur Common Nomenclature, an extension
of the Harmonized System). Main task: classify the description into the NCM (8 digits) or the chapter
(2 digits). Secondary tasks: classification-inconsistency detection, description normalisation, public
spending by category.

- **3,094,298** items over six months (2025-04 to 2025-09), 7,381 NCM codes, 96 chapters, ~900 k distinct
  normalised descriptions. Splits: `train` 2,062,719 (2025-04..07) · `valid` 483,861 (2025-08) · `test`
  547,718 (2025-09), in the `split` column of a single Parquet file (155 MB, ZSTD).
- Language: Brazilian Portuguese supplier text (abbreviations, upper case, typos).
- **License:** open government data (ODbL as registered on dados.gov.br); generating code is MIT. Cite:
  Controladoria-Geral da União, Portal da Transparência, Notas Fiscais Eletrônicas (accessed Nov 2026);
  derived by Rafael Bueno, `raio-x-fiscal`.
- **Privacy:** removed access key (contains issuer CNPJ), issuer CPF/CNPJ and name, state registration,
  recipient CNPJ and name, invoice number and series. Kept: description, NCM and official NCM text, CFOP,
  unit, quantity, amounts, issuer and recipient state, month. `item_id` = md5(access key, item number),
  not reversible without the key. Formatted **manufacturer** CNPJs typed inside descriptions (10
  occurrences in 3.09 M rows) were masked as `[cnpj]`; the scan found no personal CPF, e-mail or access key
  in the text. Brand names may appear, as in the source.
- **Columns:** see the table above (`descricao_produto`, `descricao_normalizada`, `ncm_codigo` = label,
  `capitulo`, `posicao`, `ncm_descricao`, `cfop`, `unidade`, `quantidade`, `valor_unitario`,
  `valor_total`, `emitente_uf`, `destinatario_uf`, `seen_in_train`).
- **Recommended protocol:** temporal split; deduplicate training to one row per normalised description
  (label = most frequent NCM); report the test month in four cuts (all items, unique descriptions, items
  with `seen_in_train = false`, unique unseen descriptions). Known label noise: 3.6% of training
  descriptions carry more than one NCM (26% of items); for seen test items the declared NCM matches
  training only 86.5% of the time.
- **Baseline** (TF-IDF word + char, hierarchical LinearSVC; model `RafaelBueno00/raio-x-fiscal-ncm-baseline`):
  chapter 89.0% / 96.0% top-1 / top-5 on all test items and 79.7% / 92.4% on unseen unique descriptions;
  NCM 78.7% / 87.8% on all items and 60.0% / 76.1% on unseen unique descriptions (macro F1 26.5%).
- **Limitations:** federal procurement only (medical supplies, medicines, food, books, machinery,
  electronics), not retail; noisy labels; very short descriptions are ambiguous; six months of one year.

Code, pipeline, tests and reports: https://github.com/Bueno-00/raio-x-fiscal
