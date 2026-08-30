"""Construcción de URLs de búsqueda de Zonaprop.

Zonaprop usa URLs "semánticas":
    /departamentos-ph-alquiler-vicente-lopez-2-ambientes.html
    /departamentos-alquiler-nunez-1-ambiente-pagina-3.html

El orden de los segmentos es: <tipos>-<operacion>-<zona>-<ambientes>[-<extras>][-pagina-N].html
Los filtros de precio no entran en la URL semántica de forma confiable, así que se
aplican del lado nuestro sobre los resultados (que es más robusto ante cambios).
"""

from __future__ import annotations

import re
import unicodedata

BASE = "https://www.zonaprop.com.ar"

# Tipos de propiedad admitidos y su slug en la URL.
TIPOS = {
    "departamento": "departamentos",
    "departamentos": "departamentos",
    "depto": "departamentos",
    "ph": "ph",
    "casa": "casas",
    "casas": "casas",
    "local": "locales-comerciales",
    "oficina": "oficinas-comerciales",
}

OPERACIONES = {
    "alquiler": "alquiler",
    "venta": "venta",
    "temporal": "alquiler-temporal",
}


def slugify(texto: str) -> str:
    """'Vicente López' -> 'vicente-lopez'; 'Núñez' -> 'nunez'."""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def _slug_ambientes(ambientes) -> str:
    """[1] -> '1-ambiente'; [1,2] -> '1-2-ambientes'; [] -> ''.

    Ojo: Zonaprop normaliza algunos rangos (pide 1-2 y a veces te devuelve solo 2).
    Por eso, cuando pedís más de un valor de ambientes, el scraper hace UNA
    búsqueda por cada valor y después une los resultados deduplicando por id.
    Esta función se usa con un solo valor por vez.
    """
    if not ambientes:
        return ""
    if len(ambientes) == 1:
        n = ambientes[0]
        return f"{n}-ambiente" if n == 1 else f"{n}-ambientes"
    return "-".join(str(a) for a in ambientes) + "-ambientes"


def construir_url(
    zona: str,
    tipos=("departamentos", "ph"),
    operacion: str = "alquiler",
    ambientes=None,
    pagina: int = 1,
    precio_max: float | int | None = None,
    precio_min: float | int | None = None,
    extras=(),
) -> str:
    """Devuelve la URL de una página de resultados.

    zona: 'vicente-lopez', 'nunez', 'belgrano', 'olivos', 'capital-federal'...
    tipos: lista de tipos de propiedad.
    ambientes: lista de enteros, normalmente uno solo (ver _slug_ambientes).
    precio_max: tope de precio en pesos para la URL de Zonaprop.
    extras: segmentos extra opcionales, p.ej. ('apto-mascotas',).
    """
    tipos_slug = [TIPOS.get(t.lower(), slugify(t)) for t in tipos]
    partes = ["-".join(tipos_slug), OPERACIONES.get(operacion, operacion), slugify(zona)]

    amb = _slug_ambientes(ambientes or [])
    if amb:
        partes.append(amb)

    if precio_max:
        partes.append(f"menos-{int(precio_max)}-pesos")
    if precio_min:
        partes.append(f"mas-de-{int(precio_min)}-pesos")

    partes.extend(slugify(e) for e in extras)

    slug = "-".join(p for p in partes if p)
    if pagina > 1:
        slug += f"-pagina-{pagina}"
    return f"{BASE}/{slug}.html"


def nombre_run(zona: str | list[str] | tuple[str, ...], ambientes=None, operacion: str = "alquiler") -> str:
    if isinstance(zona, (list, tuple)):
        if len(zona) == 1:
            z_slug = slugify(zona[0])
        elif len(zona) <= 3:
            z_slug = "-".join(slugify(z) for z in zona)
        else:
            z_slug = f"{slugify(zona[0])}-y-{len(zona)-1}-zonas"
    else:
        z_slug = slugify(zona)

    amb = "-".join(str(a) for a in (ambientes or [])) or "todos"
    return f"{z_slug}-{amb}amb-{operacion}"
