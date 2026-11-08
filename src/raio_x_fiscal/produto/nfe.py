"""Leitura de XML de NF-e / NFC-e (modelos 55 e 65): arquivo solto, pasta, .zip ou .zip dentro de pasta.

Porta 1 do Raio-X: a pessoa arrasta as notas do mês. Cada subpasta (ou cada .zip na raiz) vira
um "grupo", que normalmente é uma empresa cliente: `entrada-local/<empresa>/*.xml`. Sem subpasta,
o grupo é o emitente da nota.

Segurança (as notas são de clientes e nunca saem da máquina):
- nada é enviado para fora; só leitura local;
- XML com DOCTYPE/ENTITY é recusado (NF-e nunca tem; evita "bomba" de entidades);
- limites de tamanho por arquivo, de arquivos por lote e do total descompactado dos .zip;
- caminhos dentro do .zip são tratados como nomes, nunca extraídos para o disco.
"""

from __future__ import annotations

import io
import logging
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

NS = "{http://www.portalfiscal.inf.br/nfe}"
MAX_XML_BYTES = 5 * 1024 * 1024
MAX_ARQUIVOS = 20_000
MAX_ZIP_TOTAL = 1024 * 1024 * 1024  # 1 GB descompactado por lote
CANCELAMENTO = "110111"


@dataclass
class Item:
    n_item: int
    codigo: str
    gtin: str | None
    descricao: str
    ncm: str
    cest: str | None
    cfop: str
    unidade: str
    quantidade: float
    valor_unitario: float
    valor_total: float
    cst: str | None = None  # CST do ICMS (regime normal)
    csosn: str | None = None  # CSOSN (Simples Nacional)
    origem: str | None = None
    servico: bool = False


@dataclass
class Nota:
    arquivo: str
    grupo: str | None
    chave: str
    modelo: str
    serie: str
    numero: str
    data_emissao: date | None
    natureza: str
    tp_nf: str  # 0 entrada, 1 saída (do ponto de vista de quem emitiu)
    id_dest: str | None  # 1 interna, 2 interestadual, 3 exterior
    ind_pres: str | None
    ind_final: str | None
    fin_nfe: str | None
    emit_cnpj: str
    emit_nome: str
    emit_uf: str
    crt: str | None
    dest_doc: str | None
    dest_nome: str | None
    dest_uf: str | None
    valor_total: float
    itens: list[Item] = field(default_factory=list)
    cancelada: bool = False


@dataclass
class Leitura:
    notas: list[Nota] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    cancelamentos: set[str] = field(default_factory=set)
    arquivos_lidos: int = 0


def _q(path: str) -> str:
    return "/".join(NS + p for p in path.split("/"))


def _txt(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    f = el.find(_q(path))
    return f.text.strip() if f is not None and f.text else None


def _num(s: str | None) -> float:
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _data(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.strip()[:10]).date()
    except ValueError:
        return None


def _seguro(raw: bytes) -> bool:
    cabeca = raw[:4096].upper()
    return b"<!DOCTYPE" not in cabeca and b"<!ENTITY" not in raw.upper()


def _item(det: ET.Element) -> Item:
    prod = det.find(_q("prod"))
    imp = det.find(_q("imposto"))
    cst = csosn = origem = None
    icms = imp.find(_q("ICMS")) if imp is not None else None
    if icms is not None and len(icms):
        grupo = icms[0]
        cst = _txt(grupo, "CST")
        csosn = _txt(grupo, "CSOSN")
        origem = _txt(grupo, "orig")
    servico = imp is not None and imp.find(_q("ISSQN")) is not None
    gtin = _txt(prod, "cEAN")
    if gtin and gtin.upper().startswith("SEM GTIN"):
        gtin = None
    return Item(
        n_item=int(det.get("nItem", "0") or 0),
        codigo=_txt(prod, "cProd") or "",
        gtin=gtin,
        descricao=_txt(prod, "xProd") or "",
        ncm=(_txt(prod, "NCM") or "").strip(),
        cest=_txt(prod, "CEST"),
        cfop=(_txt(prod, "CFOP") or "").strip(),
        unidade=_txt(prod, "uCom") or "",
        quantidade=_num(_txt(prod, "qCom")),
        valor_unitario=_num(_txt(prod, "vUnCom")),
        valor_total=_num(_txt(prod, "vProd")),
        cst=cst,
        csosn=csosn,
        origem=origem,
        servico=servico,
    )


def parse_xml(raw: bytes, arquivo: str, grupo: str | None) -> tuple[Nota | None, str | None, str | None]:
    """Devolve (nota, chave_cancelada, aviso). Só um dos três costuma vir preenchido."""
    if len(raw) > MAX_XML_BYTES:
        return None, None, f"{arquivo}: maior que 5 MB, ignorado"
    if not _seguro(raw):
        return None, None, f"{arquivo}: XML com DOCTYPE/ENTITY, recusado por segurança"
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return None, None, f"{arquivo}: não é um XML válido ({e})"

    tag = root.tag.replace(NS, "")
    if tag in ("procEventoNFe", "evento", "retEnvEvento"):
        inf = root.find(".//" + NS + "infEvento")
        if inf is not None and _txt(inf, "tpEvento") == CANCELAMENTO:
            return None, _txt(inf, "chNFe"), None
        return None, None, None  # carta de correção e outros eventos: não são notas
    inf = root.find(".//" + NS + "infNFe")
    if inf is None:
        return None, None, f"{arquivo}: não parece uma NF-e (sem infNFe)"

    ide = inf.find(_q("ide"))
    emit = inf.find(_q("emit"))
    dest = inf.find(_q("dest"))
    chave = (inf.get("Id") or "").replace("NFe", "")
    prot = root.find(".//" + NS + "chNFe")
    if prot is not None and prot.text:
        chave = prot.text.strip()
    dest_uf = _txt(dest, "enderDest/UF") if dest is not None else None
    nota = Nota(
        arquivo=arquivo,
        grupo=grupo,
        chave=chave,
        modelo=_txt(ide, "mod") or "",
        serie=_txt(ide, "serie") or "",
        numero=_txt(ide, "nNF") or "",
        data_emissao=_data(_txt(ide, "dhEmi") or _txt(ide, "dEmi")),
        natureza=_txt(ide, "natOp") or "",
        tp_nf=_txt(ide, "tpNF") or "",
        id_dest=_txt(ide, "idDest"),
        ind_pres=_txt(ide, "indPres"),
        ind_final=_txt(ide, "indFinal"),
        fin_nfe=_txt(ide, "finNFe"),
        emit_cnpj=_txt(emit, "CNPJ") or _txt(emit, "CPF") or "",
        emit_nome=_txt(emit, "xNome") or "",
        emit_uf=_txt(emit, "enderEmit/UF") or "",
        crt=_txt(emit, "CRT"),
        dest_doc=(_txt(dest, "CNPJ") or _txt(dest, "CPF") or _txt(dest, "idEstrangeiro")) if dest is not None else None,
        dest_nome=_txt(dest, "xNome") if dest is not None else None,
        dest_uf=dest_uf,
        valor_total=_num(_txt(inf, "total/ICMSTot/vNF")),
    )
    nota.itens = [_item(det) for det in inf.findall(_q("det"))]
    return nota, None, None


def _arquivos(raiz: Path) -> Iterator[tuple[str, str | None, bytes]]:
    """(nome, grupo, bytes) de cada XML encontrado, abrindo .zip (e .zip dentro de .zip, 1 nível)."""
    raiz = raiz.resolve()

    def de_zip(data: bytes, nome_zip: str, grupo: str | None, nivel: int, total: list[int]):
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            yield nome_zip, grupo, b"__ZIP_INVALIDO__"
            return
        for info in zf.infolist():
            if info.is_dir():
                continue
            total[0] += info.file_size
            if total[0] > MAX_ZIP_TOTAL:
                yield nome_zip, grupo, b"__ZIP_GRANDE__"
                return
            nome = f"{nome_zip}/{info.filename}"
            low = info.filename.lower()
            if low.endswith(".xml"):
                if info.file_size > MAX_XML_BYTES:
                    yield nome, grupo, b"__XML_GRANDE__"
                    continue
                yield nome, grupo, zf.read(info)
            elif low.endswith(".zip") and nivel < 2:
                yield from de_zip(zf.read(info), nome, grupo, nivel + 1, total)

    total = [0]
    if raiz.is_file():
        itens = [raiz]
        base = raiz.parent
    else:
        itens = sorted(p for p in raiz.rglob("*") if p.is_file())
        base = raiz
    for p in itens:
        rel = PurePosixPath(p.relative_to(base).as_posix())
        if any(part.startswith(".") for part in rel.parts):
            continue
        grupo = rel.parts[0] if len(rel.parts) > 1 else None
        low = p.name.lower()
        if low.endswith(".xml"):
            if p.stat().st_size > MAX_XML_BYTES:
                yield str(rel), grupo, b"__XML_GRANDE__"
                continue
            yield str(rel), grupo, p.read_bytes()
        elif low.endswith(".zip"):
            yield from de_zip(p.read_bytes(), str(rel), grupo or p.stem, 1, total)


ESPECIAIS = {
    b"__ZIP_INVALIDO__": "arquivo .zip corrompido ou não é zip",
    b"__ZIP_GRANDE__": "zip passa de 1 GB descompactado; parei de ler aqui",
    b"__XML_GRANDE__": "maior que 5 MB, ignorado",
}


def ler_entrada(caminho: Path) -> Leitura:
    """Lê tudo o que for XML de NF-e no caminho (arquivo, pasta ou zip)."""
    leitura = Leitura()
    vistos: set[str] = set()
    for nome, grupo, raw in _arquivos(Path(caminho)):
        if raw in ESPECIAIS:
            leitura.avisos.append(f"{nome}: {ESPECIAIS[raw]}")
            continue
        leitura.arquivos_lidos += 1
        if leitura.arquivos_lidos > MAX_ARQUIVOS:
            leitura.avisos.append(f"mais de {MAX_ARQUIVOS} arquivos: o resto foi ignorado")
            break
        nota, cancelada, aviso = parse_xml(raw, nome, grupo)
        if aviso:
            leitura.avisos.append(aviso)
        if cancelada:
            leitura.cancelamentos.add(cancelada)
        if nota is not None:
            if nota.chave and nota.chave in vistos:
                leitura.avisos.append(f"{nome}: nota repetida (mesma chave), contada uma vez")
                continue
            vistos.add(nota.chave)
            leitura.notas.append(nota)
    for n in leitura.notas:
        n.cancelada = n.chave in leitura.cancelamentos
    return leitura


def empresa_do_grupo(notas: list[Nota]) -> str | None:
    """CNPJ que mais aparece (como emitente ou destinatário) nas notas do grupo."""
    c: Counter[str] = Counter()
    for n in notas:
        if n.emit_cnpj:
            c[n.emit_cnpj] += 1
        if n.dest_doc:
            c[n.dest_doc] += 1
    if not c:
        return None
    top, qtd = c.most_common(1)[0]
    return top if qtd >= max(1, len(notas) // 2) else None
