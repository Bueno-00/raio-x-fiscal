"""Porta 2: planilha do cadastro de produtos (exportada do sistema), conferida ANTES de emitir.

Aceita CSV (separador ; , ou tab; UTF-8 ou Latin-1) e XLSX. As colunas são achadas pelo nome
(código/SKU, descrição, NCM, GTIN/EAN), então serve para a exportação do Bling e de outros
sistemas sem configurar nada.

Fluxo com gente no meio (a máquina não troca NCM sozinha):
1. `rxf cadastro planilha.csv` -> relatório + planilha de correção com a coluna "NCM aprovado"
   (vem preenchida com o NCM atual; a pessoa troca só onde concorda com a sugestão);
2. `rxf cadastro-exportar correcao.xlsx` -> arquivo no layout da planilha original, só com as
   linhas que mudaram, para importar de volta no sistema (ver README: Bling e Domínio).
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

from raio_x_fiscal.pipeline.normalize import normalize_description
from raio_x_fiscal.produto import regras as R

ALIASES = {
    "codigo": ["codigo", "codigo sku", "sku", "cod", "codigo do produto", "cod produto", "referencia", "codigo (sku)"],
    "descricao": ["descricao", "descricao do produto", "nome", "produto", "nome do produto", "descricao completa"],
    "ncm": ["ncm", "classificacao fiscal", "class fiscal", "ncm sh", "codigo ncm", "ncm/sh"],
    "gtin": [
        "gtin",
        "ean",
        "gtin ean",
        "gtin/ean",
        "codigo de barras",
        "cod barras",
        "ean gtin",
        "gtin ean (codigo de barras)",
    ],
}


def _norm_col(c: str) -> str:
    s = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9/()]+", " ", s).strip()


def achar_colunas(cols: list[str]) -> dict[str, str]:
    """{'codigo': 'Código', 'descricao': 'Descrição', 'ncm': 'NCM', 'gtin': 'GTIN/EAN'} (o que achar)."""
    normal = {_norm_col(c): c for c in cols}
    out = {}
    for campo, nomes in ALIASES.items():
        for n in nomes:
            if n in normal:
                out[campo] = normal[n]
                break
        else:
            for nc, orig in normal.items():
                if any(nc.startswith(n) for n in nomes) and orig not in out.values():
                    out[campo] = orig
                    break
    return out


def ler_planilha(path: Path) -> tuple[pd.DataFrame, dict]:
    """Lê CSV/XLSX como texto (sem converter NCM e GTIN em número). Devolve (df, info do formato)."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        df = pd.read_excel(path, dtype=str).fillna("")
        return df, {"tipo": "xlsx"}
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    primeira = texto.splitlines()[0] if texto else ""
    sep = max([";", ",", "\t"], key=primeira.count)
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
    return df, {"tipo": "csv", "separador": sep, "codificacao": enc}


def so_digitos(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))


def auditar_cadastro(df: pd.DataFrame, ctx) -> tuple[pd.DataFrame, dict]:
    """Semáforo por produto. Devolve (planilha de correção, resumo)."""
    cols = achar_colunas(list(df.columns))
    if "descricao" not in cols or "ncm" not in cols:
        raise ValueError(
            "não achei as colunas de descrição e NCM na planilha "
            f"(colunas encontradas: {', '.join(map(str, df.columns))})"
        )
    tabela = ctx.historico.atual
    desc = df[cols["descricao"]].astype(str).tolist()
    ncms = [so_digitos(x) for x in df[cols["ncm"]]]
    gtins = [so_digitos(x) for x in df[cols["gtin"]]] if "gtin" in cols else [""] * len(df)
    sug = ctx.classificador.sugerir(desc, tabela) if ctx.classificador else {}

    ncm_por_gtin: dict[str, Counter] = {}
    for g, n in zip(gtins, ncms, strict=True):
        if g and R.gtin_valido(g):
            ncm_por_gtin.setdefault(g, Counter())[n] += 1

    linhas = []
    for idx, (d, n, g) in enumerate(zip(desc, ncms, gtins, strict=True)):
        s = sug.get(normalize_description(d), [])
        achados = R.regra_ncm_formato(n)
        if not achados and not tabela.existe(n):
            achados.append(
                R.Achado(
                    "NCM_INEXISTENTE",
                    R.VERMELHO,
                    f"O NCM {R.fmt_ncm(n)} não existe na tabela oficial de hoje ({tabela.vigente_em}). "
                    "A próxima nota com ele sai errada.",
                    "Troque pelo NCM correto (veja a sugestão).",
                )
            )
        if not any(a.regra == "NCM_AUSENTE" for a in achados):
            achados += R.regra_ncm_modelo(n, d, s, tabela, ctx.limiar_vermelho, ctx.limiar_amarelo)
        achados += R.regra_gtin(g or None)
        if g and g in ncm_por_gtin and len(ncm_por_gtin[g]) > 1:
            outros = ", ".join(R.fmt_ncm(c) for c in ncm_por_gtin[g] if c != n)
            achados.append(
                R.Achado(
                    "PRODUTO_NCM_DIVERGENTE",
                    R.AMARELO,
                    f"O mesmo código de barras está cadastrado com outro NCM: {outros}.",
                    "Deixe um NCM só para o produto.",
                )
            )
        nivel = max((a.nivel for a in achados), default=R.VERDE)
        ncm_sug = next((a.ncm_sugerido for a in achados if a.ncm_sugerido), None)
        if not ncm_sug and any(a.regra in ("NCM_INEXISTENTE", "NCM_AUSENTE") for a in achados) and s:
            ncm_sug = s[0][0]
        linhas.append(
            {
                "linha_planilha": idx + 2,
                "semaforo": R.NOME_NIVEL[nivel],
                "nivel": nivel,
                "motivo": " | ".join(a.motivo for a in achados),
                "o_que_fazer": " | ".join(dict.fromkeys(a.acao for a in achados if a.acao)),
                "ncm_atual": n,
                "ncm_atual_descricao": tabela.descricao(n),
                "ncm_atual_curta": tabela.curta(n),
                "ncm_sugerido": ncm_sug or "",
                "ncm_sugerido_descricao": tabela.descricao(ncm_sug) if ncm_sug else "",
                "ncm_sugerido_curta": tabela.curta(ncm_sug) if ncm_sug else "",
                "confianca_modelo": round(s[0][1], 4) if s else None,
                "top3_modelo": "; ".join(f"{c} ({p:.0%})" for c, p in s[:3]),
                "ncm_aprovado": n,
                "regras": ", ".join(a.regra for a in achados),
            }
        )
    out = pd.concat([df.reset_index(drop=True), pd.DataFrame(linhas)], axis=1)
    resumo = {
        "produtos": len(out),
        "vermelho": int((out["nivel"] == R.VERMELHO).sum()),
        "amarelo": int((out["nivel"] == R.AMARELO).sum()),
        "verde": int((out["nivel"] == R.VERDE).sum()),
        "colunas": cols,
        "tabela_ncm": f"vigente em {tabela.vigente_em} ({tabela.ato})",
        "modelo": ctx.classificador.info if ctx.classificador else "",
    }
    return out.sort_values(["nivel", "linha_planilha"], ascending=[False, True]), resumo


def eh_exportacao_bling(colunas: list[str]) -> bool:
    """A exportação de produtos do Bling começa por ID, Código, Descrição, Unidade, NCM (ajuda do Bling)."""
    n = [_norm_col(c) for c in colunas[:6]]
    return (
        len(n) >= 5
        and n[0] == "id"
        and n[1] == "codigo"
        and n[2] == "descricao"
        and n[4] in ("ncm", "classificacao fiscal")
    )


def exportar_aprovados(correcao: Path, destino_dir: Path, max_linhas: int = 1000) -> dict:
    """Lê a planilha de correção (com 'ncm_aprovado' revisado pela pessoa) e grava, no layout
    original e com todas as colunas originais intactas, só as linhas cujo NCM mudou.

    Regras do Bling (ajuda oficial, 07/11/2026): a chave é a coluna ID; célula vazia apaga o dado
    no cadastro, então nenhuma outra coluna é mexida; no máximo 1000 produtos por arquivo; importar
    em "Importar e Atualizar produtos" com a operação "Atualizar".
    """
    df = pd.read_excel(correcao, sheet_name="Correção", dtype=str).fillna("")
    extras = {
        "linha_planilha", "semaforo", "nivel", "motivo", "o_que_fazer", "ncm_atual", "ncm_atual_descricao",
        "ncm_atual_curta", "ncm_sugerido", "ncm_sugerido_descricao", "ncm_sugerido_curta", "confianca_modelo",
        "top3_modelo", "ncm_aprovado", "regras",
    }  # fmt: skip
    originais = [c for c in df.columns if c not in extras]
    cols = achar_colunas(originais)
    mudou = df[df["ncm_aprovado"].map(so_digitos) != df["ncm_atual"].map(so_digitos)].copy()
    invalidos = [v for v in mudou["ncm_aprovado"] if len(so_digitos(v)) != 8]
    if invalidos:
        raise ValueError(f"NCM aprovado com formato errado: {', '.join(invalidos[:5])}")
    bling = eh_exportacao_bling(originais)
    avisos = []
    if bling:
        sem_id = mudou[originais[0]].str.strip() == ""
        if sem_id.any():
            avisos.append(f"{int(sem_id.sum())} linhas sem ID ficaram de fora (sem ID o Bling cria produto novo)")
            mudou = mudou[~sem_id]

    def formata(orig: str, novo: str) -> str:
        d = so_digitos(novo)
        return f"{d[:4]}.{d[4:6]}.{d[6:]}" if "." in str(orig) else d

    mudou[cols["ncm"]] = [formata(o, a) for o, a in zip(mudou[cols["ncm"]], mudou["ncm_aprovado"], strict=True)]
    saida = mudou[originais]
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    prefixo = "para-importar-bling" if bling else "para-importar"
    arquivos = []
    for k, ini in enumerate(range(0, max(len(saida), 1), max_linhas), start=1):
        parte = saida.iloc[ini : ini + max_linhas]
        if parte.empty:
            break
        arq = destino_dir / f"{prefixo}-parte-{k}.xlsx"
        parte.to_excel(arq, index=False)
        arquivos.append(str(arq))
    return {"linhas_alteradas": len(saida), "arquivos": arquivos, "layout_bling": bling, "avisos": avisos}
