"""Testes do produto (3 portas, regras, regra do escritório, robô da tabela NCM, relatório, painel).

Tudo offline: as notas são as sintéticas de `produto/exemplos.py`, a tabela NCM é a cópia do pacote
e o modelo, quando aparece, é um modelo minúsculo treinado aqui mesmo.
"""

from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from raio_x_fiscal.ml.features import TextFeaturizer
from raio_x_fiscal.ml.fit import fit_hierarchical
from raio_x_fiscal.produto import cadastro as CAD
from raio_x_fiscal.produto import exemplos, motor, relatorio
from raio_x_fiscal.produto import regras as R
from raio_x_fiscal.produto.ncm_tabela import SEED, HistoricoNCM, TabelaNCM, atualizar_tabela, hash_conteudo, ler_json
from raio_x_fiscal.produto.nfe import ler_entrada, parse_xml


@pytest.fixture(scope="module")
def pasta_exemplos(tmp_path_factory):
    d = tmp_path_factory.mktemp("exemplos")
    exemplos.gerar(d)
    return d


@pytest.fixture(scope="module")
def historico():
    return HistoricoNCM.carregar(None)


@pytest.fixture(scope="module")
def resultado(pasta_exemplos, historico):
    ctx = motor.Contexto(
        historico=historico, escritorio=R.RegrasDoEscritorio.ler(pasta_exemplos / "regras-do-escritorio.csv")
    )
    return motor.auditar_notas(ler_entrada(pasta_exemplos / "notas"), ctx)


def _item(res, numero, descricao):
    df = res.itens
    linha = df[(df["numero"] == str(numero)) & (df["descricao"] == descricao)]
    assert len(linha) == 1, (numero, descricao)
    return linha.iloc[0]


# ---------------------------------------------------------------------------------------------
# Porta 1: leitura dos XML
# ---------------------------------------------------------------------------------------------


def test_le_pasta_zip_e_cancelamento(pasta_exemplos):
    lt = ler_entrada(pasta_exemplos / "notas")
    assert len(lt.notas) == 15 and not lt.avisos
    grupos = {n.grupo for n in lt.notas}
    assert grupos == {"loja-exemplo-a", "distribuidora-exemplo-b", "oficina-exemplo-c"}  # o .zip vira grupo
    canceladas = [n for n in lt.notas if n.cancelada]
    assert len(canceladas) == 1 and canceladas[0].numero == "2005"
    n = next(n for n in lt.notas if n.numero == "102")
    assert n.emit_uf == "SP" and n.crt == "1" and n.data_emissao == date(2026, 10, 12)
    assert [i.ncm for i in n.itens] == ["01012100", "09011110", "48181000", "34025000"]
    assert len(n.chave) == 44


def test_le_zip_solto_e_ignora_repetida(pasta_exemplos, tmp_path):
    origem = next((pasta_exemplos / "notas" / "loja-exemplo-a").glob("*.xml"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mes/nota.xml", origem.read_bytes())
        zf.writestr("mes/copia.xml", origem.read_bytes())
    (tmp_path / "notas.zip").write_bytes(buf.getvalue())
    lt = ler_entrada(tmp_path / "notas.zip")
    assert len(lt.notas) == 1 and any("repetida" in a for a in lt.avisos)


def test_recusa_xml_com_doctype_e_xml_quebrado():
    bomba = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    nota, _, aviso = parse_xml(bomba, "bomba.xml", None)
    assert nota is None and "DOCTYPE" in aviso
    nota, _, aviso = parse_xml(b"<nfeProc><NFe>", "quebrado.xml", None)
    assert nota is None and "não é um XML válido" in aviso


# ---------------------------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------------------------


def test_gtin():
    assert R.gtin_valido(exemplos.gtin_com_dv("789100000001"))
    assert not R.gtin_valido("7891000000127")
    assert not R.gtin_valido("123")
    assert R.regra_gtin(None) == [] and R.regra_gtin("7891000000127")[0].nivel == R.AMARELO


@pytest.mark.parametrize(
    ("cfop", "tp", "uf_e", "uf_d", "pres", "nivel", "sugerido"),
    [
        ("5102", "1", "SP", "SP", "9", None, None),  # certo
        ("5102", "1", "MG", "SP", "9", R.AMARELO, "6102"),  # interna numa nota para outro estado
        ("6102", "1", "MG", "MG", "9", R.AMARELO, "5102"),  # interestadual dentro do estado
        ("5102", "1", "SP", "MG", "1", R.VERDE, None),  # venda presencial: aceito sozinho
        ("1102", "1", "SP", "SP", "9", R.VERMELHO, None),  # CFOP de entrada em nota de saída
        ("51O2", "1", "SP", "SP", "9", R.VERMELHO, None),  # formato
        ("5102", "1", "SP", "EX", "9", R.AMARELO, "7102"),  # exportação
    ],
)
def test_regra_cfop(cfop, tp, uf_e, uf_d, pres, nivel, sugerido):
    ach = R.regra_cfop(cfop, tp, uf_e, uf_d, None, pres, "55", {"6102", "5102", "7102"})
    if nivel is None:
        assert ach == []
    else:
        assert ach[0].nivel == nivel and ach[0].cfop_sugerido == sugerido


def test_regra_cfop_nfce_e_interna():
    assert R.regra_cfop("5102", "1", "SP", None, None, "1", "65") == []


def test_regra_cst_regime():
    assert R.regra_cst_regime("1", "00", None)[0].regra == "CST_REGIME"
    assert R.regra_cst_regime("3", None, "102")[0].nivel == R.VERMELHO
    assert R.regra_cst_regime("1", None, "102") == [] and R.regra_cst_regime("3", "00", None) == []


def test_regra_ncm_formato_e_servico():
    assert R.regra_ncm_formato("3306100")[0].nivel == R.VERMELHO
    assert R.regra_ncm_formato("00")[0].nivel == R.AMARELO
    assert R.regra_ncm_formato("00", servico=True) == []
    assert R.regra_ncm_formato("04029900") == []


def _tabela(codigos: dict[str, str], desde: date, inicio: str = "01/04/2022") -> TabelaNCM:
    noms = [{"Codigo": f"{c[:4]}.{c[4:6]}.{c[6:]}", "Descricao": d, "Data_Inicio": inicio} for c, d in codigos.items()]
    return TabelaNCM.from_json({"Ato": "teste", "Nomenclaturas": noms}, desde)


def test_regra_ncm_tabela_por_data():
    v1 = _tabela({"34022000": "Detergente antigo", "04029900": "Outros"}, date(2026, 1, 1))
    v2 = _tabela({"34025000": "Detergente novo", "04029900": "Outros"}, date(2026, 6, 1))
    hist = HistoricoNCM([v1, v2])
    assert hist.na_data(date(2025, 12, 31)) is None and hist.na_data(date(2026, 3, 1)) is v1
    # nota de março: o código antigo valia
    assert R.regra_ncm_tabela("34022000", date(2026, 3, 1), hist) == []
    # nota de julho: já tinha saído da tabela -> vermelho
    assert R.regra_ncm_tabela("34022000", date(2026, 7, 1), hist)[0].nivel == R.VERMELHO
    # nota mais velha que a 1ª tabela guardada: só dá para comparar com hoje -> amarelo
    assert R.regra_ncm_tabela("34022000", date(2025, 5, 1), hist)[0].nivel == R.AMARELO
    v3 = _tabela({"34025000": "Detergente novo"}, date(2026, 6, 1), inicio="01/06/2026")
    ach = R.regra_ncm_tabela("34025000", date(2026, 7, 1), HistoricoNCM([v3]))
    assert ach == []
    ach = R.regra_ncm_tabela("34025000", date(2025, 5, 1), HistoricoNCM([v3]))
    assert ach[0].regra == "NCM_VIGENCIA"


def test_regra_do_escritorio():
    texto = (
        "# comentário\ncnpj_empresa;regra;cfop;ncm;codigo_produto;motivo\n11.222.333/0001-81;cfop_uf;5102;;;balcão\n"
    )
    reg = R.RegrasDoEscritorio.de_texto(texto)
    assert len(reg.excecoes) == 1 and reg.excecoes[0].cnpj_empresa == "11222333000181"
    a = R.Achado("CFOP_UF", R.AMARELO, "x")
    reg.aplicar([a], "11222333000181", "11222333000181", "5102", "04029900", "A1")
    assert a.aceito == "balcão" and a.nivel_efetivo == R.VERDE
    b = R.Achado("CFOP_UF", R.AMARELO, "x")
    reg.aplicar([b], "99999999000199", "99999999000199", "5102", "04029900", "A1")
    assert b.aceito is None  # outra empresa: continua amarelo


# ---------------------------------------------------------------------------------------------
# Motor nas notas de exemplo (sem modelo: só regras)
# ---------------------------------------------------------------------------------------------


def test_motor_regras_nas_notas_de_exemplo(resultado):
    s = resultado.resumo
    assert s["notas"] == 15 and s["itens"] == 41
    assert _item(resultado, 102, "CAFE TORRADO E MOIDO 500G")["regras"] == "PRODUTO_NCM_DIVERGENTE"
    assert _item(resultado, 102, "CAFE TORRADO E MOIDO 500G")["ncm_sugerido"] == "09012100"
    assert _item(resultado, 102, "PAPEL HIGIENICO FOLHA DUPLA 12 ROLOS")["regras"] == "GTIN_INVALIDO"
    sabao = _item(resultado, 104, "SABAO EM PO 1KG")  # nota de 07/11/2026: a tabela do dia já vale
    assert sabao["semaforo"] == "vermelho" and "NCM_INEXISTENTE" in sabao["regras"]
    iogurte = _item(resultado, 103, "IOGURTE NATURAL 170G")  # nota antiga: só amarelo
    assert iogurte["semaforo"] == "amarelo"
    assert _item(resultado, 103, "BISCOITO RECHEADO CHOCOLATE 140G")["regras"] == "CST_REGIME"
    assert _item(resultado, 103, "CREME DENTAL 90G")["regras"] == "NCM_AUSENTE"
    assert _item(resultado, 2002, "CABO FLEXIVEL 2,5MM 750V ROLO 100M")["cfop_sugerido"] == "6102"
    assert _item(resultado, 2003, "LAMPADA LED BULBO 9W BIVOLT")["cfop_sugerido"] == "5102"
    assert _item(resultado, 105, "ACUCAR CRISTAL 5KG")["semaforo"] == "verde"  # presencial
    rj = _item(resultado, 106, "OLEO DE SOJA REFINADO 900ML")
    assert rj["semaforo"] == "verde" and rj["aceitas_escritorio"] == "CFOP_UF"
    assert _item(resultado, 301, "MAO DE OBRA TROCA DE OLEO")["semaforo"] == "verde"  # serviço
    assert _item(resultado, 2005, "PNEU 175/70 R14")["regras"] == "NOTA_CANCELADA"
    assert _item(resultado, 9001, "PARAFUSO SEXTAVADO ACO ZINCADO M8X40")["sentido"] == "entrada"
    assert s["aceitos_escritorio"] == 2


def test_empresa_e_sentido(resultado):
    emp = resultado.empresas.set_index("grupo")
    assert emp.loc["loja-exemplo-a", "empresa_cnpj"] == "11222333000181"
    assert emp.loc["loja-exemplo-a", "empresa"] == "LOJA EXEMPLO A LTDA"
    assert set(resultado.itens["sentido"]) == {"saída", "entrada"}


# ---------------------------------------------------------------------------------------------
# Motor com um modelo minúsculo (checagem NCM x descrição e porta 3)
# ---------------------------------------------------------------------------------------------


class _Pred:
    def __init__(self, featurizer, model):
        self.featurizer, self.model = featurizer, model


@pytest.fixture(scope="module")
def classificador():
    textos = {
        "10063021": ["arroz tipo 1 {m} 5kg", "arroz branco {m}", "arroz agulhinha {m} 1kg"],
        "96081000": ["caneta esferografica azul {m}", "caneta {m} ponta fina", "caneta azul caixa {m}"],
        "04029900": ["leite condensado {m} 395g", "leite condensado {m} lata", "leite condensado caixa {m}"],
        "07061000": ["cenoura {m} kg", "cenoura fresca {m}", "cenoura extra {m}"],
    }
    marcas = ["alfa", "beta", "gama", "delta", "omega", "sigma", "kappa", "zeta"]
    rows = [(t.format(m=m), ncm) for ncm, ts in textos.items() for t in ts for m in marcas]
    df = pd.DataFrame(rows, columns=["d", "ncm"]).drop_duplicates("d")
    feat = TextFeaturizer(word_min_df=1, char_min_df=1)
    X = feat.fit_transform(df["d"].tolist())
    model = fit_hierarchical(X, df["ncm"].to_numpy(dtype=object), sw=np.ones(len(df), dtype=np.float32))
    model.calibrate(X, df["ncm"].to_numpy(dtype=object))
    c = motor.Classificador(_Pred(feat, model), limiar_vermelho=0.5)
    c.info = "modelo de teste"
    return c


def test_modelo_aponta_ncm_que_nao_combina(pasta_exemplos, historico, classificador):
    ctx = motor.Contexto(historico=historico, classificador=classificador, limiar_amarelo=0.3)
    res = motor.auditar_notas(ler_entrada(pasta_exemplos / "notas"), ctx)
    cenoura = _item(res, 102, "CENOURA KG")
    assert cenoura["semaforo"] == "vermelho" and "NCM_MODELO" in cenoura["regras"]
    assert cenoura["ncm_sugerido"] == "07061000"
    assert _item(res, 101, "LEITE CONDENSADO 395G")["semaforo"] == "verde"


def test_pesquisa_devolve_ncm_com_descricao_oficial(historico, classificador):
    ctx = motor.Contexto(historico=historico, classificador=classificador)
    res = motor.pesquisar("leite condensado 395 g", ctx, k=3)
    assert res[0]["ncm"] == "04029900" and res[0]["ncm_formatado"] == "0402.99.00"
    assert "Leite" in res[0]["descricao_oficial"] and 0 < res[0]["confianca"] <= 1
    assert len(res) <= 3


def test_pesquisa_sem_modelo_explica(historico):
    with pytest.raises(RuntimeError, match="modelo"):
        motor.pesquisar("arroz", motor.Contexto(historico=historico))


# ---------------------------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------------------------


def test_relatorio_html_escapa_texto_da_nota(resultado, tmp_path):
    res = resultado
    res.itens.loc[res.itens.index[0], "descricao"] = '<script>alert("x")</script>'
    h = relatorio.html_notas(res, "teste")
    assert "<script>alert" not in h and "&lt;script&gt;" in h
    assert h.count("<script>") == 1  # só o script do filtro
    out = relatorio.xlsx_notas(res, tmp_path / "r.xlsx")
    from openpyxl import load_workbook

    wb = load_workbook(out)
    assert wb.sheetnames == ["Resumo", "Itens", "Notas", "Correção de cadastro", "Regra do escritório"]
    assert wb["Itens"].max_row == res.resumo["itens"] + 1


# ---------------------------------------------------------------------------------------------
# Porta 2: cadastro (formato da exportação do Bling) e exportação para importar de volta
# ---------------------------------------------------------------------------------------------


def test_cadastro_bling_ida_e_volta(pasta_exemplos, historico, tmp_path):
    df, info = CAD.ler_planilha(pasta_exemplos / "cadastro-loja-a.csv")
    assert info["separador"] == ";" and CAD.eh_exportacao_bling(list(df.columns))
    assert CAD.achar_colunas(list(df.columns)) == {
        "codigo": "Código",
        "descricao": "Descrição",
        "ncm": "NCM",
        "gtin": "GTIN/EAN",
    }
    out, s = CAD.auditar_cadastro(df, motor.Contexto(historico=historico))
    assert s["produtos"] == 12
    sabao = out[out["Código"] == "A-0301"].iloc[0]
    assert sabao["semaforo"] == "vermelho" and "NCM_INEXISTENTE" in sabao["regras"]
    assert out[out["Código"] == "A-0303"].iloc[0]["semaforo"] == "amarelo"  # GTIN inválido

    # a pessoa aprova 2 trocas na planilha de correção
    xlsx = relatorio.xlsx_cadastro(out, s, tmp_path / "correcao.xlsx")
    corr = pd.read_excel(xlsx, sheet_name="Correção", dtype=str).fillna("")
    corr.loc[corr["Código"] == "A-0301", "ncm_aprovado"] = "34025000"
    corr.loc[corr["Código"] == "A-0201", "ncm_aprovado"] = "0706.10.00"
    with pd.ExcelWriter(xlsx) as w:
        corr.to_excel(w, sheet_name="Correção", index=False)
    r = CAD.exportar_aprovados(xlsx, tmp_path / "saida", max_linhas=1)
    assert r["linhas_alteradas"] == 2 and r["layout_bling"] and len(r["arquivos"]) == 2  # 1 por arquivo
    partes = pd.concat(pd.read_excel(a, dtype=str).fillna("") for a in r["arquivos"])
    assert list(partes.columns) == list(df.columns)  # mesmo layout, nenhuma coluna a mais ou a menos
    assert set(partes["NCM"]) == {"3402.50.00", "0706.10.00"}  # formato com pontos, como veio
    assert set(partes["ID"]) == {"900006", "900005"} and set(partes["Preço"]) == {"12,90", "4,50"}


def test_exportar_recusa_ncm_aprovado_errado(pasta_exemplos, historico, tmp_path):
    df, _ = CAD.ler_planilha(pasta_exemplos / "cadastro-loja-a.csv")
    out, s = CAD.auditar_cadastro(df, motor.Contexto(historico=historico))
    xlsx = relatorio.xlsx_cadastro(out, s, tmp_path / "c.xlsx")
    corr = pd.read_excel(xlsx, sheet_name="Correção", dtype=str).fillna("")
    corr.loc[corr.index[0], "ncm_aprovado"] = "1234"
    with pd.ExcelWriter(xlsx) as w:
        corr.to_excel(w, sheet_name="Correção", index=False)
    with pytest.raises(ValueError, match="formato errado"):
        CAD.exportar_aprovados(xlsx, tmp_path / "s")


# ---------------------------------------------------------------------------------------------
# Robô da tabela NCM (sem internet: o download é trocado por uma função)
# ---------------------------------------------------------------------------------------------


def test_robo_tabela_ncm(tmp_path):
    base = ler_json(SEED)
    dia = datetime(2026, 11, 8, 6, 0)
    r1 = atualizar_tabela(tmp_path, baixar=lambda: base, agora=dia)
    assert r1["resultado"].startswith("primeira versão") and r1["arquivo"]
    # no dia seguinte só muda o "Vigente em": não é mudança
    outro_dia = dict(base, Data_Ultima_Atualizacao_NCM="Vigente em 09/11/2026")
    assert hash_conteudo(outro_dia) == hash_conteudo(base)
    r2 = atualizar_tabela(tmp_path, baixar=lambda: outro_dia, agora=datetime(2026, 11, 9, 6, 0))
    assert r2["resultado"] == "sem mudança"
    # uma resolução nova tira um código e cria outro
    noms = [n for n in base["Nomenclaturas"] if n["Codigo"] != "3402.50.00"]
    noms.append({"Codigo": "3402.50.10", "Descricao": "Novo", "Data_Inicio": "10/11/2026", "Data_Fim": "31/12/9999"})
    nova = dict(base, Nomenclaturas=noms, Ato="Resolução Gecex nº 999/2026")
    r3 = atualizar_tabela(tmp_path, baixar=lambda: nova, agora=datetime(2026, 11, 10, 6, 0))
    assert r3["resultado"] == "mudou" and r3["entraram"] == 1 and r3["sairam"] == 1

    # site fora do ar: registra erro, não quebra
    def falha():
        raise RuntimeError("timeout")

    r4 = atualizar_tabela(tmp_path, baixar=falha, agora=datetime(2026, 11, 11, 6, 0))
    assert r4["resultado"] == "erro" and "timeout" in r4["detalhe"]
    registro = (tmp_path / "ncm" / "registro.csv").read_text(encoding="utf-8").splitlines()
    assert len(registro) == 5  # cabeçalho + 4 dias
    hist = HistoricoNCM.carregar(tmp_path)
    assert hist.na_data(date(2026, 11, 9)).existe("34025000")
    assert not hist.na_data(date(2026, 11, 10)).existe("34025000") and hist.atual.existe("34025010")


# ---------------------------------------------------------------------------------------------
# Painel local (127.0.0.1)
# ---------------------------------------------------------------------------------------------


def _multipart(arquivos: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    fronteira = "----raioxteste"
    partes = []
    for nome, dados in arquivos:
        partes.append(
            f'--{fronteira}\r\nContent-Disposition: form-data; name="f"; filename="{nome}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
            + dados
            + b"\r\n"
        )
    corpo = b"".join(partes) + f"--{fronteira}--\r\n".encode()
    return corpo, f"multipart/form-data; boundary={fronteira}"


def test_painel_local(pasta_exemplos, historico, tmp_path):
    from raio_x_fiscal.produto.servidor import HOST, criar_servidor

    srv = criar_servidor(motor.Contexto(historico=historico), tmp_path / "painel", porta=0)
    assert srv.server_address[0] == HOST == "127.0.0.1"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        assert "Painel local" in urllib.request.urlopen(url + "/").read().decode()
        xmls = sorted((pasta_exemplos / "notas" / "loja-exemplo-a").glob("*.xml"))[:2]
        corpo, ct = _multipart(
            [(f"loja/{p.name}", p.read_bytes()) for p in xmls] + [("../../fora.xml", xmls[0].read_bytes())]
        )
        req = urllib.request.Request(url + "/api/notas", data=corpo, headers={"Content-Type": ct}, method="POST")
        r = json.loads(urllib.request.urlopen(req).read())
        assert r["html"].startswith("/r/") and "notas" in r["texto"]
        assert urllib.request.urlopen(url + r["html"]).status == 200
        assert not (tmp_path / "fora.xml").exists()  # '..' não sai da pasta do painel
        with pytest.raises(urllib.error.HTTPError) as erro:  # sem modelo: a pesquisa explica e não quebra
            urllib.request.urlopen(url + "/api/pesquisar?q=arroz")
        assert erro.value.code == 400 and "modelo" in json.loads(erro.value.read())["erro"]
    finally:
        srv.shutdown()
        srv.server_close()
