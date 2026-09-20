"""Funciones comunes y utilidades de formato compartidas entre módulos."""

from __future__ import annotations


def _plata(v: float | int | None) -> str:
    """Formatea valores monetarios al estilo argentino ($1.234.567, 0 -> '$0', None -> '-')."""
    if v is None:
        return "-"
    if v == 0:
        return "$0"
    return f"${v:,.0f}".replace(",", ".")
