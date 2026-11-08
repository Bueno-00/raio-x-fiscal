"""App web do Raio-X Fiscal: as 3 portas numa página, pronta para publicar atrás do Nginx.

    rxf app                    # http://127.0.0.1:8770 (só nesta máquina; o Nginx publica)

Privacidade e abuso (quem visita manda nota de verdade):
- o arquivo enviado é lido na MEMÓRIA, conferido e descartado: nada vai para o disco (o corpo do
  envio é lido aqui mesmo, sem o "spool" em arquivo temporário do servidor) e nada vai para o log
  (sem log de acesso; o log do app só registra contagens);
- o resultado fica na memória por 30 minutos, só para você baixar a planilha; depois some;
- limites: tamanho do envio, número de arquivos, itens por envio, envios por IP por hora e por dia,
  e uma conferência por vez (o servidor é pequeno);
- cabeçalhos de segurança (CSP sem nada de fora, sem iframe, sem referrer).

O chat "Pergunte ao Simples" (projeto à parte) só entra se o pacote `pergunte_ao_simples` estiver
instalado E a variável CHAT_ENV_FILE apontar para um arquivo que existe. O app não lê esse arquivo.
"""

from __future__ import annotations

import email.parser
import email.policy
import importlib.util
import io
import logging
import os
import re
import secrets
import threading
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from raio_x_fiscal.produto import cadastro as CAD
from raio_x_fiscal.produto import exemplos_lojas as EL
from raio_x_fiscal.produto import formatos as FMT
from raio_x_fiscal.produto import motor, relatorio
from raio_x_fiscal.produto import regras as R
from raio_x_fiscal.produto.nfe import ler_memoria

log = logging.getLogger("raio_x_fiscal.app")
STATIC = Path(__file__).resolve().parent / "static"
HOST = "127.0.0.1"
PORTA = 8770

MAX_ENVIO = 25 * 1024 * 1024  # 25 MB por envio (o Nginx corta no mesmo valor)
MAX_ARQUIVOS = 3_000  # XML por envio (contando os de dentro do .zip)
MAX_ITENS = 30_000  # itens de nota por envio
MAX_PLANILHA = 5 * 1024 * 1024
MAX_PRODUTOS = 5_000
MAX_VERDES_NA_TELA = 3_000  # os vermelhos e amarelos vão todos; os verdes, até aqui (a planilha leva todos)
TTL = 30 * 60
MAX_GUARDADOS = 40

LIMITES = {  # (quantos, em quantos segundos)
    "envio": [(12, 3600), (40, 86400)],
    "pesquisa": [(90, 3600), (400, 86400)],
    "exemplo": [(60, 3600)],
    "baixar": [(120, 3600)],
}


# ---------------------------------------------------------------------------------------------
# Limites por IP e guarda temporária (tudo na memória)
# ---------------------------------------------------------------------------------------------


class Limitador:
    def __init__(self, regras: dict[str, list[tuple[int, int]]]):
        self.regras = regras
        self.hist: dict[tuple[str, str], deque] = defaultdict(deque)
        self.trava = threading.Lock()

    def permitir(self, ip: str, tipo: str) -> int | None:
        """None se pode; senão, em quantos minutos tenta de novo."""
        agora = time.time()
        maior = max(s for _, s in self.regras[tipo])
        with self.trava:
            h = self.hist[(ip, tipo)]
            while h and agora - h[0] > maior:
                h.popleft()
            for qtd, seg in self.regras[tipo]:
                recentes = [t for t in h if agora - t <= seg]
                if len(recentes) >= qtd:
                    return max(1, int((seg - (agora - recentes[0])) / 60) + 1)
            h.append(agora)
            if len(self.hist) > 50_000:  # não deixa a memória crescer sem fim
                for k in list(self.hist)[:10_000]:
                    self.hist.pop(k, None)
        return None


@dataclass
class Guardado:
    tipo: str  # "notas" ou "cadastro"
    criado: float
    resultado: object = None  # motor.Resultado (notas)
    cadastro: pd.DataFrame | None = None  # planilha de correção (cadastro)
    original: pd.DataFrame | None = None
    info: dict = field(default_factory=dict)
    resumo: dict = field(default_factory=dict)
    nome: str = ""
    permanente: bool = False


class Guarda:
    def __init__(self):
        self.d: OrderedDict[str, Guardado] = OrderedDict()
        self.trava = threading.Lock()

    def por(self, g: Guardado, token: str | None = None) -> str:
        token = token or secrets.token_urlsafe(18)
        with self.trava:
            self._limpa()
            self.d[token] = g
            while len([k for k, v in self.d.items() if not v.permanente]) > MAX_GUARDADOS:
                for k, v in self.d.items():
                    if not v.permanente:
                        self.d.pop(k)
                        break
        return token

    def pegar(self, token: str) -> Guardado | None:
        with self.trava:
            self._limpa()
            return self.d.get(token)

    def _limpa(self):
        agora = time.time()
        for k in [k for k, v in self.d.items() if not v.permanente and agora - v.criado > TTL]:
            self.d.pop(k, None)


# ---------------------------------------------------------------------------------------------
# Leitura do envio sem tocar no disco
# ---------------------------------------------------------------------------------------------


async def ler_corpo(request: Request, limite: int) -> bytes:
    n = int(request.headers.get("content-length") or 0)
    if n > limite:
        raise HTTPException(413, f"Envio maior que {limite // (1024 * 1024)} MB.")
    partes, total = [], 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > limite:
            raise HTTPException(413, f"Envio maior que {limite // (1024 * 1024)} MB.")
        partes.append(pedaco)
    return b"".join(partes)


_NOME = re.compile(r"[^\w.\- /]+", re.UNICODE)


def arquivos_do_multipart(content_type: str, corpo: bytes) -> list[tuple[str, bytes]]:
    if "multipart/form-data" not in (content_type or ""):
        raise HTTPException(400, "Envie os arquivos pelo formulário da página.")
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + corpo
    )
    out = []
    for parte in msg.iter_parts():
        nome = parte.get_filename() or ""
        if not nome:
            continue
        nome = _NOME.sub("_", nome.replace("\\", "/"))[:300]
        partes = [p for p in nome.split("/") if p not in ("", ".", "..")]
        if partes:
            out.append(("/".join(partes), parte.get_payload(decode=True) or b""))
    return out


# ---------------------------------------------------------------------------------------------
# Resultado -> JSON da tela (sem a chave de acesso inteira nem CNPJ de destinatário pessoa física)
# ---------------------------------------------------------------------------------------------


def _txt(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def json_notas(res, origem: str) -> dict:
    itens = res.itens
    s = dict(res.resumo)
    s.pop("por_regra", None)
    por_regra = [
        {"regra": k, "nome": v["nome"], "vermelho": v["vermelho"], "amarelo": v["amarelo"], "aceitos": v["aceitos"]}
        for k, v in sorted(
            res.resumo.get("por_regra", {}).items(), key=lambda kv: (-kv[1]["vermelho"], -kv[1]["amarelo"])
        )
    ]
    empresas = []
    if not res.empresas.empty:
        for _, e in res.empresas.iterrows():
            empresas.append(
                {
                    "grupo": _txt(e["grupo"]),
                    "nome": _txt(e.get("empresa")) or _txt(e["grupo"]),
                    "cnpj": relatorio.fmt_doc(_txt(e["empresa_cnpj"])),
                    "notas": int(e["notas"]),
                    "itens": int(e["itens"]),
                    "vermelho": int(e["vermelho"]),
                    "amarelo": int(e["amarelo"]),
                    "verde": int(e["verde"]),
                }
            )
    lista = []
    if not itens.empty:
        # Dentro de cada cor, primeiro o que é mais fácil de entender e de conferir: o modelo com mais
        # certeza, depois as regras objetivas.
        prio = {"NCM_MODELO": 0, "NCM_AUSENTE": 1, "CST_REGIME": 2, "CFOP_SENTIDO": 3, "NCM_INEXISTENTE": 4,
                "CFOP_UF": 5, "PRODUTO_NCM_DIVERGENTE": 6, "CADASTRO_DIVERGENTE": 7, "GTIN_INVALIDO": 8}  # fmt: skip
        ordem = itens.assign(
            _p=itens["regras"].map(lambda r: min((prio.get(x, 9) for x in str(r).split(", ") if x), default=9)),
            _c=-itens["confianca_modelo"].fillna(0),
            # a 1ª vez de cada produto vem antes das repetições (o mesmo erro de cadastro em várias notas)
            _k=itens.groupby(["grupo", "codigo", "ncm"]).cumcount(),
        ).sort_values(
            ["nivel", "_k", "_p", "_c", "grupo", "numero", "n_item"],
            ascending=[False, True, True, True, True, True, True],
        )
        verdes = 0
        for idx, r in ordem.iterrows():
            if r["nivel"] == R.VERDE:
                verdes += 1
                if verdes > MAX_VERDES_NA_TELA:
                    continue
            lista.append(
                {
                    "id": int(idx),
                    "grupo": _txt(r["grupo"]),
                    "semaforo": r["semaforo"],
                    "sentido": _txt(r["sentido"]),
                    "modelo": "NFC-e" if r["modelo"] == "65" else "NF-e",
                    "numero": _txt(r["numero"]),
                    "data": relatorio.fmt_data(r["data_emissao"]),
                    "emitente": _txt(r["emitente"]),
                    "n_item": int(r["n_item"]),
                    "codigo": _txt(r["codigo"]),
                    "gtin": _txt(r["gtin"]),
                    "descricao": _txt(r["descricao"]),
                    "ncm": R.fmt_ncm(_txt(r["ncm"])),
                    "ncm_curta": _txt(r["ncm_descricao_curta"]),
                    "ncm_sugerido": R.fmt_ncm(_txt(r["ncm_sugerido"])) if r["ncm_sugerido"] else "",
                    "ncm_sugerido_curta": _txt(r["ncm_sugerido_curta"]),
                    "cfop": _txt(r["cfop"]),
                    "cfop_sugerido": _txt(r["cfop_sugerido"]),
                    "cst": _txt(r["cst_csosn"]),
                    "valor": float(r["valor_total"] or 0),
                    "confianca": None if pd.isna(r["confianca_modelo"]) else float(r["confianca_modelo"]),
                    "regras": [x for x in _txt(r["regras"]).split(", ") if x],
                    "aceito": _txt(r["aceitas_escritorio"]),
                    "motivo": _txt(r["motivo"]),
                    "o_que_fazer": _txt(r["o_que_fazer"]),
                }
            )
    return {
        "tipo": "notas",
        "origem": origem,
        "resumo": s,
        "por_regra": por_regra,
        "empresas": empresas,
        "itens": lista,
        "itens_omitidos": max(0, len(itens) - len(lista)),
        "avisos": res.avisos[:50],
        "nomes_regras": R.REGRAS,
    }


def json_cadastro(out: pd.DataFrame, s: dict, nome: str) -> dict:
    cols = s.get("colunas", {})
    lista = []
    for _, r in out.iterrows():
        lista.append(
            {
                "linha": int(r["linha_planilha"]) - 2,
                "linha_planilha": int(r["linha_planilha"]),
                "semaforo": r["semaforo"],
                "codigo": _txt(r.get(cols.get("codigo", ""), "")),
                "gtin": _txt(r.get(cols.get("gtin", ""), "")),
                "descricao": _txt(r.get(cols.get("descricao", ""), "")),
                "ncm": R.fmt_ncm(_txt(r["ncm_atual"])),
                "ncm_curta": _txt(r["ncm_atual_curta"]),
                "ncm_sugerido": R.fmt_ncm(_txt(r["ncm_sugerido"])) if r["ncm_sugerido"] else "",
                "ncm_sugerido_curta": _txt(r["ncm_sugerido_curta"]),
                "confianca": None if pd.isna(r["confianca_modelo"]) else float(r["confianca_modelo"]),
                "regras": [x for x in _txt(r["regras"]).split(", ") if x],
                "motivo": _txt(r["motivo"]),
                "o_que_fazer": _txt(r["o_que_fazer"]),
            }
        )
    tem_id = FMT.coluna_id([c for c in out.columns]) is not None
    return {
        "tipo": "cadastro",
        "origem": nome,
        "resumo": {k: v for k, v in s.items() if k != "colunas"},
        "colunas": cols,
        "tem_id": tem_id,
        "bling": CAD.eh_exportacao_bling([c for c in out.columns if c not in ("linha_planilha", "semaforo", "nivel")]),
        "itens": lista,
        "nomes_regras": R.REGRAS,
    }


def _conferencia_exemplo(res) -> dict:
    _, _, gab = EL.montar()
    c = EL.conferir(res, gab)
    return {
        "itens": c["itens"],
        "itens_com_erro": c["itens_com_erro"],
        "erros_plantados": c["erros_plantados"],
        "erros_pegos": c["erros_pegos"],
        "por_tipo": [{"tipo": k, **v} for k, v in c["por_tipo"].items()],
        "itens_limpos": c["itens_limpos"],
        "limpos_sem_alerta": c["limpos_sem_alerta"],
        "perdidos": [
            {"empresa": p["empresa"], "nota": p["nota"], "descricao": p["descricao"], "erro": p["o_que_e"]}
            for p in c["perdidos"][:20]
        ],
    }


# ---------------------------------------------------------------------------------------------
# Chat (projeto A), opcional
# ---------------------------------------------------------------------------------------------


def _widget_do_pacote() -> Path | None:
    spec = importlib.util.find_spec("pergunte_ao_simples")
    if spec is None:
        return None
    pastas = list(spec.submodule_search_locations or []) or ([str(Path(spec.origin).parent)] if spec.origin else [])
    for p in pastas:
        achados = sorted(Path(p).rglob("chat-simples.js"))
        if achados:
            return achados[0]
    return None


def montar_chat(app: FastAPI) -> dict:
    env = os.environ.get("CHAT_ENV_FILE", "")
    if not env or not Path(env).is_file():  # só confere se existe; nunca abre o arquivo
        return {"ativo": False}
    try:
        from pergunte_ao_simples import criar_router  # type: ignore[import-not-found]
    except ImportError:
        return {"ativo": False}
    try:
        app.include_router(criar_router(), prefix="/api/chat")
    except Exception:  # noqa: BLE001 - chat com defeito não derruba o Raio-X
        log.exception("chat: não consegui montar o router; o Raio-X segue sem o chat")
        return {"ativo": False}
    js = _widget_do_pacote()
    if js is not None:

        @app.get("/chat/chat-simples.js", include_in_schema=False)
        def _widget():
            return FileResponse(js, media_type="text/javascript")

        return {"ativo": True, "js": "/chat/chat-simples.js"}
    return {"ativo": True, "js": "/api/chat/chat-simples.js"}


# ---------------------------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------------------------


def criar_app(ctx: motor.Contexto | None = None, *, com_modelo: bool = True, com_chat: bool = True) -> FastAPI:
    from raio_x_fiscal.config import Paths

    if ctx is None:
        paths = Paths.from_env()
        ctx = motor.Contexto.padrao(paths.data, paths.models, com_modelo=com_modelo)
    app = FastAPI(title="Raio-X Fiscal", docs_url=None, redoc_url=None, openapi_url=None)
    lim = Limitador(LIMITES)
    guarda = Guarda()
    vez = threading.BoundedSemaphore(1)
    chat = montar_chat(app) if com_chat else {"ativo": False}
    extra = os.environ.get("RAIOX_CSP_EXTRA", "").strip()  # ex.: https://challenges.cloudflare.com (captcha do chat)
    csp = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; "
        f"script-src 'self' {extra}; connect-src 'self' {extra}; frame-src {extra or 'none'}; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
    )

    # Notas de exemplo: geradas e conferidas uma vez, na memória.
    ex_arquivos = EL.arquivos()
    ex_zip = EL.zip_bytes()
    lt = ler_memoria(list(ex_arquivos.items()))
    ctx_ex = motor.Contexto(
        historico=ctx.historico,
        classificador=ctx.classificador,
        escritorio=R.RegrasDoEscritorio.de_texto(lt.regras_texto, "exemplo"),
    )
    res_ex = motor.auditar_notas(lt, ctx_ex)
    ex_json = json_notas(res_ex, "notas de exemplo")
    ex_json["conferencia"] = _conferencia_exemplo(res_ex)
    ex_json["token"] = guarda.por(Guardado("notas", time.time(), res_ex, nome="exemplo", permanente=True), "exemplo")

    # Cadastro de exemplo: a exportação "do Bling" do mercado fictício (porta 2 + arquivo pronto do Bling).
    nome_cad = next(k for k in ex_arquivos if k.endswith("-bling.csv"))
    df_cad, info_cad = CAD.ler_planilha_bytes(nome_cad, ex_arquivos[nome_cad])
    out_cad, s_cad = CAD.auditar_cadastro(df_cad, ctx)
    cad_json = json_cadastro(out_cad, s_cad, Path(nome_cad).name)
    cad_json["token"] = guarda.por(
        Guardado(
            "cadastro", time.time(), cadastro=out_cad, original=df_cad, info=info_cad, resumo=s_cad,
            nome="mercado-exemplo", permanente=True,
        ),
        "cadastro-exemplo",
    )  # fmt: skip

    estado = {
        "modelo": ctx.classificador is not None,
        "modelo_info": ctx.classificador.info if ctx.classificador else "",
        "tabela_ncm": ex_json["resumo"]["tabela_ncm"],
        "chat": chat,
        "sistemas": FMT.publico(),
        "limites": {
            "envio_mb": MAX_ENVIO // (1024 * 1024),
            "arquivos": MAX_ARQUIVOS,
            "itens": MAX_ITENS,
            "planilha_mb": MAX_PLANILHA // (1024 * 1024),
            "produtos": MAX_PRODUTOS,
            "envios_hora": LIMITES["envio"][0][0],
            "envios_dia": LIMITES["envio"][1][0],
        },
    }

    def ip_de(request: Request) -> str:
        return request.client.host if request.client else "?"

    def checa(request: Request, tipo: str):
        espera = lim.permitir(ip_de(request), tipo)
        if espera is not None:
            raise HTTPException(429, f"Muitos pedidos seguidos. Tente de novo em {espera} min.")

    def uma_vez(fn, *a):
        if not vez.acquire(timeout=40):
            raise HTTPException(503, "O Raio-X está conferindo outro envio agora. Tente de novo em 1 minuto.")
        try:
            return fn(*a)
        finally:
            vez.release()

    @app.middleware("http")
    async def cabecalhos(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = csp
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(HTTPException)
    async def erro_http(_request: Request, exc: HTTPException):
        return JSONResponse({"erro": exc.detail}, status_code=exc.status_code)

    @app.get("/", include_in_schema=False)
    def inicio():
        return FileResponse(STATIC / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/saude")
    def saude():
        return {"ok": True, "modelo": ctx.classificador is not None}

    @app.get("/api/estado")
    def ver_estado():
        return estado

    @app.post("/api/exemplo")
    def exemplo(request: Request):
        checa(request, "exemplo")
        return ex_json

    @app.get("/api/exemplo/notas.zip")
    def exemplo_zip(request: Request):
        checa(request, "baixar")
        return Response(
            ex_zip,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{EL.PASTA_ZIP}.zip"'},
        )

    @app.get("/api/exemplo/gabarito.csv")
    def exemplo_gabarito(request: Request):
        checa(request, "baixar")
        return Response(
            ex_arquivos[f"{EL.PASTA_ZIP}/gabarito.csv"],
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="gabarito-notas-exemplo.csv"'},
        )

    @app.post("/api/notas")
    async def notas(request: Request):
        checa(request, "envio")
        corpo = await ler_corpo(request, MAX_ENVIO)
        arqs = arquivos_do_multipart(request.headers.get("content-type", ""), corpo)
        del corpo
        if not arqs:
            raise HTTPException(400, "Nenhum arquivo recebido.")
        if not any(n.lower().endswith((".xml", ".zip")) for n, _ in arqs):
            raise HTTPException(400, "Envie arquivos .xml de NF-e/NFC-e ou um .zip com eles.")

        def conferir():
            lt = ler_memoria(arqs, max_arquivos=MAX_ARQUIVOS)
            if not lt.notas:
                motivo = "; ".join(lt.avisos[:3]) or "nenhum XML de NF-e encontrado"
                raise HTTPException(400, f"Não achei nota fiscal nos arquivos ({motivo}).")
            n_itens = sum(len(n.itens) for n in lt.notas)
            if n_itens > MAX_ITENS:
                raise HTTPException(413, f"São {n_itens} itens; o limite por envio é {MAX_ITENS}. Divida o envio.")
            regras = (
                R.RegrasDoEscritorio.de_texto(lt.regras_texto, "envio") if lt.regras_texto else R.RegrasDoEscritorio()
            )
            c = motor.Contexto(historico=ctx.historico, classificador=ctx.classificador, escritorio=regras)
            t0 = time.time()
            res = motor.auditar_notas(lt, c)
            log.info("notas: %d notas, %d itens, %.1fs", len(lt.notas), n_itens, time.time() - t0)
            return res

        res = await run_in_threadpool(uma_vez, conferir)
        arqs.clear()
        out = json_notas(res, "arquivos enviados")
        out["token"] = guarda.por(Guardado("notas", time.time(), res, nome="notas"))
        return out

    @app.post("/api/cadastro/exemplo")
    def cadastro_exemplo(request: Request):
        checa(request, "exemplo")
        return cad_json

    @app.post("/api/cadastro")
    async def cadastro(request: Request):
        checa(request, "envio")
        corpo = await ler_corpo(request, MAX_PLANILHA + 64 * 1024)
        arqs = arquivos_do_multipart(request.headers.get("content-type", ""), corpo)
        del corpo
        if not arqs:
            raise HTTPException(400, "Nenhuma planilha recebida.")
        nome, raw = arqs[0]
        if not nome.lower().endswith((".csv", ".xlsx", ".txt")):
            raise HTTPException(400, "Envie a planilha em .csv ou .xlsx (exportada do seu sistema).")

        def conferir():
            try:
                df, info = CAD.ler_planilha_bytes(nome, raw)
            except Exception as ex:  # noqa: BLE001
                raise HTTPException(400, "Não consegui ler a planilha. Confira se é CSV ou XLSX.") from ex
            if len(df) > MAX_PRODUTOS:
                raise HTTPException(413, f"São {len(df)} produtos; o limite por envio é {MAX_PRODUTOS}.")
            try:
                out, s = CAD.auditar_cadastro(df, ctx)
            except ValueError as ex:
                raise HTTPException(400, str(ex)) from ex
            return df, info, out, s

        df, info, out, s = await run_in_threadpool(uma_vez, conferir)
        resp = json_cadastro(out, s, Path(nome).name)
        resp["token"] = guarda.por(
            Guardado("cadastro", time.time(), cadastro=out, original=df, info=info, resumo=s, nome=Path(nome).stem)
        )
        return resp

    @app.post("/api/pesquisar")
    async def pesquisar(request: Request):
        checa(request, "pesquisa")
        corpo = await ler_corpo(request, 4096)
        try:
            import json as _json

            q = str(_json.loads(corpo or b"{}").get("q", ""))[:200].strip()
        except ValueError as ex:
            raise HTTPException(400, "Pedido inválido.") from ex
        if len(q) < 3:
            raise HTTPException(400, "Escreva pelo menos 3 letras.")
        if ctx.classificador is None:
            raise HTTPException(503, "A pesquisa precisa do modelo, que não está carregado neste servidor.")
        return {"q": q, "resultados": motor.pesquisar(q, ctx, k=3)}

    @app.get("/api/relatorio/{token}")
    def baixar_relatorio(token: str, request: Request):
        checa(request, "baixar")
        g = guarda.pegar(token)
        if g is None:
            raise HTTPException(404, "Esse resultado já saiu da memória (30 min). Confira de novo.")
        buf = io.BytesIO()
        if g.tipo == "notas":
            relatorio.xlsx_notas(g.resultado, buf)
            nome = "raio-x-notas.xlsx" if g.nome != "exemplo" else "raio-x-notas-de-exemplo.xlsx"
        else:
            relatorio.xlsx_cadastro(g.cadastro, g.resumo, buf)
            nome = f"raio-x-cadastro-{re.sub(r'[^A-Za-z0-9_-]', '', g.nome)[:40] or 'planilha'}.xlsx"
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )

    @app.post("/api/exportar")
    async def exportar(request: Request):
        checa(request, "baixar")
        import json as _json

        corpo = await ler_corpo(request, 512 * 1024)
        try:
            pedido = _json.loads(corpo or b"{}")
        except ValueError as ex:
            raise HTTPException(400, "Pedido inválido.") from ex
        sistema = str(pedido.get("sistema", "generico"))
        if sistema not in FMT.SISTEMAS:
            raise HTTPException(400, "Sistema desconhecido.")
        g = guarda.pegar(str(pedido.get("token", "")))
        if g is None:
            raise HTTPException(404, "Esse resultado já saiu da memória (30 min). Confira de novo.")
        try:
            arq = _exportar(g, sistema, pedido)
        except ValueError as ex:
            raise HTTPException(400, str(ex)) from ex
        h = {"Content-Disposition": f'attachment; filename="{arq.nome}"'}
        if arq.avisos:
            h["X-Raiox-Avisos"] = " | ".join(arq.avisos).encode("ascii", "xmlcharrefreplace").decode()[:900]
        return Response(arq.dados, media_type=arq.tipo, headers=h)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _linhas_lista_notas(res, empresa: str | None) -> list[dict]:
    corr = res.correcoes
    if corr is None or corr.empty:
        return []
    out = []
    itens = res.itens
    for _, r in corr.iterrows():
        if empresa and r["grupo"] != empresa:
            continue
        # Só os produtos da própria empresa (as notas que ela emitiu): os de fornecedor, o fornecedor corrige.
        emp = itens.loc[itens["grupo"] == r["grupo"], "empresa_cnpj"]
        if len(emp) and emp.iloc[0] and r["emitente_cnpj"] != emp.iloc[0]:
            continue
        out.append(
            {
                "Empresa": _txt(r["emitente"]),
                "Código do produto": _txt(r["codigo"]),
                "Código de barras (GTIN)": _txt(r["gtin"]),
                "Descrição": _txt(r["descricao"]),
                "NCM atual": _txt(r["ncm_atual"]),
                "NCM novo": _txt(r["ncm_sugerido"]),
                "Descrição oficial do NCM novo": _txt(r["ncm_sugerido_descricao"]),
                "Por que trocar": _txt(r["motivo"]),
            }
        )
    return out


def _exportar(g: Guardado, sistema: str, pedido: dict) -> FMT.Arquivo:
    if g.tipo == "notas":
        linhas = _linhas_lista_notas(g.resultado, pedido.get("empresa") or None)
        return FMT.lista_correcao(sistema, linhas, "correcao-ncm-das-notas")
    aprovados_raw = pedido.get("aprovados") or []
    aprovados: dict[int, str] = {}
    for a in aprovados_raw[:MAX_PRODUTOS]:
        try:
            aprovados[int(a["linha"])] = re.sub(r"\D", "", str(a["ncm"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not aprovados:
        raise ValueError("Marque pelo menos um produto para trocar o NCM.")
    s = FMT.SISTEMAS[sistema]
    col_ncm = (g.resumo.get("colunas") or {}).get("ncm")
    if s.arquivo_pronto and FMT.coluna_id(list(g.original.columns)) is not None:
        return FMT.arquivo_pronto(sistema, g.original, g.info, col_ncm, aprovados, g.nome or "produtos")
    cols = g.resumo.get("colunas") or {}
    linhas = []
    por_linha = {int(r["linha_planilha"]) - 2: r for _, r in g.cadastro.iterrows()}
    for i, ncm in sorted(aprovados.items()):
        r = por_linha.get(i)
        if r is None:
            continue
        linhas.append(
            {
                "Empresa": "",
                "Código do produto": _txt(r.get(cols.get("codigo", ""), "")),
                "Código de barras (GTIN)": _txt(r.get(cols.get("gtin", ""), "")),
                "Descrição": _txt(r.get(cols.get("descricao", ""), "")),
                "NCM atual": _txt(r["ncm_atual"]),
                "NCM novo": ncm,
                "Descrição oficial do NCM novo": _txt(r["ncm_sugerido_descricao"]) if r["ncm_sugerido"] == ncm else "",
                "Por que trocar": _txt(r["motivo"]),
            }
        )
    return FMT.lista_correcao(sistema, linhas, f"correcao-ncm-{g.nome or 'cadastro'}")


def rodar(porta: int = PORTA) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = criar_app()
    log.info("Raio-X Fiscal em http://%s:%d (só nesta máquina; o Nginx publica)", HOST, porta)
    uvicorn.run(
        app,
        host=HOST,
        port=porta,
        access_log=False,  # sem log de acesso: nem IP, nem caminho
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        workers=1,
        log_level="warning",
        timeout_keep_alive=10,
    )
