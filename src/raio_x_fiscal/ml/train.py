"""Train the baselines, evaluate them honestly, write models and the results report.

Evaluation subsets of the test month (all numbers are reported, none is hidden):
- `todos`:            every item of the test month (the number a deployed system would show);
- `unicos`:           one row per distinct normalised description (removes repetition);
- `nao_vistos`:       items whose description never appeared in training (true generalisation);
- `nao_vistos_unicos`: the above, one row per distinct description (the headline number).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd

from raio_x_fiscal.config import ROOT, Paths, connect
from raio_x_fiscal.ml.evaluate import (
    classification_metrics,
    confidence_table,
    confusion_pairs,
    measure_latency,
    per_class_report,
    pick_threshold,
)
from raio_x_fiscal.ml.features import TextFeaturizer
from raio_x_fiscal.ml.models import (
    HierarchicalLinearNCM,
    LookupBaseline,
    MajorityBaseline,
    chapter_of,
    hybrid_topk,
)

log = logging.getLogger(__name__)

ML_REPORT = ROOT / "reports" / "ml_results.md"
K = 5
AUDIT_TARGET_PRECISION = 0.95
CONFIDENCE_EDGES = [0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.01]


def _subsets(df: pd.DataFrame) -> dict[str, np.ndarray]:
    first = ~df["descricao_normalizada"].duplicated().to_numpy()
    unseen = ~df["seen_in_train"].to_numpy()
    return {
        "todos": np.arange(len(df)),
        "unicos": np.flatnonzero(first),
        "nao_vistos": np.flatnonzero(unseen),
        "nao_vistos_unicos": np.flatnonzero(first & unseen),
    }


def _names(paths: Paths) -> tuple[dict[str, str], dict[str, str]]:
    with connect(paths.gold_db, read_only=True) as con:
        ncm = dict(con.execute("SELECT ncm_codigo, ncm_descricao FROM dim_ncm").fetchall())
        cap = dict(con.execute("SELECT capitulo, descricao_capitulo FROM dim_capitulo").fetchall())
    return ncm, cap


def train_and_evaluate(paths: Paths, sample: int | None = None) -> dict:
    paths.ensure()
    t_start = time.perf_counter()
    train = pd.read_parquet(paths.ml / "train.parquet")
    valid = pd.read_parquet(paths.ml / "valid.parquet")
    test = pd.read_parquet(paths.ml / "test.parquet")
    if sample:
        train = train.sample(min(sample, len(train)), random_state=0).reset_index(drop=True)
        valid = valid.sample(min(sample, len(valid)), random_state=0).reset_index(drop=True)
        test = test.sample(min(sample, len(test)), random_state=0).reset_index(drop=True)
    ncm_names, cap_names = _names(paths)
    log.info("treino %d descricoes unicas | validacao %d | teste %d", len(train), len(valid), len(test))

    # ------------------------------------------------------------------ fit
    feat = TextFeaturizer()
    t0 = time.perf_counter()
    X_train = feat.fit_transform(train["descricao_normalizada"].tolist())
    y_train = train["ncm_codigo"].to_numpy(dtype=object)
    weights = np.log1p(train["n_itens"].to_numpy(dtype=float))
    feat_seconds = time.perf_counter() - t0
    log.info("features: %d dims, %d nnz em %.0fs", feat.n_features, X_train.nnz, feat_seconds)

    majority = MajorityBaseline().fit(y_train)
    lookup = LookupBaseline().fit(train["descricao_normalizada"].to_numpy(), y_train)
    model = HierarchicalLinearNCM().fit(X_train, y_train, sample_weight=weights)
    del X_train

    # ------------------------------------------------------------------ calibrate on validation
    X_valid = feat.transform(valid["descricao_normalizada"].tolist())
    y_valid = valid["ncm_codigo"].to_numpy(dtype=object)
    temps = model.calibrate(X_valid, y_valid)
    pv = model.predict_topk(X_valid, K)
    valid_correct = pv["ncm_topk"][:, 0] == y_valid
    calib = confidence_table(pv["ncm_prob"][:, 0], valid_correct, CONFIDENCE_EDGES)
    threshold = pick_threshold(pv["ncm_prob"][:, 0], valid_correct, AUDIT_TARGET_PRECISION, np.arange(0.5, 1.0, 0.01))
    valid_metrics = {
        name: classification_metrics(y_valid[idx], pv["ncm_topk"][idx]) for name, idx in _subsets(valid).items()
    }
    del X_valid, pv

    # ------------------------------------------------------------------ evaluate on test
    X_test = feat.transform(test["descricao_normalizada"].tolist())
    y_test = test["ncm_codigo"].to_numpy(dtype=object)
    y_test_cap = chapter_of(y_test)
    t0 = time.perf_counter()
    pt = model.predict_topk(X_test, K)
    predict_seconds = time.perf_counter() - t0
    lk = lookup.predict(test["descricao_normalizada"].to_numpy())
    preds = {
        "majoritario": {"ncm": majority.predict_topk(len(test), K)},
        "lookup_exato": {"ncm": hybrid_topk(lk, majority.predict_topk(len(test), K))},
        "tfidf_svm_hierarquico": {"ncm": pt["ncm_topk"], "cap": pt["capitulo_topk"]},
        "hibrido_lookup_depois_svm": {"ncm": hybrid_topk(lk, pt["ncm_topk"])},
    }
    for name in ("majoritario", "lookup_exato", "hibrido_lookup_depois_svm"):
        preds[name]["cap"] = np.vectorize(lambda c: c[:2])(preds[name]["ncm"])

    subsets = _subsets(test)
    results: dict[str, dict] = {}
    for mname, p in preds.items():
        results[mname] = {}
        for sname, idx in subsets.items():
            results[mname][sname] = {
                "ncm": classification_metrics(y_test[idx], p["ncm"][idx]),
                "capitulo": classification_metrics(y_test_cap[idx], p["cap"][idx]),
            }

    idx = subsets["nao_vistos_unicos"]
    cap_pred = pt["capitulo_topk"][idx, 0]
    chapter_report = per_class_report(y_test_cap[idx], cap_pred, cap_names)
    chapter_confusions = confusion_pairs(y_test_cap[idx], cap_pred, 12)
    ncm_confusions = confusion_pairs(y_test[idx], pt["ncm_topk"][idx, 0], 12)
    errors = _error_examples(test, pt, y_test, idx, ncm_names, n=25)
    latency = measure_latency(lambda X: model.predict_topk(X, K), X_test, n_single=200, batch=2000)

    # ------------------------------------------------------------------ persist
    joblib.dump(feat, paths.models / "featurizer.joblib", compress=3)
    joblib.dump(model, paths.models / "hier_svm.joblib", compress=3)
    joblib.dump(lookup, paths.models / "lookup.joblib", compress=3)
    joblib.dump(majority, paths.models / "majority.joblib", compress=3)
    splits = json.loads((paths.ml / "splits.json").read_text())
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sample": sample,
        "splits": splits,
        "features": {
            "n_features": feat.n_features,
            "word_vocab": len(feat.word.vocabulary_),
            "char_vocab": len(feat.char.vocabulary_),
            "fit_seconds": round(feat_seconds, 1),
        },
        "model": model.describe(),
        "temperatures": temps,
        "audit": {"target_precision": AUDIT_TARGET_PRECISION, "threshold": threshold},
        "valid_metrics_svm": valid_metrics,
        "test_results": results,
        "latency": latency,
        "predict_seconds_test": round(predict_seconds, 1),
        "total_seconds": round(time.perf_counter() - t_start, 1),
        "model_bytes": sum(p.stat().st_size for p in paths.models.glob("*.joblib")),
    }
    (paths.models / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=str))
    calib.to_csv(paths.ml / "calibration_valid.csv", index=False)
    chapter_report.to_csv(paths.ml / "chapter_report_test.csv", index=False)
    errors.to_csv(paths.ml / "error_examples_test.csv", index=False)
    _write_report(metadata, calib, chapter_report, chapter_confusions, ncm_confusions, errors, cap_names, ncm_names)
    log.info("treino + avaliacao em %.0fs; relatorio em %s", metadata["total_seconds"], ML_REPORT)
    return {k: metadata[k] for k in ("model", "temperatures", "audit", "latency", "total_seconds")} | {
        "headline": results["tfidf_svm_hierarquico"]
    }


def _error_examples(test, pt, y_test, idx, ncm_names, n: int) -> pd.DataFrame:
    wrong = idx[pt["ncm_topk"][idx, 0] != y_test[idx]]
    rng = np.random.default_rng(0)
    pick = rng.choice(wrong, size=min(n, len(wrong)), replace=False) if len(wrong) else wrong
    rows = []
    for i in pick:
        rows.append(
            {
                "descricao": test["descricao_produto"].iat[i],
                "ncm_declarado": y_test[i],
                "ncm_declarado_desc": ncm_names.get(y_test[i]) or "",
                "ncm_previsto": pt["ncm_topk"][i, 0],
                "ncm_previsto_desc": ncm_names.get(pt["ncm_topk"][i, 0]) or "",
                "confianca": round(float(pt["ncm_prob"][i, 0]), 3),
                "declarado_no_top5": bool((pt["ncm_topk"][i] == y_test[i]).any()),
                "mesmo_capitulo": y_test[i][:2] == pt["ncm_topk"][i, 0][:2],
            }
        )
    return pd.DataFrame(rows).sort_values("confianca", ascending=False).reset_index(drop=True)


def _fmt(x: float) -> str:
    return f"{100 * x:.1f}%"


def _write_report(
    meta, calib, chapter_report, chapter_confusions, ncm_confusions, errors, cap_names, ncm_names
) -> None:
    r = meta["test_results"]
    s = meta["splits"]
    L = []
    L.append("# Resultados do baseline: descricao -> NCM")
    L.append("")
    L.append(
        f"Gerado em {meta['generated_at']}. Treino: {', '.join(s['train_months'])}. "
        f"Validacao (calibracao): {s['valid_month']}. Teste: {s['test_month']}."
        + (f" **Amostra de {meta['sample']} linhas (depuracao).**" if meta["sample"] else "")
    )
    L.append("")
    L.append("## Dados")
    L.append("")
    tr, te = s["train"], s["test"]
    L.append(
        f"- Treino: **{tr['descricoes_unicas']:,}** descricoes unicas (de {tr['itens_originais']:,} itens), "
        f"{tr['ncm_distintos']:,} NCMs, {tr['capitulos_distintos']} capitulos.".replace(",", ".")
    )
    L.append(
        f"- Ruido de rotulo no treino: {tr['pct_descricoes_com_mais_de_um_ncm']}% das descricoes aparecem "
        f"com mais de um NCM, e elas concentram {tr['pct_itens_com_descricao_ambigua']}% dos itens "
        f"(pureza media do rotulo {tr['pureza_media_do_rotulo']})."
    )
    L.append(
        f"- Teste: **{te['itens']:,}** itens, {te['descricoes_unicas']:,} descricoes unicas; "
        f"{te['pct_itens_vistos']}% dos itens tem descricao identica a alguma do treino e "
        f"{te['descricoes_unicas_nao_vistas']:,} descricoes unicas nunca foram vistas.".replace(",", ".")
    )
    L.append(
        f"- Entre os itens vistos, a mesma descricao recebeu o mesmo NCM do treino em "
        f"{te['pct_vistos_em_que_lookup_acerta']}% dos casos "
        "(o resto e inconsistencia de classificacao entre fornecedores, nao erro do modelo)."
    )
    L.append("")
    L.append("## Tabela principal (mes de teste)")
    L.append("")
    L.append(
        "Top-1 / Top-5 / F1 macro / F1 ponderado. `todos` = como em producao (com repeticao); "
        "`nao_vistos_unicos` = descricoes nunca vistas, sem repeticao (numero honesto de generalizacao)."
    )
    L.append("")
    for task, label in (
        ("capitulo", "Capitulo (2 digitos, 96 classes)"),
        ("ncm", "NCM completo (8 digitos)"),
    ):
        L.append(f"### {label}")
        L.append("")
        L.append("| Modelo | Subconjunto | n | Top-1 | Top-5 | F1 macro | F1 pond. |")
        L.append("|---|---|---:|---:|---:|---:|---:|")
        for mname, subs in r.items():
            for sname, m in subs.items():
                mm = m[task]
                L.append(
                    f"| {mname} | {sname} | {mm['n']:,} | {_fmt(mm['top1'])} | {_fmt(mm['top5'])} | "
                    f"{_fmt(mm['f1_macro'])} | {_fmt(mm['f1_weighted'])} |".replace(",", ".")
                )
        L.append("")
    L.append("## Modelo e custo")
    L.append("")
    md, ft, lat = meta["model"], meta["features"], meta["latency"]
    L.append(
        f"- Features: TF-IDF palavra (1-2 gramas, {ft['word_vocab']:,} termos) + "
        f"caractere (3-5, {ft['char_vocab']:,} termos) "
        f"= {ft['n_features']:,} dimensoes, float32, ajustadas em {ft['fit_seconds']}s.".replace(",", ".")
    )
    L.append(
        f"- Modelo: LinearSVC do capitulo ({md['capitulos']} classes) + {md['sub_modelos']} LinearSVC por capitulo "
        f"({md['ncm_classes']:,} NCMs no total, {md['coeficientes']:,} coeficientes float32). "
        f"Treino: {md['fit_seconds']}.".replace(",", ".")
    )
    L.append(
        f"- Calibracao por temperatura no mes de validacao: T_capitulo = {md['t_chapter']:.3f}, "
        f"T_ncm = {md['t_ncm']:.3f}."
    )
    L.append(
        f"- Latencia de inferencia (CPU, 2 nucleos, inclui vetorizacao ja feita): "
        f"item unico p50 {lat['single_p50_ms']} ms, "
        f"p95 {lat['single_p95_ms']} ms; em lote de {lat['batch_size']}: {lat['batch_ms_per_item']} ms/item. "
        f"Mes de teste inteiro previsto em {meta['predict_seconds_test']}s."
    )
    L.append(f"- Artefatos em `models/` ({meta['model_bytes'] / 1e6:.0f} MB, fora do git).")
    L.append("")
    L.append("## Calibracao (mes de validacao) e limiar da auditoria")
    L.append("")
    L.append(
        "Acuracia do top-1 por faixa de confianca P(ncm) e precisao acumulada acima de cada faixa. "
        f"Limiar escolhido para a auditoria (precisao >= {int(100 * meta['audit']['target_precision'])}%): "
        f"**{meta['audit']['threshold']}**."
    )
    L.append("")
    L.append("| Faixa | n | Acuracia na faixa | n acima | Precisao acima |")
    L.append("|---|---:|---:|---:|---:|")
    for _, row in calib.iterrows():
        L.append(
            f"| {row['faixa']} | {row['n']:,} | {row['acuracia_na_faixa']} | {row['n_acima']:,} | "
            f"{row['precisao_acima']} |".replace(",", ".")
        )
    L.append("")
    L.append("## Por capitulo (descricoes nao vistas, unicas; 20 maiores)")
    L.append("")
    L.append("| Capitulo | Descricao | Precisao | Recall | F1 | Suporte |")
    L.append("|---|---|---:|---:|---:|---:|")
    for _, row in chapter_report.head(20).iterrows():
        L.append(
            f"| {row['classe']} | {row['nome'][:60]} | {row['precisao']} | {row['recall']} | {row['f1']} | "
            f"{row['suporte']:,} |".replace(",", ".")
        )
    L.append("")
    L.append("## Capitulos mais confundidos (verdadeiro -> previsto)")
    L.append("")
    L.append("| Verdadeiro | Previsto | n |")
    L.append("|---|---|---:|")
    for t, p, c in chapter_confusions:
        L.append(f"| {t} {(cap_names.get(t) or '')[:40]} | {p} {(cap_names.get(p) or '')[:40]} | {c} |")
    L.append("")
    L.append("## NCMs mais confundidos (verdadeiro -> previsto)")
    L.append("")
    L.append("| Verdadeiro | Previsto | n |")
    L.append("|---|---|---:|")
    for t, p, c in ncm_confusions:
        L.append(f"| {t} {(ncm_names.get(t) or '')[:45]} | {p} {(ncm_names.get(p) or '')[:45]} | {c} |")
    L.append("")
    L.append("## Exemplos de erro (descricoes nao vistas, ordenados por confianca)")
    L.append("")
    L.append("| Descricao | NCM declarado | NCM previsto | Conf. | Declarado no top-5 | Mesmo cap. |")
    L.append("|---|---|---|---:|---|---|")
    for _, e in errors.iterrows():
        L.append(
            f"| {str(e['descricao'])[:70]} | {e['ncm_declarado']} {str(e['ncm_declarado_desc'])[:40]} | "
            f"{e['ncm_previsto']} {str(e['ncm_previsto_desc'])[:40]} | {e['confianca']} | "
            f"{'sim' if e['declarado_no_top5'] else 'nao'} | {'sim' if e['mesmo_capitulo'] else 'nao'} |"
        )
    L.append("")
    ML_REPORT.parent.mkdir(parents=True, exist_ok=True)
    ML_REPORT.write_text("\n".join(L))
