"""Tabela NCM oficial (Siscomex / Portal Único) e o robô que confere a atualização.

A tabela oficial em JSON só traz os códigos **vigentes hoje** (todos com `Data_Fim` 31/12/9999).
Por isso a história precisa ser guardada por nós: cada vez que o robô roda ele baixa a tabela,
tira um hash (sha256) do conteúdo e compara com a última versão guardada.

- mudou: grava a versão nova em `data/ncm/versoes/ncm_<AAAA-MM-DD>_<hash8>.json.gz`;
- não mudou: só escreve uma linha "sem mudança" no registro, para provar que rodou;
- erro (site fora, arquivo estranho): escreve "erro" e sai com código 2.

O hash ignora o campo `Data_Ultima_Atualizacao_NCM` ("Vigente em dd/mm/aaaa"), que muda todo dia
mesmo quando nenhum código muda.

Uma cópia da tabela de 07/11/2026 vai junto no pacote (`seeds/`), para o Raio-X funcionar logo
depois do `git clone`, sem internet. A versão mais nova em `data/ncm/versoes/` sempre ganha.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import logging
import re
import time
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

URL_SISCOMEX = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO"
SEED = Path(__file__).resolve().parents[1] / "seeds" / "ncm_siscomex_2026-11-07.json.gz"
SEED_DESDE = date(2026, 11, 7)
MIN_CODIGOS_8 = 9_000  # abaixo disso o arquivo baixado está incompleto: vira "erro", não "mudou"

REGISTRO_CAMPOS = [
    "data_hora",
    "resultado",
    "vigente_em",
    "ato",
    "hash",
    "codigos_8_digitos",
    "entraram",
    "sairam",
    "descricao_mudou",
    "arquivo",
    "detalhe",
]


def _digitos(codigo: str) -> str:
    return codigo.replace(".", "").strip()


def _data_br(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


_TAG = re.compile(r"<[^>]+>")
GENERICOS = {"outros", "outras", "outro", "outra", "os demais", "as demais", "outros(as)"}


def _limpa(desc: str) -> str:
    return _TAG.sub("", desc).lstrip("- ").strip().rstrip(":").strip()


def _corta(s: str, n: int = 60) -> str:
    if len(s) <= n:
        return s
    corte = s[:n].rsplit(" ", 1)[0].rstrip(",;.")
    return corte + "…"


def descricao_curta(cadeia: list[str]) -> str:
    """Os últimos trechos que dizem alguma coisa (+ '› Outros' quando a folha é genérica)."""
    uteis = [c for c in cadeia if c.lower().rstrip(".") not in GENERICOS]
    partes: list[str] = []
    for c in reversed(uteis):  # do mais específico para o mais geral, até ter ~25 letras de contexto
        partes.insert(0, _corta(c))
        if len(partes) >= 3 or (len(partes) >= 2 and sum(len(x) for x in partes) >= 25):
            break
    if cadeia and cadeia[-1].lower().rstrip(".") in GENERICOS:
        partes.append(cadeia[-1])
    return " › ".join(partes)


@dataclass
class TabelaNCM:
    """Uma versão da tabela: códigos de 8 dígitos com descrição oficial e início de vigência."""

    vigente_em: str
    ato: str
    desde: date
    folhas: dict[str, dict] = field(default_factory=dict)  # '01012100' -> {descricao, inicio, completa}
    niveis: dict[str, str] = field(default_factory=dict)  # '0101', '01012', '010121' ... -> descrição
    hash: str = ""

    @classmethod
    def from_json(cls, data: dict, desde: date) -> TabelaNCM:
        niveis: dict[str, str] = {}
        brutas: list[dict] = []
        for n in data.get("Nomenclaturas", []):
            cod = _digitos(n.get("Codigo", ""))
            if not cod.isdigit():
                continue
            if len(cod) == 8:
                brutas.append(n)
            niveis[cod] = n.get("Descricao", "").strip()
        folhas = {}
        for n in brutas:
            cod = _digitos(n["Codigo"])
            cadeia = []
            for k in (4, 5, 6, 7):
                d = niveis.get(cod[:k])
                if d:
                    cadeia.append(_limpa(d))
            folha = _limpa(n.get("Descricao", ""))
            cadeia.append(folha)
            cadeia = list(dict.fromkeys(c for c in cadeia if c))
            folhas[cod] = {
                "descricao": folha,
                "completa": " › ".join(cadeia),
                "curta": descricao_curta(cadeia),
                "inicio": _data_br(n.get("Data_Inicio")),
            }
        return cls(
            vigente_em=str(data.get("Data_Ultima_Atualizacao_NCM", "")).replace("Vigente em", "").strip(),
            ato=str(data.get("Ato", "")).strip(),
            desde=desde,
            folhas=folhas,
            niveis=niveis,
            hash=hash_conteudo(data),
        )

    @classmethod
    def from_file(cls, path: Path, desde: date) -> TabelaNCM:
        return cls.from_json(ler_json(path), desde)

    def existe(self, ncm: str | None) -> bool:
        return bool(ncm) and ncm in self.folhas

    def descricao(self, ncm: str | None, completa: bool = True) -> str:
        f = self.folhas.get(ncm or "")
        if not f:
            return ""
        return f["completa"] if completa else f["descricao"]

    def curta(self, ncm: str | None) -> str:
        f = self.folhas.get(ncm or "")
        return f["curta"] if f else ""

    def inicio(self, ncm: str) -> date | None:
        f = self.folhas.get(ncm)
        return f["inicio"] if f else None

    def __len__(self) -> int:
        return len(self.folhas)


def ler_json(path: Path) -> dict:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8-sig"))


def hash_conteudo(data: dict) -> str:
    """sha256 do que importa (códigos, descrições, datas e ato), ignorando o 'Vigente em' do dia."""
    nomes = sorted(data.get("Nomenclaturas", []), key=lambda n: n.get("Codigo", ""))
    canon = json.dumps({"ato": data.get("Ato"), "n": nomes}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# Histórico de versões (qual tabela valia na data da nota)
# ---------------------------------------------------------------------------------------------


def pasta_ncm(data_dir: Path) -> Path:
    return data_dir / "ncm"


def _versoes_salvas(data_dir: Path) -> list[tuple[date, Path]]:
    pasta = pasta_ncm(data_dir) / "versoes"
    out = []
    for p in sorted(pasta.glob("ncm_*.json.gz")) if pasta.exists() else []:
        try:
            out.append((datetime.strptime(p.name.split("_")[1], "%Y-%m-%d").date(), p))
        except (IndexError, ValueError):
            continue
    return out


@dataclass
class HistoricoNCM:
    """Versões em ordem de data. `na_data(d)` devolve a versão que valia em d (ou None se d é
    anterior à primeira versão que temos guardada)."""

    versoes: list[TabelaNCM]

    @classmethod
    def carregar(cls, data_dir: Path | None) -> HistoricoNCM:
        versoes: list[TabelaNCM] = []
        salvas = _versoes_salvas(data_dir) if data_dir else []
        if not salvas or salvas[0][0] > SEED_DESDE:
            versoes.append(TabelaNCM.from_file(SEED, SEED_DESDE))
        for desde, p in salvas:
            t = TabelaNCM.from_file(p, desde)
            if versoes and versoes[-1].hash == t.hash:
                continue
            versoes.append(t)
        versoes.sort(key=lambda t: t.desde)
        return cls(versoes)

    @property
    def atual(self) -> TabelaNCM:
        return self.versoes[-1]

    @property
    def primeira_data(self) -> date:
        return self.versoes[0].desde

    def na_data(self, d: date | None) -> TabelaNCM | None:
        if d is None:
            return self.atual
        i = bisect_right([t.desde for t in self.versoes], d)
        return self.versoes[i - 1] if i > 0 else None


# ---------------------------------------------------------------------------------------------
# Robô de atualização (rodar uma vez por dia; o agendamento fica com quem opera o servidor)
# ---------------------------------------------------------------------------------------------


def baixar_siscomex(url: str = URL_SISCOMEX, tentativas: int = 3, timeout: int = 60) -> dict:
    import requests

    erro: Exception | None = None
    for i in range(tentativas):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "raio-x-fiscal/0.2 (tabela NCM)"})
            r.raise_for_status()
            return json.loads(r.content.decode("utf-8-sig"))
        except Exception as e:  # noqa: BLE001 - qualquer falha de rede vira nova tentativa
            erro = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"não consegui baixar a tabela NCM: {erro}")


def _diferenca(antiga: TabelaNCM | None, nova: TabelaNCM) -> tuple[int, int, int]:
    if antiga is None:
        return len(nova.folhas), 0, 0
    a, b = set(antiga.folhas), set(nova.folhas)
    mudou = sum(1 for c in a & b if antiga.folhas[c]["completa"] != nova.folhas[c]["completa"])
    return len(b - a), len(a - b), mudou


def _escreve_registro(data_dir: Path, linha: dict) -> Path:
    reg = pasta_ncm(data_dir) / "registro.csv"
    reg.parent.mkdir(parents=True, exist_ok=True)
    novo = not reg.exists()
    with reg.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTRO_CAMPOS, delimiter=";")
        if novo:
            w.writeheader()
        w.writerow({k: linha.get(k, "") for k in REGISTRO_CAMPOS})
    return reg


def atualizar_tabela(
    data_dir: Path,
    baixar: Callable[[], dict] = baixar_siscomex,
    agora: datetime | None = None,
) -> dict:
    """Baixa, compara e registra. Devolve a linha gravada no registro (com 'resultado')."""
    agora = agora or datetime.now()
    linha: dict = {"data_hora": agora.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        data = baixar()
        if not isinstance(data, dict) or "Nomenclaturas" not in data:
            raise ValueError("arquivo sem a lista 'Nomenclaturas'")
        nova = TabelaNCM.from_json(data, agora.date())
        if len(nova) < MIN_CODIGOS_8:
            raise ValueError(f"só {len(nova)} códigos de 8 dígitos (esperado mais de {MIN_CODIGOS_8})")
    except Exception as e:  # noqa: BLE001
        linha.update(resultado="erro", detalhe=str(e)[:300])
        _escreve_registro(data_dir, linha)
        log.error("tabela NCM: erro: %s", e)
        return linha

    salvas = _versoes_salvas(data_dir)
    ultima, desde = (salvas[-1][1], salvas[-1][0]) if salvas else (SEED, SEED_DESDE)
    anterior = TabelaNCM.from_file(ultima, desde)
    linha.update(
        vigente_em=nova.vigente_em,
        ato=nova.ato,
        hash=nova.hash[:16],
        codigos_8_digitos=len(nova),
    )
    if salvas and anterior.hash == nova.hash:
        linha.update(resultado="sem mudança", entraram=0, sairam=0, descricao_mudou=0)
    else:
        entraram, sairam, mudou = _diferenca(anterior, nova)
        destino = pasta_ncm(data_dir) / "versoes" / f"ncm_{agora:%Y-%m-%d}_{nova.hash[:8]}.json.gz"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8"), 9))
        if not salvas and anterior.hash == nova.hash:
            resultado = "primeira versão guardada (igual à cópia do pacote)"
        elif not salvas:
            resultado = "primeira versão guardada (mudou desde a cópia do pacote)"
        else:
            resultado = "mudou"
        linha.update(
            resultado=resultado,
            entraram=entraram,
            sairam=sairam,
            descricao_mudou=mudou,
            arquivo=destino.name,
        )
    _escreve_registro(data_dir, linha)
    log.info("tabela NCM: %s (vigente em %s, %s)", linha["resultado"], nova.vigente_em, nova.ato)
    return linha
