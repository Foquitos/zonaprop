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
# CABA (Todos los 48 barrios oficiales + subzonas principales)
# --------------------------------------------------------------------------- #
CABA = [
    Zona("capital-federal", "CABA (toda)", "CABA, Capital Federal", "region",
         nota="Más de 16.000 avisos. Conviene filtrar por barrio específico."),

    # --- Corredor Norte ---
    Zona("nunez", "Núñez", "Núñez, CABA", "barrio", "capital-federal"),
    Zona("belgrano", "Belgrano", "Belgrano, CABA", "barrio", "capital-federal"),
    Zona("belgrano-c", "Belgrano C", "Belgrano, CABA", "subbarrio", "belgrano"),
    Zona("belgrano-r", "Belgrano R", "Belgrano, CABA", "subbarrio", "belgrano"),
    Zona("bajo-belgrano", "Bajo Belgrano", "Belgrano, CABA", "subbarrio", "belgrano"),
    Zona("las-canitas", "Las Cañitas", "Palermo, CABA", "subbarrio", "palermo"),
    Zona("colegiales", "Colegiales", "Colegiales, CABA", "barrio", "capital-federal"),
    Zona("saavedra", "Saavedra", "Saavedra, CABA", "barrio", "capital-federal"),
    Zona("coghlan", "Coghlan", "Coghlan, CABA", "barrio", "capital-federal"),
    Zona("villa-urquiza", "Villa Urquiza", "Villa Urquiza, CABA", "barrio", "capital-federal"),
    Zona("villa-pueyrredon", "Villa Pueyrredón", "Villa Pueyrredón, CABA", "barrio", "capital-federal"),
    Zona("chacarita", "Chacarita", "Chacarita, CABA", "barrio", "capital-federal"),

    # --- Palermo, Recoleta y Eje Este ---
    Zona("palermo", "Palermo", "Palermo, CABA", "barrio", "capital-federal"),
    Zona("palermo-soho", "Palermo Soho", "Palermo, CABA", "subbarrio", "palermo"),
    Zona("palermo-hollywood", "Palermo Hollywood", "Palermo, CABA", "subbarrio", "palermo"),
    Zona("palermo-chico", "Palermo Chico", "Palermo, CABA", "subbarrio", "palermo"),
    Zona("recoleta", "Recoleta", "Recoleta, CABA", "barrio", "capital-federal"),
    Zona("barrio-norte-capital-federal", "Barrio Norte", "Barrio Norte, CABA", "subbarrio", "recoleta"),
    Zona("retiro", "Retiro", "Retiro, CABA", "barrio", "capital-federal"),
    Zona("puerto-madero", "Puerto Madero", "Puerto Madero, CABA", "barrio", "capital-federal"),

    # --- Centro y Casco Histórico ---
    Zona("san-telmo", "San Telmo", "San Telmo, CABA", "barrio", "capital-federal"),
    Zona("monserrat", "Monserrat", "Monserrat, CABA", "barrio", "capital-federal"),
    Zona("san-nicolas", "San Nicolás (Centro)", "San Nicolás, CABA", "barrio", "capital-federal"),
    Zona("balvanera", "Balvanera (Once / Abasto)", "Balvanera, CABA", "barrio", "capital-federal"),
    Zona("san-cristobal", "San Cristóbal", "San Cristóbal, CABA", "barrio", "capital-federal"),
    Zona("constitucion", "Constitución", "Constitución, CABA", "barrio", "capital-federal"),

    # --- Centro Geográfico y Noroeste ---
    Zona("caballito", "Caballito", "Caballito, CABA", "barrio", "capital-federal"),
    Zona("almagro", "Almagro", "Almagro, CABA", "barrio", "capital-federal"),
    Zona("boedo", "Boedo", "Boedo, CABA", "barrio", "capital-federal"),
    Zona("villa-crespo", "Villa Crespo", "Villa Crespo, CABA", "barrio", "capital-federal"),
    Zona("parque-chas", "Parque Chas", "Parque Chas, CABA", "barrio", "capital-federal"),
    Zona("villa-ortuzar", "Villa Ortúzar", "Villa Ortúzar, CABA", "barrio", "capital-federal"),
    Zona("agronomia", "Agronomía", "Agronomía, CABA", "barrio", "capital-federal"),
    Zona("la-paternal", "La Paternal", "La Paternal, CABA", "barrio", "capital-federal"),
    Zona("villa-general-mitre", "Villa General Mitre", "Villa General Mitre, CABA", "barrio", "capital-federal"),
    Zona("villa-santa-rita", "Villa Santa Rita", "Villa Santa Rita, CABA", "barrio", "capital-federal"),
    Zona("villa-del-parque", "Villa del Parque", "Villa del Parque, CABA", "barrio", "capital-federal"),
    Zona("villa-devoto", "Villa Devoto", "Villa Devoto, CABA", "barrio", "capital-federal"),
    Zona("monte-castro", "Monte Castro", "Monte Castro, CABA", "barrio", "capital-federal"),

    # --- Zona Oeste ---
    Zona("flores", "Flores", "Flores, CABA", "barrio", "capital-federal"),
    Zona("floresta", "Floresta", "Floresta, CABA", "barrio", "capital-federal"),
    Zona("parque-chacabuco", "Parque Chacabuco", "Parque Chacabuco, CABA", "barrio", "capital-federal"),
    Zona("versalles", "Versalles", "Versalles, CABA", "barrio", "capital-federal"),
    Zona("villa-real", "Villa Real", "Villa Real, CABA", "barrio", "capital-federal"),
    Zona("villa-luro", "Villa Luro", "Villa Luro, CABA", "barrio", "capital-federal"),
    Zona("velez-sarsfield", "Vélez Sársfield", "Vélez Sársfield, CABA", "barrio", "capital-federal"),
    Zona("liniers", "Liniers", "Liniers, CABA", "barrio", "capital-federal"),
    Zona("mataderos", "Mataderos", "Mataderos, CABA", "barrio", "capital-federal"),
    Zona("parque-avellaneda", "Parque Avellaneda", "Parque Avellaneda, CABA", "barrio", "capital-federal"),

    # --- Zona Sur ---
    Zona("barracas", "Barracas", "Barracas, CABA", "barrio", "capital-federal"),
    Zona("la-boca", "La Boca", "La Boca, CABA", "barrio", "capital-federal"),
    Zona("parque-patricios", "Parque Patricios", "Parque Patricios, CABA", "barrio", "capital-federal"),
    Zona("nueva-pompeya", "Nueva Pompeya", "Nueva Pompeya, CABA", "barrio", "capital-federal"),
    Zona("villa-soldati", "Villa Soldati", "Villa Soldati, CABA", "barrio", "capital-federal"),
    Zona("villa-lugano", "Villa Lugano", "Villa Lugano, CABA", "barrio", "capital-federal"),
    Zona("villa-riachuelo", "Villa Riachuelo", "Villa Riachuelo, CABA", "barrio", "capital-federal"),
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
    ("CABA — Corredor Norte", [
        "nunez", "belgrano", "belgrano-c", "belgrano-r", "bajo-belgrano",
        "las-canitas", "colegiales", "saavedra", "coghlan",
        "villa-urquiza", "villa-pueyrredon", "chacarita",
    ]),
    ("CABA — Palermo, Recoleta y Eje Este", [
        "palermo", "palermo-soho", "palermo-hollywood", "palermo-chico",
        "recoleta", "barrio-norte-capital-federal", "retiro", "puerto-madero",
    ]),
    ("CABA — Centro y Casco Histórico", [
        "san-telmo", "monserrat", "san-nicolas", "balvanera", "san-cristobal", "constitucion",
    ]),
    ("CABA — Centro Geográfico y Noroeste", [
        "caballito", "almagro", "boedo", "villa-crespo", "parque-chas",
        "villa-ortuzar", "agronomia", "la-paternal", "villa-general-mitre",
        "villa-santa-rita", "villa-del-parque", "villa-devoto", "monte-castro",
    ]),
    ("CABA — Zona Oeste", [
        "flores", "floresta", "parque-chacabuco", "versalles", "villa-real",
        "villa-luro", "velez-sarsfield", "liniers", "mataderos", "parque-avellaneda",
    ]),
    ("CABA — Zona Sur", [
        "barracas", "la-boca", "parque-patricios", "nueva-pompeya",
        "villa-soldati", "villa-lugano", "villa-riachuelo",
    ]),
    ("CABA — Toda la Ciudad", [
        "capital-federal",
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
