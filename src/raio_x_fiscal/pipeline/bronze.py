"""Bronze: raw CSV (latin-1, ';') -> Parquet, as-is, plus ingestion metadata.

Rules of the layer:
- no value is changed (everything stays VARCHAR, exactly as published);
- the header must match the schema contract or the month fails loudly;
- one Hive partition per month and entity (bronze/<entity>/mes=<AAAAMM>/data.parquet);
- reprocessing a month replaces its partition, so the layer is idempotent;
- the extracted CSVs are deleted right after the Parquet is written (disk hygiene).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from raio_x_fiscal.config import CSV_SUFFIX, ENTITIES, Paths, connect, validate_month
from raio_x_fiscal.pipeline.schema import quote_ident, raw_columns

log = logging.getLogger(__name__)


class SchemaDriftError(RuntimeError):
    """The CSV header differs from the contract in `schema.py`."""


def read_header(csv_path: Path, encoding: str = "latin-1") -> list[str]:
    with csv_path.open("r", encoding=encoding, newline="") as fh:
        first = fh.readline()
    return next(csv.reader(io.StringIO(first), delimiter=";", quotechar='"'))


def check_header(entity: str, csv_path: Path) -> None:
    expected = raw_columns(entity)
    got = read_header(csv_path)
    if got != expected:
        missing = [c for c in expected if c not in got]
        extra = [c for c in got if c not in expected]
        raise SchemaDriftError(
            f"{csv_path.name}: cabecalho diferente do contrato "
            f"(faltando={missing}, extras={extra}, ordem_igual={sorted(got) == sorted(expected)})"
        )


def read_csv_sql(csv_path: Path, entity: str) -> str:
    """DuckDB read_csv call for one of the CGU files (all columns as VARCHAR)."""
    cols = ", ".join(f"{quote_ident(c)}: 'VARCHAR'" for c in raw_columns(entity))
    return (
        f"read_csv('{csv_path.as_posix()}', delim=';', quote='\"', header=true, "
        f"encoding='latin-1', columns={{{cols}}}, null_padding=true, strict_mode=false)"
    )


def extract_zip(zip_path: Path, dest: Path) -> dict[str, Path]:
    """Extract only the three expected CSVs; returns {entity: csv_path}."""
    dest.mkdir(parents=True, exist_ok=True)
    month = zip_path.name.split("_", 1)[0]
    found: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for entity in ENTITIES:
            name = f"{month}{CSV_SUFFIX[entity]}"
            if name not in names:
                raise FileNotFoundError(f"{zip_path.name} nao contem {name} (tem {sorted(names)})")
            zf.extract(name, dest)
            found[entity] = dest / name
    return found


def ingest_month(
    month: str,
    paths: Paths,
    con: duckdb.DuckDBPyConnection | None = None,
    keep_csv: bool = False,
) -> dict[str, dict]:
    """Zip of one month -> three bronze partitions. Returns a manifest per entity."""
    validate_month(month)
    paths.ensure()
    zip_path = paths.raw_zip(month)
    if not zip_path.exists():
        raise FileNotFoundError(f"zip nao encontrado: {zip_path} (rode o download antes)")
    own_con = con is None
    con = con or connect()
    work = paths.tmp / f"bronze_{month}"
    manifests: dict[str, dict] = {}
    try:
        csvs = extract_zip(zip_path, work)
        for entity, csv_path in csvs.items():
            check_header(entity, csv_path)
            manifests[entity] = _write_partition(con, entity, month, csv_path, paths)
            log.info("bronze %s/%s: %d linhas", month, entity, manifests[entity]["rows"])
    finally:
        if not keep_csv and work.exists():
            shutil.rmtree(work)
        if own_con:
            con.close()
    return manifests


def _write_partition(
    con: duckdb.DuckDBPyConnection, entity: str, month: str, csv_path: Path, paths: Paths
) -> dict:
    part_dir = paths.partition("bronze", entity, month)
    if part_dir.exists():
        shutil.rmtree(part_dir)  # idempotent: the month is rebuilt from scratch
    part_dir.mkdir(parents=True)
    out = part_dir / "data.parquet"
    ingested_at = datetime.now(UTC).isoformat(timespec="seconds")
    con.execute(
        f"""
        COPY (
            SELECT *,
                   '{month}'::VARCHAR          AS _mes_referencia,
                   '{csv_path.name}'::VARCHAR  AS _source_file,
                   TIMESTAMP '{ingested_at[:19].replace("T", " ")}' AS _ingested_at
            FROM {read_csv_sql(csv_path, entity)}
        ) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
    manifest = {
        "layer": "bronze",
        "entity": entity,
        "month": month,
        "rows": int(rows),
        "columns": raw_columns(entity),
        "source_file": csv_path.name,
        "source_bytes": csv_path.stat().st_size,
        "parquet_bytes": out.stat().st_size,
        "ingested_at": ingested_at,
    }
    (part_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def bronze_path(paths: Paths, entity: str, month: str) -> Path:
    return paths.partition("bronze", entity, month) / "data.parquet"
