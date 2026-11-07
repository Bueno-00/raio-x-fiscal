#!/usr/bin/env python3
"""Gera o notebook do Kaggle (publicar/kaggle/notebook/raio-x-fiscal-ncm-baseline.ipynb).

O notebook carrega o dataset publicado no Kaggle e reproduz o classificador baseline
descrição -> NCM (TF-IDF palavra + caractere, SVM linear hierárquico: capítulo, depois NCM
dentro do capítulo), com o mesmo protocolo do repositório: split temporal, dedup do treino por
descrição normalizada e quatro cortes de teste.

Uso:
  python3 publicar/kaggle/gerar_notebook.py            # escreve o .ipynb
  python3 publicar/kaggle/gerar_notebook.py --run      # executa as células aqui (teste de fumaça)
      RXF_PUBLISH_PARQUET=/caminho/amostra.parquet RXF_NB_SMOKE=1
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "notebook" / "raio-x-fiscal-ncm-baseline.ipynb"

MD = []  # (tipo, fonte)

MD.append(("md", """# Raio-X Fiscal: descrição de produto → NCM (baseline reproduzível)

**Português** (English summary at the end of this notebook).

Este notebook carrega o dataset **NF-e públicas BR: descrição de produto → NCM** (3,09 milhões de
itens de nota fiscal de compras do governo federal, Portal da Transparência / CGU) e reproduz o
classificador *baseline* do projeto [raio-x-fiscal](https://github.com/Bueno-00/raio-x-fiscal):

1. **split temporal**: treino 2025-04 a 2025-07, validação 2025-08, teste 2025-09;
2. **dedup do treino** por descrição normalizada (rótulo = NCM mais frequente, peso `log(1 + ocorrências)`);
3. **TF-IDF palavra (1-2) + caractere (3-5)** e **SVM linear hierárquico**: um modelo para o capítulo
   (2 dígitos) e um modelo por capítulo para o NCM de 8 dígitos;
4. avaliação em **quatro cortes** do mês de teste: todos os itens, descrições únicas, itens cuja descrição
   nunca apareceu no treino e descrições únicas nunca vistas (o número honesto de generalização).

**Por que isso importa:** NCM errado é imposto errado. E prever a categoria a partir de um texto curto, cheio
de abreviações e digitado por terceiros, é o mesmo formato de problema da categorização de catálogo em
marketplace.

> **Modo rápido (padrão):** amostra de 150 mil descrições de treino e 200 mil itens de teste, vocabulário
> menor, ~10 min em CPU. Para o protocolo completo (526 mil descrições, 547 mil itens, 400 mil features;
> ~45 min e ~6 GB de RAM) defina `MODO_RAPIDO = False` na célula de configuração. Os números de
> referência do modo completo estão no fim do notebook.
"""))

MD.append(("code", r'''import os, time, json
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.metrics import f1_score

# ---------------------------------------------------------------- configuração
KAGGLE_IN = Path("/kaggle/input")
_cands = sorted(KAGGLE_IN.glob("*/nfe_ncm_dataset.parquet")) if KAGGLE_IN.exists() else []
DATA = Path(os.environ.get("RXF_PUBLISH_PARQUET", _cands[0] if _cands else "nfe_ncm_dataset.parquet"))

MODO_RAPIDO = True            # False = protocolo completo (demora ~45 min em CPU)
SMOKE = os.environ.get("RXF_NB_SMOKE") == "1"   # só para testar o notebook fora do Kaggle

N_TRAIN_DESC = 150_000 if MODO_RAPIDO else None
N_TEST_ITENS = 200_000 if MODO_RAPIDO else None
WORD_MAX, CHAR_MAX = (60_000, 120_000) if MODO_RAPIDO else (150_000, 250_000)
if SMOKE:
    N_TRAIN_DESC, N_TEST_ITENS, WORD_MAX, CHAR_MAX = 15_000, 10_000, 8_000, 15_000
SEED = 42
C_SVM = 0.5
TOP_CAPS = 3       # capítulos candidatos para o top-k de NCM
T_CAP, T_NCM = 0.29, 0.25   # temperaturas do softmax ajustadas no mês de validação do protocolo completo (metadata.json)
LOTE = 50_000      # linhas por lote na predição

print("dataset:", DATA, "| modo rápido:", MODO_RAPIDO, "| smoke:", SMOKE)
'''))

MD.append(("md", """## 1. Carregar o dataset

Só as colunas necessárias. `descricao_normalizada` já vem pronta (minúsculas, sem acento, só `[a-z0-9]`),
igual à camada silver do pipeline, então a mesma regra vale aqui e em produção.
"""))

MD.append(("code", r'''t0 = time.time()
cols = ["split", "mes_referencia", "descricao_produto", "descricao_normalizada", "ncm_codigo", "capitulo"]
df = pd.read_parquet(DATA, columns=cols)
for c in ("ncm_codigo", "capitulo"):
    df[c] = df[c].astype(str)
print(f"{len(df):,} linhas em {time.time() - t0:.0f}s")
display(df.groupby("split").agg(itens=("ncm_codigo", "size"), meses=("mes_referencia", "nunique"),
                                ncms=("ncm_codigo", "nunique"), descricoes=("descricao_normalizada", "nunique")))
display(df.sample(5, random_state=SEED)[["descricao_produto", "ncm_codigo", "capitulo"]])
'''))

MD.append(("md", """## 2. Treino deduplicado por descrição

O mesmo texto aparece milhares de vezes (o mês de teste repete 68% das descrições do treino). Treinar com
repetição mede memória, não generalização. Por isso o treino colapsa para **uma linha por descrição
normalizada**, com o NCM mais frequente como rótulo e peso `log(1 + ocorrências)`.

Também medimos o **ruído de rótulo**: descrições que aparecem com mais de um NCM. Esse é o teto de qualquer
modelo, porque o rótulo é o que o fornecedor declarou, não uma verdade auditada.
"""))

MD.append(("code", r'''train = df[df.split == "train"]
pares = train.groupby(["descricao_normalizada", "ncm_codigo"]).size().rename("n").reset_index()
pares = pares.sort_values(["descricao_normalizada", "n"], ascending=[True, False])
ocorr = pares.groupby("descricao_normalizada")["n"].sum().rename("ocorrencias")
n_ncm_por_desc = pares.groupby("descricao_normalizada").size()
train_u = (pares.drop_duplicates("descricao_normalizada")[["descricao_normalizada", "ncm_codigo"]]
           .set_index("descricao_normalizada").join(ocorr).reset_index())
train_u["capitulo"] = train_u["ncm_codigo"].str[:2]
train_u["peso"] = np.log1p(train_u["ocorrencias"])

amb = n_ncm_por_desc > 1
itens_amb = ocorr[amb].sum()
print(f"descrições únicas no treino: {len(train_u):,} (de {len(train):,} itens)")
print(f"descrições com mais de um NCM: {amb.sum():,} ({amb.mean():.1%}), que concentram {itens_amb / ocorr.sum():.1%} dos itens")

if N_TRAIN_DESC and len(train_u) > N_TRAIN_DESC:
    # amostra ponderada pelas ocorrências (Efraimidis-Spirakis): mantém o vocabulário frequente e corta a cauda
    rng = np.random.default_rng(SEED)
    chave = rng.random(len(train_u)) ** (1.0 / train_u["ocorrencias"].to_numpy())
    train_u = train_u.iloc[np.argsort(-chave)[:N_TRAIN_DESC]].reset_index(drop=True)
    print(f"modo rápido: {len(train_u):,} descrições de treino")
print(f"NCMs no treino: {train_u.ncm_codigo.nunique():,} | capítulos: {train_u.capitulo.nunique()}")
'''))

MD.append(("md", """## 3. Mês de teste em quatro cortes

`vista` = a descrição normalizada existe no treino (recalculada para o treino usado nesta execução).
"""))

MD.append(("code", r'''test = df[df.split == "test"].copy()
if N_TEST_ITENS and len(test) > N_TEST_ITENS:
    test = test.sample(n=N_TEST_ITENS, random_state=SEED)
test = test.reset_index(drop=True)
vistas = set(train_u["descricao_normalizada"])
test["vista"] = test["descricao_normalizada"].isin(vistas)
primeira = ~test.duplicated("descricao_normalizada")
cortes = {
    "todos": np.arange(len(test)),
    "unicos": np.flatnonzero(primeira),
    "nao_vistos": np.flatnonzero(~test.vista),
    "nao_vistos_unicos": np.flatnonzero(~test.vista & primeira),
}
print({k: f"{len(v):,}" for k, v in cortes.items()})
print(f"itens do teste com descrição vista no treino: {test.vista.mean():.1%}")
del df  # libera memória
'''))

MD.append(("md", """## 4. Features: TF-IDF de palavras e de caracteres

Palavras (1-2) capturam vocabulário (`arroz`, `parafuso canulado`); caracteres (3-5, dentro da palavra)
sobrevivem a abreviações, erros de digitação e unidades coladas (`2 5mm2`, `desc est`), que estão em toda
descrição digitada por fornecedor.
"""))

MD.append(("code", r'''t0 = time.time()
tf_w = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=WORD_MAX,
                       sublinear_tf=True, dtype=np.float32, token_pattern=r"(?u)\b\w+\b")
tf_c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=CHAR_MAX,
                       sublinear_tf=True, dtype=np.float32)
txt_tr = train_u["descricao_normalizada"].tolist()
Xtr = sp.hstack([tf_w.fit_transform(txt_tr), tf_c.fit_transform(txt_tr)], format="csr", dtype=np.float32)

def featurize(textos):
    return sp.hstack([tf_w.transform(textos), tf_c.transform(textos)], format="csr", dtype=np.float32)

Xte = featurize(test["descricao_normalizada"].tolist())
print(f"features: {Xtr.shape[1]:,} | treino {Xtr.shape} | teste {Xte.shape} | {time.time() - t0:.0f}s")
'''))

MD.append(("md", """## 5. SVM linear hierárquico

Um modelo plano com ~6,6 mil classes x 400 mil features precisaria de ~20 GB de coeficientes. A hierarquia
(capítulo → NCM dentro do capítulo) reduz isso para a soma de `classes_do_capitulo x features`, e cada
sub-modelo treina em segundos. Capítulos com um único NCM viram regra direta.
"""))

MD.append(("code", r'''t0 = time.time()
y_cap = train_u["capitulo"].to_numpy()
y_ncm = train_u["ncm_codigo"].to_numpy()
peso = train_u["peso"].to_numpy()

clf_cap = LinearSVC(C=C_SVM)
clf_cap.fit(Xtr, y_cap, sample_weight=peso)
print(f"capítulo: {len(clf_cap.classes_)} classes em {time.time() - t0:.0f}s")

t0 = time.time()
subs = {}
for cap, idx in train_u.groupby("capitulo").indices.items():
    classes = np.unique(y_ncm[idx])
    if len(classes) == 1:
        subs[cap] = ("unico", classes[0])
        continue
    m = LinearSVC(C=C_SVM)
    m.fit(Xtr[idx], y_ncm[idx], sample_weight=peso[idx])
    subs[cap] = ("modelo", m)
print(f"NCM: {sum(1 for v in subs.values() if v[0] == 'modelo')} sub-modelos em {time.time() - t0:.0f}s")
'''))

MD.append(("md", """### Predição top-k

`P(ncm) = P(capítulo) x P(ncm | capítulo)`, com softmax sobre os scores do SVM. No repositório as duas
temperaturas do softmax são ajustadas no mês de validação (*temperature scaling*, Guo et al., 2017); aqui
usamos os valores encontrados lá (0,29 e 0,25) como constantes, para manter o notebook curto. A temperatura
não muda a ordem do top-k, só a confiança reportada.
"""))

MD.append(("code", r'''def softmax(z, t=1.0):
    z = np.asarray(z, dtype=np.float32) / np.float32(t)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)

def _scores2d(m, X):
    d = m.decision_function(X)
    return np.stack([-d, d], axis=1) if d.ndim == 1 else d   # caso binário

def predict_topk(X, k=5):
    classes_cap = clf_cap.classes_
    p_cap = softmax(clf_cap.decision_function(X), T_CAP)
    ordem = np.argsort(-p_cap, axis=1)
    cap_topk = classes_cap[ordem[:, :k]]
    n = X.shape[0]
    best_p = np.zeros((n, k), dtype=np.float32)
    best_c = np.full((n, k), "", dtype=object)
    cand = ordem[:, :TOP_CAPS]
    for ci in np.unique(cand):
        cap = classes_cap[ci]
        rows = np.flatnonzero((cand == ci).any(axis=1))
        pc = p_cap[rows, ci]
        tipo, m = subs[cap]
        if tipo == "unico":
            probs, ncms = pc[:, None], np.array([m], dtype=object)
        else:
            probs, ncms = softmax(_scores2d(m, X[rows]), T_NCM) * pc[:, None], m.classes_.astype(object)
        allp = np.concatenate([best_p[rows], probs], axis=1)
        allc = np.concatenate([best_c[rows], np.tile(ncms, (len(rows), 1))], axis=1)
        o = np.argsort(-allp, axis=1)[:, :k]
        best_p[rows] = np.take_along_axis(allp, o, axis=1)
        best_c[rows] = np.take_along_axis(allc, o, axis=1)
    return cap_topk, best_c, best_p

t0 = time.time()
partes = [predict_topk(Xte[i:i + LOTE]) for i in range(0, Xte.shape[0], LOTE)]
cap_topk = np.concatenate([p[0] for p in partes]); ncm_topk = np.concatenate([p[1] for p in partes])
ncm_prob = np.concatenate([p[2] for p in partes])
dt = time.time() - t0
print(f"predição de {Xte.shape[0]:,} itens em {dt:.0f}s ({1000 * dt / Xte.shape[0]:.2f} ms/item em lote)")
'''))

MD.append(("md", """## 6. Baselines de referência e avaliação nos quatro cortes

- **classe majoritária**: o piso;
- **lookup exato**: memorização pura (descrição vista → NCM do treino; nunca vista → classe majoritária);
- **TF-IDF + SVM hierárquico**: o modelo deste notebook.
"""))

MD.append(("code", r'''maj_ncm = train_u.groupby("ncm_codigo")["ocorrencias"].sum().idxmax()
maj_cap = maj_ncm[:2]
lookup = dict(zip(train_u["descricao_normalizada"], train_u["ncm_codigo"]))
look_ncm = np.array([lookup.get(d, maj_ncm) for d in test["descricao_normalizada"]], dtype=object)
look_cap = np.array([c[:2] for c in look_ncm], dtype=object)

y_te_ncm = test["ncm_codigo"].to_numpy(dtype=object)
y_te_cap = test["capitulo"].to_numpy(dtype=object)

def avalia(idx, cap_pred_topk, ncm_pred_topk):
    yc, yn = y_te_cap[idx], y_te_ncm[idx]
    c1, n1 = cap_pred_topk[idx][:, 0], ncm_pred_topk[idx][:, 0]
    return {
        "cap top-1": (c1 == yc).mean(),
        "cap top-5": (cap_pred_topk[idx] == yc[:, None]).any(axis=1).mean(),
        "ncm top-1": (n1 == yn).mean(),
        "ncm top-5": (ncm_pred_topk[idx] == yn[:, None]).any(axis=1).mean(),
        "ncm F1 macro": f1_score(yn, n1, average="macro", zero_division=0),
        "ncm F1 ponderado": f1_score(yn, n1, average="weighted", zero_division=0),
    }

linhas = []
for nome, idx in cortes.items():
    n = len(idx)
    maj_c = np.full((len(test), 5), maj_cap, dtype=object); maj_n = np.full((len(test), 5), maj_ncm, dtype=object)
    linhas.append({"corte": nome, "itens": n, "modelo": "classe majoritária", **avalia(idx, maj_c, maj_n)})
    linhas.append({"corte": nome, "itens": n, "modelo": "lookup exato",
                   **avalia(idx, np.repeat(look_cap[:, None], 5, axis=1), np.repeat(look_ncm[:, None], 5, axis=1))})
    linhas.append({"corte": nome, "itens": n, "modelo": "TF-IDF + SVM hierárquico", **avalia(idx, cap_topk, ncm_topk)})
res = pd.DataFrame(linhas)
metricas = [c for c in res.columns if c not in ("corte", "itens", "modelo")]
res_fmt = res.copy()
for c in metricas:
    res_fmt[c] = (100 * res[c]).map("{:.1f}%".format)
pd.set_option("display.width", 160)
display(res_fmt.to_string(index=False))
'''))

MD.append(("md", """### O que os números dizem

- **Memorizar não generaliza.** O lookup exato vai bem em `todos` porque a maioria dos itens repete uma
  descrição do treino; em `nao_vistos_unicos` ele cai para o nível da classe majoritária. O número de
  referência do modelo é a coluna `nao_vistos_unicos`.
- **Teto de ruído.** Parte do "erro" é acerto contra um rótulo errado (a auditoria de NCM do repositório
  confirma: em 60 alertas inspecionados à mão, 50 eram NCM declarado errado).
- **Cauda longa.** Milhares de NCMs com poucos exemplos: F1 macro baixo e F1 ponderado bem mais alto. É o
  ponto que a FASE 2 (fine-tuning de um encoder em português) precisa melhorar.
"""))

MD.append(("code", r'''# exemplos: acertos com confiança alta e erros do modelo
test["ncm_pred"] = ncm_topk[:, 0]; test["conf"] = ncm_prob[:, 0]
test["acertou"] = test["ncm_pred"] == test["ncm_codigo"]
mostrar = ["descricao_produto", "ncm_codigo", "ncm_pred", "conf", "vista"]
print("erros com confiança alta (candidatos a NCM declarado errado):")
display(test[~test.acertou].sort_values("conf", ascending=False).head(10)[mostrar])
print("acertos em descrições nunca vistas:")
display(test[test.acertou & ~test.vista].sample(min(8, int((test.acertou & ~test.vista).sum())), random_state=SEED)[mostrar])
'''))

MD.append(("code", r'''# experimente com descrições suas
exemplos = ["ARROZ TIPO 1 5KG", "CABO FLEXIVEL 2,5MM2 750V", "PARACETAMOL 500MG COMPRIMIDO", "NOTEBOOK 16GB RAM SSD 512GB"]
import re, unicodedata
def normaliza(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()
cap_e, ncm_e, p_e = predict_topk(featurize([normaliza(e) for e in exemplos]), k=3)
for e, n, p in zip(exemplos, ncm_e, p_e):
    print(f"{e:40s} -> {n[0]} ({p[0]:.0%}) | alternativas: {n[1]} ({p[1]:.0%}), {n[2]} ({p[2]:.0%})")
'''))

MD.append(("md", """## 7. Referência: resultados do protocolo completo

Treino com as 526.441 descrições, 400 mil features, calibração por temperatura no mês de validação,
teste nos 547.718 itens de 2025-09 (relatório completo em
[`reports/ml_results.md`](https://github.com/Bueno-00/raio-x-fiscal/blob/main/reports/ml_results.md)):

| Tarefa | Modelo | Todos os itens: top-1 / top-5 | Nunca vistas, únicas: top-1 / top-5 | F1 macro (nunca vistas) |
|---|---|---:|---:|---:|
| Capítulo | TF-IDF + LinearSVC | **89,0% / 96,0%** | **79,7% / 92,4%** | 60,3% |
| NCM (8 dígitos) | TF-IDF + LinearSVC hierárquico | 77,3% / 87,7% | **60,0% / 76,1%** | 26,5% |
| NCM | híbrido lookup → SVM | **78,7% / 87,8%** | 60,0% / 76,1% | 26,5% |

Auditoria de NCM (itens cujo NCM declarado diverge da predição com confiança ≥ 0,99): 3.580 alertas no mês
de teste; numa inspeção manual de 60, **50 (83%)** eram NCM declarado errado com a sugestão do modelo
correta e 3 (5%) eram erro do modelo.

**Próximos passos (FASE 2):** fine-tuning de um encoder em português (BERTimbau) na GPU do Kaggle com este
mesmo dataset e protocolo, para comparar diretamente com o baseline; modelo e demo no Hugging Face.

Código, pipeline medalhão (DuckDB + Airflow), testes e relatórios: https://github.com/Bueno-00/raio-x-fiscal
(licença MIT; dados: Portal da Transparência / CGU, dados abertos).
"""))

MD.append(("md", """---

## English summary

**Raio-X Fiscal: product description → NCM (reproducible baseline).** This notebook loads the public
dataset of Brazilian federal-government e-invoice items (3.09 M items, Portal da Transparência / CGU) and
reproduces the baseline classifier of the [raio-x-fiscal](https://github.com/Bueno-00/raio-x-fiscal)
project. Every item carries the supplier's free-text description and the declared **NCM** (Mercosur tariff
code, 8 digits; an extension of the Harmonized System). Wrong NCM means wrong tax, and predicting a
hierarchical category from short, noisy, third-party text is the same shape of problem as marketplace
catalog categorization.

Protocol: **temporal split** (train 2025-04..07, validation 2025-08, test 2025-09); **training
deduplicated** to one row per normalised description (label = most frequent NCM, weight `log(1 + count)`);
**word (1-2) + character (3-5) TF-IDF** and a **hierarchical linear SVM** (chapter, then NCM within the
chapter); evaluation on **four test cuts**: all items, unique descriptions, items whose description never
appeared in training, and unique unseen descriptions (the honest generalisation number).

Full-protocol reference (see table above): chapter top-1 89.0% on all items and 79.7% on unseen unique
descriptions; NCM top-1 78.7% on all items and 60.0% (top-5 76.1%) on unseen unique descriptions; macro F1
26.5% on the long tail. Label noise ceiling: among test items whose description was seen in training, the
declared NCM matches the training label only 86.5% of the time; a manual inspection of 60 high-confidence
disagreements found 50 (83%) to be supplier errors, not model errors.

The default **fast mode** trains on a weighted sample of 150 k descriptions with a smaller vocabulary
(~10 min on CPU); set `MODO_RAPIDO = False` for the full run. Next step (Phase 2): fine-tune a Portuguese
encoder (BERTimbau) on Kaggle's free GPU with the same split and cuts, and publish model and demo on
Hugging Face.
"""))


def build_notebook():
    import nbformat as nbf

    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    cells = []
    for kind, src in MD:
        cells.append(nbf.v4.new_markdown_cell(src.strip()) if kind == "md" else nbf.v4.new_code_cell(src.strip()))
    nb.cells = cells
    OUT.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, OUT)
    print("escrito:", OUT)


def run_cells():
    """Executa as células de código em sequência (teste de fumaça fora do Kaggle)."""
    ns = {"display": print}
    for kind, src in MD:
        if kind != "code":
            continue
        exec(compile(src, "<cell>", "exec"), ns)  # noqa: S102 (teste local, código nosso)


if __name__ == "__main__":
    if "--run" in sys.argv:
        run_cells()
    else:
        build_notebook()
