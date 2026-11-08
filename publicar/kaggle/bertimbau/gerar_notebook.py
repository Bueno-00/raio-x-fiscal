#!/usr/bin/env python3
"""Gera o notebook do Kaggle da FASE 2, parte 2: fine-tuning do BERTimbau (descrição -> NCM).

Escreve publicar/kaggle/bertimbau/notebook/raio-x-fiscal-ncm-bertimbau.ipynb.

Mesmo protocolo do baseline (publicar/kaggle/gerar_notebook.py e reports/ml_results.md):
split temporal (treino 2025-04..07, validação 2025-08, teste 2025-09), treino deduplicado por
descrição normalizada (rótulo = NCM mais frequente, peso log(1 + ocorrências)) e os quatro cortes
do mês de teste. A validação só calibra a temperatura da confiança.

Uso:
  python3 publicar/kaggle/bertimbau/gerar_notebook.py          # escreve o .ipynb
  python3 publicar/kaggle/bertimbau/gerar_notebook.py --check  # compila todas as células (sintaxe)
  python3 publicar/kaggle/bertimbau/gerar_notebook.py --run    # executa aqui (teste de fumaça, CPU)
      RXF_PUBLISH_PARQUET=/caminho/amostra.parquet RXF_NB_SMOKE=1 RXF_NB_MODELO=prajjwal1/bert-tiny
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "notebook" / "raio-x-fiscal-ncm-bertimbau.ipynb"

CELLS: list[tuple[str, str]] = []

CELLS.append(("md", """# Raio-X Fiscal: BERTimbau para descrição de produto → NCM (FASE 2)

**Português** (English summary at the end of this notebook).

A FASE 1 do projeto [raio-x-fiscal](https://github.com/Bueno-00/raio-x-fiscal) treinou um classificador
clássico (TF-IDF + SVM linear hierárquico, só CPU) que acerta **78,7%** do NCM de 8 dígitos no mês de teste
e **60,0%** (top-5 76,1%) nas descrições que nunca apareceram no treino. Este notebook faz o *fine-tuning*
de um encoder em português, o **BERTimbau base** (`neuralmind/bert-base-portuguese-cased`, Souza, Nogueira e
Lotufo, 2020), no mesmo dataset e com **o mesmo protocolo**, para comparar os dois de forma direta:

1. **split temporal**: treino 2025-04 a 2025-07, validação 2025-08 (só para calibrar a confiança), teste 2025-09;
2. **treino deduplicado** por descrição normalizada: uma linha por descrição, rótulo = NCM mais frequente,
   peso `log(1 + ocorrências)` na perda;
3. **classificação plana** em todos os NCMs do treino (cerca de 6,6 mil classes; a cabeça linear cabe com folga
   na GPU, então nenhum NCM raro foi agrupado em "outros");
4. avaliação nos **quatro cortes** do mês de teste e o **híbrido** (descrição já vista → NCM do treino; nova →
   modelo), igual ao baseline.

> **Modo rápido (padrão):** 1 época, textos até 48 *tokens*, orçamento de **25 min** de treino numa T4 (o
> agendamento da taxa de aprendizado encolhe sozinho se o tempo acabar antes da época). Total de ~40 min com
> carga, calibração e teste. `MODO_RAPIDO = False`: 3 épocas, 64 *tokens*, orçamento de 150 min.
"""))

CELLS.append(("code", r'''import os, time, json, math, random
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- configuração
KAGGLE_IN = Path("/kaggle/input")
if KAGGLE_IN.exists():
    print("entradas em /kaggle/input:", [str(q.relative_to(KAGGLE_IN)) for q in KAGGLE_IN.rglob("*") if q.is_file()][:20])
_cands = sorted(KAGGLE_IN.rglob("nfe_ncm_dataset*.parquet")) if KAGGLE_IN.exists() else []
DATA = Path(os.environ.get("RXF_PUBLISH_PARQUET", _cands[0] if _cands else "nfe_ncm_dataset.parquet"))
assert DATA.exists(), f"arquivo não encontrado: {DATA}. Adicione o dataset rafabueno/nfe-ncm-brasil-raio-x-fiscal em 'Add input'."
SAIDA = Path(os.environ.get("RXF_NB_SAIDA", "/kaggle/working" if Path("/kaggle/working").exists() else "saida-bertimbau"))
SAIDA.mkdir(parents=True, exist_ok=True)

MODO_RAPIDO = True             # False = 3 épocas, 64 tokens, orçamento de 150 min
SMOKE = os.environ.get("RXF_NB_SMOKE") == "1"   # só para testar o notebook fora do Kaggle (CPU, modelo minúsculo)

MODELO = os.environ.get("RXF_NB_MODELO", "neuralmind/bert-base-portuguese-cased")
MAX_LEN = 48 if MODO_RAPIDO else 64
EPOCAS = 1 if MODO_RAPIDO else 3
ORCAMENTO_TREINO_MIN = 25 if MODO_RAPIDO else 150
BATCH, BATCH_PRED = 256, 1024
LR_ENCODER, LR_CABECA = 5e-5, 1e-3     # a cabeça (6,6 mil classes) começa do zero e aprende com taxa maior
WARMUP = 0.06
WEIGHT_DECAY = 0.01
N_TRAIN_DESC = None            # None = todas as ~526 mil descrições únicas do treino
N_TEST_ITENS = None            # None = mês de teste inteiro (547.718 itens)
N_VALID_CALIB = 30_000         # itens do mês de validação para calibrar a temperatura
LIMIAR_AUDITORIA = 0.99        # mesmo limiar da auditoria de NCM do repositório
SEED = 42
if SMOKE:
    MAX_LEN, EPOCAS, ORCAMENTO_TREINO_MIN, BATCH, BATCH_PRED = 32, 1, 1.0, 32, 128
    N_TRAIN_DESC, N_TEST_ITENS, N_VALID_CALIB = 4_000, 2_000, 500

random.seed(SEED); np.random.seed(SEED)
print("dataset:", DATA, "| saída:", SAIDA, "| modelo:", MODELO, "| modo rápido:", MODO_RAPIDO, "| smoke:", SMOKE)
'''))

CELLS.append(("md", """## 1. Carregar o dataset

O BERTimbau é *cased* e conhece acentos, então o texto de entrada é a **descrição original** do fornecedor
(`descricao_produto`). A descrição normalizada (minúsculas, sem acento, só `[a-z0-9]`) continua sendo a
**chave** do protocolo: deduplicação do treino, "vista ou não vista" e lookup, exatamente como no baseline.
"""))

CELLS.append(("code", r'''t0 = time.time()
cols = ["split", "mes_referencia", "descricao_produto", "descricao_normalizada", "ncm_codigo"]
df = pd.read_parquet(DATA, columns=cols)
for c in cols:
    df[c] = df[c].astype(str)
df["descricao_produto"] = df["descricao_produto"].str.strip()
print(f"{len(df):,} linhas em {time.time() - t0:.0f}s")
display(df.groupby("split").agg(itens=("ncm_codigo", "size"), meses=("mes_referencia", "nunique"),
                                ncms=("ncm_codigo", "nunique"), descricoes=("descricao_normalizada", "nunique")))
'''))

CELLS.append(("md", """## 2. Treino deduplicado por descrição

Uma linha por descrição normalizada: rótulo = NCM mais frequente, texto = a grafia original mais frequente
daquela descrição, peso `log(1 + ocorrências)`. O lookup (memorização pura) e a marca "vista" usam o treino
inteiro, como no repositório.
"""))

CELLS.append(("code", r'''train = df[df.split == "train"]
pares = train.groupby(["descricao_normalizada", "ncm_codigo"]).size().rename("n").reset_index()
pares = pares.sort_values(["descricao_normalizada", "n"], ascending=[True, False])
ocorr = pares.groupby("descricao_normalizada")["n"].sum().rename("ocorrencias")
n_ncm_por_desc = pares.groupby("descricao_normalizada").size()
train_u = (pares.drop_duplicates("descricao_normalizada")[["descricao_normalizada", "ncm_codigo"]]
           .set_index("descricao_normalizada").join(ocorr).reset_index())
grafias = (train.groupby(["descricao_normalizada", "descricao_produto"]).size().rename("n").reset_index()
           .sort_values(["descricao_normalizada", "n"], ascending=[True, False])
           .drop_duplicates("descricao_normalizada").set_index("descricao_normalizada")["descricao_produto"])
train_u["texto"] = train_u["descricao_normalizada"].map(grafias)
train_u["peso"] = np.log1p(train_u["ocorrencias"]).astype(np.float32)

amb = n_ncm_por_desc > 1
print(f"descrições únicas no treino: {len(train_u):,} (de {len(train):,} itens)")
print(f"descrições com mais de um NCM: {amb.sum():,} ({amb.mean():.1%}), que concentram {ocorr[amb].sum() / ocorr.sum():.1%} dos itens")

lookup = dict(zip(train_u["descricao_normalizada"], train_u["ncm_codigo"]))   # treino inteiro
maj_ncm = train_u.groupby("ncm_codigo")["ocorrencias"].sum().idxmax()

if N_TRAIN_DESC and len(train_u) > N_TRAIN_DESC:
    rng = np.random.default_rng(SEED)
    chave = rng.random(len(train_u)) ** (1.0 / train_u["ocorrencias"].to_numpy())
    train_u = train_u.iloc[np.argsort(-chave)[:N_TRAIN_DESC]].reset_index(drop=True)
    print(f"amostra: {len(train_u):,} descrições de treino")

CLASSES = np.array(sorted(train_u["ncm_codigo"].unique()), dtype=object)
CLS2ID = {c: i for i, c in enumerate(CLASSES)}
y_train = train_u["ncm_codigo"].map(CLS2ID).to_numpy(np.int64)
print(f"classes (NCMs no treino): {len(CLASSES):,} | capítulos: {train_u.ncm_codigo.str[:2].nunique()}")
del train, pares, grafias
'''))

CELLS.append(("md", """## 3. Mês de teste em quatro cortes e amostra de calibração

A predição roda uma vez por **grafia única** do mês de teste e é copiada para os itens repetidos (mesmo
resultado, bem menos GPU).
"""))

CELLS.append(("code", r'''test = df[df.split == "test"].copy()
if N_TEST_ITENS and len(test) > N_TEST_ITENS:
    test = test.sample(n=N_TEST_ITENS, random_state=SEED)
test = test.reset_index(drop=True)
test["vista"] = test["descricao_normalizada"].isin(lookup.keys())
primeira = ~test.duplicated("descricao_normalizada")
cortes = {
    "todos": np.arange(len(test)),
    "unicos": np.flatnonzero(primeira),
    "nao_vistos": np.flatnonzero(~test.vista),
    "nao_vistos_unicos": np.flatnonzero(~test.vista & primeira),
}
print({k: f"{len(v):,}" for k, v in cortes.items()})
print(f"itens do teste com descrição vista no treino: {test.vista.mean():.1%}")
test_textos, test_inv = np.unique(test["descricao_produto"].to_numpy(dtype=object), return_inverse=True)
print(f"grafias únicas a predizer no teste: {len(test_textos):,}")

valid = df[(df.split == "valid") & df.ncm_codigo.isin(CLS2ID.keys())]
if len(valid) == 0:   # amostra local sem mês de validação: calibra num pedaço do teste (só no teste de fumaça)
    valid = test[test.ncm_codigo.isin(CLS2ID.keys())]
valid = valid.sample(n=min(N_VALID_CALIB, len(valid)), random_state=SEED)
print(f"itens de calibração: {len(valid):,}")
del df
'''))

CELLS.append(("md", """## 4. Modelo, tokenização e treino

`AutoModelForSequenceClassification` com uma cabeça linear nova. Precisão mista (fp16) na GPU, *batch* de
256, AdamW com taxa maior na cabeça. O agendamento linear com aquecimento usa o **maior** entre o progresso
em passos e o progresso no tempo: se o orçamento acabar antes da época, a taxa já terá caído a zero e o
modelo termina "fechado", não no meio de uma taxa alta.
"""))

CELLS.append(("code", r'''import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
torch.manual_seed(SEED)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
USA_AMP = DEVICE.type == "cuda"
print("dispositivo:", DEVICE, torch.cuda.get_device_name(0) if USA_AMP else "", "| torch", torch.__version__)

tok = AutoTokenizer.from_pretrained(MODELO)
model = AutoModelForSequenceClassification.from_pretrained(
    MODELO, num_labels=len(CLASSES), ignore_mismatched_sizes=True,
    id2label={i: c for i, c in enumerate(CLASSES)}, label2id={c: i for i, c in enumerate(CLASSES)})
model.to(DEVICE)

def tokeniza(textos):
    return tok(list(textos), truncation=True, max_length=MAX_LEN, add_special_tokens=True)["input_ids"]

t0 = time.time()
ids_train = tokeniza(train_u["texto"].tolist())
lens = np.array([len(x) for x in ids_train])
print(f"tokenização do treino: {time.time() - t0:.0f}s | tokens por descrição: mediana {np.median(lens):.0f}, "
      f"p95 {np.percentile(lens, 95):.0f}, cortadas em {MAX_LEN}: {(lens >= MAX_LEN).mean():.1%}")

PAD = tok.pad_token_id
def colar(lista_ids):
    m = max(len(x) for x in lista_ids)
    ids = torch.full((len(lista_ids), m), PAD, dtype=torch.long)
    att = torch.zeros((len(lista_ids), m), dtype=torch.long)
    for i, x in enumerate(lista_ids):
        ids[i, :len(x)] = torch.tensor(x, dtype=torch.long); att[i, :len(x)] = 1
    return ids, att
'''))

CELLS.append(("code", r'''cabeca = [p for n, p in model.named_parameters() if n.startswith("classifier")]
encoder = [p for n, p in model.named_parameters() if not n.startswith("classifier")]
opt = torch.optim.AdamW([{"params": encoder, "lr": LR_ENCODER}, {"params": cabeca, "lr": LR_CABECA}],
                        weight_decay=WEIGHT_DECAY)
LRS_BASE = [LR_ENCODER, LR_CABECA]
scaler = torch.amp.GradScaler("cuda", enabled=USA_AMP)

n = len(ids_train)
passos_por_epoca = math.ceil(n / BATCH)
total_passos = EPOCAS * passos_por_epoca
passos_warmup = max(10, min(300, int(WARMUP * total_passos)))
orcamento_s = ORCAMENTO_TREINO_MIN * 60
peso_t = torch.tensor(train_u["peso"].to_numpy(), dtype=torch.float32)
y_t = torch.tensor(y_train, dtype=torch.long)
print(f"{n:,} descrições | {passos_por_epoca:,} passos por época | {total_passos:,} passos planejados | "
      f"aquecimento {passos_warmup} | orçamento {ORCAMENTO_TREINO_MIN} min")

model.train()
passo, vistos, t_ini, parou_por_tempo = 0, 0, time.time(), False
hist = []
for ep in range(EPOCAS):
    ordem = np.random.default_rng(SEED + ep).permutation(n)
    perda_acum, k_acum = 0.0, 0
    for b in range(passos_por_epoca):
        dec = time.time() - t_ini
        prog = max(passo / total_passos, dec / orcamento_s)
        if prog >= 1.0:
            parou_por_tempo = passo < total_passos
            break
        fator = min(1.0, (passo + 1) / passos_warmup, (1.0 - prog) / (1.0 - WARMUP))
        for g, base in zip(opt.param_groups, LRS_BASE):
            g["lr"] = base * max(fator, 0.0)
        idx = ordem[b * BATCH:(b + 1) * BATCH]
        ids, att = colar([ids_train[i] for i in idx])
        ids, att = ids.to(DEVICE, non_blocking=True), att.to(DEVICE, non_blocking=True)
        yb, wb = y_t[idx].to(DEVICE), peso_t[idx].to(DEVICE)
        with torch.autocast(device_type=DEVICE.type, dtype=torch.float16, enabled=USA_AMP):
            logits = model(input_ids=ids, attention_mask=att).logits
        perda = (F.cross_entropy(logits.float(), yb, reduction="none") * wb).sum() / wb.sum()
        opt.zero_grad(set_to_none=True)
        scaler.scale(perda).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt); scaler.update()
        passo += 1; vistos += len(idx); perda_acum += perda.item(); k_acum += 1
        if passo % 100 == 0 or passo == 1:
            dec = time.time() - t_ini
            taxa = vistos / max(dec, 1e-9)
            print(f"época {ep + 1} passo {passo:,}/{total_passos:,} | perda {perda_acum / k_acum:.3f} | "
                  f"{taxa:,.0f} descr/s | {dec / 60:.1f} min | lr enc {opt.param_groups[0]['lr']:.2e}", flush=True)
            hist.append({"passo": passo, "perda": perda_acum / k_acum, "min": dec / 60, "descr_por_s": taxa})
            perda_acum, k_acum = 0.0, 0
    if parou_por_tempo:
        break
tempo_treino_min = (time.time() - t_ini) / 60
epocas_feitas = vistos / n
print(f"treino: {passo:,} passos, {vistos:,} exemplos ({epocas_feitas:.2f} épocas) em {tempo_treino_min:.1f} min"
      + (" (parou pelo orçamento de tempo)" if parou_por_tempo else ""))
'''))

CELLS.append(("md", """## 5. Calibração da confiança e predição no mês de teste

A confiança do modelo passa por *temperature scaling* (Guo et al., 2017) ajustado no mês de **validação**:
uma única temperatura `T` que minimiza a perda logarítmica. `T` não muda a ordem do top-k, só a confiança
(usada no limiar da auditoria).
"""))

CELLS.append(("code", r'''@torch.no_grad()
def logits_de(textos, k=5, temperatura=None, guardar_logits=False):
    """Prediz em lotes ordenados por tamanho. Devolve top-k (índices, probabilidades) e, se pedido, os logits."""
    model.eval()
    ids_all = tokeniza(textos)
    ordem = np.argsort([len(x) for x in ids_all])
    top_i = np.zeros((len(textos), k), dtype=np.int64)
    top_p = np.zeros((len(textos), k), dtype=np.float32)
    guard = np.zeros((len(textos), len(CLASSES)), dtype=np.float16) if guardar_logits else None
    T = temperatura or 1.0
    for s in range(0, len(textos), BATCH_PRED):
        sel = ordem[s:s + BATCH_PRED]
        ids, att = colar([ids_all[i] for i in sel])
        with torch.autocast(device_type=DEVICE.type, dtype=torch.float16, enabled=USA_AMP):
            lg = model(input_ids=ids.to(DEVICE), attention_mask=att.to(DEVICE)).logits.float()
        lp = torch.log_softmax(lg / T, dim=1)
        v, i = lp.topk(k, dim=1)
        top_i[sel] = i.cpu().numpy(); top_p[sel] = v.exp().cpu().numpy()
        if guardar_logits:
            guard[sel] = lg.cpu().numpy().astype(np.float16)
    return top_i, top_p, guard

t0 = time.time()
_, _, lg_val = logits_de(valid["descricao_produto"].tolist(), guardar_logits=True)
y_val = torch.tensor(valid["ncm_codigo"].map(CLS2ID).to_numpy(np.int64))
lg_val_t = torch.tensor(lg_val.astype(np.float32))
grade = np.round(np.arange(0.5, 3.01, 0.05), 2)
nll = [F.cross_entropy(lg_val_t / t, y_val).item() for t in grade]
T_CAL = float(grade[int(np.argmin(nll))])
acc_val = (lg_val_t.argmax(1) == y_val).float().mean().item()
print(f"validação: top-1 {acc_val:.1%} em {len(valid):,} itens | temperatura {T_CAL} (perda {min(nll):.3f}, com T=1: {nll[int(np.argmin(np.abs(grade - 1)))]:.3f}) | {time.time() - t0:.0f}s")
del lg_val, lg_val_t

t0 = time.time()
ti, tp, _ = logits_de(list(test_textos), k=5, temperatura=T_CAL)
dt = time.time() - t0
ncm_topk = CLASSES[ti][test_inv]
ncm_prob = tp[test_inv]
print(f"predição de {len(test_textos):,} grafias únicas ({len(test):,} itens) em {dt:.0f}s "
      f"({1000 * dt / len(test_textos):.2f} ms por descrição em lote)")
'''))

CELLS.append(("md", """## 6. Avaliação nos quatro cortes, lado a lado com o baseline

- **BERTimbau**: o modelo deste notebook;
- **híbrido lookup → BERTimbau**: descrição já vista no treino recebe o NCM do treino; nova vai para o modelo
  (mesma regra do melhor baseline);
- linhas do baseline copiadas de `reports/ml_results.md` (protocolo completo, mesmo mês de teste).
"""))

CELLS.append(("code", r'''from sklearn.metrics import f1_score
y_te = test["ncm_codigo"].to_numpy(dtype=object)
look = np.array([lookup.get(d) for d in test["descricao_normalizada"]], dtype=object)

hib_topk = ncm_topk.copy()
tem = np.flatnonzero(look != None)  # noqa: E711
for r in tem:
    resto = [c for c in ncm_topk[r] if c != look[r]][:4]
    hib_topk[r] = [look[r]] + resto

def avalia(idx, topk):
    yn, n1 = y_te[idx], topk[idx][:, 0]
    return {
        "ncm_top1": float((n1 == yn).mean()),
        "ncm_top5": float((topk[idx] == yn[:, None]).any(axis=1).mean()),
        "cap_top1": float((np.array([c[:2] for c in n1]) == np.array([c[:2] for c in yn])).mean()),
        "f1_macro": float(f1_score(yn, n1, average="macro", zero_division=0)),
        "f1_ponderado": float(f1_score(yn, n1, average="weighted", zero_division=0)),
    }

BASELINE = {  # reports/ml_results.md, NCM 8 dígitos, protocolo completo (04/11/2026)
    ("tfidf_svm_hierarquico", "todos"): (0.773, 0.877), ("tfidf_svm_hierarquico", "unicos"): (0.698, 0.832),
    ("tfidf_svm_hierarquico", "nao_vistos"): (0.621, 0.775), ("tfidf_svm_hierarquico", "nao_vistos_unicos"): (0.600, 0.761),
    ("hibrido_lookup_svm", "todos"): (0.787, 0.878), ("hibrido_lookup_svm", "unicos"): (0.712, 0.832),
    ("hibrido_lookup_svm", "nao_vistos"): (0.621, 0.775), ("hibrido_lookup_svm", "nao_vistos_unicos"): (0.600, 0.761),
}
linhas = []
for nome, idx in cortes.items():
    if len(idx) == 0:
        continue
    linhas.append({"modelo": "bertimbau", "corte": nome, "n": len(idx), **avalia(idx, ncm_topk)})
    linhas.append({"modelo": "hibrido_lookup_bertimbau", "corte": nome, "n": len(idx), **avalia(idx, hib_topk)})
res = pd.DataFrame(linhas)
fmt = res.copy()
for c in ["ncm_top1", "ncm_top5", "cap_top1", "f1_macro", "f1_ponderado"]:
    fmt[c] = (100 * res[c]).map("{:.1f}%".format)
pd.set_option("display.width", 180)
print(fmt.to_string(index=False))

alertas = (ncm_topk[:, 0] != y_te) & (ncm_prob[:, 0] >= LIMIAR_AUDITORIA)
print(f"\nauditoria: {alertas.sum():,} itens ({alertas.mean():.2%}) com NCM declarado diferente da predição e "
      f"confiança >= {LIMIAR_AUDITORIA} (baseline: 3.580 alertas, 0,65%)")
'''))

CELLS.append(("code", r'''def pct(x):
    return f"{100 * x:.1f}%".replace(".", ",")

def milhar(x):
    return f"{x:,}".replace(",", ".")

def linha_md(rotulo, corte, top1, top5):
    return f"| {rotulo} | {corte} | {pct(top1)} / {pct(top5)} |"

md = ["# BERTimbau x baseline: descrição -> NCM (8 dígitos)", "",
      f"Gerado em {time.strftime('%Y-%m-%d %H:%M')} UTC. Modelo `{MODELO}`, {'modo rápido' if MODO_RAPIDO else 'modo completo'}, "
      f"max_len {MAX_LEN}, {epocas_feitas:.2f} época(s) em {tempo_treino_min:.0f} min de treino"
      + (" (parou pelo orçamento de tempo)" if parou_por_tempo else "") + f", temperatura {T_CAL}.", "",
      f"Treino: {milhar(len(train_u))} descrições únicas, {milhar(len(CLASSES))} NCMs. Teste: {milhar(len(test))} itens de 2025-09.", "",
      "| Modelo | Corte | Top-1 / Top-5 |", "|---|---|---:|"]
for nome in cortes:
    for mod, rot in (("tfidf_svm_hierarquico", "TF-IDF + SVM hierárquico (baseline)"), ("hibrido_lookup_svm", "híbrido lookup -> SVM (baseline)")):
        b = BASELINE.get((mod, nome))
        if b:
            md.append(linha_md(rot, nome, *b))
    for mod, rot in (("bertimbau", "**BERTimbau**"), ("hibrido_lookup_bertimbau", "**híbrido lookup -> BERTimbau**")):
        r = res[(res.modelo == mod) & (res.corte == nome)]
        if len(r):
            md.append(linha_md(rot, nome, r.ncm_top1.iloc[0], r.ncm_top5.iloc[0]))
n_alertas = f"{int(alertas.sum()):,}".replace(",", ".")
md += ["", f"Auditoria (NCM declarado diferente da predição com confiança >= {LIMIAR_AUDITORIA}): "
       f"{n_alertas} itens ({100 * alertas.mean():.2f}%); baseline: 3.580 (0,65%)."]
tabela_md = "\n".join(md)
(SAIDA / "resultados_bertimbau.md").write_text(tabela_md + "\n", encoding="utf-8")
print(tabela_md)

metricas = {
    "modelo": MODELO, "modo_rapido": MODO_RAPIDO, "smoke": SMOKE, "max_len": MAX_LEN, "batch": BATCH,
    "lr_encoder": LR_ENCODER, "lr_cabeca": LR_CABECA, "epocas_planejadas": EPOCAS, "epocas_feitas": epocas_feitas,
    "passos": passo, "tempo_treino_min": tempo_treino_min, "parou_por_tempo": parou_por_tempo,
    "orcamento_treino_min": ORCAMENTO_TREINO_MIN, "temperatura": T_CAL, "n_train_desc": len(train_u),
    "n_classes": len(CLASSES), "n_test_itens": len(test), "n_test_grafias": len(test_textos),
    "ms_por_descricao_lote": 1000 * dt / len(test_textos),
    "gpu": torch.cuda.get_device_name(0) if USA_AMP else "cpu",
    "resultados": linhas, "baseline": {f"{m}|{c}": v for (m, c), v in BASELINE.items()},
    "auditoria": {"limiar": LIMIAR_AUDITORIA, "alertas": int(alertas.sum()), "fracao": float(alertas.mean())},
    "historico_treino": hist,
}
(SAIDA / "metricas_bertimbau.json").write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")

test["ncm_pred"] = ncm_topk[:, 0]; test["conf"] = ncm_prob[:, 0]
cand = test[(test.ncm_pred != test.ncm_codigo)].sort_values("conf", ascending=False).drop_duplicates("descricao_normalizada")
cand.head(300)[["descricao_produto", "ncm_codigo", "ncm_pred", "conf", "vista"]].to_csv(SAIDA / "divergencias_confiantes.csv", index=False)
print("gravados:", sorted(p.name for p in SAIDA.iterdir()))
'''))

CELLS.append(("code", r'''# exemplos e grava o modelo (fp16, ~220 MB) para subir depois ao Hugging Face
exemplos = ["ARROZ TIPO 1 5KG", "CABO FLEXIVEL 2,5MM2 750V", "PARACETAMOL 500MG COMPRIMIDO",
            "NOTEBOOK 16GB RAM SSD 512GB", "Leite condensado 395 g", "Cenoura in natura kg"]
ei, ep_, _ = logits_de(exemplos, k=3, temperatura=T_CAL)
for e, i, p in zip(exemplos, ei, ep_):
    print(f"{e:35s} -> {CLASSES[i[0]]} ({p[0]:.0%}) | alternativas: {CLASSES[i[1]]} ({p[1]:.0%}), {CLASSES[i[2]]} ({p[2]:.0%})")

if not SMOKE:
    destino = SAIDA / "modelo-bertimbau-ncm"
    model.half().save_pretrained(destino, safe_serialization=True)
    tok.save_pretrained(destino)
    (destino / "raio_x_fiscal.json").write_text(json.dumps(
        {"temperatura": T_CAL, "max_len": MAX_LEN, "protocolo": "treino 2025-04..07, validação 2025-08, teste 2025-09",
         "dataset": "rafabueno/nfe-ncm-brasil-raio-x-fiscal"}, ensure_ascii=False, indent=2), encoding="utf-8")
    tam = sum(f.stat().st_size for f in destino.rglob("*") if f.is_file()) / 1e6
    print(f"modelo gravado em {destino} ({tam:.0f} MB)")
'''))

CELLS.append(("md", """## 7. Como ler o resultado

- **Coluna que importa:** `nao_vistos_unicos` (descrições que o modelo nunca viu, sem repetição). O baseline
  tem 60,0% / 76,1% ali. Se o BERTimbau ganhar nesse corte, ele generaliza melhor; se ganhar só em `todos`,
  está só memorizando melhor.
- **Teto de ruído:** o rótulo é o NCM que o fornecedor declarou. Em 60 divergências conferidas à mão no
  baseline, 50 eram erro do fornecedor. Parte do "erro" de qualquer modelo é acerto contra um rótulo errado.
- **Custo:** o baseline treina em 43 min numa CPU de 1 núcleo e prediz em 0,23 ms por item. O BERTimbau precisa
  de GPU para treinar; a linha de `ms por descrição` acima mostra o custo de predição na T4.
- `divergencias_confiantes.csv`: as 300 descrições em que o modelo discorda do declarado com mais confiança
  (candidatas à auditoria).

---

## English summary

**Raio-X Fiscal, Phase 2: BERTimbau fine-tuning for product description → NCM.** Same public dataset
(Brazilian federal-government e-invoice items, 3.09 M items) and the **same protocol** as the Phase 1 baseline
(TF-IDF + hierarchical linear SVM: 78.7% top-1 on all test items, 60.0% / 76.1% top-1 / top-5 on unseen
unique descriptions): temporal split (train 2025-04..07, validation 2025-08 used only for temperature
scaling, test 2025-09), training deduplicated to one row per normalised description (majority label,
`log(1 + count)` loss weight), flat classification over every training NCM (~6.6 k classes), and the four
test cuts plus the lookup → model hybrid. Input text is the original (cased, accented) supplier description;
the normalised description stays the protocol key. Fast mode (default): 1 epoch, 48 tokens, a 25-minute
training budget on a T4 with a step-or-time linear schedule (~40 min end to end). Outputs: a comparison table
(`resultados_bertimbau.md`), metrics JSON, the 300 most confident disagreements, and the fp16 model.
"""))


def build_notebook() -> None:
    import nbformat as nbf

    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "accelerator": "GPU",
    }
    nb.cells = [
        nbf.v4.new_markdown_cell(src.strip()) if kind == "md" else nbf.v4.new_code_cell(src.strip())
        for kind, src in CELLS
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, OUT)
    print("escrito:", OUT)


def check_cells() -> None:
    for i, (kind, src) in enumerate(CELLS):
        if kind == "code":
            compile(src, f"<celula {i}>", "exec")
    print(f"{sum(1 for k, _ in CELLS if k == 'code')} células de código compilam")


def run_cells() -> None:
    """Executa as células de código em sequência (teste de fumaça fora do Kaggle)."""
    ns = {"display": print}
    for kind, src in CELLS:
        if kind == "code":
            exec(compile(src, "<cell>", "exec"), ns)  # noqa: S102 (teste local, código nosso)


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_cells()
    elif "--run" in sys.argv:
        run_cells()
    else:
        build_notebook()
