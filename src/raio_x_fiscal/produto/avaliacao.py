"""Como o semáforo se comporta em notas reais: amostra do dado público, num mês que o modelo não viu.

    rxf avaliar-publico --mes 202509 --amostra 50000

As notas públicas (compras do governo federal) passam pelo MESMO motor das notas XML: cada linha do
gold vira uma `Nota` com seus itens. O que não existe no dado público (CRT, CST, GTIN, código do
produto) simplesmente não dispara as regras que dependem disso. Grava `reports/produto_amostra_publica.md`.

É também o "backtest do mês": o modelo foi treinado até 2025-07 e calibrado em 2025-08; 2025-09 é
um mês que ele nunca viu. Rodar isso todo mês, com o mês novo, mede o acerto sem ninguém conferir à mão.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime

from raio_x_fiscal.config import ROOT, Paths, connect
from raio_x_fiscal.fmt import num, pct
from raio_x_fiscal.produto import motor
from raio_x_fiscal.produto import regras as R
from raio_x_fiscal.produto.nfe import Item, Leitura, Nota

log = logging.getLogger(__name__)
RELATORIO = ROOT / "reports" / "produto_amostra_publica.md"


def _codigo(s: str | None) -> str | None:
    return (s or "").split(" ", 1)[0].strip() or None


def amostra_publica(paths: Paths, mes: str, n: int, semente: int = 42) -> Leitura:
    rotulo = f"{mes[:4]}-{mes[4:]}"
    with connect(paths.gold_db, read_only=True) as con:
        con.execute(f"SELECT setseed({semente / 100})")
        df = con.execute(
            """
            WITH notas AS (
              SELECT chave_acesso FROM fato_nota WHERE mes_referencia = ? ORDER BY random() LIMIT ?
            )
            SELECT i.chave_acesso, i.numero_produto, i.data_emissao, i.emitente_id, i.emitente_uf,
                   i.destinatario_uf, i.cfop, coalesce(i.ncm_codigo, i.ncm_raw) AS ncm, i.descricao_produto,
                   i.quantidade, i.unidade, i.valor_unitario, i.valor_total,
                   n.modelo, n.destino_operacao, n.presenca_comprador, n.consumidor_final, n.numero_nota
            FROM fato_item i JOIN notas USING (chave_acesso) JOIN fato_nota n USING (chave_acesso)
            ORDER BY i.chave_acesso, i.numero_produto
            """,
            [rotulo, max(1, n // 3)],
        ).df()
    df = df.head(n)
    leitura = Leitura()
    for chave, g in df.groupby("chave_acesso", sort=False):
        r = g.iloc[0]
        nota = Nota(
            arquivo="dado-publico",
            grupo=None,
            chave=chave,
            modelo=str(int(r["modelo"])) if r["modelo"] == r["modelo"] else "55",
            serie="",
            numero=str(r["numero_nota"]),
            data_emissao=r["data_emissao"].date() if hasattr(r["data_emissao"], "date") else r["data_emissao"],
            natureza="",
            tp_nf="",  # o dado público não diz se a nota é de entrada ou de saída
            id_dest=_codigo(r["destino_operacao"]),
            ind_pres=_codigo(r["presenca_comprador"]),
            ind_final=_codigo(r["consumidor_final"]),
            fin_nfe=None,
            emit_cnpj=str(r["emitente_id"]),
            emit_nome="",
            emit_uf=r["emitente_uf"] or "",
            crt=None,
            dest_doc=None,
            dest_nome="órgão público",
            dest_uf=r["destinatario_uf"],
            valor_total=float(g["valor_total"].sum()),
        )
        nota.itens = [
            Item(
                n_item=int(x["numero_produto"]),
                codigo="",
                gtin=None,
                descricao=x["descricao_produto"] or "",
                ncm="00" if (x["ncm"] or "").strip() in ("", "-1") else x["ncm"],  # -1 = sem NCM no CSV
                cest=None,
                cfop=x["cfop"] or "",
                unidade=x["unidade"] or "",
                quantidade=float(x["quantidade"] or 0),
                valor_unitario=float(x["valor_unitario"] or 0),
                valor_total=float(x["valor_total"] or 0),
            )
            for _, x in g.iterrows()
        ]
        leitura.notas.append(nota)
    leitura.arquivos_lidos = len(leitura.notas)
    return leitura


def avaliar(paths: Paths, mes: str = "202509", n: int = 50_000) -> dict:
    t0 = datetime.now()
    ctx = motor.Contexto.padrao(paths.data, paths.models)
    leitura = amostra_publica(paths, mes, n)
    t1 = datetime.now()
    res = motor.auditar_notas(leitura, ctx)
    seg = (datetime.now() - t1).total_seconds()
    s = res.resumo
    itens = res.itens
    total = len(itens)

    # Concordância do NCM declarado com o modelo (o "acerto" possível sem gabarito humano).
    conf = itens["confianca_modelo"].fillna(0)
    top1 = itens["top3_modelo"].str.split(" ").str[0].fillna("")
    concorda = int((top1 == itens["ncm"]).sum())
    no_top3 = int(sum(ncm in t for ncm, t in zip(itens["ncm"], itens["top3_modelo"].fillna(""), strict=True)))
    faixas = Counter()
    for c in conf:
        faixas["≥ 0,99" if c >= 0.99 else "0,90 a 0,99" if c >= 0.9 else "0,50 a 0,90" if c >= 0.5 else "< 0,50"] += 1

    regras_itens: dict[str, Counter] = defaultdict(Counter)
    presencial = 0
    for achados in itens["_achados"]:
        for a in achados:
            if a.nivel > R.VERDE:
                regras_itens[a.regra][R.NOME_NIVEL[a.nivel]] += 1
            elif a.regra == "CFOP_UF":
                presencial += 1

    exemplos = (
        itens[itens["regras"].str.contains("NCM_MODELO")]
        .sort_values("confianca_modelo", ascending=False)
        .drop_duplicates("descricao")
        .head(8)
    )
    out = {
        "mes": mes,
        "notas": s["notas"],
        "itens": total,
        "vermelho": s["vermelho"],
        "amarelo": s["amarelo"],
        "verde": s["verde"],
        "segundos_auditoria": round(seg, 1),
        "itens_por_segundo": round(total / seg) if seg else None,
        "concorda_top1": concorda,
        "concorda_top3": no_top3,
        "por_regra": {k: dict(v) for k, v in regras_itens.items()},
        "cfop_presencial_ok": presencial,
    }
    _escreve(out, faixas, exemplos, ctx, t0)
    return out


def _escreve(o: dict, faixas: Counter, exemplos, ctx, t0) -> None:
    n = max(o["itens"], 1)
    linhas = [
        "# Raio-X Fiscal: o produto numa amostra real do dado público",
        "",
        f"Gerado por `rxf avaliar-publico` em {t0:%d/%m/%Y %H:%M}. Mês {o['mes'][:4]}-{o['mes'][4:]} (o modelo",
        "foi treinado até 2025-07 e calibrado em 2025-08: este mês ele nunca viu). Notas sorteadas com semente fixa;",
        "cada nota pública passa pelo mesmo motor das notas XML. Sem CST, CRT, GTIN e código do produto no dado",
        "público, as regras que dependem deles não rodam aqui (elas estão cobertas pelos testes e pelos XML de exemplo).",
        "",
        "## Semáforo",
        "",
        "| | Itens | % |",
        "|---|---:|---:|",
        f"| Vermelho (erro provável) | {num(o['vermelho'])} | {pct(o['vermelho'] / n)} |",
        f"| Amarelo (conferir) | {num(o['amarelo'])} | {pct(o['amarelo'] / n)} |",
        f"| Verde (ok) | {num(o['verde'])} | {pct(o['verde'] / n)} |",
        f"| **Total** | **{num(o['itens'])}** ({num(o['notas'])} notas) | |",
        "",
        f"Tempo do motor (regras + modelo, CPU de 2 núcleos): {num(o['segundos_auditoria'], 1)} s, "
        f"cerca de {num(o['itens_por_segundo'] or 0)} itens por segundo.",
        "",
        "## Por checagem",
        "",
        "| Checagem | Vermelho | Amarelo |",
        "|---|---:|---:|",
    ]
    for regra, c in sorted(o["por_regra"].items(), key=lambda kv: -sum(kv[1].values())):
        linhas.append(f"| {R.REGRAS.get(regra, regra)} | {num(c.get('vermelho', 0))} | {num(c.get('amarelo', 0))} |")
    linhas += [
        "",
        f"Além disso, {num(o['cfop_presencial_ok'])} itens com CFOP de dentro do estado numa nota para outro estado",
        "ficaram verdes sozinhos porque a nota diz que a venda foi presencial (nesse caso a operação é interna).",
        "",
        "## O modelo e o NCM declarado (sem gabarito humano)",
        "",
        f"- O NCM da nota é o 1º do modelo em {pct(o['concorda_top1'] / n)} dos itens e está entre os 3 primeiros "
        f"em {pct(o['concorda_top3'] / n)}.",
        f"- Vermelho do modelo: confiança ≥ {ctx.limiar_vermelho:.2f} e o NCM declarado diferente (o limiar da "
        "auditoria da fase 1, em que 50 de 60 alertas inspecionados à mão eram erro real).",
        f"- Amarelo do modelo: confiança ≥ {ctx.limiar_amarelo:.2f} e o NCM declarado fora dos 5 mais prováveis; "
        f"ou o NCM declarado fora dos 10 mais prováveis e de outro capítulo (confiança ≥ {R.LIMIAR_OUTRO_CAPITULO:.2f}) "
        f"ou de outra posição de 4 dígitos (confiança ≥ {R.LIMIAR_OUTRA_POSICAO:.2f}). Esta última entrou em "
        "08/11/2026: nesta amostra ela marca mais 1,6% dos itens; em 43% deles quase ninguém usa aquele NCM para "
        "aquela descrição no dado público (provável erro real) e em menos de 5% o NCM da nota é o de sempre "
        "(provável alarme falso).",
        "",
        "| Confiança do 1º NCM do modelo | Itens |",
        "|---|---:|",
    ]
    for k in ["≥ 0,99", "0,90 a 0,99", "0,50 a 0,90", "< 0,50"]:
        linhas.append(f"| {k} | {num(faixas.get(k, 0))} |")
    linhas += ["", "## Exemplos de vermelho e amarelo do modelo (os mais confiantes)", ""]
    linhas += ["| Descrição | NCM da nota | Sugerido | Confiança |", "|---|---|---|---:|"]
    for _, r in exemplos.iterrows():
        d = str(r["descricao"]).replace("|", "/")[:70]
        linhas.append(
            f"| {d} | {R.fmt_ncm(r['ncm'])} | {R.fmt_ncm(r['ncm_sugerido'])} | {pct(r['confianca_modelo'])} |"
        )
    linhas += [
        "",
        "## Como ler",
        "",
        "- CFOP x estados vira amarelo, nunca vermelho: em compra pública muita venda entre estados sai com",
        "  5.xxx por ser presencial ou por regra da operação. A regra do escritório tira o que é de propósito.",
        "- NCM fora da tabela em nota de 2025 fica amarelo: a cópia mais antiga da tabela guardada é de",
        '  07/11/2026, então para notas anteriores o Raio-X só diz "não existe mais hoje; corrija o cadastro".',
        "",
    ]
    RELATORIO.write_text("\n".join(linhas), encoding="utf-8")
    log.info("relatório: %s", RELATORIO)
