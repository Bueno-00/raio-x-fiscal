"""Baselines for descricao -> NCM, built to fit an 8 GB box shared with production.

- MajorityBaseline: always the most frequent class (the floor).
- LookupBaseline: exact match of the normalised description seen in training (memorisation;
  shows how much of the 'as deployed' accuracy is just repetition).
- HierarchicalLinearNCM: TF-IDF + linear SVM for the chapter (2 digits), then one linear SVM per
  chapter for the full 8-digit code. A flat linear model over ~6.6k classes x 400k features
  would need ~20 GB of dense coefficients. The hierarchy reduces that to sum(k_c x F_c), and the
  per-chapter heads are stored as pruned sparse float32 matrices (weights below a relative
  threshold are dropped; the agreement with the dense head is measured on the chapter's own
  training rows and reported). Scores become probabilities by temperature scaling fitted on the
  validation month, and P(ncm) = P(capitulo) x P(ncm | capitulo) drives top-k and the audit
  confidence.

Training lives in `ml/fit.py` (resumable, checkpointed); this module holds what inference needs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

TEMPERATURE_GRID = np.logspace(-1.0, 1.3, 36)


def softmax(scores: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = scores.astype(np.float32) / np.float32(temperature)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def chapter_of(codes: np.ndarray) -> np.ndarray:
    return np.array([c[:2] for c in codes], dtype=object)


class MajorityBaseline:
    def fit(self, y: np.ndarray) -> MajorityBaseline:
        self.ranking_ = [c for c, _ in Counter(y).most_common()]
        return self

    def predict_topk(self, n: int, k: int = 5) -> np.ndarray:
        top = self.ranking_[:k]
        return np.tile(np.array(top, dtype=object), (n, 1))


class LookupBaseline:
    """descricao_normalizada -> label seen in training; None when never seen."""

    def fit(self, descriptions: np.ndarray, y: np.ndarray) -> LookupBaseline:
        self.table_ = dict(zip(descriptions, y, strict=True))
        return self

    def predict(self, descriptions: np.ndarray) -> np.ndarray:
        return np.array([self.table_.get(d) for d in descriptions], dtype=object)


@dataclass
class LinearHead:
    """One-vs-rest linear scores: decision(X) = X @ W.T + b, W dense or sparse float32 (k, F)."""

    classes: np.ndarray
    W: np.ndarray | sp.csr_matrix
    b: np.ndarray

    def decision(self, X: sp.csr_matrix) -> np.ndarray:
        s = (X @ self.W.T).toarray() if sp.issparse(self.W) else X @ self.W.T
        return np.asarray(s, dtype=np.float32) + self.b.astype(np.float32)

    @property
    def n_coef(self) -> int:
        return int(self.W.nnz) if sp.issparse(self.W) else int(self.W.size)

    @property
    def n_classes(self) -> int:
        return int(len(self.classes))


class TemperatureFitter:
    """Accumulates NLL over a grid of temperatures, chunk by chunk (no giant score matrix)."""

    def __init__(self, grid: np.ndarray = TEMPERATURE_GRID):
        self.grid = grid
        self.nll = np.zeros(len(grid), dtype=np.float64)
        self.n = 0

    def add(self, scores: np.ndarray, true_idx: np.ndarray) -> None:
        if len(true_idx) == 0:
            return
        rows = np.arange(len(true_idx))
        for i, t in enumerate(self.grid):
            p = softmax(scores, t)[rows, true_idx]
            self.nll[i] -= np.log(np.clip(p, 1e-12, 1.0)).sum()
        self.n += len(true_idx)

    def best(self) -> float:
        return float(self.grid[int(np.argmin(self.nll))]) if self.n else 1.0


def fit_temperature(scores: np.ndarray, true_idx: np.ndarray) -> float:
    """Single-scalar temperature minimising NLL (Guo et al., 2017)."""
    f = TemperatureFitter()
    f.add(scores, true_idx)
    return f.best()


@dataclass
class HierarchicalLinearNCM:
    chapter: LinearHead
    sub: dict[str, LinearHead] = field(default_factory=dict)  # chapters with >= 2 NCMs
    single: dict[str, str] = field(default_factory=dict)  # chapters with exactly 1 NCM
    t_chapter: float = 1.0
    t_ncm: float = 1.0
    top_chapters: int = 3
    meta: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- calibration
    def calibrate(self, X: sp.csr_matrix, y_ncm: np.ndarray) -> dict[str, float]:
        """In-memory convenience (tests / small data); the staged trainer does this per chunk."""
        fc, fn = TemperatureFitter(), TemperatureFitter()
        self.accumulate_calibration(X, y_ncm, fc, fn)
        self.t_chapter, self.t_ncm = fc.best(), fn.best()
        return {"t_chapter": self.t_chapter, "t_ncm": self.t_ncm}

    def accumulate_calibration(
        self, X: sp.csr_matrix, y_ncm: np.ndarray, fit_cap: TemperatureFitter, fit_ncm: TemperatureFitter
    ) -> None:
        y_cap = chapter_of(y_ncm)
        idx = {c: i for i, c in enumerate(self.chapter.classes)}
        keep = np.array([c in idx for c in y_cap], dtype=bool)
        if keep.any():
            fit_cap.add(self.chapter.decision(X[keep]), np.array([idx[c] for c in y_cap[keep]]))
        for cap, head in self.sub.items():
            rows = np.flatnonzero(y_cap == cap)
            if len(rows) == 0:
                continue
            cidx = {c: i for i, c in enumerate(head.classes)}
            known = np.array([y in cidx for y in y_ncm[rows]], dtype=bool)
            rows = rows[known]
            if len(rows) == 0:
                continue
            fit_ncm.add(head.decision(X[rows]), np.array([cidx[y] for y in y_ncm[rows]]))

    # ---------------------------------------------------------------- inference
    def chapter_proba(self, X: sp.csr_matrix) -> np.ndarray:
        return softmax(self.chapter.decision(X), self.t_chapter)

    def predict_topk(self, X: sp.csr_matrix, k: int = 5) -> dict[str, np.ndarray]:
        """Top-k chapters and top-k NCMs with calibrated joint probabilities."""
        X = X.tocsr()
        n = X.shape[0]
        classes = self.chapter.classes
        p_cap = self.chapter_proba(X)
        order = np.argsort(-p_cap, axis=1)
        cap_topk = classes[order[:, :k]]
        cap_prob = np.take_along_axis(p_cap, order[:, :k], axis=1)
        cand = order[:, : self.top_chapters]

        best_prob = np.zeros((n, k), dtype=np.float32)
        best_ncm = np.full((n, k), "", dtype=object)
        for ci in np.unique(cand):
            cap = classes[ci]
            rows = np.flatnonzero((cand == ci).any(axis=1))
            pc = p_cap[rows, ci]
            if cap in self.sub:
                head = self.sub[cap]
                joint = softmax(head.decision(X[rows]), self.t_ncm) * pc[:, None]
                kk = min(k, joint.shape[1])
                part = np.argpartition(-joint, kk - 1, axis=1)[:, :kk]
                joint = np.take_along_axis(joint, part, axis=1)
                labels = head.classes[part]
            else:
                joint = pc[:, None]
                labels = np.full((len(rows), 1), self.single[cap], dtype=object)
            merged_p = np.concatenate([best_prob[rows], joint.astype(np.float32)], axis=1)
            merged_l = np.concatenate([best_ncm[rows], labels.astype(object)], axis=1)
            o = np.argsort(-merged_p, axis=1)[:, :k]
            best_prob[rows] = np.take_along_axis(merged_p, o, axis=1)
            best_ncm[rows] = np.take_along_axis(merged_l, o, axis=1)
        return {
            "capitulo_topk": cap_topk,
            "capitulo_prob": cap_prob,
            "ncm_topk": best_ncm,
            "ncm_prob": best_prob,
        }

    def describe(self) -> dict:
        return {
            "capitulos": self.chapter.n_classes,
            "sub_modelos": len(self.sub),
            "capitulos_com_um_ncm": len(self.single),
            "ncm_classes": int(sum(h.n_classes for h in self.sub.values()) + len(self.single)),
            "coeficientes_capitulo": self.chapter.n_coef,
            "coeficientes_ncm_apos_poda": int(sum(h.n_coef for h in self.sub.values())),
            "t_chapter": self.t_chapter,
            "t_ncm": self.t_ncm,
            **self.meta,
        }


def hybrid_topk(lookup: np.ndarray, model_topk: np.ndarray) -> np.ndarray:
    """Lookup first (when the description was seen), model ranking after it (deduplicated)."""
    out = model_topk.copy()
    k = out.shape[1]
    for i, hit in enumerate(lookup):
        if hit is None:
            continue
        rest = [c for c in out[i] if c != hit][: k - 1]
        out[i] = np.array([hit, *rest], dtype=object)
    return out
