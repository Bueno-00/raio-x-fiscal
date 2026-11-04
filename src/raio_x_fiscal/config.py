"""Paths, constants and the DuckDB connection factory.

Everything that depends on the machine (data directory, memory limit, thread count) is read
from environment variables with safe defaults, so the same code runs on the VPS (via CLI),
inside Airflow (via the DAG) and in tests (via a temporary directory).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]

DOWNLOAD_URL = "https://portaldatransparencia.gov.br/download-de-dados/notas-fiscais/{month}"
MONTH_RE = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])$")

DUCKDB_MEMORY_LIMIT = os.environ.get("RXF_DUCKDB_MEMORY", "1500MB")
DUCKDB_THREADS = int(os.environ.get("RXF_DUCKDB_THREADS", "2"))

ENTITIES = ("nota", "item", "evento")

# Suffix of each CSV inside the monthly zip, e.g. 202509_NFe_NotaFiscalItem.csv
CSV_SUFFIX = {
    "nota": "_NFe_NotaFiscal.csv",
    "item": "_NFe_NotaFiscalItem.csv",
    "evento": "_NFe_NotaFiscalEvento.csv",
}


def validate_month(month: str) -> str:
    """Accept only AAAAMM strings (the format used by the Portal da Transparencia)."""
    if not MONTH_RE.match(month):
        raise ValueError(f"mes invalido: {month!r} (esperado AAAAMM, ex. 202509)")
    return month


def month_label(month: str) -> str:
    """202509 -> 2025-09 (the label stored in the tables)."""
    validate_month(month)
    return f"{month[:4]}-{month[4:]}"


@dataclass(frozen=True)
class Paths:
    """All filesystem locations used by the pipeline, derived from one data root."""

    data: Path
    models: Path

    @classmethod
    def from_env(cls) -> Paths:
        data = Path(os.environ.get("RXF_DATA_DIR", ROOT / "data"))
        models = Path(os.environ.get("RXF_MODELS_DIR", ROOT / "models"))
        return cls(data=data, models=models)

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def tmp(self) -> Path:
        return self.data / "tmp"

    @property
    def bronze(self) -> Path:
        return self.data / "bronze"

    @property
    def silver(self) -> Path:
        return self.data / "silver"

    @property
    def gold(self) -> Path:
        return self.data / "gold"

    @property
    def gold_db(self) -> Path:
        return self.gold / "raio_x_fiscal.duckdb"

    @property
    def quality(self) -> Path:
        return self.data / "quality"

    @property
    def ml(self) -> Path:
        return self.data / "ml"

    @property
    def publish(self) -> Path:
        return self.data / "publish"

    def raw_zip(self, month: str) -> Path:
        return self.raw / f"{validate_month(month)}_NFe.zip"

    def partition(self, layer: str, entity: str, month: str) -> Path:
        """Hive-style partition directory: <layer>/<entity>/mes=<AAAAMM>/."""
        base = {"bronze": self.bronze, "silver": self.silver}[layer]
        return base / entity / f"mes={validate_month(month)}"

    def ensure(self) -> None:
        for p in (
            self.raw,
            self.tmp,
            self.bronze,
            self.silver,
            self.gold,
            self.quality,
            self.ml,
            self.publish,
            self.models,
        ):
            p.mkdir(parents=True, exist_ok=True)


def connect(database: str | Path = ":memory:", read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """DuckDB connection with the memory and thread limits this box can afford."""
    con = duckdb.connect(str(database), read_only=read_only)
    con.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"SET threads={DUCKDB_THREADS}")
    con.execute("SET preserve_insertion_order=false")
    return con


def list_months(paths: Paths, layer: str, entity: str = "item") -> list[str]:
    """Months already materialised in a layer (from the partition directories)."""
    base = {"bronze": paths.bronze, "silver": paths.silver}[layer] / entity
    if not base.exists():
        return []
    months = sorted(p.name.split("=", 1)[1] for p in base.iterdir() if p.name.startswith("mes="))
    return [m for m in months if MONTH_RE.match(m)]
