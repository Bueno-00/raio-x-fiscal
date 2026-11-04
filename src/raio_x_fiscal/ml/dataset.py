"""Temporal split with description-level deduplication for the descricao -> NCM task.

Why this matters: the same free-text description ('ARROZ TIPO 1') repeats thousands of times
across months. A random split puts copies of the same string on both sides and the model
'learns' by memorising. Here:

- train = all months strictly before the validation month, collapsed to ONE row per
  normalised description (label = most frequent NCM for that description, with the count and
  the number of distinct NCMs seen, which measures label noise);
- valid = the month before the test month, all items (used only to calibrate temperatures and
  the audit threshold, never to fit the classifiers);
- test  = the most recent month, all items, each flagged `seen_in_train` so the evaluation can
  report the honest number (descriptions never seen) next to the inflated one.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from raio_x_fiscal.config import Paths, connect, list_months, month_label

log = logging.getLogger(__name__)


def split_months(all_months: list[str], valid_month: str, test_month: str) -> list[str]:
    train = [m for m in all_months if m < valid_month]
    if not train:
        raise ValueError(f"nenhum mes de treino antes de {valid_month} em {all_months}")
    if valid_month >= test_month:
        raise ValueError("mes de validacao precisa ser anterior ao de teste")
    return train


def build_splits(paths: Paths, test_month: str, valid_month: str) -> dict:
    paths.ensure()
    months = list_months(paths, "silver")
    train_months = split_months(months, valid_month, test_month)
    labels = {m: month_label(m) for m in months}
    train_labels = ", ".join(f"'{labels[m]}'" for m in train_months)

    with connect(paths.gold_db, read_only=True) as con:
        con.execute(
            f"""CREATE OR REPLACE TEMP TABLE train AS
                SELECT descricao_normalizada,
                       arg_max(ncm_codigo, n)              AS ncm_codigo,
                       substr(arg_max(ncm_codigo, n), 1, 2) AS capitulo,
                       sum(n)                              AS n_itens,
                       count(*)                            AS n_ncm_distintos,
                       max(n) / sum(n)                     AS pureza,
                       arg_max(descricao_produto, n)       AS descricao_produto
                FROM (
                    SELECT descricao_normalizada, ncm_codigo, count(*) AS n,
                           min(descricao_produto) AS descricao_produto
                    FROM ml_ncm_items WHERE mes_referencia IN ({train_labels})
                    GROUP BY 1, 2
                )
                GROUP BY 1"""
        )
        con.execute(f"COPY train TO '{(paths.ml / 'train.parquet').as_posix()}' (FORMAT PARQUET)")

        for name, month in (("valid", valid_month), ("test", test_month)):
            con.execute(
                f"""COPY (
                    SELECT i.item_id, i.mes_referencia, i.descricao_produto, i.descricao_normalizada,
                           i.ncm_codigo, i.capitulo, i.ncm_descricao, i.cfop, i.unidade,
                           i.quantidade, i.valor_unitario, i.valor_total, i.emitente_uf,
                           t.descricao_normalizada IS NOT NULL AS seen_in_train,
                           t.ncm_codigo AS ncm_lookup
                    FROM ml_ncm_items i LEFT JOIN train t USING (descricao_normalizada)
                    WHERE i.mes_referencia = '{labels[month]}'
                ) TO '{(paths.ml / f'{name}.parquet').as_posix()}' (FORMAT PARQUET)"""
            )

        stats = {
            "train_months": [labels[m] for m in train_months],
            "valid_month": labels[valid_month],
            "test_month": labels[test_month],
            "train": _train_stats(con),
            "valid": _eval_stats(con, paths, "valid"),
            "test": _eval_stats(con, paths, "test"),
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    (paths.ml / "splits.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    log.info("splits: %s", json.dumps(stats, ensure_ascii=False))
    return stats


def _train_stats(con) -> dict:
    row = con.execute(
        """SELECT count(*), sum(n_itens), count(DISTINCT ncm_codigo), count(DISTINCT capitulo),
                  sum(CASE WHEN n_ncm_distintos > 1 THEN 1 ELSE 0 END),
                  sum(CASE WHEN n_ncm_distintos > 1 THEN n_itens ELSE 0 END),
                  avg(pureza)
           FROM train"""
    ).fetchone()
    n_desc, n_items, n_ncm, n_cap, noisy_desc, noisy_items, purity = row
    return {
        "descricoes_unicas": int(n_desc),
        "itens_originais": int(n_items),
        "ncm_distintos": int(n_ncm),
        "capitulos_distintos": int(n_cap),
        "descricoes_com_mais_de_um_ncm": int(noisy_desc),
        "pct_descricoes_com_mais_de_um_ncm": round(100.0 * noisy_desc / n_desc, 2),
        "pct_itens_com_descricao_ambigua": round(100.0 * noisy_items / n_items, 2),
        "pureza_media_do_rotulo": round(float(purity), 4),
    }


def _eval_stats(con, paths: Paths, name: str) -> dict:
    p = (paths.ml / f"{name}.parquet").as_posix()
    row = con.execute(
        f"""SELECT count(*), count(DISTINCT descricao_normalizada),
                   sum(CASE WHEN seen_in_train THEN 1 ELSE 0 END),
                   count(DISTINCT CASE WHEN NOT seen_in_train THEN descricao_normalizada END),
                   count(DISTINCT ncm_codigo),
                   sum(CASE WHEN seen_in_train AND ncm_lookup = ncm_codigo THEN 1 ELSE 0 END)
            FROM read_parquet('{p}')"""
    ).fetchone()
    n, n_uniq, seen, unseen_uniq, n_ncm, lookup_ok = row
    return {
        "itens": int(n),
        "descricoes_unicas": int(n_uniq),
        "itens_com_descricao_vista_no_treino": int(seen),
        "pct_itens_vistos": round(100.0 * seen / n, 2),
        "descricoes_unicas_nao_vistas": int(unseen_uniq),
        "ncm_distintos": int(n_ncm),
        "pct_vistos_em_que_lookup_acerta": round(100.0 * lookup_ok / seen, 2) if seen else None,
    }
