"""Parseo del HTML de Zonaprop: página de listado y página de detalle.

Todo lo que se extrae acá sale de dos lugares estables:
  - Las tarjetas del listado, marcadas con atributos data-qa (POSTING_CARD_*).
  - El JSON embebido de la página de detalle, del que sacamos la galería completa
    y las "mainFeatures" (antigüedad, orientación, disposición, luminosidad).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict

from selectolax.parser import HTMLParser

# --------------------------------------------------------------------------- #
# Listado
# --------------------------------------------------------------------------- #

_NUM = re.compile(r"[\d.]+")


def _num(texto: str | None) -> float | None:
    """'$ 890.000' -> 890000.0 ; '100 m² tot.' -> 100.0"""
    if not texto:
        return None
    m = _NUM.search(texto.replace(",", "."))
    if not m:
        return None
    crudo = m.group(0)
    # Los miles van con punto en es-AR; si hay más de un punto o el bloque final
    # tiene 3 dígitos, son separadores de miles.
    if crudo.count(".") >= 1 and len(crudo.split(".")[-1]) == 3:
        crudo = crudo.replace(".", "")
    try:
        return float(crudo)
    except ValueError:
        return None


@dataclass
class Aviso:
    id: str
    url: str = ""
    titulo: str = ""
    tipo: str = "departamento"   # 'departamento', 'ph', 'casa'
    precio: float | None = None
    moneda: str = ""
    expensas: float | None = None
    # None = el aviso no informa; 0.0 = el aviso dice explícitamente que no paga.
    # No es lo mismo y confundirlos premiaba a los que ocultan el dato.
    expensas_informadas: bool = False
    m2_total: float | None = None
    m2_cubierto: float | None = None
    ambientes: int | None = None
    dormitorios: int | None = None
    banos: int | None = None
    cocheras: int | None = None
    direccion: str = ""
    barrio: str = ""
    publicador: str = ""
    descripcion: str = ""
    destacado: str = ""          # 'Luminoso', 'Terraza', etc. (badge de la tarjeta)
    fotos: list = field(default_factory=list)
    # Se completan en la etapa de detalle:
    antiguedad: str = ""
    orientacion: str = ""
    disposicion: str = ""
    luminosidad: str = ""
    descripcion_completa: str = ""
    fecha_publicacion: str = ""
    latitude: float | None = None
    longitude: float | None = None
    # Campos estructurados para diagnóstico LLM:
    garantias_aceptadas: list[str] = field(default_factory=list)
    politica_mascotas: str = ""
    ajuste_frecuencia: str = ""
    ajuste_indice: str = ""
    deposito_monto: str = ""
    plazo_contrato: str = ""
    costos_adicionales: list[str] = field(default_factory=list)
    dias_publicado: int | None = None
    preguntas_visita: list[str] = field(default_factory=list)

    def dict(self):
        return asdict(self)


def _qa(nodo, valor: str) -> str:
    el = nodo.css_first(f'[data-qa="{valor}"]')
    return el.text(separator=" ", strip=True) if el else ""


def detectar_tipo(url: str = "", titulo: str = "", texto: str = "") -> str:
    """Clasifica el tipo de propiedad: 'ph', 'casa' o 'departamento'."""
    u = url.lower()
    if "alclphin" in u:
        return "ph"
    if "alclcain" in u:
        return "casa"
    if "alclapin" in u:
        return "departamento"

    combinado = f"{titulo} {texto} {url}".lower()
    if re.search(r"\bph\b|\btipo\s+casa\b", combinado):
        return "ph"
    if re.search(r"\bcasa\b|\bchalet\b|\bduplex\b|\btriplex\b|\btownhouse\b", combinado):
        return "casa"
    return "departamento"


def parsear_listado(html: str) -> list[Aviso]:
    """Devuelve los avisos de una página de resultados."""
    doc = HTMLParser(html)
    avisos: list[Aviso] = []

    for card in doc.css('[data-qa="posting PROPERTY"]'):
        pid = card.attributes.get("data-id") or ""
        if not pid:
            continue

        href = card.attributes.get("data-to-posting") or ""
        if not href:
            a = card.css_first("a[href]")
            href = a.attributes.get("href", "") if a else ""
        url = href if href.startswith("http") else f"https://www.zonaprop.com.ar{href}"

        precio_txt = _qa(card, "POSTING_CARD_PRICE")
        moneda = "USD" if "USD" in precio_txt.upper() else ("ARS" if "$" in precio_txt else "")

        feats = _qa(card, "POSTING_CARD_FEATURES")
        desc_card = _qa(card, "POSTING_CARD_DESCRIPTION")

        h2 = card.css_first("h2, h3")
        titulo = h2.text(strip=True) if h2 else ""

        tipo = detectar_tipo(url, titulo, desc_card)
        expensas, informadas = _leer_expensas(
            _qa(card, "expensas"), desc_card, titulo=titulo, url=url, tipo=tipo
        )
        # 'Consultar precio' y similares quedan con precio None y se filtran después.
        av = Aviso(
            id=pid,
            url=url,
            titulo=titulo,
            tipo=tipo,
            precio=_num(precio_txt),
            moneda=moneda,
            expensas=expensas,
            expensas_informadas=informadas,
            m2_total=_extraer_feature(feats, r"([\d.,]+)\s*m²\s*tot"),
            m2_cubierto=_extraer_feature(feats, r"([\d.,]+)\s*m²\s*cub"),
            ambientes=_int(_extraer_feature(feats, r"([\d.,]+)\s*amb")),
            dormitorios=_int(_extraer_feature(feats, r"([\d.,]+)\s*dorm")),
            banos=_int(_extraer_feature(feats, r"([\d.,]+)\s*baño")),
            cocheras=_int(_extraer_feature(feats, r"([\d.,]+)\s*coch")),
            barrio=_qa(card, "POSTING_CARD_LOCATION"),
            publicador=_qa(card, "POSTING_CARD_PUBLISHER"),
            descripcion=desc_card,
        )

        dir_el = card.css_first('[class*="location-address"]')
        if dir_el:
            av.direccion = dir_el.text(strip=True)

        badge = card.css_first('[class*="highlight"], [class*="badge"]')
        if badge:
            av.destacado = badge.text(strip=True)

        av.fotos = [
            img.attributes.get("src") or img.attributes.get("data-src") or ""
            for img in card.css('[data-qa="POSTING_CARD_GALLERY"] img')
        ]
        av.fotos = [f for f in av.fotos if f.startswith("http")]

        avisos.append(av)

    return avisos


# Frases con las que un aviso declara que no hay expensas. Solo con una de estas
# el 0 es un 0 de verdad; si no, el dato falta y hay que estimarlo.
_RE_SIN_EXPENSAS = re.compile(
    r"sin\s+expensas|no\s+paga\s+expensas|expensas\s*:?\s*\$?\s*0(?!\d)|"
    r"expensas\s+incluidas|no\s+posee\s+expensas|libre\s+de\s+expensas|"
    r"no\s+tiene\s+expensas|sin\s+gastos\s+comunes|no\s+abona\s+expensas|"
    r"sin\s+exp\b",
    re.IGNORECASE,
)


def _leer_expensas(
    texto_expensas: str,
    descripcion: str,
    titulo: str = "",
    url: str = "",
    tipo: str = "",
) -> tuple[float | None, bool]:
    """Devuelve (monto, informado).

    - El aviso publica un monto      -> (monto, True)
    - El aviso dice 'sin expensas'   -> (0.0, True)
    - El aviso no dice nada          -> (None, False)   <- NO es cero
    """
    monto = _num(texto_expensas)
    if monto:
        return monto, True
    todo = f"{texto_expensas} {titulo} {url} {descripcion}"
    if _RE_SIN_EXPENSAS.search(todo):
        return 0.0, True
    return None, False


def _extraer_feature(texto: str, patron: str) -> float | None:
    m = re.search(patron, texto, re.IGNORECASE)
    return _num(m.group(1)) if m else None


def _int(v):
    return int(v) if v is not None else None


def titulo_busqueda(html: str) -> str:
    """El h1, que es donde Zonaprop dice qué zona entendió que le pediste."""
    doc = HTMLParser(html)
    h1 = doc.css_first("h1")
    return h1.text(strip=True) if h1 else ""


def total_resultados(html: str) -> int | None:
    doc = HTMLParser(html)
    h1 = doc.css_first("h1")
    if not h1:
        return None
    m = re.search(r"([\d.]+)", h1.text())
    return int(m.group(1).replace(".", "")) if m else None


# --------------------------------------------------------------------------- #
# Detalle
# --------------------------------------------------------------------------- #

_RE_FOTOS = re.compile(r'"resizeUrl1200x1200":"([^"]+)"')
_RE_FEATURE = re.compile(
    r'"label":"([^"]{1,40})","measure":(?:"[^"]*"|null),"value":"([^"]{0,60})"'
)

# Cómo se llama cada label en el JSON -> campo del Aviso.
_MAPA_FEATURES = {
    "antigüedad": "antiguedad",
    "antiguedad": "antiguedad",
    "orientación": "orientacion",
    "disposición": "disposicion",
    "luminosidad": "luminosidad",
}


def parsear_dias_publicado(texto: str | None) -> int | None:
    """Parsea expresiones relativas de antigüedad de publicación a días como entero.

    Variantes soportadas:
      - 'hoy' / 'publicado hoy' -> 0
      - 'ayer' / 'publicado ayer' -> 1
      - 'hace 1 dia' / 'hace 1 día' / 'hace un dia' -> 1
      - 'hace N dias' / 'hace N días' -> N
      - 'hace mas de un anio' / 'hace más de un año' / 'mas de 1 anio' -> 365
    Tolerante a mayúsculas y tildes presentes o ausentes.
    Si no parsea devuelve None (nunca 0, que representaría 'hoy').
    """
    if not texto:
        return None
    t = texto.strip().lower()

    # Más de un año / años (con o sin tilde, anio o año)
    if re.search(r"m[aá]s\s+de\s+(?:un|1)\s+a(?:[nñ]|ni)os?", t):
        return 365
    m_anios = re.search(r"m[aá]s\s+de\s+(\d+)\s+a(?:[nñ]|ni)os?", t)
    if m_anios:
        return int(m_anios.group(1)) * 365

    # Hoy / ayer (palabra completa)
    if re.search(r"\bhoy\b", t):
        return 0
    if re.search(r"\bayer\b", t):
        return 1

    # Hace N días / hace N dias / N días / N dias
    m_dias = re.search(r"(?:hace\s+)?(\d+)\s+d[ií]as?", t)
    if m_dias:
        return int(m_dias.group(1))

    # Hace un día / hace un dia
    if re.search(r"hace\s+un\s+d[ií]a", t):
        return 1

    return None


def parsear_detalle(html: str) -> dict:
    """Extrae del detalle: galería completa, features, descripción larga y días de publicación."""
    fotos = []
    vistas = set()
    for u in _RE_FOTOS.findall(html):
        u = u.encode().decode("unicode_escape")
        base = u.split("?")[0]
        if base not in vistas:
            vistas.add(base)
            fotos.append(u)

    datos = {"fotos": fotos}

    for label, valor in _RE_FEATURE.findall(html):
        campo = _MAPA_FEATURES.get(label.strip().lower())
        if campo:
            datos[campo] = valor.strip()

    # Zonaprop NO publica coordenadas en el HTML del detalle (verificado en
    # septiembre de 2026 contra tests/capturas/detalle-51264287-2026-09.html.gz);
    # por eso las coordenadas salen de zp/geocodificador.py via Nominatim sobre la
    # direccion; si alguien ve un campo de coordenadas, confirmarlo contra una
    # captura antes de reactivar nada.

    doc = HTMLParser(html)

    # Días desde la publicación:
    # 1) Vía selector CSS buscando el prefijo de clase userViews-module__post-antiquity-views
    # 2) Fallback por regex sobre el texto plano del HTML buscando 'Publicado...'
    dias_pub = None
    el_antiguedad = doc.css_first('[class*="userViews-module__post-antiquity-views"]')
    if el_antiguedad:
        dias_pub = parsear_dias_publicado(el_antiguedad.text(strip=True))

    if dias_pub is None:
        m_txt = re.search(r"publicad[oa]\s+([^\n<]{1,60})", html, re.IGNORECASE)
        if m_txt:
            dias_pub = parsear_dias_publicado(m_txt.group(0))

    datos["dias_publicado"] = dias_pub

    desc = doc.css_first("#longDescription") or doc.css_first('[class*="description"]')
    if desc:
        datos["descripcion_completa"] = desc.text(separator="\n", strip=True)
        if _RE_SIN_EXPENSAS.search(datos["descripcion_completa"]):
            datos["expensas"] = 0.0
            datos["expensas_informadas"] = True

    # Amenities / características generales del edificio, si están en el DOM.
    amen = [n.text(strip=True) for n in doc.css('[class*="general-features"] li')]
    if amen:
        datos["amenities"] = amen

    return datos
