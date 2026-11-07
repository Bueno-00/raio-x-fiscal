#!/usr/bin/env python3
"""Gera o notebook do projeto B: "Catálogo de mercado", LoRA de um LLM aberto em português para
classificar produtos de supermercado (Open Food Facts, recorte Brasil) em categorias, comparado com
zero-shot e com TF-IDF + SVM linear no mesmo teste.

Uso:
  python3 publicar/kaggle/projeto-b-lora/gerar_notebook.py          # escreve notebook/catalogo-mercado-lora.ipynb
  RXF_B_MODO=smoke python3 publicar/kaggle/projeto-b-lora/gerar_notebook.py --run   # executa as células aqui (CPU, sem modelo)

Nada aqui roda na GPU nem publica nada: o notebook é enviado ao Kaggle como PRIVADO com `--no-run`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "notebook" / "catalogo-mercado-lora.ipynb"

C: list[tuple[str, str]] = []

C.append(("md", r"""# Catálogo de mercado: fine-tuning leve (LoRA) de um LLM em português para classificar produtos

**Português** (English summary at the end).

Pegamos produtos vendidos no Brasil (nome, marca, quantidade, do **Open Food Facts**) e classificamos
cada um na **categoria do catálogo** (ex.: `yogurts`, `chocolates`, `fruit-juices`). O mesmo teste é
respondido de **três jeitos**, para comparar com honestidade:

1. **Zero-shot**: o modelo de linguagem aberto `Qwen2.5-1.5B-Instruct` recebe a lista de categorias e
   o nome do produto, sem nenhum treino;
2. **TF-IDF + SVM linear**: o classificador clássico de texto (o mesmo tipo usado no baseline do
   [Raio-X Fiscal](https://github.com/Bueno-00/raio-x-fiscal));
3. **LoRA (QLoRA, 4 bits)**: o mesmo modelo de linguagem, treinado por 1 época numa GPU T4 do Kaggle
   com um *adapter* pequeno por cima dos pesos congelados.

**Por que isso conta no iFood.** É o problema do time de catálogo do iFood: classificar milhões de ofertas
de restaurante e mercado numa taxonomia, usando LLMs para rotular dados e monitorar classificadores
(Anna Castro e Murilo Menezes, iFood, workshop WAMLM do KDD 2024). Antes disso, o **FoodBERT** (blog
iFood Engineering, com a Prosus) fez pré-treino e fine-tuning de BERT para enriquecer cardápios. E o iFood
Mercado vive de catálogo de supermercado.

**O que se aprende aqui.** LoRA e QLoRA (treinar só uma camada pequena por cima de um modelo quantizado
em 4 bits), tokenizador e máscara de perda (só a resposta entra na perda), épocas e overfitting, uso de
GPU, avaliação com o mesmo teste para os três jeitos, e publicação do adapter no Hugging Face com card.

> **Modos.** `smoke` (200 produtos, só dados e TF-IDF; roda em CPU), `rapido` (3 mil produtos, zero-shot
> em 300, LoRA em ~2,4 mil; ~35 a 50 min na T4) e `completo` (60 mil produtos; ~2 a 3 h na T4, pode
> precisar de 2 sessões). Sem GPU, as células do modelo são puladas com aviso.
"""))

C.append(("code", r'''import os, re, time, json, difflib
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- configuração
MODO = os.environ.get("RXF_B_MODO", "rapido")          # "smoke" | "rapido" | "completo"
assert MODO in ("smoke", "rapido", "completo")
SEED = 42
TOP_CATEGORIAS = 60
MODELO = "Qwen/Qwen2.5-1.5B-Instruct"
EPOCAS, LR, LORA_R, MAX_LEN = 1, 2e-4, 16, 96
BATCH, ACUM = 8, 4
N_MAX_BR = {"smoke": 200, "rapido": 3_000, "completo": 60_000}[MODO]
N_ZERO_SHOT = {"smoke": 0, "rapido": 300, "completo": 1_000}[MODO]
N_TESTE_LORA = {"smoke": 0, "rapido": 600, "completo": 3_000}[MODO]
SAIDA = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(os.environ.get("RXF_B_SAIDA", ".tmp/projeto-b"))
SAIDA.mkdir(parents=True, exist_ok=True)

try:
    import torch
    TEM_GPU = torch.cuda.is_available()
except Exception:  # torch ausente (teste local)
    torch = None
    TEM_GPU = False
print(f"modo={MODO} | gpu={TEM_GPU} | saída={SAIDA}")
if TEM_GPU:
    print(torch.cuda.get_device_name(0))
'''))

C.append(("code", r'''# dependências que não vêm prontas no Kaggle (transformers, torch e accelerate já existem)
if MODO != "smoke":
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "peft>=0.13", "bitsandbytes>=0.43", "duckdb"], check=False)
'''))

C.append(("md", r"""## 1. Dados: Open Food Facts, recorte Brasil

O Open Food Facts (licença ODbL) publica um Parquet único com ~4,9 milhões de produtos. Em vez de baixar
tudo, lemos **só as colunas necessárias e só as linhas do Brasil** direto do arquivo remoto com DuckDB
(`list_contains(countries_tags, 'en:brazil')`). Colunas reais do arquivo (conferidas em 07/11/2026):
`product_name` é uma lista de `{lang, text}` (pegamos `pt`, depois `main`, depois o primeiro),
`brands`, `quantity`, `categories_tags` (lista; ficamos com as tags `en:`), `lang`, `code`.

**Rótulo.** A taxonomia do Open Food Facts é uma árvore e cada produto traz vários nós (do mais geral ao
mais específico, com ruído). Escolha simples e documentada: o rótulo é **a última tag da lista que esteja
entre as `TOP_CATEGORIAS` mais frequentes do recorte**. Produtos sem nenhuma tag frequente saem do
conjunto. Isso favorece a categoria mais específica entre as comuns e corta a cauda; o ruído que sobra é
parte do problema real (o time de catálogo do iFood lida com o mesmo).
"""))

C.append(("code", r'''import duckdb

URL = "https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet"
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; SET threads=2; SET memory_limit='2GB';")
t0 = time.time()
# sem lambdas no SQL (a sintaxe mudou entre versões do DuckDB); listas são tratadas em Python
sql = f"""
SELECT code, product_name, brands, quantity, lang, categories_tags
FROM read_parquet('{URL}')
WHERE list_contains(countries_tags, 'en:brazil')
  AND len(categories_tags) > 0 AND len(product_name) > 0
LIMIT {N_MAX_BR}
"""
cache = SAIDA / f"raw_br_{MODO}.parquet"   # evita baixar de novo ao reexecutar a célula

def nome_de(lista):
    itens = [] if lista is None else list(lista)   # o DuckDB devolve numpy array de dicts
    por_lingua = {d.get("lang"): (d.get("text") or "") for d in itens if isinstance(d, dict)}
    for chave in ("pt", "main"):
        if por_lingua.get(chave, "").strip():
            return por_lingua[chave].strip()
    return next((v.strip() for v in por_lingua.values() if v and v.strip()), "")

if cache.exists():
    raw = pd.read_parquet(cache)
    raw["categorias"] = raw["categorias"].map(list)
    print("cache:", cache)
else:
    raw = con.execute(sql).df()
    raw["nome"] = raw["product_name"].map(nome_de)
    raw["categorias"] = raw["categories_tags"].map(lambda ts: [t for t in ([] if ts is None else list(ts)) if isinstance(t, str) and t.startswith("en:")])
    raw = raw[(raw["nome"] != "") & (raw["categorias"].map(len) > 0)].drop(columns=["product_name", "categories_tags"]).reset_index(drop=True)
    raw.to_parquet(cache, index=False)
print(f"{len(raw):,} produtos do Brasil em {time.time() - t0:.0f}s")
display(raw.head(5))
'''))

C.append(("code", r'''# rótulo = última tag da lista entre as TOP_CATEGORIAS mais frequentes
freq = Counter(t for cats in raw["categorias"] for t in cats)
top = [t for t, _ in freq.most_common(TOP_CATEGORIAS)]
top_set = set(top)

def rotulo(cats):
    for t in reversed(list(cats)):
        if t in top_set:
            return t
    return None

raw["categoria"] = raw["categorias"].map(rotulo)
df = raw.dropna(subset=["categoria"]).copy()
df["texto"] = (df["nome"] + " | " + df["brands"].fillna("") + " | " + df["quantity"].fillna("")).str.replace(r"\s+", " ", regex=True).str.strip(" |")
df["categoria_legivel"] = df["categoria"].str.replace("en:", "", regex=False)
print(f"com rótulo: {len(df):,} de {len(raw):,} ({len(df) / max(len(raw), 1):.0%}) | categorias usadas: {df.categoria.nunique()}")
display(df["categoria_legivel"].value_counts().head(15))

# split estratificado 80/20 (classes com 1 exemplo vão para o treino)
from sklearn.model_selection import train_test_split
vc = df["categoria"].value_counts()
estrat = df[df["categoria"].isin(vc[vc >= 2].index)]
solo = df[~df["categoria"].isin(vc[vc >= 2].index)]
tr, te = train_test_split(estrat, test_size=0.2, random_state=SEED, stratify=estrat["categoria"])
tr = pd.concat([tr, solo]).sample(frac=1, random_state=SEED).reset_index(drop=True)
te = te.reset_index(drop=True)
df.to_parquet(SAIDA / "catalogo_br.parquet", index=False)
print(f"treino {len(tr):,} | teste {len(te):,} | salvo em {SAIDA / 'catalogo_br.parquet'}")
CATEGORIAS = sorted(df["categoria_legivel"].unique().tolist())
'''))

C.append(("md", r"""## 2. Baseline 1: TF-IDF + SVM linear

TF-IDF transforma cada texto num vetor de pesos de palavras e de pedaços de palavra (3 a 5 letras), dando
mais peso ao que é raro e distintivo. O SVM linear aprende uma reta por categoria nesse espaço. É barato,
roda em CPU e é a régua que o LLM precisa superar.
"""))

C.append(("code", r'''import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score, f1_score

def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

t0 = time.time()
tf_w = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True, dtype=np.float32)
tf_c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, dtype=np.float32)
xtr_txt, xte_txt = tr["texto"].map(norm), te["texto"].map(norm)
Xtr = sp.hstack([tf_w.fit_transform(xtr_txt), tf_c.fit_transform(xtr_txt)], format="csr")
Xte = sp.hstack([tf_w.transform(xte_txt), tf_c.transform(xte_txt)], format="csr")
svm = LinearSVC(C=0.5).fit(Xtr, tr["categoria_legivel"])
t_svm = time.time() - t0
pred_svm = svm.predict(Xte)
res = {"TF-IDF + SVM": {"acuracia": accuracy_score(te["categoria_legivel"], pred_svm),
                        "f1_macro": f1_score(te["categoria_legivel"], pred_svm, average="macro", zero_division=0),
                        "ms_por_item": 1000 * t_svm / max(len(te), 1), "n": len(te)}}
print(json.dumps(res, indent=1, ensure_ascii=False))
'''))

C.append(("md", r"""## 3. Baseline 2: zero-shot com o LLM (sem treino)

Prompt curto em português com a lista de categorias permitidas; geração gulosa de poucos tokens; a
resposta é mapeada para a categoria mais parecida (`difflib`), porque o modelo às vezes devolve variações.
Só em `N_ZERO_SHOT` itens do teste, para caber no tempo; o tempo por item também é medido.
"""))

C.append(("code", r'''def prompt_de(texto):
    lista = ", ".join(CATEGORIAS)
    return (f"Classifique o produto de supermercado numa única categoria da lista.\n"
            f"Categorias: {lista}\n"
            f"Produto: {texto}\n"
            f"Responda só com o nome da categoria.")

def mapear(resposta):
    r = resposta.strip().split("\n")[0].strip().strip(".").lower()
    if r in CATEGORIAS:
        return r
    m = difflib.get_close_matches(r, CATEGORIAS, n=1, cutoff=0.0)
    return m[0] if m else CATEGORIAS[0]

llm = tok = None
if TEM_GPU and N_ZERO_SHOT > 0:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4")
    tok = AutoTokenizer.from_pretrained(MODELO)
    tok.padding_side = "left"
    llm = AutoModelForCausalLM.from_pretrained(MODELO, quantization_config=bnb, device_map="auto")
    llm.eval()

    def gerar(textos, modelo, lote=16, max_new=12):
        saidas = []
        for i in range(0, len(textos), lote):
            msgs = [[{"role": "user", "content": prompt_de(t)}] for t in textos[i:i + lote]]
            enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", padding=True, return_dict=True).to(modelo.device)
            with torch.no_grad():
                out = modelo.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
            saidas += tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        return saidas

    amostra = te.sample(n=min(N_ZERO_SHOT, len(te)), random_state=SEED)
    t0 = time.time()
    pred_zs = [mapear(s) for s in gerar(amostra["texto"].tolist(), llm)]
    dt = time.time() - t0
    res["zero-shot"] = {"acuracia": accuracy_score(amostra["categoria_legivel"], pred_zs),
                        "f1_macro": f1_score(amostra["categoria_legivel"], pred_zs, average="macro", zero_division=0),
                        "ms_por_item": 1000 * dt / len(amostra), "n": len(amostra)}
    print(json.dumps(res["zero-shot"], indent=1))
else:
    print("zero-shot pulado (sem GPU ou N_ZERO_SHOT = 0)")
'''))

C.append(("md", r"""## 4. LoRA (QLoRA, 4 bits)

- Modelo congelado em 4 bits (`BitsAndBytesConfig`), `prepare_model_for_kbit_training`;
- `LoraConfig(r=16, alpha=32, dropout=0.05)` nas projeções de atenção `q, k, v, o`;
- cada exemplo vira *instrução → resposta* no formato de chat do modelo; **só a resposta entra na perda**
  (tokens do prompt recebem `-100`);
- 1 época, batch 8 com acumulação 4 (32 exemplos por passo), `fp16`, taxa de aprendizado 2e-4;
- o adapter (poucos MB) é salvo em `/kaggle/working/adapter` e o tempo total é registrado.
"""))

C.append(("code", r'''t_lora = None
if TEM_GPU and MODO != "smoke":
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import Trainer, TrainingArguments, DataCollatorForSeq2Seq
    from datasets import Dataset

    if llm is None:  # caso o zero-shot tenha sido pulado
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4")
        tok = AutoTokenizer.from_pretrained(MODELO)
        llm = AutoModelForCausalLM.from_pretrained(MODELO, quantization_config=bnb, device_map="auto")
    tok.padding_side = "right"
    base = prepare_model_for_kbit_training(llm)
    cfg = LoraConfig(r=LORA_R, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                     target_modules=["q_proj", "k_proj", "v_proj", "o_proj"])
    modelo = get_peft_model(base, cfg)
    modelo.print_trainable_parameters()

    def tokenizar(ex):
        msgs = [{"role": "user", "content": prompt_de(ex["texto"])}]
        p_ids = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True)
        r_ids = tok(ex["categoria_legivel"] + tok.eos_token, add_special_tokens=False)["input_ids"]
        ids = (p_ids + r_ids)[:MAX_LEN]
        labels = ([-100] * len(p_ids) + r_ids)[:MAX_LEN]
        return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}

    ds_tr = Dataset.from_pandas(tr[["texto", "categoria_legivel"]]).map(tokenizar, remove_columns=["texto", "categoria_legivel"])
    args = TrainingArguments(output_dir=str(SAIDA / "treino"), num_train_epochs=EPOCAS, learning_rate=LR,
                             per_device_train_batch_size=BATCH, gradient_accumulation_steps=ACUM, fp16=True,
                             logging_steps=20, save_strategy="no", report_to=[], seed=SEED,
                             lr_scheduler_type="cosine", warmup_ratio=0.03, optim="paged_adamw_8bit")
    trainer = Trainer(model=modelo, args=args, train_dataset=ds_tr,
                      data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100))
    t0 = time.time()
    trainer.train()
    t_lora = time.time() - t0
    modelo.save_pretrained(str(SAIDA / "adapter"))
    print(f"treino LoRA: {t_lora / 60:.1f} min em {len(ds_tr):,} exemplos; adapter em {SAIDA / 'adapter'}")
else:
    print("treino LoRA pulado (sem GPU ou modo smoke)")
'''))

C.append(("md", r"""## 5. Avaliação do LoRA no mesmo teste e tabela final"""))

C.append(("code", r'''if t_lora is not None:
    modelo.eval(); tok.padding_side = "left"
    amostra = te.sample(n=min(N_TESTE_LORA, len(te)), random_state=SEED)
    t0 = time.time()
    pred_lora = [mapear(s) for s in gerar(amostra["texto"].tolist(), modelo)]
    dt = time.time() - t0
    res["LoRA"] = {"acuracia": accuracy_score(amostra["categoria_legivel"], pred_lora),
                   "f1_macro": f1_score(amostra["categoria_legivel"], pred_lora, average="macro", zero_division=0),
                   "ms_por_item": 1000 * dt / len(amostra), "n": len(amostra), "treino_min": t_lora / 60}
    erros = amostra.assign(pred=pred_lora)
    erros = erros[erros["pred"] != erros["categoria_legivel"]].head(10)[["texto", "categoria_legivel", "pred"]]
    print("10 erros do LoRA:"); display(erros)

tabela = pd.DataFrame(res).T
display(tabela.style.format({"acuracia": "{:.1%}", "f1_macro": "{:.1%}", "ms_por_item": "{:.0f}"}, na_rep="") if hasattr(tabela, "style") else tabela)
(SAIDA / "resultados.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
'''))

C.append(("md", r"""## 6. Subir o adapter para o Hugging Face (PRIVADO, opcional)

Desligado por padrão. Para usar: no Kaggle, menu **Add-ons › Secrets**, crie o secret `HF_TOKEN` com um token
de escrita do Hugging Face (nunca cole o token no notebook). Depois mude `SUBIR_HF = True`. O repositório é
criado **privado**; virar público é decisão do dono, no site.
"""))

C.append(("code", r'''SUBIR_HF = False
if SUBIR_HF and t_lora is not None:
    from kaggle_secrets import UserSecretsClient
    from huggingface_hub import HfApi
    token = UserSecretsClient().get_secret("HF_TOKEN")
    api = HfApi(token=token)
    repo = "RafaelBueno00/catalogo-mercado-lora"
    api.create_repo(repo, private=True, exist_ok=True)
    api.upload_folder(folder_path=str(SAIDA / "adapter"), repo_id=repo, commit_message="adapter LoRA (QLoRA 4 bits) sobre Qwen2.5-1.5B-Instruct")
    api.upload_file(path_or_fileobj=str(SAIDA / "resultados.json"), path_in_repo="resultados.json", repo_id=repo)
    print("ok (privado):", f"https://huggingface.co/{repo}")
'''))

C.append(("md", r"""---

## English summary

**Grocery catalog: light fine-tuning (LoRA) of an open Portuguese-capable LLM to classify supermarket
products.** Products sold in Brazil (name, brand, quantity) from **Open Food Facts** (ODbL; read straight
from the remote Parquet with DuckDB, Brazil rows only) are classified into one of the 60 most frequent
taxonomy nodes of the Brazilian cut (label = the most specific frequent tag in `categories_tags`,
documented as a noisy label). The same held-out test is answered three ways: **zero-shot**
`Qwen2.5-1.5B-Instruct` (4-bit), **TF-IDF + linear SVM**, and **QLoRA** (r=16 on q/k/v/o, 1 epoch,
response-only loss, fp16, T4). Reported: accuracy, macro F1 and ms per item for each, plus 10 LoRA errors.

Why it matters for iFood: this is the shape of the catalog-understanding problem (Castro & Menezes, iFood,
WAMLM @ KDD 2024; FoodBERT on the iFood Engineering blog). What it teaches: LoRA/QLoRA, tokenisation and loss
masking, epochs vs. overfitting, GPU budgeting, honest three-way comparison, publishing an adapter with a
model card. The adapter can be pushed to a **private** Hugging Face repo from Kaggle Secrets (off by default).
"""))


def build():
    import nbformat as nbf

    nb = nbf.v4.new_notebook()
    nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}}
    nb.cells = [nbf.v4.new_markdown_cell(s.strip()) if k == "md" else nbf.v4.new_code_cell(s.strip()) for k, s in C]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, OUT)
    print("escrito:", OUT)


def run():
    ns = {"display": print}
    for k, s in C:
        if k == "code":
            exec(compile(s, "<cell>", "exec"), ns)  # noqa: S102 (teste local)


if __name__ == "__main__":
    run() if "--run" in sys.argv else build()
