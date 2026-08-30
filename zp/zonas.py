"""Catálogo de zonas de Zonaprop, con los slugs verificados uno por uno.

Por qué existe este archivo en vez de armar el slug al vuelo desde el nombre:
Zonaprop **falla en silencio**. Si el slug no existe, no tira 404: te devuelve
una búsqueda de todo el país, o de otra provincia, con status 200 y 30 avisos
que parecen normales. Verificados el 30/8/2026:

    zona-norte    -> 45.738 avisos "en Argentina"          (la zona no existe)
    barrio-chino  -> 45.738 avisos "en Argentina"
    san-martin    -> 4 avisos en San Martín, MENDOZA        (hay que usar general-san-martin)
    la-lucila     -> 0 avisos                               (hay que usar la-lucila-vicente-lopez)

Además, cuando dos zonas se llaman igual, el slug lleva el partido pegado
(`vicente-lopez-vicente-lopez` es la localidad; `vicente-lopez` a secas es todo
el partido). Y cuando un slug tiene un guion de más, Zonaprop lo interpreta como
un OR de dos zonas: `florida-belgrano-oeste` devuelve "Belgrano, CABA o Florida,
Vicente López", que no es lo que nadie quiso pedir.

Por eso cada zona guarda el texto que Zonaprop tiene que devolver en el <h1>.
`validar_h1()` compara, y si no coincide se corta la corrida en vez de traerte
600 departamentos de Palermo pensando que son de Villa Martelli.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Zona:
    slug: str          # lo que va en la URL
    nombre: str        # cómo se muestra en el menú
    esperado: str      # lo que tiene que decir el h1 de Zonaprop
    nivel: str         # region | partido | localidad | barrio
    padre: str | None = None
    nota: str = ""


# --------------------------------------------------------------------------- #
# GBA Norte
# --------------------------------------------------------------------------- #
GBA_NORTE = [
    Zona("gba-norte", "GBA Norte (todo)", "Provincia de GBA Norte", "region",
         nota="Toda la zona norte del conurbano. Son miles de avisos."),

    # --- Partido de Vicente López ---
    Zona("vicente-lopez", "Vicente López (todo el partido)", "Vicente López, GBA Norte",
         "partido", "gba-norte",
         nota="Incluye Olivos, Florida, La Lucila, Munro, Carapachay, "
              "Villa Martelli, Florida Oeste y la localidad de Vicente López."),
    Zona("vicente-lopez-vicente-lopez", "Vicente López (solo la localidad)",
         "Vicente López, Vicente López", "localidad", "vicente-lopez",
         nota="Ojo: NO es todo el partido. Es el barrio pegado a General Paz y el río."),
    Zona("olivos", "Olivos", "Olivos, Vicente López", "localidad", "vicente-lopez"),
    Zona("la-lucila-vicente-lopez", "La Lucila", "La Lucila, Vicente López",
         "localidad", "vicente-lopez",
         nota="El slug lleva el partido pegado; `la-lucila` a secas devuelve 0."),
    Zona("florida", "Florida", "Florida, Vicente López", "localidad", "vicente-lopez"),
    Zona("florida-oeste", "Florida Oeste", "Florida Oeste, Vicente López",
         "localidad", "vicente-lopez", nota="Muy poca oferta, típicamente menos de 10 avisos."),
    Zona("munro", "Munro", "Munro, Vicente López", "localidad", "vicente-lopez"),
    Zona("carapachay", "Carapachay", "Carapachay, Vicente López", "localidad", "vicente-lopez"),
    Zona("villa-martelli", "Villa Martelli", "Villa Martelli, Vicente López",
         "localidad", "vicente-lopez"),

    # --- Otros partidos ---
    Zona("san-isidro", "San Isidro (partido)", "San Isidro, GBA Norte", "partido", "gba-norte"),
    Zona("martinez", "Martínez", "Martínez, San Isidro", "localidad", "san-isidro"),
    Zona("villa-adelina", "Villa Adelina", "Villa Adelina, San Isidro",
         "localidad", "san-isidro",
         nota="Zonaprop la cuelga de San Isidro, aunque parte cae en Vicente López."),
    Zona("general-san-martin", "General San Martín", "General San Martín, GBA Norte",
         "partido", "gba-norte",
         nota="Usar este slug: `san-martin` te devuelve San Martín de MENDOZA."),
    Zona("san-fernando", "San Fernando", "San Fernando, GBA Norte", "partido", "gba-norte"),
    Zona("tigre", "Tigre", "Tigre, GBA Norte", "partido", "gba-norte"),
]

# --------------------------------------------------------------------------- #
# CABA
# --------------------------------------------------------------------------- #
CABA = [
    Zona("capital-federal", "CABA (toda)", "CABA, Capital Federal", "region",
         nota="Más de 16.000 avisos. Conviene bajar a barrio."),

    Zona("nunez", "Núñez", "Núñez, CABA", "barrio", "capital-federal"),
    Zona("belgrano", "Belgrano", "Belgrano, CABA", "barrio", "capital-federal",
         nota="Zonaprop no separa Belgrano C, R ni Chico: los tres caen acá."),
    Zona("colegiales", "Colegiales", "Colegiales, CABA", "barrio", "capital-federal"),
    Zona("saavedra", "Saavedra", "Saavedra, CABA", "barrio", "capital-federal"),
    Zona("coghlan", "Coghlan", "Coghlan, CABA", "barrio", "capital-federal"),
    Zona("villa-urquiza", "Villa Urquiza", "Villa Urquiza, CABA", "barrio", "capital-federal"),
    Zona("chacarita", "Chacarita", "Chacarita, CABA", "barrio", "capital-federal"),
    Zona("palermo", "Palermo", "Palermo, CABA", "barrio", "capital-federal"),
    Zona("villa-crespo", "Villa Crespo", "Villa Crespo, CABA", "barrio", "capital-federal"),
    Zona("caballito", "Caballito", "Caballito, CABA", "barrio", "capital-federal"),
    Zona("recoleta", "Recoleta", "Recoleta, CABA", "barrio", "capital-federal"),
    Zona("almagro", "Almagro", "Almagro, CABA", "barrio", "capital-federal"),
    Zona("villa-devoto", "Villa Devoto", "Villa Devoto, CABA", "barrio", "capital-federal"),
    Zona("villa-pueyrredon", "Villa Pueyrredón", "Villa Pueyrredón, CABA",
         "barrio", "capital-federal"),
]

TODAS = {z.slug: z for z in (GBA_NORTE + CABA)}

# Cómo se agrupa en el menú.
GRUPOS = [
    ("GBA Norte — Partido de Vicente López", [
        "vicente-lopez", "vicente-lopez-vicente-lopez", "olivos",
        "la-lucila-vicente-lopez", "florida", "florida-oeste", "munro",
        "carapachay", "villa-martelli",
    ]),
    ("GBA Norte — otros partidos", [
        "san-isidro", "martinez", "villa-adelina", "general-san-martin",
        "san-fernando", "tigre", "gba-norte",
    ]),
    ("CABA — corredor norte", [
        "nunez", "belgrano", "colegiales", "saavedra", "coghlan",
        "villa-urquiza", "villa-pueyrredon", "chacarita",
    ]),
    ("CABA — resto", [
        "palermo", "villa-crespo", "caballito", "recoleta", "almagro",
        "villa-devoto", "capital-federal",
    ]),
]


# --------------------------------------------------------------------------- #
def obtener(slug: str) -> Zona | None:
    return TODAS.get(slug)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


def validar_h1(slug: str, h1: str) -> tuple[bool, str]:
    """¿El h1 que devolvió Zonaprop corresponde a la zona que pedimos?

    Devuelve (ok, mensaje). Si la zona no está en el catálogo, no bloquea:
    avisa y deja seguir, porque puede ser un slug nuevo que todavía no cargué.
    """
    z = TODAS.get(slug)
    if not z:
        return True, f"'{slug}' no está en el catálogo; no puedo validar la zona."

    if _norm(z.esperado) in _norm(h1):
        return True, ""

    # Los dos errores clásicos, con el diagnóstico ya escrito.
    if "en argentina" in _norm(h1):
        return False, (
            f"Zonaprop no reconoció '{slug}' y devolvió resultados de todo el país. "
            "El slug no existe o cambió."
        )
    return False, (
        f"Pedí '{z.nombre}' y Zonaprop devolvió «{h1.strip()[:80]}». "
        "No coinciden: puede ser una zona homónima de otra provincia."
    )


def buscar(texto: str) -> list[Zona]:
    """Búsqueda por nombre para el filtro del menú."""
    t = _norm(texto)
    if not t:
        return list(TODAS.values())
    return [z for z in TODAS.values() if t in _norm(z.nombre) or t in _norm(z.slug)]


def resumen() -> str:
    """Listado en texto, para `python zp.py zonas`."""
    lineas = []
    for titulo, slugs in GRUPOS:
        lineas.append(f"\n{titulo}")
        lineas.append("-" * len(titulo))
        for s in slugs:
            z = TODAS[s]
            lineas.append(f"  {z.slug:<30} {z.nombre}")
            if z.nota:
                lineas.append(f"  {'':<30} └ {z.nota}")
    return "\n".join(lineas)
