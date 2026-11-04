"""Data-quality expectations per layer, with the measured numbers written to disk.

Philosophy: every rule is explicit, every number is recorded (also the ugly ones), and only
rules that make downstream data wrong are `fail` (they stop the pipeline). Divergences that
are a property of the source (e.g. note total != sum of items because of freight and
discounts) are measured and reported as `info`/`warn`, never hidden.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from raio_x_fiscal.config import Paths, month_label, validate_month
from raio_x_fiscal.pipeline.bronze import bronze_path
from raio_x_fiscal.pipeline.schema import BRONZE_META_COLUMNS, raw_columns
from raio_x_fiscal.pipeline.silver import silver_path

log = logging.getLogger(__name__)

PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"


class QualityGateError(RuntimeError):
    """At least one `fail` check: the layer must not be consumed downstream."""


@dataclass
class Check:
    layer: str
    name: str
    description: str
    status: str
    observed: Any
    expected: str
    details: dict[str, Any] = field(default_factory=dict)


def _pct(num: float, den: float) -> float:
    return round(100.0 * num / den, 4) if den else 0.0


def _threshold(value: float, warn_below: float, fail_below: float | None = None) -> str:
    if fail_below is not None and value < fail_below:
        return FAIL
    return WARN if value < warn_below else PASS


# ---------------------------------------------------------------------------------------------
# Bronze
# ---------------------------------------------------------------------------------------------


def bronze_checks(con: duckdb.DuckDBPyConnection, paths: Paths, month: str) -> list[Check]:
    validate_month(month)
    checks: list[Check] = []
    for entity in ("nota", "item", "evento"):
        p = bronze_path(paths, entity, month)
        rel = f"read_parquet('{p.as_posix()}', hive_partitioning=false)"
        rows = con.execute(f"SELECT count(*) FROM {rel}").fetchone()[0]
        cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()]
        expected_cols = raw_columns(entity) + list(BRONZE_META_COLUMNS)
        checks.append(
            Check(
                "bronze",
                f"{entity}_schema_contract",
                "Colunas do parquet batem com o contrato de schema (ordem incluida)",
                PASS if cols == expected_cols else FAIL,
                cols == expected_cols,
                "igual ao contrato",
            )
        )
        min_rows = 0 if entity == "evento" else 1
        checks.append(
            Check(
                "bronze",
                f"{entity}_row_count",
                "Linhas ingeridas do CSV",
                PASS if rows >= min_rows and (rows > 0 or entity == "evento") else FAIL,
                int(rows),
                f">= {min_rows}" if entity != "evento" else "pode ser 0 (arquivo vazio na fonte)",
            )
        )
        if rows:
            null_key = con.execute(
                f'SELECT count(*) FROM {rel} WHERE "CHAVE DE ACESSO" IS NULL OR trim("CHAVE DE ACESSO") = \'\''
            ).fetchone()[0]
            checks.append(
                Check(
                    "bronze",
                    f"{entity}_chave_presente",
                    "Chave de acesso presente em toda linha",
                    PASS if null_key == 0 else FAIL,
                    int(null_key),
                    "0",
                )
            )
    return checks


# ---------------------------------------------------------------------------------------------
# Silver
# ---------------------------------------------------------------------------------------------


def silver_checks(con: duckdb.DuckDBPyConnection, paths: Paths, month: str) -> list[Check]:
    validate_month(month)
    label = month_label(month)
    item = f"read_parquet('{silver_path(paths, 'item', month).as_posix()}', hive_partitioning=false)"
    nota = f"read_parquet('{silver_path(paths, 'nota', month).as_posix()}', hive_partitioning=false)"
    bronze_item = f"read_parquet('{bronze_path(paths, 'item', month).as_posix()}', hive_partitioning=false)"
    checks: list[Check] = []

    manifests = {}
    for entity in ("nota", "item"):
        mp = paths.partition("silver", entity, month) / "_manifest.json"
        manifests[entity] = json.loads(mp.read_text()) if mp.exists() else {}
        m = manifests[entity]
        if m:
            rej_pct = _pct(m["rejected"], m["rows_in"])
            checks.append(
                Check(
                    "silver",
                    f"{entity}_rejeitadas",
                    "Linhas rejeitadas (chave/data/valor invalidos)",
                    PASS if rej_pct == 0 else (WARN if rej_pct < 0.5 else FAIL),
                    m["rejected"],
                    "< 0,5% das linhas",
                    {"pct": rej_pct, "por_motivo": m["rejected_by_reason"]},
                )
            )
            checks.append(
                Check(
                    "silver",
                    f"{entity}_duplicadas_removidas",
                    "Duplicatas da chave natural removidas",
                    INFO,
                    m["duplicates_removed"],
                    "informativo",
                    {"chave": m["key"]},
                )
            )

    # Primary keys
    n_item, n_item_pk = con.execute(
        f"SELECT count(*), count(DISTINCT (chave_acesso, numero_produto)) FROM {item}"
    ).fetchone()
    checks.append(
        Check(
            "silver",
            "item_pk_unica",
            "(chave_acesso, numero_produto) e unica",
            PASS if n_item == n_item_pk else FAIL,
            int(n_item - n_item_pk),
            "0 duplicatas",
            {"linhas": int(n_item)},
        )
    )
    n_nota, n_nota_pk = con.execute(f"SELECT count(*), count(DISTINCT chave_acesso) FROM {nota}").fetchone()
    checks.append(
        Check(
            "silver",
            "nota_pk_unica",
            "chave_acesso e unica na tabela de notas",
            PASS if n_nota == n_nota_pk else FAIL,
            int(n_nota - n_nota_pk),
            "0 duplicatas",
            {"linhas": int(n_nota)},
        )
    )

    # Key format (should be 100% after rejects; the check guards the output, not the input)
    bad_key = con.execute(
        f"SELECT count(*) FROM {item} WHERE NOT regexp_matches(chave_acesso, '^[0-9]{{44}}$')"
    ).fetchone()[0]
    checks.append(
        Check(
            "silver",
            "item_chave_44_digitos",
            "Chave de acesso com exatamente 44 digitos",
            PASS if bad_key == 0 else FAIL,
            int(bad_key),
            "0",
        )
    )

    # NCM validity, with the raw-length distribution that explains it
    ncm_valid = con.execute(f"SELECT count(*) FROM {item} WHERE ncm_codigo IS NOT NULL").fetchone()[0]
    ncm_pct = _pct(ncm_valid, n_item)
    raw_lengths = con.execute(
        f"""SELECT CASE WHEN ncm_raw = '-1' THEN 'sentinela -1' ELSE 'len=' || length(ncm_raw) END k,
                   count(*) FROM {item} GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()
    n_ncm_distinct = con.execute(f"SELECT count(DISTINCT ncm_codigo) FROM {item}").fetchone()[0]
    checks.append(
        Check(
            "silver",
            "item_ncm_valido_pct",
            "Itens com NCM valido de 8 digitos (apos zero a esquerda)",
            _threshold(ncm_pct, warn_below=97.0, fail_below=80.0),
            ncm_pct,
            ">= 97%",
            {
                "validos": int(ncm_valid),
                "invalidos": int(n_item - ncm_valid),
                "ncm_distintos": int(n_ncm_distinct),
                "ncm_raw_por_tamanho": {k: int(v) for k, v in raw_lengths},
            },
        )
    )

    cfop_valid = con.execute(f"SELECT count(*) FROM {item} WHERE cfop IS NOT NULL").fetchone()[0]
    cfop_pct = _pct(cfop_valid, n_item)
    checks.append(
        Check(
            "silver",
            "item_cfop_valido_pct",
            "CFOP com 4 digitos e primeiro digito em 1,2,3,5,6,7",
            _threshold(cfop_pct, warn_below=99.9),
            cfop_pct,
            ">= 99,9%",
            {"invalidos": int(n_item - cfop_valid)},
        )
    )

    # Referential integrity between the two files
    orphans = con.execute(
        f"SELECT count(*) FROM {item} i WHERE NOT EXISTS (SELECT 1 FROM {nota} n WHERE n.chave_acesso = i.chave_acesso)"
    ).fetchone()[0]
    checks.append(
        Check(
            "silver",
            "item_sem_nota",
            "Itens cuja chave nao existe no arquivo de notas",
            PASS if orphans == 0 else WARN,
            int(orphans),
            "0",
        )
    )
    childless = con.execute(
        f"SELECT count(*) FROM {nota} n WHERE NOT EXISTS (SELECT 1 FROM {item} i WHERE i.chave_acesso = n.chave_acesso)"
    ).fetchone()[0]
    checks.append(
        Check(
            "silver",
            "nota_sem_item",
            "Notas sem nenhum item no arquivo de itens",
            PASS if childless == 0 else WARN,
            int(childless),
            "0",
        )
    )

    # Arithmetic inside the item
    bad_math = con.execute(
        f"SELECT count(*) FROM {item} WHERE abs(quantidade * valor_unitario - valor_total) > 0.011"
    ).fetchone()[0]
    math_pct = _pct(n_item - bad_math, n_item)
    checks.append(
        Check(
            "silver",
            "item_qtd_x_unitario_igual_total",
            "quantidade x valor_unitario = valor_total (tolerancia 1 centavo)",
            _threshold(math_pct, warn_below=99.0),
            math_pct,
            ">= 99%",
            {"divergentes": int(bad_math)},
        )
    )

    # Sum of items vs note total: a known, expected divergence (freight, discount, IPI, ICMS-ST)
    row = con.execute(
        f"""
        WITH it AS (SELECT chave_acesso, sum(valor_total) soma FROM {item} GROUP BY 1)
        SELECT count(*),
               sum(CASE WHEN abs(soma - valor_nota) <= 0.011 THEN 1 ELSE 0 END),
               sum(CASE WHEN soma > valor_nota + 0.011 THEN 1 ELSE 0 END),
               sum(CASE WHEN soma < valor_nota - 0.011 THEN 1 ELSE 0 END),
               sum(valor_nota), sum(soma)
        FROM {nota} n JOIN it USING (chave_acesso)
        """
    ).fetchone()
    n_join, eq, gt, lt, total_nota, total_itens = row
    eq_pct = _pct(eq or 0, n_join)
    checks.append(
        Check(
            "silver",
            "soma_itens_vs_valor_nota",
            "Notas em que a soma dos itens bate com o valor da nota (1 centavo)",
            INFO if eq_pct >= 70 else WARN,
            eq_pct,
            "divergencia esperada: frete, desconto, IPI e ICMS-ST entram no total da nota e nao nos itens",
            {
                "notas_comparadas": int(n_join),
                "batem": int(eq or 0),
                "itens_maior_que_nota (desconto)": int(gt or 0),
                "itens_menor_que_nota (frete/impostos)": int(lt or 0),
                "valor_total_notas": float(total_nota or 0),
                "valor_total_itens": float(total_itens or 0),
            },
        )
    )

    neg = con.execute(f"SELECT count(*) FROM {item} WHERE valor_total < 0 OR quantidade < 0").fetchone()[0]
    checks.append(
        Check(
            "silver",
            "item_valores_nao_negativos",
            "valor_total e quantidade nao negativos",
            PASS if neg == 0 else WARN,
            int(neg),
            "0",
        )
    )

    in_month = con.execute(f"SELECT count(*) FROM {item} WHERE strftime(data_emissao, '%Y-%m') = '{label}'").fetchone()[
        0
    ]
    in_pct = _pct(in_month, n_item)
    checks.append(
        Check(
            "silver",
            "item_data_emissao_no_mes",
            "Itens com data de emissao dentro do mes do arquivo",
            _threshold(in_pct, warn_below=95.0),
            in_pct,
            ">= 95%",
            {"fora_do_mes": int(n_item - in_month)},
        )
    )

    empty_desc = con.execute(f"SELECT count(*) FROM {item} WHERE descricao_normalizada = ''").fetchone()[0]
    checks.append(
        Check(
            "silver",
            "item_descricao_vazia",
            "Itens sem texto util na descricao apos normalizacao",
            INFO,
            int(empty_desc),
            "informativo (excluidos do dataset de ML)",
        )
    )

    cpf = con.execute(f"SELECT count(*) FROM {nota} WHERE emitente_tipo = 'CPF'").fetchone()[0]
    checks.append(
        Check(
            "silver",
            "nota_emitente_pessoa_fisica",
            "Notas emitidas por CPF (dado pessoal: mascarado no gold, removido do dataset publico)",
            INFO,
            int(cpf),
            "informativo (LGPD)",
        )
    )

    nulls = con.execute(
        f"""SELECT
            {_pct_null("ncm_descricao")}, {_pct_null("orgao_codigo")}, {_pct_null("emitente_ie")},
            {_pct_null("unidade")}, {_pct_null("destinatario_uf")}
            FROM {item}"""
    ).fetchone()
    checks.append(
        Check(
            "silver",
            "item_nulos_por_coluna",
            "Percentual de nulos em colunas descritivas",
            INFO,
            dict(
                zip(
                    ["ncm_descricao", "orgao_codigo", "emitente_ie", "unidade", "destinatario_uf"],
                    [round(float(v or 0), 2) for v in nulls],
                    strict=True,
                )
            ),
            "informativo ('Sem informação' e '-1' virarem NULL e intencional)",
        )
    )

    bronze_rows = con.execute(f"SELECT count(*) FROM {bronze_item}").fetchone()[0]
    checks.append(
        Check(
            "silver",
            "item_reconciliacao_bronze",
            "bronze = silver + rejeitadas + duplicadas",
            PASS
            if bronze_rows
            == n_item + manifests["item"].get("rejected", 0) + manifests["item"].get("duplicates_removed", 0)
            else FAIL,
            int(bronze_rows),
            f"{n_item} + rejeitadas + duplicadas",
        )
    )
    return checks


def _pct_null(col: str) -> str:
    return f"100.0 * sum(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) / count(*)"


# ---------------------------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------------------------

ML_FORBIDDEN_COLUMNS = {
    "chave_acesso",
    "emitente_cpf_cnpj",
    "emitente_razao_social",
    "emitente_ie",
    "emitente_id",
    "destinatario_cnpj",
    "destinatario_nome",
    "numero_nota",
    "serie",
}


def gold_checks(con: duckdb.DuckDBPyConnection, silver_item_glob: str) -> list[Check]:
    checks: list[Check] = []
    n, n_pk = con.execute("SELECT count(*), count(DISTINCT item_id) FROM fato_item").fetchone()
    checks.append(
        Check(
            "gold",
            "fato_item_pk_unica",
            "item_id unico em fato_item",
            PASS if n == n_pk else FAIL,
            int(n - n_pk),
            "0",
            {"linhas": int(n)},
        )
    )

    fk_ncm = con.execute(
        "SELECT count(*) FROM fato_item f WHERE f.ncm_codigo IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM dim_ncm d WHERE d.ncm_codigo = f.ncm_codigo)"
    ).fetchone()[0]
    checks.append(
        Check(
            "gold",
            "fato_item_fk_dim_ncm",
            "Todo NCM do fato existe em dim_ncm",
            PASS if fk_ncm == 0 else FAIL,
            int(fk_ncm),
            "0",
        )
    )

    fk_cap = con.execute(
        "SELECT count(*) FROM dim_ncm d WHERE NOT EXISTS (SELECT 1 FROM dim_capitulo c WHERE c.capitulo = d.capitulo)"
    ).fetchone()[0]
    checks.append(
        Check(
            "gold",
            "dim_ncm_fk_dim_capitulo",
            "Todo capitulo de dim_ncm existe em dim_capitulo (seed)",
            PASS if fk_cap == 0 else FAIL,
            int(fk_cap),
            "0",
        )
    )

    fk_nota = con.execute(
        "SELECT count(*) FROM fato_item f "
        "WHERE NOT EXISTS (SELECT 1 FROM fato_nota n WHERE n.chave_acesso = f.chave_acesso)"
    ).fetchone()[0]
    checks.append(
        Check(
            "gold",
            "fato_item_fk_fato_nota",
            "Todo item aponta para uma nota existente",
            PASS if fk_nota == 0 else WARN,
            int(fk_nota),
            "0",
        )
    )

    silver_sum, silver_n = con.execute(
        f"SELECT sum(valor_total), count(*) FROM read_parquet('{silver_item_glob}', hive_partitioning=false)"
    ).fetchone()
    gold_sum, gold_n = con.execute("SELECT sum(valor_total), count(*) FROM fato_item").fetchone()
    ok = silver_n == gold_n and abs(float(silver_sum) - float(gold_sum)) < 0.01
    checks.append(
        Check(
            "gold",
            "conservacao_silver_para_gold",
            "Mesmas linhas e mesmo valor total entre silver e fato_item",
            PASS if ok else FAIL,
            {"silver": [int(silver_n), float(silver_sum)], "gold": [int(gold_n), float(gold_sum)]},
            "iguais",
        )
    )

    agg_sum = con.execute("SELECT sum(valor_total) FROM agg_gasto_ncm_mes").fetchone()[0]
    fact_sum = con.execute("SELECT sum(valor_total) FROM fato_item WHERE ncm_codigo IS NOT NULL").fetchone()[0]
    ok = abs(float(agg_sum or 0) - float(fact_sum or 0)) < 0.01
    checks.append(
        Check(
            "gold",
            "agg_ncm_mes_consistente",
            "Soma do agregado por NCM/mes = soma do fato (itens com NCM)",
            PASS if ok else FAIL,
            {"agg": float(agg_sum or 0), "fato": float(fact_sum or 0)},
            "iguais",
        )
    )

    ml_cols = {r[0] for r in con.execute("DESCRIBE ml_ncm_items").fetchall()}
    leaked = sorted(ml_cols & ML_FORBIDDEN_COLUMNS)
    checks.append(
        Check(
            "gold",
            "ml_sem_identificadores",
            "Tabela de ML sem identificadores de emitente/destinatario/chave (LGPD)",
            PASS if not leaked else FAIL,
            leaked,
            "[]",
        )
    )

    ml_n = con.execute("SELECT count(*) FROM ml_ncm_items").fetchone()[0]
    checks.append(
        Check(
            "gold",
            "ml_linhas",
            "Linhas da tabela pronta para ML (NCM valido e descricao nao vazia)",
            PASS if ml_n > 0 else FAIL,
            int(ml_n),
            "> 0",
        )
    )

    cpf_leak = con.execute(
        "SELECT count(*) FROM fato_nota WHERE emitente_tipo = 'CPF' "
        "AND (emitente_razao_social IS NOT NULL OR emitente_id NOT LIKE 'cpf:%')"
    ).fetchone()[0]
    checks.append(
        Check(
            "gold",
            "fato_nota_cpf_mascarado",
            "Emitentes pessoa fisica sem CPF e sem nome em claro no gold",
            PASS if cpf_leak == 0 else FAIL,
            int(cpf_leak),
            "0",
        )
    )
    return checks


# ---------------------------------------------------------------------------------------------
# Persistence and report
# ---------------------------------------------------------------------------------------------


def save_checks(paths: Paths, layer: str, scope: str, checks: list[Check]) -> Path:
    paths.quality.mkdir(parents=True, exist_ok=True)
    out = paths.quality / f"{layer}_{scope}.json"
    payload = {
        "layer": layer,
        "scope": scope,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {s: sum(1 for c in checks if c.status == s) for s in (PASS, WARN, FAIL, INFO)},
        "checks": [asdict(c) for c in checks],
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return out


def enforce(checks: list[Check], layer: str, scope: str) -> None:
    failed = [c for c in checks if c.status == FAIL]
    for c in checks:
        lvl = logging.ERROR if c.status == FAIL else logging.WARNING if c.status == WARN else logging.INFO
        log.log(lvl, "quality %s/%s %-38s %s observado=%s", layer, scope, c.name, c.status.upper(), c.observed)
    if failed:
        names = ", ".join(c.name for c in failed)
        raise QualityGateError(f"{layer}/{scope}: {len(failed)} checagem(ns) falharam: {names}")


def load_all(paths: Paths) -> list[dict]:
    if not paths.quality.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(paths.quality.glob("*.json"))]


def render_report(paths: Paths, out: Path) -> str:
    """All saved checks -> one markdown report with the real numbers."""
    runs = load_all(paths)
    lines = ["# Relatorio de qualidade de dados", ""]
    lines.append(f"Gerado em {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} a partir de `data/quality/*.json`.")
    lines.append("")
    lines.append(
        "Legenda: **pass** regra atendida; **warn** fora do esperado, registrado; "
        "**fail** bloqueia a camada; **info** medida sem limiar."
    )
    lines.append("")

    silver_runs = [r for r in runs if r["layer"] == "silver"]
    if silver_runs:
        lines.append("## Resumo por mes (silver)")
        lines.append("")
        lines.append(
            "| Mes | Notas | Itens | Rejeitadas | Duplicadas | NCM valido | q x unit = total | "
            "Soma itens = nota | Itens sem nota | Emitentes CPF |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in sorted(silver_runs, key=lambda x: x["scope"]):
            c = {x["name"]: x for x in r["checks"]}
            lines.append(
                "| {mes} | {notas:,} | {itens:,} | {rej} | {dup} | {ncm:.2f}% | {math:.2f}% | "
                "{soma:.2f}% | {orf} | {cpf} |".format(
                    mes=month_label(r["scope"]),
                    notas=c["nota_pk_unica"]["details"]["linhas"],
                    itens=c["item_pk_unica"]["details"]["linhas"],
                    rej=c["item_rejeitadas"]["observed"] + c["nota_rejeitadas"]["observed"],
                    dup=c["item_duplicadas_removidas"]["observed"] + c["nota_duplicadas_removidas"]["observed"],
                    ncm=c["item_ncm_valido_pct"]["observed"],
                    math=c["item_qtd_x_unitario_igual_total"]["observed"],
                    soma=c["soma_itens_vs_valor_nota"]["observed"],
                    orf=c["item_sem_nota"]["observed"],
                    cpf=c["nota_emitente_pessoa_fisica"]["observed"],
                )
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )
        lines.append("")

    for r in runs:
        title = r["scope"] if r["layer"] == "gold" else month_label(r["scope"])
        s = r["summary"]
        lines.append(
            f"## {r['layer']} / {title}  (pass {s['pass']}, warn {s['warn']}, fail {s['fail']}, info {s['info']})"
        )
        lines.append("")
        lines.append("| Checagem | Status | Observado | Esperado | Detalhes |")
        lines.append("|---|---|---|---|---|")
        for c in r["checks"]:
            det = json.dumps(c["details"], ensure_ascii=False) if c["details"] else ""
            obs = (
                json.dumps(c["observed"], ensure_ascii=False)
                if isinstance(c["observed"], (dict, list))
                else str(c["observed"])
            )
            lines.append(f"| `{c['name']}` | {c['status']} | {obs} | {c['expected']} | {det} |")
        lines.append("")
    text = "\n".join(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return text
