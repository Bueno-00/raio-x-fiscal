"""NCM audit: items whose declared NCM disagrees with a confident prediction become alerts.

Business use: a wrong NCM means wrong tax (IPI, PIS/COFINS, ICMS-ST all key off the NCM) and,
in a marketplace, a wrong catalogue category. The model does not decide; it ranks what a
human should look at first. The threshold comes from the validation month (precision target),
and a random sample of alerts is dumped for manual inspection, whose verdicts are written to
`reports/ncm_audit_inspection.md` by hand (that file states how many alerts looked like real
declaration errors versus model errors).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from raio_x_fiscal.config import ROOT, Paths, connect
from raio_x_fiscal.ml.predict import NcmPredictor

log = logging.getLogger(__name__)

AUDIT_REPORT = ROOT / "reports" / "ncm_audit.md"
CHUNK = 50_000


def run_audit(paths: Paths, sample_size: int = 40, threshold: float | None = None) -> dict:
    paths.ensure()
    meta = json.loads((paths.models / "metadata.json").read_text())
    thr = threshold if threshold is not None else meta["audit"]["threshold"]
    if thr is None:
        raise RuntimeError("limiar da auditoria nao definido: a calibracao nao atingiu a precisao alvo")
    predictor = NcmPredictor.load(paths.models)
    test = pd.read_parquet(paths.ml / "test.parquet")
    with connect(paths.gold_db, read_only=True) as con:
        ncm_names = dict(con.execute("SELECT ncm_codigo, ncm_descricao FROM dim_ncm").fetchall())

    # Predict in chunks (the whole month at once would hold two large sparse matrices).
    top1, prob, cap1 = [], [], []
    norm = test["descricao_normalizada"].tolist()
    for start in range(0, len(norm), CHUNK):
        X = predictor.featurizer.transform(norm[start : start + CHUNK])
        out = predictor.model.predict_topk(X, 1)
        top1.append(out["ncm_topk"][:, 0])
        prob.append(out["ncm_prob"][:, 0])
        cap1.append(out["capitulo_topk"][:, 0])
    test["ncm_previsto"] = np.concatenate(top1)
    test["confianca"] = np.concatenate(prob)
    test["capitulo_previsto"] = np.concatenate(cap1)
    test["diverge"] = test["ncm_previsto"] != test["ncm_codigo"]
    test["alerta"] = test["diverge"] & (test["confianca"] >= thr)
    test["mesmo_capitulo"] = test["ncm_previsto"].str[:2] == test["capitulo"]

    n = len(test)
    n_div = int(test["diverge"].sum())
    alerts = test[test["alerta"]].copy()
    n_alert = len(alerts)
    valor_alertas = float(alerts["valor_total"].sum())
    by_cap = (
        alerts.groupby("capitulo").agg(n=("item_id", "size"), valor=("valor_total", "sum"))
        .sort_values("n", ascending=False).head(15)
    )
    cross_chapter = int((~alerts["mesmo_capitulo"]).sum())
    uniq_desc_alerts = int(alerts["descricao_normalizada"].nunique())
    seen_alerts = int(alerts["seen_in_train"].sum())

    # Pairs (declared -> predicted) that repeat: systematic disagreement, the cheapest to review.
    pairs = (
        alerts.groupby(["ncm_codigo", "ncm_previsto"]).agg(n=("item_id", "size"), valor=("valor_total", "sum"),
                                                          exemplo=("descricao_produto", "first"))
        .sort_values("n", ascending=False).head(15).reset_index()
    )

    rng = np.random.default_rng(42)
    sample_idx = rng.choice(alerts.index.to_numpy(), size=min(sample_size, n_alert), replace=False)
    sample = alerts.loc[sample_idx, ["item_id", "descricao_produto", "ncm_codigo", "ncm_previsto", "confianca",
                                     "valor_total", "unidade", "seen_in_train"]].copy()
    sample["ncm_declarado_desc"] = sample["ncm_codigo"].map(lambda c: ncm_names.get(c) or "")
    sample["ncm_previsto_desc"] = sample["ncm_previsto"].map(lambda c: ncm_names.get(c) or "")
    sample = sample.sort_values("confianca", ascending=False).reset_index(drop=True)
    sample.insert(0, "n", range(1, len(sample) + 1))

    alerts_out = alerts[["item_id", "mes_referencia", "descricao_produto", "ncm_codigo", "ncm_previsto", "confianca",
                         "valor_total", "capitulo", "capitulo_previsto", "seen_in_train"]]
    alerts_out.to_parquet(paths.ml / "ncm_alerts_test.parquet", index=False)
    sample.to_csv(paths.ml / "ncm_audit_sample.csv", index=False)

    summary = {
        "mes": meta["splits"]["test_month"],
        "limiar": thr,
        "precisao_alvo_validacao": meta["audit"]["target_precision"],
        "itens": int(n),
        "divergem_do_declarado": n_div,
        "pct_divergem": round(100.0 * n_div / n, 2),
        "alertas_confiantes": n_alert,
        "pct_alertas": round(100.0 * n_alert / n, 3),
        "alertas_descricoes_unicas": uniq_desc_alerts,
        "alertas_com_descricao_vista_no_treino": seen_alerts,
        "alertas_trocam_de_capitulo": cross_chapter,
        "valor_total_itens_em_alerta": round(valor_alertas, 2),
        "amostra_inspecao": len(sample),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (paths.ml / "ncm_audit_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    _write_report(summary, by_cap, pairs, sample, ncm_names)
    log.info("auditoria: %s", json.dumps(summary, ensure_ascii=False))
    return summary


def _write_report(summary, by_cap, pairs, sample, ncm_names) -> None:
    L = ["# Auditoria de NCM (mes de teste)", ""]
    L.append(f"Gerado em {summary['generated_at']}. Mes {summary['mes']}. "
             f"Limiar de confianca **{summary['limiar']}** (escolhido no mes de validacao para precisao >= "
             f"{int(100 * summary['precisao_alvo_validacao'])}% do top-1).")
    L.append("")
    L.append("## Numeros")
    L.append("")
    L.append(f"- Itens avaliados: **{summary['itens']:,}**.".replace(",", "."))
    L.append(f"- Predicao diverge do NCM declarado: {summary['divergem_do_declarado']:,} ({summary['pct_divergem']}%). "
             "Divergir nao e alerta: a maior parte e incerteza do modelo.".replace(",", "."))
    L.append(f"- **Alertas** (divergencia com confianca >= limiar): **{summary['alertas_confiantes']:,}** "
             f"({summary['pct_alertas']}% dos itens), em {summary['alertas_descricoes_unicas']:,} descricoes distintas, "
             f"somando R$ {summary['valor_total_itens_em_alerta']:,.2f}.".replace(",", "X").replace(".", ",").replace("X", "."))
    L.append(f"- Alertas em que o modelo troca o capitulo (2 digitos): {summary['alertas_trocam_de_capitulo']:,} "
             f"(troca de capitulo costuma ser erro grosseiro de um dos lados).".replace(",", "."))
    L.append(f"- Alertas cuja descricao identica ja aparecia no treino com outro NCM: "
             f"{summary['alertas_com_descricao_vista_no_treino']:,} (inconsistencia entre fornecedores).".replace(",", "."))
    L.append("")
    L.append("## Alertas por capitulo declarado (15 maiores)")
    L.append("")
    L.append("| Capitulo | Alertas | Valor (R$) |")
    L.append("|---|---:|---:|")
    for cap, row in by_cap.iterrows():
        L.append(f"| {cap} | {int(row['n']):,} | {row['valor']:,.2f} |".replace(",", "X").replace(".", ",").replace("X", "."))
    L.append("")
    L.append("## Pares declarado -> previsto mais frequentes")
    L.append("")
    L.append("| Declarado | Previsto | Alertas | Valor (R$) | Exemplo |")
    L.append("|---|---|---:|---:|---|")
    for _, r in pairs.iterrows():
        L.append(f"| {r['ncm_codigo']} {(ncm_names.get(r['ncm_codigo']) or '')[:35]} | "
                 f"{r['ncm_previsto']} {(ncm_names.get(r['ncm_previsto']) or '')[:35]} | {int(r['n'])} | "
                 f"{r['valor']:,.2f} | {str(r['exemplo'])[:50]} |".replace(",", "X").replace(".", ",").replace("X", "."))
    L.append("")
    L.append(f"## Amostra aleatoria para inspecao manual ({len(sample)} alertas)")
    L.append("")
    L.append("Veredito manual em `reports/ncm_audit_inspection.md`.")
    L.append("")
    L.append("| # | Descricao | NCM declarado | NCM previsto | Conf. | Valor (R$) |")
    L.append("|---:|---|---|---|---:|---:|")
    for _, r in sample.iterrows():
        L.append(f"| {r['n']} | {str(r['descricao_produto'])[:70]} | {r['ncm_codigo']} {r['ncm_declarado_desc'][:40]} | "
                 f"{r['ncm_previsto']} {r['ncm_previsto_desc'][:40]} | {r['confianca']:.3f} | {r['valor_total']:,.2f} |"
                 .replace(",", "X").replace(".", ",").replace("X", "."))
    L.append("")
    AUDIT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_REPORT.write_text("\n".join(L))
