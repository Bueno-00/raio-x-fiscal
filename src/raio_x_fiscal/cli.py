"""Command-line entry point (`rxf`), used by the Makefile on the VPS.

rxf pipeline --meses 202504-202509      # download -> bronze -> silver -> quality -> gold
rxf bronze --meses 202509                # one layer, one or more months
rxf ml-dataset / ml-train / ml-audit     # baseline descricao -> NCM
rxf publish                              # anonymised dataset + card for Kaggle/HF
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from raio_x_fiscal.config import Paths, list_months, validate_month
from raio_x_fiscal.pipeline import tasks


def parse_months(spec: list[str]) -> list[str]:
    """['202504-202506', '202509'] -> ['202504', '202505', '202506', '202509']."""
    months: list[str] = []
    for s in spec:
        if "-" in s:
            a, b = s.split("-", 1)
            validate_month(a)
            validate_month(b)
            y, m = int(a[:4]), int(a[4:])
            while f"{y}{m:02d}" <= b:
                months.append(f"{y}{m:02d}")
                m += 1
                if m == 13:
                    y, m = y + 1, 1
        else:
            months.append(validate_month(s))
    return sorted(set(months))


def _add_months(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument(
        "--meses",
        nargs="+",
        required=required,
        metavar="AAAAMM",
        help="meses AAAAMM ou intervalo AAAAMM-AAAAMM (ex.: 202504-202509)",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rxf", description="Raio-X Fiscal: pipeline e baseline de ML")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, helptext in (
        ("download", "baixa o zip do mes"),
        ("bronze", "zip -> parquet bruto"),
        ("silver", "bronze -> tabelas tipadas e limpas"),
        ("quality", "checagens de qualidade bronze+silver do mes"),
    ):
        _add_months(sub.add_parser(name, help=helptext))

    sp = sub.add_parser("pipeline", help="download -> bronze -> silver -> quality -> gold -> relatorio")
    _add_months(sp)
    sp.add_argument("--sem-download", action="store_true", help="usa os zips ja presentes em data/raw")

    sub.add_parser("gold", help="todas as particoes silver -> star schema + agregados + tabela de ML")
    sub.add_parser("report", help="gera reports/quality_report.md a partir de data/quality/*.json")

    ds = sub.add_parser("ml-dataset", help="split temporal + dedup a partir do gold")
    ds.add_argument("--teste", default=None, help="mes de teste AAAAMM (padrao: ultimo mes)")
    ds.add_argument("--validacao", default=None, help="mes de validacao AAAAMM (padrao: penultimo)")

    tr = sub.add_parser("ml-train", help="treina baselines por etapas retomaveis e grava reports/ml_results.md")
    tr.add_argument("--amostra", type=int, default=None, help="limita linhas de treino (depuracao)")
    tr.add_argument(
        "--etapa",
        default="tudo",
        choices=["features", "capitulo", "ncm", "avaliar", "tudo"],
        help="etapa a rodar (checkpoints em models/ckpt permitem retomar)",
    )
    tr.add_argument("--orcamento", type=float, default=None, help="segundos de orcamento da etapa (retoma depois)")

    au = sub.add_parser("ml-audit", help="auditoria de NCM no mes de teste")
    au.add_argument("--amostra", type=int, default=40, help="alertas para inspecao manual")

    sub.add_parser("publish", help="dataset anonimizado + dataset card em data/publish/")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    paths = Paths.from_env()
    paths.ensure()
    out: object

    if args.cmd in ("download", "bronze", "silver", "quality"):
        fn = {
            "download": tasks.task_download,
            "bronze": tasks.task_bronze,
            "silver": tasks.task_silver,
            "quality": tasks.task_quality_month,
        }[args.cmd]
        out = {m: fn(m, paths) for m in parse_months(args.meses)}
    elif args.cmd == "pipeline":
        out = tasks.run_pipeline(parse_months(args.meses), paths, skip_download=args.sem_download)
    elif args.cmd == "gold":
        out = {"gold": tasks.task_gold(paths), "quality": tasks.task_quality_gold(paths)}
    elif args.cmd == "report":
        out = tasks.task_report(paths)
    elif args.cmd == "ml-dataset":
        from raio_x_fiscal.ml.dataset import build_splits

        months = list_months(paths, "silver")
        test = args.teste or months[-1]
        valid = args.validacao or months[-2]
        out = build_splits(paths, test_month=test, valid_month=valid)
    elif args.cmd == "ml-train":
        from raio_x_fiscal.ml.train import train_and_evaluate

        out = train_and_evaluate(paths, stage=args.etapa, budget_s=args.orcamento, sample=args.amostra)
    elif args.cmd == "ml-audit":
        from raio_x_fiscal.ml.audit import run_audit

        out = run_audit(paths, sample_size=args.amostra)
    elif args.cmd == "publish":
        from raio_x_fiscal.publish.dataset import build_publish

        out = build_publish(paths)
    else:  # pragma: no cover
        raise SystemExit(2)

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
