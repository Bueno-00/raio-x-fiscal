"""Brazilian number formatting for the Markdown reports (1.234.567,89).

Only numbers go through here. Swapping separators on a whole line also rewrites the free text
around the numbers (product descriptions, NCM names), so callers format each number on its own.
"""

from __future__ import annotations

_SWAP = str.maketrans({",": ".", ".": ","})


def num(x: float, nd: int = 0) -> str:
    """1234567.891 -> '1.234.567,89' (nd=2)."""
    return f"{x:,.{nd}f}".translate(_SWAP)


def pct(x: float, nd: int = 1) -> str:
    """Fraction to percent: 0.1234 -> '12,3%'."""
    return num(100 * x, nd) + "%"
