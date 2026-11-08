# Phase 2, part 2: BERTimbau on Kaggle's GPU (private)

[Português](README.md) · **English**

Private notebook `rafabueno/raio-x-fiscal-ncm-bertimbau` (T4 GPU; internet on only to download
`neuralmind/bert-base-portuguese-cased` from the Hugging Face Hub). It fine-tunes BERTimbau base on the
private dataset `rafabueno/nfe-ncm-brasil-raio-x-fiscal` to classify a product description into its 8-digit
NCM code.

**Same protocol as the baseline:** temporal split (train 2025-04..07, validation 2025-08 used only for
temperature scaling, test 2025-09); training deduplicated to one row per normalised description (majority
NCM label, `log(1 + count)` loss weight; the input text is the most frequent original spelling, since the
model is cased); four test cuts plus the lookup → model hybrid, printed next to the baseline rows from
`reports/ml_results.md`.

**Choices:** flat head over every training NCM (~6.6 k classes, ~5 M parameters, no "other" bucket); fp16,
batch 256, AdamW (5e-5 encoder, 1e-3 new head), 6% warm-up, gradient clipping 1.0; a linear schedule driven
by the larger of step progress and wall-clock progress, so a time budget always ends with the learning rate
at zero; prediction once per unique spelling. Fast mode (default, version 1): 1 epoch, 48 tokens, 25-minute
training budget, ~40 min end to end. Full mode: 3 epochs, 64 tokens, 150 minutes.

**Outputs** (`/kaggle/working`): `resultados_bertimbau.md`, `metricas_bertimbau.json`,
`divergencias_confiantes.csv` and the fp16 model in `modelo-bertimbau-ncm/` (~220 MB). Commands are in the
Portuguese README.

**First run (version 1, fast mode, 2026-11-07).** 1 epoch, 48 tokens, 16 minutes of training on a T4. Test
month 2025-09: all items 61.5% / 79.4% top-1 / top-5 (lookup -> BERTimbau hybrid 75.1% / 85.8%) against the
baseline's **78.7% / 87.8%**; never-seen unique descriptions 48.6% / 68.9% against **60.0% / 76.1%**.
**The baseline still wins**: one epoch is not enough for the long tail (macro F1 9% vs 26.5%), so the product's
traffic light keeps the TF-IDF + SVM model. Version 2, full mode (3 epochs, 64 tokens, 150-minute budget),
was submitted on 2026-11-07; it only replaces the baseline if it wins on the same test month.

**Second run (version 2, full mode, finished 2026-11-08 01:33 UTC).** 3 epochs, 64 tokens, 62 minutes of
training on a T4 (~426 descriptions per second). Test month 2025-09: all items 69.5% / 86.5% top-1 / top-5
(lookup -> BERTimbau hybrid 77.7% / **88.9%**) against the baseline's **78.7%** / 87.8%; never-seen unique
descriptions 56.6% / **76.6%** against **60.0%** / 76.1%; macro F1 19.4% vs 26.5%. At confidence ≥ 0.99
it flags 105 disagreements (0.02%) against the baseline's 3,580. **The baseline stays in the traffic light**
(the rule was to switch only if BERTimbau won on never-seen descriptions, and at top-1 it still loses by
3.4 points). It ties or wins at top-5 and makes different mistakes, so the next experiment is an ensemble.

