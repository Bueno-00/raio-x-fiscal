"""Monta o catálogo de produtos das notas de exemplo a partir do DADO PÚBLICO (gold).

Para cada tipo de negócio, procura descrições reais que começam por palavras típicas daquele
comércio ("ARROZ", "FILTRO DE OLEO", "DIPIRONA"...), e fica só com as que têm NCM conhecido:
- a descrição aparece pelo menos 8 vezes no dado público;
- pelo menos 85% dessas vezes com o mesmo NCM (o "NCM de consenso");
- o NCM existe na tabela oficial de hoje;
- o modelo da fase 1 concorda com o NCM de consenso (top-1, confiança >= 0,5), para que o item
  "limpo" das notas de exemplo seja limpo de verdade.

Também guarda pares (descrição, NCM antigo) cujo NCM não existe mais na tabela de hoje: viram o
erro plantado "código antigo no cadastro".

Saída: src/raio_x_fiscal/seeds/catalogo_exemplos.csv (vai para o git; dado público, sem CNPJ).
Rodar:  .venv/bin/python scripts/extrair_catalogo_exemplos.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from raio_x_fiscal.pipeline.normalize import normalize_description  # noqa: E402
from raio_x_fiscal.produto.motor import Classificador  # noqa: E402
from raio_x_fiscal.produto.ncm_tabela import HistoricoNCM  # noqa: E402

PALAVRAS = {
    "mercado": [
        "ARROZ", "FEIJAO", "ACUCAR", "CAFE TORRADO", "CAFE EM PO", "OLEO DE SOJA", "LEITE UHT", "LEITE INTEGRAL",
        "LEITE CONDENSADO", "MACARRAO", "FARINHA DE TRIGO", "MOLHO DE TOMATE", "EXTRATO DE TOMATE", "BISCOITO",
        "SAL REFINADO", "MARGARINA", "CREME DE LEITE", "AGUA MINERAL", "REFRIGERANTE", "SUCO", "DETERGENTE",
        "SABAO EM PO", "PAPEL HIGIENICO", "CREME DENTAL", "SABONETE", "AMACIANTE", "AGUA SANITARIA", "BANANA",
        "TOMATE", "CEBOLA", "BATATA", "OVOS", "ACHOCOLATADO", "FUBA", "MILHO VERDE", "VINAGRE", "AZEITE",
        "SARDINHA", "ERVILHA", "GOIABADA",
    ],
    "autopecas": [
        "FILTRO DE OLEO", "FILTRO DE AR", "FILTRO DE COMBUSTIVEL", "FILTRO COMBUSTIVEL", "PASTILHA DE FREIO",
        "PASTILHA FREIO", "DISCO DE FREIO", "OLEO LUBRIFICANTE", "OLEO MOTOR", "OLEO DE MOTOR", "PNEU",
        "BATERIA 12V", "BATERIA AUTOMOTIVA", "VELA DE IGNICAO", "CORREIA DENTADA", "CORREIA", "AMORTECEDOR",
        "LAMPADA H4", "LAMPADA H7", "PALHETA", "FLUIDO DE FREIO", "ADITIVO", "ROLAMENTO", "BOMBA D AGUA",
        "KIT EMBREAGEM", "LONA DE FREIO", "CABO DE VELA", "TERMINAL DE DIRECAO",
    ],
    "farmacia": [
        "DIPIRONA", "PARACETAMOL", "IBUPROFENO", "AMOXICILINA", "LOSARTANA", "OMEPRAZOL", "SORO FISIOLOGICO",
        "ALCOOL 70", "ALCOOL EM GEL", "GAZE", "ESPARADRAPO", "LUVA DE PROCEDIMENTO", "SERINGA", "FRALDA",
        "ABSORVENTE", "PROTETOR SOLAR", "SHAMPOO", "ESCOVA DENTAL", "TERMOMETRO", "METFORMINA", "VITAMINA C",
        "ALGODAO", "CURATIVO", "ATADURA", "SIMETICONA", "LORATADINA", "CAPTOPRIL", "HIDROCLOROTIAZIDA",
    ],
    "construcao": [
        "CIMENTO", "AREIA", "BRITA", "CAL HIDRATADA", "ARGAMASSA", "TIJOLO", "BLOCO DE CONCRETO", "VERGALHAO",
        "TUBO PVC", "JOELHO", "TINTA ACRILICA", "MASSA CORRIDA", "FIO FLEXIVEL", "CABO FLEXIVEL", "DISJUNTOR",
        "TOMADA", "INTERRUPTOR", "PREGO", "PISO CERAMICO", "REJUNTE", "TELHA", "REGISTRO", "TORNEIRA",
        "CAIXA D AGUA", "LIXA", "ROLO DE PINTURA", "SELADOR", "MANTA ASFALTICA", "PARAFUSO", "BUCHA",
    ],
    "roupas": [
        "CAMISETA", "CAMISA POLO", "CALCA JEANS", "BERMUDA", "JAQUETA", "MOLETOM", "BLUSA", "VESTIDO", "SAIA",
        "MEIA", "CUECA", "CALCINHA", "TENIS", "SAPATO", "SANDALIA", "CHINELO", "BONE", "CINTO", "AGASALHO",
        "CAMISA SOCIAL", "SHORT", "PIJAMA", "CALCA", "CAMISA", "SUTIA", "LEGGING", "REGATA", "BOTA", "TOUCA",
        "GRAVATA", "BLUSA DE", "JAQUETA JEANS", "TOP ",
    ],
    "restaurante": [
        "REFEICAO", "MARMITEX", "MARMITA", "LANCHE", "SALGADO", "SUCO NATURAL", "REFRIGERANTE LATA",
        "AGUA MINERAL 500", "SANDUICHE", "PAO DE QUEIJO", "BOLO", "PIZZA", "PRATO FEITO", "CAFE DA MANHA",
        "COFFEE BREAK", "SUCO DE LARANJA", "ALMOCO", "JANTAR", "SOBREMESA", "CHA ",
    ],
    "papelaria": [
        "CANETA ESFEROGRAFICA", "LAPIS PRETO", "LAPIS GRAFITE", "BORRACHA", "CADERNO", "PAPEL A4", "PAPEL SULFITE",
        "GRAMPEADOR", "GRAMPO", "CLIPS", "COLA BRANCA", "TESOURA", "PASTA", "ENVELOPE", "MARCA TEXTO",
        "CORRETIVO", "FITA ADESIVA", "REGUA", "APONTADOR", "PINCEL ATOMICO", "BLOCO DE NOTAS", "ETIQUETA",
        "LIVRO ATA", "PERFURADOR",
    ],
    "informatica": [
        "MOUSE", "TECLADO", "MONITOR", "NOTEBOOK", "COMPUTADOR", "HD EXTERNO", "PEN DRIVE", "PENDRIVE", "SSD",
        "MEMORIA RAM", "CABO HDMI", "ROTEADOR", "SWITCH", "NOBREAK", "ESTABILIZADOR", "IMPRESSORA", "TONER",
        "CARTUCHO", "WEBCAM", "HEADSET", "FONTE ATX", "CABO DE REDE", "ADAPTADOR",
    ],
}  # fmt: skip

# Compras públicas têm muito item que nenhum comércio comum vende: fora.
PROIBIDAS = re.compile(
    r"ICMBIO|AMOSTRA|PLACEBO|MILITAR|EXERCITO|COMBATE|BRIGADIST|ANALISE|PARENTERAL|LICITA|PREGAO|CONTRATO|"
    r"EMPENHO|ITEM \d|LOTE|CONFORME|SOLICITA|TERMO DE REF|\bTR\b|SIAFI|CATMAT|POLICIA|PRF|FUNAI|EMBRAPA|"
    r"UNIFORME|FARDA|DIVERSOS|MATERIAL P|MATERIAIS|SERVICO|MANUTENC|HOSPITALAR|LABORAT|CIRURG|VETERIN|"
    r"ESPEC|DESCRI|MARCA:|REF\.|FABRIC|MODELO:|COD\.|CODIGO|\(|\)|\*|;",
    re.IGNORECASE,
)

MIN_VEZES, MIN_CONSENSO, POR_PALAVRA = 8, 0.85, 3
POR_PALAVRA_NEGOCIO = {"roupas": 5}


def main() -> None:
    con = duckdb.connect(str(RAIZ / "data/gold/raio_x_fiscal.duckdb"), read_only=True)
    con.execute("SET enable_progress_bar=false")
    hist = HistoricoNCM.carregar(RAIZ / "data")
    tabela = hist.atual
    clf = Classificador.carregar(RAIZ / "models")
    if clf is None:
        raise SystemExit("precisa do modelo em models/ (make ml)")

    base = con.sql(
        """
        with b as (
          select descricao_normalizada dn, ncm_codigo ncm, count(*) n,
                 mode(upper(descricao_produto)) d, median(valor_unitario) pu, mode(upper(unidade)) un
          from fato_item where ncm_valido group by 1, 2),
        t as (select dn, sum(n) tot from b group by 1)
        select b.dn, b.ncm, b.n, t.tot, b.n / t.tot share, b.d, b.pu, b.un,
               row_number() over (partition by b.dn order by b.n desc) r
        from b join t using (dn)
        """
    ).df()
    consenso = base[(base.r == 1) & (base.tot >= MIN_VEZES) & (base.share >= MIN_CONSENSO)].copy()
    consenso = consenso[consenso["d"].str.len().between(8, 46)]
    consenso = consenso[~consenso["d"].str.contains(r"\d{7,}", regex=True)]
    consenso = consenso[~consenso["d"].str.contains(PROIBIDAS)]
    consenso = consenso[consenso["ncm"].map(tabela.existe)]

    linhas = []
    for negocio, palavras in PALAVRAS.items():
        for p in palavras:
            pn = normalize_description(p)
            cand = consenso[consenso["dn"].str.startswith(pn + " ") | (consenso["dn"] == pn)]
            cand = cand.sort_values("tot", ascending=False).head(25)
            if cand.empty:
                continue
            sug = clf.sugerir(cand["d"].tolist(), tabela, k=3)
            escolhidos = 0
            for _, r in cand.iterrows():
                s = sug.get(normalize_description(r["d"]), [])
                if not s or s[0][0] != r["ncm"] or s[0][1] < 0.5:
                    continue
                linhas.append(
                    {
                        "negocio": negocio,
                        "palavra": p,
                        "descricao": re.sub(r"\s+", " ", r["d"]).strip(),
                        "ncm": r["ncm"],
                        "unidade": (r["un"] if isinstance(r["un"], str) and r["un"] else "UN")[:6],
                        "preco": round(float(r["pu"] or 1), 2),
                        "vezes_no_dado_publico": int(r["tot"]),
                        "consenso": round(float(r["share"]), 3),
                        "confianca_modelo": round(s[0][1], 3),
                        "ncm_antigo": "",
                    }
                )
                escolhidos += 1
                if escolhidos >= POR_PALAVRA_NEGOCIO.get(negocio, POR_PALAVRA):
                    break

    # Códigos antigos: descrição real com NCM que não existe mais na tabela de hoje.
    antigos = base[(base.r == 1) & (base.tot >= 5) & (base.share >= 0.8)].copy()
    antigos = antigos[~antigos["ncm"].map(tabela.existe)]
    antigos = antigos[antigos["d"].str.len().between(8, 46) & ~antigos["d"].str.contains(PROIBIDAS)]
    antigos = antigos[~antigos["d"].str.contains(r"\d{7,}", regex=True)]
    for _, r in antigos.sort_values("tot", ascending=False).head(60).iterrows():
        linhas.append(
            {
                "negocio": "codigo_antigo",
                "palavra": "",
                "descricao": re.sub(r"\s+", " ", r["d"]).strip(),
                "ncm": "",
                "unidade": (r["un"] if isinstance(r["un"], str) and r["un"] else "UN")[:6],
                "preco": round(float(r["pu"] or 1), 2),
                "vezes_no_dado_publico": int(r["tot"]),
                "consenso": round(float(r["share"]), 3),
                "confianca_modelo": "",
                "ncm_antigo": r["ncm"],
            }
        )

    destino = RAIZ / "src/raio_x_fiscal/seeds/catalogo_exemplos.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    por = {}
    for ln in linhas:
        por[ln["negocio"]] = por.get(ln["negocio"], 0) + 1
    print(destino, len(linhas), por)


if __name__ == "__main__":
    main()
