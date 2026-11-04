"""Gold: star schema + aggregates + the ML-ready table, in one DuckDB file.

Full refresh from every silver partition (CREATE OR REPLACE), which keeps the layer
idempotent: running it twice yields the same tables. Every table is also exported to Parquet
(data/gold/parquet/<table>.parquet) for tools that do not speak DuckDB.

Privacy (LGPD): the emitter may be a natural person (CPF). In gold the CPF is replaced by a
salted hash and the person's name is dropped; CNPJs (legal entities) stay, because public
procurement with a company is public information. The ML table carries no identifier at all.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

import duckdb

from raio_x_fiscal.config import Paths, connect
from raio_x_fiscal.pipeline.silver import silver_glob

log = logging.getLogger(__name__)

SEEDS = Path(__file__).resolve().parents[1] / "seeds"

GOLD_TABLES = (
    "dim_capitulo",
    "dim_uf",
    "dim_ncm",
    "dim_cfop",
    "dim_orgao",
    "dim_destinatario",
    "fato_nota",
    "fato_item",
    "agg_gasto_ncm_mes",
    "agg_gasto_orgao_mes",
    "agg_gasto_capitulo_uf_mes",
    "ml_ncm_items",
)


def _salt() -> str:
    """Secret salt for CPF hashing. Without RXF_HASH_SALT a random one is used per build
    (hashes then differ between builds, which is fine: nothing joins on them)."""
    return os.environ.get("RXF_HASH_SALT") or secrets.token_hex(16)


def build_gold(paths: Paths, con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    paths.ensure()
    own_con = con is None
    if con is None:
        if paths.gold_db.exists():
            paths.gold_db.unlink()  # full refresh; the file is a build artefact
        con = connect(paths.gold_db)
    salt = _salt()
    item_glob = silver_glob(paths, "item")
    nota_glob = silver_glob(paths, "nota")
    try:
        con.execute(
            f"CREATE OR REPLACE VIEW silver_item AS SELECT * FROM read_parquet('{item_glob}', hive_partitioning=false)"
        )
        con.execute(
            f"CREATE OR REPLACE VIEW silver_nota AS SELECT * FROM read_parquet('{nota_glob}', hive_partitioning=false)"
        )
        _seeds(con)
        _dims(con)
        _facts(con, salt)
        _aggregates(con)
        _ml_table(con)
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in GOLD_TABLES}
        _export_parquet(con, paths)
        for t, n in counts.items():
            log.info("gold %-28s %10d linhas", t, n)
        return counts
    finally:
        if own_con:
            con.close()


def _seeds(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        f"""CREATE OR REPLACE TABLE dim_capitulo AS
            SELECT capitulo::VARCHAR AS capitulo, secao, descricao_capitulo
            FROM read_csv('{(SEEDS / "ncm_capitulos.csv").as_posix()}', delim='|', header=true,
                          columns={{'capitulo': 'VARCHAR', 'secao': 'VARCHAR', 'descricao_capitulo': 'VARCHAR'}})"""
    )
    con.execute(
        f"""CREATE OR REPLACE TABLE dim_uf AS
            SELECT * FROM read_csv('{(SEEDS / "ufs.csv").as_posix()}', delim='|', header=true,
                          columns={{'uf': 'VARCHAR', 'nome': 'VARCHAR', 'regiao': 'VARCHAR'}})"""
    )


def _dims(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """CREATE OR REPLACE TABLE dim_ncm AS
           SELECT ncm_codigo,
                  substr(ncm_codigo, 1, 2) AS capitulo,
                  substr(ncm_codigo, 1, 4) AS posicao,
                  substr(ncm_codigo, 1, 6) AS subposicao,
                  mode(ncm_descricao)      AS ncm_descricao,
                  count(*)                 AS n_itens,
                  count(DISTINCT descricao_normalizada) AS n_descricoes_distintas
           FROM silver_item WHERE ncm_codigo IS NOT NULL
           GROUP BY 1"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE dim_cfop AS
           SELECT cfop,
                  CASE substr(cfop, 1, 1)
                       WHEN '1' THEN 'entrada' WHEN '2' THEN 'entrada' WHEN '3' THEN 'entrada'
                       ELSE 'saida' END AS tipo_operacao,
                  CASE substr(cfop, 1, 1)
                       WHEN '1' THEN 'estadual' WHEN '5' THEN 'estadual'
                       WHEN '2' THEN 'interestadual' WHEN '6' THEN 'interestadual'
                       ELSE 'exterior' END AS ambito,
                  count(*) AS n_itens
           FROM silver_item WHERE cfop IS NOT NULL GROUP BY 1"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE dim_orgao AS
           SELECT orgao_codigo,
                  mode(orgao_nome)           AS orgao_nome,
                  mode(orgao_superior_codigo) AS orgao_superior_codigo,
                  mode(orgao_superior_nome)   AS orgao_superior_nome,
                  count(*)                    AS n_notas
           FROM silver_nota WHERE orgao_codigo IS NOT NULL GROUP BY 1"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE dim_destinatario AS
           SELECT destinatario_cnpj,
                  mode(destinatario_nome) AS destinatario_nome,
                  mode(destinatario_uf)   AS destinatario_uf,
                  mode(orgao_codigo)      AS orgao_codigo,
                  count(*)                AS n_notas
           FROM silver_nota GROUP BY 1"""
    )


def _facts(con: duckdb.DuckDBPyConnection, salt: str) -> None:
    emitente_id = (
        "CASE WHEN emitente_tipo = 'CPF' "
        f"THEN 'cpf:' || substr(sha256('{salt}' || emitente_cpf_cnpj), 1, 16) "
        "ELSE emitente_cpf_cnpj END"
    )
    razao = "CASE WHEN emitente_tipo = 'CPF' THEN NULL ELSE emitente_razao_social END"
    con.execute(
        f"""CREATE OR REPLACE TABLE fato_nota AS
            SELECT chave_acesso, mes_referencia, data_emissao, modelo, serie, numero_nota,
                   natureza_operacao, evento_mais_recente, data_hora_evento_mais_recente,
                   {emitente_id} AS emitente_id, emitente_tipo, {razao} AS emitente_razao_social,
                   emitente_uf, emitente_municipio,
                   destinatario_cnpj, destinatario_uf, orgao_codigo, orgao_superior_codigo,
                   indicador_ie_destinatario, destino_operacao, consumidor_final, presenca_comprador,
                   valor_nota
            FROM silver_nota"""
    )
    con.execute(
        f"""CREATE OR REPLACE TABLE fato_item AS
            SELECT i.item_id, i.chave_acesso, i.numero_produto, i.mes_referencia, i.data_emissao,
                   {emitente_id.replace("emitente_", "i.emitente_")} AS emitente_id,
                   i.emitente_tipo, i.emitente_uf,
                   i.destinatario_cnpj, i.destinatario_uf,
                   -- the item file says 'Sem informação' for the organ in ~83% of rows while the
                   -- note file has it for ~98%: take the note's value when the item lacks it
                   coalesce(i.orgao_codigo, n.orgao_codigo) AS orgao_codigo,
                   coalesce(i.orgao_superior_codigo, n.orgao_superior_codigo) AS orgao_superior_codigo,
                   i.natureza_operacao, i.cfop,
                   i.ncm_codigo, i.ncm_codigo IS NOT NULL AS ncm_valido, i.ncm_raw,
                   substr(i.ncm_codigo, 1, 2) AS capitulo,
                   i.descricao_produto, i.descricao_normalizada,
                   i.quantidade, i.unidade, i.valor_unitario, i.valor_total
            FROM silver_item i
            LEFT JOIN silver_nota n ON n.chave_acesso = i.chave_acesso"""
    )


def _aggregates(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """CREATE OR REPLACE TABLE agg_gasto_ncm_mes AS
           SELECT mes_referencia, ncm_codigo, substr(ncm_codigo, 1, 2) AS capitulo,
                  count(*) AS n_itens, count(DISTINCT chave_acesso) AS n_notas,
                  sum(quantidade) AS quantidade, sum(valor_total) AS valor_total
           FROM fato_item WHERE ncm_codigo IS NOT NULL GROUP BY 1, 2, 3"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE agg_gasto_orgao_mes AS
           SELECT mes_referencia, orgao_superior_codigo, orgao_codigo, destinatario_cnpj,
                  count(*) AS n_notas, sum(valor_nota) AS valor_total
           FROM fato_nota GROUP BY 1, 2, 3, 4"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE agg_gasto_capitulo_uf_mes AS
           SELECT mes_referencia, capitulo, emitente_uf, destinatario_uf,
                  count(*) AS n_itens, sum(valor_total) AS valor_total
           FROM fato_item WHERE ncm_codigo IS NOT NULL GROUP BY 1, 2, 3, 4"""
    )


def _ml_table(con: duckdb.DuckDBPyConnection) -> None:
    """Anonymised, ML-ready rows: text + label + a few cheap context features."""
    con.execute(
        """CREATE OR REPLACE TABLE ml_ncm_items AS
           SELECT f.item_id, f.mes_referencia, f.data_emissao,
                  f.descricao_produto, f.descricao_normalizada,
                  f.ncm_codigo, f.capitulo, substr(f.ncm_codigo, 1, 4) AS posicao,
                  d.ncm_descricao,
                  f.cfop, f.unidade, f.quantidade, f.valor_unitario, f.valor_total,
                  f.emitente_uf, f.destinatario_uf
           FROM fato_item f LEFT JOIN dim_ncm d USING (ncm_codigo)
           WHERE f.ncm_codigo IS NOT NULL AND f.descricao_normalizada <> ''"""
    )


def _export_parquet(con: duckdb.DuckDBPyConnection, paths: Paths) -> None:
    out = paths.gold / "parquet"
    out.mkdir(parents=True, exist_ok=True)
    for t in GOLD_TABLES:
        con.execute(f"COPY {t} TO '{(out / f'{t}.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
