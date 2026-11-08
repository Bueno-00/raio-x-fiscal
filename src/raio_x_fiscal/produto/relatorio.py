"""Relatório do Raio-X: página HTML (um arquivo só, abre offline) e planilha XLSX.

O HTML é feito para ler no computador (largo, em colunas) e funciona no celular (cada item vira
um cartão). Todo texto que vem da nota passa por `html.escape`: XML de terceiro é dado, não código.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from raio_x_fiscal.produto import regras as R

CORES = {"vermelho": "#b42318", "amarelo": "#a15c00", "verde": "#1f7a4d"}
FUNDOS = {"vermelho": "#fdecea", "amarelo": "#fff4d6", "verde": "#e9f6ef"}
ROTULO = {"vermelho": "Erro provável", "amarelo": "Conferir", "verde": "Ok"}
ORDEM = {"vermelho": 0, "amarelo": 1, "verde": 2}

COLUNAS_XLSX = {
    "grupo": "Pasta / empresa",
    "empresa_cnpj": "CNPJ da empresa",
    "sentido": "Sentido para a empresa",
    "numero": "Nota",
    "serie": "Série",
    "data_emissao": "Emissão",
    "emitente": "Emitente",
    "emitente_cnpj": "CNPJ emitente",
    "emitente_uf": "UF emitente",
    "destinatario": "Destinatário",
    "destinatario_uf": "UF destinatário",
    "n_item": "Item",
    "codigo": "Código do produto",
    "gtin": "GTIN/EAN",
    "descricao": "Descrição",
    "ncm": "NCM da nota",
    "ncm_descricao_oficial": "Descrição oficial do NCM da nota",
    "cfop": "CFOP",
    "cst_csosn": "CST/CSOSN",
    "quantidade": "Quantidade",
    "valor_total": "Valor (R$)",
    "semaforo": "Semáforo",
    "motivo": "Motivo",
    "o_que_fazer": "O que fazer",
    "ncm_sugerido": "NCM sugerido",
    "ncm_sugerido_descricao": "Descrição oficial do NCM sugerido",
    "cfop_sugerido": "CFOP sugerido",
    "confianca_modelo": "Confiança do modelo",
    "top3_modelo": "3 NCMs mais prováveis (modelo)",
    "regras": "Regras",
    "aceitas_escritorio": "Aceito pela regra do escritório",
    "chave": "Chave de acesso",
}

e = html.escape


def fmt_doc(d: str) -> str:
    d = "".join(c for c in str(d or "") if c.isdigit())
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"  # CPF de pessoa: só o miolo, como nos portais públicos
    return d


def fmt_data(d) -> str:
    try:
        return pd.Timestamp(d).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""


def fmt_moeda(v: float) -> str:
    return "R$ " + f"{v:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


CSS = """
:root{--text:#1a1a1a;--text2:#3d3d3d;--muted:#5f5f5f;--line:#d9d9d9;--line2:#ebebeb;--accent:#1F4E79;--bg:#f5f6f7;--card:#fff;
--vm:#b42318;--vm-bg:#fdecea;--am:#a15c00;--am-bg:#fff4d6;--vd:#1f7a4d;--vd-bg:#e9f6ef}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.45}
.wrap{max-width:1360px;margin:0 auto;padding:28px 32px 60px}
header{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;border-bottom:2px solid var(--accent);padding-bottom:14px;margin-bottom:20px}
.marca{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:26px;margin:2px 0 4px;font-weight:700}
.meta{color:var(--muted);font-size:13px;margin:0}
.meta b{color:var(--text2);font-weight:600}
.selo{font-size:12px;color:var(--muted);text-align:right;max-width:360px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;border-top:4px solid var(--line)}
.kpi .n{font-size:30px;font-weight:700;line-height:1.1}
.kpi .l{font-size:13px;color:var(--muted)}
.kpi.vm{border-top-color:var(--vm)}.kpi.vm .n{color:var(--vm)}
.kpi.am{border-top-color:var(--am)}.kpi.am .n{color:var(--am)}
.kpi.vd{border-top-color:var(--vd)}.kpi.vd .n{color:var(--vd)}
.kpi.esc{border-top-color:var(--accent)}.kpi.esc .n{color:var(--accent)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0;overflow-x:auto}
.box h2{font-size:15px;margin:0 0 10px}
table{border-collapse:collapse;width:100%}
.mini th,.mini td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line2);font-size:13px;vertical-align:top}
.mini th{color:var(--muted);font-weight:600;font-size:12px}
.mini td.num,.mini th.num{text-align:right;font-variant-numeric:tabular-nums}
.c-vm{color:var(--vm);font-weight:600}.c-am{color:var(--am);font-weight:600}.c-vd{color:var(--vd);font-weight:600}
.barra{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--line);margin-bottom:14px}
.barra button{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--card);border-radius:999px;padding:6px 14px;cursor:pointer;color:var(--text2)}
.barra button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
.barra input{font:inherit;font-size:13px;flex:1;min-width:200px;max-width:420px;border:1px solid var(--line);border-radius:8px;padding:7px 10px;background:#fff}
.barra .cont{color:var(--muted);font-size:13px;margin-left:auto}
.empresa{margin:22px 0 8px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.empresa h2{font-size:19px;margin:0}
.empresa .sub{color:var(--muted);font-size:13px}
details.nota{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:10px 0;overflow:hidden}
details.nota>summary{list-style:none;cursor:pointer;padding:12px 16px;display:grid;grid-template-columns:14px 1fr auto;gap:12px;align-items:center}
details.nota>summary::-webkit-details-marker{display:none}
details.nota[open]>summary{border-bottom:1px solid var(--line2)}
.titulo-nota{font-weight:600}
.titulo-nota small{font-weight:400;color:var(--muted)}
.rota{color:var(--text2);font-size:13px}
.chips{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.chip{font-size:12px;border-radius:999px;padding:2px 9px;font-weight:600;white-space:nowrap}
.chip.vm{background:var(--vm-bg);color:var(--vm)}.chip.am{background:var(--am-bg);color:var(--am)}.chip.vd{background:var(--vd-bg);color:var(--vd)}.chip.cx{background:#eee;color:#444}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;flex:none}
.dot.vermelho{background:var(--vm)}.dot.amarelo{background:#e0a100}.dot.verde{background:var(--vd)}
table.itens{table-layout:fixed}
table.itens th,table.itens td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line2);vertical-align:top;font-size:13px;overflow-wrap:anywhere}
table.itens col.c-sem{width:128px}table.itens col.c-it{width:64px}table.itens col.c-prod{width:20%}table.itens col.c-ncm{width:17%}
table.itens col.c-cfop{width:92px}table.itens col.c-sug{width:17%}
table.itens th{background:#fafafa;color:var(--muted);font-weight:600;font-size:12px}
table.itens tr:last-child td{border-bottom:0}
tr.vermelho td:first-child{box-shadow:inset 4px 0 0 var(--vm)}
tr.amarelo td:first-child{box-shadow:inset 4px 0 0 #e0a100}
tr.verde td:first-child{box-shadow:inset 4px 0 0 var(--vd)}
.cod{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;white-space:nowrap}
.of{color:var(--muted);font-size:12px;margin-top:2px}
.sug{color:var(--accent);font-weight:600}
.motivo{color:var(--text)}
.acao{margin-top:4px;color:var(--text2)}
.acao:before{content:"O que fazer: ";font-weight:600}
.aceito{margin-top:4px;color:var(--accent);font-size:12px}
.semaforo{display:flex;gap:8px;align-items:center;font-weight:600;white-space:nowrap}
.avisos{background:#fff;border:1px dashed var(--line);border-radius:10px;padding:12px 16px;margin-top:18px;color:var(--text2);font-size:13px}
.ajuda{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:26px}
.ajuda .box p{margin:6px 0 0;color:var(--text2);font-size:13px}
footer{margin-top:26px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:12px}
.oculto{display:none!important}
@media (max-width:900px){
 .wrap{padding:16px 16px 40px}
 header{flex-direction:column;align-items:flex-start}
 .selo{text-align:left}
 .kpis{grid-template-columns:repeat(2,1fr)}
 .grid2,.ajuda{grid-template-columns:1fr}
 details.nota>summary{grid-template-columns:14px 1fr}
 .chips{grid-column:1/-1;justify-content:flex-start}
 table.itens thead,table.itens colgroup{display:none}
 table.itens{table-layout:auto}
 .empresa h2{font-size:17px}
 .barra input{min-width:0;max-width:none;flex-basis:100%}
 .barra .cont{margin-left:0}
 table.itens tr{display:block;border-bottom:1px solid var(--line2);padding:8px 4px}
 table.itens td{display:block;border:0;padding:4px 10px}
 table.itens td[data-r]:before{content:attr(data-r);display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
 tr.vermelho td:first-child,tr.amarelo td:first-child,tr.verde td:first-child{box-shadow:none}
 tr.vermelho{box-shadow:inset 4px 0 0 var(--vm)}tr.amarelo{box-shadow:inset 4px 0 0 #e0a100}tr.verde{box-shadow:inset 4px 0 0 var(--vd)}
 .mini .opc{display:none}
 table.itens td[data-r="Semáforo"],table.itens td[data-r="Item"],table.itens td[data-r="Linha"]{display:inline-block;padding-right:0}
 table.itens td[data-r="Semáforo"]:before,table.itens td[data-r="Item"]:before,table.itens td[data-r="Linha"]:before{display:none}
 table.itens td[data-r="Item"]:after{content:"º item";color:var(--muted)}
 table.itens td[data-r="Linha"]:after{content:"ª linha";color:var(--muted)}
 .mini th,.mini td{padding:6px 5px}
}
@media print{.barra{display:none}details.nota{break-inside:avoid}}
"""

JS = """
(function(){
 var filtro='olhar', busca='';
 var bts=document.querySelectorAll('.barra button');
 var inp=document.getElementById('busca');
 function aplica(){
  var vis=0;
  document.querySelectorAll('tr[data-n]').forEach(function(tr){
   var nv=tr.getAttribute('data-n');
   var ok=(filtro==='tudo')||(filtro==='olhar'&&nv!=='verde')||(filtro===nv);
   if(ok&&busca){ok=tr.textContent.toLowerCase().indexOf(busca)>=0||(tr.closest('details').querySelector('summary').textContent.toLowerCase().indexOf(busca)>=0);}
   tr.classList.toggle('oculto',!ok); if(ok)vis++;
  });
  document.querySelectorAll('details.nota').forEach(function(d){
   var n=d.querySelectorAll('tr[data-n]:not(.oculto)').length; d.classList.toggle('oculto',n===0);
  });
  document.querySelectorAll('section.grupo').forEach(function(s){
   s.classList.toggle('oculto',s.querySelectorAll('details.nota:not(.oculto)').length===0);
  });
  document.getElementById('cont').textContent=vis+' itens na tela';
 }
 bts.forEach(function(b){b.addEventListener('click',function(){
  filtro=b.getAttribute('data-f'); bts.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');}); aplica();});});
 inp.addEventListener('input',function(){busca=inp.value.trim().toLowerCase(); aplica();});
 aplica();
})();
"""


def _chips(r) -> str:
    out = []
    if r.get("nota_cancelada"):
        out.append('<span class="chip cx">cancelada</span>')
    for k, cls in (("vermelho", "vm"), ("amarelo", "am"), ("verde", "vd")):
        v = int(r[k])
        if v:
            out.append(f'<span class="chip {cls}">{v} {ROTULO[k].lower()}</span>')
    return "".join(out)


def _celula_ncm(codigo: str, curta: str, completa: str = "") -> str:
    return (
        f'<div class="cod">{e(R.fmt_ncm(codigo))}</div>'
        f'<div class="of" title="{e(completa or curta)}">{e(curta or "fora da tabela oficial")}</div>'
    )


def _linha_item(it: pd.Series) -> str:
    sem = it["semaforo"]
    sug = []
    if it["ncm_sugerido"]:
        conf = f" · {it['confianca_modelo']:.0%}" if pd.notna(it["confianca_modelo"]) and it["ncm_sugerido"] else ""
        sug.append(
            f'<div><span class="sug cod">NCM {e(R.fmt_ncm(it["ncm_sugerido"]))}</span>{e(conf)}</div>'
            f'<div class="of" title="{e(it["ncm_sugerido_descricao"])}">{e(it["ncm_sugerido_curta"])}</div>'
        )
    if it["cfop_sugerido"]:
        sug.append(f'<div><span class="sug cod">CFOP {e(it["cfop_sugerido"])}</span></div>')
    motivo = it["motivo"] or ("Nada encontrado." if sem == "verde" else "")
    partes_motivo = [f'<div class="motivo">{e(m)}</div>' for m in motivo.split(" | ") if m]
    if it["o_que_fazer"] and sem != "verde":
        partes_motivo.append(f'<div class="acao">{e(it["o_que_fazer"])}</div>')
    if it["aceitas_escritorio"]:
        partes_motivo.append(
            f'<div class="aceito">Aceito pela regra do escritório ({e(it["aceitas_escritorio"])}).</div>'
        )
    gt = f'<div class="of">GTIN {e(it["gtin"])}</div>' if it["gtin"] else ""
    return (
        f'<tr class="{sem}" data-n="{sem}">'
        f'<td data-r="Semáforo"><span class="semaforo"><span class="dot {sem}"></span>{ROTULO[sem]}</span></td>'
        f'<td data-r="Item">{int(it["n_item"])}</td>'
        f'<td data-r="Produto"><div>{e(it["descricao"])}</div><div class="of">cód. {e(it["codigo"])}</div>{gt}</td>'
        f'<td data-r="NCM da nota">{_celula_ncm(it["ncm"], it["ncm_descricao_curta"], it["ncm_descricao_oficial"])}</td>'
        f'<td data-r="CFOP"><span class="cod">{e(it["cfop"])}</span><div class="of">{e(it["cst_csosn"] and "CST/CSOSN " + it["cst_csosn"])}</div></td>'
        f'<td data-r="Sugestão">{"".join(sug) or "<span class=of>sem sugestão</span>"}</td>'
        f'<td data-r="Motivo">{"".join(partes_motivo)}</td>'
        f"</tr>"
    )


def html_notas(res, origem: str, titulo: str = "Conferência das notas fiscais") -> str:
    s = res.resumo
    itens = res.itens
    corpo = []
    if not itens.empty:
        emp = res.empresas.sort_values(["vermelho", "amarelo"], ascending=False)
        for _, eg in emp.iterrows():
            g = eg["grupo"]
            notas_g = res.notas[res.notas["grupo"] == g]
            cab = (
                f'<div class="empresa"><h2>{e(eg["empresa"] or g)}</h2>'
                f'<span class="sub">{e(fmt_doc(eg["empresa_cnpj"]))} · pasta {e(g)} · {int(eg["notas"])} notas · '
                f"{int(eg['itens'])} itens</span></div>"
            )
            blocos = []
            for _, nt in notas_g.iterrows():
                its = itens[(itens["grupo"] == g) & (itens["chave"] == nt["chave"])].sort_values("n_item")
                pior = nt["semaforo"]
                aberto = " open" if pior != "verde" else ""
                rota = f"{e(nt['emitente'])} ({e(nt['emitente_uf'])}) → {e(nt['destinatario'] or 'consumidor')} ({e(nt['destinatario_uf'] or '-')})"
                linhas = "".join(_linha_item(it) for _, it in its.iterrows())
                blocos.append(
                    f'<details class="nota"{aberto}><summary><span class="dot {pior}"></span>'
                    f'<div><div class="titulo-nota">Nota {e(str(nt["numero"]))} <small>· série {e(str(nt["serie"]))} · '
                    f'{fmt_data(nt["data_emissao"])} · {e(nt["sentido"])}</small></div><div class="rota">{rota}</div></div>'
                    f'<div class="chips">{_chips(nt)}</div></summary>'
                    f'<table class="itens"><colgroup><col class="c-sem"><col class="c-it"><col class="c-prod"><col class="c-ncm">'
                    f'<col class="c-cfop"><col class="c-sug"><col></colgroup><thead><tr><th>Semáforo</th><th>Item</th><th>Produto</th><th>NCM da nota</th>'
                    f"<th>CFOP</th><th>Sugestão</th><th>Motivo e o que fazer</th></tr></thead><tbody>{linhas}</tbody></table>"
                    f"</details>"
                )
            corpo.append(f'<section class="grupo">{cab}{"".join(blocos)}</section>')

    regras_rows = (
        "".join(
            f'<tr><td>{e(v["nome"])}</td><td class="num c-vm">{v["vermelho"] or ""}</td>'
            f'<td class="num c-am">{v["amarelo"] or ""}</td><td class="num">{v["aceitos"] or ""}</td></tr>'
            for _, v in sorted(s["por_regra"].items(), key=lambda kv: (-kv[1]["vermelho"], -kv[1]["amarelo"]))
        )
        or '<tr><td colspan="4">Nenhum alerta.</td></tr>'
    )
    emp_rows = ""
    if not itens.empty:
        emp_rows = "".join(
            f'<tr><td>{e(r["empresa"] or r["grupo"])}<div class="of">{e(fmt_doc(r["empresa_cnpj"]))}</div></td>'
            f'<td class="num opc">{int(r["notas"])}</td><td class="num opc">{int(r["itens"])}</td>'
            f'<td class="num c-vm">{int(r["vermelho"]) or ""}</td><td class="num c-am">{int(r["amarelo"]) or ""}</td>'
            f'<td class="num c-vd">{int(r["verde"])}</td></tr>'
            for _, r in res.empresas.sort_values(["vermelho", "amarelo"], ascending=False).iterrows()
        )
    avisos = ""
    if res.avisos:
        avisos = (
            '<div class="avisos"><b>Arquivos que não entraram na conferência:</b><ul>'
            + "".join(f"<li>{e(a)}</li>" for a in res.avisos[:200])
            + "</ul></div>"
        )
    modelo = (
        f"Modelo: {e(s['modelo'])}; vermelho com confiança de {s['limiar_vermelho']:.0%} ou mais, "
        f"amarelo de {s['limiar_amarelo']:.0%} quando o NCM da nota nem aparece entre os 5 mais prováveis."
        if s["modelo"]
        else "Modelo de NCM não carregado (pasta models/ vazia): a checagem NCM x descrição ficou de fora."
    )
    n = max(s["itens"], 1)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Raio-X Fiscal: relatório</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><div><div class="marca">Raio-X Fiscal</div><h1>{e(titulo)}</h1>
<p class="meta"><b>{s["notas"]} notas</b> · <b>{s["itens"]} itens</b> · origem: {e(origem)} · gerado em {e(s["gerado_em"])}</p>
<p class="meta">Tabela NCM oficial {e(s["tabela_ncm"])}. Regras do escritório: {s["regras_escritorio"]}.</p></div>
<div class="selo">Feito na própria máquina: nenhuma nota saiu daqui. O Raio-X aponta; quem decide é a pessoa.</div></header>
<div class="kpis">
<div class="kpi vm"><div class="n">{s["vermelho"]}</div><div class="l">Erro provável ({s["vermelho"] / n:.0%} dos itens)</div></div>
<div class="kpi am"><div class="n">{s["amarelo"]}</div><div class="l">Conferir ({s["amarelo"] / n:.0%})</div></div>
<div class="kpi vd"><div class="n">{s["verde"]}</div><div class="l">Ok ({s["verde"] / n:.0%})</div></div>
<div class="kpi esc"><div class="n">{s["aceitos_escritorio"]}</div><div class="l">Alertas aceitos pela regra do escritório</div></div>
</div>
<div class="grid2">
<div class="box"><h2>O que mais apareceu</h2><table class="mini"><thead><tr><th>Checagem</th><th class="num">Vermelho</th><th class="num">Amarelo</th><th class="num">Aceitos</th></tr></thead><tbody>{regras_rows}</tbody></table></div>
<div class="box"><h2>Por empresa</h2><table class="mini"><thead><tr><th>Empresa</th><th class="num opc">Notas</th><th class="num opc">Itens</th><th class="num">Vermelho</th><th class="num">Amarelo</th><th class="num">Ok</th></tr></thead><tbody>{emp_rows}</tbody></table></div>
</div>
<div class="barra" role="toolbar" aria-label="Filtro">
<button data-f="olhar" aria-pressed="true">Só o que precisa olhar</button><button data-f="vermelho" aria-pressed="false">Vermelho</button>
<button data-f="amarelo" aria-pressed="false">Amarelo</button><button data-f="tudo" aria-pressed="false">Tudo</button>
<input id="busca" type="search" placeholder="Buscar produto, NCM, CFOP ou nota" aria-label="Buscar"><span class="cont" id="cont"></span></div>
{"".join(corpo) or "<p>Nenhuma nota encontrada.</p>"}
{avisos}
<div class="ajuda">
<div class="box"><h2><span class="dot vermelho"></span> Vermelho: erro provável</h2><p>Regra objetiva (NCM que não existe, CST de outro regime) ou o modelo com confiança muito alta de que o NCM não combina com a descrição. Na inspeção do dado público, 50 de 60 alertas desse tipo eram erro de verdade.</p></div>
<div class="box"><h2><span class="dot amarelo"></span> Amarelo: conferir</h2><p>Pode ser erro, pode ser de propósito: CFOP de dentro do estado numa venda para fora, código antigo, mesmo produto com dois NCMs. Se for de propósito, vira regra do escritório e para de aparecer.</p></div>
<div class="box"><h2><span class="dot verde"></span> Verde: ok</h2><p>Nenhuma checagem encontrou problema. {e(modelo)}</p></div>
</div>
<footer>Raio-X Fiscal · github.com/Bueno-00/raio-x-fiscal · As sugestões de NCM vêm de um modelo treinado em notas públicas e da tabela oficial do Siscomex; confira antes de alterar o cadastro.</footer>
</div><script>{JS}</script></body></html>"""


# ---------------------------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------------------------


def _estilo_planilha(ws, df: pd.DataFrame, col_semaforo: str | None, larguras: dict[str, int] | None = None):
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cab = PatternFill("solid", fgColor="1F4E79")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = cab
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    cols = list(df.columns)
    for i, nome in enumerate(cols, start=1):
        larg = (larguras or {}).get(nome)
        if larg is None:
            amostra = [len(str(nome))] + [len(str(v)) for v in df[nome].head(200)]
            larg = min(max(amostra) + 2, 60)
        ws.column_dimensions[get_column_letter(i)].width = max(larg, 8)
    if col_semaforo and col_semaforo in cols:
        j = cols.index(col_semaforo) + 1
        for row in range(2, ws.max_row + 1):
            c = ws.cell(row=row, column=j)
            v = str(c.value or "")
            if v in FUNDOS:
                c.fill = PatternFill("solid", fgColor=FUNDOS[v].lstrip("#"))
                c.font = Font(bold=True, color=CORES[v].lstrip("#"))
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=isinstance(c.value, str) and len(c.value) > 40)


def xlsx_notas(res, destino: Path) -> Path:
    from openpyxl import Workbook

    destino = Path(destino)
    s = res.resumo
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"
    linhas = [
        ["Raio-X Fiscal: conferência das notas"],
        ["Gerado em", s["gerado_em"]],
        ["Tabela NCM oficial", s["tabela_ncm"]],
        ["Modelo", s["modelo"] or "não carregado"],
        [],
        ["Notas", s["notas"]],
        ["Itens", s["itens"]],
        ["Vermelho (erro provável)", s["vermelho"]],
        ["Amarelo (conferir)", s["amarelo"]],
        ["Verde (ok)", s["verde"]],
        ["Aceitos pela regra do escritório", s["aceitos_escritorio"]],
        [],
        ["Checagem", "Vermelho", "Amarelo", "Aceitos"],
    ]
    for _, v in sorted(s["por_regra"].items(), key=lambda kv: (-kv[1]["vermelho"], -kv[1]["amarelo"])):
        linhas.append([v["nome"], v["vermelho"], v["amarelo"], v["aceitos"]])
    for ln in linhas:
        ws.append(ln)
    from openpyxl.styles import Font

    ws["A1"].font = Font(bold=True, size=14, color="1F4E79")
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 48

    if not res.itens.empty:
        cols = [c for c in COLUNAS_XLSX if c in res.itens.columns]
        df = res.itens.copy()
        df["ordem"] = df["semaforo"].map(ORDEM)
        df = df.sort_values(["ordem", "grupo", "numero", "n_item"])[cols]
        df["data_emissao"] = df["data_emissao"].map(fmt_data)
        df = df.rename(columns=COLUNAS_XLSX)
        wi = wb.create_sheet("Itens")
        wi.append(list(df.columns))
        for row in df.itertuples(index=False):
            wi.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in row])
        _estilo_planilha(wi, df, "Semáforo", {"Motivo": 70, "O que fazer": 50, "Descrição": 40})

        nt = res.notas.copy()
        nt["data_emissao"] = nt["data_emissao"].map(fmt_data)
        nt = nt.rename(
            columns={
                "grupo": "Pasta / empresa",
                "chave": "Chave de acesso",
                "numero": "Nota",
                "serie": "Série",
                "data_emissao": "Emissão",
                "emitente": "Emitente",
                "emitente_uf": "UF emitente",
                "destinatario": "Destinatário",
                "destinatario_uf": "UF destinatário",
                "sentido": "Sentido",
                "nota_cancelada": "Cancelada",
                "itens": "Itens",
                "vermelho": "Vermelho",
                "amarelo": "Amarelo",
                "verde": "Verde",
                "valor_itens": "Valor dos itens (R$)",
                "semaforo": "Semáforo",
            }  # fmt: skip
        )
        wn = wb.create_sheet("Notas")
        wn.append(list(nt.columns))
        for row in nt.itertuples(index=False):
            wn.append(list(row))
        _estilo_planilha(wn, nt, "Semáforo")

    if res.correcoes is not None and not res.correcoes.empty:
        cc = res.correcoes.copy()
        cc["ncm_aprovado"] = cc["ncm_atual"].map(lambda v: v.split(",")[0].strip())
        cc = cc.rename(
            columns={
                "grupo": "Pasta / empresa",
                "emitente_cnpj": "CNPJ emitente",
                "emitente": "Emitente",
                "codigo": "Código do produto",
                "gtin": "GTIN/EAN",
                "descricao": "Descrição",
                "ncm_atual": "NCM atual",
                "ncm_sugerido": "NCM sugerido",
                "ncm_sugerido_descricao": "Descrição oficial do NCM sugerido",
                "semaforo": "Semáforo",
                "motivo": "Motivo",
                "notas": "Notas com o produto",
                "ncm_aprovado": "NCM aprovado (preencha)",
            }  # fmt: skip
        )
        wc = wb.create_sheet("Correção de cadastro")
        wc.append(list(cc.columns))
        for row in cc.itertuples(index=False):
            wc.append(list(row))
        _estilo_planilha(wc, cc, "Semáforo", {"Motivo": 70, "Descrição oficial do NCM sugerido": 50})

    wr = wb.create_sheet("Regra do escritório")
    for ln in R.MODELO_CSV_EXCECOES.splitlines():
        if ln.startswith("#"):
            wr.append([ln.lstrip("# ")])
        else:
            wr.append(ln.split(";"))
    wr.column_dimensions["A"].width = 18
    wr.column_dimensions["F"].width = 60
    wb.save(destino)
    return destino


def html_cadastro(df: pd.DataFrame, resumo: dict, origem: str) -> str:
    """Relatório da porta 2 (planilha de cadastro), no mesmo visual do relatório das notas."""
    cols = resumo["colunas"]
    linhas = []
    for _, r in df.iterrows():
        sem = r["semaforo"]
        sug = ""
        if r["ncm_sugerido"]:
            conf = f" · {r['confianca_modelo']:.0%}" if pd.notna(r["confianca_modelo"]) else ""
            sug = (
                f'<div><span class="sug cod">NCM {e(R.fmt_ncm(r["ncm_sugerido"]))}</span>{e(conf)}</div>'
                f'<div class="of" title="{e(r["ncm_sugerido_descricao"])}">{e(r["ncm_sugerido_curta"])}</div>'
            )
        motivo = "".join(f'<div class="motivo">{e(m)}</div>' for m in str(r["motivo"]).split(" | ") if m)
        if sem != "verde" and r["o_que_fazer"]:
            motivo += f'<div class="acao">{e(r["o_que_fazer"])}</div>'
        linhas.append(
            f'<tr class="{sem}" data-n="{sem}"><td data-r="Semáforo"><span class="semaforo"><span class="dot {sem}"></span>{ROTULO[sem]}</span></td>'
            f'<td data-r="Linha">{int(r["linha_planilha"])}</td>'
            f'<td data-r="Produto"><div>{e(str(r[cols["descricao"]]))}</div><div class="of">cód. {e(str(r[cols["codigo"]]) if "codigo" in cols else "")}</div></td>'
            f'<td data-r="NCM no cadastro">{_celula_ncm(r["ncm_atual"], r["ncm_atual_curta"], r["ncm_atual_descricao"])}</td>'
            f'<td data-r="Sugestão">{sug or "<span class=of>sem sugestão</span>"}</td>'
            f'<td data-r="Motivo">{motivo or "<div class=motivo>Nada encontrado.</div>"}</td></tr>'
        )
    n = max(resumo["produtos"], 1)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Raio-X Fiscal: cadastro</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><div><div class="marca">Raio-X Fiscal</div><h1>Conferência do cadastro de produtos</h1>
<p class="meta"><b>{resumo["produtos"]} produtos</b> · origem: {e(origem)} · tabela NCM {e(resumo["tabela_ncm"])}</p>
<p class="meta">Colunas usadas: {e(", ".join(f"{k} = {v}" for k, v in cols.items()))}</p></div>
<div class="selo">Confere o NCM antes de emitir. A planilha de correção tem a coluna "NCM aprovado" para você revisar.</div></header>
<div class="kpis">
<div class="kpi vm"><div class="n">{resumo["vermelho"]}</div><div class="l">Erro provável ({resumo["vermelho"] / n:.0%})</div></div>
<div class="kpi am"><div class="n">{resumo["amarelo"]}</div><div class="l">Conferir ({resumo["amarelo"] / n:.0%})</div></div>
<div class="kpi vd"><div class="n">{resumo["verde"]}</div><div class="l">Ok ({resumo["verde"] / n:.0%})</div></div>
<div class="kpi esc"><div class="n">{resumo["produtos"]}</div><div class="l">Produtos na planilha</div></div></div>
<div class="barra" role="toolbar" aria-label="Filtro">
<button data-f="olhar" aria-pressed="true">Só o que precisa olhar</button><button data-f="vermelho" aria-pressed="false">Vermelho</button>
<button data-f="amarelo" aria-pressed="false">Amarelo</button><button data-f="tudo" aria-pressed="false">Tudo</button>
<input id="busca" type="search" placeholder="Buscar produto ou NCM" aria-label="Buscar"><span class="cont" id="cont"></span></div>
<section class="grupo"><details class="nota" open><summary><span class="dot {"vermelho" if resumo["vermelho"] else ("amarelo" if resumo["amarelo"] else "verde")}"></span><div><div class="titulo-nota">Produtos</div></div><div></div></summary>
<table class="itens"><colgroup><col class="c-sem"><col class="c-it"><col class="c-prod"><col class="c-ncm"><col class="c-sug"><col></colgroup><thead><tr><th>Semáforo</th><th>Linha</th><th>Produto</th><th>NCM no cadastro</th><th>Sugestão</th><th>Motivo e o que fazer</th></tr></thead>
<tbody>{"".join(linhas)}</tbody></table></details></section>
<footer>Raio-X Fiscal · github.com/Bueno-00/raio-x-fiscal · Nada é alterado sozinho: você aprova o NCM na planilha e só então exporta para importar no sistema.</footer>
</div><script>{JS}</script></body></html>"""


def xlsx_cadastro(df: pd.DataFrame, resumo: dict, destino: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Correção"
    out = df.drop(columns=["nivel"])
    ws.append(list(out.columns))
    for row in out.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in row])
    _estilo_planilha(ws, out, "semaforo", {"motivo": 70, "o_que_fazer": 50})
    wr = wb.create_sheet("Como usar")
    for ln in [
        ["1. Olhe primeiro as linhas vermelhas, depois as amarelas."],
        ["2. Onde concordar com a sugestão, troque a coluna ncm_aprovado pelo NCM sugerido."],
        ["3. Salve e rode: rxf cadastro-exportar <esta planilha> --saida para-importar.csv"],
        ["4. O arquivo gerado tem o layout da planilha original e só as linhas que mudaram."],
        [f"Tabela NCM: {resumo['tabela_ncm']}"],
        [json.dumps(resumo["colunas"], ensure_ascii=False)],
    ]:
        wr.append(ln)
    wr.column_dimensions["A"].width = 100
    wb.save(destino)
    return Path(destino)
