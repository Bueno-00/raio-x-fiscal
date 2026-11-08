"""Regras de conferência por item e a "regra do escritório" (exceções aceitas).

Cada regra devolve zero ou mais `Achado`: um nível do semáforo, o motivo em português e o que
fazer. O semáforo do item é o pior nível entre os achados que não foram aceitos pelo escritório.

- vermelho: erro provável (o modelo tem confiança muito alta, ou a regra é objetiva);
- amarelo: conferir (pode ser erro, pode ser caso especial: venda presencial, código antigo...);
- verde: nada encontrado (ou só observações).

A regra do escritório é uma planilha simples (CSV) que diz "para esta empresa, este CFOP/NCM/
produto está certo de propósito". O achado continua no relatório, mas vira verde com o motivo.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

VERDE, AMARELO, VERMELHO = 0, 1, 2
NOME_NIVEL = {VERDE: "verde", AMARELO: "amarelo", VERMELHO: "vermelho"}

REGRAS = {
    "NCM_AUSENTE": "NCM vazio ou fora do formato",
    "NCM_INEXISTENTE": "NCM não existe na tabela oficial",
    "NCM_VIGENCIA": "NCM começou a valer depois da data da nota",
    "NCM_MODELO": "NCM não combina com a descrição",
    "CFOP_INVALIDO": "CFOP fora do formato",
    "CFOP_SENTIDO": "CFOP de entrada numa nota de saída (ou o contrário)",
    "CFOP_UF": "CFOP não bate com os estados da nota",
    "CST_REGIME": "CST/CSOSN não combina com o regime da empresa",
    "PRODUTO_NCM_DIVERGENTE": "Mesmo produto com NCM diferente em outra nota",
    "CADASTRO_DIVERGENTE": "NCM da nota diferente do cadastro",
    "GTIN_INVALIDO": "Código de barras (GTIN) inválido",
    "NOTA_CANCELADA": "Nota cancelada",
}

_CFOP_RE = re.compile(r"^[123567]\d{3}$")
_NCM_RE = re.compile(r"^\d{8}$")
AMBITO = {"1": "interna", "2": "interestadual", "3": "exterior", "5": "interna", "6": "interestadual", "7": "exterior"}
DIGITO = {
    ("1", "interna"): "5",
    ("1", "interestadual"): "6",
    ("1", "exterior"): "7",
    ("0", "interna"): "1",
    ("0", "interestadual"): "2",
    ("0", "exterior"): "3",
}


@dataclass
class Achado:
    regra: str
    nivel: int
    motivo: str
    acao: str = ""
    ncm_sugerido: str | None = None
    cfop_sugerido: str | None = None
    aceito: str | None = None  # motivo da regra do escritório, quando aceito

    @property
    def nivel_efetivo(self) -> int:
        return VERDE if self.aceito else self.nivel


def fmt_data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "sem data"


def fmt_ncm(n: str | None) -> str:
    if not n or len(n) != 8:
        return n or "(vazio)"
    return f"{n[:4]}.{n[4:6]}.{n[6:]}"


# ---------------------------------------------------------------------------------------------
# NCM
# ---------------------------------------------------------------------------------------------


def codigos_do_grupo(ncm: str, tabela, maximo: int = 60) -> list[str]:
    """Códigos que existem hoje no grupo mais próximo do NCM (mesmos 7, 6, 5 ou 4 primeiros dígitos)."""
    if tabela is None or not ncm:
        return []
    for k in (7, 6, 5, 4):
        filhos = sorted(c for c in tabela.folhas if c[:k] == ncm[:k])
        if filhos:
            return filhos[:maximo]
    return []


def regra_ncm_formato(ncm: str, servico: bool = False, tabela=None) -> list[Achado]:
    if servico:
        return []  # item de serviço (grupo ISSQN): NCM 00 é o esperado
    if _NCM_RE.match(ncm or "") and ncm != "00000000":
        return []
    if ncm in ("00", "00000000"):
        return [
            Achado(
                "NCM_AUSENTE",
                AMARELO,
                "Item sem NCM de mercadoria (NCM 00, usado para serviço).",
                "Se for mercadoria, coloque o NCM de 8 dígitos no cadastro. Se for serviço, está ok.",
            )
        ]
    if re.fullmatch(r"\d{7}", ncm or "") and tabela is not None and tabela.existe("0" + ncm):
        certo = "0" + ncm
        return [
            Achado(
                "NCM_AUSENTE",
                VERMELHO,
                f"NCM '{ncm}' tem 7 dígitos: o zero da frente sumiu (comum quando a planilha passa pelo Excel). "
                f"Com o zero, {fmt_ncm(certo)} existe: {tabela.curta(certo)}.",
                f"Corrija o NCM no cadastro para {fmt_ncm(certo)} e deixe a coluna de NCM como texto na planilha.",
                ncm_sugerido=certo,
            )
        ]
    return [
        Achado(
            "NCM_AUSENTE",
            VERMELHO,
            f"NCM '{ncm or ''}' não tem 8 dígitos.",
            "Corrija o NCM no cadastro do produto antes da próxima nota.",
        )
    ]


def _hoje_no_grupo(ncm: str, tabela) -> str:
    grupo = codigos_do_grupo(ncm, tabela)
    if not grupo:
        return ""
    mostra = ", ".join(fmt_ncm(c) for c in grupo[:4]) + (f" e mais {len(grupo) - 4}" if len(grupo) > 4 else "")
    return f" No mesmo grupo, hoje existem: {mostra}."


def regra_ncm_tabela(ncm: str, data_nota: date | None, historico) -> list[Achado]:
    """NCM inexistente / fora de vigência, comparando com a tabela que valia na data da nota."""
    if not _NCM_RE.match(ncm or "") or ncm == "00000000":
        return []
    atual = historico.atual
    da_data = historico.na_data(data_nota)
    if da_data is not None:
        if not da_data.existe(ncm):
            return [
                Achado(
                    "NCM_INEXISTENTE",
                    VERMELHO,
                    f"O NCM {fmt_ncm(ncm)} não existe na tabela oficial que valia em {fmt_data(data_nota)} "
                    f"(tabela de {fmt_data(da_data.desde)}, {da_data.ato}).{_hoje_no_grupo(ncm, da_data)}",
                    "Troque pelo NCM correto no cadastro (veja a sugestão) e confira se a nota precisa de correção.",
                )
            ]
        ini = da_data.inicio(ncm)
        if ini and data_nota and ini > data_nota:
            return [
                Achado(
                    "NCM_VIGENCIA",
                    AMARELO,
                    f"O texto oficial do NCM {fmt_ncm(ncm)} começou a valer em {fmt_data(ini)}, "
                    f"depois da nota ({fmt_data(data_nota)}).",
                    "Confira se o código valia na data da nota.",
                )
            ]
        return []
    # Nota mais antiga que a primeira tabela guardada: só dá para comparar com a de hoje.
    if not atual.existe(ncm):
        return [
            Achado(
                "NCM_INEXISTENTE",
                AMARELO,
                f"O NCM {fmt_ncm(ncm)} não existe na tabela de hoje ({atual.vigente_em or fmt_data(atual.desde)}). "
                f"A nota é de {fmt_data(data_nota)}: o código pode ter valido naquela época."
                f"{_hoje_no_grupo(ncm, atual)}",
                "Corrija o cadastro para as próximas notas (veja a sugestão).",
            )
        ]
    ini = atual.inicio(ncm)
    if ini and data_nota and ini > data_nota:
        return [
            Achado(
                "NCM_VIGENCIA",
                AMARELO,
                f"O texto oficial do NCM {fmt_ncm(ncm)} começou a valer em {fmt_data(ini)}, "
                f"depois da nota ({fmt_data(data_nota)}).",
                "Confira se o código valia na data da nota.",
            )
        ]
    return []


# Medidos em 08/11/2026 na amostra pública (50.000 itens de 2025-09): juntos, marcam mais 1,6% dos
# itens; em 43% deles quase ninguém usa aquele NCM para aquela descrição (provável erro real) e em
# menos de 5% o NCM da nota é o de sempre (provável alarme falso). Ver reports/produto_amostra_publica.md.
LIMIAR_OUTRO_CAPITULO = 0.60
LIMIAR_OUTRA_POSICAO = 0.75


def regra_ncm_modelo(
    ncm: str,
    descricao: str,
    sugestoes: list[tuple[str, float]],
    tabela,
    limiar_vermelho: float,
    limiar_amarelo: float,
) -> list[Achado]:
    """Compara o NCM declarado com o que o modelo lê na descrição (top-10 já filtrado pela tabela).

    - vermelho: o modelo tem confiança >= limiar da auditoria (0,99) num NCM diferente;
    - amarelo: o NCM da nota está fora dos 5 mais prováveis e o modelo tem >= 0,90;
    - amarelo: o NCM da nota nem aparece entre os 10 mais prováveis e é de OUTRO CAPÍTULO (modelo
      >= 0,60) ou de OUTRA POSIÇÃO de 4 dígitos (modelo >= 0,75): o caso típico do NCM copiado de
      outro produto no cadastro.
    """
    if not sugestoes or not _NCM_RE.match(ncm or ""):
        return []
    top1, p1 = sugestoes[0]
    if top1 == ncm:
        return []
    top5 = {c for c, _ in sugestoes[:5]}
    top10 = {c for c, _ in sugestoes[:10]}
    desc_top = tabela.curta(top1) or "sem descrição oficial"
    desc_decl = tabela.curta(ncm) or "código fora da tabela"
    if p1 >= limiar_vermelho:
        nivel = VERMELHO
        motivo = (
            f"A descrição parece ser do NCM {fmt_ncm(top1)} ({desc_top}), com {p1:.0%} de confiança. "
            f"O NCM da nota, {fmt_ncm(ncm)}, é: {desc_decl}."
        )
        acao = f"Confira o produto. Se for o que a descrição diz, corrija o NCM no cadastro para {fmt_ncm(top1)}."
    elif ncm not in top5 and p1 >= limiar_amarelo:
        nivel = AMARELO
        motivo = (
            f"O NCM {fmt_ncm(ncm)} ({desc_decl}) não aparece entre os 5 mais prováveis para esta descrição. "
            f"O mais provável é {fmt_ncm(top1)} ({desc_top}), {p1:.0%}."
        )
        acao = "Confira o produto e o NCM no cadastro."
    elif ncm not in top10 and (
        (p1 >= LIMIAR_OUTRO_CAPITULO and ncm[:2] != top1[:2]) or (p1 >= LIMIAR_OUTRA_POSICAO and ncm[:4] != top1[:4])
    ):
        nivel = AMARELO
        onde = "outro capítulo" if ncm[:2] != top1[:2] else "outra posição"
        motivo = (
            f"O NCM {fmt_ncm(ncm)} ({desc_decl}) é de {onde} da tabela e nem aparece entre os 10 mais "
            f"prováveis para esta descrição. O mais provável é {fmt_ncm(top1)} ({desc_top}), {p1:.0%}."
        )
        acao = "Parece NCM copiado de outro produto. Confira o cadastro."
    else:
        return []
    return [Achado("NCM_MODELO", nivel, motivo, acao, ncm_sugerido=top1)]


# ---------------------------------------------------------------------------------------------
# CFOP
# ---------------------------------------------------------------------------------------------


def ambito_da_nota(emit_uf: str | None, dest_uf: str | None, id_dest: str | None, modelo: str | None) -> str | None:
    if (dest_uf or "").upper() == "EX" or id_dest == "3":
        return "exterior"
    if modelo == "65":
        return "interna"  # NFC-e é sempre operação interna
    if emit_uf and dest_uf:
        return "interna" if emit_uf.upper() == dest_uf.upper() else "interestadual"
    if id_dest in ("1", "2"):
        return AMBITO[id_dest]
    return None


def regra_cfop(
    cfop: str,
    tp_nf: str | None,
    emit_uf: str | None,
    dest_uf: str | None,
    id_dest: str | None,
    ind_pres: str | None,
    modelo: str | None,
    cfops_conhecidos: set[str] | None = None,
) -> list[Achado]:
    if not _CFOP_RE.match(cfop or ""):
        return [
            Achado(
                "CFOP_INVALIDO",
                VERMELHO,
                f"CFOP '{cfop or ''}' fora do formato (4 dígitos, começando por 1, 2, 3, 5, 6 ou 7).",
                "Corrija o CFOP.",
            )
        ]
    d = cfop[0]
    if tp_nf == "1" and d in "123":
        return [
            Achado(
                "CFOP_SENTIDO",
                VERMELHO,
                f"Nota de saída com CFOP de entrada ({cfop}).",
                "Notas de saída usam CFOP 5, 6 ou 7. Confira a natureza da operação.",
            )
        ]
    if tp_nf == "0" and d in "567":
        return [
            Achado(
                "CFOP_SENTIDO",
                VERMELHO,
                f"Nota de entrada com CFOP de saída ({cfop}).",
                "Notas de entrada usam CFOP 1, 2 ou 3. Confira a natureza da operação.",
            )
        ]
    ambito = ambito_da_nota(emit_uf, dest_uf, id_dest, modelo)
    if ambito is None or AMBITO[d] == ambito:
        return []
    rota = f"de {emit_uf or '?'} para {dest_uf or '?'}"
    if ambito == "interestadual" and AMBITO[d] == "interna" and ind_pres == "1":
        return [
            Achado(
                "CFOP_UF",
                VERDE,
                f"CFOP {cfop} (dentro do estado) numa nota {rota}, mas a venda foi presencial: "
                "nesse caso a operação conta como interna.",
                "Nada a fazer.",
            )
        ]
    sentido = tp_nf if tp_nf in ("0", "1") else ("1" if d in "567" else "0")
    novo_d = DIGITO[(sentido, ambito)]
    sugerido = novo_d + cfop[1:]
    if cfops_conhecidos is not None and sugerido not in cfops_conhecidos:
        sugerido = None
    nome = {"interna": "dentro do estado", "interestadual": "entre estados", "exterior": "com o exterior"}
    acao = (
        f"Se não for um caso especial, o CFOP seria {sugerido}."
        if sugerido
        else f"Se não for um caso especial, use o CFOP equivalente {nome[ambito]} ({novo_d}.xxx)."
    )
    return [
        Achado(
            "CFOP_UF",
            AMARELO,
            f"CFOP {cfop} é de operação {nome[AMBITO[d]]} ({d}.xxx), mas a nota vai {rota} (operação {nome[ambito]}).",
            acao + " Pode ser de propósito: nesse caso, cadastre na regra do escritório.",
            cfop_sugerido=sugerido,
        )
    ]


# ---------------------------------------------------------------------------------------------
# CST x regime, GTIN
# ---------------------------------------------------------------------------------------------


def regra_cst_regime(crt: str | None, cst: str | None, csosn: str | None) -> list[Achado]:
    if crt in ("1", "4") and cst and not csosn:
        return [
            Achado(
                "CST_REGIME",
                VERMELHO,
                f"Empresa do Simples Nacional (CRT {crt}) usando CST {cst}, que é de regime normal.",
                "No Simples o ICMS usa CSOSN (101, 102, 500...). Corrija a tributação do produto.",
            )
        ]
    if crt in ("2", "3") and csosn and not cst:
        return [
            Achado(
                "CST_REGIME",
                VERMELHO,
                f"Empresa de regime normal (CRT {crt}) usando CSOSN {csosn}, que é do Simples.",
                "No regime normal o ICMS usa CST (00, 20, 60...). Corrija a tributação do produto.",
            )
        ]
    return []


def gtin_valido(gtin: str) -> bool:
    if not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        return False
    digitos = [int(c) for c in gtin]
    corpo, dv = digitos[:-1], digitos[-1]
    soma = sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10 == dv


def regra_gtin(gtin: str | None) -> list[Achado]:
    if not gtin or gtin_valido(gtin):
        return []
    return [
        Achado(
            "GTIN_INVALIDO",
            AMARELO,
            f"Código de barras {gtin} inválido (tamanho ou dígito verificador).",
            "Confira o GTIN/EAN no cadastro, ou use 'SEM GTIN' se o produto não tem código de barras.",
        )
    ]


# ---------------------------------------------------------------------------------------------
# Regra do escritório
# ---------------------------------------------------------------------------------------------

COLUNAS_EXCECAO = ["cnpj_empresa", "regra", "cfop", "ncm", "codigo_produto", "motivo"]


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


@dataclass
class Excecao:
    cnpj_empresa: str = ""
    regra: str = ""
    cfop: str = ""
    ncm: str = ""
    codigo_produto: str = ""
    motivo: str = ""

    def casa(self, regra: str, empresa: str | None, emit: str | None, cfop: str, ncm: str, codigo: str) -> bool:
        if self.regra and self.regra.upper() != regra:
            return False
        if self.cnpj_empresa and self.cnpj_empresa not in (empresa or "", emit or ""):
            return False
        if self.cfop and self.cfop != cfop:
            return False
        if self.ncm and self.ncm != ncm:
            return False
        return not (self.codigo_produto and self.codigo_produto != codigo)


@dataclass
class RegrasDoEscritorio:
    excecoes: list[Excecao] = field(default_factory=list)
    origem: str = ""

    @classmethod
    def ler(cls, path: Path | None) -> RegrasDoEscritorio:
        if path is None or not Path(path).exists():
            return cls()
        texto = Path(path).read_text(encoding="utf-8-sig")
        return cls.de_texto(texto, str(path))

    @classmethod
    def de_texto(cls, texto: str, origem: str = "") -> RegrasDoEscritorio:
        linhas = [ln for ln in texto.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        if not linhas:
            return cls(origem=origem)
        sep = ";" if linhas[0].count(";") >= linhas[0].count(",") else ","
        out = []
        for row in csv.DictReader(io.StringIO("\n".join(linhas)), delimiter=sep):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not any(row.get(c) for c in COLUNAS_EXCECAO[:-1]):
                continue
            out.append(
                Excecao(
                    cnpj_empresa=_so_digitos(row.get("cnpj_empresa")),
                    regra=row.get("regra", "").upper(),
                    cfop=_so_digitos(row.get("cfop")),
                    ncm=_so_digitos(row.get("ncm")),
                    codigo_produto=row.get("codigo_produto", ""),
                    motivo=row.get("motivo", "") or "aceito pelo escritório",
                )
            )
        return cls(out, origem)

    def aplicar(self, achados: list[Achado], empresa, emit, cfop, ncm, codigo) -> None:
        for a in achados:
            if a.nivel == VERDE:
                continue
            for e in self.excecoes:
                if e.casa(a.regra, empresa, emit, cfop, ncm, codigo):
                    a.aceito = e.motivo
                    break


MODELO_CSV_EXCECOES = (
    "# Regra do escritório: o que está certo de propósito. Uma linha por exceção; vazio = qualquer.\n"
    "# regra: CFOP_UF, NCM_MODELO, NCM_INEXISTENTE, PRODUTO_NCM_DIVERGENTE, GTIN_INVALIDO...\n"
    "cnpj_empresa;regra;cfop;ncm;codigo_produto;motivo\n"
    "11222333000181;CFOP_UF;5102;;;Venda presencial no balcão para cliente de outro estado\n"
)
