"""Distancia de cada aviso al barrio popular más cercano, según el RENABAP.

Qué mide este dato, porque la etiqueta importa
----------------------------------------------
El RENABAP (Registro Nacional de Barrios Populares) es el registro oficial que
lleva el Estado argentino de los barrios donde hay informalidad en la tenencia
de la tierra y falta de acceso formal a servicios básicos. Se creó para dar
títulos y financiar obras, y clasifica cada barrio en 'Villa', 'Asentamiento' o
'Conjunto habitacional unifamiliar'.

NO es una estadística de delito ni de seguridad. Es un dato de urbanismo. La
cercanía a un barrio popular es un factor inmobiliario real —afecta el precio
y es algo que la gente pondera al alquilar— pero conviene tener claro que lo
que se está midiendo es distancia a un barrio registrado, no "peligrosidad".
Por eso los textos que genera este módulo dicen lo que el dato dice y nada más,
y la penalización vive en PENALIZACION_DISTANCIA, para que se pueda tocar o
apagar sin tocar el resto del scoring.

Fuente: datos.gob.ar, dataset "Registro Nacional de Barrios Populares".
El archivo bundleado es un recorte de AMBA del snapshot 2023-12-05, con las
coordenadas redondeadas a 5 decimales (~1 m) y sólo los campos que se usan.

Cómo se calcula la distancia
----------------------------
Distancia real al BORDE del polígono, no al centro: un barrio de 40 hectáreas
tiene un centro que puede estar a 600 m de su propia esquina, y lo que importa
es cuán cerca está el departamento del límite. Si el punto cae adentro, es 0.

Para no recorrer los 1677 polígonos vértice por vértice en cada aviso se usa
una poda por bounding box: la distancia al bbox es una cota inferior de la
distancia al polígono, así que alcanza con evaluar en detalle los candidatos
cuyo bbox esté más cerca que el mejor resultado encontrado hasta el momento.
El resultado es exacto, no aproximado.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO = RAIZ / "datos" / "renabap-amba.geojson.gz"

# Penalización de calidad, en puntos del mismo pozo que BONOS y PENAS de
# scoring.py. Es continua en la distancia y escalada por el tamaño del barrio:
#
#     puntos = PENALIZACION_BASE * peso_tamaño(familias) * decaimiento(metros)
#
# La primera versión usaba tramos discretos de distancia y no servía: un
# departamento en Pumacahua al 1600 está a 175 m de Villa 13 Bis (165 familias)
# y a 602 m de la 1-11-14 (15.400 familias), y con tramos el barrio chico y
# cercano le ganaba al grande. O sea que el aviso se llevaba una penalización
# menor justamente por lo que más importaba.
PENALIZACION_BASE = -12.0

# A partir de acá no se penaliza nada. ~11 cuadras.
ALCANCE_M = 1200


def _peso_tamanio(familias: int | None) -> float:
    """Un asentamiento de 20 familias y una villa de 15.000 no son lo mismo."""
    if not familias:
        return 0.8  # sin dato: ni lo peor ni lo mejor
    if familias >= 8000:
        return 2.2
    if familias >= 2000:
        return 1.7
    if familias >= 500:
        return 1.2
    if familias >= 100:
        return 0.8
    return 0.5


def _decaimiento(metros: int) -> float:
    """1.0 pegado, 0 a partir de ALCANCE_M, lineal en el medio."""
    if metros <= 0:
        return 1.0
    if metros >= ALCANCE_M:
        return 0.0
    return 1.0 - metros / ALCANCE_M


_CACHE: list[dict] | None = None

# Metros por grado. A la latitud de Buenos Aires alcanza de sobra: el error de
# la aproximación plana a estas distancias es de menos del 0,5%.
_M_POR_GRADO_LAT = 110574.0
_LAT_REF = -34.6
_M_POR_GRADO_LNG = 111320.0 * math.cos(math.radians(_LAT_REF))


def _cargar() -> list[dict]:
    """Lee el GeoJSON bundleado una sola vez y precalcula bbox por barrio."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not ARCHIVO.exists():
        _CACHE = []
        return _CACHE
    try:
        with gzip.open(ARCHIVO, "rt", encoding="utf-8") as f:
            datos = json.load(f)
    except Exception as e:
        print(f"  [barrios_populares] No pude leer {ARCHIVO.name} ({e}); "
              "se sigue sin el dato de cercanía.")
        _CACHE = []
        return _CACHE

    barrios = []
    for feat in datos.get("features", []):
        anillos = _anillos(feat.get("geometry") or {})
        if not anillos:
            continue
        xs = [c[0] for anillo in anillos for c in anillo]
        ys = [c[1] for anillo in anillos for c in anillo]
        p = feat.get("properties") or {}
        barrios.append({
            "nombre": p.get("nombre_barrio") or "sin nombre",
            "clasificacion": p.get("clasificacion_barrio") or "",
            "familias": p.get("cantidad_familias_aproximada"),
            "localidad": p.get("localidad") or "",
            "anillos": anillos,
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
        })
    _CACHE = barrios
    return _CACHE


def _anillos(geom: dict) -> list[list]:
    """Aplana Polygon / MultiPolygon a una lista de anillos de coordenadas."""
    tipo = geom.get("type")
    coords = geom.get("coordinates") or []
    if tipo == "Polygon":
        return [a for a in coords if a]
    if tipo == "MultiPolygon":
        return [a for poligono in coords for a in poligono if a]
    return []


def _dist_punto_segmento(px, py, ax, ay, bx, by) -> float:
    """Distancia de un punto al segmento AB, en el plano ya proyectado."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _dentro(lng: float, lat: float, anillo: list) -> bool:
    """Ray casting sobre un anillo en grados."""
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > lat) != (yj > lat):
            x_corte = xi + (lat - yi) * (xj - xi) / (yj - yi)
            if lng < x_corte:
                dentro = not dentro
        j = i
    return dentro


def _dist_a_bbox(lng: float, lat: float, bbox: tuple) -> float:
    """Distancia en metros del punto al bbox. Es cota inferior de la real."""
    x0, y0, x1, y1 = bbox
    dx = max(x0 - lng, 0.0, lng - x1) * _M_POR_GRADO_LNG
    dy = max(y0 - lat, 0.0, lat - y1) * _M_POR_GRADO_LAT
    return math.hypot(dx, dy)


def _dist_a_barrio(lng: float, lat: float, barrio: dict) -> float:
    """Distancia en metros al borde del polígono. 0 si el punto cae adentro."""
    px, py = lng * _M_POR_GRADO_LNG, lat * _M_POR_GRADO_LAT
    mejor = float("inf")
    for anillo in barrio["anillos"]:
        if _dentro(lng, lat, anillo):
            return 0.0
        n = len(anillo)
        for i in range(n):
            ax, ay = anillo[i][0] * _M_POR_GRADO_LNG, anillo[i][1] * _M_POR_GRADO_LAT
            bx, by = anillo[(i + 1) % n][0] * _M_POR_GRADO_LNG, anillo[(i + 1) % n][1] * _M_POR_GRADO_LAT
            d = _dist_punto_segmento(px, py, ax, ay, bx, by)
            if d < mejor:
                mejor = d
    return mejor


def mas_cercano(lat: float, lng: float) -> dict | None:
    """Devuelve el barrio popular más cercano al punto, o None si no hay datos.

    {'distancia_m': int, 'nombre': str, 'clasificacion': str,
     'familias': int|None, 'localidad': str, 'dentro': bool}
    """
    barrios = _cargar()
    if not barrios or lat is None or lng is None:
        return None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None

    # Poda: se ordenan por distancia al bbox (cota inferior) y se corta apenas
    # el mejor exacto encontrado es menor que la cota del siguiente candidato.
    candidatos = sorted(
        ((_dist_a_bbox(lng, lat, b["bbox"]), b) for b in barrios),
        key=lambda t: t[0],
    )

    mejor_d = float("inf")
    mejor_b = None
    for cota, b in candidatos:
        if cota >= mejor_d:
            break  # ninguno de los que siguen puede mejorar
        d = _dist_a_barrio(lng, lat, b)
        if d < mejor_d:
            mejor_d, mejor_b = d, b

    if mejor_b is None:
        return None
    return {
        "distancia_m": int(round(mejor_d)),
        "nombre": mejor_b["nombre"],
        "clasificacion": mejor_b["clasificacion"],
        "familias": mejor_b["familias"],
        "localidad": mejor_b["localidad"],
        "dentro": mejor_d == 0.0,
    }


def cercanos(lat: float, lng: float, radio_m: int = 1000) -> list[dict]:
    """Todos los barrios populares dentro del radio, del más cercano al más lejano."""
    barrios = _cargar()
    if not barrios or lat is None or lng is None:
        return []
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return []

    encontrados = []
    for b in barrios:
        if _dist_a_bbox(lng, lat, b["bbox"]) > radio_m:
            continue
        d = _dist_a_barrio(lng, lat, b)
        if d <= radio_m:
            encontrados.append({
                "distancia_m": int(round(d)),
                "nombre": b["nombre"],
                "clasificacion": b["clasificacion"],
                "familias": b["familias"],
                "localidad": b["localidad"],
                "dentro": d == 0.0,
            })
    encontrados.sort(key=lambda x: x["distancia_m"])
    return encontrados


def _penalizacion(info: dict) -> tuple[float, str | None]:
    """Penalización de UN barrio, según su distancia y su tamaño."""
    d = info["distancia_m"]
    pts = PENALIZACION_BASE * _peso_tamanio(info["familias"]) * _decaimiento(d)
    if pts > -0.5:
        return 0.0, None
    if info.get("dentro"):
        etiqueta = "dentro de un barrio popular"
    elif d <= 150:
        etiqueta = "pegado a un barrio popular"
    else:
        etiqueta = f"a ~{_cuadras(d)} de un barrio popular"
    return round(pts, 1), etiqueta


def evaluar(lat: float, lng: float) -> tuple[dict | None, float, str | None]:
    """Devuelve (info_del_mas_relevante, puntos_de_penalizacion, etiqueta).

    `puntos` es negativo o 0 y se suma al pozo de calidad de scoring.py.

    Se evalúan TODOS los barrios del radio y gana el que más pesa, que no
    siempre es el más cercano. El caso que motivó esto: un departamento en
    Pumacahua al 1600 está a 175 m de Villa 13 Bis, que tiene 165 familias,
    pero a 602 m de la 1-11-14, que tiene 15.400. Mirando sólo el más cercano
    el aviso se llevaba una penalización chica y seguía saliendo recomendado,
    que es exactamente el problema que se quería resolver.
    """
    cerca = cercanos(lat, lng)
    if not cerca:
        info = mas_cercano(lat, lng)
        return info, 0.0, None

    peor_pts, peor_info, peor_etiqueta = 0.0, None, None
    for info in cerca:
        pts, etiqueta = _penalizacion(info)
        if pts < peor_pts:
            peor_pts, peor_info, peor_etiqueta = pts, info, etiqueta

    if peor_info is None:
        return cerca[0], 0.0, None

    detalle = f"{peor_etiqueta}: {peor_info['nombre']} a {peor_info['distancia_m']} m"
    if peor_info["familias"]:
        detalle += f" ({peor_info['familias']:,} familias)".replace(",", ".")
    # Si el que pesa no es el que está más cerca, conviene decir las dos cosas.
    if peor_info is not cerca[0] and cerca[0]["distancia_m"] < peor_info["distancia_m"]:
        detalle += f"; el más cercano es {cerca[0]['nombre']} a {cerca[0]['distancia_m']} m"
    return peor_info, peor_pts, detalle


def _tipo_con_articulo(clasificacion: str) -> str:
    """'Villa' es femenino y 'asentamiento' masculino: 'de la villa' / 'del asentamiento'."""
    c = (clasificacion or "").strip().lower()
    if c.startswith("villa"):
        return "de la villa"
    if c.startswith("asentamiento"):
        return "del asentamiento"
    if c.startswith("conjunto"):
        return "del conjunto habitacional"
    return "del barrio popular"


def _cuadras(metros: int) -> str:
    """Las cuadras de Buenos Aires son de ~110 m."""
    if metros < 60:
        return "menos de media cuadra"
    c = round(metros / 110)
    if c <= 1:
        return "1 cuadra"
    return f"{c} cuadras"


def descripcion(info: dict | None) -> str:
    """Texto factual para el dossier y el dashboard."""
    if not info:
        return "sin dato"
    tipo = _tipo_con_articulo(info.get("clasificacion"))
    if info.get("dentro"):
        base = f"dentro {tipo} {info['nombre']} (RENABAP)"
    else:
        base = (f"a {info['distancia_m']} m (~{_cuadras(info['distancia_m'])}) "
                f"{tipo} {info['nombre']} (RENABAP)")
    if info.get("familias"):
        base += f", {info['familias']:,} familias".replace(",", ".")
    return base
