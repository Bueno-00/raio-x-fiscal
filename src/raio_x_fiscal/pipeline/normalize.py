"""Pure normalisation rules, in Python and in DuckDB SQL.

The silver layer applies these rules in SQL (fast, set-based). The Python versions exist so
the rules can be unit-tested one value at a time and so the ML inference path normalises a
free-text description exactly like the pipeline did (tests assert SQL/Python parity).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

NCM_MISSING_SENTINELS = {"", "-1", "0", "00000000"}
# NCM/SH chapters go from 01 to 97; 77 is reserved (never used); 98 and 99 are not used in NCM.
VALID_CHAPTERS = {f"{c:02d}" for c in range(1, 98)} - {"77"}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"^\d+$")


def parse_decimal_br(value: str | None) -> Decimal | None:
    """'1.234,56' -> Decimal('1234.56'); '-1' -> Decimal('-1'); garbage -> None."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date_br(value: str | None) -> date | None:
    """'01/09/2025 00:00:00' or '01/09/2025' -> date(2025, 9, 1)."""
    if value is None:
        return None
    s = value.strip()[:10]
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def normalize_ncm(value: str | None) -> str | None:
    """Return a valid 8-digit NCM or None.

    The CSV loses the leading zero of chapters 01 to 09 ('7133399' means '07133399'), and uses
    '-1' when the item has no NCM. Anything else (wrong length, invalid chapter) is None.
    """
    if value is None:
        return None
    s = value.strip()
    if s in NCM_MISSING_SENTINELS or not _DIGITS.match(s):
        return None
    if len(s) == 7:
        s = "0" + s
    if len(s) != 8 or s[:2] not in VALID_CHAPTERS:
        return None
    return s


def ncm_parts(ncm: str) -> dict[str, str]:
    """Hierarchy of a valid NCM: capitulo (2), posicao (4), subposicao (6), item (8)."""
    return {"capitulo": ncm[:2], "posicao": ncm[:4], "subposicao": ncm[:6], "ncm": ncm}


def normalize_cfop(value: str | None) -> str | None:
    """CFOP must be 4 digits starting with 1, 2, 3 (entradas) or 5, 6, 7 (saidas)."""
    if value is None:
        return None
    s = value.strip()
    if len(s) == 4 and _DIGITS.match(s) and s[0] in "123567":
        return s
    return None


def is_valid_chave(value: str | None) -> bool:
    """NF-e access key: exactly 44 digits."""
    return value is not None and len(value) == 44 and _DIGITS.match(value) is not None


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_description(text: str | None) -> str:
    """Lowercase, no accents, only [a-z0-9] tokens separated by one space.

    Deliberately light: it keeps numbers and units ('500ml', '2,5mm' -> '2 5mm') because size
    and material often decide the NCM. Mirrors `SQL_NORMALIZE_DESCRIPTION`.
    """
    if text is None:
        return ""
    s = strip_accents(text).lower()
    s = _NON_ALNUM.sub(" ", s)
    return s.strip()


def emitente_tipo(cpf_cnpj: str | None) -> str:
    """'CNPJ' (14 digits), 'CPF' (11 digits) or 'OUTRO'."""
    if cpf_cnpj is None:
        return "OUTRO"
    s = cpf_cnpj.strip()
    if len(s) == 14 and _DIGITS.match(s):
        return "CNPJ"
    if len(s) == 11 and _DIGITS.match(s):
        return "CPF"
    return "OUTRO"


# ---------------------------------------------------------------------------------------------
# SQL counterparts (DuckDB). Each takes a column expression and returns a SQL expression.
# ---------------------------------------------------------------------------------------------


def sql_decimal_br(col: str, scale: int = 2) -> str:
    return (
        f"TRY_CAST(replace(replace(trim({col}), '.', ''), ',', '.') AS DECIMAL(18,{scale}))"
    )


def sql_date_br(col: str) -> str:
    return f"TRY_STRPTIME(substr(trim({col}), 1, 10), '%d/%m/%Y')::DATE"


def sql_timestamp_br(col: str) -> str:
    return f"TRY_STRPTIME(trim({col}), '%d/%m/%Y %H:%M:%S')"


def sql_normalize_ncm(col: str) -> str:
    """Same rule as `normalize_ncm`, as a SQL CASE expression."""
    s = f"trim({col})"
    padded = f"CASE WHEN length({s}) = 7 THEN '0' || {s} ELSE {s} END"
    sentinels = ", ".join(f"'{v}'" for v in sorted(NCM_MISSING_SENTINELS) if v)
    return (
        f"CASE WHEN {s} IN ({sentinels}) OR {s} = '' OR NOT regexp_matches({s}, '^[0-9]+$') "
        f"THEN NULL "
        f"WHEN length({padded}) <> 8 THEN NULL "
        f"WHEN substr({padded}, 1, 2) NOT IN ({', '.join(repr(c) for c in sorted(VALID_CHAPTERS))}) "
        f"THEN NULL "
        f"ELSE {padded} END"
    )


def sql_normalize_cfop(col: str) -> str:
    s = f"trim({col})"
    return f"CASE WHEN regexp_matches({s}, '^[123567][0-9]{{3}}$') THEN {s} ELSE NULL END"


def sql_is_valid_chave(col: str) -> str:
    return f"regexp_matches({col}, '^[0-9]{{44}}$')"


def sql_normalize_description(col: str) -> str:
    return f"trim(regexp_replace(lower(strip_accents(coalesce({col}, ''))), '[^a-z0-9]+', ' ', 'g'))"


def sql_emitente_tipo(col: str) -> str:
    s = f"trim({col})"
    return (
        f"CASE WHEN regexp_matches({s}, '^[0-9]{{14}}$') THEN 'CNPJ' "
        f"WHEN regexp_matches({s}, '^[0-9]{{11}}$') THEN 'CPF' ELSE 'OUTRO' END"
    )
