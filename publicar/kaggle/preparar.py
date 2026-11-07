#!/usr/bin/env python3
"""Monta publicar/kaggle/dataset/ com hard links para os arquivos de data/publish/ e os cards.

Hard link evita copiar ~380 MB e não entra no git (ver .gitignore da pasta).
"""

from pathlib import Path
import os, shutil

ROOT = Path(__file__).resolve().parents[2]
DST = ROOT / "publicar" / "kaggle" / "dataset"
SRC = ROOT / "data" / "publish"
DST.mkdir(parents=True, exist_ok=True)
for name in ("nfe_ncm_dataset.parquet", "nfe_ncm_dataset.csv.gz", "manifest.json"):
    s, d = SRC / name, DST / name
    if d.exists() or d.is_symlink():
        d.unlink()
    try:
        os.link(s, d)
    except OSError:
        shutil.copy2(s, d)
    print("ok", d.name, f"{d.stat().st_size / 1e6:.1f} MB")
for name in ("DATASET_CARD.md", "DATASET_CARD.en.md"):
    shutil.copy2(ROOT / "docs" / name, DST / name)
    print("ok", name)
