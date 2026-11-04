"""Schema contract of the Portal da Transparencia NF-e CSVs.

The raw header is the contract with the source: bronze refuses a file whose header differs
(schema drift is a loud failure, not a silent one). The snake_case names are what silver uses.
"""

from __future__ import annotations

# (raw header as published by CGU, snake_case name used from silver on)
NOTA_COLUMNS: list[tuple[str, str]] = [
    ("CHAVE DE ACESSO", "chave_acesso"),
    ("MODELO", "modelo"),
    ("SÉRIE", "serie"),
    ("NÚMERO", "numero_nota"),
    ("NATUREZA DA OPERAÇÃO", "natureza_operacao"),
    ("DATA EMISSÃO", "data_emissao"),
    ("EVENTO MAIS RECENTE", "evento_mais_recente"),
    ("DATA/HORA EVENTO MAIS RECENTE", "data_hora_evento_mais_recente"),
    ("CPF/CNPJ Emitente", "emitente_cpf_cnpj"),
    ("RAZÃO SOCIAL EMITENTE", "emitente_razao_social"),
    ("INSCRIÇÃO ESTADUAL EMITENTE", "emitente_ie"),
    ("UF EMITENTE", "emitente_uf"),
    ("MUNICÍPIO EMITENTE", "emitente_municipio"),
    ("CÓDIGO ÓRGÃO SUPERIOR DESTINATÁRIO", "orgao_superior_codigo"),
    ("ÓRGÃO SUPERIOR DESTINATÁRIO", "orgao_superior_nome"),
    ("CÓDIGO ÓRGÃO DESTINATÁRIO", "orgao_codigo"),
    ("ÓRGÃO DESTINATÁRIO", "orgao_nome"),
    ("CNPJ DESTINATÁRIO", "destinatario_cnpj"),
    ("NOME DESTINATÁRIO", "destinatario_nome"),
    ("UF DESTINATÁRIO", "destinatario_uf"),
    ("INDICADOR IE DESTINATÁRIO", "indicador_ie_destinatario"),
    ("DESTINO DA OPERAÇÃO", "destino_operacao"),
    ("CONSUMIDOR FINAL", "consumidor_final"),
    ("PRESENÇA DO COMPRADOR", "presenca_comprador"),
    ("VALOR NOTA FISCAL", "valor_nota"),
]

ITEM_COLUMNS: list[tuple[str, str]] = [
    ("CHAVE DE ACESSO", "chave_acesso"),
    ("MODELO", "modelo"),
    ("SÉRIE", "serie"),
    ("NÚMERO", "numero_nota"),
    ("NATUREZA DA OPERAÇÃO", "natureza_operacao"),
    ("DATA EMISSÃO", "data_emissao"),
    ("CPF/CNPJ Emitente", "emitente_cpf_cnpj"),
    ("RAZÃO SOCIAL EMITENTE", "emitente_razao_social"),
    ("INSCRIÇÃO ESTADUAL EMITENTE", "emitente_ie"),
    ("UF EMITENTE", "emitente_uf"),
    ("MUNICÍPIO EMITENTE", "emitente_municipio"),
    ("CÓDIGO ÓRGÃO SUPERIOR DESTINATÁRIO", "orgao_superior_codigo"),
    ("ÓRGÃO SUPERIOR DESTINATÁRIO", "orgao_superior_nome"),
    ("CÓDIGO ÓRGÃO DESTINATÁRIO", "orgao_codigo"),
    ("ÓRGÃO DESTINATÁRIO", "orgao_nome"),
    ("CNPJ DESTINATÁRIO", "destinatario_cnpj"),
    ("NOME DESTINATÁRIO", "destinatario_nome"),
    ("UF DESTINATÁRIO", "destinatario_uf"),
    ("INDICADOR IE DESTINATÁRIO", "indicador_ie_destinatario"),
    ("DESTINO DA OPERAÇÃO", "destino_operacao"),
    ("CONSUMIDOR FINAL", "consumidor_final"),
    ("PRESENÇA DO COMPRADOR", "presenca_comprador"),
    ("NÚMERO PRODUTO", "numero_produto"),
    ("DESCRIÇÃO DO PRODUTO/SERVIÇO", "descricao_produto"),
    ("CÓDIGO NCM/SH", "ncm_raw"),
    ("NCM/SH (TIPO DE PRODUTO)", "ncm_descricao"),
    ("CFOP", "cfop_raw"),
    ("QUANTIDADE", "quantidade_raw"),
    ("UNIDADE", "unidade_raw"),
    ("VALOR UNITÁRIO", "valor_unitario_raw"),
    ("VALOR TOTAL", "valor_total_raw"),
]

EVENTO_COLUMNS: list[tuple[str, str]] = [
    ("CHAVE DE ACESSO", "chave_acesso"),
    ("MODELO", "modelo"),
    ("SÉRIE", "serie"),
    ("NÚMERO", "numero_nota"),
    ("NATUREZA DA OPERAÇÃO", "natureza_operacao"),
    ("DATA EMISSÃO", "data_emissao"),
    ("EVENTO", "evento"),
    ("DATA/HORA EVENTO", "data_hora_evento"),
    ("DESCRIÇÃO EVENTO", "descricao_evento"),
    ("MOTIVO EVENTO", "motivo_evento"),
]

CONTRACTS: dict[str, list[tuple[str, str]]] = {
    "nota": NOTA_COLUMNS,
    "item": ITEM_COLUMNS,
    "evento": EVENTO_COLUMNS,
}

# Metadata columns appended by bronze to every row.
BRONZE_META_COLUMNS = ("_mes_referencia", "_source_file", "_ingested_at")


def raw_columns(entity: str) -> list[str]:
    return [raw for raw, _ in CONTRACTS[entity]]


def snake_columns(entity: str) -> list[str]:
    return [snake for _, snake in CONTRACTS[entity]]


def quote_ident(name: str) -> str:
    """Quote a SQL identifier for DuckDB (raw headers contain spaces, slashes and accents)."""
    return '"' + name.replace('"', '""') + '"'
