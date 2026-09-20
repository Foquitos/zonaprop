"""Valores de referencia de mercado de Zonaprop Index (informe mensual).

Proporciona referencias objetivas de $/m² cubierto por mes para alquileres
sin expensas, desagregadas por región (CABA y GBA Norte) y cantidad de ambientes.
Sirve como ancla externa ("el afuera") para evitar sesgos al evaluar el valor
de mercado de las unidades.

Snapshot por defecto: agosto 2026.
Fuente: Informes mensuales Zonaprop Index (publicados en septiembre 2026).
"""

from __future__ import annotations

import io
import re
import unicodedata
import urllib.error
import urllib.request
from typing import Any

from zp import zonas

# --------------------------------------------------------------------------- #
# Snapshot bundleado (offline, sin dependencias)
# --------------------------------------------------------------------------- #
# Valores en $/m² CUBIERTO por mes, alquiler SIN expensas (agosto 2026).
# Derivados de tipologías estándar relevadas por Zonaprop:
#   CABA:
#     - Monoambiente: 40 m², $771.871 -> 18.378 $/m²
#     - 2 ambientes:  50 m², $886.527 -> 16.886 $/m²
#     - 3 ambientes:  70 m², $1.196.413 -> 16.278 $/m²
#   GBA Norte:
#     - 2 ambientes:  50 m², $819.219 -> 16.384 $/m²
#     - 3 ambientes:  70 m², $1.159.904 -> 15.781 $/m²
#
# Nota sobre monoambiente en GBA Norte: Zonaprop Index no releva tipología de 1 amb
# para GBA Norte. Para subsanar esto sin inventar arbitrariedades ni anular la
# corrección de sesgo, se extrapola aplicando el gradiente mono/2amb observado en CABA
# (18.378 / 16.886 ≈ +8.8357%), dando ~17.832 $/m².

FECHA_SNAPSHOT = "2026-08"

SNAPSHOT: dict[str, Any] = {
    "fecha": FECHA_SNAPSHOT,
    "regiones": {
        "caba": {
            1: 18378.0,
            2: 16886.0,
            3: 16278.0,
        },
        "gba_norte": {
            2: 16384.0,
            3: 15781.0,
        },
    },
    "fuente": "Zonaprop Index (informe mensual)",
    "muestras_originales": {
        "caba": {
            1: {"m2": 40, "balcon": 4, "precio": 771871},
            2: {"m2": 50, "balcon": 5, "precio": 886527},
            3: {"m2": 70, "balcon": 7, "precio": 1196413},
        },
        "gba_norte": {
            2: {"m2": 50, "balcon": 5, "precio": 819219},
            3: {"m2": 70, "balcon": 7, "precio": 1159904},
        },
    },
}

# Referencia sobre m² TOTALES, que es la única base comparable con lo que
# scrapeamos: verificado sobre 30 tarjetas reales, Zonaprop publica "50 m² tot."
# y NUNCA "m² cub." (0 de 30; y 0 de 369 avisos en las corridas guardadas). Si
# se usa la superficie cubierta como divisor, vs_zpindex se puede calcular para
# el 0% de los avisos.
#
# El $/m² que publica ZPIndex no sirve para esto porque su denominador es
# cubierta + balcón/2, la convención argentina de superficie computable
# (886.527 / 16.886 = 52,5 = 50 + 5/2). Acá no hace falta adivinar convenciones:
# se dividen el precio y las áreas que el informe publica, y queda una base de
# m² totales igual a la de las tarjetas.
REFERENCIA_TOTAL: dict[str, dict[int, float]] = {
    region: {
        amb: round(d["precio"] / (d["m2"] + d["balcon"]), 1)
        for amb, d in estratos.items()
    }
    for region, estratos in SNAPSHOT["muestras_originales"].items()
}


# --------------------------------------------------------------------------- #
# Mapeo de slugs de zonas a regiones ('caba' o 'gba_norte')
# --------------------------------------------------------------------------- #

def _norm_slug(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


_SLUGS_CABA: set[str] = {_norm_slug(z.slug) for z in zonas.CABA}
_SLUGS_GBA_NORTE: set[str] = {_norm_slug(z.slug) for z in zonas.GBA_NORTE}

_NOMBRES_CABA: set[str] = {_norm_slug(z.nombre) for z in zonas.CABA} | {_norm_slug(z.esperado) for z in zonas.CABA}
_NOMBRES_GBA_NORTE: set[str] = {_norm_slug(z.nombre) for z in zonas.GBA_NORTE} | {_norm_slug(z.esperado) for z in zonas.GBA_NORTE}


def region_de_zona(slug: str) -> str:
    """Mapea un slug o nombre del catálogo de zonas a 'caba' o 'gba_norte'.

    Cubre todo el catálogo de zp/zonas.py. Si no pertenece a ninguna región
    conocida, devuelve cadena vacía ("").
    """
    if not slug:
        return ""

    s = _norm_slug(slug)

    # 1. Búsqueda directa por slug o alias de región
    if s in _SLUGS_CABA or s in ("caba", "capital-federal", "capital"):
        return "caba"
    if s in _SLUGS_GBA_NORTE or s in ("gba-norte", "gba_norte", "gba"):
        return "gba_norte"

    # 2. Búsqueda por nombre o texto esperado exacto
    if s in _NOMBRES_CABA:
        return "caba"
    if s in _NOMBRES_GBA_NORTE:
        return "gba_norte"

    # 3. Subcadenas contra el catálogo (ej: si viene un texto como 'Florida, Vicente López')
    # Evaluamos primero GBA Norte porque varias localidades incluyen el partido 'vicente-lopez'
    for z in zonas.GBA_NORTE:
        z_s = _norm_slug(z.slug)
        if z_s and (z_s in s or s in z_s):
            return "gba_norte"
    for z in zonas.CABA:
        z_s = _norm_slug(z.slug)
        if z_s and (z_s in s or s in z_s):
            return "caba"

    # 4. Palabras clave generales
    if any(k in s for k in ("capital-federal", "caba", "capital", "buenos-aires-caba")):
        return "caba"
    if any(k in s for k in ("vicente-lopez", "san-isidro", "san-martin", "san-fernando", "tigre", "gba-norte")):
        return "gba_norte"

    return ""


# --------------------------------------------------------------------------- #
# Consulta de $/m² de referencia
# --------------------------------------------------------------------------- #

def referencia(region: str, ambientes: int) -> float | None:
    """Devuelve el $/m² cubierto de referencia para una región y cantidad de ambientes.

    Regiones válidas: 'caba' y 'gba_norte'.
    Si la región no está en el snapshot, devuelve None (nunca inventa regiones).

    Criterios de interpolación / extrapolación:
      - 1 amb en GBA Norte: el reporte oficial no releva monoambientes en GBA Norte.
        Se extrapola aplicando el gradiente mono/2amb de CABA (18.378 / 16.886 ≈ +8.84%),
        obteniendo 16.384 * 1.088357 ≈ 17.832 $/m². Usar el más cercano (16.384)
        dejaría el ratio en 1.0 y anularía el ajuste del sesgo de tamaño.
      - 4 o más ambientes: se toma el valor del estrato más cercano (3 amb).
      - Entre ambientes existentes (si se recibiera float): interpolación lineal.
    """
    if not region:
        return None

    reg = region.lower().strip().replace("-", "_")
    if reg not in SNAPSHOT["regiones"]:
        return None

    if ambientes is None or ambientes < 1:
        return None

    datos = SNAPSHOT["regiones"][reg]
    amb = int(round(ambientes))

    # Si existe el dato exacto
    if amb in datos:
        return float(datos[amb])

    # Extrapolación monoambiente en GBA Norte
    if reg == "gba_norte" and amb == 1:
        ref_2_gba = datos[2]
        ref_1_caba = SNAPSHOT["regiones"]["caba"][1]
        ref_2_caba = SNAPSHOT["regiones"]["caba"][2]
        return float(round(ref_2_gba * (ref_1_caba / ref_2_caba)))

    # Si supera el máximo relevado (ej: 4, 5 ambientes), usar el más cercano (3 amb)
    max_amb = max(datos.keys())
    if amb > max_amb:
        return float(datos[max_amb])

    min_amb = min(datos.keys())
    if amb < min_amb:
        return float(datos[min_amb])

    # Interpolación lineal si no es entero exacto
    claves = sorted(datos.keys())
    for i in range(len(claves) - 1):
        c1, c2 = claves[i], claves[i + 1]
        if c1 <= ambientes <= c2:
            v1, v2 = datos[c1], datos[c2]
            return float(v1 + (v2 - v1) * (ambientes - c1) / (c2 - c1))

    return None


def referencia_total(region: str, ambientes: int) -> float | None:
    """Igual que referencia(), pero en $/m² TOTALES en vez de cubiertos.

    Esta es la que sirve para comparar contra un aviso real: Zonaprop publica
    sólo la superficie total en las tarjetas, así que es el único divisor que
    existe en la práctica. Ver el comentario de REFERENCIA_TOTAL arriba.
    """
    if not region:
        return None
    reg = region.lower().strip().replace("-", "_")
    if reg not in REFERENCIA_TOTAL or ambientes is None or ambientes < 1:
        return None

    datos = REFERENCIA_TOTAL[reg]
    amb = int(round(ambientes))
    if amb in datos:
        return float(datos[amb])

    # Monoambiente en GBA Norte: no relevado. Se extrapola con el gradiente
    # mono/2amb de CABA, igual que en referencia().
    if reg == "gba_norte" and amb == 1:
        return float(round(datos[2] * (REFERENCIA_TOTAL["caba"][1] / REFERENCIA_TOTAL["caba"][2]), 1))

    if amb > max(datos):
        return float(datos[max(datos)])
    if amb < min(datos):
        return float(datos[min(datos)])
    return None


# --------------------------------------------------------------------------- #
# Actualización opcional desde informes PDF oficiales
# --------------------------------------------------------------------------- #

def _parsear_texto_pdf(texto: str, region: str) -> dict[int, float] | None:
    """Extrae valores de $/m² o precios de tipologías del texto del PDF."""
    resultado: dict[int, float] = {}

    # Patrones comunes en Zonaprop Index:
    # 1 ambiente / monoambiente: m2 y precio
    m_mono = re.search(r"(?:monoambiente|1\s*amb).*?(\d{2})\s*m²?.*?\$?\s*([\d.]+)", texto, re.IGNORECASE)
    if m_mono and region == "caba":
        m2 = float(m_mono.group(1))
        precio = float(m_mono.group(2).replace(".", ""))
        if m2 > 0 and precio > 100000:
            resultado[1] = round(precio / m2)

    # 2 ambientes
    m_2amb = re.search(r"2\s*amb.*?(\d{2})\s*m²?.*?\$?\s*([\d.]+)", texto, re.IGNORECASE)
    if m_2amb:
        m2 = float(m_2amb.group(1))
        precio = float(m_2amb.group(2).replace(".", ""))
        if m2 > 0 and precio > 100000:
            resultado[2] = round(precio / m2)

    # 3 ambientes
    m_3amb = re.search(r"3\s*amb.*?(\d{2})\s*m²?.*?\$?\s*([\d.]+)", texto, re.IGNORECASE)
    if m_3amb:
        m2 = float(m_3amb.group(1))
        precio = float(m_3amb.group(2).replace(".", ""))
        if m2 > 0 and precio > 100000:
            resultado[3] = round(precio / m2)

    return resultado if len(resultado) >= 2 else None


def actualizar(anio: int = 2026, mes: int = 8) -> dict | None:
    """Descarga los PDF oficiales de Zonaprop y actualiza los valores de referencia.

    Requiere `pypdf` (dependencia opcional en requirements-dev.txt).
    Si `pypdf` no está disponible o falla la conexión, emite un aviso descriptivo
    y conserva el snapshot bundleado sin interrumpir la ejecución.
    """
    try:
        import pypdf
    except ImportError:
        print("pypdf no está instalado. Para actualizar desde el PDF oficial, "
              "instalá pypdf (`pip install -r requirements-dev.txt`). "
              "Se mantiene el snapshot bundleado.")
        return None

    pub_mes = mes + 1
    pub_anio = anio
    if pub_mes > 12:
        pub_mes = 1
        pub_anio += 1

    pub_mm = f"{pub_mes:02d}"
    inf_mm = f"{mes:02d}"
    fecha_inf = f"{anio}-{inf_mm}"

    regiones_urls = {
        "caba": f"https://www.zonaprop.com.ar/blog/wp-content/uploads/{pub_anio}/{pub_mm}/INDEX_CABA_REPORTE_{fecha_inf}.pdf",
        "gba_norte": f"https://www.zonaprop.com.ar/blog/wp-content/uploads/{pub_anio}/{pub_mm}/INDEX_GBA_NORTE_REPORTE_{fecha_inf}.pdf",
    }

    nuevos_datos = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for reg, url in regiones_urls.items():
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                pdf_bytes = resp.read()
        except urllib.error.URLError as e:
            print(f"No se pudo descargar el informe ZPIndex para {reg} desde {url}: {e}. "
                  "Se mantiene el snapshot bundleado.")
            return None
        except Exception as e:
            print(f"Error al obtener {url} ({type(e).__name__}: {e}). "
                  "Se mantiene el snapshot bundleado.")
            return None

        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            texto_completo = "\n".join(pag.extract_text() or "" for pag in reader.pages)
            datos_reg = _parsear_texto_pdf(texto_completo, reg)
            if datos_reg:
                nuevos_datos[reg] = datos_reg
        except Exception as e:
            print(f"Error al procesar el PDF de {reg} con pypdf ({type(e).__name__}: {e}). "
                  "Se mantiene el snapshot bundleado.")
            return None

    if nuevos_datos:
        SNAPSHOT["fecha"] = fecha_inf
        SNAPSHOT["regiones"].update(nuevos_datos)
        print(f"ZPIndex actualizado exitosamente a fecha {fecha_inf}: {nuevos_datos}")
        return SNAPSHOT

    return None
