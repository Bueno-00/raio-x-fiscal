"""Baselines for descricao -> NCM.

- MajorityBaseline: always the most frequent class (the floor).
- LookupBaseline: exact match of the normalised description seen in training (memorisation;
  shows how much of the 'as deployed' accuracy is just repetition).
- HierarchicalLinearNCM: TF-IDF + LinearSVC for the chapter (2 digits), then one LinearSVC per
  chapter for the full 8-digit code. A flat linear model over ~6.5k classes x 400k features
  would need ~20 GB of dense coefficients; the hierarchy keeps it at sum(k_c x F_c), each
  sub-model restricted to the feature columns that occur in its chapter. Scores are turned into
  probabilities by temperature scaling fitted on the validation month (never on test), and the
  joint P(ncm) = P(capitulo) x P(ncm | capitulo) is used for top-k and for the audit confidence.
"""

from __future__ import annotations

import logging
import time
import warnings
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from sklearn.svm import LinearSVC

log = logging.getLogger(__name__)

# Many chapters have more NCM classes than unique descriptions; sklearn's heuristic warning does
# not apply (the labels are categorical codes).
warnings.filterwarnings("ignore", message="The number of unique classes is greater than 50%")

TEMPERATURE_GRID = np.logspace(-1.0, 1.3, 36)


def softmax(scores: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = scores / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _as_2d_scores(clf: LinearSVC, X: sp.csr_matrix) -> np.ndarray:
    """decision_function returns 1-D for binary problems; make it (n, 2) like multiclass."""
    s = clf.decision_function(X)
    if s.ndim == 1:
        s = np.column_stack([-s, s])
    return s


def fit_temperature(scores: np.ndarray, true_idx: np.ndarray) -> float:
    """Single-scalar temperature minimising NLL (Guo et al., 2017). Vectorised grid search."""
    best_t, best_nll = 1.0, np.inf
    rows = np.arange(len(true_idx))
    for t in TEMPERATURE_GRID:
        p = softmax(scores, t)[rows, true_idx]
        nll = -np.log(np.clip(p, 1e-12, 1.0)).mean()
        if nll < best_nll:
            best_t, best_nll = float(t), float(nll)
    return best_t


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
class HierarchicalLinearNCM:
    C: float = 1.0
    top_chapters: int = 3
    max_iter: int = 2000
    chapter_clf: LinearSVC = field(init=False, repr=False)
    sub: dict[str, tuple[np.ndarray | None, LinearSVC | None, np.ndarray]] = field(
        init=False, default_factory=dict, repr=False
    )
    t_chapter: float = 1.0
    t_ncm: float = 1.0
    fit_seconds_: dict[str, float] = field(init=False, default_factory=dict)

    # ---------------------------------------------------------------- training
    def fit(
        self, X: sp.csr_matrix, y_ncm: np.ndarray, sample_weight: np.ndarray | None = None
    ) -> HierarchicalLinearNCM:
        y_cap = chapter_of(y_ncm)
        t0 = time.perf_counter()
        self.chapter_clf = LinearSVC(C=self.C, dual="auto", max_iter=self.max_iter, tol=1e-3)
        self.chapter_clf.fit(X, y_cap, sample_weight=sample_weight)
        self.chapter_clf.coef_ = self.chapter_clf.coef_.astype(np.float32)
        self.fit_seconds_["chapter"] = time.perf_counter() - t0
        log.info("capitulo: %d classes em %.0fs", len(self.chapter_clf.classes_), self.fit_seconds_["chapter"])

        t0 = time.perf_counter()
        X = X.tocsr()
        for cap in self.chapter_clf.classes_:
            rows = np.flatnonzero(y_cap == cap)
            labels = y_ncm[rows]
            classes = np.unique(labels)
            if len(classes) == 1:
                self.sub[cap] = (None, None, classes)
                continue
            Xc = X[rows]
            cols = np.unique(Xc.indices)
            Xc = Xc[:, cols]
            clf = LinearSVC(C=self.C, dual="auto", max_iter=self.max_iter, tol=1e-3)
            sw = None if sample_weight is None else sample_weight[rows]
            clf.fit(Xc, labels, sample_weight=sw)
            clf.coef_ = clf.coef_.astype(np.float32)
            self.sub[cap] = (cols.astype(np.int32), clf, clf.classes_)
        self.fit_seconds_["ncm"] = time.perf_counter() - t0
        n_models = sum(1 for v in self.sub.values() if v[1] is not None)
        log.info("ncm: %d sub-modelos em %.0fs", n_models, self.fit_seconds_["ncm"])
        return self

    # ---------------------------------------------------------------- calibration
    def calibrate(self, X: sp.csr_matrix, y_ncm: np.ndarray) -> dict[str, float]:
        """Fit the two temperatures on a held-out month (validation), not on test."""
        y_cap = chapter_of(y_ncm)
        classes = list(self.chapter_clf.classes_)
        idx = {c: i for i, c in enumerate(classes)}
        keep = np.array([c in idx for c in y_cap])
        scores = self.chapter_clf.decision_function(X[keep])
        self.t_chapter = fit_temperature(scores, np.array([idx[c] for c in y_cap[keep]]))

        all_scores, all_idx = [], []
        for cap, (cols, clf, cls) in self.sub.items():
            if clf is None:
                continue
            rows = np.flatnonzero(y_cap == cap)
            if len(rows) == 0:
                continue
            cidx = {c: i for i, c in enumerate(cls)}
            known = np.array([y in cidx for y in y_ncm[rows]])
            rows = rows[known]
            if len(rows) == 0:
                continue
            s = _as_2d_scores(clf, X[rows][:, cols])
            # pad to a common width so one grid search covers every chapter
            all_scores.append(s)
            all_idx.append(np.array([cidx[y] for y in y_ncm[rows]]))
        width = max(s.shape[1] for s in all_scores)
        padded = np.full((sum(len(s) for s in all_scores), width), -1e4, dtype=np.float32)
        pos = 0
        for s in all_scores:
            padded[pos : pos + len(s), : s.shape[1]] = s
            pos += len(s)
        self.t_ncm = fit_temperature(padded, np.concatenate(all_idx))
        return {"t_chapter": self.t_chapter, "t_ncm": self.t_ncm}

    # ---------------------------------------------------------------- inference
    def chapter_proba(self, X: sp.csr_matrix) -> np.ndarray:
        return softmax(self.chapter_clf.decision_function(X), self.t_chapter)

    def predict_topk(self, X: sp.csr_matrix, k: int = 5) -> dict[str, np.ndarray]:
        """Top-k chapters and top-k NCMs with calibrated joint probabilities."""
        X = X.tocsr()
        n = X.shape[0]
        classes = self.chapter_clf.classes_
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
            cols, clf, cls = self.sub[cap]
            if clf is None:
                joint = pc[:, None]
                labels = np.tile(cls, (len(rows), 1))
            else:
                s = _as_2d_scores(clf, X[rows][:, cols])
                joint = softmax(s, self.t_ncm) * pc[:, None]
                kk = min(k, joint.shape[1])
                part = np.argpartition(-joint, kk - 1, axis=1)[:, :kk]
                joint = np.take_along_axis(joint, part, axis=1)
                labels = cls[part]
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
        n_sub = sum(1 for v in self.sub.values() if v[1] is not None)
        params = int(self.chapter_clf.coef_.size) + sum(
            int(v[1].coef_.size) for v in self.sub.values() if v[1] is not None
        )
        return {
            "capitulos": int(len(self.chapter_clf.classes_)),
            "sub_modelos": n_sub,
            "ncm_classes": int(sum(len(v[2]) for v in self.sub.values())),
            "coeficientes": params,
            "t_chapter": self.t_chapter,
            "t_ncm": self.t_ncm,
            "fit_seconds": {k: round(v, 1) for k, v in self.fit_seconds_.items()},
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
