---
language:
  - pt
license: mit
library_name: sklearn
pipeline_tag: text-classification
tags:
  - text-classification
  - ncm
  - nf-e
  - fiscal
  - tf-idf
  - linear-svm
  - hierarchical-classification
  - portuguese
  - brazil
metrics:
  - accuracy
  - f1
model-index:
  - name: raio-x-fiscal-ncm-baseline
    results:
      - task:
          type: text-classification
          name: Product description -> NCM (8 digits)
        dataset:
          type: portal-da-transparencia-nfe
          name: NF-e publicas BR (Portal da Transparencia / CGU), test month 2025-09
        metrics:
          - type: accuracy
            name: NCM top-1, all test items (547,718)
            value: 0.787
          - type: accuracy
            name: NCM top-1, unseen unique descriptions (126,723)
            value: 0.600
          - type: accuracy
            name: NCM top-5, unseen unique descriptions
            value: 0.761
          - type: f1
            name: NCM macro F1, unseen unique descriptions
            value: 0.265
          - type: accuracy
            name: Chapter (2 digits) top-1, unseen unique descriptions
            value: 0.797
---

# Raio-X Fiscal: descrição de produto → NCM (baseline)

**Português** · [English below](#english)

> **Status (06/11/2026):** este é o **baseline da FASE 1** (TF-IDF + SVM linear hierárquico, só CPU).
> A **FASE 2** (fine-tuning de um encoder em português, BERTimbau, na GPU do Kaggle, mesmo protocolo)
> está **em treinamento**; o modelo novo será publicado neste mesmo perfil com a comparação lado a lado.
> Repositório privado até a revisão final; vira público com a FASE 2.

Modelo que lê a **descrição livre de um produto** numa nota fiscal eletrônica brasileira (ex.: `CABO
FLEXIVEL 2,5MM2 750V`) e sugere o **NCM** (Nomenclatura Comum do Mercosul, 8 dígitos, extensão do Sistema
Harmonizado), com confiança calibrada e top-k. NCM errado é imposto errado (IPI, PIS/COFINS, ICMS-ST).
Prever uma classe hierárquica a partir de texto curto, cheio de abreviações e digitado por terceiros é o
mesmo formato de problema da **categorização de catálogo em marketplace**.

Código, pipeline de dados, testes e relatórios: https://github.com/Bueno-00/raio-x-fiscal

## Dados de treino

Itens de NF-e de **compras do governo federal** publicados pelo Portal da Transparência (CGU), dados
abertos. Seis meses (2025-04 a 2025-09): 878.858 notas e 3.124.925 itens; 7.381 NCMs distintos.

- **Split temporal:** treino 2025-04 a 2025-07, validação 2025-08 (só calibração e limiar da auditoria),
  teste 2025-09. Nada do mês de teste toca o ajuste.
- **Dedup:** o treino colapsa para **uma linha por descrição normalizada** (526.441 descrições, de 2,06
  milhões de itens), rótulo = NCM mais frequente, peso `log(1 + ocorrências)`.
- **Ruído de rótulo:** 3,6% das descrições de treino aparecem com mais de um NCM, concentrando 26% dos
  itens. O rótulo é o NCM declarado pelo fornecedor, não uma verdade auditada.
- **Privacidade:** o modelo só viu descrição de produto e NCM. Nenhuma chave de acesso, CNPJ/CPF, razão
  social ou destinatário entrou no treino. O vocabulário do TF-IDF e a tabela de lookup contêm apenas
  n-gramas e descrições normalizadas de produtos; CNPJs de fabricante digitados dentro da descrição foram
  mascarados no dataset publicado.

## Arquitetura

| Peça | O que é | Arquivo |
|---|---|---|
| Featurizer | TF-IDF palavra (1-2 gramas, 150 mil) + caractere `char_wb` (3-5 gramas, 250 mil), float32, 400 mil dimensões | `featurizer.joblib` (4 MB) |
| Capítulo | LinearSVC one-vs-rest, 96 classes (2 dígitos) | dentro de `hier_svm.joblib` |
| NCM | um LinearSVC por capítulo (95 sub-modelos, 6.583 classes no total), cabeças podadas para esparso (4,4% dos coeficientes retidos, concordância top-1 de 99,6% com o denso) | `hier_svm.joblib` (215 MB) |
| Calibração | temperature scaling ajustado no mês de validação; `P(ncm) = P(capítulo) × P(ncm \| capítulo)` | `metadata.json` |
| Lookup | descrição normalizada → NCM visto no treino (memorização; usado no híbrido) | `lookup.joblib` (12 MB) |
| Majoritário | classe mais frequente (piso) | `majority.joblib` |

Um modelo plano com ~6,6 mil classes × 400 mil features precisaria de ~20 GB de coeficientes; a hierarquia
reduz isso para a soma de `classes_do_capítulo × features_presentes_no_capítulo`.

## Resultados (mês de teste 2025-09, 547.718 itens)

Quatro cortes, todos reportados; o número honesto de generalização é **"nunca vistas, únicas"**
(126.723 descrições que não existiam no treino).

| Tarefa | Modelo | Todos os itens: top-1 / top-5 | Nunca vistas, únicas: top-1 / top-5 | F1 macro (nunca vistas) |
|---|---|---:|---:|---:|
| Capítulo | classe majoritária | 7,6% / 30,7% | 5,4% / 27,8% | 0,1% |
| Capítulo | lookup exato | 65,3% / 73,8% | 5,4% / 27,8% | 0,1% |
| Capítulo | **TF-IDF + LinearSVC** | **89,0% / 96,0%** | **79,7% / 92,4%** | 60,3% |
| NCM (8 dígitos) | classe majoritária | 5,8% / 18,1% | 4,2% / 13,5% | 0,0% |
| NCM | lookup exato | 60,0% / 64,1% | 4,2% / 13,5% | 0,0% |
| NCM | TF-IDF + LinearSVC hierárquico | 77,3% / 87,7% | **60,0% / 76,1%** | 26,5% |
| NCM | **híbrido lookup → SVM** | **78,7% / 87,8%** | 60,0% / 76,1% | 26,5% |

- F1 ponderado nas descrições nunca vistas: 57,7% (a cauda longa de NCMs raros puxa o F1 macro para baixo).
- Entre itens de teste com descrição já vista no treino, o NCM declarado coincide com o do treino em só
  **86,5%**: parte do "erro" do modelo é acerto contra um rótulo errado.
- **Auditoria de NCM** (desacordo com confiança ≥ 0,99): 3.580 alertas no mês de teste; numa inspeção
  manual de 60, **50 (83%, IC 95% 72% a 91%)** eram NCM declarado errado com a sugestão do modelo correta
  e 3 (5%) eram erro do modelo. Uso honesto: priorizar revisão humana, não corrigir automaticamente.
- **Custo:** treino em CPU de 1 núcleo, 28 min (capítulo) + 15 min (NCM), pico de 2,9 GB de RAM;
  inferência 0,23 ms/item em lote e 150 ms (p50) por item isolado.

Relatórios completos: [`reports/ml_results.md`](https://github.com/Bueno-00/raio-x-fiscal/blob/main/reports/ml_results.md),
[`reports/ncm_audit.md`](https://github.com/Bueno-00/raio-x-fiscal/blob/main/reports/ncm_audit.md),
[`reports/ncm_audit_inspection.md`](https://github.com/Bueno-00/raio-x-fiscal/blob/main/reports/ncm_audit_inspection.md).

## Como usar

Os arquivos `joblib` guardam objetos do pacote `raio_x_fiscal` (MIT), então instale o pacote primeiro:

```bash
pip install "git+https://github.com/Bueno-00/raio-x-fiscal" huggingface_hub
```

```python
from pathlib import Path
from huggingface_hub import snapshot_download
from raio_x_fiscal.ml.predict import NcmPredictor

d = Path(snapshot_download("RafaelBueno00/raio-x-fiscal-ncm-baseline"))
pred = NcmPredictor.load(d)
for p in pred.predict(["ARROZ TIPO 1 5KG", "CABO FLEXIVEL 2,5MM2 750V", "PARACETAMOL 500MG"], k=3):
    print(p.as_dict())
```

Saída: `ncm_top1`, `confianca` (calibrada), `top_k`, `capitulo_top1` e `visto_no_treino` (NCM da tabela de
lookup quando a descrição exata já existia no treino).

## Limitações e uso pretendido

- Cobertura: compras do governo federal, com peso forte em material médico-hospitalar (cap. 90),
  medicamentos (30), alimentos (07, 08), livros (49), máquinas e eletrônicos (84, 85). Não representa o
  varejo nem a indústria em geral; descrições de outros domínios vão cair em NCMs frequentes.
- Rótulo ruidoso; descrições muito curtas ("VENDA", "SERVICO") são legitimamente ambíguas.
- A confiança é calibrada por temperatura (barata e útil), mas continua uma aproximação.
- **Não** usar para corrigir NCM automaticamente em documento fiscal. Usar para sugerir, priorizar revisão e
  medir inconsistência de cadastro.
- Fase 2 (encoder em português com fine-tuning) existe justamente para melhorar a cauda longa.

## Licença e citação

Código e pesos: MIT. Dados de origem: Portal da Transparência / CGU, dados abertos (ODbL registrada no
catálogo dados.gov.br). Citação: Rafael Bueno, *Raio-X Fiscal: descrição de produto → NCM*, 2026,
https://github.com/Bueno-00/raio-x-fiscal.

---

<a id="english"></a>
# English

**Raio-X Fiscal: product description → NCM (baseline)**

> **Status (2026-11-06):** this is the **Phase 1 baseline** (TF-IDF + hierarchical linear SVM, CPU only).
> **Phase 2** (fine-tuning a Portuguese encoder, BERTimbau, on Kaggle's free GPU with the same protocol) is
> **in training**; the new model will be published under this profile with a side-by-side comparison.
> Private until the final review; goes public together with Phase 2.

The model reads the **free-text description of a product** on a Brazilian electronic invoice (NF-e), e.g.
`CABO FLEXIVEL 2,5MM2 750V`, and suggests the **NCM** (Mercosur Common Nomenclature, 8 digits, an extension
of the Harmonized System) with calibrated confidence and top-k alternatives. A wrong NCM means wrong taxes
(IPI, PIS/COFINS, ICMS-ST). Predicting a hierarchical class from short, abbreviation-heavy, third-party text
is the same shape of problem as **marketplace catalog categorization**.

Code, data pipeline, tests and reports: https://github.com/Bueno-00/raio-x-fiscal

**Training data.** Federal-government purchase e-invoice items published as open data by Portal da
Transparência (CGU). Six months (2025-04 to 2025-09): 878,858 invoices and 3,124,925 items; 7,381 distinct
NCM codes. Temporal split (train 2025-04..07, validation 2025-08 for calibration and audit threshold only,
test 2025-09). Training is deduplicated to one row per normalised description (526,441 descriptions from
2.06 M items), label = most frequent NCM, weight `log(1 + count)`. Label noise: 3.6% of training
descriptions carry more than one NCM, concentrating 26% of the items; the label is what the supplier
declared, not an audited truth. Privacy: the model only saw product descriptions and NCM codes; no access
key, CNPJ/CPF, company name or recipient entered training, and formatted manufacturer CNPJs typed inside
descriptions were masked in the published dataset.

**Architecture.** Word (1-2 gram, 150 k) + character `char_wb` (3-5 gram, 250 k) TF-IDF, float32, 400 k
dimensions (`featurizer.joblib`); a one-vs-rest LinearSVC for the chapter (96 classes) and one LinearSVC
per chapter for the 8-digit NCM (95 sub-models, 6,583 classes), heads pruned to sparse (4.4% of
coefficients kept, 99.6% top-1 agreement with the dense heads) (`hier_svm.joblib`, 215 MB); temperature
scaling fitted on the validation month, `P(ncm) = P(chapter) × P(ncm | chapter)`; exact-match lookup table
used by the hybrid (`lookup.joblib`); majority-class floor (`majority.joblib`). A flat model over ~6.6 k
classes × 400 k features would need ~20 GB of coefficients; the hierarchy reduces that to the sum of
`chapter_classes × chapter_features`.

**Results (test month 2025-09, 547,718 items).** All four cuts are reported; the honest generalisation
number is *unseen unique descriptions* (126,723). Chapter: 89.0% / 96.0% top-1 / top-5 on all items,
79.7% / 92.4% on unseen unique, macro F1 60.3%. NCM: 78.7% / 87.8% on all items (hybrid lookup → SVM),
60.0% / 76.1% on unseen unique, macro F1 26.5% (weighted F1 57.7%). Majority class and exact lookup collapse
to 4.2% top-1 on unseen descriptions, which is why memorisation is reported separately. Among test items
whose description was seen in training the declared NCM matches the training label only 86.5% of the time.
NCM audit (disagreement with confidence ≥ 0.99): 3,580 alerts in the test month; a manual inspection of 60
found 50 (83%, 95% CI 72–91%) to be supplier errors with the model's suggestion correct and 3 (5%) model
errors. Cost: 28 + 15 min of single-core CPU training, 2.9 GB peak RAM; inference 0.23 ms/item batched and
150 ms (p50) for a single item.

**How to use.** The `joblib` files hold objects from the MIT-licensed `raio_x_fiscal` package:
`pip install "git+https://github.com/Bueno-00/raio-x-fiscal" huggingface_hub`, then
`NcmPredictor.load(Path(snapshot_download("RafaelBueno00/raio-x-fiscal-ncm-baseline")))` and
`.predict([...], k=3)` (see the Portuguese section for the full snippet).

**Limitations and intended use.** Coverage is federal procurement (heavy on medical supplies, medicines,
food, books, machinery and electronics), not retail or industry at large; labels are noisy; very short
descriptions are legitimately ambiguous; calibrated confidence is an approximation. Do **not** use it to
auto-correct NCM on fiscal documents: use it to suggest, to prioritise human review and to measure
catalog inconsistency. Phase 2 (fine-tuned Portuguese encoder) targets the long tail.

**License and citation.** Code and weights: MIT. Source data: Portal da Transparência / CGU, open data
(ODbL as registered on dados.gov.br). Cite as: Rafael Bueno, *Raio-X Fiscal: product description → NCM*,
2026, https://github.com/Bueno-00/raio-x-fiscal.
