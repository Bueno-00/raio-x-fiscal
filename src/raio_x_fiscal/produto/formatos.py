"""Planilha de correção no formato de cada sistema (para importar de volta e atualizar o NCM).

Pesquisa nas ajudas oficiais, acessadas em 08/11/2026 (links em `SISTEMAS[...].fontes`):

| Sistema | Atualiza NCM por planilha? | Chave | O que o Raio-X entrega |
|---|---|---|---|
| Bling | sim ("Importar e Atualizar produtos", operação Atualizar) | ID | arquivo pronto: o mesmo CSV que você exportou, só com as linhas que mudaram e só o NCM trocado, em partes de 1.000 |
| Olist ERP (antigo Tiny) | sim ("Importar produtos de uma planilha", modelo oficial, sem mudar colunas) | ID (ou SKU) | arquivo pronto: o mesmo layout da sua exportação, só NCM trocado, em partes de 500 (recomendação da ajuda) |
| Omie | sim, mas só no modelo oficial protegido por senha e célula vazia APAGA o dado | não publicada (provável "Código do Produto") | lista de-para para colar no modelo oficial, com o aviso |
| Conta Azul | não: a importação só cadastra; NCM se edita produto por produto | - | lista para corrigir um a um |
| Domínio | sem leiaute público de importação de produtos | - | lista para o utilitário "Alterar Produtos" (solução 172) ou para pedir o leiaute ao suporte |

Regra de ouro dos arquivos prontos: nenhuma outra coluna é mexida (no Bling e no Omie, célula
apagada apaga o dado no cadastro) e só vão as linhas que a pessoa aprovou.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field

import pandas as pd

ACESSO = "08/11/2026"


@dataclass(frozen=True)
class Sistema:
    id: str
    nome: str
    arquivo_pronto: bool
    resumo: str
    passos: tuple[str, ...]
    cuidados: tuple[str, ...] = ()
    chave: str = ""
    limite: int = 0
    fontes: tuple[str, ...] = field(default_factory=tuple)


SISTEMAS: dict[str, Sistema] = {
    s.id: s
    for s in (
        Sistema(
            "bling",
            "Bling",
            True,
            "Arquivo pronto para importar: o mesmo CSV que você exportou do Bling, só com os produtos "
            "aprovados e só o NCM trocado (chave: coluna ID; até 1.000 produtos por arquivo).",
            (
                "No Bling, exporte os produtos: Cadastros > Produtos > Mais ações > Exportar dados para planilha.",
                "Envie esse CSV na porta 2 do Raio-X, marque as sugestões que aceita e baixe o arquivo do Bling.",
                "Importe: ícone do perfil > Todas as configurações > Importações de Dados > Importar e Atualizar "
                "produtos > operação Atualizar > Procurar Arquivo > Validar > Importar.",
            ),
            (
                "Não apague colunas nem células: no Bling, informação removida da planilha é removida do cadastro.",
                "Deixe desmarcado 'Atualizar estoque'.",
                "Faça backup (exportação) antes de importar.",
            ),
            "ID",
            1000,
            (
                "https://ajuda.bling.com.br/hc/pt-br/articles/360060827554-Como-editar-e-atualizar-meus-produtos-por-planilha",
                "https://ajuda.bling.com.br/hc/pt-br/articles/360062630653-Cadastrar-produtos-simples-por-planilha",
            ),
        ),
        Sistema(
            "olist",
            "Olist ERP (antigo Tiny)",
            True,
            "Arquivo pronto: o mesmo layout da planilha que você exportou do Olist, só com os produtos "
            "aprovados e só o NCM trocado (chave: coluna ID; até 500 produtos por arquivo, como a ajuda recomenda).",
            (
                "No Olist, exporte os produtos em Cadastros > Produtos (ou baixe o modelo em Início > Ferramentas > "
                "Importações > Produtos e preencha com a sua exportação).",
                "Envie a planilha na porta 2 do Raio-X, marque as sugestões que aceita e baixe o arquivo do Olist.",
                "Importe: Cadastros > Produtos > Mais ações > Importar produtos de uma planilha > Enviar planilha > "
                "critério de reconhecimento: ID > Validar > Meus dados estão corretos > Confirmar a importação.",
            ),
            (
                "Não mude o nome nem a ordem das colunas (a ajuda exige o modelo oficial).",
                "Na pré-visualização, confira se todos aparecem em 'Atualizados' e nenhum em 'Novos'.",
                "Deixe desmarcada a opção de atualizar custo e estoque.",
            ),
            "ID",
            500,
            (
                "https://ajuda.olist.com/produtos/importar-planilha-de-produtos",
                "https://ajuda.olist.com/produtos/acoes-em-lote-e-gerenciamento-de-produtos",
            ),
        ),
        Sistema(
            "omie",
            "Omie",
            False,
            "Lista de-para (Código do Produto e NCM novo) para colar no modelo oficial do Omie. Não dá para "
            "gerar o arquivo pronto: o modelo é protegido por senha e só ele é aceito.",
            (
                "No Omie: Produtos > Importar vários produtos (via planilha) > baixe o modelo (aba Omie_Produtos).",
                "Preencha TODAS as colunas com o valor atual de cada produto (exporte a Relação de Produtos) e "
                "troque só a coluna Código NCM pelos valores desta lista.",
                "Importe o modelo e aguarde o e-mail do Omie com o resultado.",
            ),
            (
                "No Omie, coluna em branco APAGA a informação do cadastro.",
                "A ajuda não diz qual coluna é a chave da atualização; o mais provável é Código do Produto. "
                "Teste com 1 produto antes.",
            ),
            "Código do Produto (provável)",
            0,
            (
                "https://ajuda.omie.com.br/pt-BR/articles/6590176-cadastrando-produtos-em-lote-via-planilha",
                "https://ajuda.omie.com.br/pt-BR/articles/6886853-dicas-para-a-migracao-de-dados-via-planilha-no-omie",
            ),
        ),
        Sistema(
            "contaazul",
            "Conta Azul",
            False,
            "Lista para corrigir produto por produto. A importação da Conta Azul só cadastra produto novo "
            "e a ajuda diz que NCM e CFOP são definidos individualmente em cada produto.",
            ("Estoque > Cadastros > Produtos > abra o produto > Dados fiscais > troque o NCM pelo desta lista.",),
            ("Não use a importação por planilha para isso: produto com código repetido é bloqueado ou arquivado.",),
            "",
            0,
            (
                "https://ajuda.contaazul.com/hc/pt-br/articles/45670706289677-Produtos-como-preencher-a-planilha-modelo-de-cadastro",
                "https://ajuda.contaazul.com/hc/pt-br/articles/49003711419149-A%C3%A7%C3%B5es-em-lote-o-que-%C3%A9-poss%C3%ADvel-fazer-em-lote-na-Conta-Azul-Pro",
            ),
        ),
        Sistema(
            "dominio",
            "Domínio (Thomson Reuters)",
            False,
            "Lista para corrigir no próprio Domínio. Não há leiaute público de importação de cadastro de "
            "produtos (a Central de Soluções só abre para clientes).",
            (
                "No módulo Escrita: Utilitários > Alterar Produtos > Alteração de Produtos > Buscar > selecione os "
                "produtos > Alterar... > guia Impostos (solução 172 da Central de Soluções).",
                "Ou peça ao suporte da Domínio o leiaute de importação de produtos e mande esta lista junto.",
            ),
            (
                "O Domínio cria sozinho uma nova vigência de NCM quando o XML importado difere do cadastro: "
                "confira as notas ANTES do robô importar.",
            ),
            "",
            0,
            (
                "https://www.dominiosistemas.com.br/atualizacoes",
                "http://web.archive.org/web/20240519013553/https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=172",
            ),
        ),
        Sistema(
            "generico",
            "Outro sistema (planilha genérica)",
            False,
            "Planilha com código, código de barras, descrição, NCM atual e NCM novo, para usar em qualquer sistema.",
            ("Use a coluna 'NCM novo' para corrigir o cadastro no seu sistema.",),
            (),
            "",
            0,
            (),
        ),
    )
}


def _norm(c: str) -> str:
    s = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def coluna_id(colunas: list[str]) -> str | None:
    for c in colunas:
        if _norm(c) == "id":
            return c
    return None


def _so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _formata_como(original: str, novo: str) -> str:
    d = _so_digitos(novo)
    return f"{d[:4]}.{d[4:6]}.{d[6:]}" if "." in str(original) else d


def _csv_bytes(df: pd.DataFrame, sep: str, codificacao: str) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, sep=sep, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    enc = "utf-8-sig" if codificacao.lower().startswith("utf") else codificacao
    return buf.getvalue().encode(enc, errors="replace")


@dataclass
class Arquivo:
    nome: str
    dados: bytes
    tipo: str
    linhas: int
    avisos: list[str]


def arquivo_pronto(
    sistema: str,
    original: pd.DataFrame,
    info: dict,
    col_ncm: str,
    aprovados: dict[int, str],
    nome_base: str = "produtos",
) -> Arquivo:
    """Bling e Olist: mesmo layout da planilha enviada, só as linhas aprovadas, só o NCM trocado.

    `aprovados` = {índice da linha na planilha original (0 = primeira linha de dados): NCM novo}.
    """
    s = SISTEMAS[sistema]
    avisos: list[str] = []
    cid = coluna_id(list(original.columns))
    if cid is None:
        raise ValueError(
            f"Para gerar o arquivo do {s.nome}, a planilha precisa ter a coluna ID (é a chave da atualização). "
            "Exporte os produtos do próprio sistema e envie de novo."
        )
    idx = [i for i in sorted(aprovados) if 0 <= i < len(original)]
    invalidos = [aprovados[i] for i in idx if len(_so_digitos(aprovados[i])) != 8]
    if invalidos:
        raise ValueError(f"NCM com formato errado: {', '.join(invalidos[:5])}")
    saida = original.iloc[idx].copy()
    # NCM no mesmo jeito da coluna (com pontos ou só dígitos), olhando a maioria das linhas.
    com_ponto = bool(original[col_ncm].astype(str).str.contains(".", regex=False).mean() >= 0.5)
    saida[col_ncm] = [_formata_como("." if com_ponto else "", aprovados[i]) for i in idx]
    sem_id = saida[cid].astype(str).str.strip() == ""
    if sem_id.any():
        avisos.append(f"{int(sem_id.sum())} produto(s) sem ID ficaram de fora (sem ID o sistema cria produto novo).")
        saida = saida[~sem_id]
    if saida.empty:
        raise ValueError("Nenhum produto aprovado para trocar o NCM.")
    sep = info.get("separador") or ";"
    cod = info.get("codificacao") or "utf-8"
    partes = [saida.iloc[i : i + s.limite] for i in range(0, len(saida), s.limite)] if s.limite else [saida]
    if len(partes) == 1:
        return Arquivo(
            f"{nome_base}-para-importar-{s.id}.csv", _csv_bytes(partes[0], sep, cod), "text/csv", len(saida), avisos
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for k, p in enumerate(partes, start=1):
            zf.writestr(f"{nome_base}-para-importar-{s.id}-parte-{k}.csv", _csv_bytes(p, sep, cod))
    avisos.append(f"{len(partes)} arquivos de até {s.limite} produtos (limite do {s.nome}). Importe um de cada vez.")
    return Arquivo(f"{nome_base}-para-importar-{s.id}.zip", buf.getvalue(), "application/zip", len(saida), avisos)


COLUNAS_LISTA = [
    "Empresa",
    "Código do produto",
    "Código de barras (GTIN)",
    "Descrição",
    "NCM atual",
    "NCM novo",
    "Descrição oficial do NCM novo",
    "Por que trocar",
]


def lista_correcao(sistema: str, linhas: list[dict], nome_base: str = "correcao-ncm") -> Arquivo:
    """Omie, Conta Azul, Domínio e genérico (e Bling/Olist quando não há a planilha com ID): XLSX com a
    lista de-para e uma aba 'Como usar' com os passos daquele sistema e as fontes."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    s = SISTEMAS[sistema]
    if not linhas:
        raise ValueError("Nenhum produto com NCM para trocar.")
    wb = Workbook()
    ws = wb.active
    ws.title = "Correção de NCM"
    ws.append(COLUNAS_LISTA)
    for r in linhas:
        ws.append([r.get(c, "") for c in COLUNAS_LISTA])
    cab = PatternFill("solid", fgColor="12355B")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = cab
        c.alignment = Alignment(vertical="center", wrap_text=True)
    larg = [26, 18, 20, 46, 12, 12, 60, 70]
    for i, w in enumerate(larg):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=isinstance(c.value, str) and len(c.value) > 40)
    como = wb.create_sheet("Como usar")
    texto = [[f"Raio-X Fiscal: correção de NCM para {s.nome}"], [""], [s.resumo], [""], ["Passo a passo"]]
    texto += [[f"{k}. {p}"] for k, p in enumerate(s.passos, start=1)]
    if s.cuidados:
        texto += [[""], ["Cuidados"]] + [[f"- {c}"] for c in s.cuidados]
    if s.fontes:
        texto += [[""], [f"Fontes (ajuda oficial, acesso em {ACESSO})"]] + [[f] for f in s.fontes]
    texto += [[""], ["Confira cada troca antes: o Raio-X sugere, quem decide é você."]]
    for ln in texto:
        como.append(ln)
    como["A1"].font = Font(bold=True, size=13)
    como.column_dimensions["A"].width = 120
    for row in como.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return Arquivo(
        f"{nome_base}-{s.id}.xlsx",
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        len(linhas),
        [],
    )


def publico() -> list[dict]:
    """Resumo dos sistemas para a tela (sem os passos longos)."""
    return [
        {
            "id": s.id,
            "nome": s.nome,
            "arquivo_pronto": s.arquivo_pronto,
            "resumo": s.resumo,
            "passos": list(s.passos),
            "cuidados": list(s.cuidados),
            "fontes": list(s.fontes),
        }
        for s in SISTEMAS.values()
    ]
