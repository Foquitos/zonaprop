"""Geocodificador real y exacto para CABA y GBA con caché local.

Convierte direcciones reales (ej: "Beauchef 1300", "Av. La Plata 1407", "Laprida 4500")
en coordenadas GPS exactas (latitud, longitud) utilizando OpenStreetMap Nominatim
y Photon, con caché persistente en disco para máxima velocidad y cero saturación.
"""

from __future__ import annotations

import atexit
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CACHE_FILE = RAIZ / "salida" / ".geocache.json"

_CACHE: dict[str, list[float] | None] = {}
_CARGADO = False
_CAMBIOS_PENDIENTES = 0


def _cargar_cache():
    global _CACHE, _CARGADO
    if _CARGADO:
        return
    if CACHE_FILE.exists():
        try:
            _CACHE = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [geocodificador] Error al leer caché existente ({e}), inicializando vacía.")
            _CACHE = {}
    _CARGADO = True


def guardar_cache():
    """Persiste la caché acumulada en disco solo si hubo modificaciones nuevas."""
    global _CAMBIOS_PENDIENTES
    if _CAMBIOS_PENDIENTES == 0:
        return
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
        _CAMBIOS_PENDIENTES = 0
    except Exception as e:
        print(f"  [geocodificador] Error al guardar caché en disco: {e}")


_guardar_cache = guardar_cache
atexit.register(guardar_cache)


def normalizar_direccion(dir_txt: str) -> str:
    """Limpia prefijos innecesarios para mejorar la precisión del geocodificador."""
    if not dir_txt:
        return ""
    d = dir_txt.strip()
    # Quitar 'al 1500' -> '1500', 'del 0 al 100' -> ''
    d = re.sub(r"\bdel\s+\d+\s+al\s+\d+\b", "", d, flags=re.IGNORECASE)
    d = re.sub(r"\bal\s+(\d+)\b", r"\1", d, flags=re.IGNORECASE)
    # Quitar aclaraciones de piso/dpto (ej: '3° B', 'Piso 4', '8vo')
    d = re.sub(r"\b\d+[°º]\s*[a-zA-Z0-9]*\b", "", d)
    d = re.sub(r"\bpiso\s+\d+.*$", "", d, flags=re.IGNORECASE)
    d = re.sub(r"\bentre\s+.*$", "", d, flags=re.IGNORECASE)
    d = re.sub(r"\s+", " ", d).strip(", ")
    return d


def tiene_altura_o_calle(dir_txt: str) -> bool:
    """Verifica si la dirección tiene al menos una calle y altura/número real."""
    d = normalizar_direccion(dir_txt)
    # Si solo dice el barrio (ej: 'Parque Chacabuco', 'Caballito'), no es una dirección geolocalizable exacta
    if not re.search(r"\d+", d):
        return False
    return len(d) >= 5


def esta_en_cache(direccion: str, barrio: str = "") -> bool:
    """Verifica si una dirección ya fue consultada y existe en la caché local."""
    _cargar_cache()
    dir_limpia = normalizar_direccion(direccion)
    if not tiene_altura_o_calle(dir_limpia):
        return False
    clave = f"{dir_limpia.lower()}|{barrio.lower()}".strip()
    return clave in _CACHE


def geocodificar_direccion(direccion: str, barrio: str = "") -> tuple[float, float] | None:
    """Consulta OpenStreetMap Nominatim para obtener la coordenada exacta de la calle y altura."""
    global _CAMBIOS_PENDIENTES
    _cargar_cache()

    dir_limpia = normalizar_direccion(direccion)
    if not tiene_altura_o_calle(dir_limpia):
        return None

    # Clave de caché
    clave = f"{dir_limpia.lower()}|{barrio.lower()}".strip()
    if clave in _CACHE:
        val = _CACHE[clave]
        return (val[0], val[1]) if val else None

    # Consulta Nominatim
    consulta = f"{dir_limpia}, {barrio}, Buenos Aires, Argentina"
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(consulta)}&format=json&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "ZonapropForensicAuditor/1.0"})

    coords = None
    try:
        # Nominatim exige un máximo estricto de 1 request por segundo según su política de uso.
        time.sleep(1.0)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                if -35.2 <= lat <= -34.2 and -59.0 <= lon <= -58.0:
                    coords = (round(lat, 6), round(lon, 6))
    except Exception as e:
        # Un fallo de red NO es una respuesta: es no haber preguntado.
        # Si lo cacheáramos como None, un timeout o un corte de wifi de dos
        # segundos dejaría esa dirección marcada como "no geocodificable" para
        # siempre, porque la corrida siguiente encontraría la clave en la caché
        # y devolvería None sin volver a consultar. Se sale sin escribir nada,
        # así se reintenta en la próxima corrida.
        print(f"  [geocodificador] Falló la consulta de '{dir_limpia}' ({type(e).__name__}); "
              "no la cacheo para poder reintentarla.")
        return None

    # Acá sí hay respuesta de Nominatim. Un None ahora significa "contestó y no
    # encontró nada" (o cayó fuera del bounding box de AMBA), que es un negativo
    # legítimo y conviene cachear para no volver a preguntar lo mismo.
    _CACHE[clave] = [coords[0], coords[1]] if coords else None
    _CAMBIOS_PENDIENTES += 1
    # Guardamos periódicamente cada 25 consultas a red para evitar reescribir el disco en cada llamada,
    # manteniendo persistencia intermedia si el proceso se interrumpe.
    if _CAMBIOS_PENDIENTES >= 25:
        guardar_cache()
    return coords


def obtener_coordenadas_reales(aviso: dict) -> tuple[float, float] | None:
    """Obtiene las coordenadas reales: primero de Zonaprop, luego geocodificando la dirección real."""
    # 1. Coordenadas directas publicadas en Zonaprop
    lat = aviso.get("latitude")
    lng = aviso.get("longitude")
    if lat is not None and lng is not None:
        try:
            f_lat, f_lng = float(lat), float(lng)
            if abs(f_lat) > 0 and abs(f_lng) > 0 and -90 <= f_lat <= 90 and -180 <= f_lng <= 180:
                return round(f_lat, 6), round(f_lng, 6)
        except (ValueError, TypeError):
            pass

    # 2. Geocodificación exacta de calle y altura
    dir_txt = aviso.get("direccion") or ""
    barrio_txt = aviso.get("barrio") or ""
    return geocodificar_direccion(dir_txt, barrio_txt)
