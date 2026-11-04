"""Silver: typed, cleaned, deduplicated tables (one partition per month).

What happens here, in order:
1. rename raw headers to snake_case (contract in `schema.py`);
2. type everything: Brazilian decimals ('1.234,56'), dd/mm/aaaa dates, integer codes;
3. normalise: NCM to 8 digits (or NULL), CFOP 4 digits, free-text description, unit uppercase;
4. reject rows that cannot be trusted (invalid 44-digit key, no date, no value) into a
   `rejects` partition with the reason, so nothing disappears silently;
5. deduplicate on the natural key (nota: chave_acesso; item: chave_acesso + numero_produto).

Rebuilding a month overwrites its partitions, which makes the layer idempotent.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import duckdb

from raio_x_fiscal.config import Paths, connect, month_label, validate_month
from raio_x_fiscal.pipeline.bronze import bronze_path
from raio_x_fiscal.pipeline.normalize import (
    sql_date_br,
    sql_decimal_br,
    sql_emitente_tipo,
    sql_is_valid_chave,
    sql_normalize_cfop,
    sql_normalize_description,
    sql_normalize_ncm,
    sql_timestamp_br,
)

log = logging.getLogger(__name__)

SEM_INFO = "'Sem informação'"


def _nullif_sem_info(col: str) -> str:
    return f"nullif(nullif(trim({col}), {SEM_INFO}), '-1')"


def _code(col: str) -> str:
    """Org codes come as '26000' or '-1' (meaning unknown)."""
    return f"TRY_CAST(nullif(nullif(trim({col}), '-1'), '') AS INTEGER)"


def _header_columns() -> str:
    """Columns shared by nota and item (the item file repeats the note header)."""
    return f"""
        trim("CHAVE DE ACESSO")                                   AS chave_acesso,
        TRY_CAST(regexp_extract(trim("MODELO"), '^([0-9]+)', 1) AS SMALLINT) AS modelo,
        trim("SÉRIE")                                             AS serie,
        TRY_CAST(trim("NÚMERO") AS BIGINT)                        AS numero_nota,
        trim("NATUREZA DA OPERAÇÃO")                              AS natureza_operacao,
        {sql_date_br('"DATA EMISSÃO"')}                           AS data_emissao,
        trim("CPF/CNPJ Emitente")                                 AS emitente_cpf_cnpj,
        {sql_emitente_tipo('"CPF/CNPJ Emitente"')}                AS emitente_tipo,
        trim("RAZÃO SOCIAL EMITENTE")                             AS emitente_razao_social,
        {_nullif_sem_info('"INSCRIÇÃO ESTADUAL EMITENTE"')}       AS emitente_ie,
        upper(trim("UF EMITENTE"))                                AS emitente_uf,
        trim("MUNICÍPIO EMITENTE")                                AS emitente_municipio,
        {_code('"CÓDIGO ÓRGÃO SUPERIOR DESTINATÁRIO"')}           AS orgao_superior_codigo,
        {_nullif_sem_info('"ÓRGÃO SUPERIOR DESTINATÁRIO"')}       AS orgao_superior_nome,
        {_code('"CÓDIGO ÓRGÃO DESTINATÁRIO"')}                    AS orgao_codigo,
        {_nullif_sem_info('"ÓRGÃO DESTINATÁRIO"')}                AS orgao_nome,
        trim("CNPJ DESTINATÁRIO")                                 AS destinatario_cnpj,
        trim("NOME DESTINATÁRIO")                                 AS destinatario_nome,
        upper(trim("UF DESTINATÁRIO"))                            AS destinatario_uf,
        trim("INDICADOR IE DESTINATÁRIO")                         AS indicador_ie_destinatario,
        trim("DESTINO DA OPERAÇÃO")                               AS destino_operacao,
        trim("CONSUMIDOR FINAL")                                  AS consumidor_final,
        trim("PRESENÇA DO COMPRADOR")                             AS presenca_comprador,
    """


def nota_sql(src: str, month: str) -> str:
    return f"""
    SELECT
        {_header_columns()}
        trim("EVENTO MAIS RECENTE")                               AS evento_mais_recente,
        {sql_timestamp_br('"DATA/HORA EVENTO MAIS RECENTE"')}     AS data_hora_evento_mais_recente,
        {sql_decimal_br('"VALOR NOTA FISCAL"', 2)}                AS valor_nota,
        '{month_label(month)}'                                    AS mes_referencia,
        _source_file, _ingested_at
    FROM {src}
    """


def item_sql(src: str, month: str) -> str:
    return f"""
    SELECT
        md5(trim("CHAVE DE ACESSO") || '-' || trim("NÚMERO PRODUTO")) AS item_id,
        {_header_columns()}
        TRY_CAST(trim("NÚMERO PRODUTO") AS INTEGER)               AS numero_produto,
        trim("DESCRIÇÃO DO PRODUTO/SERVIÇO")                      AS descricao_produto,
        {sql_normalize_description('"DESCRIÇÃO DO PRODUTO/SERVIÇO"')} AS descricao_normalizada,
        trim("CÓDIGO NCM/SH")                                     AS ncm_raw,
        {sql_normalize_ncm('"CÓDIGO NCM/SH"')}                    AS ncm_codigo,
        {_nullif_sem_info('"NCM/SH (TIPO DE PRODUTO)"')}          AS ncm_descricao,
        trim("CFOP")                                              AS cfop_raw,
        {sql_normalize_cfop('"CFOP"')}                            AS cfop,
        {sql_decimal_br('"QUANTIDADE"', 4)}                       AS quantidade,
        upper(trim("UNIDADE"))                                    AS unidade,
        {sql_decimal_br('"VALOR UNITÁRIO"', 4)}                   AS valor_unitario,
        {sql_decimal_br('"VALOR TOTAL"', 2)}                      AS valor_total,
        '{month_label(month)}'                                    AS mes_referencia,
        _source_file, _ingested_at
    FROM {src}
    """


def evento_sql(src: str, month: str) -> str:
    return f"""
    SELECT
        trim("CHAVE DE ACESSO")                                   AS chave_acesso,
        TRY_CAST(regexp_extract(trim("MODELO"), '^([0-9]+)', 1) AS SMALLINT) AS modelo,
        trim("SÉRIE")                                             AS serie,
        TRY_CAST(trim("NÚMERO") AS BIGINT)                        AS numero_nota,
        trim("NATUREZA DA OPERAÇÃO")                              AS natureza_operacao,
        {sql_date_br('"DATA EMISSÃO"')}                           AS data_emissao,
        trim("EVENTO")                                            AS evento,
        {sql_timestamp_br('"DATA/HORA EVENTO"')}                  AS data_hora_evento,
        trim("DESCRIÇÃO EVENTO")                                  AS descricao_evento,
        trim("MOTIVO EVENTO")                                     AS motivo_evento,
        '{month_label(month)}'                                    AS mes_referencia,
        _source_file, _ingested_at
    FROM {src}
    """


# Reject rules: (reason, SQL predicate over the typed row). First match wins.
NOTA_REJECTS = [
    ("chave_invalida", f"NOT {sql_is_valid_chave('chave_acesso')}"),
    ("data_emissao_invalida", "data_emissao IS NULL"),
    ("valor_nota_invalido", "valor_nota IS NULL"),
]
ITEM_REJECTS = [
    ("chave_invalida", f"NOT {sql_is_valid_chave('chave_acesso')}"),
    ("numero_produto_invalido", "numero_produto IS NULL"),
    ("data_emissao_invalida", "data_emissao IS NULL"),
    ("valor_total_invalido", "valor_total IS NULL"),
]
NOTA_KEY = ["chave_acesso"]
ITEM_KEY = ["chave_acesso", "numero_produto"]


def _reject_case(rules: list[tuple[str, str]]) -> str:
    whens = " ".join(f"WHEN {pred} THEN '{reason}'" for reason, pred in rules)
    return f"CASE {whens} ELSE NULL END"


def _write(con: duckdb.DuckDBPyConnection, query: str, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]


def _reset(part_dir: Path) -> Path:
    if part_dir.exists():
        shutil.rmtree(part_dir)
    part_dir.mkdir(parents=True)
    return part_dir


def _build_entity(
    con: duckdb.DuckDBPyConnection,
    entity: str,
    month: str,
    paths: Paths,
    typed_sql: str,
    rejects: list[tuple[str, str]],
    key: list[str],
) -> dict:
    con.execute(f"CREATE OR REPLACE TEMP TABLE typed_{entity} AS {typed_sql}")
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE flagged_{entity} AS "
        f"SELECT *, {_reject_case(rejects)} AS reject_reason FROM typed_{entity}"
    )
    total = con.execute(f"SELECT count(*) FROM flagged_{entity}").fetchone()[0]
    reject_counts = dict(
        con.execute(
            f"SELECT reject_reason, count(*) FROM flagged_{entity} "
            "WHERE reject_reason IS NOT NULL GROUP BY 1 ORDER BY 1"
        ).fetchall()
    )
    key_cols = ", ".join(key)
    accepted_sql = f"""
        SELECT * EXCLUDE (reject_reason) FROM flagged_{entity}
        WHERE reject_reason IS NULL
        QUALIFY row_number() OVER (PARTITION BY {key_cols} ORDER BY _source_file) = 1
    """
    out_dir = _reset(paths.partition("silver", entity, month))
    accepted = _write(con, accepted_sql, out_dir / "data.parquet")

    rejects_sql = f"""
        SELECT '{entity}' AS entity, reject_reason, chave_acesso,
               {"numero_produto" if "numero_produto" in key else "NULL::INTEGER AS numero_produto"},
               mes_referencia, _source_file
        FROM flagged_{entity} WHERE reject_reason IS NOT NULL
    """
    rej_dir = paths.partition("silver", "rejects", month)
    rej_dir.mkdir(parents=True, exist_ok=True)
    rejected = _write(con, rejects_sql, rej_dir / f"{entity}.parquet")
    duplicates = int(total - rejected - accepted)
    manifest = {
        "layer": "silver",
        "entity": entity,
        "month": month,
        "rows_in": int(total),
        "rows_out": int(accepted),
        "rejected": int(rejected),
        "rejected_by_reason": {k: int(v) for k, v in reject_counts.items()},
        "duplicates_removed": duplicates,
        "key": key,
    }
    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    con.execute(f"DROP TABLE IF EXISTS typed_{entity}")
    con.execute(f"DROP TABLE IF EXISTS flagged_{entity}")
    return manifest


def build_month(month: str, paths: Paths, con: duckdb.DuckDBPyConnection | None = None) -> dict[str, dict]:
    """Bronze partitions of one month -> silver nota/item/evento (+ rejects)."""
    validate_month(month)
    own_con = con is None
    con = con or connect()
    manifests: dict[str, dict] = {}
    try:
        for entity in ("nota", "item", "evento"):
            src_path = bronze_path(paths, entity, month)
            if not src_path.exists():
                raise FileNotFoundError(f"bronze ausente: {src_path} (rode o bronze antes)")
            src = f"read_parquet('{src_path.as_posix()}', hive_partitioning=false)"
            if entity == "nota":
                m = _build_entity(con, entity, month, paths, nota_sql(src, month), NOTA_REJECTS, NOTA_KEY)
            elif entity == "item":
                m = _build_entity(con, entity, month, paths, item_sql(src, month), ITEM_REJECTS, ITEM_KEY)
            else:
                m = _build_entity(
                    con,
                    entity,
                    month,
                    paths,
                    evento_sql(src, month),
                    NOTA_REJECTS[:2],
                    ["chave_acesso", "data_hora_evento"],
                )
            manifests[entity] = m
            log.info(
                "silver %s/%s: %d -> %d (rejeitadas %d, duplicadas %d)",
                month,
                entity,
                m["rows_in"],
                m["rows_out"],
                m["rejected"],
                m["duplicates_removed"],
            )
    finally:
        if own_con:
            con.close()
    return manifests


def silver_path(paths: Paths, entity: str, month: str) -> Path:
    return paths.partition("silver", entity, month) / "data.parquet"


def silver_glob(paths: Paths, entity: str) -> str:
    return (paths.silver / entity / "mes=*" / "data.parquet").as_posix()
