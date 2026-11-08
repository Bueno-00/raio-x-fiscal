"""Gera notas fiscais de EXEMPLO (XML sintético), com erros plantados de propósito.

Nada aqui é nota real: empresas, CNPJs e chaves são inventados (CNPJ com dígito verificador
válido só para passar no formato). Serve para:
- mostrar o Raio-X funcionando sem precisar de nota de cliente;
- testar cada regra com um caso certo e um errado (os testes usam estes mesmos arquivos).

Estrutura gerada (uma subpasta por empresa, como o escritório organiza):

    exemplos/notas/
      loja-exemplo-a/            Simples Nacional, SP, NF-e e NFC-e
      distribuidora-exemplo-b/   regime normal, MG (+ um evento de cancelamento)
      oficina-exemplo-c.zip      Simples Nacional, PR, dentro de um .zip
    exemplos/regras-do-escritorio.csv
    exemplos/cadastro-loja-a.csv  (porta 2: planilha de cadastro)
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

NS = "http://www.portalfiscal.inf.br/nfe"
UF_COD = {"SP": "35", "MG": "31", "PR": "41", "RJ": "33", "BA": "29", "RS": "43", "SC": "42", "GO": "52"}


def dv_cnpj(base12: str) -> str:
    def dv(s: str, pesos: list[int]) -> str:
        r = sum(int(a) * b for a, b in zip(s, pesos, strict=True)) % 11
        return "0" if r < 2 else str(11 - r)

    d1 = dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + d2


def dv_chave(c43: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    s = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(c43)))
    r = s % 11
    return c43 + ("0" if r < 2 else str(11 - r))


def gtin_com_dv(corpo: str) -> str:
    soma = sum(int(v) * (3 if i % 2 == 0 else 1) for i, v in enumerate(reversed(corpo)))
    return corpo + str((10 - soma % 10) % 10)


# Empresas fictícias (mesma raiz de CNPJ de exemplo já usada nos testes do pipeline).
LOJA_A = ("11222333000181", "LOJA EXEMPLO A LTDA", "SP", "1")
DISTR_B = (dv_cnpj("112223330002"), "DISTRIBUIDORA EXEMPLO B LTDA", "MG", "3")
OFICINA_C = (dv_cnpj("112223330003"), "OFICINA EXEMPLO C LTDA", "PR", "1")
CLIENTE_MG = (dv_cnpj("998887770001"), "CLIENTE EXEMPLO MG LTDA", "MG")
CLIENTE_SP = (dv_cnpj("998887770002"), "CLIENTE EXEMPLO SP LTDA", "SP")
CLIENTE_RJ = (dv_cnpj("998887770003"), "CLIENTE EXEMPLO RJ LTDA", "RJ")
CLIENTE_PR = (dv_cnpj("998887770004"), "CLIENTE EXEMPLO PR LTDA", "PR")
FORNEC_GO = (dv_cnpj("776665550001"), "FORNECEDOR EXEMPLO GO LTDA", "GO", "3")


@dataclass
class P:
    codigo: str
    descricao: str
    ncm: str
    valor: float
    qtd: float = 1
    unidade: str = "UN"
    cfop: str | None = None
    gtin: str | None = None
    cst: str | None = None
    csosn: str | None = None
    servico: bool = False


@dataclass
class N:
    numero: int
    data: str  # AAAA-MM-DD
    emit: tuple
    dest: tuple | None
    cfop: str
    itens: list[P] = field(default_factory=list)
    modelo: str = "55"
    tp_nf: str = "1"
    ind_pres: str = "9"
    ind_final: str = "0"
    natureza: str = "VENDA DE MERCADORIA"


ARROZ = P("A-0101", "ARROZ TIPO 1 BRANCO 5KG", "10063021", 27.9, 10, "PCT", gtin=gtin_com_dv("789100000001"))
FEIJAO = P("A-0103", "FEIJAO CARIOCA TIPO 1 1KG", "07133399", 8.49, 12, "PCT", gtin=gtin_com_dv("789100000003"))
LEITE_COND = P("A-0104", "LEITE CONDENSADO 395G", "04029900", 6.99, 24, gtin=gtin_com_dv("789100000004"))
CAFE_OK = P("A-0102", "CAFE TORRADO E MOIDO 500G", "09012100", 18.9, 6, "PCT", gtin=gtin_com_dv("789100000002"))
CAFE_DIV = P("A-0102", "CAFE TORRADO E MOIDO 500G", "09011110", 18.9, 6, "PCT", gtin=gtin_com_dv("789100000002"))
ACUCAR = P("A-0105", "ACUCAR CRISTAL 5KG", "17019900", 21.5, 5, "PCT", gtin=gtin_com_dv("789100000005"))
OLEO = P("A-0106", "OLEO DE SOJA REFINADO 900ML", "15079011", 7.29, 20, gtin=gtin_com_dv("789100000006"))
CENOURA_ERRADA = P("A-0201", "CENOURA KG", "01012100", 4.5, 30, "KG")
SABAO_EXTINTO = P("A-0301", "SABAO EM PO 1KG", "34022000", 12.9, 10, gtin=gtin_com_dv("789100000011"))
IOGURTE_ANTIGO = P("A-0302", "IOGURTE NATURAL 170G", "04031000", 3.2, 24)
PAPEL = P("A-0303", "PAPEL HIGIENICO FOLHA DUPLA 12 ROLOS", "48181000", 19.9, 4, gtin="7891000000127")  # DV errado
DETERGENTE = P("A-0304", "DETERGENTE LIQUIDO NEUTRO 500ML", "34025000", 2.79, 24, gtin=gtin_com_dv("789100000013"))
BISCOITO_CST = P("A-0305", "BISCOITO RECHEADO CHOCOLATE 140G", "19053100", 3.49, 30, cst="00")
NCM_CURTO = P("A-0306", "CREME DENTAL 90G", "3306100", 4.99, 12)

PARAFUSO = P("B-1001", "PARAFUSO SEXTAVADO ACO ZINCADO M8X40", "73181500", 0.85, 500, "UN", cst="00")
CABO = P("B-1002", "CABO FLEXIVEL 2,5MM 750V ROLO 100M", "85444900", 189.0, 5, "RL", cst="00")
LAMPADA = P("B-1003", "LAMPADA LED BULBO 9W BIVOLT", "85395200", 7.9, 100, cst="00")
CANETA_ERRADA = P("B-1004", "CANETA ESFEROGRAFICA AZUL CX 50", "73181500", 39.9, 10, "CX", cst="00")
FITA_CSOSN = P("B-1005", "FITA ISOLANTE 19MM X 20M", "39191000", 6.5, 40, csosn="102")
PNEU = P("B-2001", "PNEU 175/70 R14", "40111000", 389.0, 4, cst="00")

OLEO_MOTOR = P("C-0001", "OLEO LUBRIFICANTE MOTOR 5W30 1L", "27101932", 39.9, 4, "L")
FILTRO = P("C-0002", "FILTRO DE OLEO", "84212300", 32.0, 1)
MAO_DE_OBRA = P("C-9001", "MAO DE OBRA TROCA DE OLEO", "00", 80.0, 1, "SV", servico=True)


def notas_exemplo() -> dict[str, list[N]]:
    return {
        "loja-exemplo-a": [
            N(101, "2026-10-05", LOJA_A, CLIENTE_SP, "5102", [ARROZ, FEIJAO, LEITE_COND, CAFE_OK, ACUCAR, OLEO]),
            N(102, "2026-10-12", LOJA_A, CLIENTE_SP, "5102", [CENOURA_ERRADA, CAFE_DIV, PAPEL, DETERGENTE]),
            N(103, "2026-10-20", LOJA_A, CLIENTE_SP, "5102", [IOGURTE_ANTIGO, BISCOITO_CST, NCM_CURTO]),
            N(104, "2026-11-07", LOJA_A, CLIENTE_SP, "5102", [SABAO_EXTINTO, ARROZ, LEITE_COND]),
            # venda presencial a cliente de MG: 5102 é aceito automaticamente
            N(105, "2026-11-03", LOJA_A, CLIENTE_MG, "5102", [CAFE_OK, ACUCAR], ind_pres="1", ind_final="1"),
            # sistema da loja marcou indPres=9; o escritório confirmou que foi balcão (regra do escritório)
            N(106, "2026-11-04", LOJA_A, CLIENTE_RJ, "5102", [OLEO, FEIJAO]),
            N(
                107,
                "2026-11-06",
                LOJA_A,
                None,
                "5102",
                [ARROZ, LEITE_COND, CAFE_OK],
                modelo="65",
                ind_pres="1",
                ind_final="1",
            ),  # fmt: skip
        ],
        "distribuidora-exemplo-b": [
            N(2001, "2026-10-08", DISTR_B, CLIENTE_MG, "5102", [PARAFUSO, CABO, LAMPADA]),
            N(2002, "2026-10-15", DISTR_B, CLIENTE_SP, "5102", [PARAFUSO, CABO]),  # interestadual com 5xxx
            N(2003, "2026-10-22", DISTR_B, CLIENTE_MG, "6102", [LAMPADA, CANETA_ERRADA]),  # interna com 6xxx
            N(2004, "2026-10-29", DISTR_B, CLIENTE_MG, "5102", [FITA_CSOSN, PNEU]),
            N(2005, "2026-11-02", DISTR_B, CLIENTE_MG, "5102", [PNEU, LAMPADA]),  # cancelada (evento na pasta)
            # compra de fornecedor de GO: entrada para a distribuidora
            N(9001, "2026-10-03", FORNEC_GO, DISTR_B[:3], "6102", [PARAFUSO, CABO]),
        ],
        "oficina-exemplo-c": [
            N(301, "2026-10-10", OFICINA_C, CLIENTE_PR, "5102", [OLEO_MOTOR, FILTRO, MAO_DE_OBRA]),
            N(302, "2026-10-24", OFICINA_C, CLIENTE_PR, "5102", [OLEO_MOTOR, FILTRO]),
        ],
    }


def _chave(n: N) -> str:
    cuf = UF_COD[n.emit[2]]
    aamm = n.data[2:4] + n.data[5:7]
    base = f"{cuf}{aamm}{n.emit[0]}{n.modelo}{1:03d}{n.numero:09d}1{n.numero * 7919 % 10**8:08d}"
    return dv_chave(base)


def _icms(n: N, p: P) -> str:
    crt = n.emit[3] if len(n.emit) > 3 else "3"
    if p.csosn or (crt in ("1", "4") and not p.cst):
        cs = p.csosn or "102"
        return f"<ICMS><ICMSSN{cs}><orig>0</orig><CSOSN>{cs}</CSOSN></ICMSSN{cs}></ICMS>"
    cst = p.cst or "00"
    return (
        f"<ICMS><ICMS{cst}><orig>0</orig><CST>{cst}</CST><modBC>3</modBC><vBC>{p.valor * p.qtd:.2f}</vBC>"
        f"<pICMS>18.00</pICMS><vICMS>{p.valor * p.qtd * 0.18:.2f}</vICMS></ICMS{cst}></ICMS>"
    )


def xml_nota(n: N) -> str:
    chave = _chave(n)
    emit_cnpj, emit_nome, emit_uf = n.emit[:3]
    crt = n.emit[3] if len(n.emit) > 3 else "3"
    # Como numa nota autorizada: idDest acompanha o CFOP (a SEFAZ rejeita se não acompanhar).
    id_dest = {"1": "1", "5": "1", "2": "2", "6": "2", "3": "3", "7": "3"}[n.cfop[0]]
    dets = []
    total = 0.0
    for i, p in enumerate(n.itens, start=1):
        v = round(p.valor * p.qtd, 2)
        total += v
        cean = p.gtin or "SEM GTIN"
        imposto = (
            f"<ISSQN><vBC>{v:.2f}</vBC><vAliq>5.00</vAliq><vISSQN>{v * 0.05:.2f}</vISSQN><cMunFG>4106902</cMunFG>"
            f"<cListServ>14.01</cListServ><indISS>1</indISS><indIncentivo>2</indIncentivo></ISSQN>"
            if p.servico
            else _icms(n, p)
        )
        dets.append(
            f'<det nItem="{i}"><prod><cProd>{escape(p.codigo)}</cProd><cEAN>{cean}</cEAN>'
            f"<xProd>{escape(p.descricao)}</xProd><NCM>{p.ncm}</NCM><CFOP>{p.cfop or n.cfop}</CFOP>"
            f"<uCom>{p.unidade}</uCom><qCom>{p.qtd:.4f}</qCom><vUnCom>{p.valor:.10f}</vUnCom>"
            f"<vProd>{v:.2f}</vProd><cEANTrib>{cean}</cEANTrib><uTrib>{p.unidade}</uTrib>"
            f"<qTrib>{p.qtd:.4f}</qTrib><vUnTrib>{p.valor:.10f}</vUnTrib><indTot>1</indTot></prod>"
            f"<imposto>{imposto}</imposto></det>"
        )
    dest = ""
    if n.dest is not None:
        dest = (
            f"<dest><CNPJ>{n.dest[0]}</CNPJ><xNome>{escape(n.dest[1])}</xNome><enderDest>"
            f"<xLgr>RUA EXEMPLO</xLgr><nro>100</nro><xBairro>CENTRO</xBairro><cMun>0000000</cMun>"
            f"<xMun>CIDADE EXEMPLO</xMun><UF>{n.dest[2]}</UF></enderDest><indIEDest>9</indIEDest></dest>"
        )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<nfeProc xmlns="{NS}" versao="4.00"><NFe><infNFe '
        f'Id="NFe{chave}" versao="4.00"><ide><cUF>{UF_COD[emit_uf]}</cUF><cNF>{chave[35:43]}</cNF>'
        f"<natOp>{n.natureza}</natOp><mod>{n.modelo}</mod><serie>1</serie><nNF>{n.numero}</nNF>"
        f"<dhEmi>{n.data}T10:00:00-03:00</dhEmi><tpNF>{n.tp_nf}</tpNF><idDest>{id_dest}</idDest>"
        f"<cMunFG>0000000</cMunFG><tpImp>1</tpImp><tpEmis>1</tpEmis><cDV>{chave[-1]}</cDV><tpAmb>2</tpAmb>"
        f"<finNFe>1</finNFe><indFinal>{n.ind_final}</indFinal><indPres>{n.ind_pres}</indPres>"
        f"<procEmi>0</procEmi><verProc>EXEMPLO</verProc></ide>"
        f"<emit><CNPJ>{emit_cnpj}</CNPJ><xNome>{escape(emit_nome)}</xNome><enderEmit><xLgr>RUA EXEMPLO</xLgr>"
        f"<nro>1</nro><xBairro>CENTRO</xBairro><cMun>0000000</cMun><xMun>CIDADE EXEMPLO</xMun><UF>{emit_uf}</UF>"
        f"</enderEmit><IE>ISENTO</IE><CRT>{crt}</CRT></emit>{dest}{''.join(dets)}"
        f"<total><ICMSTot><vProd>{total:.2f}</vProd><vNF>{total:.2f}</vNF></ICMSTot></total>"
        f"<transp><modFrete>9</modFrete></transp></infNFe></NFe>"
        f'<protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><chNFe>{chave}</chNFe><cStat>100</cStat>'
        f"<xMotivo>EXEMPLO: nota sintetica, nao autorizada</xMotivo></infProt></protNFe></nfeProc>\n"
    )


def xml_cancelamento(chave: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<procEventoNFe xmlns="{NS}" versao="1.00"><evento versao="1.00">'
        f'<infEvento Id="ID110111{chave}01"><cOrgao>31</cOrgao><tpAmb>2</tpAmb><chNFe>{chave}</chNFe>'
        f"<dhEvento>2026-11-02T15:00:00-03:00</dhEvento><tpEvento>110111</tpEvento><nSeqEvento>1</nSeqEvento>"
        f'<detEvento versao="1.00"><descEvento>Cancelamento</descEvento><xJust>EXEMPLO: pedido desfeito</xJust>'
        f"</detEvento></infEvento></evento></procEventoNFe>\n"
    )


REGRAS_ESCRITORIO = (
    "# Regra do escritório (EXEMPLO): o que está certo de propósito. Vazio = qualquer.\n"
    "cnpj_empresa;regra;cfop;ncm;codigo_produto;motivo\n"
    f"{LOJA_A[0]};CFOP_UF;5102;;;Venda no balcão para cliente de outro estado (confirmado com a loja)\n"
)

# Porta 2: cadastro no formato da exportação de produtos do Bling (primeiras colunas como na
# ajuda oficial: ID, Código, Descrição, Unidade, NCM, Origem, Preço...). IDs inventados.
_CAB = "ID;Código;Descrição;Unidade;NCM;Origem;Preço;Valor IPI fixo;Observações;Situação;GTIN/EAN;CEST"
_PRODUTOS = [
    ("A-0101", "ARROZ TIPO 1 BRANCO 5KG", "PCT", "1006.30.21", "27,90", ARROZ.gtin),
    ("A-0102", "CAFE TORRADO E MOIDO 500G", "PCT", "0901.21.00", "18,90", CAFE_OK.gtin),
    ("A-0103", "FEIJAO CARIOCA TIPO 1 1KG", "PCT", "0713.33.99", "8,49", FEIJAO.gtin),
    ("A-0104", "LEITE CONDENSADO 395G", "UN", "0402.99.00", "6,99", LEITE_COND.gtin),
    ("A-0201", "CENOURA KG", "KG", "0101.21.00", "4,50", ""),
    ("A-0301", "SABAO EM PO 1KG", "UN", "3402.20.00", "12,90", SABAO_EXTINTO.gtin),
    ("A-0303", "PAPEL HIGIENICO FOLHA DUPLA 12 ROLOS", "UN", "4818.10.00", "19,90", "7891000000127"),
    ("A-0307", "MOLHO DE TOMATE TRADICIONAL 340G", "UN", "2103.20.10", "2,99", ""),
    ("A-0308", "REFRIGERANTE COLA 2L", "UN", "2202.10.00", "8,99", ""),
    ("A-0309", "BANANA PRATA KG", "KG", "0803.90.00", "5,99", ""),
    ("A-0310", "SHAMPOO ANTICASPA 200ML", "UN", "9608.10.00", "14,90", ""),
    ("A-0311", "AGUA MINERAL SEM GAS 500ML", "UN", "2201.10.00", "1,99", ""),
]
CADASTRO_LOJA_A = (
    _CAB
    + "\n"
    + "\n".join(f"{900001 + i};{c};{d};{u};{n};0;{p};0;;Ativo;{g};" for i, (c, d, u, n, p, g) in enumerate(_PRODUTOS))
    + "\n"
)


def gerar(destino: Path) -> dict:
    """Escreve os exemplos em `destino` (sobrescreve). Devolve o que foi gerado."""
    notas_dir = destino / "notas"
    notas_dir.mkdir(parents=True, exist_ok=True)
    feitos = []
    for grupo, notas in notas_exemplo().items():
        arquivos = {}
        for n in notas:
            chave = _chave(n)
            arquivos[f"{chave}-nfe.xml"] = xml_nota(n)
            if n.numero == 2005:
                arquivos[f"{chave}-cancelamento.xml"] = xml_cancelamento(chave)
        if grupo == "oficina-exemplo-c":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for nome, xml in arquivos.items():
                    zf.writestr(nome, xml)
            (notas_dir / f"{grupo}.zip").write_bytes(buf.getvalue())
        else:
            (notas_dir / grupo).mkdir(exist_ok=True)
            for nome, xml in arquivos.items():
                (notas_dir / grupo / nome).write_text(xml, encoding="utf-8")
        feitos.append((grupo, len(notas)))
    (destino / "regras-do-escritorio.csv").write_text(REGRAS_ESCRITORIO, encoding="utf-8")
    (destino / "cadastro-loja-a.csv").write_text(CADASTRO_LOJA_A, encoding="utf-8")
    return {"grupos": feitos, "pasta": str(destino)}
