"""CLI month parsing and the Airflow DAG file (parsed without an Airflow install)."""

import ast
from pathlib import Path

import pytest

from raio_x_fiscal.cli import build_parser, parse_months
from raio_x_fiscal.pipeline import tasks

DAG_FILE = Path(__file__).resolve().parents[1] / "dags" / "raio_x_fiscal_dag.py"


def test_parse_months_ranges_and_lists():
    assert parse_months(["202504-202506"]) == ["202504", "202505", "202506"]
    assert parse_months(["202511-202602"]) == ["202511", "202512", "202601", "202602"]
    assert parse_months(["202509", "202504", "202509"]) == ["202504", "202509"]
    with pytest.raises(ValueError):
        parse_months(["2025-09"])
    with pytest.raises(ValueError):
        parse_months(["202513"])


def test_cli_parser_has_every_stage():
    p = build_parser()
    for cmd in (
        "download",
        "bronze",
        "silver",
        "quality",
        "pipeline",
        "gold",
        "report",
        "ml-dataset",
        "ml-train",
        "ml-audit",
        "publish",
    ):
        assert (
            p.parse_args(
                [cmd]
                + (["--meses", "202509"] if cmd in ("download", "bronze", "silver", "quality", "pipeline") else [])
            ).cmd
            == cmd
        )


def test_dag_file_wires_the_shared_tasks():
    """Every @task in the DAG delegates to a function that exists in pipeline.tasks."""
    tree = ast.parse(DAG_FILE.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "raio_x_fiscal.pipeline.tasks"
        for alias in node.names
    }
    assert imported == {
        "task_download",
        "task_bronze",
        "task_silver",
        "task_quality_month",
        "task_gold",
        "task_quality_gold",
        "task_report",
    }
    for name in imported:
        assert callable(getattr(tasks, name))
    task_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            (isinstance(d, ast.Name) and d.id == "task")
            or (isinstance(d, ast.Call) and getattr(d.func, "id", "") == "task")
            for d in node.decorator_list
        )
    }
    assert task_names == {
        "months",
        "download",
        "bronze",
        "silver",
        "quality",
        "gold",
        "quality_gold",
        "report",
    }


def test_dag_imports_in_airflow():
    # the repo has an `airflow/` folder (docker-compose), so check the real package, not the namespace
    pytest.importorskip("airflow.models", reason="apache-airflow nao instalado neste venv")
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(DAG_FILE.parent), include_examples=False)
    assert not bag.import_errors, bag.import_errors
    dag = bag.get_dag("raio_x_fiscal_pipeline")
    assert dag is not None
    assert set(dag.task_ids) == {
        "months",
        "download",
        "bronze",
        "silver",
        "quality",
        "gold",
        "quality_gold",
        "report",
    }
    assert dag.get_task("gold").upstream_task_ids == {"quality"}
    assert dag.get_task("report").upstream_task_ids == {"quality_gold"}
