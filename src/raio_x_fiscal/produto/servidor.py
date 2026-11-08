"""Página local do Raio-X (opcional): as 3 portas numa tela, só em 127.0.0.1.

    rxf painel            # abre em http://127.0.0.1:8765 e para com Ctrl+C

- escuta SÓ em 127.0.0.1 (não aceita outro endereço): ninguém de fora da máquina acessa;
- os arquivos enviados ficam em `saida-local/painel/<data-hora>/` (fora do git) e não saem dali;
- nada de chave de API, nada de serviço externo: o modelo roda no próprio processo.

No servidor (VPS), para ver no seu computador, use um túnel SSH:
    ssh -L 8765:127.0.0.1:8765 usuario@servidor   e abra http://127.0.0.1:8765
"""

from __future__ import annotations

import email.parser
import email.policy
import json
import logging
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

from raio_x_fiscal.produto import cadastro as CAD
from raio_x_fiscal.produto import motor, relatorio
from raio_x_fiscal.produto.nfe import ler_entrada

log = logging.getLogger(__name__)
HOST = "127.0.0.1"
MAX_UPLOAD = 300 * 1024 * 1024
_NOME_OK = re.compile(r"[^A-Za-z0-9._ -]+")


def _seguro(rel: str) -> PurePosixPath | None:
    """Caminho relativo enviado pelo navegador -> caminho limpo dentro da pasta (sem '..')."""
    partes = [_NOME_OK.sub("_", p).strip() for p in PurePosixPath(rel.replace("\\", "/")).parts]
    partes = [p for p in partes if p and p not in (".", "..")]
    return PurePosixPath(*partes) if partes else None


def _multipart(content_type: str, corpo: bytes) -> list[tuple[str, str, bytes]]:
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + corpo
    )
    out = []
    for parte in msg.iter_parts():
        nome = parte.get_param("name", header="content-disposition") or ""
        arq = parte.get_filename() or ""
        out.append((nome, arq, parte.get_payload(decode=True) or b""))
    return out


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raio-X Fiscal: painel local</title><style>
:root{--text:#1a1a1a;--muted:#5f5f5f;--line:#d9d9d9;--accent:#1F4E79;--bg:#f5f6f7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",system-ui,sans-serif;font-size:14px}
.wrap{max-width:1360px;margin:0 auto;padding:24px 32px}
header{border-bottom:2px solid var(--accent);padding-bottom:12px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.marca{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}h1{margin:2px 0 0;font-size:24px}
.local{font-size:12px;color:var(--muted)}
.abas{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}.abas button{font:inherit;border:1px solid var(--line);background:#fff;border-radius:999px;padding:8px 16px;cursor:pointer}
.abas button[aria-selected=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.painel{background:#fff;border:1px solid var(--line);border-radius:10px;padding:18px}
.zona{border:2px dashed var(--line);border-radius:10px;padding:28px;text-align:center;color:var(--muted)}.zona.sobre{border-color:var(--accent);background:#f3f7fb}
.linha{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.btn{text-decoration:none;display:inline-block;font:inherit;border:0;background:var(--accent);color:#fff;border-radius:8px;padding:9px 16px;cursor:pointer}.btn.sec{background:#fff;color:var(--accent);border:1px solid var(--accent)}
input[type=text]{font:inherit;border:1px solid var(--line);border-radius:8px;padding:9px 12px;min-width:320px;flex:1}
.res{margin-top:14px}.res iframe{width:100%;height:78vh;border:1px solid var(--line);border-radius:10px;background:#fff}
.ncm{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-top:10px;display:grid;grid-template-columns:130px 1fr 120px;gap:12px;align-items:center}
.ncm .c{font-family:ui-monospace,Consolas,monospace;font-weight:700;color:var(--accent)}.barra{height:8px;background:#eee;border-radius:9px;overflow:hidden}.barra i{display:block;height:100%;background:var(--accent)}
.of{color:var(--muted);font-size:13px}.oculto{display:none}
@media(max-width:800px){.wrap{padding:16px}.ncm{grid-template-columns:1fr}input[type=text]{min-width:0}}
</style></head><body><div class="wrap">
<header><div><div class="marca">Raio-X Fiscal</div><h1>Painel local</h1></div><div class="local">Rodando só nesta máquina (127.0.0.1). Os arquivos não saem daqui.</div></header>
<div class="abas" role="tablist"><button role="tab" aria-selected="true" data-a="notas">1. Notas (XML)</button><button role="tab" aria-selected="false" data-a="cadastro">2. Cadastro (planilha)</button><button role="tab" aria-selected="false" data-a="pesquisa">3. Pesquisar produto</button></div>
<section class="painel" id="notas"><div class="zona" id="zona">Arraste aqui um .zip, uma pasta ou os XML das notas<br><span class="of">uma subpasta por empresa vira um grupo no relatório</span></div>
<div class="linha"><label class="btn sec">Escolher arquivos<input type="file" id="arqs" multiple accept=".xml,.zip" class="oculto"></label>
<label class="btn sec">Escolher pasta<input type="file" id="pasta" webkitdirectory multiple class="oculto"></label>
<button class="btn" id="ir">Conferir</button><span class="of" id="sel">nenhum arquivo</span></div><div class="res" id="r1"></div></section>
<section class="painel oculto" id="cadastro"><p>Planilha exportada do sistema (CSV ou XLSX), por exemplo <b>Bling: Cadastros &gt; Produtos &gt; Mais ações &gt; Planilhas &gt; Exportar dados para planilha</b>.</p>
<div class="linha"><input type="file" id="plan" accept=".csv,.xlsx"><button class="btn" id="ir2">Conferir cadastro</button></div><div class="res" id="r2"></div></section>
<section class="painel oculto" id="pesquisa"><div class="linha"><input type="text" id="q" placeholder="Ex.: leite condensado 395 g"><button class="btn" id="ir3">Pesquisar</button></div><div class="res" id="r3"></div></section>
</div><script>
var arquivos=[];
document.querySelectorAll('.abas button').forEach(function(b){b.onclick=function(){document.querySelectorAll('.abas button').forEach(function(x){x.setAttribute('aria-selected',x===b)});
['notas','cadastro','pesquisa'].forEach(function(id){document.getElementById(id).classList.toggle('oculto',id!==b.dataset.a)})}});
function mostra(){document.getElementById('sel').textContent=arquivos.length+' arquivo(s)'}
document.getElementById('arqs').onchange=function(e){arquivos=Array.from(e.target.files).map(function(f){return[f,f.name]});mostra()};
document.getElementById('pasta').onchange=function(e){arquivos=Array.from(e.target.files).map(function(f){return[f,f.webkitRelativePath||f.name]});mostra()};
function le(entry,cam,lista){return new Promise(function(ok){if(entry.isFile){entry.file(function(f){lista.push([f,cam+f.name]);ok()})}else{var r=entry.createReader(),tudo=[];
(function prox(){r.readEntries(function(es){if(!es.length){Promise.all(tudo.map(function(x){return le(x,cam+entry.name+'/',lista)})).then(ok)}else{tudo=tudo.concat(Array.from(es));prox()}})})()}})}
var z=document.getElementById('zona');z.ondragover=function(e){e.preventDefault();z.classList.add('sobre')};z.ondragleave=function(){z.classList.remove('sobre')};
z.ondrop=function(e){e.preventDefault();z.classList.remove('sobre');var lista=[];var ps=[];Array.from(e.dataTransfer.items).forEach(function(it){var en=it.webkitGetAsEntry&&it.webkitGetAsEntry();if(en)ps.push(le(en,'',lista))});
Promise.all(ps).then(function(){arquivos=lista;mostra()})};
function envia(url,fd,alvo){alvo.innerHTML='<p class=of>Conferindo...</p>';fetch(url,{method:'POST',body:fd}).then(function(r){return r.json()}).then(function(j){
if(j.erro){alvo.innerHTML='<p>'+j.erro.replace(/</g,'&lt;')+'</p>';return}
alvo.innerHTML='<div class=linha><a class=btn href="'+j.xlsx+'">Baixar planilha (XLSX)</a><a class="btn sec" href="'+j.html+'" target=_blank>Abrir relatório em outra aba</a><span class=of>'+j.texto+'</span></div><iframe src="'+j.html+'" title="Relatório"></iframe>'})}
document.getElementById('ir').onclick=function(){if(!arquivos.length){alert('Escolha os arquivos');return}var fd=new FormData();arquivos.forEach(function(a){fd.append('f',a[0],a[1])});envia('/api/notas',fd,document.getElementById('r1'))};
document.getElementById('ir2').onclick=function(){var f=document.getElementById('plan').files[0];if(!f){alert('Escolha a planilha');return}var fd=new FormData();fd.append('f',f,f.name);envia('/api/cadastro',fd,document.getElementById('r2'))};
function pesq(){var q=document.getElementById('q').value.trim();if(!q)return;var a=document.getElementById('r3');a.innerHTML='<p class=of>Pesquisando...</p>';
fetch('/api/pesquisar?q='+encodeURIComponent(q)).then(function(r){return r.json()}).then(function(j){if(j.erro){a.textContent=j.erro;return}
a.innerHTML=j.resultados.map(function(x){var d=document.createElement('div');d.textContent=x.descricao_oficial;return '<div class=ncm><div class=c>'+x.ncm_formatado+'</div><div>'+d.innerHTML+'</div><div><div class=barra><i style="width:'+Math.round(x.confianca*100)+'%"></i></div><span class=of>'+(x.confianca<0.005?'menos de 1':Math.round(x.confianca*100))+'% de confiança</span></div></div>'}).join('')||'<p>Nada encontrado.</p>'})}
document.getElementById('ir3').onclick=pesq;document.getElementById('q').onkeydown=function(e){if(e.key==='Enter')pesq()};
</script></body></html>"""


def criar_servidor(ctx: motor.Contexto, base: Path, porta: int = 8765) -> ThreadingHTTPServer:
    base = Path(base).resolve()
    base.mkdir(parents=True, exist_ok=True)
    trava = threading.Lock()

    class H(BaseHTTPRequestHandler):
        server_version = "RaioX/0.2"

        def log_message(self, fmt, *args):  # sem log de conteúdo; só a rota
            log.info("%s %s", self.command, self.path.split("?")[0])

        def _json(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _arquivo(self, p: Path, tipo: str):
            b = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(b)))
            if tipo.startswith("application/vnd"):
                self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                b = PAGINA.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            if u.path == "/api/pesquisar":
                q = (parse_qs(u.query).get("q") or [""])[0][:200]
                try:
                    self._json({"resultados": motor.pesquisar(q, ctx, k=3)})
                except RuntimeError as ex:
                    self._json({"erro": str(ex)}, 400)
                return
            m = re.fullmatch(r"/r/([0-9_-]+)/(relatorio\.html|relatorio\.xlsx)", u.path)
            if m:
                p = base / m.group(1) / m.group(2)
                if p.exists():
                    tipo = (
                        "text/html; charset=utf-8"
                        if p.suffix == ".html"
                        else ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    )
                    self._arquivo(p, tipo)
                    return
            self.send_error(404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_UPLOAD:
                self._json({"erro": "envio vazio ou maior que 300 MB"}, 413)
                return
            partes = _multipart(self.headers.get("Content-Type", ""), self.rfile.read(n))
            rid = datetime.now().strftime("%Y%m%d_%H%M%S_") + f"{int(time.time() * 1000) % 1000:03d}"
            pasta = base / rid
            entrada = pasta / "entrada"
            entrada.mkdir(parents=True, exist_ok=True)
            salvos = []
            for _, nome, dados in partes:
                rel = _seguro(nome)
                if rel is None:
                    continue
                destino = entrada / rel
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(dados)
                salvos.append(destino)
            if not salvos:
                self._json({"erro": "nenhum arquivo recebido"}, 400)
                return
            try:
                with trava:
                    if self.path == "/api/notas":
                        res = motor.auditar_notas(ler_entrada(entrada), ctx)
                        (pasta / "relatorio.html").write_text(relatorio.html_notas(res, "arquivos enviados ao painel"))
                        relatorio.xlsx_notas(res, pasta / "relatorio.xlsx")
                        s = res.resumo
                        texto = (
                            f"{s['notas']} notas, {s['itens']} itens: {s['vermelho']} vermelho, {s['amarelo']} amarelo"
                        )
                    elif self.path == "/api/cadastro":
                        df, _ = CAD.ler_planilha(salvos[0])
                        out, s = CAD.auditar_cadastro(df, ctx)
                        (pasta / "relatorio.html").write_text(relatorio.html_cadastro(out, s, salvos[0].name))
                        relatorio.xlsx_cadastro(out, s, pasta / "relatorio.xlsx")
                        texto = f"{s['produtos']} produtos: {s['vermelho']} vermelho, {s['amarelo']} amarelo"
                    else:
                        self.send_error(404)
                        return
            except Exception as ex:  # noqa: BLE001 - devolve o erro na tela, sem derrubar o painel
                log.exception("falha ao conferir")
                self._json({"erro": f"não consegui conferir: {ex}"}, 400)
                return
            self._json({"html": f"/r/{rid}/relatorio.html", "xlsx": f"/r/{rid}/relatorio.xlsx", "texto": texto})

    return ThreadingHTTPServer((HOST, porta), H)
