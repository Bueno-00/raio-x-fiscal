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
