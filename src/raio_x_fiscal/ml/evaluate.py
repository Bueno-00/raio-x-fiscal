"""Metrics, confusion pairs and latency measurement (framework-free, numpy + sklearn)."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score


def topk_accuracy(y_true: np.ndarray, topk: np.ndarray) -> float:
    hits = (topk == y_true[:, None]).any(axis=1)
    return float(hits.mean()) if len(y_true) else float("nan")


def classification_metrics(y_true: np.ndarray, topk: np.ndarray) -> dict[str, float]:
    """top-1, top-k, macro and weighted F1 for one evaluation subset."""
    y_pred = topk[:, 0]
    return {
        "n": int(len(y_true)),
        "top1": round(topk_accuracy(y_true, topk[:, :1]), 4),
        f"top{topk.shape[1]}": round(topk_accuracy(y_true, topk), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_weighted": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
    }


def per_class_report(y_true: np.ndarray, y_pred: np.ndarray, names: dict[str, str] | None = None) -> pd.DataFrame:
    """Precision / recall / F1 / support per class, sorted by support."""
    classes = np.unique(np.concatenate([y_true, y_pred]))
    rows = []
    for c in classes:
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        support = tp + fn
        if support == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / support
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        rows.append(
            {
                "classe": c,
                "nome": (names or {}).get(c) or "",
                "precisao": round(p, 3),
                "recall": round(r, 3),
                "f1": round(f1, 3),
                "suporte": support,
            }
        )
    return pd.DataFrame(rows).sort_values("suporte", ascending=False).reset_index(drop=True)


def confusion_pairs(y_true: np.ndarray, y_pred: np.ndarray, n: int = 10) -> list[tuple[str, str, int]]:
    """Most frequent (true, predicted) pairs among errors."""
    wrong = y_true != y_pred
    pairs = Counter(zip(y_true[wrong], y_pred[wrong], strict=True))
    return [(t, p, c) for (t, p), c in pairs.most_common(n)]


def measure_latency(predict: Callable, X, n_single: int = 200, batch: int = 1000) -> dict[str, float]:
    """Wall-clock latency of `predict` (ms): single-item p50/p95 and amortised per item in batch."""
    n_single = min(n_single, X.shape[0])
    singles = []
    for i in range(n_single):
        t0 = time.perf_counter()
        predict(X[i])
        singles.append((time.perf_counter() - t0) * 1000)
    b = min(batch, X.shape[0])
    t0 = time.perf_counter()
    predict(X[:b])
    per_item = (time.perf_counter() - t0) * 1000 / b
    return {
        "single_p50_ms": round(float(np.percentile(singles, 50)), 2),
        "single_p95_ms": round(float(np.percentile(singles, 95)), 2),
        "batch_ms_per_item": round(per_item, 4),
        "batch_size": b,
    }


def confidence_table(prob: np.ndarray, correct: np.ndarray, edges: list[float]) -> pd.DataFrame:
    """Accuracy by confidence bucket (calibration view) plus cumulative precision above each edge."""
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (prob >= lo) & (prob < hi)
        above = prob >= lo
        rows.append(
            {
                "faixa": f"[{lo:.2f}, {hi:.2f})",
                "n": int(m.sum()),
                "acuracia_na_faixa": round(float(correct[m].mean()), 4) if m.any() else None,
                "n_acima": int(above.sum()),
                "precisao_acima": round(float(correct[above].mean()), 4) if above.any() else None,
            }
        )
    return pd.DataFrame(rows)


def pick_threshold(prob: np.ndarray, correct: np.ndarray, target_precision: float, grid: np.ndarray) -> float | None:
    """Smallest threshold whose cumulative precision (prob >= t) reaches the target."""
    for t in grid:
        m = prob >= t
        if m.sum() >= 100 and correct[m].mean() >= target_precision:
            return float(t)
    return None


def best_precision_threshold(
    prob: np.ndarray, correct: np.ndarray, grid: np.ndarray, min_support: int = 1000
) -> tuple[float, float] | None:
    """Threshold with the highest cumulative precision among those keeping at least `min_support` items.

    Fallback for when the target is out of reach. Here "precision" is agreement with the declared
    NCM, and the declared NCM is itself noisy (identical descriptions get different codes from
    different suppliers), so the attainable agreement has a ceiling below 100% that no model removes.
    """
    best = None
    for t in grid:
        m = prob >= t
        if m.sum() < min_support:
            continue
        p = float(correct[m].mean())
        if best is None or p > best[1]:
            best = (float(t), p)
    return best
