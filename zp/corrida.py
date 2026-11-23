"""Lo que vive en la carpeta de una corrida, además del ranking.

`ranking.json` se reescribe entero cada vez que se corre `rankear` o `fotos`.
Mientras fue el único lugar donde quedaba el detalle de cada aviso (galería,
descripción completa, días publicado), cualquier corte a mitad de `fotos` o un
`rankear` posterior perdía datos. Por eso el detalle, los parámetros de la
corrida y el veredicto del auditor viven en archivos propios que nadie pisa:

    parametros.json      presupuesto, dólar, ambientes buscados, fecha de la búsqueda
    detalles/<id>.json   lo que trajo la página del aviso, uno por aviso
    auditoria.json       veredictos del LLM (lo escribe zp/auditor.py)

Y una sola función, `puntuar_corrida`, puntúa siempre con los mismos
argumentos. Antes `fotos` volvía a puntuar sin historial y con el presupuesto
que le llegara por línea de comandos (None si se corría a mano), y así
revivían los avisos que `rankear` había descartado por caros.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path

from zp import scoring

DIAS_DETALLE_FRESCO = 3


def escribir_json(ruta: Path, datos) -> None:
    """Escribe a un temporal y lo reemplaza: un corte no deja el archivo a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".tmp", dir=str(ruta.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def leer_json(ruta: Path, defecto):
    if not ruta.exists():
        return defecto
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! no pude leer {ruta} ({e}); sigo como si no existiera")
        return defecto


# --------------------------------------------------------------------------- #
# Parámetros
# --------------------------------------------------------------------------- #

def cargar_parametros(carpeta: Path) -> dict:
    return leer_json(carpeta / "parametros.json", {})


def guardar_parametros(carpeta: Path, **valores) -> dict:
    """Mezcla los valores nuevos con los que ya había. None no pisa nada."""
    params = cargar_parametros(carpeta)
    params.update({k: v for k, v in valores.items() if v is not None})
    escribir_json(carpeta / "parametros.json", params)
    return params


def fecha_busqueda(carpeta: Path) -> str:
    """Cuándo se scrapeó el listado, no cuándo se rankeó.

    Las corridas viejas no tienen parametros.json: se toma la fecha de
    modificación de listado.json, que es la del último `buscar`.
    """
    params = cargar_parametros(carpeta)
    if params.get("fecha_busqueda"):
        return params["fecha_busqueda"]
    listado = carpeta / "listado.json"
    if listado.exists():
        return datetime.date.fromtimestamp(listado.stat().st_mtime).isoformat()
    return datetime.date.today().isoformat()


# --------------------------------------------------------------------------- #
# Detalle por aviso
# --------------------------------------------------------------------------- #

def guardar_detalle(carpeta: Path, aviso_id: str, detalle: dict) -> None:
    datos = dict(detalle)
    datos["fecha_detalle"] = datetime.date.today().isoformat()
    escribir_json(carpeta / "detalles" / f"{aviso_id}.json", datos)


def cargar_detalles(carpeta: Path) -> dict[str, dict]:
    salida: dict[str, dict] = {}
    dir_det = carpeta / "detalles"
    if not dir_det.exists():
        return salida
    for archivo in sorted(dir_det.glob("*.json")):
        datos = leer_json(archivo, None)
        if isinstance(datos, dict):
            salida[archivo.stem] = datos
    return salida


def detalle_fresco(detalle: dict | None, dias: int = DIAS_DETALLE_FRESCO) -> bool:
    if not detalle or not detalle.get("fecha_detalle"):
        return False
    try:
        fecha = datetime.date.fromisoformat(detalle["fecha_detalle"])
    except ValueError:
        return False
    return (datetime.date.today() - fecha).days < dias


# Lo que las corridas viejas tenían sólo dentro de ranking.json. Se sigue
# rescatando de ahí para las carpetas que todavía no tienen detalles/.
_CAMPOS_DETALLE_LEGADO = (
    "antiguedad", "orientacion", "disposicion", "luminosidad",
    "descripcion_completa", "fotos_totales", "fotos_final_galeria",
    "amenities", "fecha_publicacion", "latitude", "longitude",
    "dias_publicado", "fotos",
)


def fusionar_detalles(carpeta: Path, avisos: list[dict]) -> int:
    """Le suma a cada aviso del listado lo que se sabe de su página de detalle.

    Devuelve cuántos avisos quedaron con detalle.
    """
    detalles = cargar_detalles(carpeta)
    previos: dict[str, dict] = {}
    if (carpeta / "ranking.json").exists():
        crudo = leer_json(carpeta / "ranking.json", [])
        previos = {a["id"]: a for a in crudo if isinstance(a, dict) and a.get("id")}

    con_detalle = 0
    for a in avisos:
        aid = str(a.get("id"))
        prev = previos.get(aid)
        if prev:
            for k in _CAMPOS_DETALLE_LEGADO:
                if prev.get(k) is not None and prev.get(k) != []:
                    a[k] = prev[k]
        det = detalles.get(aid)
        if det:
            for k, v in det.items():
                if v is not None:
                    a[k] = v
            con_detalle += 1
        elif prev and prev.get("descripcion_completa"):
            con_detalle += 1
    return con_detalle


# --------------------------------------------------------------------------- #
# Puntuación
# --------------------------------------------------------------------------- #

def puntuar_corrida(carpeta: Path, avisos: list[dict], presupuesto: float | None,
                    dolar: float) -> list[dict]:
    """Puntúa con el historial y los parámetros de la corrida. Es la única
    puerta de entrada a scoring.puntuar desde la CLI."""
    from zp import historial as mod_historial

    params = cargar_parametros(carpeta)
    fecha = fecha_busqueda(carpeta)
    # Registrar es idempotente por fecha de búsqueda, así que da lo mismo que
    # lo llame `rankear` o `fotos`, o las dos pasadas de `rankear`. La
    # comparación de precios mira sólo snapshots de búsquedas anteriores.
    mod_historial.registrar(carpeta, avisos, fecha=fecha)
    hist = mod_historial.cargar(carpeta)
    ordenados = scoring.puntuar(
        avisos,
        presupuesto=presupuesto,
        dolar=dolar,
        historial=mod_historial.ultimo_precio(hist, antes_de=fecha),
        ambientes_buscados=params.get("ambientes"),
    )
    for a in ordenados:
        # Se recalcula siempre: un ranking viejo puede traer una nota que ya no aplica.
        a.pop("nota_historial", None)
        nota = mod_historial.resumen_bajas(hist, str(a.get("id")))
        if nota:
            a["nota_historial"] = nota
    return ordenados
