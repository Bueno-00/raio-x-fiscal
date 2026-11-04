from datetime import date
from decimal import Decimal

import duckdb
import pytest

from raio_x_fiscal.pipeline import normalize as nz


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("20,99", Decimal("20.99")),
        ("-1", Decimal("-1")),
        ("  0,00 ", Decimal("0.00")),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_decimal_br(raw, expected):
    assert nz.parse_decimal_br(raw) == expected


def test_parse_date_br():
    assert nz.parse_date_br("01/09/2025 00:00:00") == date(2025, 9, 1)
    assert nz.parse_date_br("31/12/2024") == date(2024, 12, 31)
    assert nz.parse_date_br("2025-09-01") is None
    assert nz.parse_date_br(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10063021", "10063021"),
        ("7133399", "07133399"),  # leading zero lost in the CSV
        ("-1", None),
        ("", None),
        ("99999999", None),  # chapter 99 is not an NCM chapter
        ("77010000", None),  # chapter 77 is reserved
        ("00000000", None),
        ("123456", None),  # too short to be a dropped-zero case
        ("1006302A", None),
    ],
)
def test_normalize_ncm(raw, expected):
    assert nz.normalize_ncm(raw) == expected


def test_ncm_parts():
    assert nz.ncm_parts("07133399") == {
        "capitulo": "07",
        "posicao": "0713",
        "subposicao": "071333",
        "ncm": "07133399",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5102", "5102"), ("6949", "6949"), ("ABCD", None), ("4102", None), ("510", None), (None, None)],
)
def test_normalize_cfop(raw, expected):
    assert nz.normalize_cfop(raw) == expected


def test_is_valid_chave():
    assert nz.is_valid_chave("2" * 44)
    assert not nz.is_valid_chave("2" * 43)
    assert not nz.is_valid_chave("2" * 43 + "x")
    assert not nz.is_valid_chave(None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ARROZ TIPO 1", "arroz tipo 1"),
        ("  CANETA AZUL C/ TAMPA (10 UN) ", "caneta azul c tampa 10 un"),
        ("FEIJÃO TIPO I", "feijao tipo i"),
        ("CABO FLEXÍVEL 2,5MM² 750V", "cabo flexivel 2 5mm2 750v"),
        ("", ""),
        (None, ""),
        ("---", ""),
    ],
)
def test_normalize_description(raw, expected):
    assert nz.normalize_description(raw) == expected


def test_emitente_tipo():
    assert nz.emitente_tipo("11222333000181") == "CNPJ"
    assert nz.emitente_tipo("12345678901") == "CPF"
    assert nz.emitente_tipo("-1") == "OUTRO"
    assert nz.emitente_tipo(None) == "OUTRO"


def test_sql_and_python_rules_agree():
    """The silver layer runs the SQL version; inference runs the Python one. They must match."""
    samples = [
        "ARROZ TIPO 1",
        "FEIJÃO TIPO I",
        "CANETA AZUL C/ TAMPA (10 UN)",
        "Vidro Temperado 6mm",
        "cobas e, Elecsys THYROAB PC v2",
        "PARAFUSO 3,5 X 32MM - SUS: 07.02.03.062-7",
        "",
        "ÁGUA",
    ]
    ncms = ["10063021", "7133399", "-1", "99999999", "77010000", "", "0", "1006302A", "07133399"]
    cfops = ["5102", "ABCD", "4102", "6949", ""]
    con = duckdb.connect()

    def sql(expr: str, value: str):
        return con.execute(f"SELECT {expr} FROM (SELECT ?::VARCHAR AS v)", [value]).fetchone()[0]

    for s in samples:
        assert sql(nz.sql_normalize_description("v"), s) == nz.normalize_description(s), s
    for n in ncms:
        assert sql(nz.sql_normalize_ncm("v"), n) == nz.normalize_ncm(n), n
    for c in cfops:
        assert sql(nz.sql_normalize_cfop("v"), c) == nz.normalize_cfop(c), c
    for v in ["1.234,56", "20,99", "-1", "abc"]:
        assert sql(nz.sql_decimal_br("v", 2), v) == nz.parse_decimal_br(v), v
    for d in ["01/09/2025 00:00:00", "2025-09-01"]:
        assert sql(nz.sql_date_br("v"), d) == nz.parse_date_br(d), d
