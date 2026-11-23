"""En qué quedó cada aviso: favorito, contactado, visita agendada, descartado.

Vive en `salida/seguimiento.json`, uno solo para todas las zonas: el mismo
aviso aparece en varias búsquedas (Vicente López contiene a Munro y a Villa
Martelli) y lo que se decidió sobre él vale en todas. Ninguna corrida lo
pisa: `buscar` y `rankear` lo leen, nunca lo escriben.

Se edita de tres maneras:
  - `python zp.py seguir <id> <estado> [--motivo ...]`
  - desde el dashboard (botones por aviso; se guarda en el navegador y se
    exporta con "Exportar seguimiento")
  - `python zp.py seguir --importar <archivo exportado>`
"""

from __future__ import annotations

import datetime
from pathlib import Path

from zp import corrida

ESTADOS = ("favorito", "contactado", "visita", "visitado", "descartado")
ETIQUETAS = {
    "favorito": "★ Favorito",
    "contactado": "Contactado",
    "visita": "Visita agendada",
    "visitado": "Visitado",
    "descartado": "Descartado",
}


def ruta(salida: Path) -> Path:
    return salida / "seguimiento.json"


def cargar(salida: Path) -> dict[str, dict]:
    datos = corrida.leer_json(ruta(salida), {})
    return datos if isinstance(datos, dict) else {}


def marcar(salida: Path, aviso_id: str, estado: str, motivo: str | None = None,
           nota: str | None = None, visita: str | None = None) -> dict:
    if estado not in ESTADOS and estado != "borrar":
        raise ValueError(f"estado desconocido: {estado!r}. Opciones: {', '.join(ESTADOS)} o borrar")
    datos = cargar(salida)
    if estado == "borrar":
        datos.pop(str(aviso_id), None)
        corrida.escribir_json(ruta(salida), datos)
        return {}
    entrada = datos.get(str(aviso_id), {})
    entrada.update({
        "estado": estado,
        "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    if motivo is not None:
        entrada["motivo"] = motivo
    if nota is not None:
        entrada["nota"] = nota
    if visita is not None:
        entrada["visita"] = visita
    datos[str(aviso_id)] = entrada
    corrida.escribir_json(ruta(salida), datos)
    return entrada


def importar(salida: Path, archivo: Path) -> tuple[int, int]:
    """Mezcla un seguimiento exportado del dashboard. Gana el cambio más nuevo.

    Devuelve (avisos actualizados, avisos ignorados por ser más viejos).
    """
    externo = corrida.leer_json(archivo, None)
    if not isinstance(externo, dict):
        raise ValueError(f"{archivo} no es un seguimiento exportado del dashboard")
    datos = cargar(salida)
    actualizados = ignorados = 0
    for aid, entrada in externo.items():
        # estado None = se desmarcó en el dashboard.
        if not isinstance(entrada, dict) or (entrada.get("estado") not in ESTADOS
                                             and entrada.get("estado") is not None):
            ignorados += 1
            continue
        actual = datos.get(str(aid))
        if actual and actual.get("fecha", "") >= entrada.get("fecha", ""):
            ignorados += 1
            continue
        if entrada.get("estado") is None:
            if datos.pop(str(aid), None) is not None:
                actualizados += 1
            continue
        datos[str(aid)] = entrada
        actualizados += 1
    corrida.escribir_json(ruta(salida), datos)
    return actualizados, ignorados


def anotar_avisos(salida: Path, avisos: list[dict]) -> int:
    """Le pega a cada aviso en memoria su estado (clave "seguimiento")."""
    datos = cargar(salida)
    n = 0
    for a in avisos:
        e = datos.get(str(a.get("id")))
        if e:
            a["seguimiento"] = e
            n += 1
        else:
            a.pop("seguimiento", None)
    return n


def estado(a: dict) -> str | None:
    return (a.get("seguimiento") or {}).get("estado")
