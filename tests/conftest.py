"""Offline fixtures: a tiny monthly zip (latin-1, ';', Brazilian decimals) with known edge cases.

The fixture is generated from the schema contract, so the header always matches `schema.py`.
Edge cases on purpose:
- NCM with 7 digits (leading zero lost) and NCM '-1' (missing);
- CFOP invalid ('ABCD');
- a duplicated item row (same chave + numero produto);
- a note and its item with a 43-digit key (rejected);
- an item whose note is missing (orphan) and a note without items;
- a note emitted by a CPF (natural person) to test masking;
- a decimal with thousands separator ('1.234,56') and a note total that includes freight.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from raio_x_fiscal.config import CSV_SUFFIX, Paths
from raio_x_fiscal.pipeline.schema import raw_columns

MONTH = "202501"
K1 = "35250111222333000181550010000001001000000011"  # 44 digits
K2 = "35250111222333000181550010000001011000000022"
K3 = "3525011122233300018155001000000102100000003"  # 43 digits -> rejected
K4 = "35250111222333000181550010000001031000000044"  # note without items
K5 = "35250111222333000181550010000001041000000055"  # item without note (orphan)
K6 = "35250100000000000001550010000001051000000066"  # CPF emitter

MODELO = "55 - NF-E EMITIDA EM SUBSTITUIÇÃO AO MODELO 1 OU 1A"


def _header(chave, numero, emit, razao, ie, uf, mun, data="05/01/2025 00:00:00"):
    return {
        "CHAVE DE ACESSO": chave,
        "MODELO": MODELO,
        "SÉRIE": "1",
        "NÚMERO": numero,
        "NATUREZA DA OPERAÇÃO": "VENDA",
        "DATA EMISSÃO": data,
        "CPF/CNPJ Emitente": emit,
        "RAZÃO SOCIAL EMITENTE": razao,
        "INSCRIÇÃO ESTADUAL EMITENTE": ie,
        "UF EMITENTE": uf,
        "MUNICÍPIO EMITENTE": mun,
        "CÓDIGO ÓRGÃO SUPERIOR DESTINATÁRIO": "26000",
        "ÓRGÃO SUPERIOR DESTINATÁRIO": "Ministério da Educação",
        "CÓDIGO ÓRGÃO DESTINATÁRIO": "26243",
        "ÓRGÃO DESTINATÁRIO": "Universidade Federal X",
        "CNPJ DESTINATÁRIO": "24365710000183",
        "NOME DESTINATÁRIO": "UNIVERSIDADE FEDERAL X",
        "UF DESTINATÁRIO": "RN",
        "INDICADOR IE DESTINATÁRIO": "NÃO CONTRIBUINTE",
        "DESTINO DA OPERAÇÃO": "1 - OPERAÇÃO INTERNA",
        "CONSUMIDOR FINAL": "1 - CONSUMIDOR FINAL",
        "PRESENÇA DO COMPRADOR": "0 - NÃO SE APLICA",
    }


NOTAS = [
    (_header(K1, "1", "11222333000181", "DISTRIBUIDORA EXEMPLO LTDA", "123456789", "RN", "NATAL"), "791,95"),
    (_header(K2, "2", "11222333000181", "DISTRIBUIDORA EXEMPLO LTDA", "123456789", "RN", "NATAL"), "1.300,00"),
    (_header(K3, "3", "11222333000181", "DISTRIBUIDORA EXEMPLO LTDA", "123456789", "RN", "NATAL"), "10,00"),
    (_header(K4, "4", "11222333000181", "DISTRIBUIDORA EXEMPLO LTDA", "Sem informação", "RN", "NATAL"), "50,00"),
    (_header(K6, "5", "12345678901", "FULANO DE TAL", "-1", "SP", "SÃO PAULO"), "99,90"),
]

ITENS = [
    # chave, numero, numero_produto, descricao, ncm, ncm_desc, cfop, qtd, unid, vunit, vtotal
    (
        K1,
        "1",
        "1",
        "ARROZ TIPO 1",
        "10063021",
        "Arroz semibranqueado ou branqueado",
        "5102",
        "30,00",
        "UNIDAD",
        "20,99",
        "629,70",
    ),
    (
        K1,
        "1",
        "2",
        "FEIJÃO TIPO I",
        "7133399",
        "Outros feijões comuns, secos, em grãos",
        "5102",
        "25,00",
        "KG",
        "6,49",
        "162,25",
    ),
    (
        K1,
        "1",
        "2",
        "FEIJÃO TIPO I",
        "7133399",
        "Outros feijões comuns, secos, em grãos",
        "5102",
        "25,00",
        "KG",
        "6,49",
        "162,25",
    ),
    (
        K2,
        "2",
        "1",
        "(3 MODELOS) - BANNERS EM LONA, 120X150CM",
        "-1",
        "Sem informação",
        "6949",
        "1,00",
        "UNIDAD",
        "1.234,56",
        "1.234,56",
    ),
    (
        K2,
        "2",
        "2",
        "CANETA AZUL C/ TAMPA (10 UN)",
        "96081000",
        "Canetas esferográficas",
        "ABCD",
        "2,00",
        "UNIDAD",
        "5,00",
        "10,00",
    ),
    (K3, "3", "1", "LAPIS PRETO", "96091000", "Lápis", "5102", "1,00", "UNIDAD", "10,00", "10,00"),
    (
        K5,
        "6",
        "1",
        "ÁGUA MINERAL 20LT",
        "22011000",
        "Águas minerais",
        "5102",
        "4,00",
        "UNIDAD",
        "12,00",
        "48,00",
    ),
    (
        K6,
        "5",
        "1",
        "VIDRO TEMPERADO ESPESSURA 6MM",
        "70071900",
        "Vidros temperados",
        "5102",
        "1,00",
        "M2",
        "99,90",
        "99,90",
    ),
    (
        K6,
        "5",
        "2",
        "MESA DE MADEIRA",
        "94036000",
        "Outros móveis de madeira",
        "5933",
        "1,00",
        "UNIDAD",
        "0,00",
        "0,00",
    ),
]


def _csv(entity: str, rows: list[dict]) -> bytes:
    cols = raw_columns(entity)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue().encode("latin-1")


def nota_rows() -> list[dict]:
    out = []
    for h, valor in NOTAS:
        r = dict(h)
        r.update(
            {
                "EVENTO MAIS RECENTE": "Autorização de Uso",
                "DATA/HORA EVENTO MAIS RECENTE": "05/01/2025 13:13:00",
                "VALOR NOTA FISCAL": valor,
            }
        )
        out.append(r)
    return out


def item_rows() -> list[dict]:
    headers = {K1: NOTAS[0][0], K2: NOTAS[1][0], K3: NOTAS[2][0], K6: NOTAS[4][0]}
    headers[K5] = _header(K5, "6", "11222333000181", "DISTRIBUIDORA EXEMPLO LTDA", "123456789", "RN", "NATAL")
    out = []
    for chave, _num, nprod, desc, ncm, ncm_desc, cfop, qtd, unid, vu, vt in ITENS:
        r = dict(headers[chave])
        r.update(
            {
                "NÚMERO PRODUTO": nprod,
                "DESCRIÇÃO DO PRODUTO/SERVIÇO": desc,
                "CÓDIGO NCM/SH": ncm,
                "NCM/SH (TIPO DE PRODUTO)": ncm_desc,
                "CFOP": cfop,
                "QUANTIDADE": qtd,
                "UNIDADE": unid,
                "VALOR UNITÁRIO": vu,
                "VALOR TOTAL": vt,
            }
        )
        out.append(r)
    return out


def write_fixture_zip(raw_dir: Path, month: str = MONTH, item_header_override: list[str] | None = None) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / f"{month}_NFe.zip"
    item_csv = _csv("item", item_rows())
    if item_header_override is not None:
        body = item_csv.split(b"\n", 1)[1]
        head = ";".join(f'"{c}"' for c in item_header_override).encode("latin-1") + b"\n"
        item_csv = head + body
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{month}{CSV_SUFFIX['nota']}", _csv("nota", nota_rows()))
        zf.writestr(f"{month}{CSV_SUFFIX['item']}", item_csv)
        zf.writestr(f"{month}{CSV_SUFFIX['evento']}", _csv("evento", []))
    return zip_path


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(data=tmp_path / "data", models=tmp_path / "models")
    p.ensure()
    write_fixture_zip(p.raw)
    return p
