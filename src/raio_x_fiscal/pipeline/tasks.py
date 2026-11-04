"""Plain-function tasks shared by the CLI (VPS) and the Airflow DAG (docker-compose).

Each task takes a month (AAAAMM) and the `Paths`, does one thing, and returns a small,
JSON-serialisable summary (Airflow stores it as XCom). No Airflow import here, so the same
functions run in tests, in `make pipeline` and inside the DAG.
"""

from __future__ import annotations

import logging
from pathlib import Path

from raio_x_fiscal.config import ROOT, Paths, connect, list_months, validate_month
from raio_x_fiscal.pipeline import bronze, download, gold, quality, silver

log = logging.getLogger(__name__)

QUALITY_REPORT = ROOT / "reports" / "quality_report.md"


def task_download(month: str, paths: Paths | None = None) -> str:
    paths = paths or Paths.from_env()
    return str(download.download_month(validate_month(month), paths))


def task_bronze(month: str, paths: Paths | None = None) -> dict:
    paths = paths or Paths.from_env()
    with connect() as con:
        manifests = bronze.ingest_month(month, paths, con)
    return {e: m["rows"] for e, m in manifests.items()}


def task_silver(month: str, paths: Paths | None = None) -> dict:
    paths = paths or Paths.from_env()
    with connect() as con:
        manifests = silver.build_month(month, paths, con)
    return {e: {k: m[k] for k in ("rows_in", "rows_out", "rejected", "duplicates_removed")} for e, m in manifests.items()}


def task_quality_month(month: str, paths: Paths | None = None) -> dict:
    """Bronze + silver expectations for one month. Raises QualityGateError on `fail`."""
    paths = paths or Paths.from_env()
    summary = {}
    with connect() as con:
        for layer, fn in (("bronze", quality.bronze_checks), ("silver", quality.silver_checks)):
            checks = fn(con, paths, month)
            quality.save_checks(paths, layer, month, checks)
            quality.enforce(checks, layer, month)
            summary[layer] = {c.name: c.status for c in checks}
    return summary


def task_gold(paths: Paths | None = None) -> dict:
    paths = paths or Paths.from_env()
    return {k: int(v) for k, v in gold.build_gold(paths).items()}


def task_quality_gold(paths: Paths | None = None) -> dict:
    paths = paths or Paths.from_env()
    with connect(paths.gold_db, read_only=True) as con:
        checks = quality.gold_checks(con, silver.silver_glob(paths, "item"))
    quality.save_checks(paths, "gold", "all", checks)
    quality.enforce(checks, "gold", "all")
    return {c.name: c.status for c in checks}


def task_report(paths: Paths | None = None, out: Path = QUALITY_REPORT) -> str:
    paths = paths or Paths.from_env()
    quality.render_report(paths, out)
    return str(out)


def run_month(month: str, paths: Paths | None = None, skip_download: bool = False) -> dict:
    """download -> bronze -> silver -> quality, for one month (idempotent)."""
    paths = paths or Paths.from_env()
    out: dict = {"month": month}
    if not skip_download:
        out["zip"] = task_download(month, paths)
    out["bronze"] = task_bronze(month, paths)
    out["silver"] = task_silver(month, paths)
    out["quality"] = task_quality_month(month, paths)
    return out


def run_pipeline(months: list[str], paths: Paths | None = None, skip_download: bool = False) -> dict:
    """Months in sequence (RAM-friendly), then gold over everything in silver, then the report."""
    paths = paths or Paths.from_env()
    results = {"months": [run_month(m, paths, skip_download) for m in months]}
    results["silver_months"] = list_months(paths, "silver")
    results["gold"] = task_gold(paths)
    results["gold_quality"] = task_quality_gold(paths)
    results["report"] = task_report(paths)
    return results
