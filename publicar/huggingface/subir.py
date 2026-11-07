#!/usr/bin/env python3
"""Sobe o modelo baseline e o dataset anonimizado para o Hugging Face, em repositórios PRIVADOS.

Nada aqui torna um repositório público: isso é um clique no site (Settings > Change visibility), feito
pelo dono da conta quando ele decidir. O token vem só de `HF_TOKEN` no ambiente (carregue o `.env` com
`set -a; . .env; set +a`); nunca é impresso nem gravado.

Uso (na raiz do repositório):
  .venv/bin/python publicar/huggingface/subir.py modelo     # card + featurizer, hier_svm, lookup, majority, metadata
  .venv/bin/python publicar/huggingface/subir.py dataset    # card + nfe_ncm_dataset.parquet (+ manifest)
  .venv/bin/python publicar/huggingface/subir.py status     # lista o que existe e a visibilidade
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
USER = "RafaelBueno00"
REPO_MODELO = f"{USER}/raio-x-fiscal-ncm-baseline"
REPO_DATASET = f"{USER}/nfe-ncm-brasil"

MODEL_FILES = ["featurizer.joblib", "hier_svm.joblib", "lookup.joblib", "majority.joblib", "metadata.json"]


def api() -> HfApi:
    tok = os.environ.get("HF_TOKEN")
    if not tok:
        sys.exit("HF_TOKEN ausente no ambiente (set -a; . .env; set +a)")
    return HfApi(token=tok)


def subir_modelo() -> None:
    a = api()
    a.create_repo(REPO_MODELO, repo_type="model", private=True, exist_ok=True)
    a.upload_file(path_or_fileobj=str(HERE / "MODEL_CARD.md"), path_in_repo="README.md", repo_id=REPO_MODELO,
                  commit_message="docs: model card (pt + en)")
    for name in MODEL_FILES:
        p = ROOT / "models" / name
        if not p.exists():
            print("faltando, pulado:", p)
            continue
        print(f"subindo {name} ({p.stat().st_size / 1e6:.1f} MB)")
        a.upload_file(path_or_fileobj=str(p), path_in_repo=name, repo_id=REPO_MODELO,
                      commit_message=f"model: {name} (baseline FASE 1, treino 2025-04..07)")
    print("ok:", f"https://huggingface.co/{REPO_MODELO}", "(privado)")


def subir_dataset() -> None:
    a = api()
    a.create_repo(REPO_DATASET, repo_type="dataset", private=True, exist_ok=True)
    a.upload_file(path_or_fileobj=str(HERE / "DATASET_CARD_HF.md"), path_in_repo="README.md",
                  repo_id=REPO_DATASET, repo_type="dataset", commit_message="docs: dataset card (pt + en)")
    for name in ("nfe_ncm_dataset.parquet", "manifest.json"):
        p = ROOT / "data" / "publish" / name
        print(f"subindo {name} ({p.stat().st_size / 1e6:.1f} MB)")
        a.upload_file(path_or_fileobj=str(p), path_in_repo=f"data/{name}" if name.endswith(".parquet") else name,
                      repo_id=REPO_DATASET, repo_type="dataset",
                      commit_message=f"data: {name} (6 meses, anonimizado, split temporal)")
    print("ok:", f"https://huggingface.co/datasets/{REPO_DATASET}", "(privado)")


def status() -> None:
    a = api()
    for rid, rt in ((REPO_MODELO, "model"), (REPO_DATASET, "dataset")):
        try:
            info = a.repo_info(rid, repo_type=rt)
            files = [s.rfilename for s in info.siblings] if info.siblings else []
            print(f"{rt}: {rid} | privado={info.private} | arquivos={files}")
        except Exception as e:  # noqa: BLE001
            print(f"{rt}: {rid} | nao existe ({type(e).__name__})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"modelo": subir_modelo, "dataset": subir_dataset, "status": status}[cmd]()
