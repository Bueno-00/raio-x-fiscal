"""Motor do Raio-X: junta leitura (XML, planilha ou texto), modelo e regras, e devolve tabelas.

As 3 portas de entrada usam o mesmo motor:
1. `auditar_notas(leitura)`: XML das notas -> semáforo por item, agrupado por empresa e nota;
2. `auditar_cadastro(df)`: planilha do cadastro de produtos -> semáforo por produto, antes de emitir;
3. `pesquisar(texto)`: descrição digitada -> os NCMs mais prováveis com a descrição oficial.

O modelo é o baseline da fase 1 (TF-IDF + SVM hierárquico, calibrado). Se a pasta `models/` não
existir (um clone novo do repositório), as regras rodam do mesmo jeito e o relatório avisa que a
checagem "NCM x descrição" ficou de fora.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from raio_x_fiscal.pipeline.normalize import normalize_description
from raio_x_fiscal.produto import regras as R
from raio_x_fiscal.produto.ncm_tabela import HistoricoNCM
from raio_x_fiscal.produto.nfe import Leitura, Nota, empresa_do_grupo

log = logging.getLogger(__name__)

LIMIAR_VERMELHO_PADRAO = 0.99  # limiar da auditoria da fase 1 (inspeção manual: 50 de 60 eram erro real)
LIMIAR_AMARELO_PADRAO = 0.90
SEEDS = Path(__file__).resolve().parents[1] / "seeds"


def cfops_conhecidos() -> set[str]:
    p = SEEDS / "cfop_vistos.txt"
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text().splitlines() if re.fullmatch(r"\d{4}", ln.strip())}


class Classificador:
    """Modelo descrição -> NCM com as sugestões filtradas pela tabela oficial vigente."""

    def __init__(self, predictor, limiar_vermelho: float = LIMIAR_VERMELHO_PADRAO):
        self.predictor = predictor
        self.limiar_vermelho = limiar_vermelho
        self.info = ""

    @classmethod
    def carregar(cls, models_dir: Path) -> Classificador | None:
        if not (models_dir / "hier_svm.joblib").exists():
            log.warning("modelo não encontrado em %s: a checagem NCM x descrição fica de fora", models_dir)
            return None
        from raio_x_fiscal.ml.predict import NcmPredictor

        pred = NcmPredictor.load(models_dir)
        limiar = LIMIAR_VERMELHO_PADRAO
        meta_p = models_dir / "metadata.json"
        info = "baseline TF-IDF + SVM hierárquico (fase 1)"
        if meta_p.exists():
            meta = json.loads(meta_p.read_text())
            limiar = float((meta.get("audit") or {}).get("threshold") or limiar)
        c = cls(pred, limiar)
        c.info = info
        return c

    def sugerir(self, descricoes: list[str], tabela, k: int = 5, lote: int = 20_000) -> dict[str, list]:
        """{descrição normalizada: [(ncm, p), ...]} só com códigos que existem na tabela."""
        unicos = sorted({normalize_description(d) for d in descricoes if d})
        out: dict[str, list] = {}
        for i in range(0, len(unicos), lote):
            parte = unicos[i : i + lote]
            X = self.predictor.featurizer.transform(parte)
            res = self.predictor.model.predict_topk(X, k + 5)
            for j, norm in enumerate(parte):
                pares = [
                    (str(c), float(p))
                    for c, p in zip(res["ncm_topk"][j], res["ncm_prob"][j], strict=True)
                    if tabela.existe(str(c))
                ]
                out[norm] = pares[:k]
        return out


@dataclass
class Contexto:
    historico: HistoricoNCM
    classificador: Classificador | None = None
    escritorio: R.RegrasDoEscritorio = field(default_factory=R.RegrasDoEscritorio)
    limiar_amarelo: float = LIMIAR_AMARELO_PADRAO
    cadastro: dict | None = None  # {"codigo": {...}, "gtin": {...}} -> ncm do cadastro
    cfops: set[str] = field(default_factory=cfops_conhecidos)

    @property
    def limiar_vermelho(self) -> float:
        return self.classificador.limiar_vermelho if self.classificador else LIMIAR_VERMELHO_PADRAO

    @classmethod
    def padrao(
        cls,
        data_dir: Path | None,
        models_dir: Path | None,
        excecoes: Path | None = None,
        com_modelo: bool = True,
    ) -> Contexto:
        hist = HistoricoNCM.carregar(data_dir)
        clf = Classificador.carregar(models_dir) if (com_modelo and models_dir) else None
        return cls(historico=hist, classificador=clf, escritorio=R.RegrasDoEscritorio.ler(excecoes))


@dataclass
class Resultado:
    itens: pd.DataFrame
    notas: pd.DataFrame
    empresas: pd.DataFrame
    resumo: dict
    avisos: list[str]
    correcoes: pd.DataFrame


def _pior(achados: list[R.Achado]) -> int:
    return max((a.nivel_efetivo for a in achados), default=R.VERDE)


def _texto(achados: list[R.Achado], attr: str) -> str:
    partes = []
    for a in achados:
        if a.aceito:
            if attr == "motivo":
                partes.append(f"{a.motivo} Aceito pela regra do escritório: {a.aceito}.")
            continue
        v = getattr(a, attr)
        if v and v not in partes:
            partes.append(v)
    return " | ".join(partes)


def _sugestao_ncm(achados: list[R.Achado], sugestoes: list) -> str | None:
    for a in achados:
        if a.ncm_sugerido and not a.aceito:
            return a.ncm_sugerido
    if any(a.regra in ("NCM_INEXISTENTE", "NCM_AUSENTE") and not a.aceito for a in achados) and sugestoes:
        return sugestoes[0][0]
    return None


def auditar_notas(leitura: Leitura, ctx: Contexto) -> Resultado:
    tabela = ctx.historico.atual
    notas = leitura.notas

    # Grupo = subpasta/zip; sem grupo, cada emitente vira o seu grupo.
    grupos: dict[str, list[Nota]] = defaultdict(list)
    for n in notas:
        grupos[n.grupo or f"emitente {n.emit_cnpj}"].append(n)
    empresa_de = {g: empresa_do_grupo(ns) for g, ns in grupos.items()}

    sugestoes = {}
    if ctx.classificador:
        sugestoes = ctx.classificador.sugerir([i.descricao for n in notas for i in n.itens], tabela)

    # Mesmo produto (emitente + código, ou GTIN) com NCMs diferentes dentro do grupo.
    ncm_por_produto: dict[tuple, Counter] = defaultdict(Counter)
    for g, ns in grupos.items():
        for n in ns:
            for i in n.itens:
                ncm_por_produto[(g, "cod", n.emit_cnpj, i.codigo)][i.ncm] += 1
                if i.gtin and R.gtin_valido(i.gtin):
                    ncm_por_produto[(g, "gtin", i.gtin)][i.ncm] += 1

    linhas = []
    for g, ns in grupos.items():
        empresa = empresa_de[g]
        for n in ns:
            if empresa and n.emit_cnpj == empresa:
                sentido = "saída"
            elif empresa and n.dest_doc == empresa:
                sentido = "entrada"
            else:
                sentido = "terceiros" if empresa else ("saída" if n.tp_nf == "1" else "entrada")
            for i in n.itens:
                norm = normalize_description(i.descricao)
                sug = [] if i.servico else sugestoes.get(norm, [])
                achados: list[R.Achado] = []
                if n.cancelada:
                    achados.append(
                        R.Achado(
                            "NOTA_CANCELADA",
                            R.AMARELO,
                            "Existe evento de cancelamento desta nota na pasta.",
                            "Não importe esta nota.",
                        )
                    )
                achados += R.regra_ncm_formato(i.ncm, i.servico)
                if not i.servico:
                    achados += R.regra_ncm_tabela(i.ncm, n.data_emissao, ctx.historico)
                if not any(a.regra in ("NCM_AUSENTE",) for a in achados):
                    achados += R.regra_ncm_modelo(
                        i.ncm, i.descricao, sug, tabela, ctx.limiar_vermelho, ctx.limiar_amarelo
                    )
                achados += R.regra_cfop(
                    i.cfop, n.tp_nf, n.emit_uf, n.dest_uf, n.id_dest, n.ind_pres, n.modelo, ctx.cfops or None
                )
                achados += R.regra_cst_regime(n.crt, i.cst, i.csosn)
                achados += R.regra_gtin(i.gtin)
                achados += _divergencias(g, n, i, ncm_por_produto)
                if ctx.cadastro:
                    achados += _contra_cadastro(i, ctx.cadastro, sentido)
                ctx.escritorio.aplicar(achados, empresa, n.emit_cnpj, i.cfop, i.ncm, i.codigo)
                nivel = _pior(achados)
                ncm_sug = _sugestao_ncm(achados, sug)
                cfop_sug = next((a.cfop_sugerido for a in achados if a.cfop_sugerido and not a.aceito), None)
                linhas.append(
                    {
                        "grupo": g,
                        "empresa_cnpj": empresa or "",
                        "sentido": sentido,
                        "chave": n.chave,
                        "modelo": n.modelo,
                        "serie": n.serie,
                        "numero": n.numero,
                        "data_emissao": n.data_emissao,
                        "emitente": n.emit_nome,
                        "emitente_cnpj": n.emit_cnpj,
                        "emitente_uf": n.emit_uf,
                        "destinatario": n.dest_nome or "",
                        "destinatario_doc": n.dest_doc or "",
                        "destinatario_uf": n.dest_uf or "",
                        "crt": n.crt or "",
                        "n_item": i.n_item,
                        "codigo": i.codigo,
                        "gtin": i.gtin or "",
                        "descricao": i.descricao,
                        "ncm": i.ncm,
                        "ncm_descricao_oficial": tabela.descricao(i.ncm),
                        "ncm_descricao_curta": tabela.curta(i.ncm),
                        "cfop": i.cfop,
                        "cst_csosn": i.csosn or i.cst or "",
                        "quantidade": i.quantidade,
                        "valor_total": i.valor_total,
                        "semaforo": R.NOME_NIVEL[nivel],
                        "nivel": nivel,
                        "regras": ", ".join(a.regra for a in achados if not a.aceito and a.nivel > R.VERDE),
                        "aceitas_escritorio": ", ".join(a.regra for a in achados if a.aceito),
                        "motivo": _texto(achados, "motivo"),
                        "o_que_fazer": _texto([a for a in achados if a.nivel > R.VERDE], "acao"),
                        "ncm_sugerido": ncm_sug or "",
                        "ncm_sugerido_descricao": tabela.descricao(ncm_sug) if ncm_sug else "",
                        "ncm_sugerido_curta": tabela.curta(ncm_sug) if ncm_sug else "",
                        "confianca_modelo": round(sug[0][1], 4) if sug else None,
                        "top3_modelo": "; ".join(f"{c} ({p:.0%})" for c, p in sug[:3]),
                        "cfop_sugerido": cfop_sug or "",
                        "nota_cancelada": n.cancelada,
                        "_achados": achados,
                    }
                )

    itens = pd.DataFrame(linhas)
    return _montar(itens, leitura.avisos, ctx, n_arquivos=leitura.arquivos_lidos, n_notas=len(notas))


def _divergencias(g, n: Nota, i, ncm_por_produto) -> list[R.Achado]:
    for chave, nome in (((g, "cod", n.emit_cnpj, i.codigo), f"código {i.codigo}"), ((g, "gtin", i.gtin), None)):
        if chave[-1] in (None, "") or chave not in ncm_por_produto:
            continue
        cont = ncm_por_produto[chave]
        if len(cont) < 2:
            continue
        mais, qtd = cont.most_common(1)[0]
        empate = sum(1 for v in cont.values() if v == qtd) > 1
        if i.ncm == mais and not empate:
            continue
        outros = ", ".join(f"{R.fmt_ncm(c)} ({v}x)" for c, v in cont.most_common() if c != i.ncm)
        ident = nome or f"código de barras {i.gtin}"
        return [
            R.Achado(
                "PRODUTO_NCM_DIVERGENTE",
                R.AMARELO,
                f"O mesmo produto ({ident}) aparece com outro NCM em notas desta pasta: {outros}.",
                "Unifique o NCM do produto no cadastro.",
                ncm_sugerido=None if empate else mais,
            )
        ]
    return []


def _contra_cadastro(i, cadastro: dict, sentido: str) -> list[R.Achado]:
    ncm_cad = None
    if i.gtin and i.gtin in cadastro.get("gtin", {}):
        ncm_cad = cadastro["gtin"][i.gtin]
    elif sentido == "saída" and i.codigo in cadastro.get("codigo", {}):
        ncm_cad = cadastro["codigo"][i.codigo]
    if not ncm_cad or ncm_cad == i.ncm:
        return []
    return [
        R.Achado(
            "CADASTRO_DIVERGENTE",
            R.AMARELO,
            f"No cadastro de produtos o NCM é {R.fmt_ncm(ncm_cad)}; nesta nota saiu {R.fmt_ncm(i.ncm)}.",
            "Descubra qual está certo e deixe nota e cadastro iguais.",
            ncm_sugerido=ncm_cad,
        )
    ]


def _montar(itens: pd.DataFrame, avisos: list[str], ctx: Contexto, n_arquivos: int, n_notas: int) -> Resultado:
    tabela = ctx.historico.atual
    if itens.empty:
        vazio = pd.DataFrame()
        resumo = _resumo(itens, ctx, n_arquivos, n_notas)
        return Resultado(itens, vazio, vazio, resumo, avisos, vazio)

    def contagem(df):
        return pd.Series(
            {
                "itens": len(df),
                "vermelho": int((df["nivel"] == R.VERMELHO).sum()),
                "amarelo": int((df["nivel"] == R.AMARELO).sum()),
                "verde": int((df["nivel"] == R.VERDE).sum()),
                "valor_itens": float(df["valor_total"].sum()),
            }
        )

    chave_nota = ["grupo", "chave", "numero", "serie", "data_emissao", "emitente", "emitente_uf",
                  "destinatario", "destinatario_uf", "sentido", "nota_cancelada"]  # fmt: skip
    notas = itens.groupby(chave_nota, dropna=False).apply(contagem, include_groups=False).reset_index()
    notas["semaforo"] = notas.apply(
        lambda r: "vermelho" if r["vermelho"] else ("amarelo" if r["amarelo"] else "verde"), axis=1
    )
    notas = notas.sort_values(["grupo", "vermelho", "amarelo", "numero"], ascending=[True, False, False, True])

    emp = itens.groupby(["grupo", "empresa_cnpj"], dropna=False).apply(contagem, include_groups=False).reset_index()
    emp["notas"] = emp["grupo"].map(itens.groupby("grupo")["chave"].nunique())
    nomes = {}
    for g, df in itens.groupby("grupo"):
        cnpj = df["empresa_cnpj"].iloc[0]
        nome = ""
        if cnpj:
            m = df.loc[df["emitente_cnpj"] == cnpj, "emitente"]
            m2 = df.loc[df["destinatario_doc"] == cnpj, "destinatario"]
            nome = (m.iloc[0] if len(m) else (m2.iloc[0] if len(m2) else "")) or ""
        nomes[g] = nome or (df["emitente"].iloc[0] if g.startswith("emitente ") else "")
    emp["empresa"] = emp["grupo"].map(nomes)

    # Correção de cadastro: um produto por linha (emitente + código), com o NCM sugerido.
    corr = itens[itens["ncm_sugerido"] != ""].copy()
    if not corr.empty:
        corr = (
            corr.groupby(["grupo", "emitente_cnpj", "emitente", "codigo"], dropna=False)
            .agg(
                gtin=("gtin", "first"),
                descricao=("descricao", "first"),
                ncm_atual=("ncm", lambda s: ", ".join(sorted(set(s)))),
                ncm_sugerido=("ncm_sugerido", lambda s: Counter(s).most_common(1)[0][0]),
                semaforo=("nivel", "max"),
                motivo=("motivo", "first"),
                notas=("chave", "nunique"),
            )
            .reset_index()
        )
        corr["semaforo"] = corr["semaforo"].map(R.NOME_NIVEL)
        corr["ncm_sugerido_descricao"] = corr["ncm_sugerido"].map(tabela.descricao)
        corr = corr.sort_values(
            ["semaforo", "grupo"],
            key=lambda s: s.map({"vermelho": 0, "amarelo": 1, "verde": 2}) if s.name == "semaforo" else s,
        )
    resumo = _resumo(itens, ctx, n_arquivos, n_notas)
    return Resultado(itens, notas, emp, resumo, avisos, corr)


def _resumo(itens: pd.DataFrame, ctx: Contexto, n_arquivos: int, n_notas: int) -> dict:
    t = ctx.historico.atual
    por_regra: dict[str, dict] = {}
    aceitos = 0
    if not itens.empty:
        for achados in itens["_achados"]:
            for a in achados:
                if a.nivel == R.VERDE:
                    continue
                d = por_regra.setdefault(
                    a.regra, {"nome": R.REGRAS.get(a.regra, a.regra), "vermelho": 0, "amarelo": 0, "aceitos": 0}
                )
                if a.aceito:
                    d["aceitos"] += 1
                    aceitos += 1
                else:
                    d[R.NOME_NIVEL[a.nivel]] += 1
    n = len(itens)
    contar = (lambda nv: int((itens["nivel"] == nv).sum())) if n else (lambda nv: 0)
    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "arquivos": n_arquivos,
        "notas": n_notas,
        "itens": n,
        "vermelho": contar(R.VERMELHO),
        "amarelo": contar(R.AMARELO),
        "verde": contar(R.VERDE),
        "aceitos_escritorio": aceitos,
        "por_regra": por_regra,
        "tabela_ncm": f"vigente em {t.vigente_em or t.desde.strftime('%d/%m/%Y')} ({t.ato})",
        "tabela_desde": ctx.historico.primeira_data.strftime("%d/%m/%Y"),
        "modelo": ctx.classificador.info if ctx.classificador else "",
        "limiar_vermelho": ctx.limiar_vermelho,
        "limiar_amarelo": ctx.limiar_amarelo,
        "regras_escritorio": len(ctx.escritorio.excecoes),
    }


# ---------------------------------------------------------------------------------------------
# Porta 3: pesquisa de um produto
# ---------------------------------------------------------------------------------------------


def pesquisar(texto: str, ctx: Contexto, k: int = 3) -> list[dict]:
    tabela = ctx.historico.atual
    if not ctx.classificador:
        raise RuntimeError("a pesquisa precisa do modelo (pasta models/); rode `make ml` ou baixe os pesos")
    sug = ctx.classificador.sugerir([texto], tabela, k=k).get(normalize_description(texto), [])
    return [
        {
            "ncm": c,
            "ncm_formatado": R.fmt_ncm(c),
            "confianca": round(p, 4),
            "descricao_oficial": tabela.descricao(c),
            "descricao_curta": tabela.curta(c),
        }
        for c, p in sug[:k]
    ]
