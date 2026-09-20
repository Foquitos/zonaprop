"""Historial de precios y snapshots para auditoría forense de bajas de precio."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from zp.comun import _plata


def cargar(carpeta: Path) -> dict:
    """Lee salida/<run>/historial.json. Si no existe o está corrupto, devuelve {}."""
    archivo = carpeta / "historial.json"
    if not archivo.exists():
        return {}
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [historial] Error al leer '{archivo}' ({e}); iniciando historial vacío.")
        return {}


def registrar(carpeta: Path, avisos: list[dict]) -> None:
    """Agrega un snapshot con la fecha de hoy si el precio cambió respecto del último."""
    historial = cargar(carpeta)
    hoy = datetime.date.today().isoformat()
    hubo_cambios = False

    for a in avisos:
        aviso_id = str(a.get("id") or "").strip()
        if not aviso_id:
            continue
        precio = a.get("precio")
        if precio is None:
            continue
        expensas = a.get("expensas")

        if aviso_id not in historial:
            historial[aviso_id] = {"snapshots": []}

        snapshots = historial[aviso_id].setdefault("snapshots", [])
        if not snapshots:
            snapshots.append({"fecha": hoy, "precio": precio, "expensas": expensas})
            hubo_cambios = True
        else:
            ultimo = snapshots[-1]
            if ultimo.get("precio") != precio:
                snapshots.append({"fecha": hoy, "precio": precio, "expensas": expensas})
                hubo_cambios = True

    archivo = carpeta / "historial.json"
    if hubo_cambios or not archivo.exists():
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            archivo.write_text(
                json.dumps(historial, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"  [historial] Error al escribir historial en '{archivo}' ({e}).")


def ultimo_precio(historial: dict) -> dict:
    """Devuelve el dict {'<id>': {'precio': N}} que espera detectar_bajas_precio.

    Toma el ÚLTIMO snapshot, no el penúltimo, y el motivo está en el orden de
    `cmd_rankear`: se carga el historial, se puntúa, y recién después se
    registra la corrida de hoy. O sea que mientras se puntúa, el historial
    todavía no contiene el precio de hoy: el último snapshot ES el precio
    conocido anterior, que es contra el que hay que comparar.

    Usar el penúltimo acá compara contra dos corridas atrás y reporta una baja
    más grande de la real: con 1000 -> 900 -> hoy 800, la baja reportable es
    del 11% contra los 900 de la corrida pasada, no del 20% contra los 1000
    de la primera.
    """
    resultado = {}
    for aviso_id, datos in historial.items():
        snapshots = datos.get("snapshots", [])
        if not snapshots:
            continue
        resultado[aviso_id] = {"precio": snapshots[-1]["precio"]}
    return resultado


def resumen_bajas(historial: dict, aviso_id: str) -> str | None:
    """Genera un resumen textual si el aviso bajó más de una vez en el tiempo.

    Ejemplo: 'bajó 3 veces en 40 días: $850.000 -> $700.000 (-18%)'.
    Si bajó una sola vez o ninguna, devuelve None.
    """
    datos = historial.get(str(aviso_id))
    if not datos:
        return None
    snapshots = datos.get("snapshots", [])
    if len(snapshots) < 3:
        # Se necesitan al menos 3 snapshots para registrar más de una baja
        return None

    bajas = 0
    for i in range(1, len(snapshots)):
        p_anterior = snapshots[i - 1].get("precio")
        p_actual = snapshots[i].get("precio")
        if p_anterior is not None and p_actual is not None and p_actual < p_anterior:
            bajas += 1

    if bajas <= 1:
        return None

    try:
        fecha_ini = datetime.date.fromisoformat(snapshots[0]["fecha"])
        fecha_fin = datetime.date.fromisoformat(snapshots[-1]["fecha"])
        dias = max(0, (fecha_fin - fecha_ini).days)
    except Exception as e:
        print(f"  [historial] Error al calcular intervalo de fechas para aviso {aviso_id} ({e}).")
        dias = 0

    p_inicial = snapshots[0].get("precio")
    p_final = snapshots[-1].get("precio")
    if p_inicial is None or p_final is None or p_inicial <= 0:
        return None

    diff = p_inicial - p_final
    pct = round((diff / p_inicial) * 100)
    dias_texto = f"{dias} días" if dias != 1 else "1 día"

    return f"bajó {bajas} veces en {dias_texto}: {_plata(p_inicial)} -> {_plata(p_final)} (-{pct}%)"
