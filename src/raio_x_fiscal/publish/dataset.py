"""Anonymised, split-aware dataset for Kaggle / Hugging Face (Phase 2 publishes it; here we only
build the files and the dataset card inputs, nothing leaves the machine).

Columns are the gold `ml_ncm_items` ones (no emitter, no recipient, no access key) plus the
`split` assigned by the temporal protocol in `ml/dataset.py`. The train split keeps every item
(not the deduplicated version) so a future user can choose their own dedup policy; the file
also carries `seen_in_train` for valid and test rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from raio_x_fiscal.config import Paths, connect

log = logging.getLogger(__name__)

PUBLIC_COLUMNS = [
    "item_id",
    "split",
    "mes_referencia",
    "descricao_produto",
    "descricao_normalizada",
    "ncm_codigo",
    "capitulo",
    "posicao",
    "ncm_descricao",
    "cfop",
    "unidade",
    "quantidade",
    "valor_unitario",
    "valor_total",
    "emitente_uf",
    "destinatario_uf",
    "seen_in_train",
]


def build_publish(paths: Paths) -> dict:
    paths.ensure()
    splits = json.loads((paths.ml / "splits.json").read_text())
    train_months = ", ".join(f"'{m}'" for m in splits["train_months"])
    out = paths.publish / "nfe_ncm_dataset.parquet"
    out_csv = paths.publish / "nfe_ncm_dataset.csv.gz"
    with connect(paths.gold_db, read_only=True) as con:
        con.execute(
            "CREATE TEMP VIEW train_desc AS SELECT DISTINCT descricao_normalizada "
            f"FROM read_parquet('{(paths.ml / 'train.parquet').as_posix()}')"
        )
        con.execute(
            f"""CREATE TEMP TABLE pub AS
                SELECT i.item_id,
                       CASE WHEN i.mes_referencia IN ({train_months}) THEN 'train'
                            WHEN i.mes_referencia = '{splits["valid_month"]}' THEN 'valid'
                            WHEN i.mes_referencia = '{splits["test_month"]}' THEN 'test' END AS split,
                       i.mes_referencia, i.descricao_produto, i.descricao_normalizada,
                       i.ncm_codigo, i.capitulo, i.posicao, i.ncm_descricao, i.cfop, i.unidade,
                       i.quantidade, i.valor_unitario, i.valor_total, i.emitente_uf, i.destinatario_uf,
                       CASE WHEN i.mes_referencia IN ({train_months}) THEN NULL
                            ELSE t.descricao_normalizada IS NOT NULL END AS seen_in_train
                FROM ml_ncm_items i LEFT JOIN train_desc t USING (descricao_normalizada)"""
        )
        cols = [r[0] for r in con.execute("DESCRIBE pub").fetchall()]
        assert cols == PUBLIC_COLUMNS, cols
        con.execute(f"COPY pub TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        con.execute(f"COPY pub TO '{out_csv.as_posix()}' (FORMAT CSV, HEADER, COMPRESSION GZIP)")
        stats = {
            "rows": con.execute("SELECT count(*) FROM pub").fetchone()[0],
            "by_split": dict(con.execute("SELECT split, count(*) FROM pub GROUP BY 1 ORDER BY 1").fetchall()),
            "ncm_distintos": con.execute("SELECT count(DISTINCT ncm_codigo) FROM pub").fetchone()[0],
            "capitulos": con.execute("SELECT count(DISTINCT capitulo) FROM pub").fetchone()[0],
            "descricoes_unicas": con.execute("SELECT count(DISTINCT descricao_normalizada) FROM pub").fetchone()[0],
            "meses": [r[0] for r in con.execute("SELECT DISTINCT mes_referencia FROM pub ORDER BY 1").fetchall()],
            "valor_total_brl": float(con.execute("SELECT sum(valor_total) FROM pub").fetchone()[0]),
        }
    manifest = {
        **stats,
        "columns": PUBLIC_COLUMNS,
        "files": {
            out.name: {"bytes": out.stat().st_size, "sha256": _sha(out)},
            out_csv.name: {"bytes": out_csv.stat().st_size, "sha256": _sha(out_csv)},
        },
        "source": "Portal da Transparencia (CGU), Notas Fiscais Eletronicas, dados abertos",
        "anonymisation": (
            "sem chave de acesso, CPF/CNPJ, razao social, IE, CNPJ/nome do destinatario; item_id = md5(chave, item)"
        ),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (paths.publish / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    log.info("publish: %s", json.dumps(stats, ensure_ascii=False, default=str))
    return manifest


def _sha(path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
