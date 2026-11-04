"""Inference: free-text description(s) -> top-k NCM with calibrated confidence.

    python -m raio_x_fiscal.ml.predict "ARROZ TIPO 1" "CABO FLEXIVEL 2,5MM2 750V"
    python -m raio_x_fiscal.ml.predict --json --k 3 "Vidro temperado 6mm"

Loads the artefacts written by `rxf ml-train` from models/ (or RXF_MODELS_DIR).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from raio_x_fiscal.config import Paths
from raio_x_fiscal.ml.features import TextFeaturizer
from raio_x_fiscal.ml.models import HierarchicalLinearNCM, LookupBaseline
from raio_x_fiscal.pipeline.normalize import normalize_description


@dataclass
class Prediction:
    descricao: str
    descricao_normalizada: str
    ncm_topk: list[str]
    ncm_prob: list[float]
    capitulo_topk: list[str]
    capitulo_prob: list[float]
    lookup: str | None

    def as_dict(self) -> dict:
        return {
            "descricao": self.descricao,
            "descricao_normalizada": self.descricao_normalizada,
            "ncm_top1": self.ncm_topk[0],
            "confianca": round(self.ncm_prob[0], 4),
            "top_k": [{"ncm": n, "p": round(p, 4)} for n, p in zip(self.ncm_topk, self.ncm_prob, strict=True)],
            "capitulo_top1": self.capitulo_topk[0],
            "capitulo_confianca": round(self.capitulo_prob[0], 4),
            "visto_no_treino": self.lookup,
        }


class NcmPredictor:
    """Thin wrapper that holds the featurizer, the hierarchical model and the lookup table."""

    def __init__(self, featurizer: TextFeaturizer, model: HierarchicalLinearNCM, lookup: LookupBaseline | None = None):
        self.featurizer = featurizer
        self.model = model
        self.lookup = lookup

    @classmethod
    def load(cls, models_dir: Path | None = None) -> NcmPredictor:
        d = models_dir or Paths.from_env().models
        lookup_path = d / "lookup.joblib"
        return cls(
            joblib.load(d / "featurizer.joblib"),
            joblib.load(d / "hier_svm.joblib"),
            joblib.load(lookup_path) if lookup_path.exists() else None,
        )

    def predict(self, descriptions: list[str], k: int = 5) -> list[Prediction]:
        norm = [normalize_description(d) for d in descriptions]
        X = self.featurizer.transform(norm)
        out = self.model.predict_topk(X, k)
        hits = self.lookup.predict(np.array(norm, dtype=object)) if self.lookup else [None] * len(norm)
        return [
            Prediction(
                descricao=d,
                descricao_normalizada=n,
                ncm_topk=[str(c) for c in out["ncm_topk"][i]],
                ncm_prob=[float(p) for p in out["ncm_prob"][i]],
                capitulo_topk=[str(c) for c in out["capitulo_topk"][i]],
                capitulo_prob=[float(p) for p in out["capitulo_prob"][i]],
                lookup=hits[i],
            )
            for i, (d, n) in enumerate(zip(descriptions, norm, strict=True))
        ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="descricao de produto -> NCM (top-k)")
    ap.add_argument("descricoes", nargs="+")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    args = ap.parse_args(argv)
    predictor = NcmPredictor.load()
    preds = predictor.predict(args.descricoes, k=args.k)
    if args.json:
        print(json.dumps([p.as_dict() for p in preds], indent=2, ensure_ascii=False))
        return 0
    for p in preds:
        print(f"\n{p.descricao}")
        for ncm, prob in zip(p.ncm_topk, p.ncm_prob, strict=True):
            print(f"  {ncm}  p={prob:.3f}")
        if p.lookup:
            print(f"  (descricao identica vista no treino com NCM {p.lookup})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
