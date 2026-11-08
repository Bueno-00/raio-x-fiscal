"""Notas de exemplo "de verdade": 8 comércios fictícios com produtos tirados do DADO PÚBLICO.

Para mostrar o Raio-X sem nota de cliente. Cada empresa é inventada (nome com "EXEMPLO", CNPJ
com dígito verificador válido só para passar no formato, chave em ambiente de homologação), mas
os produtos são descrições reais das notas públicas do Portal da Transparência, com o NCM de
consenso (o mesmo NCM em 85% ou mais das vezes; ver `scripts/extrair_catalogo_exemplos.py`).

Os erros são plantados como acontecem no escritório:
- a maioria nasce no CADASTRO do produto e se repete em toda nota que sai com ele (NCM copiado
  de outro produto, código antigo que saiu da tabela, zero da frente perdido no Excel, código de
  barras digitado errado, tributação do regime normal numa empresa do Simples);
- outros nascem na NOTA (CFOP de dentro do estado numa venda para outro estado, e o contrário;
  um NCM diferente digitado só naquela nota; CFOP de compra numa venda; nota cancelada depois).

Proporção: cerca de 1 em cada 10 itens com algum erro plantado, um pouco acima do que o próprio
Raio-X achou na amostra pública (5,1% dos itens com alerta), para dar para ver cada tipo de erro.

Tudo é determinístico (mesma semente, mesmas notas) e vem com o GABARITO: a lista do que foi
plantado, item por item, para conferir o que o Raio-X pegou e o que deixou passar.
"""

from __future__ import annotations

import csv
import hashlib
import io
import random
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from raio_x_fiscal.produto.exemplos import NS, dv_chave, dv_cnpj, gtin_com_dv
from raio_x_fiscal.produto.ncm_tabela import HistoricoNCM

SEEDS = Path(__file__).resolve().parents[1] / "seeds"
CATALOGO = SEEDS / "catalogo_exemplos.csv"
UF_COD = {
    "SP": "35", "MG": "31", "PR": "41", "RJ": "33", "BA": "29", "RS": "43", "SC": "42", "GO": "52",
    "DF": "53", "SE": "28", "ES": "32",
}  # fmt: skip
SEMENTE = 20261108
PASTA_ZIP = "notas-exemplo-raio-x"

UNIDADES = {
    "UNIDAD": "UN", "UNI": "UN", "UND": "UN", "PEÇA": "PC", "PECA": "PC", "PCS": "PC", "P": "PAR", "PA": "PAR",
    "KG0001": "KG", "KG1": "KG", "METRO": "M3", "LITRO": "L", "EMB.": "UN", "EMB": "UN", "FRASCO": "FR",
    "500 ML": "UN", "PAC": "PCT", "PT": "PCT", "BB": "UN", "BJ": "BDJ", "C": "CENTO", "CNT": "CENTO",
}  # fmt: skip


@dataclass
class Produto:
    codigo: str
    descricao: str
    ncm_certo: str  # NCM de consenso no dado público (ou o código antigo, nos "antigos")
    ncm_cadastro: str  # o que está no cadastro da empresa (pode estar errado: erro plantado)
    unidade: str
    preco: float
    gtin: str | None
    granel: bool = False
    cst_errado: bool = False
    erros: list[str] = field(default_factory=list)  # erros plantados no cadastro deste produto


@dataclass
class Negocio:
    id: str
    nome: str
    tipo: str
    uf: str
    crt: str  # 1 Simples Nacional, 3 regime normal
    raiz: str  # 12 primeiros dígitos do CNPJ
    produtos: list[str]
    antigos: list[str] = field(default_factory=list)
    n_nfce: int = 0
    nfe_ufs: list[str] = field(default_factory=list)  # UF do cliente de cada NF-e de venda
    entradas: int = 0  # notas de compra de um fornecedor (a empresa é a destinatária)
    fornecedor_uf: str = ""
    producao: tuple[str, ...] = ()  # palavras dos itens produzidos no local (CFOP 5101)

    @property
    def cnpj(self) -> str:
        return dv_cnpj(self.raiz)


NEGOCIOS = [
    Negocio(
        "mercado-bom-preco", "MERCADO BOM PRECO EXEMPLO LTDA", "Mercado", "SP", "1", "112223330011",
        [
            "ARROZ LONGO FINO - 1KG", "FEIJAO CARIOCA 1KG", "FEIJAO PRETO KG", "ACUCAR CRISTAL UNIAO 1KG",
            "ACUCAR ALTO ALEGRE REFINADO PCT 1KG", "CAFE TORRADO E MOIDO A VACUO 500G",
            "CAFE EM PO PILAO TRADICIONAL VACUO 500G", "OLEO DE SOJA 900ML", "LEITE UHT INTEGRAL PIRACANJUBA 1 LITRO",
            "LEITE CONDENSADO ITALAC 395G", "MACARRAO ESPAGUETE 500G", "MACARRAO TIPO PARAFUSO 500G",
            "FARINHA DE TRIGO 1KG", "MOLHO DE TOMATE 340 GR", "EXTRATO DE TOMATE 340 GR", "BISCOITO MAISENA",
            "SAL REFINADO 1KG", "MARGARINA 500G", "CREME DE LEITE ITALAC 200G.", "AGUA MINERAL 20L",
            "REFRIGERANTE EMB 2 LITROS", "REFRIGERANTE A BASE DE GUARANA", "DETERGENTE YPE LAVA LOUCAS NEUTRO 500ML",
            "SABAO EM PO 1 KG", "PAPEL HIGIENICO FOLHA DUPLA", "CREME DENTAL 90GRS", "AGUA SANITARIA 1LT",
            "BANANA PRATA COMUM CRFO KG", "TOMATE KG", "BATATA DOCE ROSA", "OVOS - DZ", "ACHOCOLATADO 400G",
            "FUBA DE MILHO 500 GR", "VINAGRE 750ML", "AZEITE OLIVA E.VIRGEM 500ML", "SARDINHA CONSERVA OLEO 125G",
            "GOIABADA 500G", "AMACIANTE DE ROUPA",
        ],
        antigos=["IOG. COOPERBELGO MORANGO 120 GR", "VEJA MULTIUSO 500ML ORIGINAL"],
        n_nfce=18, nfe_ufs=["SP", "SP", "SP", "SP", "MG", "RJ"],
    ),
    Negocio(
        "autopecas-roda-forte", "AUTOPECAS RODA FORTE EXEMPLO LTDA", "Autopeças", "PR", "3", "112223330012",
        [
            "FILTRO DE OLEO SINTE", "FILTRO DE AR L200", "FILTRO COMBUSTIVEL UNIVERSAL", "FILTRO, COMBUSTIVEL MOTOR",
            "PASTILHA DE FREIO TRASEIRO", "PASTILHA FREIO DT S10 2017...", "DISCO DE FREIO DIANTEIRO VENTILADO",
            "OLEO LUBRIFICANTE 5W30", "OLEO MOTOR 15W40", "OLEO DE MOTOR 1L", "PNEU 185/60R15 84H ENASAVE",
            "PNEU 265/60R18 110H AT25 DU", "BATERIA AUTOMOTIVA", "VELA DE IGNICAO NGK BPMR7A", "CORREIA TIPO V",
            "CORREIA V NERVURADA", "AMORTECEDOR DIANTEIRO DIREITO", "AMORTECEDOR TRAS", "LAMPADA H7 12V 55W",
            "PALHETA, LIMPADOR PARABRISA", "FLUIDO DE FREIO DOT 4 500ML", "ADITIVO RADIADOR DNK PRONTOPARA USO ROSA",
        ],
        antigos=["CAPACETE TEXX FECHA KAIMAN SOLID PRET FOSC 60", "CAPACETE ORIGINE LOGIC SOLID BLACK MATT M"],
        nfe_ufs=["PR"] * 9 + ["SC", "SC", "SP"], entradas=2, fornecedor_uf="SP",
    ),
    Negocio(
        "farmacia-saude-viva", "FARMACIA SAUDE VIVA EXEMPLO LTDA", "Farmácia", "MG", "1", "112223330013",
        [
            "DIPIRONA 500MG COMPRIMIDOS", "PARACETAMOL 750MG CPR", "IBUPROFENO 50MG/ML FR 30 ML IBUPROTRAT NATULAB",
            "AMOXICILINA+CLAVULANATO 500+125MG CPR C/18", "LOSARTANA 50MG", "OMEPRAZOL 20MG CPS C/56",
            "SORO FISIOLOGICO 0,9% 100ML BS", "ALCOOL 70% 500ML", "ALCOOL EM GEL 500 ML - 70° ANTISSEPTICO",
            "ESPARADRAPO 10CM X 4,5M", "LUVA DE PROCEDIMENTO TAM G", "SERINGA DESCARTAVEL DE 10ML LUER LOCK",
            "FRALDA DESCART. GRANDE ATE 15 KG", "ABSORVENTE DESCARTAVEL COM ABAS PCT 32 UNID.",
            "PROTETOR SOLAR FPS 60 120ML", "ESCOVA DENTAL", "TERMOMETRO DIGITAL C/BIP", "METFORMINA 500MG CPR C/30",
            "ALGODAO BOLA COTTON BABY 95G", "CURATIVO ADESIVO COTTON BABY CX 10UN", "ATADURA CREPE 15CM X 1,8M 13F",
            "SIMETICONA 40MG", "LORATADINA 10MG VITAMEDIC", "CREME DENTAL MAXIMA PROTECAO ANTICARIES 30G",
        ],
        antigos=["ALCOOL ETILICO 70% 1000ML"],
        n_nfce=14, nfe_ufs=["MG", "MG", "MG", "ES"],
    ),
    Negocio(
        "construmais-materiais", "CONSTRUMAIS MATERIAIS EXEMPLO LTDA", "Material de construção", "GO", "3",
        "112223330014",
        [
            "CIMENTO CPII", "AREIA LAVADA GRANULOMETRIA MEDIA", "BRITA 01", "CAL HIDRATADA PARA REBOCO 20 KG",
            "ARGAMASSA PISO SOBRE PISO-ARGASUL", "TIJOLO DE CERAMICA 19X19X9 DE 8 FUROS",
            "VERGALHAO CA-50, 10,0 MM", "TUBO PVC SOLDAVEL 25MM", "TUBO PVC SOLDAVEL 50MM", "JOELHO SOLDAVEL 25MM",
            "JOELHO 90 PVC ESGOTO BRANCO 100MM", "TINTA ACRILICA BRANCO NEVE", "MASSA CORRIDA PVA INTER - 25KG ALWICOR",
            "CABO FLEXIVEL 2.50MM - MF", "CABO FLEXIVEL 4.00MM - MF", "DISJUNTOR DIN, MONOPOLAR DE 6 ATE 32A",
            "DISJUNTOR DIN, BIPOLAR DE 6 ATE 32A", "TOMADA 2P+T 10A BRANCA", "INTERRUPTOR EMBUTIR 1 TECLA SIMPLES BRANCA",
            "REJUNTE BRANCO", "TELHA DE FIBROCIMENTO 2,44X1,10X6MM", "REGISTRO DE ESFERA PVC, 20MM",
            "TORNEIRA JARDIM BICO MANGUEIRA 1/2' PR", "CAIXA D' AGUA POLIETILENO 1000L COM TAMPA",
            "LIXA MASSA MADEIRA G120 225X275MM", "ROLO DE PINTURA PREDIAL 9CM", "SELADOR ACRILICO INCOLOR 18 LITROS",
            "MANTA ASFALTICA 30CMX1MM", "BUCHA NYLON S12",
        ],
        antigos=["ELETRODUTO FZ LEVE 3/4", "CAPACETE DE SEGURANCA"],
        nfe_ufs=["GO"] * 10 + ["DF", "DF", "DF"],
    ),
    Negocio(
        "moda-estilo", "MODA ESTILO EXEMPLO LTDA", "Loja de roupas", "SC", "1", "112223330015",
        [
            "CAMISETA CINZA MC TAM M", "CAMISETA CINZA MC TAM G", "CAMISETA CINZA ML TAM M", "CAMISA POLO AZUL ROYAL",
            "CAMISA POLO BRANCA", "CAMISA POLO AZUL CELESTE", "BERMUDA FEM AZUL MARINHO CB/MN", "MOLETOM AZUL TAM M",
            "MOLETOM CINZA TAM G", "MEIA ESPORTIVA BRANCA", "MEIA PRETA", "TENIS PRETO", "SAPATO SOC C/SALTO FEM",
            "SAPATO PRETO TAM 42", "BONE TACTEL AZUL ROYAL", "BONE PRETO", "CINTO MASCULINO", "CALCA BRIM BEGE M",
            "CALCA OXFORD AZUL TAM G", "BOTA PVC CANO CURTO PTO 38", "TOUCA AZUL ROYAL", "CAMISA PERSONALIZADA",
        ],
        n_nfce=12, nfe_ufs=["SC", "SC", "PR", "RS"],
    ),
    Negocio(
        "restaurante-sabor-caseiro", "RESTAURANTE SABOR CASEIRO EXEMPLO LTDA", "Restaurante", "RJ", "1",
        "112223330016",
        [
            "MARMITEX 2 MEDIO UN COMIDA PRONTA UN", "MARMITEX 6 MEDIO UN COMIDA PRONTA UN", "MARMITA G",
            "LANCHE DA TARDE", "CAFE DA MANHA", "SALGADO KIBE RECHEADO, PACOTE COM 300G.", "SALGADO - PASTEL DE CARNE",
            "SANDUICHE NATURAL DE ATUM OU FRANGO", "PAO DE QUEIJO TRADICIONAL 1KG", "BOLO CASEIRO - CONVENCIONAL",
            "SOBREMESA LACTEA CHOCOLATE 360G", "SUCO NATURAL DE MACA - ART SUCO 200ML", "REFRIGERANTE LATA 350ML",
            "AGUA MINERAL 500 ML COM GAS", "CHA MATTE NATURAL LEAO 25UN", "CHA DE CIDREIRA LEAO 25UN",
        ],
        antigos=["MINI COXINHA", "MINI EMPADA"],
        n_nfce=18, entradas=3, fornecedor_uf="RJ",
        producao=("MARMIT", "LANCHE", "CAFE DA MANHA", "SALGADO", "SANDUICHE", "BOLO", "MINI "),
    ),
    Negocio(
        "papelaria-ponto-certo", "PAPELARIA PONTO CERTO EXEMPLO LTDA", "Papelaria", "BA", "1", "112223330017",
        [
            "CANETA ESFEROGRAFICA AZUL", "CANETA ESFEROGRAFICA PRETA", "LAPIS GRAFITE NO2 HB SEXTAVADO PRETO",
            "BORRACHA BRANCA COM CINTA PLASTICA GO OFFICE", "CADERNO CAPA DURA 17X24CM COM WIRE-O", "PAPEL A4 500 FLS PCT",
            "PAPEL SULFITE A4 75G 210X297 CHAMEX 500 FLS", "GRAMPEADOR METALICO GO OFFICE MEDIO",
            "GRAMPO GO OFFICE 26/6 GALVANIZADO CX 5.000UN", "CLIPS 2/0 CX C/100UN", "COLA BRANCA ESCOLAR PVA 90G FUTURO",
            "TESOURA GO OFFICE 21CM USO GERAL", "PASTA L GO OFFICE A4 CRISTAL PCT 10UN",
            "ENVELOPE SACO KRAFT NATURAL 250X353MM PCT 10UN", "MARCA TEXTO AMARELO", "CORRETIVO LIQUIDO 18 ML",
            "FITA ADESIVA SOOPER TRANSPARENTE 48MMX50M", "REGUA PLASTICA CRISTAL 30CM",
            "APONTADOR DE LAPIS PLASTICO COM DEPOSITO", "PINCEL ATOMICO PILOT DUPLO TRACO 1100-P AZUL",
            "ETIQUETA ADESIVA AQUATTRO 70MMX33MM PCT 100FLS", "LIVRO ATA COM 100 FOLHAS",
        ],
        antigos=["FITA ZEBRADA 70X200"],
        n_nfce=8, nfe_ufs=["BA", "BA", "BA", "BA", "SE", "SE"],
    ),
    Negocio(
        "infotec-informatica", "INFOTEC INFORMATICA EXEMPLO LTDA", "Informática", "SP", "3", "112223330018",
        [
            "MOUSE USB GO TECH CMM-128 PRETO", "MOUSE SEM FIO GO TECH MW01 PRETO", "TECLADO USB GO TECH LK-501 ABNT2 PRETO",
            "MONITOR LENOVO T24I-30 23.8POL", "MONITOR AOC 23,8 PN: 24E3QF/57", "NOTEBOOK DELL LATITUDE 3450",
            "NOTEBOOK UL154 I3 256GB 8GB 14.1", "COMPUTADOR BRAZILPC CORPORATE", "HD EXTERNO 2 TB",
            "PEN DRIVE SANDISK 32GB 3.2 AZUL", "PEN DRIVE GO TECH 64GB 3.0", "SSD GO TECH 240GB SATA III 2.5'",
            "SSD SATA HIKVISION 512GB", "MEMORIA RAM NOTEBOOK DDR4 2666MHZ 8GB OXYBR", "CABO HDMI 2.0 3 MTS",
            "NOBREAK 1.2 KVA SMS TECH SEM APROX 1200 BI/115", "ESTABILIZADOR BIVOLT AUTOMATICO, 500 VA",
            "IMPRESSORA EPSON WF - M5799", "CARTUCHO DE TONER PRETO RICOH P311 7K", "WEBCAM GO TECH FULL HD 1080P",
            "HEADSET USB LOGITECH H390 981-000014 PRETO", "HEADSET P2 GO TECH 0H110 BIAURICULAR PRETO",
            "FONTE ATX 500W REAL KNUP KP-522", "CABO DE REDE 1.5M COM CONECTOR RJ45", "ADAPTADOR HDMI PARA VGA 19CM",
        ],
        nfe_ufs=["SP", "SP", "SP", "SP", "SP", "RJ", "RJ", "MG", "MG", "PR", "SP", "SP"],
    ),
]  # fmt: skip

FORNECEDORES = {
    "autopecas-roda-forte": ("DISTRIBUIDORA AUTOPECAS EXEMPLO LTDA", "776665550011", "SP", "3"),
    "restaurante-sabor-caseiro": ("ATACADO ALIMENTOS EXEMPLO LTDA", "776665550012", "RJ", "3"),
}
# O que o fornecedor vende para a empresa (descrições do catálogo do mercado / autopeças).
COMPRAS = {
    "restaurante-sabor-caseiro": [
        "ARROZ LONGO FINO - 1KG", "FEIJAO CARIOCA 1KG", "OLEO DE SOJA 900ML", "FARINHA DE TRIGO 1KG", "SAL REFINADO 1KG",
        "ACUCAR CRISTAL UNIAO 1KG", "MARGARINA 500G", "TOMATE KG", "OVOS - DZ", "CAFE TORRADO E MOIDO A VACUO 500G",
    ],
    "autopecas-roda-forte": [
        "FILTRO DE OLEO SINTE", "OLEO MOTOR 15W40", "PASTILHA DE FREIO TRASEIRO", "LAMPADA H7 12V 55W",
        "CORREIA TIPO V", "VELA DE IGNICAO NGK BPMR7A",
    ],
}  # fmt: skip

# Regra do escritório do exemplo: um caso certo de propósito, para mostrar o "aceito".
REGRA_ACEITA = (
    "mercado-bom-preco",
    "CFOP_UF",
    "5102",
    "Venda no balcão para restaurante do RJ (cliente retira na loja)",
)

TIPOS_ERRO = {
    "NCM_DE_OUTRO_PRODUTO": ("NCM copiado de outro produto no cadastro", "NCM_MODELO"),
    "CODIGO_ANTIGO": ("NCM antigo, que saiu da tabela oficial", "NCM_INEXISTENTE"),
    "ZERO_PERDIDO": ("NCM com 7 dígitos (o Excel comeu o zero da frente)", "NCM_AUSENTE"),
    "GTIN_ERRADO": ("Código de barras com dígito errado", "GTIN_INVALIDO"),
    "CST_NO_SIMPLES": ("Empresa do Simples com CST do regime normal", "CST_REGIME"),
    "CFOP_5_PARA_FORA": ("CFOP 5.xxx (dentro do estado) numa venda para outro estado", "CFOP_UF"),
    "CFOP_6_DENTRO": ("CFOP 6.xxx (entre estados) numa venda dentro do estado", "CFOP_UF"),
    "NCM_SO_NESTA_NOTA": ("NCM diferente digitado só nesta nota", "PRODUTO_NCM_DIVERGENTE"),
    "CFOP_DE_COMPRA": ("CFOP de compra (1.xxx) numa nota de venda", "CFOP_SENTIDO"),
    "NOTA_CANCELADA": ("Nota cancelada depois (evento na pasta)", "NOTA_CANCELADA"),
}


def ler_catalogo() -> tuple[dict[str, dict], dict[str, dict]]:
    """({descrição: linha} dos produtos com NCM de consenso, {descrição: linha} dos códigos antigos)."""
    bons, antigos = {}, {}
    with CATALOGO.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["negocio"] == "codigo_antigo":
                antigos.setdefault(_limpa(r["descricao"]), r)
            else:
                bons.setdefault(r["descricao"], r)
    return bons, antigos


def _limpa(d: str) -> str:
    """Tira só o lixo de exportação (código na frente, aspas no fim); o texto do produto fica igual."""
    import re

    d = re.sub(r"^\d{3,5}\s*-\s*", "", d.strip())
    return d.strip("`'\" ").strip()


def _gtin(desc: str) -> str:
    h = int(hashlib.sha1(desc.encode()).hexdigest(), 16)
    return gtin_com_dv("789" + f"{h % 10**9:09d}")


def _unidade(u: str) -> str:
    u = (u or "UN").upper().strip()
    return UNIDADES.get(u, u if len(u) <= 4 else "UN")


def _preco(p: float, unidade: str, rng: random.Random) -> float:
    p = float(p or 1)
    base = p if p >= 0.05 else 0.05
    return round(base * rng.uniform(0.92, 1.12), 2)


def _ncm_outro_cabecalho(prod: Produto, todos: list[Produto], rng: random.Random) -> str:
    candidatos = [p.ncm_certo for p in todos if p.ncm_certo[:4] != prod.ncm_certo[:4] and len(p.ncm_certo) == 8]
    return rng.choice(sorted(set(candidatos)))


def _ncm_vizinho(ncm: str, tabela) -> str | None:
    """Outro NCM que existe, na mesma posição de 4 dígitos (o tipo de erro de quem digita)."""
    viz = sorted(c for c in tabela.folhas if c[:4] == ncm[:4] and c != ncm)
    return viz[0] if viz else None


@dataclass
class ItemNota:
    produto: Produto
    ncm: str
    cfop: str
    qtd: float
    preco: float
    cst: str | None = None
    csosn: str | None = None
    erros: list[str] = field(default_factory=list)


@dataclass
class NotaEx:
    negocio: Negocio
    numero: int
    serie: int
    modelo: str
    data: date
    hora: str
    emit: tuple  # (cnpj, nome, uf, crt)
    dest: tuple | None  # (cnpj, nome, uf)
    ind_pres: str
    ind_final: str
    itens: list[ItemNota] = field(default_factory=list)
    cancelada: bool = False
    erros: list[str] = field(default_factory=list)  # erros plantados na nota inteira

    @property
    def chave(self) -> str:
        cuf = UF_COD[self.emit[2]]
        aamm = self.data.strftime("%y%m")
        cnf = int(hashlib.sha1(f"{self.emit[0]}{self.modelo}{self.numero}".encode()).hexdigest(), 16) % 10**8
        base = f"{cuf}{aamm}{self.emit[0]}{self.modelo}{self.serie:03d}{self.numero:09d}1{cnf:08d}"
        return dv_chave(base)


def _cliente(uf: str, k: int) -> tuple[str, str, str]:
    return (dv_cnpj(f"99888777{k:04d}"), f"CLIENTE EXEMPLO {uf} {k:02d} LTDA", uf)


def montar(semente: int = SEMENTE) -> tuple[list[NotaEx], dict[str, list[Produto]], list[dict]]:
    """Monta as notas, os cadastros e o gabarito (sem escrever nada)."""
    rng = random.Random(semente)
    bons, antigos = ler_catalogo()
    tabela = HistoricoNCM.carregar(None).atual
    notas: list[NotaEx] = []
    cadastros: dict[str, list[Produto]] = {}
    n_cliente = 0

    for neg in NEGOCIOS:
        prods: list[Produto] = []
        for i, d in enumerate(neg.produtos, start=1):
            r = bons[d]
            un = _unidade(r["unidade"])
            granel = un in ("KG", "M3", "CENTO") or any(w in d for w in ("BANANA", "TOMATE", "BATATA", "OVOS"))
            prods.append(
                Produto(
                    f"{neg.id[:3].upper()}-{i:04d}",
                    d,
                    r["ncm"],
                    r["ncm"],
                    un,
                    _preco(float(r["preco"]), un, rng),
                    None if (granel or d in ("MARMITA G", "LANCHE DA TARDE", "CAFE DA MANHA")) else _gtin(d),
                    granel,
                )  # fmt: skip
            )
        for d in neg.antigos:
            r = antigos[d]
            un = _unidade(r["unidade"])
            p = Produto(
                f"{neg.id[:3].upper()}-{len(prods) + 1:04d}", d, r["ncm_antigo"], r["ncm_antigo"], un,
                _preco(float(r["preco"]), un, rng), _gtin(d), erros=["CODIGO_ANTIGO"],
            )  # fmt: skip
            prods.append(p)

        livres = [p for p in prods if not p.erros]
        rng.shuffle(livres)
        # Erros do cadastro (repetem em toda nota com o produto).
        n_outro = max(1, round(len(prods) * 0.08))
        for p in livres[:n_outro]:
            p.ncm_cadastro = _ncm_outro_cabecalho(p, prods, rng)
            p.erros.append("NCM_DE_OUTRO_PRODUTO")
        resto = livres[n_outro:]
        com_zero = [p for p in resto if p.ncm_certo.startswith("0")]
        if com_zero:
            p = com_zero[0]
            p.ncm_cadastro = p.ncm_certo[1:]
            p.erros.append("ZERO_PERDIDO")
            resto.remove(p)
        com_gtin = [p for p in resto if p.gtin]
        if com_gtin:
            p = com_gtin[0]
            p.gtin = p.gtin[:-1] + str((int(p.gtin[-1]) + 3) % 10)
            p.erros.append("GTIN_ERRADO")
            resto.remove(p)
        if neg.crt == "1" and resto:
            p = resto[0]
            p.cst_errado = True
            p.erros.append("CST_NO_SIMPLES")
            resto.remove(p)
        cadastros[neg.id] = prods
        emit = (neg.cnpj, neg.nome, neg.uf, neg.crt)

        # Datas: semana de 02/11 a 07/11/2026 (a competência que o escritório confere).
        def data_hora() -> tuple[date, str]:
            d = date(2026, 11, 2) + timedelta(days=rng.randint(0, 5))
            return d, f"{rng.randint(8, 19):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"

        def itens_da_nota(k: int, consumidor: bool, prods=prods, neg=neg) -> list[ItemNota]:
            out = []
            # Os produtos com erro de cadastro aparecem como qualquer outro (sem forçar).
            for p in rng.sample(prods, k=min(k, len(prods))):
                if p.granel:
                    q = round(rng.uniform(0.3, 3.5), 3) if consumidor else float(rng.randint(5, 60))
                elif p.preco < 1:
                    q = float(rng.randint(10, 60) if consumidor else rng.randint(100, 600))
                else:
                    q = float(rng.randint(1, 3) if consumidor else rng.randint(2, 40))
                cfop = "5101" if any(p.descricao.startswith(w) for w in neg.producao) else "5102"
                it = ItemNota(p, p.ncm_cadastro, cfop, q, p.preco, erros=list(p.erros))
                if neg.crt == "1":
                    it.csosn = None if p.cst_errado else "102"
                    it.cst = "00" if p.cst_errado else None
                else:
                    it.cst = "00"
                out.append(it)
            return out

        numero_nfe, numero_nfce = 1000 + rng.randint(0, 800), 20000 + rng.randint(0, 9000)
        for _ in range(neg.n_nfce):
            numero_nfce += rng.randint(1, 40)
            d, h = data_hora()
            n = NotaEx(neg, numero_nfce, 2, "65", d, h, emit, None, "1", "1")
            n.itens = itens_da_nota(rng.randint(2, 7), True)
            notas.append(n)
        for uf in neg.nfe_ufs:
            numero_nfe += rng.randint(1, 6)
            n_cliente += 1
            d, h = data_hora()
            n = NotaEx(neg, numero_nfe, 1, "55", d, h, emit, _cliente(uf, n_cliente), "9", "0")
            n.itens = itens_da_nota(rng.randint(3, 10), False)
            if uf != neg.uf:
                for it in n.itens:
                    it.cfop = "6" + it.cfop[1:]
            notas.append(n)
        for k in range(neg.entradas):
            nome, raiz, uf_f, crt_f = FORNECEDORES[neg.id]
            d, h = data_hora()
            n = NotaEx(
                neg, 50000 + k * 37 + rng.randint(0, 30), 1, "55", d, h, (dv_cnpj(raiz), nome, uf_f, crt_f),
                (neg.cnpj, neg.nome, neg.uf), "9", "0",
            )  # fmt: skip
            for desc in rng.sample(COMPRAS[neg.id], k=min(5, len(COMPRAS[neg.id]))):
                r = bons[desc]
                un = _unidade(r["unidade"])
                cod = f"F-{int(hashlib.sha1(desc.encode()).hexdigest(), 16) % 9999:04d}"
                p = Produto(cod, desc, r["ncm"], r["ncm"], un, float(r["preco"]), _gtin(desc))
                cfop = "5102" if uf_f == neg.uf else "6102"
                n.itens.append(
                    ItemNota(p, p.ncm_certo, cfop, float(rng.randint(10, 80)), round(p.preco * 0.8, 2), cst="00")
                )
            notas.append(n)

    _erros_de_nota(notas, rng, tabela)
    gabarito = _gabarito(notas)
    return notas, cadastros, gabarito


def _erros_de_nota(notas: list[NotaEx], rng: random.Random, tabela) -> None:
    por_neg: dict[str, list[NotaEx]] = {}
    for n in notas:
        por_neg.setdefault(n.negocio.id, []).append(n)
    canceladas = 0
    for neg_id, ns in por_neg.items():
        vendas_nfe = [n for n in ns if n.modelo == "55" and n.emit[0] == n.negocio.cnpj]
        fora = [n for n in vendas_nfe if n.dest and n.dest[2] != n.negocio.uf]
        dentro = [n for n in vendas_nfe if n.dest and n.dest[2] == n.negocio.uf]
        if fora:
            n = fora[-1]
            for it in n.itens:
                it.cfop = "5" + it.cfop[1:]
            if neg_id == REGRA_ACEITA[0]:
                n.erros.append("ACEITO_PELO_ESCRITORIO")  # certo de propósito: a regra do escritório aceita
            else:
                n.erros.append("CFOP_5_PARA_FORA")
        if dentro and neg_id in ("construmais-materiais", "infotec-informatica", "papelaria-ponto-certo"):
            n = dentro[-1]
            for it in n.itens:
                it.cfop = "6" + it.cfop[1:]
            n.erros.append("CFOP_6_DENTRO")
        if neg_id == "papelaria-ponto-certo" and dentro:
            it = dentro[0].itens[-1]
            it.cfop = "1102"
            it.erros.append("CFOP_DE_COMPRA")
        if neg_id in ("farmacia-saude-viva", "construmais-materiais") and vendas_nfe:
            n = vendas_nfe[1 if len(vendas_nfe) > 1 else 0]
            n.cancelada = True
            n.erros.append("NOTA_CANCELADA")
            canceladas += 1
        if neg_id in ("mercado-bom-preco", "autopecas-roda-forte", "moda-estilo", "infotec-informatica"):
            # Um produto sem erro de cadastro, que aparece em 3+ notas, sai com NCM diferente numa delas.
            cont: dict[str, list[tuple[NotaEx, ItemNota]]] = {}
            for n in ns:
                if n.emit[0] != n.negocio.cnpj or n.cancelada:
                    continue
                for it in n.itens:
                    if not it.produto.erros:
                        cont.setdefault(it.produto.codigo, []).append((n, it))
            alvo = sorted((v for v in cont.values() if len(v) >= 3), key=len, reverse=True)
            if alvo:
                n, it = alvo[0][len(alvo[0]) // 2]
                viz = _ncm_vizinho(it.ncm, tabela)
                if viz:
                    it.ncm = viz
                    it.erros.append("NCM_SO_NESTA_NOTA")


def _gabarito(notas: list[NotaEx]) -> list[dict]:
    linhas = []
    for n in notas:
        for i, it in enumerate(n.itens, start=1):
            erros = list(dict.fromkeys(it.erros + [e for e in n.erros if e in TIPOS_ERRO]))
            linhas.append(
                {
                    "empresa": n.negocio.id,
                    "tipo_de_negocio": n.negocio.tipo,
                    "modelo": n.modelo,
                    "nota": n.numero,
                    "chave": n.chave,
                    "item": i,
                    "codigo": it.produto.codigo,
                    "descricao": it.produto.descricao,
                    "ncm_na_nota": it.ncm,
                    "ncm_certo": it.produto.ncm_certo if "CODIGO_ANTIGO" not in it.erros else "",
                    "cfop": it.cfop,
                    "erro_plantado": ", ".join(erros),
                    "o_que_e": " | ".join(TIPOS_ERRO[e][0] for e in erros),
                    "regra_esperada": ", ".join(TIPOS_ERRO[e][1] for e in erros),
                    "caso_aceito": "sim" if "ACEITO_PELO_ESCRITORIO" in n.erros else "",
                }
            )
    return linhas


# ---------------------------------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------------------------------


def _icms(it: ItemNota, crt: str) -> str:
    if crt in ("1", "4") and not it.cst:
        cs = it.csosn or "102"
        return f"<ICMS><ICMSSN{cs}><orig>0</orig><CSOSN>{cs}</CSOSN></ICMSSN{cs}></ICMS>"
    cst = it.cst or "00"
    v = round(it.qtd * it.preco, 2)
    return (
        f"<ICMS><ICMS{cst}><orig>0</orig><CST>{cst}</CST><modBC>3</modBC><vBC>{v:.2f}</vBC>"
        f"<pICMS>18.00</pICMS><vICMS>{v * 0.18:.2f}</vICMS></ICMS{cst}></ICMS>"
    )


def _e(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_nota(n: NotaEx) -> str:
    chave = n.chave
    emit_cnpj, emit_nome, emit_uf, crt = n.emit
    cfop0 = n.itens[0].cfop[0]
    id_dest = {"1": "1", "5": "1", "2": "2", "6": "2", "3": "3", "7": "3"}.get(cfop0, "1")
    if n.dest is not None and n.dest[2] != emit_uf:
        id_dest = "2"
    dets, total = [], 0.0
    for i, it in enumerate(n.itens, start=1):
        v = round(it.qtd * it.preco, 2)
        total += v
        cean = it.produto.gtin or "SEM GTIN"
        dets.append(
            f'<det nItem="{i}"><prod><cProd>{_e(it.produto.codigo)}</cProd><cEAN>{cean}</cEAN>'
            f"<xProd>{_e(it.produto.descricao)}</xProd><NCM>{it.ncm}</NCM><CFOP>{it.cfop}</CFOP>"
            f"<uCom>{_e(it.produto.unidade)}</uCom><qCom>{it.qtd:.4f}</qCom><vUnCom>{it.preco:.10f}</vUnCom>"
            f"<vProd>{v:.2f}</vProd><cEANTrib>{cean}</cEANTrib><uTrib>{_e(it.produto.unidade)}</uTrib>"
            f"<qTrib>{it.qtd:.4f}</qTrib><vUnTrib>{it.preco:.10f}</vUnTrib><indTot>1</indTot></prod>"
            f"<imposto>{_icms(it, crt)}<PIS><PISNT><CST>07</CST></PISNT></PIS>"
            f"<COFINS><COFINSNT><CST>07</CST></COFINSNT></COFINS></imposto></det>"
        )
    dest = ""
    if n.dest is not None:
        dest = (
            f"<dest><CNPJ>{n.dest[0]}</CNPJ><xNome>{_e(n.dest[1])}</xNome><enderDest>"
            f"<xLgr>RUA EXEMPLO</xLgr><nro>100</nro><xBairro>CENTRO</xBairro><cMun>0000000</cMun>"
            f"<xMun>CIDADE EXEMPLO</xMun><UF>{n.dest[2]}</UF></enderDest><indIEDest>1</indIEDest>"
            f"<IE>ISENTO</IE></dest>"
        )
    nat = "VENDA DE MERCADORIA" if n.emit[0] == n.negocio.cnpj else "VENDA DE MERCADORIA A CONTRIBUINTE"
    pag = f"<pag><detPag><tPag>{'17' if n.modelo == '65' else '15'}</tPag><vPag>{total:.2f}</vPag></detPag></pag>"
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<nfeProc xmlns="{NS}" versao="4.00"><NFe><infNFe '
        f'Id="NFe{chave}" versao="4.00"><ide><cUF>{UF_COD[emit_uf]}</cUF><cNF>{chave[35:43]}</cNF>'
        f"<natOp>{nat}</natOp><mod>{n.modelo}</mod><serie>{n.serie}</serie><nNF>{n.numero}</nNF>"
        f"<dhEmi>{n.data.isoformat()}T{n.hora}-03:00</dhEmi><tpNF>1</tpNF><idDest>{id_dest}</idDest>"
        f"<cMunFG>0000000</cMunFG><tpImp>{'4' if n.modelo == '65' else '1'}</tpImp><tpEmis>1</tpEmis>"
        f"<cDV>{chave[-1]}</cDV><tpAmb>2</tpAmb><finNFe>1</finNFe><indFinal>{n.ind_final}</indFinal>"
        f"<indPres>{n.ind_pres}</indPres><procEmi>0</procEmi><verProc>RAIO-X EXEMPLO</verProc></ide>"
        f"<emit><CNPJ>{emit_cnpj}</CNPJ><xNome>{_e(emit_nome)}</xNome><enderEmit><xLgr>RUA EXEMPLO</xLgr>"
        f"<nro>1</nro><xBairro>CENTRO</xBairro><cMun>0000000</cMun><xMun>CIDADE EXEMPLO</xMun>"
        f"<UF>{emit_uf}</UF></enderEmit><IE>ISENTO</IE><CRT>{crt}</CRT></emit>{dest}{''.join(dets)}"
        f"<total><ICMSTot><vProd>{total:.2f}</vProd><vNF>{total:.2f}</vNF></ICMSTot></total>"
        f"<transp><modFrete>9</modFrete></transp>{pag}</infNFe></NFe>"
        f'<protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><chNFe>{chave}</chNFe><cStat>100</cStat>'
        f"<xMotivo>EXEMPLO: nota sintetica do Raio-X, sem valor fiscal</xMotivo></infProt></protNFe></nfeProc>\n"
    )


def xml_cancelamento(n: NotaEx) -> str:
    chave = n.chave
    quando = (n.data + timedelta(days=1)).isoformat()
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<procEventoNFe xmlns="{NS}" versao="1.00"><evento versao="1.00">'
        f'<infEvento Id="ID110111{chave}01"><cOrgao>{UF_COD[n.emit[2]]}</cOrgao><tpAmb>2</tpAmb>'
        f"<CNPJ>{n.emit[0]}</CNPJ><chNFe>{chave}</chNFe><dhEvento>{quando}T09:00:00-03:00</dhEvento>"
        f'<tpEvento>110111</tpEvento><nSeqEvento>1</nSeqEvento><detEvento versao="1.00">'
        f"<descEvento>Cancelamento</descEvento><xJust>EXEMPLO: pedido desfeito pelo cliente</xJust>"
        f"</detEvento></infEvento></evento></procEventoNFe>\n"
    )


# ---------------------------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------------------------

LEIA_ME = """NOTAS DE EXEMPLO DO RAIO-X FISCAL
=================================

Nada aqui é nota real. As 8 empresas são inventadas (todas com EXEMPLO no nome), os CNPJs só têm
o dígito verificador certo para passar no formato e as chaves são de homologação (tpAmb=2).
Os PRODUTOS são reais: descrições tiradas das notas públicas do Portal da Transparência, com o
NCM que aparece em 85% ou mais das vezes para aquela descrição.

O que tem aqui
- notas/<empresa>/  ->  os XML (NF-e modelo 55 e NFC-e modelo 65, leiaute 4.00) e 2 eventos de cancelamento
- gabarito.csv      ->  item por item, o erro que foi plantado de propósito (vazio = item sem erro)
- regras-do-escritorio.csv  ->  1 caso que está certo de propósito (o Raio-X mostra como "aceito")
- cadastros/        ->  a planilha do cadastro de produtos de cada empresa (porta 2 do Raio-X)

Como testar
1. Abra o Raio-X e arraste este .zip inteiro (ou a pasta notas/) na porta 1.
2. Compare o que ficou vermelho e amarelo com o gabarito.csv.
3. Na porta 2, envie um arquivo da pasta cadastros/ para ver o cadastro conferido antes de emitir.
"""


def _csv(linhas: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(linhas[0]), delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(linhas)
    return buf.getvalue()


def regras_escritorio() -> str:
    neg = next(n for n in NEGOCIOS if n.id == REGRA_ACEITA[0])
    return (
        "# Regra do escritório (EXEMPLO): o que está certo de propósito. Vazio = qualquer.\n"
        "cnpj_empresa;regra;cfop;ncm;codigo_produto;motivo\n"
        f"{neg.cnpj};{REGRA_ACEITA[1]};{REGRA_ACEITA[2]};;;{REGRA_ACEITA[3]}\n"
    )


def cadastro_generico(prods: list[Produto]) -> str:
    linhas = [
        {
            "Código": p.codigo,
            "Descrição": p.descricao,
            "Unidade": p.unidade,
            "NCM": p.ncm_cadastro,
            "GTIN/EAN": p.gtin or "",
            "Preço": f"{p.preco:.2f}".replace(".", ","),
        }
        for p in prods
    ]
    return _csv(linhas)


def cadastro_bling(prods: list[Produto], id_inicial: int = 700001) -> str:
    """Mesmas primeiras colunas da exportação de produtos do Bling (ID, Código, Descrição, Unidade, NCM...)."""
    cab = "ID;Código;Descrição;Unidade;NCM;Origem;Preço;Valor IPI fixo;Observações;Situação;GTIN/EAN;CEST"
    corpo = []
    for k, p in enumerate(prods):
        n = p.ncm_cadastro
        ncm = f"{n[:4]}.{n[4:6]}.{n[6:]}" if len(n) == 8 else n
        preco = f"{p.preco:.2f}".replace(".", ",")
        corpo.append(f"{id_inicial + k};{p.codigo};{p.descricao};{p.unidade};{ncm};0;{preco};0;;Ativo;{p.gtin or ''};")
    return cab + "\n" + "\n".join(corpo) + "\n"


def arquivos(semente: int = SEMENTE) -> dict[str, bytes]:
    """{caminho dentro do zip: bytes} de tudo (notas, eventos, gabarito, cadastros, regras, leia-me)."""
    notas, cadastros, gabarito = montar(semente)
    out: dict[str, bytes] = {}
    for n in notas:
        base = f"{PASTA_ZIP}/notas/{n.negocio.id}/{n.chave}"
        out[f"{base}-{'nfce' if n.modelo == '65' else 'nfe'}.xml"] = xml_nota(n).encode()
        if n.cancelada:
            out[f"{base}-cancelamento.xml"] = xml_cancelamento(n).encode()
    out[f"{PASTA_ZIP}/gabarito.csv"] = ("﻿" + _csv(gabarito)).encode()
    out[f"{PASTA_ZIP}/regras-do-escritorio.csv"] = regras_escritorio().encode()
    out[f"{PASTA_ZIP}/LEIA-ME.txt"] = LEIA_ME.encode()
    for neg_id, prods in cadastros.items():
        if neg_id == "mercado-bom-preco":
            out[f"{PASTA_ZIP}/cadastros/cadastro-{neg_id}-bling.csv"] = ("﻿" + cadastro_bling(prods)).encode()
        else:
            out[f"{PASTA_ZIP}/cadastros/cadastro-{neg_id}.csv"] = ("﻿" + cadastro_generico(prods)).encode()
    return out


def zip_bytes(semente: int = SEMENTE) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, dados in sorted(arquivos(semente).items()):
            info = zipfile.ZipInfo(nome, date_time=(2026, 11, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, dados)
    return buf.getvalue()


def gerar(destino: Path, semente: int = SEMENTE) -> dict:
    """Escreve o .zip e a pasta aberta em `destino` (sobrescreve)."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    z = zip_bytes(semente)
    (destino / f"{PASTA_ZIP}.zip").write_bytes(z)
    n_xml = 0
    for nome, dados in arquivos(semente).items():
        p = destino / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)
        n_xml += nome.endswith(".xml")
    return {"zip": str(destino / f"{PASTA_ZIP}.zip"), "bytes": len(z), "xml": n_xml}


# ---------------------------------------------------------------------------------------------
# Conferência: o que foi plantado x o que o Raio-X marcou
# ---------------------------------------------------------------------------------------------


def conferir(resultado, gabarito: list[dict]) -> dict:
    """Junta o resultado da auditoria com o gabarito (por chave da nota + número do item)."""
    itens = resultado.itens
    achou = {}
    for _, r in itens.iterrows():
        regras = {a.regra for a in r["_achados"] if a.nivel > 0 and not a.aceito}
        aceitas = {a.regra for a in r["_achados"] if a.aceito}
        achou[(r["chave"], int(r["n_item"]))] = (r["semaforo"], regras, aceitas)
    por_tipo: dict[str, dict] = {}
    falsos: dict[str, int] = {}
    limpos = limpos_verdes = 0
    perdidos = []
    for g in gabarito:
        sem, regras, aceitas = achou.get((g["chave"], int(g["item"])), ("?", set(), set()))
        erros = [e for e in g["erro_plantado"].split(", ") if e]
        if not erros:
            limpos += 1
            if sem == "verde" or not regras:
                limpos_verdes += 1
            else:
                for rg in regras:
                    falsos[rg] = falsos.get(rg, 0) + 1
            continue
        for e in erros:
            esperada = TIPOS_ERRO[e][1]
            d = por_tipo.setdefault(e, {"o_que_e": TIPOS_ERRO[e][0], "regra": esperada, "itens": 0, "pegos": 0})
            d["itens"] += 1
            if esperada in regras:
                d["pegos"] += 1
            else:
                perdidos.append({**g, "semaforo": sem, "regras_marcadas": ", ".join(sorted(regras))})
    total = sum(d["itens"] for d in por_tipo.values())
    pegos = sum(d["pegos"] for d in por_tipo.values())
    return {
        "itens": len(gabarito),
        "itens_com_erro": sum(1 for g in gabarito if g["erro_plantado"]),
        "erros_plantados": total,
        "erros_pegos": pegos,
        "por_tipo": por_tipo,
        "itens_limpos": limpos,
        "limpos_sem_alerta": limpos_verdes,
        "falsos_alarmes_por_regra": falsos,
        "perdidos": perdidos,
    }


def relatorio_md(conf: dict, resumo: dict, modelo: str) -> str:
    """reports/exemplos_lojas.md: o que foi plantado x o que o Raio-X marcou."""
    linhas = [
        "# Notas de exemplo dos 8 comércios: o que foi plantado x o que o Raio-X marcou",
        "",
        f"Gerado por `rxf exemplos-lojas` em {resumo['gerado_em']}. Modelo: {modelo or 'sem modelo (só regras)'}.",
        "",
        "8 empresas inventadas (mercado, autopeças, farmácia, material de construção, loja de roupas, restaurante,",
        "papelaria e informática), em 8 estados, com NF-e (modelo 55) e NFC-e (modelo 65) no leiaute 4.00. Os produtos",
        "são descrições reais das notas públicas do Portal da Transparência, com o NCM que aparece em 85% ou mais das",
        "vezes para aquela descrição (`src/raio_x_fiscal/seeds/catalogo_exemplos.csv`, gerado por",
        "`scripts/extrair_catalogo_exemplos.py`). Os erros foram plantados como nascem no escritório: a maioria no",
        "cadastro do produto (e se repete em toda nota com ele), alguns só numa nota.",
        "",
        f"- {resumo['notas']} notas, {conf['itens']} itens; {conf['itens_com_erro']} itens com algum erro plantado "
        f"({100 * conf['itens_com_erro'] / conf['itens']:.0f}%).",
        f"- Semáforo: {resumo['vermelho']} vermelho, {resumo['amarelo']} amarelo, {resumo['verde']} verde; "
        f"{resumo['aceitos_escritorio']} alertas aceitos pela regra do escritório (um caso certo de propósito).",
        f"- **Erros plantados marcados: {conf['erros_pegos']} de {conf['erros_plantados']}.**",
        "",
        "| Erro plantado | Regra que deve acusar | Itens | Marcados |",
        "|---|---|---:|---:|",
    ]
    for d in conf["por_tipo"].values():
        linhas.append(f"| {d['o_que_e']} | `{d['regra']}` | {d['itens']} | {d['pegos']} |")
    linhas += [
        "",
        f"Itens sem erro plantado: {conf['itens_limpos']}; sem nenhum alerta: {conf['limpos_sem_alerta']}.",
        "Cuidado ao ler este número: os produtos limpos foram escolhidos entre descrições em que o modelo concorda",
        "com o NCM de consenso, então ele não mede alarme falso. O alarme falso é medido na amostra pública",
        "([produto_amostra_publica.md](produto_amostra_publica.md)).",
        "",
    ]
    if conf["perdidos"]:
        linhas += ["## O que passou", ""]
        vistos = set()
        for p in conf["perdidos"]:
            k = (p["descricao"], p["ncm_na_nota"])
            if k in vistos:
                continue
            vistos.add(k)
            linhas.append(
                f"- {p['descricao']} com NCM {p['ncm_na_nota']} ({p['o_que_e'].lower()}): semáforo {p['semaforo']}."
            )
        linhas += [
            "",
            "Nesses casos o NCM errado estava entre os mais prováveis para o modelo, ou o modelo não teve certeza",
            "suficiente; o Raio-X prefere deixar passar a acusar sem certeza.",
            "",
        ]
    return "\n".join(linhas)
