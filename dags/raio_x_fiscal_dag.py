"""Airflow DAG: the same tasks the CLI runs, orchestrated with dynamic task mapping per month.

    months -> download[m] -> bronze[m] -> silver[m] -> quality[m] -> gold -> quality_gold -> report

Months come from the DAG param `meses` (list of AAAAMM), so a backfill of one month and a run
over six months are the same DAG. Each task is a thin wrapper around
`raio_x_fiscal.pipeline.tasks`, which is exactly what `make pipeline` calls on the VPS; the DAG
adds retries, one task instance per month and the dependency graph, nothing else.

Each step is mapped over the previous step's output (the month string is passed through), so
every month has its own task instance per step with its own retries and logs. Airflow needs the
whole upstream list to size the next map, so a step starts only after the previous step finished
for every month: that is fine here, the pipeline is bound by RAM, not by wall time.

Run locally with `docker compose -f airflow/docker-compose.yml up` (never on the production VPS).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models.param import Param

log = logging.getLogger(__name__)

DEFAULT_MONTHS = ["202504", "202505", "202506", "202507", "202508", "202509"]

default_args = {
    "owner": "rafael",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
}


@dag(
    dag_id="raio_x_fiscal_pipeline",
    description="NF-e do Portal da Transparencia: download -> bronze -> silver -> quality -> gold",
    schedule="0 6 10 * *",  # dia 10 de cada mes, quando o mes anterior ja esta publicado
    start_date=datetime(2025, 10, 1),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=2,  # RAM-bound pipeline: two months at a time is plenty
    default_args=default_args,
    params={"meses": Param(DEFAULT_MONTHS, type="array", description="meses AAAAMM a processar")},
    tags=["nfe", "medalhao", "duckdb"],
    doc_md=__doc__,
)
def raio_x_fiscal_pipeline():
    @task
    def months(**context) -> list[str]:
        from raio_x_fiscal.config import validate_month

        return [validate_month(m) for m in context["params"]["meses"]]

    @task(retries=3, retry_delay=timedelta(minutes=10))
    def download(month: str) -> str:
        from raio_x_fiscal.pipeline.tasks import task_download

        log.info("download %s -> %s", month, task_download(month))
        return month

    @task
    def bronze(month: str) -> str:
        from raio_x_fiscal.pipeline.tasks import task_bronze

        log.info("bronze %s: %s", month, task_bronze(month))
        return month

    @task
    def silver(month: str) -> str:
        from raio_x_fiscal.pipeline.tasks import task_silver

        log.info("silver %s: %s", month, task_silver(month))
        return month

    @task
    def quality(month: str) -> str:
        from raio_x_fiscal.pipeline.tasks import task_quality_month

        log.info("quality %s: %s", month, task_quality_month(month))
        return month

    @task
    def gold(months_done: list[str]) -> dict:
        from raio_x_fiscal.pipeline.tasks import task_gold

        log.info("gold apos %s", months_done)
        return task_gold()

    @task
    def quality_gold(counts: dict) -> dict:
        from raio_x_fiscal.pipeline.tasks import task_quality_gold

        log.info("gold counts: %s", counts)
        return task_quality_gold()

    @task
    def report(statuses: dict) -> str:
        from raio_x_fiscal.pipeline.tasks import task_report

        log.info("gold quality: %s", statuses)
        return task_report()

    done = quality.expand(month=silver.expand(month=bronze.expand(month=download.expand(month=months()))))
    report(quality_gold(gold(done)))


raio_x_fiscal_pipeline()
