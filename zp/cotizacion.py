"""Módulo de cotización del dólar blue con consulta a API externa y caché persistente."""

from __future__ import annotations

import datetime
import json
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CACHE_FILE = RAIZ / "salida" / ".cotizacion.json"
URL_DOLAR_BLUE = "https://dolarapi.com/v1/dolares/blue"
DOLAR_FALLBACK = 1450.0
TIMEOUT_SEGUNDOS = 5


def _guardar_cache(datos: dict) -> None:
    """Escribe la caché en disco de forma segura sin interrumpir la ejecución ante errores."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  [cotizacion] Error al guardar caché en disco ({e}); continuando.")


def obtener_dolar(forzar: bool = False, solo_cache: bool = False) -> tuple[float, str]:
    """Obtiene la cotización del dólar blue (venta) en pesos argentinos.

    Devuelve una tupla (valor, origen), donde origen puede ser:
    - 'caché de hoy': leído del archivo de caché del día actual.
    - 'api': consultado exitosamente a DolarApi.
    - 'fallback': valor por defecto ante fallos de red o datos inválidos.

    `solo_cache=True` nunca toca la red: devuelve la caché del día si está, y
    si no el fallback. Es para el menú, que se dibuja al arrancar: sin caché y
    sin internet, una consulta bloquearía la ventana hasta 5 segundos antes de
    mostrar nada. El valor de verdad se resuelve igual cuando corre `rankear`.
    """
    hoy = datetime.date.today().isoformat()

    # 1. Caché persistente del día
    if not forzar and CACHE_FILE.exists():
        try:
            datos_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            fecha = datos_cache.get("fecha")
            valor = datos_cache.get("valor")
            if fecha == hoy and valor is not None:
                v = float(valor)
                if 100.0 <= v <= 100000.0:
                    return v, "caché de hoy"
        except Exception as e:
            print(f"  [cotizacion] Error al leer caché existente ({e}); se consultará la red.")

    if solo_cache:
        return DOLAR_FALLBACK, "fallback"

    # 2. Consulta a la API externa
    try:
        req = urllib.request.Request(
            URL_DOLAR_BLUE,
            headers={
                "User-Agent": "ZonapropForensicAuditor/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEGUNDOS) as resp:
            cuerpo = resp.read().decode("utf-8")
            data = json.loads(cuerpo)
            venta = data.get("venta")
            if venta is not None:
                v = float(venta)
                if 100.0 <= v <= 100000.0:
                    _guardar_cache({"fecha": hoy, "valor": v})
                    return v, "api"
                print(f"  [cotizacion] Cotización fuera de rango plausible ({v}); usando fallback.")
            else:
                print("  [cotizacion] La respuesta de la API no contiene el campo 'venta'; usando fallback.")
    except Exception as e:
        # Fallback silencioso ante corte de red, timeout o respuesta no parseable
        return DOLAR_FALLBACK, "fallback"

    return DOLAR_FALLBACK, "fallback"
