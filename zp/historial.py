"""Historial de precios y de presencia de cada aviso entre búsquedas.

Por aviso guarda:

    snapshots     [{fecha, precio, moneda, expensas}] cada vez que cambia el precio
    primera_vez   fecha de la primera búsqueda en la que apareció
    ultima_vez    fecha de la última búsqueda en la que apareció
    direccion     para poder nombrar a los que ya no están

Las fechas son las de la BÚSQUEDA (cuándo se scrapeó), no las de `rankear`.
Antes se anotaba la fecha del día en que se rankeaba: un listado del 30/8
rankeado el 20/9 quedaba registrado como visto el 20/9.
"""

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
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [historial] Error al leer '{archivo}' ({e}); iniciando historial vacío.")
        return {}


def registrar(carpeta: Path, avisos: list[dict], fecha: str | None = None) -> None:
    """Anota la presencia de cada aviso y un snapshot si el precio cambió.

    `fecha` es la de la búsqueda; si un aviso trae `visto_en` (porque quedó de
    una búsqueda anterior que se cortó a mitad) se respeta esa.
    """
    historial = cargar(carpeta)
    fecha = fecha or datetime.date.today().isoformat()
    hubo_cambios = False

    for a in avisos:
        aviso_id = str(a.get("id") or "").strip()
        if not aviso_id:
            continue
        visto = a.get("visto_en") or fecha
        entrada = historial.setdefault(aviso_id, {"snapshots": []})
        snapshots = entrada.setdefault("snapshots", [])

        if "primera_vez" not in entrada:
            entrada["primera_vez"] = snapshots[0]["fecha"] if snapshots else visto
            hubo_cambios = True
        if entrada.get("ultima_vez", "") < visto:
            entrada["ultima_vez"] = visto
            hubo_cambios = True
        if a.get("direccion") and entrada.get("direccion") != a["direccion"]:
            entrada["direccion"] = a["direccion"]
            hubo_cambios = True

        precio = a.get("precio")
        if precio is None:
            continue
        moneda = (a.get("moneda") or "ARS").upper()
        nuevo = {"fecha": visto, "precio": precio, "moneda": moneda,
                 "expensas": a.get("expensas")}
        if not snapshots:
            snapshots.append(nuevo)
            hubo_cambios = True
        else:
            ultimo = snapshots[-1]
            cambio_precio = ultimo.get("precio") != precio
            cambio_moneda = (ultimo.get("moneda") or "ARS") != moneda
            if (cambio_precio or cambio_moneda) and ultimo.get("fecha", "") <= visto:
                snapshots.append(nuevo)
                hubo_cambios = True

    archivo = carpeta / "historial.json"
    if hubo_cambios or not archivo.exists():
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            archivo.write_text(
                json.dumps(historial, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"  [historial] Error al escribir historial en '{archivo}' ({e}).")


def ultimo_precio(historial: dict, antes_de: str | None = None) -> dict:
    """Devuelve {'<id>': {'precio': N, 'moneda': 'ARS'}} para detectar_bajas_precio.

    Es el precio conocido ANTERIOR a la búsqueda que se está puntuando. Con
    `antes_de` se toma el último snapshot de una fecha previa; así da lo mismo
    puntuar antes o después de registrar la búsqueda de hoy (antes, `fotos`
    volvía a puntuar después de que `rankear` ya había registrado el precio de
    hoy, comparaba el precio contra sí mismo y la marca de baja se perdía).

    Sin `antes_de` se toma el último snapshot, que es el comportamiento de
    siempre: se carga el historial, se puntúa, y recién después se registra.
    Usar el penúltimo acá comparaba contra dos corridas atrás y reportaba una
    baja más grande de la real.
    """
    resultado = {}
    for aviso_id, datos in historial.items():
        snapshots = datos.get("snapshots", [])
        if antes_de:
            snapshots = [s for s in snapshots if s.get("fecha", "") < antes_de]
        if not snapshots:
            continue
        resultado[aviso_id] = {"precio": snapshots[-1]["precio"],
                               "moneda": snapshots[-1].get("moneda")}
    return resultado


def resumen_bajas(historial: dict, aviso_id: str) -> str | None:
    """Genera un resumen textual si el aviso bajó más de una vez en el tiempo.

    Ejemplo: 'bajó 3 veces en 40 días: $850.000 -> $700.000 (-18%)'.
    Si bajó una sola vez o ninguna, devuelve None. Sólo compara snapshots en
    la misma moneda: pasar de $900.000 a USD 650 no es una baja del 100%.
    """
    datos = historial.get(str(aviso_id))
    if not datos:
        return None
    snapshots = datos.get("snapshots", [])
    if snapshots:
        moneda_final = snapshots[-1].get("moneda") or "ARS"
        snapshots = [s for s in snapshots if (s.get("moneda") or "ARS") == moneda_final]
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
    except (KeyError, ValueError) as e:
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


def novedades(historial: dict, busquedas: list[dict]) -> dict | None:
    """Qué cambió entre la última búsqueda y la anterior.

    `busquedas` es la lista de parametros.json: [{fecha, completo}]. Devuelve
    None si todavía hay una sola búsqueda (no hay contra qué comparar).

    Los retirados sólo se informan si la última búsqueda terminó completa: si
    se cortó en la página 3, que un aviso no aparezca no dice nada.
    """
    fechas = sorted({b["fecha"] for b in busquedas if b.get("fecha")})
    if len(fechas) < 2:
        return None
    actual, anterior = fechas[-1], fechas[-2]
    completa = any(b.get("completo", True) for b in busquedas if b.get("fecha") == actual)

    nuevos, retirados, bajas, subas = [], [], [], []
    for aid, e in historial.items():
        if e.get("primera_vez") == actual:
            nuevos.append(aid)
        if completa and e.get("ultima_vez") == anterior:
            retirados.append({"id": aid, "direccion": e.get("direccion")})
        snaps = e.get("snapshots") or []
        if len(snaps) >= 2 and snaps[-1].get("fecha") == actual:
            prev, ult = snaps[-2], snaps[-1]
            if (prev.get("moneda") or "ARS") == (ult.get("moneda") or "ARS") and prev.get("precio"):
                cambio = {"id": aid, "antes": prev["precio"], "ahora": ult["precio"],
                          "moneda": ult.get("moneda") or "ARS",
                          "pct": round((ult["precio"] - prev["precio"]) / prev["precio"] * 100)}
                if ult["precio"] < prev["precio"]:
                    bajas.append(cambio)
                elif ult["precio"] > prev["precio"]:
                    subas.append(cambio)
    return {"actual": actual, "anterior": anterior, "completa": completa,
            "nuevos": nuevos, "retirados": retirados, "bajas": bajas, "subas": subas}
