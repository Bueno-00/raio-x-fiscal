"""Resumable training of the hierarchical linear model.

Why resumable: on the 8 GB VPS the full fit takes ~40 minutes and shares the box with production
processes. Every unit of work (one binary chapter classifier, one chapter's NCM head) is written
to `models/ckpt/` as soon as it finishes, and each stage accepts a time budget: when the budget
runs out the function returns `None`, and the next call picks up where it stopped. Running the
stages without a budget (the VPS Makefile) is the same code path.

Memory discipline:
- the chapter head is one-vs-rest done by hand (one LinearSVC per chapter), so only one dense
  coefficient vector lives in RAM at a time;
- each NCM head is trained only on the feature columns that occur at least twice in its chapter,
  then pruned to a sparse float32 matrix; the agreement between dense and pruned predictions on
  the chapter's own training rows is recorded (and reported) so the pruning cost is measured,
  not assumed.
"""

from __future__ import annotations

import json
import logging
import time
import warnings
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from sklearn.svm import LinearSVC

from raio_x_fiscal.ml.models import HierarchicalLinearNCM, LinearHead, chapter_of

log = logging.getLogger(__name__)

# Many chapters have more NCM classes than unique descriptions; sklearn's heuristic warning does
# not apply (the labels are categorical codes).
warnings.filterwarnings("ignore", message="The number of unique classes is greater than 50%")

PRUNE_DEFAULTS = {"rel": 0.02, "abs_min": 1e-3, "cap": 20_000}


class Budget:
    def __init__(self, seconds: float | None):
        self.deadline = None if seconds is None else time.monotonic() + seconds

    def exhausted(self) -> bool:
        return self.deadline is not None and time.monotonic() > self.deadline


def _svc(C: float, tol: float) -> LinearSVC:
    return LinearSVC(C=C, dual="auto", tol=tol, max_iter=2000)


def fit_binary(X, y_bin: np.ndarray, sw: np.ndarray | None, C: float = 1.0, tol: float = 1e-3):
    clf = _svc(C, tol).fit(X, y_bin.astype(np.int8), sample_weight=sw)
    return clf.coef_.ravel().astype(np.float32), float(clf.intercept_[0])


def fit_multiclass(X, y: np.ndarray, sw: np.ndarray | None, C: float = 1.0, tol: float = 1e-3):
    """Returns (classes, W dense float32 (k, F), b (k,)); binary problems are expanded to 2 rows."""
    clf = _svc(C, tol).fit(X, y, sample_weight=sw)
    W = clf.coef_.astype(np.float32)
    b = clf.intercept_.astype(np.float32)
    if len(clf.classes_) == 2:
        W = np.vstack([-W, W])
        b = np.concatenate([-b, b])
    return clf.classes_.astype(object), W, b


def prune(W: np.ndarray, rel: float, abs_min: float, cap: int) -> sp.csr_matrix:
    """Keep, per class, weights with |w| >= max(abs_min, rel * max|w|), at most `cap` of them."""
    rows, cols, vals = [], [], []
    for i in range(W.shape[0]):
        row = W[i]
        a = np.abs(row)
        thr = max(abs_min, rel * float(a.max()) if a.size else abs_min)
        keep = np.flatnonzero(a >= thr)
        if len(keep) > cap:
            keep = keep[np.argpartition(-a[keep], cap - 1)[:cap]]
        rows.append(np.full(len(keep), i, dtype=np.int32))
        cols.append(keep.astype(np.int32))
        vals.append(row[keep])
    return sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=W.shape, dtype=np.float32
    )


# ---------------------------------------------------------------------------------------------
# Chapter head: one-vs-rest by hand, one checkpoint per chapter
# ---------------------------------------------------------------------------------------------


def fit_chapter_head(
    X,
    y_cap: np.ndarray,
    sw: np.ndarray | None,
    ckpt_dir: Path | None,
    budget_s: float | None = None,
    C: float = 1.0,
    tol: float = 1e-3,
) -> LinearHead | None:
    classes = np.unique(y_cap)
    budget = Budget(budget_s)
    parts: dict[str, tuple[np.ndarray, float]] = {}
    for c in classes:
        path = ckpt_dir / f"cap_{c}.npz" if ckpt_dir else None
        if path and path.exists():
            z = np.load(path)
            parts[c] = (z["w"], float(z["b"]))
            continue
        if budget.exhausted():
            log.info("capitulo: orcamento esgotado, %d/%d classes prontas", len(parts), len(classes))
            return None
        t0 = time.perf_counter()
        w, b = fit_binary(X, y_cap == c, sw, C, tol)
        if path:
            np.savez(path, w=w, b=np.float32(b), seconds=np.float32(time.perf_counter() - t0))
        parts[c] = (w, b)
        log.info("capitulo %s: %.0fs (%d/%d)", c, time.perf_counter() - t0, len(parts), len(classes))
    W = np.vstack([parts[c][0] for c in classes]).astype(np.float32)
    b = np.array([parts[c][1] for c in classes], dtype=np.float32)
    return LinearHead(classes.astype(object), W, b)


# ---------------------------------------------------------------------------------------------
# NCM heads: one multiclass SVM per chapter, pruned to sparse, one checkpoint per chapter
# ---------------------------------------------------------------------------------------------


def _fit_ncm_head(X, rows: np.ndarray, labels: np.ndarray, sw, C, tol, prune_kw) -> dict:
    Xc = X[rows]
    df = np.asarray((Xc > 0).sum(axis=0)).ravel()
    cols = np.flatnonzero(df >= 2)
    if len(cols) < 10:  # tiny chapter: keep every column that appears at all
        cols = np.flatnonzero(df >= 1)
    Xc = Xc[:, cols]
    t0 = time.perf_counter()
    classes, W, b = fit_multiclass(Xc, labels, None if sw is None else sw[rows], C, tol)
    seconds = time.perf_counter() - t0
    dense_pred = np.argmax(Xc @ W.T + b, axis=1)
    Wp = prune(W, **prune_kw)
    pruned_pred = np.argmax((Xc @ Wp.T).toarray() + b, axis=1)
    agreement = float((dense_pred == pruned_pred).mean())
    # expand to the global feature space (free: only indices change)
    Wg = sp.csr_matrix((Wp.data, cols[Wp.indices].astype(np.int32), Wp.indptr), shape=(W.shape[0], X.shape[1]))
    return {
        "classes": classes,
        "W": Wg,
        "b": b,
        "stats": {
            "rows": int(len(rows)),
            "cols": int(len(cols)),
            "classes": int(len(classes)),
            "coef_dense": int(W.size),
            "coef_pruned": int(Wg.nnz),
            "agreement_pruned_vs_dense": agreement,
            "seconds": round(seconds, 1),
        },
    }


def _save_head(path: Path, head: dict) -> None:
    W: sp.csr_matrix = head["W"]
    np.savez(
        path,
        classes=np.array(head["classes"], dtype="U8"),
        data=W.data,
        indices=W.indices,
        indptr=W.indptr,
        shape=np.array(W.shape),
        b=head["b"],
        stats=json.dumps(head["stats"]),
    )


def _load_head(path: Path) -> dict:
    z = np.load(path, allow_pickle=False)
    W = sp.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"]))
    return {"classes": z["classes"].astype(object), "W": W, "b": z["b"], "stats": json.loads(str(z["stats"]))}


def fit_ncm_heads(
    X,
    y_ncm: np.ndarray,
    sw: np.ndarray | None,
    ckpt_dir: Path | None,
    budget_s: float | None = None,
    C: float = 1.0,
    tol: float = 1e-3,
    prune_kw: dict | None = None,
) -> tuple[dict[str, LinearHead], dict[str, str], dict] | None:
    prune_kw = {**PRUNE_DEFAULTS, **(prune_kw or {})}
    y_cap = chapter_of(y_ncm)
    chapters = np.unique(y_cap)
    budget = Budget(budget_s)
    sub: dict[str, LinearHead] = {}
    single: dict[str, str] = {}
    stats: dict[str, dict] = {}
    # largest chapters first: if the budget ends, the expensive work is already checkpointed
    sizes = {c: int((y_cap == c).sum()) for c in chapters}
    for cap in sorted(chapters, key=lambda c: -sizes[c]):
        rows = np.flatnonzero(y_cap == cap)
        classes = np.unique(y_ncm[rows])
        if len(classes) == 1:
            single[cap] = str(classes[0])
            continue
        path = ckpt_dir / f"ncm_{cap}.npz" if ckpt_dir else None
        if path and path.exists():
            head = _load_head(path)
        else:
            if budget.exhausted():
                log.info("ncm: orcamento esgotado, %d/%d capitulos prontos", len(sub), len(chapters) - len(single))
                return None
            head = _fit_ncm_head(X, rows, y_ncm[rows], sw, C, tol, prune_kw)
            if path:
                _save_head(path, head)
            s = head["stats"]
            log.info(
                "ncm %s: %d classes, %d linhas, %.0fs, poda %.1f%% retida, concordancia %.3f",
                cap,
                s["classes"],
                s["rows"],
                s["seconds"],
                100 * s["coef_pruned"] / s["coef_dense"],
                s["agreement_pruned_vs_dense"],
            )
        sub[cap] = LinearHead(head["classes"], head["W"], head["b"])
        stats[cap] = head["stats"]
    dense = sum(s["coef_dense"] for s in stats.values())
    pruned = sum(s["coef_pruned"] for s in stats.values())
    rows_total = sum(s["rows"] for s in stats.values())
    summary = {
        "poda_pct_retida": round(100.0 * pruned / dense, 2) if dense else None,
        "poda_concordancia_ponderada": round(
            sum(s["agreement_pruned_vs_dense"] * s["rows"] for s in stats.values()) / rows_total, 4
        )
        if rows_total
        else None,
        "segundos_ncm": round(sum(s["seconds"] for s in stats.values()), 1),
        "por_capitulo": stats,
    }
    return sub, single, summary


def fit_hierarchical(
    X, y_ncm: np.ndarray, sw: np.ndarray | None = None, C: float = 1.0, prune_kw: dict | None = None
) -> HierarchicalLinearNCM:
    """In-memory, no checkpoints: used by tests and by small experiments."""
    y_cap = chapter_of(y_ncm)
    chapter = fit_chapter_head(X, y_cap, sw, None, None, C)
    sub, single, summary = fit_ncm_heads(X, y_ncm, sw, None, None, C, prune_kw=prune_kw)
    return HierarchicalLinearNCM(chapter=chapter, sub=sub, single=single, meta={"poda": summary["poda_pct_retida"]})
