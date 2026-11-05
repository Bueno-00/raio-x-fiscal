"""ML tests on synthetic data: leak-free split, hierarchical model, calibration, inference."""

import duckdb
import joblib
import numpy as np
import pandas as pd
import pytest

from raio_x_fiscal.config import Paths
from raio_x_fiscal.ml import dataset
from raio_x_fiscal.ml.evaluate import (
    best_precision_threshold,
    classification_metrics,
    confusion_pairs,
    pick_threshold,
    topk_accuracy,
)
from raio_x_fiscal.ml.features import TextFeaturizer
from raio_x_fiscal.ml.fit import fit_chapter_head, fit_hierarchical, prune
from raio_x_fiscal.ml.models import LookupBaseline, MajorityBaseline, chapter_of, hybrid_topk, softmax
from raio_x_fiscal.ml.predict import NcmPredictor

# Three chapters, five NCMs, templated descriptions with variation.
TEMPLATES = {
    "10063021": ["arroz tipo {n} {m}", "arroz branco {m} pacote {n}kg", "arroz agulhinha tipo {n}"],
    "07133399": ["feijao tipo {n} {m}", "feijao carioca {m} {n}kg", "feijao preto pacote {n}kg"],
    "96081000": ["caneta esferografica {m} azul", "caneta {m} ponta fina {n}", "caneta azul {m} caixa {n}"],
    "96091000": ["lapis preto {m} n {n}", "lapis grafite {m} caixa {n}", "lapis hb {m}"],
    "22011000": ["agua mineral {n}l {m}", "agua mineral sem gas {m} {n}ml", "agua {m} garrafao {n} litros"],
}
MARCAS = [
    "tio joao",
    "camil",
    "bic",
    "faber",
    "crystal",
    "minalba",
    "kicaldo",
    "prata",
    "compactor",
    "indaia",
]


def synthetic(n_per_class: int = 40, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for ncm, temps in TEMPLATES.items():
        for i in range(n_per_class):
            t = temps[i % len(temps)]
            rows.append(
                {
                    "descricao_normalizada": t.format(
                        n=int(rng.integers(1, 20)), m=MARCAS[int(rng.integers(0, len(MARCAS)))]
                    ),
                    "ncm_codigo": ncm,
                }
            )
    df = pd.DataFrame(rows).drop_duplicates("descricao_normalizada").reset_index(drop=True)
    df["n_itens"] = rng.integers(1, 50, size=len(df))
    return df


@pytest.fixture(scope="module")
def trained():
    train = synthetic(40, seed=0)
    feat = TextFeaturizer(word_min_df=1, char_min_df=1)
    X = feat.fit_transform(train["descricao_normalizada"].tolist())
    y = train["ncm_codigo"].to_numpy(dtype=object)
    model = fit_hierarchical(X, y, sw=np.log1p(train["n_itens"].to_numpy(np.float32)))
    valid = synthetic(15, seed=1)
    model.calibrate(feat.transform(valid["descricao_normalizada"].tolist()), valid["ncm_codigo"].to_numpy(dtype=object))
    lookup = LookupBaseline().fit(train["descricao_normalizada"].to_numpy(), y)
    return feat, model, lookup, train


def test_hierarchical_model_learns_and_ranks(trained):
    feat, model, _, train = trained
    test = synthetic(10, seed=7)
    X = feat.transform(test["descricao_normalizada"].tolist())
    y = test["ncm_codigo"].to_numpy(dtype=object)
    out = model.predict_topk(X, k=3)
    assert out["ncm_topk"].shape == (len(test), 3) and out["ncm_prob"].shape == (len(test), 3)
    assert topk_accuracy(y, out["ncm_topk"][:, :1]) > 0.9
    assert topk_accuracy(y, out["ncm_topk"]) >= topk_accuracy(y, out["ncm_topk"][:, :1])
    # probabilities are a proper joint distribution slice: sorted desc, in (0, 1], summing to <= 1
    assert np.all(np.diff(out["ncm_prob"], axis=1) <= 1e-6)
    assert np.all(out["ncm_prob"] > 0) and np.all(out["ncm_prob"].sum(axis=1) <= 1.0 + 1e-5)
    assert set(out["capitulo_topk"][:, 0]) <= {"10", "07", "96", "22"}
    desc = model.describe()
    assert desc["capitulos"] == 4 and desc["ncm_classes"] == 5
    assert desc["sub_modelos"] == 1 and desc["capitulos_com_um_ncm"] == 3  # only chapter 96 has 2 NCMs


def test_softmax_and_temperature():
    s = np.array([[2.0, 1.0, 0.0]])
    p = softmax(s)
    assert np.isclose(p.sum(), 1.0) and p[0, 0] > p[0, 1] > p[0, 2]
    assert softmax(s, temperature=100.0)[0, 0] < p[0, 0]  # higher T flattens


def test_baselines_and_hybrid():
    y = np.array(["a", "a", "b", "c"], dtype=object)
    maj = MajorityBaseline().fit(y)
    top = maj.predict_topk(2, k=2)
    assert top.tolist() == [["a", "b"], ["a", "b"]] or top[0, 0] == "a"
    lk = LookupBaseline().fit(np.array(["x", "y"], dtype=object), np.array(["a", "b"], dtype=object))
    hits = lk.predict(np.array(["y", "zzz"], dtype=object))
    assert hits.tolist() == ["b", None]
    model_topk = np.array([["a", "b", "c"], ["a", "b", "c"]], dtype=object)
    merged = hybrid_topk(hits, model_topk)
    assert merged[0].tolist() == ["b", "a", "c"]  # lookup first, no duplicate
    assert merged[1].tolist() == ["a", "b", "c"]  # unseen -> model ranking untouched


def test_metrics_helpers():
    y = np.array(["a", "b", "a", "c"], dtype=object)
    topk = np.array([["a", "b"], ["c", "b"], ["b", "a"], ["c", "a"]], dtype=object)
    m = classification_metrics(y, topk)
    assert m["top1"] == 0.5 and m["top2"] == 1.0 and 0 < m["f1_macro"] <= 1
    assert confusion_pairs(y, topk[:, 0])[0] == ("b", "c", 1) or confusion_pairs(y, topk[:, 0])[0] == (
        "a",
        "b",
        1,
    )
    prob = np.array([0.99, 0.98, 0.6, 0.55] * 50)
    correct = np.array([True, True, False, False] * 50)
    assert pick_threshold(prob, correct, 0.95, np.arange(0.5, 1.0, 0.01)) == pytest.approx(0.61, abs=0.011)
    assert pick_threshold(prob, correct, 0.999, np.arange(0.5, 0.6, 0.01)) is None


def test_best_precision_threshold_respects_support():
    # Precision rises with the threshold, but only 50 items sit above 0.9: too few to trust.
    prob = np.concatenate([np.full(1000, 0.6), np.full(1000, 0.8), np.full(50, 0.95)])
    correct = np.concatenate([np.zeros(1000, bool), np.r_[np.ones(900, bool), np.zeros(100, bool)], np.ones(50, bool)])
    t, p = best_precision_threshold(prob, correct, np.arange(0.5, 1.0, 0.1), min_support=500)
    assert t == pytest.approx(0.7)
    assert p == pytest.approx(950 / 1050)
    assert best_precision_threshold(prob, correct, np.arange(0.5, 1.0, 0.1), min_support=10_000) is None


def test_predictor_roundtrip(trained, tmp_path):
    feat, model, lookup, _ = trained
    joblib.dump(feat, tmp_path / "featurizer.joblib")
    joblib.dump(model, tmp_path / "hier_svm.joblib")
    joblib.dump(lookup, tmp_path / "lookup.joblib")
    pred = NcmPredictor.load(tmp_path).predict(["ARROZ TIPO 1 TIO JOÃO", "Caneta Esferográfica BIC Azul"], k=2)
    assert pred[0].descricao_normalizada == "arroz tipo 1 tio joao"  # same normalisation as silver
    assert pred[0].ncm_topk[0] == "10063021"
    assert pred[1].ncm_topk[0] == "96081000"
    d = pred[0].as_dict()
    assert set(d) >= {"ncm_top1", "confianca", "top_k", "capitulo_top1"} and len(d["top_k"]) == 2


def test_split_months_rules():
    months = ["202504", "202505", "202506", "202507"]
    assert dataset.split_months(months, "202506", "202507") == ["202504", "202505"]
    with pytest.raises(ValueError):
        dataset.split_months(months, "202504", "202507")
    with pytest.raises(ValueError):
        dataset.split_months(months, "202507", "202506")


def test_build_splits_has_no_description_leak(tmp_path):
    """Train collapses to one row per description with the majority label; test rows are flagged."""
    paths = Paths(data=tmp_path / "data", models=tmp_path / "models")
    paths.ensure()
    for m in ("202501", "202502", "202503"):
        (paths.silver / "item" / f"mes={m}").mkdir(parents=True)
    con = duckdb.connect(str(paths.gold_db))
    rows = []
    # 'arroz' seen in Jan twice as 10063021 and once as 10063011 -> majority 10063021
    rows += [("2025-01", "ARROZ", "arroz", "10063021")] * 2 + [("2025-01", "ARROZ", "arroz", "10063011")]
    rows += [("2025-01", "FEIJAO", "feijao", "07133399"), ("2025-02", "CANETA", "caneta", "96081000")]
    rows += [("2025-03", "ARROZ", "arroz", "10063021"), ("2025-03", "AGUA", "agua", "22011000")]
    con.execute(
        "CREATE TABLE ml_ncm_items AS SELECT row_number() OVER () AS item_id, * FROM (SELECT * FROM (VALUES "
        + ", ".join(
            f"('{a}', '{b}', '{c}', '{d}', substr('{d}', 1, 2), 'x', '5102', 'UN', 1, 1, 1, "
            "'SP', 'SP', DATE '2025-01-01')"
            for a, b, c, d in rows
        )
        + ") t(mes_referencia, descricao_produto, descricao_normalizada, ncm_codigo, capitulo, ncm_descricao, "
        "cfop, unidade, quantidade, valor_unitario, valor_total, emitente_uf, destinatario_uf, data_emissao))"
    )
    con.close()
    stats = dataset.build_splits(paths, test_month="202503", valid_month="202502")
    train = pd.read_parquet(paths.ml / "train.parquet")
    test = pd.read_parquet(paths.ml / "test.parquet")
    assert stats["train_months"] == ["2025-01"] and stats["valid_month"] == "2025-02"
    assert train["descricao_normalizada"].is_unique
    arroz = train.set_index("descricao_normalizada").loc["arroz"]
    assert arroz["ncm_codigo"] == "10063021" and arroz["n_itens"] == 3 and arroz["n_ncm_distintos"] == 2
    assert stats["train"]["descricoes_com_mais_de_um_ncm"] == 1
    seen = dict(zip(test["descricao_normalizada"], test["seen_in_train"], strict=True))
    assert seen == {"arroz": True, "agua": False}
    unseen = set(test.loc[~test["seen_in_train"], "descricao_normalizada"])
    assert not (unseen & set(train["descricao_normalizada"]))


def test_prune_keeps_strong_weights_and_shape():
    W = np.array([[1.0, 0.001, -0.5, 0.0], [0.0, 0.0, 0.0, 2.0]], dtype=np.float32)
    P = prune(W, rel=0.1, abs_min=1e-3, cap=10)
    assert P.shape == W.shape and P.nnz == 3
    assert P.toarray()[0].tolist() == [1.0, 0.0, -0.5, 0.0]
    capped = prune(np.ones((1, 50), dtype=np.float32), rel=0.0, abs_min=0.0, cap=7)
    assert capped.nnz == 7


def test_chapter_head_checkpoints_and_resumes(tmp_path):
    train = synthetic(20, seed=3)
    feat = TextFeaturizer(word_min_df=1, char_min_df=1)
    X = feat.fit_transform(train["descricao_normalizada"].tolist())
    y_cap = chapter_of(train["ncm_codigo"].to_numpy(dtype=object))
    # a negative budget fits nothing and reports "not done"; checkpoints from a full run are reused
    assert fit_chapter_head(X, y_cap, None, tmp_path, budget_s=-1) is None
    head = fit_chapter_head(X, y_cap, None, tmp_path)
    assert head is not None
    assert sorted(p.name for p in tmp_path.glob("cap_*.npz")) == [f"cap_{c}.npz" for c in sorted(set(y_cap))]
    again = fit_chapter_head(X, y_cap, None, tmp_path, budget_s=-1)  # all cached: budget irrelevant
    assert again is not None and np.allclose(again.W, head.W)
    scores = head.decision(X)
    assert scores.shape == (X.shape[0], len(head.classes)) and scores.dtype == np.float32
