"""Bronze -> silver -> quality -> gold on the fixture month, offline."""

from decimal import Decimal

import duckdb
import pytest

from conftest import K1, K2, K6, MONTH, write_fixture_zip
from raio_x_fiscal.pipeline import bronze, gold, quality, silver
from raio_x_fiscal.pipeline.schema import BRONZE_META_COLUMNS, raw_columns


def _rel(con, path):
    return con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}', hive_partitioning=false)")


def test_bronze_reads_latin1_and_keeps_contract(paths):
    con = duckdb.connect()
    manifests = bronze.ingest_month(MONTH, paths, con)
    assert manifests["nota"]["rows"] == 5
    assert manifests["item"]["rows"] == 9
    assert manifests["evento"]["rows"] == 0  # header-only CSV is valid
    cols = [c[0] for c in _rel(con, bronze.bronze_path(paths, "item", MONTH)).description]
    assert cols == raw_columns("item") + list(BRONZE_META_COLUMNS)
    desc = con.execute(
        f"""SELECT "DESCRIÇÃO DO PRODUTO/SERVIÇO"
            FROM read_parquet('{bronze.bronze_path(paths, "item", MONTH).as_posix()}')
            WHERE "NÚMERO PRODUTO" = '2' AND "CHAVE DE ACESSO" = '{K1}'"""
    ).fetchone()[0]
    assert desc == "FEIJÃO TIPO I"  # accents survived latin-1 decoding
    assert not (paths.tmp / f"bronze_{MONTH}").exists()  # extracted CSVs were cleaned up


def test_bronze_schema_drift_is_loud(paths):
    bad = raw_columns("item")[:-1] + ["VALOR TOTAL COM FRETE"]
    write_fixture_zip(paths.raw, item_header_override=bad)
    with pytest.raises(bronze.SchemaDriftError):
        bronze.ingest_month(MONTH, paths)


def test_bronze_is_idempotent(paths):
    bronze.ingest_month(MONTH, paths)
    first = list(paths.partition("bronze", "item", MONTH).glob("*.parquet"))
    bronze.ingest_month(MONTH, paths)
    second = list(paths.partition("bronze", "item", MONTH).glob("*.parquet"))
    assert len(first) == len(second) == 1
    con = duckdb.connect()
    n = con.execute(f"SELECT count(*) FROM read_parquet('{second[0].as_posix()}')").fetchone()[0]
    assert n == 9


def test_silver_cleans_types_rejects_and_dedups(paths):
    bronze.ingest_month(MONTH, paths)
    m = silver.build_month(MONTH, paths)
    assert m["item"] == {**m["item"], "rows_in": 9, "rows_out": 7, "rejected": 1, "duplicates_removed": 1}
    assert m["item"]["rejected_by_reason"] == {"chave_invalida": 1}
    assert m["nota"]["rows_out"] == 4 and m["nota"]["rejected"] == 1

    con = duckdb.connect()
    item = f"read_parquet('{silver.silver_path(paths, 'item', MONTH).as_posix()}', hive_partitioning=false)"
    rows = {
        (r[0], r[1]): r[2:]
        for r in con.execute(
            f"SELECT chave_acesso, numero_produto, ncm_codigo, cfop, valor_total, descricao_normalizada, "
            f"quantidade, unidade, data_emissao, emitente_tipo FROM {item}"
        ).fetchall()
    }
    assert rows[(K1, 2)][0] == "07133399"  # leading zero restored
    assert rows[(K2, 1)][0] is None  # '-1' sentinel -> NULL
    assert rows[(K2, 1)][2] == Decimal("1234.56")  # '1.234,56' parsed
    assert rows[(K2, 2)][1] is None  # CFOP 'ABCD' -> NULL
    assert rows[(K2, 2)][3] == "caneta azul c tampa 10 un"
    assert rows[(K6, 2)][0] == "94036000"
    assert rows[(K1, 1)][4] == Decimal("30.0000") and rows[(K1, 1)][5] == "UNIDAD"
    assert str(rows[(K1, 1)][6]) == "2025-01-05"
    assert rows[(K6, 1)][7] == "CPF"

    rejects = con.execute(
        "SELECT entity, reject_reason FROM read_parquet("
        f"'{(paths.partition('silver', 'rejects', MONTH) / '*.parquet').as_posix()}')"
    ).fetchall()
    assert sorted(rejects) == [("item", "chave_invalida"), ("nota", "chave_invalida")]


def test_silver_is_idempotent(paths):
    bronze.ingest_month(MONTH, paths)
    silver.build_month(MONTH, paths)
    silver.build_month(MONTH, paths)
    con = duckdb.connect()
    glob = silver.silver_glob(paths, "item")
    n, n_pk = con.execute(
        "SELECT count(*), count(DISTINCT (chave_acesso, numero_produto)) "
        f"FROM read_parquet('{glob}', hive_partitioning=false)"
    ).fetchone()
    assert n == n_pk == 7


def test_quality_checks_measure_known_divergences(paths):
    bronze.ingest_month(MONTH, paths)
    silver.build_month(MONTH, paths)
    con = duckdb.connect()
    by_name = {c.name: c for c in quality.silver_checks(con, paths, MONTH)}
    assert by_name["item_pk_unica"].status == "pass"
    assert by_name["item_chave_44_digitos"].status == "pass"
    assert by_name["item_sem_nota"].status == "warn" and by_name["item_sem_nota"].observed == 1  # K5
    assert by_name["nota_sem_item"].status == "warn" and by_name["nota_sem_item"].observed == 1  # K4
    ncm = by_name["item_ncm_valido_pct"]
    assert ncm.details["validos"] == 6 and ncm.details["invalidos"] == 1 and ncm.status == "warn"
    assert ncm.details["ncm_raw_por_tamanho"]["sentinela -1"] == 1
    soma = by_name["soma_itens_vs_valor_nota"]
    assert soma.details["batem"] == 2  # K1 and K6
    assert soma.details["itens_menor_que_nota (frete/impostos)"] == 1  # K2: 1.244,56 < 1.300,00
    assert by_name["item_qtd_x_unitario_igual_total"].observed == 100.0
    assert by_name["item_cfop_valido_pct"].details["invalidos"] == 1
    assert by_name["nota_emitente_pessoa_fisica"].observed == 1
    assert by_name["item_reconciliacao_bronze"].status == "pass"

    bronze_checks = quality.bronze_checks(con, paths, MONTH)
    assert all(c.status == "pass" for c in bronze_checks)

    quality.save_checks(paths, "silver", MONTH, list(by_name.values()))
    text = quality.render_report(paths, paths.data / "quality_report.md")
    assert "2025-01" in text and "soma_itens_vs_valor_nota" in text


def test_quality_gate_raises_on_fail():
    failing = [quality.Check("silver", "x", "d", quality.FAIL, 1, "0")]
    with pytest.raises(quality.QualityGateError):
        quality.enforce(failing, "silver", MONTH)
    quality.enforce([quality.Check("silver", "x", "d", quality.WARN, 1, "0")], "silver", MONTH)


def test_gold_star_schema_masks_cpf_and_passes_checks(paths):
    # run_month would stop at the quality gate: 1 rejected note out of 5 is 20%, far above the
    # 0,5% tolerance that makes sense on real months. Build the layers directly.
    bronze.ingest_month(MONTH, paths)
    silver.build_month(MONTH, paths)
    counts = gold.build_gold(paths)
    assert counts["fato_item"] == 7 and counts["fato_nota"] == 4
    assert counts["dim_capitulo"] == 96 and counts["dim_uf"] == 28
    con = duckdb.connect(str(paths.gold_db), read_only=True)
    cap = con.execute("SELECT capitulo, posicao FROM dim_ncm WHERE ncm_codigo = '07133399'").fetchone()
    assert cap == ("07", "0713")
    emit = con.execute(
        f"SELECT emitente_id, emitente_razao_social FROM fato_nota WHERE chave_acesso = '{K6}'"
    ).fetchone()
    assert emit[0].startswith("cpf:") and emit[1] is None
    cnpj = con.execute(f"SELECT emitente_id FROM fato_nota WHERE chave_acesso = '{K1}'").fetchone()[0]
    assert cnpj == "11222333000181"  # legal entities stay (public procurement data)
    ml_cols = {r[0] for r in con.execute("DESCRIBE ml_ncm_items").fetchall()}
    assert not (ml_cols & quality.ML_FORBIDDEN_COLUMNS)
    assert con.execute("SELECT count(*) FROM ml_ncm_items").fetchone()[0] == 6  # valid NCM + text
    checks = quality.gold_checks(con, silver.silver_glob(paths, "item"))
    status = {c.name: c.status for c in checks}
    assert status["fato_item_fk_fato_nota"] == "warn"  # the orphan K5 is reported, not hidden
    assert all(s == "pass" for n, s in status.items() if n != "fato_item_fk_fato_nota")
    con.close()
    # full refresh twice -> same counts (idempotent)
    assert gold.build_gold(paths) == counts
