"""Testes do app web, dos formatos de importação e das notas de exemplo dos 8 comércios.

Sem o modelo (rápido e offline): as regras rodam; a checagem "NCM x descrição" fica de fora.
"""

from __future__ import annotations

import io
import sys
import zipfile

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from raio_x_fiscal.app import servidor as SRV
from raio_x_fiscal.produto import exemplos_lojas as EL
from raio_x_fiscal.produto import formatos as FMT
from raio_x_fiscal.produto import motor
from raio_x_fiscal.produto import regras as R
from raio_x_fiscal.produto.ncm_tabela import HistoricoNCM
from raio_x_fiscal.produto.nfe import ler_memoria


@pytest.fixture(scope="module")
def historico():
    return HistoricoNCM.carregar(None)


@pytest.fixture(scope="module")
def cliente(historico):
    app = SRV.criar_app(motor.Contexto(historico=historico), com_chat=False)
    return TestClient(app)


# ---------------------------------------------------------------------------------------------
# Notas de exemplo dos 8 comércios
# ---------------------------------------------------------------------------------------------


def test_catalogo_tem_todos_os_produtos_e_vem_do_dado_publico():
    bons, antigos = EL.ler_catalogo()
    for n in EL.NEGOCIOS:
        assert all(d in bons for d in n.produtos), n.id
        assert all(d in antigos for d in n.antigos), n.id
        assert all(
            int(bons[d]["vezes_no_dado_publico"]) >= 8 and float(bons[d]["consenso"]) >= 0.85 for d in n.produtos
        )
    for k, v in EL.COMPRAS.items():
        assert all(d in bons for d in v), k


def test_exemplos_sao_deterministicos_e_ficticios():
    a, b = EL.zip_bytes(), EL.zip_bytes()
    assert a == b
    arqs = EL.arquivos()
    xmls = [v for k, v in arqs.items() if k.endswith(".xml")]
    assert len(xmls) > 100
    assert all(b"<tpAmb>2</tpAmb>" in x for x in xmls)  # homologação: sem valor fiscal
    assert all(b"EXEMPLO" in x for x in xmls)
    nomes = {n.nome for n in EL.NEGOCIOS}
    assert all("EXEMPLO" in nome for nome in nomes)


def test_regras_pegam_todos_os_erros_plantados_que_nao_dependem_do_modelo(historico):
    arqs = EL.arquivos()
    lt = ler_memoria(list(arqs.items()))
    assert len({n.grupo for n in lt.notas}) == 8 and lt.regras_texto  # pasta por empresa dentro do zip
    ctx = motor.Contexto(historico=historico, escritorio=R.RegrasDoEscritorio.de_texto(lt.regras_texto))
    res = motor.auditar_notas(lt, ctx)
    _, _, gab = EL.montar()
    c = EL.conferir(res, gab)
    for tipo, d in c["por_tipo"].items():
        if tipo == "NCM_DE_OUTRO_PRODUTO":  # precisa do modelo
            continue
        assert d["pegos"] == d["itens"], (tipo, d)
    assert c["limpos_sem_alerta"] == c["itens_limpos"]  # sem o modelo, nenhum alarme falso nos itens limpos
    assert res.resumo["aceitos_escritorio"] > 0  # a regra do escritório que veio no zip foi usada


def test_zero_perdido_e_codigo_antigo_ganham_sugestao_certa(historico):
    t = historico.atual
    a = R.regra_ncm_formato("4015021", tabela=t)[0]
    assert a.nivel == R.VERMELHO and a.ncm_sugerido == "04015021" and "zero" in a.motivo
    assert R.codigos_do_grupo("65061000", t) == ["65061010", "65061090"]
    achados = R.regra_ncm_tabela("65061000", None, historico)
    assert achados[0].regra == "NCM_INEXISTENTE" and "6506.10.10" in achados[0].motivo
    assert motor._sugestao_ncm(achados, [("65050032", 0.6), ("65061090", 0.2)], "65061000", t) == "65061090"


# ---------------------------------------------------------------------------------------------
# App web
# ---------------------------------------------------------------------------------------------


def test_pagina_e_seguranca(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "Raio-X" in r.text
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    e = cliente.get("/api/estado").json()
    assert e["chat"] == {"ativo": False} and {s["id"] for s in e["sistemas"]} >= {"bling", "olist", "omie"}


def test_exemplo_envio_do_zip_e_relatorio(cliente, monkeypatch):
    # O envio nunca passa pelo parser de formulário do Starlette (que grava arquivo temporário).
    from starlette.requests import Request

    def proibido(*a, **k):
        raise AssertionError("request.form() grava em disco; o app não pode usar")

    monkeypatch.setattr(Request, "form", proibido)
    ex = cliente.post("/api/exemplo").json()
    assert ex["resumo"]["notas"] > 100 and ex["conferencia"]["erros_plantados"] > 100
    z = cliente.get("/api/exemplo/notas.zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    up = cliente.post("/api/notas", files=[("f", ("notas.zip", z.content, "application/zip"))])
    j = up.json()
    assert up.status_code == 200, j
    assert j["resumo"]["itens"] == ex["resumo"]["itens"] and len(j["empresas"]) == 8
    x = cliente.get(f"/api/relatorio/{j['token']}")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    lista = cliente.post("/api/exportar", json={"token": j["token"], "sistema": "dominio"})
    assert lista.status_code == 200
    wb = pd.read_excel(io.BytesIO(lista.content), sheet_name=None)
    assert set(wb) == {"Correção de NCM", "Como usar"} and len(wb["Correção de NCM"]) > 0


def test_envio_invalido_grande_e_limite_por_ip(historico, monkeypatch):
    monkeypatch.setitem(SRV.LIMITES, "envio", [(2, 3600), (5, 86400)])
    monkeypatch.setattr(SRV, "MAX_ENVIO", 50_000)
    c = TestClient(SRV.criar_app(motor.Contexto(historico=historico), com_chat=False))
    r = c.post("/api/notas", files=[("f", ("a.txt", b"oi", "text/plain"))])
    assert r.status_code == 400 and "xml" in r.json()["erro"].lower()
    r = c.post("/api/notas", files=[("f", ("a.zip", b"x" * 60_000, "application/zip"))])
    assert r.status_code == 413
    r = c.post("/api/notas", files=[("f", ("a.xml", b"<x/>", "text/xml"))])
    assert r.status_code == 429 and "min" in r.json()["erro"]


def test_cadastro_exemplo_gera_csv_do_bling_so_com_as_linhas_aprovadas(cliente):
    cad = cliente.post("/api/cadastro/exemplo").json()
    assert cad["bling"] and cad["tem_id"] and cad["resumo"]["vermelho"] >= 2
    aprov = [{"linha": it["linha"], "ncm": it["ncm_sugerido"]} for it in cad["itens"] if it["ncm_sugerido"]][:3]
    r = cliente.post("/api/exportar", json={"token": cad["token"], "sistema": "bling", "aprovados": aprov})
    assert r.status_code == 200 and r.headers["content-disposition"].endswith('-bling.csv"')
    df = pd.read_csv(io.BytesIO(r.content), sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert list(df.columns)[:5] == ["ID", "Código", "Descrição", "Unidade", "NCM"] and len(df) == len(aprov) >= 2
    assert all(len(v) == 10 and v[4] == "." for v in df["NCM"])  # mesmo formato da coluna (com pontos)
    vazio = cliente.post("/api/exportar", json={"token": cad["token"], "sistema": "bling", "aprovados": []})
    assert vazio.status_code == 400


def test_pesquisa_sem_modelo_avisa(cliente):
    r = cliente.post("/api/pesquisar", json={"q": "leite condensado"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------------------------
# Formatos de importação
# ---------------------------------------------------------------------------------------------


def test_olist_divide_em_partes_de_500_e_mantem_layout():
    df = pd.DataFrame(
        {
            "ID": [str(i) for i in range(1, 1201)],
            "Código (SKU)": [f"S{i}" for i in range(1200)],
            "NCM": ["1902.19.00"] * 1200,
        }
    )
    arq = FMT.arquivo_pronto(
        "olist", df, {"separador": ";", "codificacao": "utf-8"}, "NCM", dict.fromkeys(range(1200), "19023000")
    )
    assert arq.nome.endswith(".zip") and arq.linhas == 1200
    with zipfile.ZipFile(io.BytesIO(arq.dados)) as zf:
        partes = [pd.read_csv(zf.open(n), sep=";", dtype=str, encoding="utf-8-sig") for n in sorted(zf.namelist())]
    assert [len(p) for p in partes] == [500, 500, 200]
    assert list(partes[0].columns) == ["ID", "Código (SKU)", "NCM"] and set(partes[0]["NCM"]) == {"1902.30.00"}


def test_arquivo_pronto_exige_id_e_lista_tem_passos_e_fontes():
    df = pd.DataFrame({"Código": ["A"], "NCM": ["19021900"]})
    with pytest.raises(ValueError, match="coluna ID"):
        FMT.arquivo_pronto("bling", df, {}, "NCM", {0: "19023000"})
    for s in ("omie", "contaazul", "dominio", "generico"):
        arq = FMT.lista_correcao(s, [{"Código do produto": "A", "NCM atual": "19021900", "NCM novo": "19023000"}])
        como = pd.read_excel(io.BytesIO(arq.dados), sheet_name="Como usar", header=None)[0].astype(str).tolist()
        assert FMT.SISTEMAS[s].nome in como[0]
        if FMT.SISTEMAS[s].fontes:
            assert any(str(x).startswith("http") for x in como)


# ---------------------------------------------------------------------------------------------
# Chat (projeto à parte): só entra com o pacote instalado E o arquivo de ambiente existindo
# ---------------------------------------------------------------------------------------------


def test_chat_so_monta_com_pacote_e_env(historico, tmp_path, monkeypatch):
    pkg = tmp_path / "pacotes" / "pergunte_ao_simples"
    (pkg / "static").mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "from fastapi import APIRouter\n"
        "def criar_router():\n"
        "    r = APIRouter()\n"
        "    @r.get('/ping')\n"
        "    def ping():\n"
        "        return {'ok': True}\n"
        "    return r\n"
    )
    (pkg / "static" / "chat-simples.js").write_text("window.ChatSimples={definirContexto:function(){}};")
    monkeypatch.syspath_prepend(str(tmp_path / "pacotes"))
    sys.modules.pop("pergunte_ao_simples", None)

    monkeypatch.delenv("CHAT_ENV_FILE", raising=False)
    sem_env = TestClient(SRV.criar_app(motor.Contexto(historico=historico)))
    assert sem_env.get("/api/estado").json()["chat"] == {"ativo": False}
    assert sem_env.get("/api/chat/ping").status_code == 404

    env = tmp_path / "chat.env"
    env.write_text("NAO_LER=1\n")
    monkeypatch.setenv("CHAT_ENV_FILE", str(env))
    com = TestClient(SRV.criar_app(motor.Contexto(historico=historico)))
    assert com.get("/api/estado").json()["chat"] == {"ativo": True, "js": "/chat/chat-simples.js"}
    assert com.get("/api/chat/ping").json() == {"ok": True}
    assert "ChatSimples" in com.get("/chat/chat-simples.js").text
    sys.modules.pop("pergunte_ao_simples", None)
